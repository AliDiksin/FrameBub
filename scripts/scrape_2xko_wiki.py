"""2XKO wiki scrape.
Pulls frame data from the 2XKO wiki into 2XKO Frame Data.ods.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import scraper_utils
from scripts.generation_utils import normal_sheet_name, write_ods_sheets, write_python_constants  # noqa: E402
from scripts.scraper_utils import (  # noqa: E402
    TWOKO_CHAMPIONS,
    TWOKO_MOVE_COLUMNS,
    apply_heading_context,
    clean_wiki_text,
    extract_headings,
    extract_templates,
    file_url_for_name,
    parse_template,
    resolve_file_urls as shared_resolve_file_urls,
)


API_URL = "https://wiki.play2xko.com/en-us/api.php"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
IMAGE_THUMB_WIDTH = 300

CHAMPIONS = list(TWOKO_CHAMPIONS)
MOVE_COLUMNS = list(TWOKO_MOVE_COLUMNS)


def compact_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


class WikiFetcher:
    """Fetch wiki API responses; fall back to Playwright when Cloudflare blocks urllib."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._page = None

    def fetch_url(self, url: str, sleep_seconds: float = 0.1) -> str:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code != 403:
                raise
            body = self._fetch_with_playwright(url, sleep_seconds)
        else:
            if sleep_seconds:
                time.sleep(sleep_seconds)
        return body

    def _fetch_with_playwright(self, url: str, sleep_seconds: float) -> str:
        if self._page is None:
            from playwright.sync_api import sync_playwright

            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)
            self._page = self._browser.new_page()
            print("[2xko] using Playwright fallback for Cloudflare-blocked wiki API", flush=True)
        self._page.goto(url, wait_until="domcontentloaded", timeout=120000)
        time.sleep(max(1.0, sleep_seconds))
        return self._page.locator("body").inner_text()

    def close(self) -> None:
        if self._page is not None:
            self._page.close()
            self._page = None
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None


def fetch_url(url: str, sleep_seconds: float = 0.1, fetcher: WikiFetcher | None = None) -> str:
    if fetcher is not None:
        return fetcher.fetch_url(url, sleep_seconds=sleep_seconds)
    return scraper_utils.fetch_url(url, sleep_seconds=sleep_seconds)


def wiki_request(params: dict[str, object], sleep_seconds: float, fetcher: WikiFetcher | None = None) -> dict:
    query = urllib.parse.urlencode(params)
    return json.loads(fetch_url(f"{API_URL}?{query}", sleep_seconds=sleep_seconds, fetcher=fetcher))


def fetch_raw_page(page_title: str, sleep_seconds: float, fetcher: WikiFetcher | None = None) -> str:
    data = wiki_request(
        {
            "action": "query",
            "prop": "revisions",
            "titles": page_title,
            "rvprop": "content",
            "rvslots": "main",
            "format": "json",
            "formatversion": "2",
        },
        sleep_seconds,
        fetcher=fetcher,
    )
    pages = data.get("query", {}).get("pages", []) or []
    if not pages or pages[0].get("missing"):
        raise RuntimeError(f"Missing wiki page: {page_title}")
    revisions = pages[0].get("revisions") or []
    if not revisions:
        return ""
    slots = revisions[0].get("slots") or {}
    main_slot = slots.get("main") or {}
    return main_slot.get("content", "") or ""




def file_name_from_wikilink(value: str) -> str:
    text = str(value or "").strip()
    match = re.search(r"\[\[(?:File|Image):([^|\]]+)", text, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    text = re.sub(r"\([^)]*\)\s*$", "", text).strip()
    if text.lower().startswith(("file:", "image:")):
        return text.split(":", 1)[1].split("|", 1)[0].strip()
    if re.search(r"\.(?:png|webp|gif|jpg|jpeg)$", text, flags=re.IGNORECASE):
        return text.split("|", 1)[0].strip()
    return ""


def default_file_name(champion: str, move_name: str, input_text: str, suffix: str = "") -> str:
    label = move_name or input_text
    if not label:
        return ""
    return f"{champion}_{label}{suffix}.png"


def resolve_file_urls(filenames: list[str], sleep_seconds: float, fetcher: WikiFetcher | None = None) -> dict[str, str]:
    request_func = lambda _api_url, params, delay: wiki_request(params, delay, fetcher=fetcher)
    return shared_resolve_file_urls(API_URL, filenames, IMAGE_THUMB_WIDTH, sleep_seconds, request_func)


def split_moveinfo_templates(info_raw: str):
    return extract_templates(str(info_raw or ""), {"moveinfo", "move info"})


def parse_champion_page(champion: str, raw_text: str) -> tuple[list[dict[str, str]], list[tuple[str, str, str, str]]]:
    headings = extract_headings(raw_text)
    move_cards = extract_templates(raw_text, {"movenew", "move new"})
    apply_heading_context(move_cards, headings)
    rows: list[dict[str, str]] = []
    media: list[tuple[str, str, str, str]] = []
    char_key = champion.lower()

    for card in move_cards:
        params = card.params
        card_name = clean_wiki_text(params.get("name", ""))
        card_input = clean_wiki_text(params.get("input", ""))
        explicit_image = file_name_from_wikilink(params.get("image", ""))
        explicit_hitbox = file_name_from_wikilink(params.get("hitbox", ""))
        info_records = split_moveinfo_templates(params.get("info", ""))
        for info_record in info_records:
            _name, info = parse_template(info_record.raw)
            input_text = clean_wiki_text(info.get("input", "")) or card_input
            move_name = card_name or input_text
            if not input_text:
                continue
            description = clean_wiki_text(info.get("description", ""))
            row = {
                "char_key": char_key,
                "char_name": champion,
                "section": clean_wiki_text(card.section),
                "subsection": clean_wiki_text(card.subsection),
                "moveName": move_name,
                "numCmd": input_text,
                "dmg": clean_wiki_text(info.get("damage", "")),
                "guardLevel": clean_wiki_text(info.get("guard", "")),
                "startup": clean_wiki_text(info.get("startup", "")),
                "active": clean_wiki_text(info.get("active", "")),
                "recovery": clean_wiki_text(info.get("recovery", "")),
                "onBlock": clean_wiki_text(info.get("onblock", "")),
                "onHit": clean_wiki_text(info.get("onhit", "")),
                "meterGain": clean_wiki_text(info.get("metergain", "")),
                "xx": clean_wiki_text(info.get("cancel", "")),
                "invuln": clean_wiki_text(info.get("invuln", "")),
                "extraInfo": description,
            }
            rows.append(row)
            move_key = input_text
            image_file = explicit_image or default_file_name(champion, card_name, input_text)
            hitbox_file = explicit_hitbox or default_file_name(champion, card_name, input_text, "_Hitbox")
            if image_file:
                media.append((char_key, move_key, "image", image_file))
            if hitbox_file:
                media.append((char_key, move_key, "hitbox", hitbox_file))
    return rows, media


def write_cache(path: Path, media: list[tuple[str, str, str, str]], urls: dict[str, str]) -> tuple[int, int]:
    image_cache: dict[str, dict[str, str]] = {}
    hitbox_cache: dict[str, dict[str, list[str]]] = {}
    for char_key, move_key, media_type, filename in media:
        url = file_url_for_name(urls, filename)
        if not url:
            continue
        normalized_move = compact_key(move_key)
        if media_type == "image":
            image_cache.setdefault(char_key, {})[normalized_move] = url
        elif media_type == "hitbox":
            links = hitbox_cache.setdefault(char_key, {}).setdefault(normalized_move, [])
            if url not in links:
                links.append(url)
    write_python_constants(
        path,
        {"TUCO_MOVE_IMAGE_URLS": image_cache, "TUCO_HITBOX_DATA": hitbox_cache},
        "scrape_2xko_wiki.py",
    )
    return sum(len(moves) for moves in image_cache.values()), sum(len(links) for moves in hitbox_cache.values() for links in moves.values())


def build(output_workbook: Path, output_cache: Path, sleep_seconds: float) -> None:
    fetcher = WikiFetcher()
    all_rows: list[dict[str, str]] = []
    all_media: list[tuple[str, str, str, str]] = []
    try:
        for champion in CHAMPIONS:
            try:
                raw = fetch_raw_page(champion, sleep_seconds, fetcher=fetcher)
                rows, media = parse_champion_page(champion, raw)
            except Exception as exc:
                print(f"[2xko] skipped {champion}: {exc}", flush=True)
                continue
            all_rows.extend(rows)
            all_media.extend(media)
            print(f"[2xko] parsed {champion}: {len(rows)} moves", flush=True)

        if not all_rows:
            raise RuntimeError("No 2XKO rows were parsed.")

        sheets = {"Moves": all_rows}
        for champion in CHAMPIONS:
            char_rows = [row for row in all_rows if row.get("char_name") == champion]
            if char_rows:
                sheets[normal_sheet_name(champion)] = char_rows
        write_ods_sheets(output_workbook, sheets, MOVE_COLUMNS)

        urls = resolve_file_urls([item[3] for item in all_media], sleep_seconds, fetcher=fetcher)
        image_count, hitbox_count = write_cache(output_cache, all_media, urls)
        print(f"[2xko] wrote {output_workbook}: {len(all_rows)} rows", flush=True)
        print(f"[2xko] wrote {output_cache}: {image_count} images, {hitbox_count} hitboxes", flush=True)
    finally:
        fetcher.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build 2XKO frame data and remote image caches from the 2XKO wiki.")
    parser.add_argument("--output-workbook", default="2XKO Frame Data.ods")
    parser.add_argument("--output-cache", default="bubbot/data/tuco_move_images.py")
    parser.add_argument("--sleep", type=float, default=0.1)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build(Path(args.output_workbook), Path(args.output_cache), args.sleep)


if __name__ == "__main__":
    main()

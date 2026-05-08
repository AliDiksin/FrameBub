from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.scrape_ggst_dustloop import (  # noqa: E402
    apply_heading_context,
    clean_wiki_text,
    extract_headings,
    extract_templates,
    parse_template,
)


API_URL = "https://wiki.play2xko.com/en-us/api.php"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
IMAGE_THUMB_WIDTH = 300

CHAMPIONS = [
    "Ahri",
    "Akali",
    "Blitzcrank",
    "Braum",
    "Caitlyn",
    "Darius",
    "Ekko",
    "Illaoi",
    "Jinx",
    "Senna",
    "Teemo",
    "Vi",
    "Warwick",
    "Yasuo",
]

MOVE_COLUMNS = [
    "char_key",
    "char_name",
    "section",
    "subsection",
    "moveName",
    "numCmd",
    "dmg",
    "guardLevel",
    "startup",
    "active",
    "recovery",
    "onBlock",
    "onHit",
    "meterGain",
    "xx",
    "invuln",
    "extraInfo",
]


def compact_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def fetch_url(url: str, sleep_seconds: float = 0.1) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read().decode("utf-8")
    if sleep_seconds:
        time.sleep(sleep_seconds)
    return body


def wiki_request(params: dict[str, object], sleep_seconds: float) -> dict:
    query = urllib.parse.urlencode(params)
    return json.loads(fetch_url(f"{API_URL}?{query}", sleep_seconds=sleep_seconds))


def fetch_raw_page(page_title: str, sleep_seconds: float) -> str:
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


def chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


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


def resolve_file_urls(filenames: list[str], sleep_seconds: float) -> dict[str, str]:
    results: dict[str, str] = {}
    unique_names = []
    seen = set()
    for filename in filenames:
        clean_name = str(filename or "").strip().replace("_", " ")
        if not clean_name or clean_name.lower() in seen:
            continue
        seen.add(clean_name.lower())
        unique_names.append(clean_name)

    for batch in chunks(unique_names, 20):
        data = wiki_request(
            {
                "action": "query",
                "titles": "|".join(f"File:{name}" for name in batch),
                "prop": "imageinfo",
                "iiprop": "url",
                "iiurlwidth": IMAGE_THUMB_WIDTH,
                "format": "json",
            },
            sleep_seconds,
        )
        for page in (data.get("query", {}).get("pages", {}) or {}).values():
            title = str(page.get("title", ""))
            if page.get("missing") or not title.startswith("File:"):
                continue
            image_info = (page.get("imageinfo") or [{}])[0]
            url = image_info.get("thumburl") or image_info.get("url")
            if not url:
                continue
            filename = title.split(":", 1)[1]
            results[filename.lower()] = url
            results[filename.replace(" ", "_").lower()] = url
    return results


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
        url = urls.get(filename.lower()) or urls.get(filename.replace(" ", "_").lower())
        if not url:
            continue
        normalized_move = compact_key(move_key)
        if media_type == "image":
            image_cache.setdefault(char_key, {})[normalized_move] = url
        elif media_type == "hitbox":
            hitbox_cache.setdefault(char_key, {}).setdefault(normalized_move, [])
            if url not in hitbox_cache[char_key][normalized_move]:
                hitbox_cache[char_key][normalized_move].append(url)
    path.write_text(
        "# Generated by scrape_2xko_wiki.py. Do not edit by hand.\n"
        f"TUCO_MOVE_IMAGE_URLS = {json.dumps(image_cache, indent=2, sort_keys=True)}\n\n"
        f"TUCO_HITBOX_DATA = {json.dumps(hitbox_cache, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
    return sum(len(moves) for moves in image_cache.values()), sum(len(links) for moves in hitbox_cache.values() for links in moves.values())


def build(output_workbook: Path, output_cache: Path, sleep_seconds: float) -> None:
    all_rows: list[dict[str, str]] = []
    all_media: list[tuple[str, str, str, str]] = []
    for champion in CHAMPIONS:
        try:
            raw = fetch_raw_page(champion, sleep_seconds)
            rows, media = parse_champion_page(champion, raw)
        except Exception as exc:
            print(f"[2xko] skipped {champion}: {exc}", flush=True)
            continue
        all_rows.extend(rows)
        all_media.extend(media)
        print(f"[2xko] parsed {champion}: {len(rows)} moves", flush=True)

    if not all_rows:
        raise RuntimeError("No 2XKO rows were parsed.")

    with pd.ExcelWriter(output_workbook, engine="odf") as writer:
        pd.DataFrame(all_rows, columns=MOVE_COLUMNS).to_excel(writer, sheet_name="Moves", index=False)
        for champion in CHAMPIONS:
            char_rows = [row for row in all_rows if row.get("char_name") == champion]
            if char_rows:
                pd.DataFrame(char_rows, columns=MOVE_COLUMNS).to_excel(writer, sheet_name=f"{champion}Normal"[:31], index=False)

    urls = resolve_file_urls([item[3] for item in all_media], sleep_seconds)
    image_count, hitbox_count = write_cache(output_cache, all_media, urls)
    print(f"[2xko] wrote {output_workbook}: {len(all_rows)} rows", flush=True)
    print(f"[2xko] wrote {output_cache}: {image_count} images, {hitbox_count} hitboxes", flush=True)


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

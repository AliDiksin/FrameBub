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

from bubbot.frame_data.sfv_frame_data import normalize_key, normalize_move_token  # noqa: E402
from scripts.scrape_ggst_dustloop import extract_templates, parse_template  # noqa: E402


API_URL = "https://wiki.supercombo.gg/api.php"
PAGE_PREFIX = "Street Fighter V"
USER_AGENT = "Mozilla/5.0 (compatible; Bub SFV scraper/1.0)"
IMAGE_THUMB_WIDTH = 300


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


def cache_file_for_page(cache_dir: Path, page_title: str) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", page_title.replace("/", "__"))
    return cache_dir / f"{safe_name}.wiki"


def fetch_raw_page(page_title: str, sleep_seconds: float, cache_dir: Path | None = None, refresh: bool = False) -> str:
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_file_for_page(cache_dir, page_title)
        if cache_path.exists() and not refresh:
            return cache_path.read_text(encoding="utf-8")
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
    raw = ((revisions[0].get("slots") or {}).get("main") or {}).get("content", "") if revisions else ""
    if cache_dir is not None:
        cache_file_for_page(cache_dir, page_title).write_text(raw, encoding="utf-8")
    return raw


def clean_wiki_text(value: object) -> str:
    text = str(value or "")
    text = re.sub(r"<nowiki>(.*?)</nowiki>", r"\1", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?[^>]+>", "", text)
    text = re.sub(r"\[\[([^|\]]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", lambda match: match.group(1).split("/")[-1], text)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = text.replace("'''", "").replace("''", "")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def split_file_list(params: dict[str, str], prefix: str) -> list[str]:
    files = []
    for index in range(1, 11):
        key = prefix if index == 1 else f"{prefix}{index}"
        value = clean_wiki_text(params.get(key, ""))
        value = re.sub(r"^(?:File|Image):", "", value, flags=re.IGNORECASE).strip()
        if value and re.search(r"\.(?:png|webp|gif|jpg|jpeg)$", value, flags=re.IGNORECASE):
            files.append(value)
    return files


def caption_lines(params: dict[str, str], prefix: str) -> list[str]:
    lines = []
    for index in range(1, 11):
        key = prefix if index == 1 else f"{prefix}{index}"
        value = clean_wiki_text(params.get(key, ""))
        if value:
            lines.append(value)
    return lines


def parse_character(display_name: str, raw_text: str) -> tuple[list[tuple[str, str, str, str]], dict[str, dict[str, str]]]:
    char_key = normalize_key(display_name)
    media = []
    notes_cache: dict[str, dict[str, str]] = {}
    for move_record in extract_templates(raw_text, {"movedata"}):
        params = move_record.params
        move_name = clean_wiki_text(params.get("name", ""))
        num_cmd = clean_wiki_text(params.get("input", ""))
        move_key = normalize_move_token(num_cmd or move_name)
        if not move_key:
            continue
        for filename in split_file_list(params, "image"):
            media.append((char_key, move_key, "image", filename))
        for filename in split_file_list(params, "hitbox"):
            media.append((char_key, move_key, "hitbox", filename))
        notes = []
        notes.extend(caption_lines(params, "caption"))
        for attack_record in extract_templates(params.get("data", ""), {"attackdata-sfv"}):
            description = clean_wiki_text(attack_record.params.get("description", ""))
            if description:
                notes.append(description)
        if notes:
            notes_cache.setdefault(char_key, {})[move_key] = "\n".join(dict.fromkeys(notes))
    return media, notes_cache


def chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def resolve_file_urls(filenames: list[str], sleep_seconds: float) -> dict[str, str]:
    results = {}
    unique_names = list(dict.fromkeys(str(name or "").strip().replace("_", " ") for name in filenames if str(name or "").strip()))
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


def character_names_from_workbook(workbook: Path) -> list[str]:
    xls = pd.ExcelFile(workbook, engine="odf")
    names = []
    seen = set()
    for sheet in xls.sheet_names:
        if not sheet.endswith("Normal"):
            continue
        name = sheet[: -len("Normal")]
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def write_cache(path: Path, media: list[tuple[str, str, str, str]], notes_cache: dict[str, dict[str, str]], urls: dict[str, str]) -> tuple[int, int, int]:
    image_cache: dict[str, dict[str, str]] = {}
    hitbox_cache: dict[str, dict[str, list[str]]] = {}
    for char_key, move_key, media_type, filename in media:
        url = urls.get(filename.lower()) or urls.get(filename.replace("_", " ").lower()) or urls.get(filename.replace(" ", "_").lower())
        if not url:
            continue
        if media_type == "image":
            image_cache.setdefault(char_key, {}).setdefault(move_key, url)
        else:
            links = hitbox_cache.setdefault(char_key, {}).setdefault(move_key, [])
            if url not in links:
                links.append(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Generated by scrape_sfv_supercombo.py. Do not edit by hand.\n"
        f"SFV_MOVE_IMAGE_URLS = {json.dumps(image_cache, indent=2, sort_keys=True, ensure_ascii=True)}\n\n"
        f"SFV_HITBOX_DATA = {json.dumps(hitbox_cache, indent=2, sort_keys=True, ensure_ascii=True)}\n\n"
        f"SFV_MOVE_NOTES = {json.dumps(notes_cache, indent=2, sort_keys=True, ensure_ascii=True)}\n",
        encoding="utf-8",
    )
    return (
        sum(len(moves) for moves in image_cache.values()),
        sum(len(links) for moves in hitbox_cache.values() for links in moves.values()),
        sum(len(moves) for moves in notes_cache.values()),
    )


def build(workbook: Path, output_cache: Path, sleep_seconds: float, cache_dir: Path | None = None, refresh: bool = False) -> None:
    all_media = []
    all_notes = {}
    for display_name in character_names_from_workbook(workbook):
        page_title = f"{PAGE_PREFIX}/{display_name}"
        raw = fetch_raw_page(page_title, sleep_seconds=sleep_seconds, cache_dir=cache_dir, refresh=refresh)
        media, notes = parse_character(display_name, raw)
        all_media.extend(media)
        for key, moves in notes.items():
            all_notes.setdefault(key, {}).update(moves)
        print(f"[sfv-scrape] {display_name}: {len(media)} media refs", flush=True)
    urls = resolve_file_urls([filename for _char, _move, _kind, filename in all_media], sleep_seconds=sleep_seconds)
    image_count, hitbox_count, notes_count = write_cache(output_cache, all_media, all_notes, urls)
    print(f"[sfv-scrape] cache images={image_count} hitboxes={hitbox_count} notes={notes_count}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape SFV move images/notes from SuperCombo raw wikitext.")
    parser.add_argument("--workbook", default="SF5 Frame Data - FAT .ods", help="SFV workbook used for the character list")
    parser.add_argument("--output-cache", default="bubbot/data/sfv_move_images.py", help="Output generated image cache module")
    parser.add_argument("--sleep", type=float, default=0.1, help="Seconds to sleep after API requests")
    parser.add_argument("--cache-dir", default=".cache/sfv_supercombo", help="Raw page cache directory")
    parser.add_argument("--refresh", action="store_true", help="Refresh cached raw pages")
    args = parser.parse_args()
    build(
        Path(args.workbook),
        Path(args.output_cache),
        args.sleep,
        cache_dir=Path(args.cache_dir) if args.cache_dir else None,
        refresh=args.refresh,
    )


if __name__ == "__main__":
    main()

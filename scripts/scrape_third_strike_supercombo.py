"""Third Strike SuperCombo scrape.
Parses MoveData and AttackData templates into Third Strike Frame Data.ods.
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.generation_utils import normal_sheet_name, write_ods_sheets, write_python_constants  # noqa: E402
from scripts import scraper_utils  # noqa: E402
from scripts.scraper_utils import (  # noqa: E402
    extract_headings,
    extract_templates,
    file_url_for_name,
    indexed_parameter_values,
    normalize_move_cache_key,
    resolve_file_urls as shared_resolve_file_urls,
)


API_URL = "https://wiki.supercombo.gg/api.php"
PAGE_PREFIX = "Street Fighter 3: 3rd Strike"
IMAGE_THUMB_WIDTH = 300

CHARACTERS = [
    "Akuma",
    "Alex",
    "Chun-Li",
    "Dudley",
    "Elena",
    "Gill",
    "Hugo",
    "Ibuki",
    "Ken",
    "Makoto",
    "Necro",
    "Oro",
    "Q",
    "Remy",
    "Ryu",
    "Sean",
    "Twelve",
    "Urien",
    "Yang",
    "Yun",
]

MOVE_COLUMNS = [
    "char_key",
    "char_name",
    "source_page_title",
    "source_page_url",
    "section",
    "subsection",
    "moveType",
    "moveName",
    "numCmd",
    "version",
    "startup",
    "active",
    "recovery",
    "onBlock",
    "onHit",
    "onHitCrouch",
    "dmg",
    "stun",
    "karaDistance",
    "guardLevel",
    "parry",
    "cancel",
    "selfMeterWhiff",
    "selfMeterHit",
    "selfMeterBlock",
    "oppMeterHit",
    "oppMeterBlock",
    "extraInfo",
]

GENEI_JIN_STATE_KEY = "genei_jin"

SIMPLE_TEMPLATE_REPLACEMENTS = {
    "lp": "LP",
    "mp": "MP",
    "hp": "HP",
    "lk": "LK",
    "mk": "MK",
    "hk": "HK",
    "p": "P",
    "k": "K",
    "pp": "PP",
    "kk": "KK",
    "ex": "EX",
    "qcf": "236",
    "qcb": "214",
    "dp": "623",
    "rdp": "421",
    "hcf": "41236",
    "hcb": "63214",
    "360": "360",
    "720": "720",
    "u": "8",
    "d": "2",
    "f": "6",
    "b": "4",
    "uf": "9",
    "ub": "7",
    "df": "3",
    "db": "1",
}



def fetch_raw_page(page_title: str, sleep_seconds: float, cache_dir: Path | None = None, refresh: bool = False) -> str:
    return scraper_utils.fetch_text(
        page_title,
        sleep_seconds=sleep_seconds,
        cache_dir=cache_dir,
        refresh=refresh,
        api_url=API_URL,
    )


def page_url(page_title: str) -> str:
    encoded = urllib.parse.quote(page_title.replace(" ", "_"), safe="/:()-'.,[]")
    return f"https://wiki.supercombo.gg/w/{encoded}"


def char_key(display_name: str) -> str:
    text = str(display_name or "").strip().lower().replace("'", "")
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def expand_simple_templates(text: str) -> str:
    def repl(match):
        name = re.sub(r"[_\s]+", " ", match.group(1).strip().lower())
        return SIMPLE_TEMPLATE_REPLACEMENTS.get(name, "")

    return re.sub(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}", repl, str(text or ""))


def clean_wiki_text(value: object) -> str:
    text = expand_simple_templates(str(value or ""))
    text = re.sub(r"\{\{3S Button FAT\|[^{}]*\}\}", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(?:big|small|u|div|span|sup|sub|nowiki|includeonly|noinclude|font)[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[\[(?:File|Image):([^|\]]+)(?:\|[^\]]*)?\]\]", lambda match: match.group(1), text, flags=re.IGNORECASE)
    text = re.sub(r"\[\[([^|\]]+)\|([^\]]+)\]\]", lambda match: match.group(2), text)
    text = re.sub(r"\[\[([^\]]+)\]\]", lambda match: match.group(1).split("/")[-1], text)
    text = re.sub(r"\[https?://[^\s\]]+\s+([^\]]+)\]", lambda match: match.group(1), text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = text.replace("'''", "").replace("''", "")
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_input_text(value: object) -> str:
    text = clean_wiki_text(value)
    text = text.replace("＋", "+")
    text = re.sub(r"\s*\+\s*", "+", text)
    text = re.sub(r"(?i)\bclose\b", "cl", text)
    text = re.sub(r"(?i)\bcrouch(?:ing)?\b", "2", text)
    text = re.sub(r"(?i)\bjump(?:ing)?\b", "j.", text)
    text = re.sub(r"(?i)\bneutral jump\b", "8", text)
    text = text.replace("+", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def compact_move_key(value: object) -> str:
    return normalize_move_cache_key(value)


def cache_move_key_for_row(row: dict[str, str], state_key: str = "") -> str:
    base_key = compact_move_key(row.get("numCmd", ""))
    if state_key:
        return compact_move_key(f"{base_key} {state_key}")
    return base_key


def row_starts_yun_genei_jin(row: dict[str, str]) -> bool:
    if str(row.get("char_key", "")).strip().lower() != "yun":
        return False
    return compact_move_key(row.get("moveName", "")) == "geneijin" and "sa3" in compact_move_key(row.get("numCmd", ""))


def _heading_parts(heading) -> tuple[int, int, object] | None:
    if isinstance(heading, dict):
        level = heading.get("level", heading.get("heading_level"))
        heading_pos = heading.get("position", heading.get("start", heading.get("pos")))
        title = heading.get("title", heading.get("text", heading.get("heading", "")))
    else:
        try:
            level, heading_pos, title = heading[:3]
        except (TypeError, ValueError, IndexError):
            return None
    try:
        return int(level), int(heading_pos), title
    except (TypeError, ValueError):
        return None


def heading_before(headings: list, position: int, level: int) -> str:
    selected = ""
    for heading in headings:
        parts = _heading_parts(heading)
        if parts is None:
            continue
        heading_level, heading_pos, title = parts
        if heading_pos >= position:
            break
        if heading_level == level:
            selected = clean_wiki_text(title)
    return selected

def split_file_list_from_params(params: dict[str, str], prefix: str) -> list[str]:
    files = []
    for raw_value in indexed_parameter_values(params, prefix):
        value = clean_wiki_text(raw_value)
        value = re.sub(r"^(?:File|Image):", "", value, flags=re.IGNORECASE).strip()
        if value and re.search(r"\.(?:png|webp|gif|jpg|jpeg)$", value, flags=re.IGNORECASE):
            files.append(value)
    return files


def caption_lines(params: dict[str, str], prefix: str) -> list[str]:
    lines = []
    for raw_value in indexed_parameter_values(params, prefix):
        line = clean_wiki_text(raw_value)
        if line:
            lines.append(line)
    return lines

def clean_description(value: object) -> str:
    text = clean_wiki_text(value)
    lines = []
    for line in text.splitlines():
        clean = line.strip(" *\t")
        if clean:
            lines.append(clean)
    return "\n".join(dict.fromkeys(lines))


def row_from_attack(display_name: str, page_title: str, move_record, attack_record, move_type: str, move_heading: str) -> dict[str, str]:
    move_params = move_record.params
    attack_params = attack_record.params
    raw_input = normalize_input_text(move_params.get("input", ""))
    heading_input = normalize_input_text(move_heading)
    move_input = heading_input or raw_input
    if heading_input and (not re.search(r"\d", raw_input) or raw_input.upper() in {"LP", "MP", "HP", "LK", "MK", "HK", "P", "K"}):
        move_input = heading_input
    move_name = clean_wiki_text(move_params.get("name", "")) or move_input
    notes = []
    notes.extend(caption_lines(move_params, "caption"))
    notes.extend(caption_lines(move_params, "hitboxCaption"))
    description = clean_description(attack_params.get("description", ""))
    if description:
        notes.append(description)
    return {
        "char_key": char_key(display_name),
        "char_name": display_name,
        "source_page_title": page_title,
        "source_page_url": page_url(page_title),
        "section": "Frame Data",
        "subsection": move_type,
        "moveType": move_type,
        "moveName": move_name,
        "numCmd": move_input,
        "version": clean_wiki_text(attack_params.get("version", "")),
        "startup": clean_wiki_text(attack_params.get("startup", "")),
        "active": clean_wiki_text(attack_params.get("active", "")),
        "recovery": clean_wiki_text(attack_params.get("recovery", "")),
        "onBlock": clean_wiki_text(attack_params.get("onBlock", "")),
        "onHit": clean_wiki_text(attack_params.get("onHit", "")),
        "onHitCrouch": clean_wiki_text(attack_params.get("onHitCrouch", "")),
        "dmg": clean_wiki_text(attack_params.get("damage", "")),
        "stun": clean_wiki_text(attack_params.get("stun", "")),
        "karaDistance": clean_wiki_text(attack_params.get("karaDistance", "")),
        "guardLevel": clean_wiki_text(attack_params.get("guard", "")),
        "parry": clean_wiki_text(attack_params.get("parry", "")),
        "cancel": clean_wiki_text(attack_params.get("cancelOptions", "")),
        "selfMeterWhiff": clean_wiki_text(attack_params.get("selfMeterWhiff", "")),
        "selfMeterHit": clean_wiki_text(attack_params.get("selfMeterHit", "")),
        "selfMeterBlock": clean_wiki_text(attack_params.get("selfMeterBlock", "")),
        "oppMeterHit": clean_wiki_text(attack_params.get("oppMeterHit", "")),
        "oppMeterBlock": clean_wiki_text(attack_params.get("oppMeterBlock", "")),
        "extraInfo": "\n".join(dict.fromkeys(note for note in notes if note)),
    }


def parse_character(display_name: str, raw_text: str) -> tuple[list[dict[str, str]], list[tuple[str, str, str, str]], dict[str, dict[str, str]]]:
    page_title = f"{PAGE_PREFIX}/{display_name}"
    headings = extract_headings(raw_text)
    move_records = extract_templates(raw_text, {"movedata"})
    rows = []
    media = []
    notes_cache: dict[str, dict[str, str]] = {}
    key = char_key(display_name)
    in_yun_genei_jin = False
    for move_record in move_records:
        move_type = heading_before(headings, move_record.start, 4) or "Moves"
        move_heading = heading_before(headings, move_record.start, 5)
        attack_records = extract_templates(move_record.params.get("data", ""), {"attackdata-3s"})
        if not attack_records:
            continue
        images = split_file_list_from_params(move_record.params, "image")
        hitboxes = split_file_list_from_params(move_record.params, "hitbox")
        for attack_record in attack_records:
            row = row_from_attack(display_name, page_title, move_record, attack_record, move_type, move_heading)
            if not row["numCmd"]:
                continue
            state_key = GENEI_JIN_STATE_KEY if in_yun_genei_jin and key == "yun" else ""
            rows.append(row)
            move_key = cache_move_key_for_row(row, state_key=state_key)
            if row["extraInfo"]:
                notes_cache.setdefault(key, {})[move_key] = row["extraInfo"]
            for filename in images:
                media.append((key, move_key, "image", filename))
            for filename in hitboxes:
                media.append((key, move_key, "hitbox", filename))
            if row_starts_yun_genei_jin(row):
                in_yun_genei_jin = True
    return rows, media, notes_cache


def resolve_file_urls(filenames: list[str], sleep_seconds: float) -> dict[str, str]:
    return shared_resolve_file_urls(API_URL, filenames, IMAGE_THUMB_WIDTH, sleep_seconds)


def write_cache(path: Path, media: list[tuple[str, str, str, str]], notes_cache: dict[str, dict[str, str]], urls: dict[str, str]) -> tuple[int, int, int]:
    image_cache: dict[str, dict[str, str]] = {}
    hitbox_cache: dict[str, dict[str, list[str]]] = {}
    for key, move_key, media_type, filename in media:
        url = file_url_for_name(urls, filename)
        if not url:
            continue
        if media_type == "image":
            image_cache.setdefault(key, {}).setdefault(move_key, url)
        elif media_type == "hitbox":
            links = hitbox_cache.setdefault(key, {}).setdefault(move_key, [])
            if url not in links:
                links.append(url)
    write_python_constants(
        path,
        {
            "THIRD_STRIKE_MOVE_IMAGE_URLS": image_cache,
            "THIRD_STRIKE_HITBOX_DATA": hitbox_cache,
            "THIRD_STRIKE_MOVE_NOTES": notes_cache,
        },
        "scrape_third_strike_supercombo.py",
    )
    return (
        sum(len(moves) for moves in image_cache.values()),
        sum(len(links) for moves in hitbox_cache.values() for links in moves.values()),
        sum(len(moves) for moves in notes_cache.values()),
    )


def safe_sheet_name(display_name: str) -> str:
    return normal_sheet_name(display_name)



def build(output_workbook: Path, output_cache: Path, sleep_seconds: float, cache_dir: Path | None = None, refresh: bool = False) -> None:
    all_rows: list[dict[str, str]] = []
    all_media: list[tuple[str, str, str, str]] = []
    all_notes: dict[str, dict[str, str]] = {}
    rows_by_character: dict[str, list[dict[str, str]]] = {}
    for display_name in CHARACTERS:
        page_title = f"{PAGE_PREFIX}/{display_name}"
        raw = fetch_raw_page(page_title, sleep_seconds=sleep_seconds, cache_dir=cache_dir, refresh=refresh)
        rows, media, notes = parse_character(display_name, raw)
        rows_by_character[display_name] = rows
        all_rows.extend(rows)
        all_media.extend(media)
        for key, moves in notes.items():
            all_notes.setdefault(key, {}).update(moves)
        print(f"[third-strike-scrape] {display_name}: {len(rows)} rows, {len(media)} media refs", flush=True)

    if not all_rows:
        raise RuntimeError("No Third Strike rows scraped")

    sheets = {
        safe_sheet_name(display_name): rows_by_character.get(display_name, [])
        for display_name in CHARACTERS
        if rows_by_character.get(display_name)
    }
    write_ods_sheets(output_workbook, sheets, MOVE_COLUMNS)

    filenames = [filename for _key, _move_key, _media_type, filename in all_media]
    urls = resolve_file_urls(filenames, sleep_seconds=sleep_seconds)
    image_count, hitbox_count, notes_count = write_cache(output_cache, all_media, all_notes, urls)
    print(
        f"[third-strike-scrape] wrote {len(all_rows)} rows to {output_workbook}; "
        f"cache images={image_count} hitboxes={hitbox_count} notes={notes_count}",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Third Strike frame data from SuperCombo raw wikitext.")
    parser.add_argument("--output", default="Third Strike Frame Data.ods", help="Output ODS workbook path")
    parser.add_argument("--output-cache", default="bubbot/data/third_strike_move_images.py", help="Output generated image cache module")
    parser.add_argument("--sleep", type=float, default=0.1, help="Seconds to sleep after API requests")
    parser.add_argument("--cache-dir", default=".cache/third_strike_supercombo", help="Raw page cache directory")
    parser.add_argument("--refresh", action="store_true", help="Refresh cached raw pages")
    args = parser.parse_args()
    build(
        output_workbook=Path(args.output),
        output_cache=Path(args.output_cache),
        sleep_seconds=args.sleep,
        cache_dir=Path(args.cache_dir) if args.cache_dir else None,
        refresh=args.refresh,
    )


if __name__ == "__main__":
    main()

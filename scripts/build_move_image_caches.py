"""Builds generated move image URL caches in bubbot/data/.
Regenerates remote image, hitbox, and notes URL dicts for supported games.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from bubbot.data.ggst_aliases import GGST_PAGE_OVERRIDES
from bubbot.frame_data import ggst_frame_data
from bubbot.utils.mediawiki_images import mediawiki_thumb_url as shared_mediawiki_thumb_url
from bubbot.utils.text_utils import compact_key
from scripts import scraper_utils
from scripts.generation_utils import write_python_constants  # noqa: E402


SF6_API_URL = "https://wiki.supercombo.gg/api.php"
GGST_API_URL = "https://www.dustloop.com/wiki/api.php"
FRAME_IMAGE_THUMB_WIDTH = 220
SF6_BOTTOM_IMAGE_WIDTH = 262
GGST_MOVE_SHEET_SUFFIXES = [
    "Dragon Install",
    "Install",
    "Normal",
    "Spells",
    "Items",
    "L2",
    "L3",
    "BR",
]


def normalize_key(value: object) -> str:
    return compact_key(value)


def wiki_request(api_url: str, params: dict[str, object], sleep_seconds: float) -> dict:
    return scraper_utils.wiki_request(api_url, params, sleep_seconds)




def resolve_file_urls(api_url: str, filenames: list[str], thumb_width: int, sleep_seconds: float) -> dict[str, str]:
    return scraper_utils.resolve_file_urls(api_url, filenames, thumb_width, sleep_seconds)



def mediawiki_thumb_url(api_url: str, filename: str, thumb_width: int = FRAME_IMAGE_THUMB_WIDTH) -> str:
    return shared_mediawiki_thumb_url(api_url, filename, thumb_width)


def write_python_cache(path: Path, variable_name: str, data: dict) -> None:
    write_python_constants(path, {variable_name: data}, "build_move_image_caches.py")


def sf6_page_title(character_label: str) -> str:
    # Wiki page names keep dotted abbreviations as-is ("C.Viper", not "C._Viper").
    return f"Street_Fighter_6/{character_label.replace(' ', '_')}"


def fetch_sf6_page_images(character_label: str, sleep_seconds: float) -> list[str]:
    data = wiki_request(
        SF6_API_URL,
        {
            "action": "parse",
            "page": sf6_page_title(character_label),
            "prop": "images",
            "format": "json",
        },
        sleep_seconds,
    )
    return list((data.get("parse") or {}).get("images") or [])


def sf6_image_move_key(filename: str) -> str:
    stem = re.sub(r"\.(?:png|webp|gif|jpg|jpeg)$", "", filename, flags=re.IGNORECASE)
    if not stem.lower().startswith("sf6_"):
        return ""
    parts = stem.split("_")
    if len(parts) < 3:
        return ""
    suffix = "_".join(parts[2:])
    if any(token in suffix.lower() for token in ("hitbox", "icon", "portrait")):
        return ""
    return normalize_key(suffix)


def build_sf6_cache(workbook_path: Path, output_path: Path, sleep_seconds: float, resolve_urls: bool) -> int:
    xls = pd.ExcelFile(workbook_path, engine="odf")
    cache: dict[str, dict[str, str]] = {}
    filenames_to_resolve: list[str] = []
    pending: dict[tuple[str, str], str] = {}

    for sheet_name in xls.sheet_names:
        if not sheet_name.endswith("Normal"):
            continue
        character_label = sheet_name[: -len("Normal")].rstrip(".")
        df = pd.read_excel(xls, sheet_name=sheet_name).fillna("")
        row_keys = {normalize_key(row.get("numCmd")): str(row.get("numCmd", "")).strip() for row in df.to_dict("records")}
        if not row_keys:
            continue
        try:
            images = fetch_sf6_page_images(character_label, sleep_seconds)
        except Exception as exc:
            print(f"[sf6-images] skipped {character_label}: {exc}", flush=True)
            continue
        for image in images:
            move_key = sf6_image_move_key(image)
            if move_key not in row_keys:
                continue
            pending[(normalize_key(character_label), row_keys[move_key])] = image
            filenames_to_resolve.append(image)

    urls = resolve_file_urls(SF6_API_URL, filenames_to_resolve, thumb_width=SF6_BOTTOM_IMAGE_WIDTH, sleep_seconds=sleep_seconds) if resolve_urls else {}
    for (char_key, move_key), filename in pending.items():
        url = urls.get(filename.lower()) or urls.get(filename.replace(" ", "_").lower()) or mediawiki_thumb_url(SF6_API_URL, filename, thumb_width=SF6_BOTTOM_IMAGE_WIDTH)
        if not url:
            continue
        cache.setdefault(char_key, {})[move_key] = url

    write_python_cache(output_path, "SF6_MOVE_IMAGE_URLS", cache)
    return sum(len(moves) for moves in cache.values())


def ggst_page_title(character_label: str) -> str:
    page_name = GGST_PAGE_OVERRIDES.get(character_label, character_label.replace(" ", "_"))
    return f"GGST/{page_name}"


def fetch_ggst_page_images(character_label: str, sleep_seconds: float) -> list[str]:
    data = wiki_request(
        GGST_API_URL,
        {
            "action": "parse",
            "page": ggst_page_title(character_label),
            "prop": "images",
            "format": "json",
        },
        sleep_seconds,
    )
    return list((data.get("parse") or {}).get("images") or [])


def ggst_match_key(value: object) -> str:
    text = str(value or "").lower().replace("hs", "h")
    if "4d" in text and "6d" in text:
        air_throw = "air" in text or "j." in text or "j4d" in text or "j6d" in text
        return "j4dj6d" if air_throw else "4d6d"
    text = re.sub(r"\bor\b", "", text)
    text = re.sub(r"\(air ok\)|\(hold ok\)", "", text)
    return re.sub(r"[^a-z0-9]", "", text)


def split_ggst_filenames(value: object) -> list[str]:
    return [part.strip() for part in re.split(r"\s*;\s*", str(value or "")) if part.strip()]


def clean_ggst_notes_text(value: object) -> str:
    text = str(value or "").replace("�", "'").replace("’", "'").replace("‘", "'").strip()
    if not text:
        return ""
    lines = []
    for line in text.splitlines():
        if line.strip().lower().startswith("gatling options:"):
            continue
        lines.append(line.rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def build_ggst_notes_text(source_row: dict[str, object]) -> str:
    parts = []
    description = clean_ggst_notes_text(source_row.get("description_text"))
    notes = clean_ggst_notes_text(source_row.get("notes_text"))
    caption = clean_ggst_notes_text(source_row.get("caption_text"))
    if description:
        parts.append(description)
    if notes:
        parts.append(notes)
    if caption and caption not in parts:
        parts.append(caption)
    return "\n\n".join(parts).strip()


def ggst_sheet_character_label(sheet_name: str) -> str:
    if sheet_name in {"IdealSheetNormal", "TemplateNormal"} or sheet_name.endswith("Stats"):
        return ""
    for suffix in GGST_MOVE_SHEET_SUFFIXES:
        if sheet_name.endswith(suffix):
            return sheet_name[: -len(suffix)]
    return ""


def ggst_filename_move_key(filename: str, character_label: str, hitbox: bool) -> str:
    stem = re.sub(r"\.(?:png|webp|gif|jpg|jpeg)$", "", filename, flags=re.IGNORECASE)
    if not stem.lower().startswith(("ggst_", "gggst_")):
        return ""
    if any(token in stem.lower() for token in ("portrait", "icon", "navigation", "color")):
        return ""
    if hitbox != ("hitbox" in stem.lower()):
        return ""
    text = stem.lower()
    character_tokens = [character_label]
    if character_label in GGST_PAGE_OVERRIDES:
        character_tokens.append(GGST_PAGE_OVERRIDES[character_label].replace("_", " "))
    for token in sorted(character_tokens, key=len, reverse=True):
        compact = re.sub(r"[^a-z0-9]+", "_", token.lower()).strip("_")
        text = re.sub(rf"^ggg?st_{re.escape(compact)}_", "", text)
    text = re.sub(r"^ggg?st_[a-z0-9.\-]+_", "", text)
    text = re.sub(r"_?hitbox(?:_preview)?(?:_?\d+)?$", "", text)
    text = re.sub(r"_\d+$", "", text)
    text = text.replace("_", "")
    return ggst_frame_data.normalize_move_token(text)


def ggst_row_match_keys(row: dict[str, object]) -> set[str]:
    keys: set[str] = set()
    values = [row.get("numCmd", ""), row.get("dustloopKey", ""), row.get("moveName", "")]
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        keys.add(ggst_match_key(text))
        keys.add(ggst_match_key(ggst_frame_data.normalize_move_token(text)))
        for alt in ggst_frame_data.expand_or_command_alternatives(text):
            keys.add(ggst_match_key(alt))
            keys.add(ggst_match_key(ggst_frame_data.normalize_move_token(alt)))
    return {key for key in keys if key}


def ggst_image_match_keys(filename_key: str) -> set[str]:
    raw = str(filename_key or "").strip()
    keys = {ggst_match_key(raw)} if raw else set()
    if not raw:
        return keys
    variants = {raw}
    if "x" in raw.lower():
        variants.update(raw.lower().replace("x", button) for button in ("p", "k", "s", "h", "d"))
    for variant in variants:
        keys.add(ggst_match_key(variant))
        keys.add(ggst_match_key(ggst_frame_data.normalize_move_token(variant)))
    return {key for key in keys if key}


def build_ggst_cache(workbook_path: Path, output_path: Path, sleep_seconds: float, resolve_urls: bool) -> tuple[int, int]:
    def fetch(page_title: str, character_label: str) -> str:
        for attempt in range(3):
            try:
                return scraper_utils.fetch_text(page_title, sleep_seconds=sleep_seconds)
            except Exception:
                if attempt == 2:
                    raise
                print(f"[ggst-images] retrying {character_label}: {page_title}", flush=True)
        raise AssertionError("unreachable")

    xls = pd.ExcelFile(workbook_path, engine="odf")
    normal_pending: dict[tuple[str, str], str] = {}
    hitbox_pending: dict[tuple[str, str], list[str]] = {}
    notes_pending: dict[tuple[str, str], str] = {}
    source_cache: dict[str, list[dict[str, str]]] = {}
    filenames: list[str] = []

    for sheet_name in xls.sheet_names:
        character_label = ggst_sheet_character_label(sheet_name)
        if not character_label:
            continue
        char_key = ggst_frame_data.resolve_character_key(character_label) or character_label.strip().lower()
        df = pd.read_excel(xls, sheet_name=sheet_name).fillna("")
        row_index: dict[str, set[str]] = {}
        for row in df.to_dict("records"):
            num_cmd = str(row.get("numCmd", "")).strip()
            move_name = str(row.get("moveName", "")).strip()
            if not num_cmd or not move_name:
                continue
            move_key = ggst_frame_data.normalize_move_token(num_cmd)
            if move_key:
                for match_key in ggst_row_match_keys(row):
                    row_index.setdefault(match_key, set()).add(move_key)
        if not row_index:
            continue
        if {"images", "hitboxes"}.issubset(df.columns):
            for row in df.to_dict("records"):
                num_cmd = str(row.get("numCmd", "")).strip()
                if not num_cmd:
                    continue
                move_key = ggst_frame_data.normalize_move_token(num_cmd)
                image_files = split_ggst_filenames(row.get("images"))
                hitbox_files = split_ggst_filenames(row.get("hitboxes"))
                if image_files and (char_key, move_key) not in normal_pending:
                    normal_pending[(char_key, move_key)] = image_files[0]
                    filenames.append(image_files[0])
                if hitbox_files:
                    pending_hitboxes = hitbox_pending.setdefault((char_key, move_key), [])
                    for hitbox_file in hitbox_files:
                        if hitbox_file not in pending_hitboxes:
                            pending_hitboxes.append(hitbox_file)
                    filenames.extend(hitbox_files)
        try:
            main_page_title = ggst_page_title(character_label)
            source_moves = source_cache.get(main_page_title)
            if source_moves is None:
                data_page_title = f"{main_page_title}/Data"
                overview_raw = fetch(main_page_title, character_label)
                data_raw = fetch(data_page_title, character_label)
                _overview_row, description_rows = scraper_utils.parse_overview_page(
                    character_label,
                    character_label,
                    main_page_title,
                    overview_raw,
                )
                description_index = scraper_utils.build_description_index(description_rows)
                _stat_rows, source_moves = scraper_utils.parse_data_page(
                    character_label,
                    character_label,
                    data_page_title,
                    data_raw,
                    description_index,
                )
                source_cache[main_page_title] = source_moves
        except Exception as exc:
            raise RuntimeError(f"[ggst-images] failed {character_label}: {exc}") from exc

        for source_row in source_moves:
            source_keys = set()
            for value in (source_row.get("input", ""), source_row.get("name", "")):
                if str(value or "").strip():
                    source_keys.add(ggst_match_key(value))
                    source_keys.add(ggst_match_key(ggst_frame_data.normalize_move_token(value)))
            target_move_keys = set()
            for source_key in source_keys:
                target_move_keys.update(row_index.get(source_key, set()))
            if not target_move_keys:
                continue

            image_files = split_ggst_filenames(source_row.get("images"))
            hitbox_files = split_ggst_filenames(source_row.get("hitboxes"))
            notes_text = build_ggst_notes_text(source_row)
            for move_key in target_move_keys:
                if notes_text and (char_key, move_key) not in notes_pending:
                    notes_pending[(char_key, move_key)] = notes_text
                if image_files and (char_key, move_key) not in normal_pending:
                    normal_pending[(char_key, move_key)] = image_files[0]
                    filenames.append(image_files[0])
                if hitbox_files:
                    pending_hitboxes = hitbox_pending.setdefault((char_key, move_key), [])
                    for hitbox_file in hitbox_files:
                        if hitbox_file not in pending_hitboxes:
                            pending_hitboxes.append(hitbox_file)
                    filenames.extend(hitbox_files)

    urls = resolve_file_urls(GGST_API_URL, filenames, thumb_width=FRAME_IMAGE_THUMB_WIDTH, sleep_seconds=sleep_seconds) if resolve_urls else {}
    normal_cache = {}
    hitbox_cache = {}
    for (char_key, move_key), filename in normal_pending.items():
        url = scraper_utils.file_url_for_name(urls, filename) or mediawiki_thumb_url(GGST_API_URL, filename)
        if url:
            normal_cache.setdefault(char_key, {})[move_key] = url
    for (char_key, move_key), filenames_for_move in hitbox_pending.items():
        move_urls = [scraper_utils.file_url_for_name(urls, name) or mediawiki_thumb_url(GGST_API_URL, name) for name in filenames_for_move]
        move_urls = [url for url in move_urls if url]
        if move_urls:
            hitbox_cache.setdefault(char_key, {})[move_key] = move_urls
    notes_cache = {}
    for (char_key, move_key), notes_text in notes_pending.items():
        if notes_text:
            notes_cache.setdefault(char_key, {})[move_key] = notes_text

    write_python_constants(
        output_path,
        {
            "GGST_MOVE_IMAGE_URLS": normal_cache,
            "GGST_HITBOX_DATA": hitbox_cache,
            "GGST_MOVE_NOTES": notes_cache,
        },
        "build_move_image_caches.py",
    )
    return (
        sum(len(moves) for moves in normal_cache.values()),
        sum(len(links) for moves in hitbox_cache.values() for links in moves.values()),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build remote image URL caches for SF6 and GGST frame embeds.")
    parser.add_argument("--sf6-workbook", default="FAT - SF6 Frame Data.ods")
    parser.add_argument("--ggst-workbook", default="GGST Frame Data.ods")
    parser.add_argument("--sf6-output", default="bubbot/data/sf6_move_images.py")
    parser.add_argument("--ggst-output", default="bubbot/data/ggst_move_images.py")
    parser.add_argument("--sleep", type=float, default=0.1)
    parser.add_argument("--resolve-urls", action="store_true", help="Resolve file URLs through the wiki API instead of deriving direct thumbnail URLs locally.")
    parser.add_argument("--skip-sf6", action="store_true")
    parser.add_argument("--skip-ggst", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.skip_sf6:
        count = build_sf6_cache(Path(args.sf6_workbook), Path(args.sf6_output), args.sleep, args.resolve_urls)
        print(f"Wrote {args.sf6_output}: {count} SF6 move image links")
    if not args.skip_ggst:
        normal_count, hitbox_count = build_ggst_cache(Path(args.ggst_workbook), Path(args.ggst_output), args.sleep, args.resolve_urls)
        print(f"Wrote {args.ggst_output}: {normal_count} GGST move image links, {hitbox_count} GGST hitbox links")


if __name__ == "__main__":
    main()

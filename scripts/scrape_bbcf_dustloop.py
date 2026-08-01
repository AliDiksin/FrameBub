"""BBCF Dustloop raw /Data scrape to ODS.
Pulls MoveData-BBCF templates into BBCF Frame Data.ods.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.generation_utils import normal_sheet_name, write_ods_sheets, write_python_constants  # noqa: E402
from bubbot.utils.mediawiki_images import mediawiki_thumb_url  # noqa: E402
from scripts.scraper_utils import (  # noqa: E402
    apply_heading_context,
    clean_wiki_text,
    dustloop_char_key,
    dustloop_page_url,
    extract_headings,
    extract_templates,
    fetch_text,
    normalize_move_cache_key,
    split_mediawiki_files,
    split_note_lines as shared_split_note_lines,
)


DUSTLOOP_BASE = "https://www.dustloop.com/wiki"
IMAGE_THUMB_WIDTH = 300

BBCF_CHARACTERS = [
    ("Amane Nishiki", "BBCF/Amane_Nishiki/Data"),
    ("Arakune", "BBCF/Arakune/Data"),
    ("Azrael", "BBCF/Azrael/Data"),
    ("Bang Shishigami", "BBCF/Bang_Shishigami/Data"),
    ("Bullet", "BBCF/Bullet/Data"),
    ("Carl Clover", "BBCF/Carl_Clover/Data"),
    ("Celica A. Mercury", "BBCF/Celica_A._Mercury/Data"),
    ("Es", "BBCF/Es/Data"),
    ("Hakumen", "BBCF/Hakumen/Data"),
    ("Hazama", "BBCF/Hazama/Data"),
    ("Hibiki Kohaku", "BBCF/Hibiki_Kohaku/Data"),
    ("Iron Tager", "BBCF/Iron_Tager/Data"),
    ("Izanami", "BBCF/Izanami/Data"),
    ("Izayoi", "BBCF/Izayoi/Data"),
    ("Jin Kisaragi", "BBCF/Jin_Kisaragi/Data"),
    ("Jubei", "BBCF/Jubei/Data"),
    ("Kagura Mutsuki", "BBCF/Kagura_Mutsuki/Data"),
    ("Kokonoe", "BBCF/Kokonoe/Data"),
    ("Lambda-11", "BBCF/Lambda-11/Data"),
    ("Litchi Faye Ling", "BBCF/Litchi_Faye_Ling/Data"),
    ("Mai Natsume", "BBCF/Mai_Natsume/Data"),
    ("Makoto Nanaya", "BBCF/Makoto_Nanaya/Data"),
    ("Mu-12", "BBCF/Mu-12/Data"),
    ("Naoto Kurogane", "BBCF/Naoto_Kurogane/Data"),
    ("Nine the Phantom", "BBCF/Nine_the_Phantom/Data"),
    ("Noel Vermillion", "BBCF/Noel_Vermillion/Data"),
    ("Nu-13", "BBCF/Nu-13/Data"),
    ("Platinum the Trinity", "BBCF/Platinum_the_Trinity/Data"),
    ("Rachel Alucard", "BBCF/Rachel_Alucard/Data"),
    ("Ragna the Bloodedge", "BBCF/Ragna_the_Bloodedge/Data"),
    ("Relius Clover", "BBCF/Relius_Clover/Data"),
    ("Susano'o", "BBCF/Susano'o/Data"),
    ("Taokaka", "BBCF/Taokaka/Data"),
    ("Tsubaki Yayoi", "BBCF/Tsubaki_Yayoi/Data"),
    ("Valkenhayn R. Hellsing", "BBCF/Valkenhayn_R._Hellsing/Data"),
    ("Yuuki Terumi", "BBCF/Yuuki_Terumi/Data"),
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
    "dmg",
    "guardLevel",
    "startup",
    "active",
    "recovery",
    "onBlock",
    "onODR",
    "attribute",
    "invuln",
    "p1",
    "p2",
    "starter",
    "cancel",
    "level",
    "blockstun",
    "groundHit",
    "airHit",
    "groundCH",
    "airCH",
    "blockstop",
    "hitstop",
    "CHstop",
    "extraInfo",
]


def char_key(display_name: str) -> str:
    return dustloop_char_key(display_name)


def page_url(page_title: str) -> str:
    return dustloop_page_url(page_title)


def split_file_list(value: str) -> list[str]:
    return split_mediawiki_files(value)


def split_note_lines(value: str) -> list[str]:
    return shared_split_note_lines(value)


def compact_move_key(value: object) -> str:
    return normalize_move_cache_key(value)


def row_from_template(display_name: str, data_page: str, record) -> tuple[dict[str, str], list[str], list[str], str]:
    params = record.params
    move_input = clean_wiki_text(params.get("input", ""))
    move_name = clean_wiki_text(params.get("name", "")) or move_input
    notes = []
    notes.extend(split_note_lines(params.get("caption", "")))
    notes.extend(split_note_lines(params.get("hitboxCaption", "")))
    notes.extend(split_note_lines(params.get("notes", "")))
    row = {
        "char_key": char_key(display_name),
        "char_name": display_name,
        "source_page_title": data_page,
        "source_page_url": page_url(data_page),
        "section": clean_wiki_text(record.section),
        "subsection": clean_wiki_text(record.subsection),
        "moveType": clean_wiki_text(params.get("type", "")),
        "moveName": move_name,
        "numCmd": move_input,
        "dmg": clean_wiki_text(params.get("damage", "")),
        "guardLevel": clean_wiki_text(params.get("guard", "")),
        "startup": clean_wiki_text(params.get("startup", "")),
        "active": clean_wiki_text(params.get("active", "")),
        "recovery": clean_wiki_text(params.get("recovery", "")),
        "onBlock": clean_wiki_text(params.get("onBlock", "")),
        "onODR": clean_wiki_text(params.get("onODR", "")),
        "attribute": clean_wiki_text(params.get("attribute", "")),
        "invuln": clean_wiki_text(params.get("invuln", "")),
        "p1": clean_wiki_text(params.get("p1", "")),
        "p2": clean_wiki_text(params.get("p2", "")),
        "starter": clean_wiki_text(params.get("starter", "")),
        "cancel": clean_wiki_text(params.get("cancel", "")),
        "level": clean_wiki_text(params.get("level", "")),
        "blockstun": clean_wiki_text(params.get("blockstun", "")),
        "groundHit": clean_wiki_text(params.get("groundHit", "")),
        "airHit": clean_wiki_text(params.get("airHit", "")),
        "groundCH": clean_wiki_text(params.get("groundCH", "")),
        "airCH": clean_wiki_text(params.get("airCH", "")),
        "blockstop": clean_wiki_text(params.get("blockstop", "")),
        "hitstop": clean_wiki_text(params.get("hitstop", "")),
        "CHstop": clean_wiki_text(params.get("CHstop", "")),
        "extraInfo": "\n".join(dict.fromkeys(notes)),
    }
    return row, split_file_list(params.get("images", "")), split_file_list(params.get("hitboxes", "")), row["extraInfo"]


def parse_character(display_name: str, data_page: str, raw_text: str) -> tuple[list[dict[str, str]], list[tuple[str, str, str, str]], dict[str, dict[str, str]]]:
    headings = extract_headings(raw_text)
    records = extract_templates(raw_text, {"movedata-bbcf"})
    apply_heading_context(records, headings)
    rows = []
    media = []
    notes_cache: dict[str, dict[str, str]] = {}
    key = char_key(display_name)
    for record in records:
        row, images, hitboxes, notes = row_from_template(display_name, data_page, record)
        if not row["numCmd"]:
            continue
        rows.append(row)
        move_key = compact_move_key(row["numCmd"])
        if notes:
            notes_cache.setdefault(key, {})[move_key] = notes
        for filename in images:
            media.append((key, move_key, "image", filename))
        for filename in hitboxes:
            media.append((key, move_key, "hitbox", filename))
    return rows, media, notes_cache


def write_cache(path: Path, media: list[tuple[str, str, str, str]], notes_cache: dict[str, dict[str, str]]) -> tuple[int, int, int]:
    image_cache: dict[str, dict[str, str]] = {}
    hitbox_cache: dict[str, dict[str, list[str]]] = {}
    for key, move_key, media_type, filename in media:
        url = mediawiki_thumb_url(DUSTLOOP_BASE, filename, IMAGE_THUMB_WIDTH)
        if media_type == "image":
            image_cache.setdefault(key, {})[move_key] = url
        elif media_type == "hitbox":
            links = hitbox_cache.setdefault(key, {}).setdefault(move_key, [])
            if url not in links:
                links.append(url)
    write_python_constants(
        path,
        {
            "BBCF_MOVE_IMAGE_URLS": image_cache,
            "BBCF_HITBOX_DATA": hitbox_cache,
            "BBCF_MOVE_NOTES": notes_cache,
        },
        "scrape_bbcf_dustloop.py",
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
    for display_name, data_page in BBCF_CHARACTERS:
        raw = fetch_text(data_page, sleep_seconds=sleep_seconds, cache_dir=cache_dir, refresh=refresh)
        rows, media, notes = parse_character(display_name, data_page, raw)
        all_rows.extend(rows)
        all_media.extend(media)
        for key, move_notes in notes.items():
            all_notes.setdefault(key, {}).update(move_notes)
        print(f"[bbcf] parsed {display_name}: {len(rows)} moves", flush=True)

    if not all_rows:
        raise RuntimeError("No BBCF rows were parsed.")

    sheets: dict[str, list[dict[str, str]]] = {"Moves": all_rows}
    for display_name, _data_page in BBCF_CHARACTERS:
        character_rows = [row for row in all_rows if row.get("char_name") == display_name]
        if character_rows:
            sheets[safe_sheet_name(display_name)] = character_rows
    write_ods_sheets(output_workbook, sheets, MOVE_COLUMNS)

    image_count, hitbox_count, notes_count = write_cache(output_cache, all_media, all_notes)
    print(f"[bbcf] wrote {output_workbook}: {len(all_rows)} rows", flush=True)
    print(f"[bbcf] wrote {output_cache}: {image_count} images, {hitbox_count} hitboxes, {notes_count} notes", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build BBCF frame data and remote image caches from Dustloop raw data pages.")
    parser.add_argument("--output-workbook", default="BBCF Frame Data.ods")
    parser.add_argument("--output-cache", default="bubbot/data/bbcf_move_images.py")
    parser.add_argument("--sleep", type=float, default=0.1)
    parser.add_argument("--cache-dir", default="")
    parser.add_argument("--refresh-cache", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build(
        Path(args.output_workbook),
        Path(args.output_cache),
        args.sleep,
        cache_dir=Path(args.cache_dir) if args.cache_dir else None,
        refresh=args.refresh_cache,
    )


if __name__ == "__main__":
    main()

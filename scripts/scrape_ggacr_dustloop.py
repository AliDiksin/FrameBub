"""GGACR Dustloop raw /Data scrape to ODS.
Pulls MoveData-GGACR templates into GGACR Frame Data.ods.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bubbot.utils.mediawiki_images import mediawiki_thumb_url  # noqa: E402
from scripts.scrape_ggst_dustloop import (  # noqa: E402
    apply_heading_context,
    clean_wiki_text,
    extract_headings,
    extract_templates,
    fetch_text,
)


DUSTLOOP_BASE = "https://www.dustloop.com/wiki"
IMAGE_THUMB_WIDTH = 300

GGACR_CHARACTERS = [
    ("A.B.A", "GGACR/A.B.A/Data"),
    ("Anji Mito", "GGACR/Anji_Mito/Data"),
    ("Axl Low", "GGACR/Axl_Low/Data"),
    ("Baiken", "GGACR/Baiken/Data"),
    ("Bridget", "GGACR/Bridget/Data"),
    ("Chipp Zanuff", "GGACR/Chipp_Zanuff/Data"),
    ("Dizzy", "GGACR/Dizzy/Data"),
    ("Eddie", "GGACR/Eddie/Data"),
    ("Faust", "GGACR/Faust/Data"),
    ("I-No", "GGACR/I-No/Data"),
    ("Jam Kuradoberi", "GGACR/Jam_Kuradoberi/Data"),
    ("Johnny", "GGACR/Johnny/Data"),
    ("Justice", "GGACR/Justice/Data"),
    ("Kliff Undersn", "GGACR/Kliff_Undersn/Data"),
    ("Ky Kiske", "GGACR/Ky_Kiske/Data"),
    ("May", "GGACR/May/Data"),
    ("Millia Rage", "GGACR/Millia_Rage/Data"),
    ("Order-Sol", "GGACR/Order-Sol/Data"),
    ("Potemkin", "GGACR/Potemkin/Data"),
    ("Robo-Ky", "GGACR/Robo-Ky/Data"),
    ("Slayer", "GGACR/Slayer/Data"),
    ("Sol Badguy", "GGACR/Sol_Badguy/Data"),
    ("Testament", "GGACR/Testament/Data"),
    ("Venom", "GGACR/Venom/Data"),
    ("Zappa", "GGACR/Zappa/Data"),
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
    "onHit",
    "tension",
    "gbp",
    "gbm",
    "prorate",
    "attribute",
    "invuln",
    "cancel",
    "extraInfo",
]


def char_key(display_name: str) -> str:
    text = str(display_name or "").strip().lower()
    text = text.replace("'", "")
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text


def page_url(page_title: str) -> str:
    title = page_title.replace(" ", "_")
    return f"https://www.dustloop.com/w/{title}"


def split_file_list(value: str) -> list[str]:
    files = []
    for item in re.split(r"[;\n]+", str(value or "")):
        clean = clean_wiki_text(item).strip()
        clean = re.sub(r"^(?:File|Image):", "", clean, flags=re.IGNORECASE).strip()
        if clean and re.search(r"\.(?:png|webp|gif|jpg|jpeg)$", clean, flags=re.IGNORECASE):
            files.append(clean)
    return files


def split_note_lines(value: str) -> list[str]:
    text = clean_wiki_text(value).strip()
    if not text:
        return []
    return [line.strip(" -;\t") for line in re.split(r"[;\\\n]+", text) if line.strip(" -;\t")]


def compact_move_key(value: object) -> str:
    text = str(value or "").lower().strip()
    text = text.replace("jumping", "j")
    text = re.sub(r"\b(?:jump|air)\s*\.?,?", "j.", text)
    text = text.replace("[", "hold")
    return re.sub(r"[^a-z0-9]+", "", text)


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
        "onHit": clean_wiki_text(params.get("onHit", "")),
        "tension": clean_wiki_text(params.get("tension", "")),
        "gbp": clean_wiki_text(params.get("gbp", "")),
        "gbm": clean_wiki_text(params.get("gbm", "")),
        "prorate": clean_wiki_text(params.get("prorate", "")),
        "attribute": clean_wiki_text(params.get("attribute", "")),
        "invuln": clean_wiki_text(params.get("invuln", "")),
        "cancel": clean_wiki_text(params.get("cancel", "")),
        "extraInfo": "\n".join(dict.fromkeys(notes)),
    }
    return row, split_file_list(params.get("images", "")), split_file_list(params.get("hitboxes", "")), row["extraInfo"]


def parse_character(display_name: str, data_page: str, raw_text: str) -> tuple[list[dict[str, str]], list[tuple[str, str, str, str]], dict[str, dict[str, str]]]:
    headings = extract_headings(raw_text)
    records = extract_templates(raw_text, {"movedata-ggacr"})
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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Generated by scrape_ggacr_dustloop.py. Do not edit by hand.\n"
        f"GGACR_MOVE_IMAGE_URLS = {json.dumps(image_cache, indent=2, sort_keys=True)}\n\n"
        f"GGACR_HITBOX_DATA = {json.dumps(hitbox_cache, indent=2, sort_keys=True)}\n\n"
        f"GGACR_MOVE_NOTES = {json.dumps(notes_cache, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
    return (
        sum(len(moves) for moves in image_cache.values()),
        sum(len(links) for moves in hitbox_cache.values() for links in moves.values()),
        sum(len(moves) for moves in notes_cache.values()),
    )


def safe_sheet_name(display_name: str) -> str:
    compact = re.sub(r"[^A-Za-z0-9]+", "", display_name)
    return f"{compact}Normal"[:31] or "CharacterNormal"


def build(output_workbook: Path, output_cache: Path, sleep_seconds: float, cache_dir: Path | None = None, refresh: bool = False) -> None:
    all_rows: list[dict[str, str]] = []
    all_media: list[tuple[str, str, str, str]] = []
    all_notes: dict[str, dict[str, str]] = {}
    for display_name, data_page in GGACR_CHARACTERS:
        raw = fetch_text(data_page, sleep_seconds=sleep_seconds, cache_dir=cache_dir, refresh=refresh)
        rows, media, notes = parse_character(display_name, data_page, raw)
        all_rows.extend(rows)
        all_media.extend(media)
        for key, move_notes in notes.items():
            all_notes.setdefault(key, {}).update(move_notes)
        print(f"[ggacr] parsed {display_name}: {len(rows)} moves", flush=True)

    if not all_rows:
        raise RuntimeError("No GGACR rows were parsed.")

    with pd.ExcelWriter(output_workbook, engine="odf") as odf_writer:
        pd.DataFrame(all_rows, columns=MOVE_COLUMNS).to_excel(odf_writer, sheet_name="Moves", index=False)
        for display_name, _data_page in GGACR_CHARACTERS:
            character_rows = [row for row in all_rows if row.get("char_name") == display_name]
            if character_rows:
                pd.DataFrame(character_rows, columns=MOVE_COLUMNS).to_excel(odf_writer, sheet_name=safe_sheet_name(display_name), index=False)

    image_count, hitbox_count, notes_count = write_cache(output_cache, all_media, all_notes)
    print(f"[ggacr] wrote {output_workbook}: {len(all_rows)} rows", flush=True)
    print(f"[ggacr] wrote {output_cache}: {image_count} images, {hitbox_count} hitboxes, {notes_count} notes", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build GGACR frame data and remote image caches from Dustloop raw data pages.")
    parser.add_argument("--output-workbook", default="GGACR Frame Data.ods")
    parser.add_argument("--output-cache", default="bubbot/data/ggacr_move_images.py")
    parser.add_argument("--sleep", type=float, default=0.1)
    parser.add_argument("--cache-dir", default=".cache/ggacr_dustloop")
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

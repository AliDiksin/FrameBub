from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote
from urllib.request import Request, urlopen

import pandas as pd
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


DREAMCANCEL_BASE = "https://www.dreamcancel.com"
COTW_MAIN_URL = f"{DREAMCANCEL_BASE}/wiki/Fatal_Fury:_City_of_the_Wolves"
IMAGE_THUMB_WIDTH = 300

MOVE_COLUMNS = [
    "char_key",
    "char_name",
    "source_page_url",
    "section",
    "subsection",
    "moveType",
    "moveName",
    "numCmd",
    "version",
    "dmg",
    "guardLevel",
    "cancel",
    "startup",
    "active",
    "recovery",
    "onHit",
    "onBlock",
    "invuln",
    "revDamage",
    "guardDamage",
    "imageUrl",
    "extraInfo",
]

DATA_FIELDS = [
    "dmg",
    "guardLevel",
    "cancel",
    "startup",
    "active",
    "recovery",
    "onHit",
    "onBlock",
    "invuln",
    "revDamage",
    "guardDamage",
]

MOVE_TYPE_HEADINGS = {
    "close normals": "normal",
    "far normals": "normal",
    "crouching normals": "normal",
    "jumping normals": "normal",
    "command moves": "command",
    "universal options": "universal",
    "throw": "throw",
    "rev blow": "rev blow",
    "dodge attacks": "dodge",
    "special moves": "special",
    "supers": "super",
    "ignition gears": "super",
    "redline gears": "super",
    "hidden gear": "super",
}


def clean_text(value: object) -> str:
    text = str(value or "")
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def char_key(display_name: str) -> str:
    text = str(display_name or "").strip().lower()
    text = text.replace(".", "")
    text = text.replace("'", "")
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def compact_move_key(value: object) -> str:
    text = str(value or "").lower().strip()
    text = text.replace("jumping", "j")
    text = re.sub(r"\b(?:jump|air)\s*\.?,?", "j.", text)
    text = text.replace("[", "hold")
    return re.sub(r"[^a-z0-9]+", "", text)


def safe_sheet_name(display_name: str) -> str:
    compact = re.sub(r"[^A-Za-z0-9]+", "", display_name)
    return f"{compact}Normal"[:31] or "CharacterNormal"


def fetch_html(url: str, sleep_seconds: float = 0.0) -> str:
    if sleep_seconds:
        time.sleep(sleep_seconds)
    request = Request(url, headers={"User-Agent": "bubbot-cotw-scraper/1.0"})
    with urlopen(request, timeout=45) as response:
        return response.read().decode("utf-8", errors="replace")


def discover_characters(main_url: str = COTW_MAIN_URL) -> list[tuple[str, str]]:
    soup = BeautifulSoup(fetch_html(main_url), "html.parser")
    found = []
    seen = set()
    for link in soup.select('a[href^="/wiki/Fatal_Fury:_City_of_the_Wolves/"]'):
        href = link.get("href") or ""
        title = link.get("title") or ""
        if not title.startswith("Fatal Fury: City of the Wolves/"):
            continue
        if any(part in href for part in ("/FAQ", "/Controls", "/System", "/Movement", "/Offense", "/Defense", "/Patch_Notes")):
            continue
        if href.endswith(("/Strategy", "/Data", "/Combos")):
            continue
        display = title.rsplit("/", 1)[-1].strip()
        if not display or display in seen:
            continue
        seen.add(display)
        found.append((display, urljoin(DREAMCANCEL_BASE, href)))
    return found


def current_section_stack(heading, headings: list) -> list[str]:
    stack = []
    for item in headings:
        if item["node"] is heading:
            break
        while stack and stack[-1]["level"] >= item["level"]:
            stack.pop()
        stack.append(item)
    return [entry["text"] for entry in stack]


def infer_move_type(section_names: list[str]) -> str:
    for section in reversed(section_names):
        key = section.lower()
        if key in MOVE_TYPE_HEADINGS:
            return MOVE_TYPE_HEADINGS[key]
    return "misc"


def first_move_image_url(table) -> str:
    for img in table.find_all("img"):
        src = img.get("src") or ""
        if not src:
            continue
        if re.search(r"/(?:A|B|C|D|Qcf|Qcb|Dp|Bk|Fw|Rev)\.gif$", src, re.IGNORECASE):
            continue
        absolute = urljoin(DREAMCANCEL_BASE, src)
        return re.sub(r"/\d+px-([^/]+)$", rf"/{IMAGE_THUMB_WIDTH}px-\1", absolute)
    return ""


def extract_move_name_and_cmd(table, fallback_name: str) -> tuple[str, str]:
    first_row = table.find("tr")
    first_cell = first_row.find(["th", "td"]) if first_row else None
    if not first_cell:
        return fallback_name, ""
    big = first_cell.find("big")
    move_name = clean_text(big.get_text(" ", strip=True)) if big else clean_text(fallback_name)
    commands = []
    for item in first_cell.select(".hoveritem"):
        text = clean_text(item.get_text(" ", strip=True))
        if text and text not in commands:
            commands.append(text)
    if not commands:
        for small in first_cell.find_all("small"):
            text = clean_text(small.get_text(" ", strip=True))
            if text and text != move_name and text not in commands:
                commands.append(text)
    return move_name or fallback_name, commands[0] if commands else ""


def extract_notes(table) -> str:
    notes = []
    rows = table.find_all("tr")
    for row in rows:
        cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
        if len(cells) == 1 and cells[0] and not re.search(r"\bDamage\b", cells[0]):
            notes.append(cells[0])
    return "\n".join(dict.fromkeys(notes))


def data_rows(table) -> list[tuple[str, list[str]]]:
    found = []
    for row in table.find_all("tr"):
        cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
        if any(len(cell) > 80 for cell in cells):
            continue
        if len(cells) == len(DATA_FIELDS):
            found.append(("", cells))
        elif len(cells) == len(DATA_FIELDS) + 1 and cells[0].lower() != "version":
            found.append((cells[0], cells[1:]))
    return found


def parse_character(display_name: str, page_url: str, html: str) -> tuple[list[dict[str, str]], dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    images: dict[str, dict[str, str]] = {}
    notes_cache: dict[str, dict[str, str]] = {}
    key = char_key(display_name)

    stack = []
    current_heading = None
    for node in soup.find_all(["h2", "h3", "h4", "h5", "table"]):
        if node.name in {"h2", "h3", "h4", "h5"}:
            text = clean_text(node.get_text(" ", strip=True))
            if not text or text in {"Contents", "Navigation", "Navigation menu"}:
                current_heading = None
                continue
            level = int(node.name[1])
            while stack and stack[-1]["level"] >= level:
                stack.pop()
            current_heading = {"level": level, "text": text}
            stack.append(current_heading)
            continue

        table = node
        if current_heading is None or "wikitable" not in (table.get("class") or []):
            continue
        parsed_rows = data_rows(table)
        if not parsed_rows:
            continue
        heading_text = current_heading["text"]
        parent_sections = [entry["text"] for entry in stack[:-1]]
        section_names = parent_sections + [heading_text]
        move_name, num_cmd = extract_move_name_and_cmd(table, heading_text)
        if not num_cmd:
            continue
        move_type = infer_move_type(section_names)
        image_url = first_move_image_url(table)
        notes = extract_notes(table)
        subsection = " > ".join(parent_sections[-2:]) if parent_sections else ""

        for version, values in parsed_rows:
            row = {
                "char_key": key,
                "char_name": display_name,
                "source_page_url": page_url,
                "section": parent_sections[-1] if parent_sections else "",
                "subsection": subsection,
                "moveType": move_type,
                "moveName": clean_text(f"{move_name} {version}") if version else move_name,
                "numCmd": num_cmd,
                "version": version,
                "imageUrl": image_url,
                "extraInfo": notes,
            }
            row.update(dict(zip(DATA_FIELDS, values)))
            rows.append(row)
            move_key = compact_move_key(row["numCmd"])
            if image_url:
                images.setdefault(key, {})[move_key] = image_url
            if notes:
                notes_cache.setdefault(key, {})[move_key] = notes
    return rows, images, notes_cache


def write_cache(path: Path, images: dict[str, dict[str, str]], notes: dict[str, dict[str, str]]) -> tuple[int, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Generated by scrape_cotw_dreamcancel.py. Do not edit by hand.\n"
        f"COTW_MOVE_IMAGE_URLS = {json.dumps(images, indent=2, sort_keys=True)}\n\n"
        f"COTW_MOVE_NOTES = {json.dumps(notes, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
    return sum(len(moves) for moves in images.values()), sum(len(moves) for moves in notes.values())


def build(output_workbook: Path, output_cache: Path, sleep_seconds: float, only_url: str | None = None) -> None:
    characters = []
    if only_url:
        parsed = urlparse(only_url)
        display = unquote(parsed.path.rsplit("/", 1)[-1]).replace("_", " ")
        characters.append((display, only_url))
    else:
        characters = discover_characters()

    all_rows: list[dict[str, str]] = []
    all_images: dict[str, dict[str, str]] = {}
    all_notes: dict[str, dict[str, str]] = {}
    for display_name, url in characters:
        html = fetch_html(url, sleep_seconds=sleep_seconds)
        rows, images, notes = parse_character(display_name, url, html)
        if not rows:
            print(f"[cotw] skipped {display_name}: no frame rows parsed", flush=True)
            continue
        all_rows.extend(rows)
        for key, move_images in images.items():
            all_images.setdefault(key, {}).update(move_images)
        for key, move_notes in notes.items():
            all_notes.setdefault(key, {}).update(move_notes)
        print(f"[cotw] parsed {display_name}: {len(rows)} moves", flush=True)

    if not all_rows:
        raise RuntimeError("No COTW rows were parsed.")

    with pd.ExcelWriter(output_workbook, engine="odf") as writer:
        pd.DataFrame(all_rows, columns=MOVE_COLUMNS).to_excel(writer, sheet_name="Moves", index=False)
        for display_name, _url in characters:
            character_rows = [row for row in all_rows if row.get("char_name") == display_name]
            if character_rows:
                pd.DataFrame(character_rows, columns=MOVE_COLUMNS).to_excel(writer, sheet_name=safe_sheet_name(display_name), index=False)

    image_count, notes_count = write_cache(output_cache, all_images, all_notes)
    print(f"[cotw] wrote {len(all_rows)} rows to {output_workbook}", flush=True)
    print(f"[cotw] wrote {image_count} image links and {notes_count} notes to {output_cache}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Fatal Fury: City of the Wolves frame data from DreamCancel.")
    parser.add_argument("--output", default="COTW Frame Data.ods")
    parser.add_argument("--output-cache", default="bubbot/data/cotw_move_images.py")
    parser.add_argument("--sleep", type=float, default=0.25)
    parser.add_argument("--url", help="Scrape only one character page URL.")
    args = parser.parse_args()
    build(Path(args.output), Path(args.output_cache), args.sleep, only_url=args.url)


if __name__ == "__main__":
    main()

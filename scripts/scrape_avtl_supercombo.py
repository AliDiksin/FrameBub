"""Build Avatar Legends: The Fighting Game frame data from SuperCombo raw wikitext."""

from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import scraper_utils  # noqa: E402
from scripts.generation_utils import normal_sheet_name, write_ods_sheets, write_python_constants  # noqa: E402
from scripts.scraper_utils import extract_headings, extract_templates, file_url_for_name  # noqa: E402

API_URL = "https://wiki.supercombo.gg/api.php"
IMAGE_THUMB_WIDTH = 300

# 12-character roster; strategy notes live on the main pages, frame rows on /Data.
CHARACTERS = (
    ("Aang", "Avatar Legends/Aang"),
    ("Avatar Aang", "Avatar Legends/Avatar Aang"),
    ("Azula", "Avatar Legends/Azula"),
    ("Katara", "Avatar Legends/Katara"),
    ("Korra", "Avatar Legends/Korra"),
    ("Kyoshi", "Avatar Legends/Kyoshi"),
    ("Nightmare Korra", "Avatar Legends/Nightmare Korra"),
    ("Ozai", "Avatar Legends/Ozai"),
    ("Sokka", "Avatar Legends/Sokka"),
    ("Toph", "Avatar Legends/Toph"),
    ("Zaheer", "Avatar Legends/Zaheer"),
    ("Zuko", "Avatar Legends/Zuko"),
)

MOVE_COLUMNS = (
    "char_key", "char_name", "source_page_title", "source_page_url", "section", "subsection",
    "moveId", "moveType", "moveName", "numCmd", "version",
    "startup", "active", "recovery", "onBlock", "onHit",
    "dmg", "flowDamage", "guardLevel", "flow", "cancel", "invuln", "properties", "extraInfo",
)

BUTTON_REPLACEMENTS = {
    "al-button|a": "A", "al-button|b": "B", "al-button|c": "C",
    "al-button|d": "D", "al-button|f": "D", "al-abc": "ABC",
    "al-button|abc": "ABC", "qcf": "236", "qcb": "214",
    "d": "2", "f": "6", "b": "4", "u": "8", "n": "5", "air": "j",
}


def char_key(display_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(display_name or "").strip().lower()).strip("_")


def page_url(page_title: str) -> str:
    slug = page_title.replace(" ", "_")
    return "https://wiki.supercombo.gg/w/" + urllib.parse.quote(slug, safe="/:()-'.,[]")


def expand_al_templates(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        inner = re.sub(r"[\s_]+", " ", match.group(1).strip().lower()).replace(" ", "|")
        # {{d}}, {{f}}, {{air}} etc arrive as single group
        key = inner.replace(" ", "")
        if "|" not in match.group(0) and key in ("d", "f", "b", "u", "n", "air", "qcf", "qcb"):
            return BUTTON_REPLACEMENTS[key]
        return BUTTON_REPLACEMENTS.get(inner, BUTTON_REPLACEMENTS.get(key, ""))

    text = re.sub(r"\{\{\s*([A-Za-z0-9_|\-\s]+?)\s*\}\}", repl, str(text or ""))
    return text


def clean_text(value: object) -> str:
    text = expand_al_templates(str(value or ""))
    text = scraper_utils.clean_wiki_text(text)
    return re.sub(r"\s+", " ", text).strip()


def clean_input(value: object) -> str:
    text = clean_text(re.split(r"<|\{\{", str(value or ""))[0])
    text = text.replace("\uFF0B", "+").replace("＋", "+")
    text = re.sub(r"\s*\+\s*", "+", text)
    text = re.sub(r"\s+", " ", text).strip().upper()
    text = re.sub(r"^J(?=[0-9A-D])", "j", text)
    return text.replace("J.", "j").replace("J ", "j")


def heading_name(raw_text: str, position: int) -> str:
    name = ""
    for level, pos, title in extract_headings(raw_text):
        if pos >= position:
            break
        if level >= 4:
            name = title
    return clean_text(name)


def section_context(raw_text: str, position: int) -> tuple[str, str]:
    section, subsection = "", ""
    for level, pos, title in extract_headings(raw_text):
        if pos >= position:
            break
        if level == 2:
            section, subsection = title, ""
        elif level == 3:
            subsection = title
    return section, subsection


def split_files(value: object) -> list[str]:
    out = []
    for item in re.split(r"[,;\n]", clean_text(value)):
        name = re.sub(r"^(?:File|Image):", "", item, flags=re.IGNORECASE).strip()
        if name and re.search(r"\.(?:png|webp|gif|jpe?g)$", name, flags=re.IGNORECASE):
            out.append(name)
    return list(dict.fromkeys(out))


def cache_move_key(num_cmd: str) -> str:
    # Must match bubbot.frame_data.avtl_frame_data.normalize_move_token: image/note
    # lookups key on numCmd only, so keying on anything else silently drops all media.
    text = str(num_cmd or "").lower().strip()
    text = text.replace("jumping", "j")
    text = re.sub(r"\b(?:jump|air)\s*\.?,?", "j.", text)
    text = text.replace("[", "hold")
    return re.sub(r"[^a-z0-9]+", "", text)


def parse_main_page_notes(raw_text: str) -> dict[str, str]:
    """Map Data-page moveId -> strategy bullets from the main character page."""
    notes = {}
    for record in extract_templates(raw_text, {"movedatacargo"}):
        info = record.params.get("info", "")
        match = re.search(r"AttackDataCargo-AL/Query\|([^}|]+)", info)
        if not match:
            continue
        move_id = match.group(1).strip()
        lines = []
        for line in scraper_utils.clean_wiki_text(info).splitlines():
            clean = line.strip(" -*\t")
            if clean and clean != move_id:
                lines.append(clean)
        text = "\n".join(dict.fromkeys(lines)).strip()
        if text:
            notes[move_id] = text
    return notes


def parse_character(display_name: str, page_title: str, raw_text: str, main_notes: dict[str, str] | None = None):
    rows, media, notes = [], [], {}
    seen: set[tuple[str, str, str]] = set()
    key = char_key(display_name)
    main_notes = main_notes or {}
    for record in extract_templates(raw_text, {"framedata-al"}):
        params = {k: clean_text(v) for k, v in record.params.items()}
        num_cmd = clean_input(record.params.get("input", ""))
        template_name = clean_text(str(record.params.get("name", "")).split("<")[0])
        head = heading_name(raw_text, record.start)
        # heading holds the real name for specials ("Air Scooter"); template name is often just "A".
        move_name = head
        if not move_name or re.fullmatch(r"(?i)(?:j\.?\s*)?[1-9]?[abcd](?:\s*[abcd+/\-]*)?", move_name):
            move_name = template_name or num_cmd or head
        if not move_name and not num_cmd:
            continue
        if not num_cmd:
            num_cmd = move_name
        section, subsection = section_context(raw_text, record.start)
        flow = params.get("flow", "")
        props = params.get("properties", "")
        flow_dmg = params.get("flowdamage", "")
        extra = " | ".join(p for p in (
            f"Flow: {flow}" if flow and flow != "-" else "",
            f"Flow Damage: {flow_dmg}" if flow_dmg and flow_dmg != "-" else "",
            f"Properties: {props}" if props else "",
        ) if p)
        dedupe_key = (params.get("moveid", ""), num_cmd, move_name)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        # drop mechanic stubs with no frame data at all (e.g. empty AS variants); real stances use '-'.
        if not any(str(params.get(f, "")).strip() for f in ("startup", "active", "recovery", "damage", "onblock", "onhit")):
            continue
        move_id = params.get("moveid", "")
        strategy = main_notes.get(move_id, "")
        full_notes = "\n".join(part for part in (extra, strategy) if part)
        move_key = cache_move_key(num_cmd)
        rows.append({
            "char_key": key, "char_name": display_name,
            "source_page_title": page_title, "source_page_url": page_url(page_title),
            "section": section or "Attack Data", "subsection": subsection,
            "moveId": move_id, "moveType": params.get("movetype", ""),
            "moveName": move_name, "numCmd": num_cmd, "version": "",
            "startup": params.get("startup", ""), "active": params.get("active", ""),
            "recovery": params.get("recovery", ""), "onBlock": params.get("onblock", ""),
            "onHit": params.get("onhit", ""), "dmg": params.get("damage", ""),
            "flowDamage": flow_dmg, "guardLevel": params.get("guard", ""),
            "flow": flow, "cancel": params.get("cancel", ""),
            "invuln": params.get("invuln", ""), "properties": props, "extraInfo": full_notes,
        })
        if full_notes:
            existing = notes.setdefault(key, {}).get(move_key, "")
            if strategy and strategy not in existing:
                notes[key][move_key] = "\n".join(part for part in (existing, full_notes) if part)
            else:
                notes[key].setdefault(move_key, full_notes)
        for filename in split_files(record.params.get("images", "")):
            media.append((key, move_key, "image", filename))
        for filename in split_files(record.params.get("hitboxes", "")):
            media.append((key, move_key, "hitbox", filename))
    return rows, media, notes


def build(output_workbook: Path, output_cache: Path, sleep: float, cache_dir: Path | None, refresh: bool) -> None:
    sheets, all_media, all_notes = {}, [], {}
    total = 0
    for display_name, base_title in CHARACTERS:
        page_title = f"{base_title}/Data"
        raw = scraper_utils.fetch_text(page_title, sleep_seconds=sleep, cache_dir=cache_dir, refresh=refresh, api_url=API_URL)
        main_raw = scraper_utils.fetch_text(base_title, sleep_seconds=sleep, cache_dir=cache_dir, refresh=refresh, api_url=API_URL)
        main_notes = parse_main_page_notes(main_raw)
        rows, media, notes = parse_character(display_name, page_title, raw, main_notes)
        print(f"[avtl-scrape] {display_name}: {len(rows)} rows, {len(media)} media refs, {len(main_notes)} strategy notes", flush=True)
        if rows:
            sheets[normal_sheet_name(display_name)] = rows
            total += len(rows)
            all_media.extend(media)
            for k, v in notes.items():
                all_notes.setdefault(k, {}).update(v)
    if not total:
        raise RuntimeError("No Avatar Legends rows scraped")
    write_ods_sheets(output_workbook, sheets, MOVE_COLUMNS)
    urls = scraper_utils.resolve_file_urls(API_URL, [f for _, _, _, f in all_media], IMAGE_THUMB_WIDTH, sleep)
    images: dict[str, dict[str, str]] = {}
    hitboxes: dict[str, dict[str, list[str]]] = {}
    for char, move, kind, filename in all_media:
        url = file_url_for_name(urls, filename)
        if not url:
            continue
        if kind == "hitbox":
            links = hitboxes.setdefault(char, {}).setdefault(move, [])
            if url not in links:
                links.append(url)
        else:
            images.setdefault(char, {}).setdefault(move, url)
    write_python_constants(output_cache, {
        "AVTL_MOVE_IMAGE_URLS": images, "AVTL_HITBOX_DATA": hitboxes, "AVTL_MOVE_NOTES": all_notes,
    }, "scrape_avtl_supercombo.py")
    print(f"[avtl-scrape] wrote {total} rows to {output_workbook}; images={sum(len(v) for v in images.values())} hitboxes={sum(len(v) for c in hitboxes.values() for v in c.values())}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Avatar Legends frame data from SuperCombo.")
    parser.add_argument("--output", default="AVTL Frame Data.ods")
    parser.add_argument("--output-cache", default="bubbot/data/avtl_move_images.py")
    parser.add_argument("--cache-dir", default=".cache/avtl_supercombo")
    parser.add_argument("--sleep", type=float, default=0.1)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    build(Path(args.output), Path(args.output_cache), args.sleep, Path(args.cache_dir) if args.cache_dir else None, args.refresh)


if __name__ == "__main__":
    main()

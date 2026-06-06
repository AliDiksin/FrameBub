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

from scripts.scrape_ggst_dustloop import (
    extract_headings,
    extract_template_span,
    extract_templates,
    parse_template,
)


API_URL = "https://wiki.supercombo.gg/api.php"
PAGE_PREFIX = "Street Fighter 6"
USER_AGENT = "Mozilla/5.0 (compatible; Bub SF6 combo scraper/1.0)"

SF6_CHARACTERS = [
    "A.K.I.",
    "Akuma",
    "Alex",
    "Blanka",
    "C.Viper",
    "Cammy",
    "Chun-Li",
    "Dee Jay",
    "Dhalsim",
    "E.Honda",
    "Ed",
    "Elena",
    "Guile",
    "Ingrid",
    "Jamie",
    "JP",
    "Juri",
    "Ken",
    "Kimberly",
    "Lily",
    "Luke",
    "M.Bison",
    "Mai",
    "Manon",
    "Marisa",
    "Rashid",
    "Ryu",
    "Sagat",
    "Terry",
    "Zangief",
]

COMBO_COLUMNS = [
    "char_key",
    "char_name",
    "source_url",
    "group",
    "position",
    "title",
    "recipe",
    "damage",
    "difficulty",
    "drive",
    "meter",
    "kameo",
    "kameo_meter",
    "tags",
    "video",
    "notes",
]

POSITION_VOCAB = {
    "midscreen",
    "corner",
    "near corner",
    "anywhere",
    "point blank",
    "corner wallsplat",
    "punish counter",
    "back to corner",
    "not in the corner",
    "not corner",
    "corner only",
    "midscreen/corner",
}

SKIP_SECTIONS = {"combo notation guide"}


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


def page_url(page_title: str) -> str:
    encoded = urllib.parse.quote(page_title.replace(" ", "_"), safe="/:()-'.,[]")
    return f"https://wiki.supercombo.gg/w/{encoded}"


def char_key(display_name: str) -> str:
    text = str(display_name or "").strip().lower().replace("'", "")
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def safe_sheet_name(display_name: str) -> str:
    compact = re.sub(r"[^A-Za-z0-9.]+", "", display_name)
    return f"{compact}Combos"[:31] or "Combos"


def count_drive_tokens(text: str) -> str:
    lowered = str(text or "").lower()
    half = len(re.findall(r"\{\{\s*drivehalf\s+sf6\s*\}\}", lowered, flags=re.IGNORECASE))
    full = len(re.findall(r"\{\{\s*drive\s+sf6\s*\}\}", lowered, flags=re.IGNORECASE))
    total = full + (0.5 * half)
    if not total:
        return ""
    if total == int(total):
        return str(int(total))
    return str(total).rstrip("0").rstrip(".")


def clean_combo_text(value: object) -> str:
    text = str(value or "")
    while True:
        updated = re.sub(
            r"\{\{\s*clr\s*\|[^|{}]*\|([^}|]*)\|?\s*\}\}",
            lambda match: str(match.group(1) or "").strip(),
            text,
            flags=re.IGNORECASE,
        )
        if updated == text:
            break
        text = updated
    text = re.sub(r"\{\{\s*drivehalf\s+sf6\s*\}\}", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\{\{\s*drive\s+sf6\s*\}\}", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = re.sub(r"\[\[(?:File|Image):[^\]]+\]\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[\[([^|\]]+)\|([^\]]+)\]\]", lambda match: match.group(2), text)
    text = re.sub(r"\[\[([^\]]+)\]\]", lambda match: match.group(1).split("/")[-1], text)
    text = re.sub(r"\[https?://[^\s\]]+\s+([^\]]+)\]", lambda match: match.group(1), text)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(?:big|small|u|div|span|sup|sub|nowiki|includeonly|noinclude|font)[^>]*>", "", text, flags=re.IGNORECASE)
    text = text.replace("'''", "").replace("''", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_difficulty(value: object) -> str:
    text = clean_combo_text(value)
    text = re.sub(r"^\s*\[\s*\d+\s*\]\s*", "", text)
    return text.strip()


def normalize_position(value: object) -> str:
    text = clean_combo_text(value).lower()
    if not text:
        return ""
    for candidate in sorted(POSITION_VOCAB, key=len, reverse=True):
        if candidate in text:
            return candidate.title()
    return clean_combo_text(value)


def is_position_tab(name: str) -> bool:
    lowered = str(name or "").strip().lower()
    return any(token in lowered for token in POSITION_VOCAB)


def heading_stack(headings: list[dict[str, str | int]], position: int) -> tuple[str, str]:
    section = ""
    category = ""
    for heading in headings:
        if int(heading["pos"]) >= position:
            break
        level = int(heading["level"])
        title = clean_combo_text(str(heading["title_raw"]))
        if level == 2:
            section = title
            category = ""
        elif level == 3:
            category = title
        elif level == 4 and not category:
            category = title
    return section, category


def build_group(section: str, category: str, title: str = "", *, position: str = "") -> str:
    parts = []
    for part in (section, category, title, position):
        clean = str(part or "").strip()
        if not clean:
            continue
        lowered = clean.lower()
        if lowered in SKIP_SECTIONS:
            continue
        if lowered.endswith(" combos"):
            clean = clean[:-7].strip()
        if clean and clean not in parts:
            parts.append(clean)
    return " — ".join(parts) if parts else "General"


def _tabber_ranges(raw_text: str) -> list[tuple[int, int, str]]:
    """Map every tabber tab (e.g. Windless/Windclad) to its character span."""
    ranges: list[tuple[int, int, str]] = []
    tab_matches = list(
        re.finditer(
            r"(?:<tabber>\s*([^\n=|]+?)\s*=|(?:^|\n)\s*\|-\|\s*([^\n=|]+?)\s*=)\s*(?:\n|$)",
            raw_text,
            flags=re.IGNORECASE | re.MULTILINE,
        )
    )
    for index, match in enumerate(tab_matches):
        tab_name = clean_combo_text(
            re.sub(r"</?tabber[^>]*>", " ", match.group(1) or match.group(2) or "", flags=re.IGNORECASE)
        )
        if not tab_name:
            continue
        chunk_start = match.end()
        chunk_end = tab_matches[index + 1].start() if index + 1 < len(tab_matches) else len(raw_text)
        ranges.append((chunk_start, chunk_end, tab_name))
    return ranges


def tabber_for(position: int, tabber_ranges: list[tuple[int, int, str]]) -> str:
    for start, end, name in tabber_ranges:
        if start <= position < end:
            if is_position_tab(name):
                return ""
            return name
    return ""


def resolve_combo_group(
    *,
    section: str,
    category: str,
    title: str = "",
    position: str = "",
    start_pos: int,
    tabber_ranges: list[tuple[int, int, str]],
) -> str:
    """Build a stable group label for any combo row on any character page."""
    tab = tabber_for(start_pos, tabber_ranges)
    if tab and not category:
        category = tab
    return build_group(section, category, title, position=position)


def split_wikitable_cells(row_text: str) -> list[str]:
    cells = []
    current = []
    index = 0
    text = str(row_text or "").strip()
    while index < len(text):
        if text.startswith("|-", index):
            break
        if text[index : index + 2] == "||":
            cells.append("".join(current).strip())
            current = []
            index += 2
            continue
        if text[index] == "\n" and index + 1 < len(text) and text[index + 1] == "|" and not text.startswith("|-", index + 1):
            cells.append("".join(current).strip())
            current = []
            index += 2
            while index < len(text) and text[index] == " ":
                index += 1
            continue
        current.append(text[index])
        index += 1
    cells.append("".join(current).strip())
    return [clean_combo_text(cell) for cell in cells if clean_combo_text(cell) or cell == ""]


def parse_wikitable_header(header_line: str) -> list[str]:
    line = clean_combo_text(header_line).strip()
    if "!!" in line:
        parts = re.split(r"\s*!!\s*", line)
    else:
        parts = re.split(r"(?:^|\n)\s*!", line)
    columns = []
    for part in parts:
        clean = clean_combo_text(part).lstrip("!").strip()
        if clean:
            columns.append(clean)
    return columns


def map_column_name(name: str) -> str:
    lowered = str(name or "").strip().lower()
    if lowered in {"combo", "combos"}:
        return "recipe"
    if lowered in {"position", "pos"}:
        return "position"
    if lowered in {"damage", "dmg"}:
        return "damage"
    if lowered in {"difficulty", "diff"}:
        return "difficulty"
    if lowered in {"video", "youtube"}:
        return "video"
    if lowered in {"notes", "note"}:
        return "notes"
    if lowered in {"meter"}:
        return "meter"
    if "drive" in lowered:
        return "drive"
    return ""


def row_from_cells(
    columns: list[str],
    cells: list[str],
    *,
    char_name: str,
    page_title: str,
    section: str,
    category: str,
    start_pos: int,
    tabber_ranges: list[tuple[int, int, str]],
    tab_position: str,
) -> dict[str, str] | None:
    mapped: dict[str, str] = {}
    extras = []
    for index, column_name in enumerate(columns):
        value = cells[index] if index < len(cells) else ""
        key = map_column_name(column_name)
        if key:
            mapped[key] = value
        elif value:
            extras.append(f"{column_name}: {value}")
    recipe = clean_combo_text(mapped.get("recipe", ""))
    if not recipe:
        return None
    position = normalize_position(mapped.get("position", "")) or tab_position
    group = resolve_combo_group(
        section=section,
        category=category,
        position=position,
        start_pos=start_pos,
        tabber_ranges=tabber_ranges,
    )
    drive = mapped.get("drive", "")
    if not drive:
        drive = count_drive_tokens(" ".join(cells))
    notes = clean_combo_text(mapped.get("notes", ""))
    if extras:
        extra_text = "\n".join(extras)
        notes = f"{notes}\n{extra_text}".strip() if notes else extra_text
    return {
        "char_key": char_key(char_name),
        "char_name": char_name,
        "source_url": page_url(page_title),
        "group": group,
        "position": position,
        "title": "",
        "recipe": recipe,
        "damage": clean_combo_text(mapped.get("damage", "")),
        "difficulty": clean_difficulty(mapped.get("difficulty", "")),
        "drive": clean_combo_text(drive),
        "meter": clean_combo_text(mapped.get("meter", "")),
        "kameo": "",
        "kameo_meter": "",
        "tags": "",
        "video": clean_combo_text(mapped.get("video", "")),
        "notes": notes,
    }


def row_from_theorybox(
    params: dict[str, str],
    *,
    char_name: str,
    page_title: str,
    section: str,
    category: str,
    start_pos: int,
    tabber_ranges: list[tuple[int, int, str]],
    tab_position: str,
) -> dict[str, str] | None:
    recipe = clean_combo_text(params.get("Recipe", ""))
    if not recipe:
        return None
    title = clean_combo_text(params.get("Title", ""))
    drive = clean_combo_text(params.get("Drive Gauge Usage", "")) or count_drive_tokens(recipe)
    group = resolve_combo_group(
        section=section,
        category=category,
        title=title,
        position=tab_position,
        start_pos=start_pos,
        tabber_ranges=tabber_ranges,
    )
    return {
        "char_key": char_key(char_name),
        "char_name": char_name,
        "source_url": page_url(page_title),
        "group": group,
        "position": tab_position,
        "title": title,
        "recipe": recipe,
        "damage": clean_combo_text(params.get("Damage", "")),
        "difficulty": clean_difficulty(params.get("Difficulty", "")),
        "drive": drive,
        "meter": clean_combo_text(params.get("Meter", "")),
        "kameo": "",
        "kameo_meter": "",
        "tags": "",
        "video": clean_combo_text(params.get("Youtube", "")),
        "notes": clean_combo_text(params.get("content", "")),
    }


def row_from_combo_table_item(params: dict[str, str], *, char_name: str, page_title: str, group: str) -> dict[str, str] | None:
    lookup = {str(key).strip().lower(): value for key, value in params.items()}
    recipe = clean_combo_text(lookup.get("combo", ""))
    if not recipe:
        return None
    drive = clean_combo_text(lookup.get("drive", "")) or count_drive_tokens(recipe)
    return {
        "char_key": char_key(char_name),
        "char_name": char_name,
        "source_url": page_url(page_title),
        "group": group,
        "position": normalize_position(lookup.get("position", "")),
        "title": "",
        "recipe": recipe,
        "damage": clean_combo_text(lookup.get("damage", "")),
        "difficulty": clean_difficulty(lookup.get("difficulty", "")),
        "drive": clean_combo_text(drive),
        "meter": clean_combo_text(lookup.get("super", "") or lookup.get("meter", "")),
        "kameo": "",
        "kameo_meter": "",
        "tags": "",
        "video": clean_combo_text(lookup.get("video", "") or lookup.get("youtube", "")),
        "notes": clean_combo_text(lookup.get("notes", "")),
    }


def parse_combo_table_items(
    display_name: str,
    raw_text: str,
    page_title: str,
    headings: list,
    *,
    tabber_ranges: list[tuple[int, int, str]] | None = None,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    tabber_ranges = tabber_ranges or _tabber_ranges(raw_text)
    for match in re.finditer(r"\{\{\s*SF6-ComboTableItem\b", raw_text, flags=re.IGNORECASE):
        start = match.start()
        try:
            span, _end = extract_template_span(raw_text, start)
        except ValueError:
            continue
        _name, params = parse_template(span)
        section, category = heading_stack(headings, start)
        if section.lower() in SKIP_SECTIONS and (not category or category.lower() in SKIP_SECTIONS):
            continue
        lookup = {str(key).strip().lower(): value for key, value in params.items()}
        position = normalize_position(lookup.get("position", ""))
        group = resolve_combo_group(
            section=section,
            category=category,
            position=position,
            start_pos=start,
            tabber_ranges=tabber_ranges,
        )
        row = row_from_combo_table_item(
            params,
            char_name=display_name,
            page_title=page_title,
            group=group,
        )
        if row:
            rows.append(row)
    return rows


def extract_wikitables(raw_text: str) -> list[str]:
    return re.findall(r"\{\|.*?\|\}", raw_text, flags=re.DOTALL)


def parse_wikitable(
    table_text: str,
    *,
    char_name: str,
    page_title: str,
    headings: list,
    start_pos: int,
    tabber_ranges: list[tuple[int, int, str]],
    tab_position: str,
) -> list[dict[str, str]]:
    section, category = heading_stack(headings, start_pos)
    if section.lower() in SKIP_SECTIONS and (not category or category.lower() in SKIP_SECTIONS):
        return []
    header_match = re.search(r"^\s*(?:\|-\s*\n)?([^\n]*!.*?)\n", table_text, flags=re.MULTILINE)
    if not header_match:
        return []
    columns = parse_wikitable_header(header_match.group(1))
    if not columns:
        return []
    rows = []
    for row_match in re.finditer(r"^\s*\|-\s*\n(.*?)(?=^\s*\|-\s*\n|^\s*\|\})", table_text, flags=re.MULTILINE | re.DOTALL):
        row_body = row_match.group(1).strip()
        if not row_body or row_body.lstrip().startswith("!"):
            continue
        cells = split_wikitable_cells(row_body)
        if not cells:
            continue
        row = row_from_cells(
            columns,
            cells,
            char_name=char_name,
            page_title=page_title,
            section=section,
            category=category,
            start_pos=start_pos,
            tabber_ranges=tabber_ranges,
            tab_position=tab_position,
        )
        if row:
            rows.append(row)
    return rows


_DEDUPE_FIELDS = ("group", "position", "title", "recipe", "damage", "difficulty", "drive", "meter", "notes")


def _dedupe_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, ...]] = set()
    unique: list[dict[str, str]] = []
    for row in rows:
        key = tuple(str(row.get(field, "")) for field in _DEDUPE_FIELDS)
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def parse_character(display_name: str, raw_text: str) -> list[dict[str, str]]:
    page_title = f"{PAGE_PREFIX}/{display_name}/Combos"
    headings = extract_headings(raw_text)
    tabber_ranges = _tabber_ranges(raw_text)
    item_rows = parse_combo_table_items(
        display_name,
        raw_text,
        page_title,
        headings,
        tabber_ranges=tabber_ranges,
    )
    base_rows = _parse_theory_and_wikitables(
        display_name,
        raw_text,
        page_title,
        headings,
        tabber_ranges=tabber_ranges,
    )
    return _dedupe_rows(base_rows + item_rows)


def _position_ranges(raw_text: str) -> list[tuple[int, int, str]]:
    """Map position-only tabber tabs (e.g. Midscreen/Corner) to character spans."""
    return [
        (start, end, normalize_position(name))
        for start, end, name in _tabber_ranges(raw_text)
        if is_position_tab(name)
    ]


def _parse_theory_and_wikitables(
    display_name: str,
    raw_text: str,
    page_title: str,
    headings: list,
    *,
    tabber_ranges: list[tuple[int, int, str]] | None = None,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    tabber_ranges = tabber_ranges or _tabber_ranges(raw_text)
    position_ranges = _position_ranges(raw_text)

    def position_for(pos: int) -> str:
        for start, end, position in position_ranges:
            if start <= pos < end:
                return position
        return ""

    for record in extract_templates(raw_text, {"theorybox"}):
        section, category = heading_stack(headings, record.start)
        if section.lower() in SKIP_SECTIONS and (not category or category.lower() in SKIP_SECTIONS):
            continue
        row = row_from_theorybox(
            record.params,
            char_name=display_name,
            page_title=page_title,
            section=section,
            category=category,
            start_pos=record.start,
            tabber_ranges=tabber_ranges,
            tab_position=position_for(record.start),
        )
        if row:
            rows.append(row)

    search_index = 0
    for table_text in extract_wikitables(raw_text):
        start_pos = raw_text.find(table_text, search_index)
        search_index = start_pos + len(table_text) if start_pos >= 0 else search_index
        rows.extend(
            parse_wikitable(
                table_text,
                char_name=display_name,
                page_title=page_title,
                headings=headings,
                start_pos=start_pos if start_pos >= 0 else 0,
                tabber_ranges=tabber_ranges,
                tab_position=position_for(start_pos if start_pos >= 0 else 0),
            )
        )

    return rows


def build(output_workbook: Path, sleep_seconds: float, cache_dir: Path | None = None, refresh: bool = False) -> None:
    rows_by_character: dict[str, list[dict[str, str]]] = {}
    total_rows = 0
    for display_name in SF6_CHARACTERS:
        page_title = f"{PAGE_PREFIX}/{display_name}/Combos"
        try:
            raw = fetch_raw_page(page_title, sleep_seconds=sleep_seconds, cache_dir=cache_dir, refresh=refresh)
        except Exception as error:
            print(f"[sf6-combo-scrape] {display_name}: skipped ({error})", flush=True)
            continue
        rows = parse_character(display_name, raw)
        rows_by_character[display_name] = rows
        total_rows += len(rows)
        print(f"[sf6-combo-scrape] {display_name}: {len(rows)} combos", flush=True)

    if not total_rows:
        raise RuntimeError("No SF6 combo rows scraped")

    with pd.ExcelWriter(output_workbook, engine="odf") as writer:
        for display_name in SF6_CHARACTERS:
            rows = rows_by_character.get(display_name, [])
            if not rows:
                continue
            df = pd.DataFrame(rows)
            for column in COMBO_COLUMNS:
                if column not in df.columns:
                    df[column] = ""
            df[COMBO_COLUMNS].to_excel(writer, sheet_name=safe_sheet_name(display_name), index=False)

    print(f"[sf6-combo-scrape] wrote {total_rows} rows to {output_workbook}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape SF6 combo pages from SuperCombo into an ODS workbook.")
    parser.add_argument("--output", default="SF6 Combos.ods", help="Output ODS workbook path")
    parser.add_argument("--sleep", type=float, default=0.1, help="Seconds to sleep after API requests")
    parser.add_argument("--cache-dir", default=".cache/sf6_combos_supercombo", help="Raw page cache directory")
    parser.add_argument("--refresh", action="store_true", help="Refresh cached raw pages")
    args = parser.parse_args()
    build(
        output_workbook=Path(args.output),
        sleep_seconds=args.sleep,
        cache_dir=Path(args.cache_dir) if args.cache_dir else None,
        refresh=args.refresh,
    )


if __name__ == "__main__":
    main()

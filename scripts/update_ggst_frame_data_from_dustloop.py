"""GGST ODS update from Dustloop.
Refreshes GGST Frame Data.ods from Dustloop raw data pages.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from bubbot.data.ggst_aliases import GGST_PAGE_OVERRIDES
from bubbot.utils.text_utils import compact_key
from scripts import scraper_utils


TARGET = Path("GGST Frame Data.ods")
BACKUP = Path("GGST Frame Data.backup.ods")
REFRESH_OUTPUT = Path("GGST Frame Data.refresh.ods")

CHARACTER_BY_SHEET_PREFIX = {
    "ABA": "A.B.A",
    "Anji": "Anji Mito",
    "Asuka": "Asuka R",
    "Axl": "Axl Low",
    "Baiken": "Baiken",
    "Bedman": "Bedman",
    "Bridget": "Bridget",
    "Chipp": "Chipp Zanuff",
    "Dizzy": "Queen Dizzy",
    "Elphelt": "Elphelt Valentine",
    "Faust": "Faust",
    "Giovanna": "Giovanna",
    "Goldlewis": "Goldlewis Dickinson",
    "H. Chaos": "Happy Chaos",
    "I-No": "I-No",
    "Jack-O": "Jack-O",
    "Jam": "Jam Kuradoberi",
    "Johnny": "Johnny",
    "Ky": "Ky Kiske",
    "Leo": "Leo Whitefang",
    "Lucy": "Lucy",
    "May": "May",
    "Millia": "Millia Rage",
    "Nagoriyuki": "Nagoriyuki",
    "Potemkin": "Potemkin",
    "Ramlethal": "Ramlethal Valentine",
    "Sin": "Sin Kiske",
    "Slayer": "Slayer",
    "Sol": "Sol Badguy",
    "Testament": "Testament",
    "Unika": "Unika",
    "Venom": "Venom",
    "Zato-1": "Zato-1",
}

MOVE_SHEET_SUFFIXES = [
    "Dragon Install",
    "Install",
    "Normal",
    "Spells",
    "Items",
    "L2",
    "L3",
    "BR",
]

def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip() == ""


def blank_to_empty(value: Any) -> str:
    return "" if is_blank(value) else str(value).strip()


def normalize_key(value: Any) -> str:
    text = blank_to_empty(value)
    if not text:
        return ""
    text = text.replace("j.", "j")
    return compact_key(text)


def normalize_number_text(value: Any) -> str:
    text = blank_to_empty(value)
    if text in {"±0", "+0", "-0"}:
        return "0"
    if re.fullmatch(r"[+]\d+(?:\.0)?", text):
        return text[1:].removesuffix(".0")
    if re.fullmatch(r"-?\d+\.0", text):
        return text.removesuffix(".0")
    return text


def simple_int(value: Any) -> int | None:
    text = normalize_number_text(value)
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return None


def active_total(value: Any) -> int | None:
    text = normalize_number_text(value)
    if re.fullmatch(r"\d+", text):
        return int(text)
    if re.fullmatch(r"\d+(?:,\d+)+", text.replace(" ", "")):
        return sum(int(part) for part in text.replace(" ", "").split(","))
    if re.fullmatch(r"\d+×\d+", text) or re.fullmatch(r"\d+x\d+", text):
        left, right = re.split("[×x]", text)
        return int(left) * int(right)
    return None


def transform_recovery_and_total(row: pd.Series) -> tuple[str, str]:
    recovery = normalize_number_text(row.get("recovery", ""))
    total = ""
    match = re.fullmatch(r"(?:Total\s+(\d+)|(\d+)\s+Total)", recovery, flags=re.IGNORECASE)
    if match:
        return "", match.group(1) or match.group(2)

    startup = simple_int(row.get("startup", ""))
    active = active_total(row.get("active", ""))
    recovery_int = simple_int(recovery)
    if startup is not None and active is not None and recovery_int is not None:
        total = str(startup + active + recovery_int - 1)
    return recovery, total


def parse_on_hit(value: Any) -> tuple[str, str]:
    text = normalize_number_text(value)
    if not text:
        return "", ""
    if re.fullmatch(r"[+-]?\d+", text):
        return normalize_number_text(text), ""

    states = []
    for state in ["HKD", "KD", "Stagger", "Freeze", "Crumple"]:
        if re.search(rf"\b{re.escape(state)}\b", text, flags=re.IGNORECASE):
            states.append(state)
    advantages = [normalize_number_text(match) for match in re.findall(r"[+]\d+", text)]
    if states:
        return "/".join(states), "/".join(advantages)
    return text, ""


def guard_level(value: Any) -> str:
    text = blank_to_empty(value).lower()
    if not text:
        return ""
    if "guard crush" in text:
        return "GC"
    if "throw" in text:
        return "T"
    if "high" in text:
        return "H"
    if "low" in text:
        return "L"
    if "all" in text or "mid" in text:
        return "M"
    return ""


def json_array(values: list[str]) -> str:
    compact = []
    for value in values:
        text = re.sub(r"\s*\n\s*", " ", blank_to_empty(value))
        text = re.sub(r"\s+", " ", text).strip()
        if text and text not in compact:
            compact.append(text)
    return json.dumps(compact, ensure_ascii=False) if compact else ""


def sheet_prefix(sheet_name: str) -> str | None:
    for suffix in MOVE_SHEET_SUFFIXES:
        if sheet_name.endswith(suffix):
            return sheet_name[: -len(suffix)]
    return None


def sheet_state(sheet_name: str) -> str:
    if sheet_name.endswith("L2"):
        return "Level 2"
    if sheet_name.endswith("L3"):
        return "Level 3"
    if sheet_name.endswith("BR"):
        return "Level BR"
    if sheet_name.endswith("Dragon Install"):
        return "DI"
    return ""


def sheet_kind(sheet_name: str) -> str:
    for suffix in MOVE_SHEET_SUFFIXES:
        if sheet_name.endswith(suffix):
            return suffix
    return ""


def row_candidates(row: pd.Series, state: str) -> list[str]:
    base_values = [row.get("numCmd", ""), row.get("dustloopKey", ""), row.get("moveName", ""), row.get("cmnName", "")]
    candidates: list[str] = []
    for value in base_values:
        text = blank_to_empty(value)
        if not text:
            continue
        variants = [text]
        if state == "DI":
            variants.insert(0, f"DI {text}")
        elif state:
            variants.insert(0, f"{text} {state}")
        for variant in variants:
            key = normalize_key(variant)
            if key and key not in candidates:
                candidates.append(key)
    return candidates


def fetch_live_source_moves() -> pd.DataFrame:
    def fetch(page_title: str) -> str:
        for attempt in range(2):
            try:
                return scraper_utils.fetch_text(page_title)
            except Exception:
                if attempt:
                    raise
                print(f"Retrying {page_title} after fetch failure", flush=True)
        raise AssertionError("unreachable")

    rows: list[dict[str, Any]] = []
    key_aliases = {"onhit": "onHit", "onblock": "onBlock", "riscgain": "riscGain"}
    for sheet_prefix, display_name in CHARACTER_BY_SHEET_PREFIX.items():
        page_name = GGST_PAGE_OVERRIDES.get(sheet_prefix, sheet_prefix.replace(" ", "_"))
        main_title = f"GGST/{page_name}"
        data_title = f"{main_title}/Data"
        data_raw = fetch(data_title)
        _stats, character_rows = scraper_utils.parse_data_page(
            sheet_prefix, display_name, data_title, data_raw, {}
        )
        if not character_rows:
            raise RuntimeError(f"No live move templates found for {display_name} ({data_title})")
        for order, source_row in enumerate(character_rows, start=1):
            canonical_row = {key_aliases.get(key, key): value for key, value in source_row.items()}
            canonical_row.update(character_display=display_name, template_order=order)
            rows.append(canonical_row)
        print(f"Fetched {display_name}: {len(character_rows)} moves", flush=True)
    return pd.DataFrame(rows).fillna("")


def transform_row(dust_row: pd.Series) -> dict[str, str]:
    recovery, total = transform_recovery_and_total(dust_row)
    on_hit, kda = parse_on_hit(dust_row.get("onHit", ""))
    notes = [
        dust_row.get("description_text", ""),
        dust_row.get("notes_text", ""),
        dust_row.get("caption_text", ""),
    ]

    return {
        "startup": normalize_number_text(dust_row.get("startup", "")),
        "active": normalize_number_text(dust_row.get("active", "")),
        "recovery": recovery,
        "total": total,
        "onHit": on_hit,
        "onBlock": normalize_number_text(dust_row.get("onBlock", "")),
        "dmg": normalize_number_text(dust_row.get("damage", "")),
        "riscGain": normalize_number_text(dust_row.get("riscGain", "")),
        "prorate": normalize_number_text(dust_row.get("prorate", "")),
        "kda": kda,
        "guardLevel": guard_level(dust_row.get("guard", "")),
        "atkLvl": normalize_number_text(dust_row.get("level", "")),
        "extraInfo": json_array(notes),
        "images": blank_to_empty(dust_row.get("images", "")),
        "hitboxes": blank_to_empty(dust_row.get("hitboxes", "")),
    }


def source_row_order(dust_row: pd.Series) -> int:
    if "source_order" in dust_row.attrs:
        return int(dust_row.attrs["source_order"])
    return int(dust_row.get("template_order", 0) or 0)


def source_rows_for_sheet(source_moves: pd.DataFrame, character: str, sheet_name: str) -> list[pd.Series]:
    rows = source_moves[source_moves["character_display"].eq(character)].copy()
    kind = sheet_kind(sheet_name)
    state = sheet_state(sheet_name)

    if kind == "Spells":
        rows = rows[rows["type"].astype(str).eq("spell")]
    elif kind == "Items":
        rows = rows[rows["section"].astype(str).eq("Items")]
    elif kind == "Install":
        rows = rows[rows["subsection"].astype(str).str.startswith("Error 6")]
    elif state == "DI":
        rows = rows[rows["input"].astype(str).str.startswith("DI ")]
    elif state:
        rows = rows[rows["input"].astype(str).str.contains(state, regex=False)]
    elif kind == "Normal":
        inputs = rows["input"].astype(str)
        sections = rows["section"].astype(str)
        subsections = rows["subsection"].astype(str)
        types = rows["type"].astype(str)
        rows = rows[
            ~inputs.str.startswith("DI ")
            & ~inputs.str.contains(" Level 2", regex=False)
            & ~inputs.str.contains(" Level 3", regex=False)
            & ~inputs.str.contains(" Level BR", regex=False)
            & ~sections.eq("Items")
            & ~subsections.str.startswith("Error 6")
            & ~types.eq("spell")
        ]
    else:
        return []

    return [row for _, row in rows.sort_values("template_order").iterrows()]


def source_command_for_sheet(dust_row: pd.Series, sheet_name: str) -> str:
    command = blank_to_empty(dust_row.get("input", ""))
    if command.lower() == "none":
        command = ""
    command = command or re.sub(r"\s+Data$", "", blank_to_empty(dust_row.get("subsection", "")))
    state = sheet_state(sheet_name)
    if state == "DI":
        return re.sub(r"^DI\s+", "", command)
    if state:
        return re.sub(rf"\s+{re.escape(state)}$", "", command)
    return command


def new_target_row_from_source(
    dust_row: pd.Series,
    columns: list[str],
    sheet_name: str,
    existing_row: pd.Series | None = None,
) -> dict[str, Any]:
    values = existing_row.to_dict() if existing_row is not None else {}
    values = {column: values.get(column, "") for column in columns}
    transformed = transform_row(dust_row)
    num_cmd = source_command_for_sheet(dust_row, sheet_name)
    move_name = blank_to_empty(values.get("moveName")) or blank_to_empty(dust_row.get("name")) or num_cmd
    source_order = source_row_order(dust_row)

    values.update(
        {
            "moveName": move_name,
            "cmnName": blank_to_empty(values.get("cmnName")) or num_cmd,
            "plnCmd": blank_to_empty(values.get("plnCmd")) or num_cmd,
            "numCmd": blank_to_empty(values.get("numCmd")) or num_cmd,
            "dustloopKey": re.sub(r"\s+Data$", "", blank_to_empty(dust_row.get("subsection", ""))),
            "moveType": blank_to_empty(dust_row.get("type", "")),
            "movesList": blank_to_empty(dust_row.get("section", "")),
            "airmove": "true" if num_cmd.startswith("j.") else "",
            "followUp": "true" if "~" in num_cmd or "target combo" in blank_to_empty(dust_row.get("section")).lower() else "",
            "nonHittingMove": "true" if transformed.get("dmg", "") == "" and blank_to_empty(dust_row.get("guard", "")) == "" else "",
            "projectile": "true" if "Projectile" in transformed.get("extraInfo", "") else "",
        }
    )
    values.update(transformed)
    if "i" in values:
        values["i"] = source_order
    return values


def rebuild_move_sheet(
    df: pd.DataFrame, source_rows: list[pd.Series], sheet_name: str
) -> tuple[pd.DataFrame, int, int]:
    existing_by_key: dict[str, list[int]] = defaultdict(list)
    state = sheet_state(sheet_name)
    for row_index, row in df.iterrows():
        for key in row_candidates(row, state):
            if row_index not in existing_by_key[key]:
                existing_by_key[key].append(row_index)

    used_existing: set[int] = set()
    records: list[dict[str, Any]] = []
    matched = 0
    for source_row in source_rows:
        source_keys = []
        for value in (source_row.get("input", ""), source_row.get("name", ""), source_row.get("subsection", "")):
            key = normalize_key(re.sub(r"\s+Data$", "", blank_to_empty(value)))
            if key and key not in source_keys:
                source_keys.append(key)
        existing_position = next(
            (
                position
                for key in source_keys
                for position in existing_by_key.get(key, [])
                if position not in used_existing
            ),
            None,
        )
        existing_row = df.loc[existing_position] if existing_position is not None else None
        if existing_position is not None:
            used_existing.add(existing_position)
            matched += 1
        records.append(new_target_row_from_source(source_row, list(df.columns), sheet_name, existing_row))
    return pd.DataFrame(records, columns=df.columns), matched, len(df) - len(used_existing)


def main() -> None:
    if not TARGET.exists():
        raise FileNotFoundError(TARGET)
    source_moves = fetch_live_source_moves()

    target_book = pd.ExcelFile(TARGET, engine="odf")
    output_sheets: dict[str, pd.DataFrame] = {}
    report_rows: list[dict[str, Any]] = []

    for sheet_name in target_book.sheet_names:
        df = pd.read_excel(target_book, sheet_name=sheet_name, engine="odf")
        prefix = sheet_prefix(sheet_name)
        character = CHARACTER_BY_SHEET_PREFIX.get(prefix or "")
        if character and sheet_name not in {"IdealSheetNormal", "TemplateNormal"}:
            source_rows = source_rows_for_sheet(source_moves, character, sheet_name)
            if not source_rows:
                raise RuntimeError(f"No live source rows map to {sheet_name}")
            updated, matched, removed = rebuild_move_sheet(df, source_rows, sheet_name)
            output_sheets[sheet_name] = updated
            report_rows.append(
                {
                    "sheet": sheet_name,
                    "old_rows": len(df),
                    "new_rows": len(updated),
                    "metadata_matches": matched,
                    "removed_old_rows": removed,
                }
            )
        else:
            output_sheets[sheet_name] = df

    target_sheet_names = list(target_book.sheet_names)
    target_book.close()
    generated_rows = sum(row["new_rows"] for row in report_rows)
    if generated_rows != len(source_moves):
        raise RuntimeError(f"Mapped {generated_rows} workbook rows from {len(source_moves)} live source rows")

    REFRESH_OUTPUT.unlink(missing_ok=True)
    with pd.ExcelWriter(REFRESH_OUTPUT, engine="odf") as writer:
        for sheet_name, df in output_sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    refreshed_book = pd.ExcelFile(REFRESH_OUTPUT, engine="odf")
    if refreshed_book.sheet_names != target_sheet_names:
        raise RuntimeError("Refreshed workbook sheet order changed")
    for sheet_name, expected in output_sheets.items():
        actual = pd.read_excel(refreshed_book, sheet_name=sheet_name, engine="odf")
        if list(actual.columns) != list(expected.columns) or len(actual) != len(expected):
            raise RuntimeError(f"Refreshed workbook schema/count validation failed for {sheet_name}")
    refreshed_book.close()

    if not BACKUP.exists():
        shutil.copy2(TARGET, BACKUP)
    REFRESH_OUTPUT.replace(TARGET)

    report = pd.DataFrame(report_rows)
    print(f"Backup retained at {BACKUP}")
    print(f"Updated {TARGET} atomically from {len(source_moves)} live Dustloop move templates")
    print(f"Metadata matches: {int(report['metadata_matches'].sum())}")
    print(f"Removed stale/duplicate rows: {int(report['removed_old_rows'].sum())}")
    print("Largest count changes:")
    report["delta"] = report["new_rows"] - report["old_rows"]
    print(report.reindex(report["delta"].abs().sort_values(ascending=False).index).head(10).to_string(index=False))


if __name__ == "__main__":
    main()

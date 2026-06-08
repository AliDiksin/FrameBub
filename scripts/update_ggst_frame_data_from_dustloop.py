"""GGST ODS update from Dustloop.
Refreshes GGST Frame Data.ods from Dustloop raw data pages.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from bubbot.utils.text_utils import compact_key


TARGET = Path("GGST Frame Data.ods")
SOURCE = Path("GGST - Dustloop Frame Data.ods")
BACKUP = Path("GGST Frame Data.backup.ods")

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

UPDATE_COLUMNS = [
    "startup",
    "active",
    "recovery",
    "total",
    "onHit",
    "onBlock",
    "dmg",
    "riscGain",
    "prorate",
    "kda",
    "guardLevel",
    "atkLvl",
    "extraInfo",
    "images",
    "hitboxes",
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
    match = re.fullmatch(r"Total\s+(\d+)", recovery, flags=re.IGNORECASE)
    if match:
        return "", match.group(1)

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


def build_dust_index(move_data: pd.DataFrame, move_details: pd.DataFrame) -> dict[str, dict[str, pd.Series]]:
    detail_by_row = {
        (str(row.character_display), int(row.template_order)): row for row in move_details.itertuples(index=False)
    }
    index_by_character: dict[str, dict[str, pd.Series]] = {}
    for _, row in move_data.iterrows():
        character = blank_to_empty(row.get("character_display", ""))
        if not character:
            continue
        index = index_by_character.setdefault(character, {})
        keys = [row.get("input", ""), row.get("name", ""), row.get("subsection", "")]
        for key_value in keys:
            key = normalize_key(key_value)
            if key and key not in index:
                index[key] = row
        details = detail_by_row.get((character, int(row.get("template_order", 0))))
        if details is not None:
            row.attrs["details"] = details
        row.attrs["source_order"] = int(row.get("template_order", 0) or 0)
    return index_by_character


def transform_row(dust_row: pd.Series) -> dict[str, str]:
    recovery, total = transform_recovery_and_total(dust_row)
    on_hit, kda = parse_on_hit(dust_row.get("onHit", ""))
    details = dust_row.attrs.get("details")
    notes = []
    if details is not None:
        notes.append(getattr(details, "notes_text", ""))

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
    elif state == "DI":
        rows = rows[rows["input"].astype(str).str.startswith("DI ")]
    elif state:
        rows = rows[rows["input"].astype(str).str.contains(state, regex=False)]
    elif kind == "Normal":
        inputs = rows["input"].astype(str)
        sections = rows["section"].astype(str)
        types = rows["type"].astype(str)
        rows = rows[
            ~inputs.str.startswith("DI ")
            & ~inputs.str.contains(" Level 2", regex=False)
            & ~inputs.str.contains(" Level 3", regex=False)
            & ~inputs.str.contains(" Level BR", regex=False)
            & ~sections.eq("Items")
            & ~types.eq("spell")
        ]
    else:
        return []

    return [row for _, row in rows.sort_values("template_order").iterrows()]


def new_target_row_from_source(dust_row: pd.Series, columns: list[str], sheet_name: str) -> dict[str, Any]:
    values = {column: "" for column in columns}
    transformed = transform_row(dust_row)
    move_name = blank_to_empty(dust_row.get("name", "")) or blank_to_empty(dust_row.get("input", ""))
    num_cmd = blank_to_empty(dust_row.get("input", ""))
    source_order = source_row_order(dust_row)

    values.update(
        {
            "moveName": move_name,
            "cmnName": num_cmd,
            "plnCmd": num_cmd,
            "numCmd": num_cmd,
            "dustloopKey": re.sub(r"\s+Data$", "", blank_to_empty(dust_row.get("subsection", ""))),
            "moveType": blank_to_empty(dust_row.get("type", "")),
            "movesList": blank_to_empty(dust_row.get("section", "")),
            "airmove": "true" if num_cmd.startswith("j.") else "",
            "followUp": "true" if "~" in num_cmd else "",
            "nonHittingMove": "true" if transformed.get("dmg", "") == "" and blank_to_empty(dust_row.get("guard", "")) == "" else "",
            "projectile": "true" if "Projectile" in transformed.get("extraInfo", "") else "",
        }
    )
    values.update(transformed)
    if "i" in values:
        values["i"] = source_order
    return values


def insert_unmatched_source_rows(
    df: pd.DataFrame,
    source_rows: list[pd.Series],
    matched_positions: dict[int, int],
    sheet_name: str,
) -> tuple[pd.DataFrame, int]:
    if not source_rows:
        return df, 0
    records = df.to_dict("records")
    order_positions = dict(matched_positions)
    existing_exact_inputs = {normalize_key(record.get("numCmd", "")) for record in records}
    inserted = 0

    for source_row in source_rows:
        source_order = source_row_order(source_row)
        source_input_key = normalize_key(source_row.get("input", ""))
        if source_input_key and source_input_key in existing_exact_inputs:
            continue
        new_row = new_target_row_from_source(source_row, list(df.columns), sheet_name)
        previous_positions = [position for order, position in order_positions.items() if order < source_order]
        insert_at = max(previous_positions) + 1 if previous_positions else len(records)
        records.insert(insert_at, new_row)
        order_positions = {
            order: position + 1 if position >= insert_at else position for order, position in order_positions.items()
        }
        order_positions[source_order] = insert_at
        if source_input_key:
            existing_exact_inputs.add(source_input_key)
        inserted += 1

    return pd.DataFrame(records, columns=df.columns), inserted


def update_move_sheet(df: pd.DataFrame, dust_index: dict[str, pd.Series], state: str) -> tuple[pd.DataFrame, int, int, dict[int, int], set[int]]:
    updated = df.copy()
    for column in UPDATE_COLUMNS:
        if column not in updated.columns:
            updated[column] = ""
        updated[column] = updated[column].astype(object)
    matched = 0
    changed = 0
    matched_positions: dict[int, int] = {}
    matched_orders: set[int] = set()
    for row_index, row in updated.iterrows():
        dust_row = None
        for candidate in row_candidates(row, state):
            dust_row = dust_index.get(candidate)
            if dust_row is not None:
                break
        if dust_row is None:
            continue

        matched += 1
        source_order = source_row_order(dust_row)
        if source_order:
            matched_positions[source_order] = int(row_index)
            matched_orders.add(source_order)
        new_values = transform_row(dust_row)
        for column, value in new_values.items():
            if column not in updated.columns:
                continue
            if value == "" and column != "extraInfo":
                continue
            old_value = blank_to_empty(updated.at[row_index, column])
            if old_value != value:
                updated.at[row_index, column] = value
                changed += 1
    return updated, matched, changed, matched_positions, matched_orders


def main() -> None:
    if not TARGET.exists():
        raise FileNotFoundError(TARGET)
    if not SOURCE.exists():
        raise FileNotFoundError(SOURCE)
    if not BACKUP.exists():
        shutil.copy2(TARGET, BACKUP)

    source_moves = pd.read_excel(SOURCE, sheet_name="MoveData", engine="odf").fillna("")
    source_details = pd.read_excel(SOURCE, sheet_name="MoveDetails", engine="odf").fillna("")
    dust_index = build_dust_index(source_moves, source_details)

    target_book = pd.ExcelFile(TARGET, engine="odf")
    output_sheets: dict[str, pd.DataFrame] = {}
    report_rows: list[dict[str, Any]] = []

    for sheet_name in target_book.sheet_names:
        df = pd.read_excel(target_book, sheet_name=sheet_name, engine="odf")
        prefix = sheet_prefix(sheet_name)
        character = CHARACTER_BY_SHEET_PREFIX.get(prefix or "")
        if character and sheet_name not in {"IdealSheetNormal", "TemplateNormal"}:
            updated, matched, changed, matched_positions, matched_orders = update_move_sheet(
                df,
                dust_index.get(character, {}),
                sheet_state(sheet_name),
            )
            updated, inserted = insert_unmatched_source_rows(
                updated,
                source_rows_for_sheet(source_moves, character, sheet_name),
                matched_positions,
                sheet_name,
            )
            output_sheets[sheet_name] = updated
            report_rows.append(
                {
                    "sheet": sheet_name,
                    "rows": len(df),
                    "matched_rows": matched,
                    "inserted_rows": inserted,
                    "changed_cells": changed,
                }
            )
        else:
            output_sheets[sheet_name] = df

    with pd.ExcelWriter(TARGET, engine="odf") as writer:
        for sheet_name, df in output_sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    report = pd.DataFrame(report_rows)
    print(f"Backed up original to {BACKUP}")
    print(f"Updated {TARGET}")
    print(f"Matched rows: {int(report['matched_rows'].sum())}")
    print(f"Inserted rows: {int(report['inserted_rows'].sum())}")
    print(f"Changed cells: {int(report['changed_cells'].sum())}")
    print("Lowest match sheets:")
    print(report.sort_values(["matched_rows", "rows"]).head(10).to_string(index=False))


if __name__ == "__main__":
    main()

"""Shared loader for games whose frame data uses ``*Normal`` ODS sheets."""
# The loader normalizes only the shared *Normal-sheet shape; each game keeps its own parser rules.

import os

import pandas as pd


def load_normal_frame_data(
    filename,
    frame_data,
    character_aliases,
    log_prefix,
    *,
    alias_variants=("key", "space", "name"),
    row_callback=None,
):
    """Load normal-move sheets into a game-owned mapping.

    ``row_callback`` may annotate a completed character row list before it is
    stored. Game-specific loaders retain ownership of those callbacks.
    """
    frame_data.clear()
    if not os.path.exists(filename):
        print(f"[{log_prefix}] frame data file not found: {filename}", flush=True)
        return False

    xls = pd.ExcelFile(filename, engine="odf")
    loaded = 0
    for sheet_name in xls.sheet_names:
        if not sheet_name.endswith("Normal"):
            continue
        df = pd.read_excel(xls, sheet_name=sheet_name).fillna("")
        sheet_character_name = sheet_name[: -len("Normal")]
        rows = []
        for row in df.to_dict("records"):
            char_key = str(
                row.get("char_key") or row.get("char_name") or sheet_character_name
            ).strip().lower()
            move_name = str(row.get("moveName", "")).strip()
            num_cmd = str(row.get("numCmd", "")).strip()
            if not move_name and not num_cmd:
                continue
            row["char_key"] = char_key
            row["char_name"] = str(row.get("char_name") or sheet_character_name).strip()
            rows.append(row)
        if not rows:
            continue
        if row_callback:
            row_callback(rows, rows[0]["char_key"])
        char_key = rows[0]["char_key"]
        frame_data[char_key] = rows
        if "key" in alias_variants:
            character_aliases.setdefault(char_key, char_key)
        if "space" in alias_variants:
            character_aliases.setdefault(char_key.replace("_", " "), char_key)
        if "name" in alias_variants:
            character_aliases.setdefault(str(rows[0]["char_name"]).lower(), char_key)
        loaded += 1

    print(f"[{log_prefix}] Total characters loaded: {loaded}", flush=True)
    return bool(frame_data)

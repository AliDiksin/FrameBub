"""Load SF6 ODS frame data: Jamie drink sheets, attack ranges, local GIF index refresh."""

import os
import re

import pandas as pd


def normalize_loader_move_key(move_name, num_cmd):
    normalized_name = re.sub(r"[^a-z0-9]+", "", str(move_name or "").lower())
    normalized_num_cmd = re.sub(r"\([^)]*\)", "", str(num_cmd or "").lower())
    normalized_num_cmd = re.sub(r"\s+", "", normalized_num_cmd)
    normalized_num_cmd = re.sub(r"[^a-z0-9>]", "", normalized_num_cmd)
    return normalized_name, normalized_num_cmd


def loader_row_signature(row):
    return tuple(
        sorted(
            (str(key), str(value).strip())
            for key, value in row.items()
            if key != "char_name" and not str(key).startswith("_jamie_")
        )
    )


# Jamie drink-level sheet merge


def merge_jamie_drink_level_sheets(xls, frame_data):
    """Merge Jamie drink-level sheets into Jamie's main moveset."""
    if "jamie" not in frame_data:
        return

    jamie_extra_sheets = [
        name for name in xls.sheet_names
        if re.fullmatch(r"JamieD[1-4]", str(name or ""), re.IGNORECASE)
    ]
    previous_signatures = {
        normalize_loader_move_key(row.get("moveName", ""), row.get("numCmd", "")): loader_row_signature(row)
        for row in frame_data["jamie"]
        if str(row.get("moveName", "")).strip() and str(row.get("numCmd", "")).strip()
    }
    for sheet_name in sorted(jamie_extra_sheets, key=str.lower):
        drink_level = int(re.search(r"([1-4])$", sheet_name, re.IGNORECASE).group(1))
        df = pd.read_excel(xls, sheet_name=sheet_name)
        records = df.fillna("").to_dict("records")
        for row in records:
            move_name = str(row.get("moveName", "")).strip()
            num_cmd = str(row.get("numCmd", "")).strip()
            if not move_name or not num_cmd:
                continue
            row_key = normalize_loader_move_key(move_name, num_cmd)
            row_signature = loader_row_signature(row)
            if previous_signatures.get(row_key) != row_signature:
                row["char_name"] = "Jamie"
                row["_jamie_drink_level"] = drink_level
                frame_data["jamie"].append(row)
            previous_signatures[row_key] = row_signature


# Attack range token normalization


def normalize_range_cmd_token(value):
    raw_text = str(value or "").lower()
    is_air_context = bool(
        "(air" in raw_text
        or raw_text.startswith("j.")
        or raw_text.startswith("j ")
        or raw_text.startswith("j")
        or "jump" in raw_text
    )
    text = raw_text
    text = text.replace("->", ">")
    text = text.replace("~", ">")
    text = text.replace("|", "/")
    text = re.sub(r"\bor\b", "/", text)
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[^a-z0-9>/+]", "", text)
    text = text.replace("+", "")
    text = re.sub(r"^j42684268", "j720", text)
    text = re.sub(r"^42684268", "720", text)
    text = re.sub(r"^j4268", "j360", text)
    text = re.sub(r"^4268", "360", text)
    if is_air_context and re.match(r"^(360|720)", text):
        text = f"j{text}"
    return text


def build_range_cmd_tokens(value):
    normalized = normalize_range_cmd_token(value)
    if not normalized:
        return []
    tokens = []
    for part in normalized.split("/"):
        token = part.strip()
        if not token:
            continue
        if token not in tokens:
            tokens.append(token)
        if token.startswith("5") and len(token) > 1:
            token_without_five = token[1:]
            if token_without_five and token_without_five not in tokens:
                tokens.append(token_without_five)
    return tokens


# Backfill atkRange from RangeData sheet


def hydrate_range_data(xls, frame_data, range_data, character_lookup, normalize_char_name, is_missing_attack_range_value, build_num_cmd_candidates_for_gif):
    def choose_preferred_range(values):
        cleaned_values = [str(value).strip() for value in values if str(value).strip()]
        if not cleaned_values:
            return ""
        for value in cleaned_values:
            if not is_missing_attack_range_value(value):
                return value
        return ""

    range_sheet_name = next((name for name in xls.sheet_names if name.lower() in {"range", "ranges"}), None)
    if range_sheet_name:
        range_df = pd.read_excel(xls, sheet_name=range_sheet_name, dtype=str).fillna("")
        for range_row in range_df.to_dict("records"):
            char_raw = str(range_row.get("chara", "")).strip()
            input_raw = str(range_row.get("input", "")).strip()
            atk_range_raw = str(range_row.get("atkRange", "")).strip()
            if not char_raw or not input_raw:
                continue
            char_key = character_lookup.get(normalize_char_name(char_raw))
            if not char_key:
                continue
            for token in build_range_cmd_tokens(input_raw):
                range_data.setdefault(char_key, {}).setdefault(token, []).append(atk_range_raw)
    else:
        print("Range sheet not found: ranges")

    for char_key, records in frame_data.items():
        char_ranges = range_data.get(char_key, {})
        for row in records:
            row_tokens = []
            for token in build_range_cmd_tokens(row.get("numCmd", "")):
                if token not in row_tokens:
                    row_tokens.append(token)
            for token in build_num_cmd_candidates_for_gif(row):
                for variant in build_range_cmd_tokens(token):
                    if variant not in row_tokens:
                        row_tokens.append(variant)

            selected_range = ""
            for token in row_tokens:
                if token not in char_ranges:
                    continue
                selected_range = choose_preferred_range(char_ranges[token])
                if selected_range:
                    break
            row["atkRange"] = selected_range


# Main ODS load: normals, stats, ranges, gif refresh


def load_frame_data(deps):
    frame_data = deps["FRAME_DATA"]
    frame_stats = deps["FRAME_STATS"]
    hitbox_gif_data = deps["HITBOX_GIF_DATA"]
    range_data = deps["RANGE_DATA"]
    character_aliases = deps["CHARACTER_ALIASES"]
    normalize_char_name = deps["normalize_char_name"]
    is_missing_attack_range_value = deps["is_missing_attack_range_value"]
    build_num_cmd_candidates_for_gif = deps["build_num_cmd_candidates_for_gif"]
    configure_extracted_modules = deps["configure_extracted_modules"]
    load_local_hitbox_gif_data = deps["load_local_hitbox_gif_data"]
    quiz_module = deps["quiz_module"]
    frame_output_module = deps["frame_output_module"]

    filename = "FAT - SF6 Frame Data.ods"
    quiz_module.QUIZ_CHARACTER_TERMS_CACHE = None
    quiz_module.QUIZ_MOVE_NAME_TERMS_CACHE = None
    quiz_module.QUIZ_CHARACTER_CENSOR_PATTERNS_CACHE = None
    if not os.path.exists(filename):
        print(f"File not found: {filename}")
        return

    try:
        print(f"Loading ODS file: {filename} (This may take a moment)...")
        xls = pd.ExcelFile(filename, engine="odf")

        frame_data.clear()
        frame_stats.clear()
        hitbox_gif_data.clear()
        range_data.clear()

        for sheet_name in xls.sheet_names:
            if sheet_name.endswith("Normal"):
                char_name = sheet_name.replace("Normal", "").rstrip(".").lower()
                df = pd.read_excel(xls, sheet_name=sheet_name)
                records = df.fillna("").to_dict("records")
                for row in records:
                    row["char_name"] = char_name.capitalize()
                frame_data[char_name] = records
            elif sheet_name.endswith("Stats") and not sheet_name.startswith("_OLD"):
                char_name = sheet_name.replace("Stats", "").rstrip(".").lower()
                df = pd.read_excel(xls, sheet_name=sheet_name)
                frame_stats[char_name] = dict(zip(df["name"], df["stat"]))

        merge_jamie_drink_level_sheets(xls, frame_data)

        print(f"Total characters loaded: {len(frame_data)}")
        print(f"Total stats loaded: {len(frame_stats)}")

        normalized_chars = {normalize_char_name(name): name for name in frame_data.keys()}
        character_lookup = dict(normalized_chars)
        for alias, canonical in character_aliases.items():
            if canonical in frame_data:
                character_lookup[normalize_char_name(alias)] = canonical
                character_lookup[normalize_char_name(canonical)] = canonical

        hydrate_range_data(
            xls,
            frame_data,
            range_data,
            character_lookup,
            normalize_char_name,
            is_missing_attack_range_value,
            build_num_cmd_candidates_for_gif,
        )

        configure_extracted_modules()
        hitbox_gif_data.update(load_local_hitbox_gif_data(character_lookup))
        configure_extracted_modules()

        print(f"Total hitbox gif links loaded: {sum(len(entries) for entries in hitbox_gif_data.values())}")
        print(f"Total range inputs loaded: {sum(len(entries) for entries in range_data.values())}")

        quiz_module.configure(
            FRAME_DATA=frame_data,
            CHARACTER_ALIASES=character_aliases,
            resolve_character_key=deps["resolve_character_key"],
            normalize_char_name=normalize_char_name,
            lookup_frame_data=deps["lookup_frame_data"],
            find_moves_in_text=deps["find_moves_in_text"],
            is_missing_attack_range_value=is_missing_attack_range_value,
            clean_embed_value=frame_output_module.clean_embed_value,
            truncate_embed_value=frame_output_module.truncate_embed_value,
            build_frame_embed=frame_output_module.build_frame_embed,
            strip_discord_mentions=deps["strip_discord_mentions"],
        )
    except Exception as error:
        print(f"Error loading {filename}: {error}")

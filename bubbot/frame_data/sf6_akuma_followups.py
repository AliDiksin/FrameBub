import re

from bubbot.frame_data.sf6_parser_helpers import append_unique


def collect_akuma_aliases(
    text_lower,
    extra_inputs,
    potential_inputs,
    *,
    air_sa1_context,
    air_sa3_context,
):
    has_od_strength = bool(re.search(r"\b(od|ex)\b", text_lower))
    followup_alias = None

    if air_sa1_context:
        append_unique(extra_inputs, "tenma gozanku")

    if re.search(r"\b(?:demon\s+)?gou\s+rasen\b", text_lower):
        followup_alias = "od demon gou rasen"
    elif re.search(r"\b(?:demon\s+)?gou\s+zanku\b", text_lower):
        followup_alias = "od demon gou zanku"
    elif re.search(r"\b(?:demon\s+)?(?:low(?:\s+slash)?|slide)\b", text_lower):
        followup_alias = "od demon low" if has_od_strength else "demon low"
    elif re.search(r"\b(?:demon\s+)?(?:guillotine|chop|overhead)\b", text_lower):
        followup_alias = "od chop" if has_od_strength else "chop"
    elif re.search(r"\b(?:blade\s+kick|divekick|dive\s+kick)\b", text_lower) and re.search(
        r"\b(?:demon|flip|raid)\b",
        text_lower,
    ):
        followup_alias = "od demon flip divekick" if has_od_strength else "demon flip divekick"
    elif re.search(r"\b(?:demon\s+)?(?:swoop|empty|stop|feint)\b", text_lower):
        followup_alias = "od empty" if has_od_strength else "empty"

    if followup_alias:
        append_unique(extra_inputs, followup_alias)
        potential_inputs = [token for token in potential_inputs if token not in {"dive kick", "divekick"}]

    if air_sa3_context:
        append_unique(extra_inputs, "sip of calamity")

    return followup_alias, potential_inputs


def infer_akuma_from_demon_terms(text_lower, frame_data, mentioned_chars):
    if mentioned_chars:
        return
    if re.search(r"\braging\s+demon\b", text_lower) or re.search(r"\bshun\s+goku\s+satsu\b", text_lower):
        if "akuma" in frame_data:
            mentioned_chars.append("akuma")


def apply_akuma_teleport_direction_aliases(text_lower, mentioned_chars, extra_inputs):
    if "akuma" not in mentioned_chars:
        return extra_inputs
    if re.search(r"\bback(?:ward)?\s+teleport\b", text_lower):
        extra_inputs = [token for token in extra_inputs if token != "teleport"]
        if "back teleport" not in extra_inputs:
            extra_inputs.insert(0, "back teleport")
    elif re.search(r"\btele(?:port)?\s+back(?:ward)?\b", text_lower):
        extra_inputs = [token for token in extra_inputs if token != "teleport"]
        if "teleport back" not in extra_inputs:
            extra_inputs.insert(0, "teleport back")
    elif re.search(r"\bforward\s+teleport\b", text_lower):
        extra_inputs = [token for token in extra_inputs if token != "teleport"]
        if "forward teleport" not in extra_inputs:
            extra_inputs.insert(0, "forward teleport")
    return extra_inputs


def filter_shoto_air_tatsu_results(results, *, mentioned_chars, normalize_char_name):
    air_tatsu_chars = {"ryu", "ken", "akuma"}
    mentioned_air_tatsu_chars = set(mentioned_chars) & air_tatsu_chars
    if not results or not mentioned_air_tatsu_chars:
        return results

    filtered_results = []
    for row in results:
        row_char_key = normalize_char_name(row.get("char_name", ""))
        row_char_matches = any(normalize_char_name(char) == row_char_key for char in mentioned_air_tatsu_chars)
        if not row_char_matches:
            filtered_results.append(row)
            continue
        move_name = str(row.get("moveName", "")).lower()
        cmn_name = str(row.get("cmnName", "")).lower()
        num_cmd = str(row.get("numCmd", "")).lower()
        if "air" in move_name or "air" in cmn_name or "(air)" in num_cmd:
            filtered_results.append(row)
    return filtered_results or results


def filter_akuma_followup_results(results, followup_alias, normalize_char_name):
    if not followup_alias or not results:
        return results

    alias_lower = followup_alias.lower()
    followup_keyword = None
    if "gou rasen" in alias_lower:
        followup_keyword = "gou rasen"
    elif "gou zanku" in alias_lower:
        followup_keyword = "gou zanku"
    elif "low" in alias_lower or "slide" in alias_lower:
        followup_keyword = "low slash"
    elif "chop" in alias_lower or "guillotine" in alias_lower:
        followup_keyword = "guillotine"
    elif "divekick" in alias_lower or "blade kick" in alias_lower:
        followup_keyword = "blade kick"
    elif any(token in alias_lower for token in ("swoop", "empty", "stop", "feint")):
        followup_keyword = "swoop"

    if not followup_keyword:
        return results

    filtered_results = []
    for row in results:
        row_char = normalize_char_name(row.get("char_name", ""))
        if row_char != "akuma":
            filtered_results.append(row)
            continue
        move_name = str(row.get("moveName", "")).lower()
        cmn_name = str(row.get("cmnName", "")).lower()
        if followup_keyword == "blade kick" and "demon" not in move_name and "demon" not in cmn_name:
            continue
        if followup_keyword in move_name or followup_keyword in cmn_name:
            filtered_results.append(row)
    return filtered_results or results


def filter_akuma_air_fireball_results(
    results,
    *,
    mentioned_chars,
    text_tokens,
    query_wants_od_strength,
    normalize_char_name,
    lookup_frame_data,
):
    if not results or not (set(mentioned_chars) & {"akuma"}):
        return results

    allow_demon_fireball = any(token in text_tokens for token in {"demon", "flip", "raid"})
    filtered_results = []
    for row in results:
        row_char_key = normalize_char_name(row.get("char_name", ""))
        if row_char_key != "akuma":
            filtered_results.append(row)
            continue
        move_name = str(row.get("moveName", "")).lower()
        cmn_name = str(row.get("cmnName", "")).lower()
        num_cmd = str(row.get("numCmd", "")).lower()
        is_air_fireball_row = (
            "air fireball" in cmn_name
            or "zanku" in move_name
            or "zanku" in cmn_name
            or "(air)" in num_cmd
        )
        if not is_air_fireball_row:
            continue
        if not allow_demon_fireball and ("demon" in move_name or "demon" in cmn_name):
            continue
        filtered_results.append(row)

    if filtered_results:
        return filtered_results

    fallback_input = "od zanku hadoken" if query_wants_od_strength else "zanku hadoken"
    fallback_row = lookup_frame_data("akuma", fallback_input)
    if fallback_row:
        return [fallback_row]
    return results


def filter_akuma_air_sa1_results(results, *, mentioned_chars, normalize_char_name, lookup_frame_data):
    if not results or not (set(mentioned_chars) & {"akuma"}):
        return results

    filtered_results = []
    for row in results:
        row_char_key = normalize_char_name(row.get("char_name", ""))
        if row_char_key != "akuma":
            filtered_results.append(row)
            continue
        move_name = str(row.get("moveName", "")).lower()
        cmn_name = str(row.get("cmnName", "")).lower()
        num_cmd = str(row.get("numCmd", "")).lower()
        is_air_sa1_row = (
            "tenma" in move_name
            or "gozanku" in move_name
            or ("super art level 1" in cmn_name and ("air" in cmn_name or "(air)" in num_cmd))
        )
        if is_air_sa1_row:
            filtered_results.append(row)

    if filtered_results:
        return filtered_results
    fallback_row = lookup_frame_data("akuma", "tenma gozanku")
    if fallback_row:
        return [fallback_row]
    return results


def filter_akuma_non_air_sa3_results(results, *, mentioned_chars, normalize_char_name, row_is_ca_variant, lookup_frame_data):
    if not results or not (set(mentioned_chars) & {"akuma"}):
        return results

    filtered_results = []
    for row in results:
        row_char_key = normalize_char_name(row.get("char_name", ""))
        if row_char_key != "akuma":
            filtered_results.append(row)
            continue
        move_name = str(row.get("moveName", "")).lower()
        cmn_name = str(row.get("cmnName", "")).lower()
        num_cmd = str(row.get("numCmd", "")).lower()
        is_air_variant = "air" in move_name or "air" in cmn_name or "(air)" in num_cmd
        is_ca_variant = row_is_ca_variant(row)
        if not is_air_variant and not is_ca_variant:
            filtered_results.append(row)

    if filtered_results:
        return filtered_results
    fallback_row = lookup_frame_data("akuma", "sip of calamity")
    if fallback_row:
        return [fallback_row]
    return results

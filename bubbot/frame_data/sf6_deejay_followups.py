"""Dee Jay Jus Cool / sway alias and result filters."""
# Dee Jay follow-ups are normalized here before the shared SF6 candidate pipeline sees them.

import re

from bubbot.frame_data.sf6_parser_helpers import append_unique


def collect_deejay_sway_alias(text_lower, extra_inputs):
    followup_alias = None
    if (
        re.search(r"\bsway\s*(?:low)?\s*>\s*(?:lk|light)\b", text_lower)
        or re.search(r"\bsway\s+low\b", text_lower)
        or re.search(r"\bsway\s+lk\b", text_lower)
    ):
        followup_alias = "sway low"
    elif (
        re.search(r"\bsway\s*(?:overhead)?\s*>\s*(?:mk|medium)\b", text_lower)
        or re.search(r"\bsway\s+overhead\b", text_lower)
        or re.search(r"\bsway\s+mk\b", text_lower)
    ):
        followup_alias = "sway overhead"
    elif (
        re.search(r"\bsway\s*(?:launch|launcher)?\s*>\s*(?:hk|heavy)\b", text_lower)
        or re.search(r"\bsway\s+(?:launch|launcher)\b", text_lower)
        or re.search(r"\bsway\s+hk\b", text_lower)
    ):
        followup_alias = "sway launch"
    elif re.search(r"\bsway\s+feint\b", text_lower) or (
        "sway" in text_lower and re.search(r"\b6p\b", text_lower) and re.search(r"\b4p\b", text_lower)
    ):
        followup_alias = "sway feint"

    if followup_alias:
        append_unique(extra_inputs, followup_alias, front=True)
        extra_inputs[:] = [token for token in extra_inputs if token not in {"sway", "jus cool", "juscool"}]
    return followup_alias


def filter_deejay_sway_results(results, followup_alias, normalize_char_name):
    if not followup_alias or not results:
        return results

    alias_lower = followup_alias.lower()
    deejay_char_key_norm = normalize_char_name("dee jay")
    followup_keywords = []
    if "low" in alias_lower:
        followup_keywords = ["funky slicer", "sway > low", "> lk"]
    elif "overhead" in alias_lower:
        followup_keywords = ["waning moon", "sway > overhead", "> mk"]
    elif any(token in alias_lower for token in ("launch", "launcher", "hk")):
        followup_keywords = ["maximum strike", "sway > launcher", "> hk"]
    elif any(token in alias_lower for token in ("feint", "dash", "backdash")):
        followup_keywords = ["juggling sway", "sway > dash > backdash", "> 6p > 4p"]

    if not followup_keywords:
        return results

    filtered_results = []
    for row in results:
        row_char = normalize_char_name(row.get("char_name", ""))
        if row_char != deejay_char_key_norm:
            filtered_results.append(row)
            continue
        move_name = str(row.get("moveName", "")).lower()
        cmn_name = str(row.get("cmnName", "")).lower()
        num_cmd = str(row.get("numCmd", "")).lower()
        if any(keyword in move_name or keyword in cmn_name or keyword in num_cmd for keyword in followup_keywords):
            filtered_results.append(row)
    return filtered_results or results

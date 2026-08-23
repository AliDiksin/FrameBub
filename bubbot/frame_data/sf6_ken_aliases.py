"""Ken Jinrai, run, and Dragonlash alias and result filters."""

import re

from bubbot.frame_data.sf6_parser_helpers import append_first_matching_alias, append_unique


def collect_ken_aliases(text_lower, extra_inputs, *, query_wants_od_strength, ken_run_followup_context):
    ken_jinrai_followup_alias = None
    if re.search(
        r"\b(?:(?:od|ex)\s+)?(?:jinrai|236k)\s*(?:>\s*)?(?:low|lk|6lk)\b"
        r"|\b(?:low|lk|6lk)\s+(?:(?:od|ex)\s+)?jinrai\b",
        text_lower,
    ):
        ken_jinrai_followup_alias = "od jinrai low" if query_wants_od_strength else "jinrai low"
    elif re.search(
        r"\b(?:(?:od|ex)\s+)?(?:jinrai|236k)\s*(?:>\s*)?(?:overhead|mk|6mk)\b"
        r"|\b(?:overhead|mk|6mk)\s+(?:(?:od|ex)\s+)?jinrai\b",
        text_lower,
    ):
        ken_jinrai_followup_alias = "od jinrai overhead" if query_wants_od_strength else "jinrai overhead"
    elif re.search(
        r"\b(?:(?:od|ex)\s+)?(?:jinrai|236k)\s*(?:>\s*)?(?:heavy|launcher|hk|6hk)\b"
        r"|\b(?:heavy|launcher|hk|6hk)\s+(?:(?:od|ex)\s+)?jinrai\b",
        text_lower,
    ):
        ken_jinrai_followup_alias = "od jinrai hk" if query_wants_od_strength else "jinrai hk"

    run_aliases = [
        (r"\brun\s+stop\b", "emergency stop"),
        (r"\brun\s+overhead\b", "thunder kick"),
        (r"\brun\s+step\s*kick\b", "forward step kick"),
        (r"\brun\s+step\b", "forward step kick"),
        (r"\brun\s+(?:dp|shoryu|shoryuken)\b", "run > shoryuken"),
        (r"\brun\s+tatsu\b", "run > tatsumaki senpukyaku"),
        (r"\brun\s+(?:dragonlash|dragon\s+lash|lash)\b", "run > dragonlash"),
    ]
    for pattern, alias_token in run_aliases:
        if re.search(pattern, text_lower):
            append_unique(extra_inputs, alias_token)

    if not ken_run_followup_context:
        lash_aliases = [
            (r"\b(?:od|ex)\s+(?:dragonlash|dragon\s+lash|lash)\b", "od lash"),
            (r"\b(?:l|light|lk)\s+(?:dragonlash|dragon\s+lash|lash)\b", "l lash"),
            (r"\b(?:m|medium|mk)\s+(?:dragonlash|dragon\s+lash|lash)\b", "m lash"),
            (r"\b(?:h|heavy|hk)\s+(?:dragonlash|dragon\s+lash|lash)\b", "h lash"),
            (r"\b(?:dragonlash|dragon\s+lash|lash)\b", "lash"),
        ]
        append_first_matching_alias(text_lower, extra_inputs, lash_aliases)

    if ken_jinrai_followup_alias:
        append_unique(extra_inputs, ken_jinrai_followup_alias, front=True)

    if re.search(r"\brun\b", text_lower) and not re.search(
        r"\brun\s+(?:stop|overhead|step|dp|shoryu|shoryuken|tatsu|dragonlash|dragon\s+lash|lash)\b",
        text_lower,
    ):
        append_unique(extra_inputs, "quick dash")

    return ken_jinrai_followup_alias


def filter_ken_jinrai_results(results, ken_jinrai_followup_alias, normalize_char_name):
    if not ken_jinrai_followup_alias or not results:
        return results

    alias_lower = ken_jinrai_followup_alias.lower()
    followup_keywords = []
    if "low" in alias_lower or "lk" in alias_lower:
        followup_keywords = ["jinrai > low", "kazekama", "> 6lk"]
    elif "overhead" in alias_lower or "mk" in alias_lower:
        followup_keywords = ["jinrai > overhead", "gorai", "> 6mk"]
    elif any(token in alias_lower for token in ("heavy", "launcher", "hk")):
        followup_keywords = ["jinrai > heavy", "senka", "> 6hk"]

    if not followup_keywords:
        return results

    filtered_results = []
    for row in results:
        row_char = normalize_char_name(row.get("char_name", ""))
        if row_char != "ken":
            filtered_results.append(row)
            continue
        move_name = str(row.get("moveName", "")).lower()
        cmn_name = str(row.get("cmnName", "")).lower()
        num_cmd = str(row.get("numCmd", "")).lower()
        if any(keyword in move_name or keyword in cmn_name or keyword in num_cmd for keyword in followup_keywords):
            filtered_results.append(row)
    return filtered_results or results

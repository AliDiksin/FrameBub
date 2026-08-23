"""Cammy Hooligan follow-up aliases and result filtering."""

import re


HOOLIGAN_FOLLOWUP_PATTERN = re.compile(
    r"\bhooligan\s+(?:combination\s+)?"
    r"(?:slide|razor\s+edge\s+slicer|dive\s*kick|cannon\s+strike|"
    r"overhead|reverse\s+edge|throw|fatal\s+leg\s+twister|"
    r"fast\s+fall|silent\s+step)\b",
)


def query_has_hooligan_followup(text_lower):
    return bool(HOOLIGAN_FOLLOWUP_PATTERN.search(str(text_lower or "")))


def filter_cammy_hooligan_results(results, *, followup_context, normalize_char_name):
    if not followup_context or not results:
        return results

    filtered_results = []
    for row in results:
        if normalize_char_name(row.get("char_name", "")) != "cammy":
            filtered_results.append(row)
            continue
        cmn_name = str(row.get("cmnName", "")).lower()
        moves_list = str(row.get("movesList", "")).lower()
        if "hooligan >" in cmn_name or ("hooligan" in moves_list and row.get("followUp")):
            filtered_results.append(row)
    return filtered_results or results

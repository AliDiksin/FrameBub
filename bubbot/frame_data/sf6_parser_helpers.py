"""Shared helpers for SF6 parser alias collection and normal notation."""
# Parser modules call these predicates to keep SF6 variant rules consistent across lookup paths.

import difflib
import re


NORMAL_BUTTON_PATTERN = (
    r"lp|mp|hp|lk|mk|hk|l\s*p|m\s*p|h\s*p|l\s*k|m\s*k|h\s*k|"
    r"light\s+punch|medium\s+punch|heavy\s+punch|light\s+kick|medium\s+kick|heavy\s+kick|"
    r"jab|strong|fierce|short|forward|roundhouse"
)

BUTTON_ALIASES = {
    "lp": "lp", "l p": "lp", "light punch": "lp", "jab": "lp",
    "mp": "mp", "m p": "mp", "medium punch": "mp", "strong": "mp",
    "hp": "hp", "h p": "hp", "heavy punch": "hp", "fierce": "hp",
    "lk": "lk", "l k": "lk", "light kick": "lk", "short": "lk",
    "mk": "mk", "m k": "mk", "medium kick": "mk", "forward": "mk",
    "hk": "hk", "h k": "hk", "heavy kick": "hk", "roundhouse": "hk",
}

CHARGE_BUTTON_PATTERN = re.compile(
    r"(?<![a-z0-9])([1-9][0-9]*)\s*\[\s*(lp|mp|hp|lk|mk|hk|pp|kk|p|k)\s*\]",
    re.IGNORECASE,
)
CHARGE_UP_MOTION_PATTERN = re.compile(r"(?<![0-9])\[\s*2\s*\]\s*8", re.IGNORECASE)
CHARGE_UP_FOLLOWUP_PATTERN = re.compile(
    r"(?<![0-9])(28k{1,2})\s*(?:~|>|-)\s*(p{1,2}|k{1,2})\b",
    re.IGNORECASE,
)
COMPACT_CHARGE_UP_FOLLOWUP_PATTERN = re.compile(
    r"(?<![0-9])(28k{1,2})(p{1,2})\b",
    re.IGNORECASE,
)


def query_has_charge_button_notation(text):
    return bool(CHARGE_BUTTON_PATTERN.search(str(text or "")))


def normalize_charge_button_notation(text):
    """Turn Street Fighter hold notation such as ``2[HP]`` into parser tokens."""
    return CHARGE_BUTTON_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2).lower()} hold",
        str(text or ""),
    )


def normalize_charge_up_motion_notation(text):
    """Normalize down-charge-up notation and its kick follow-ups."""
    text = CHARGE_UP_MOTION_PATTERN.sub("28", str(text or ""))
    text = CHARGE_UP_FOLLOWUP_PATTERN.sub(
        lambda match: f"{match.group(1).lower()}>{match.group(2).lower()}",
        text,
    )
    return COMPACT_CHARGE_UP_FOLLOWUP_PATTERN.sub(
        lambda match: f"{match.group(1).lower()}>{match.group(2).lower()}",
        text,
    )


def normalize_button_word_notation(text):
    """Convert full button names such as ``heavy punch`` to ``hp``."""
    return re.sub(
        r"\b(?:light|medium|heavy)\s+(?:punch|kick)\b",
        lambda match: _button_alias(match.group(0)),
        str(text or ""),
    )


def _button_alias(value):
    key = re.sub(r"\s+", " ", str(value or "").lower()).strip()
    return BUTTON_ALIASES.get(key, re.sub(r"\s+", "", key))


def query_has_directional_normal_notation(text_lower):
    return bool(
        re.search(rf"\b(?:f|b)\s*(?:\.|\+)?\s*(?:{NORMAL_BUTTON_PATTERN})\b", text_lower)
        or re.search(rf"\b(?:forward|back|backward)\s+(?:{NORMAL_BUTTON_PATTERN})\b", text_lower)
    )


def query_has_grounded_normal_notation(text_lower):
    return bool(
        re.search(
            rf"\b(?:stand|standing|st|s|crouch|crouching|cr|c)\s*\.?\s*(?:{NORMAL_BUTTON_PATTERN})\b",
            text_lower,
        )
    )


def normalize_directional_normal_notation(text):
    text = re.sub(
        rf"\b(f|b)\s*(?:\.|\+)?\s*({NORMAL_BUTTON_PATTERN})\b",
        lambda match: f"{'6' if match.group(1) == 'f' else '4'}{_button_alias(match.group(2))}",
        text,
    )
    return re.sub(
        rf"\b(forward|back|backward)\s+({NORMAL_BUTTON_PATTERN})\b",
        lambda match: f"{'6' if match.group(1) == 'forward' else '4'}{_button_alias(match.group(2))}",
        text,
    )


def normalize_grounded_normal_notation(text):
    return re.sub(
        rf"\b(stand|standing|st|s|crouch|crouching|cr|c)\s*\.?\s*({NORMAL_BUTTON_PATTERN})\b",
        lambda match: f"{'2' if match.group(1) in {'crouch', 'crouching', 'cr', 'c'} else '5'}{_button_alias(match.group(2))}",
        text,
    )


def collect_normal_notation_inputs(text_lower):
    inputs = []
    normalized = normalize_grounded_normal_notation(normalize_directional_normal_notation(text_lower))
    for token in re.findall(r"\b[2456](?:lp|mp|hp|lk|mk|hk)\b", normalized):
        if token not in inputs:
            inputs.append(token)
    return inputs


def append_unique(items, token, *, front=False):
    if not token or token in items:
        return False
    if front:
        items.insert(0, token)
    else:
        items.append(token)
    return True


def append_first_matching_alias(text_lower, extra_inputs, alias_patterns, *, front=False):
    for pattern, alias_token in alias_patterns:
        if re.search(pattern, text_lower):
            append_unique(extra_inputs, alias_token, front=front)
            return alias_token
    return None


def append_all_matching_aliases(text_lower, extra_inputs, alias_patterns):
    matched = []
    for pattern, alias_token in alias_patterns:
        if re.search(pattern, text_lower):
            append_unique(extra_inputs, alias_token)
            matched.append(alias_token)
    return matched


def row_is_charged_variant(row, resolve_character_key=None, normalize_num_cmd_token=None):
    move_name = str(row.get("moveName", "")).lower()
    cmn_name = str(row.get("cmnName", "")).lower()
    num_cmd = str(row.get("numCmd", "")).lower()
    char_key = (
        resolve_character_key(row.get("char_name", ""))
        if resolve_character_key
        else str(row.get("char_name", "")).strip().lower()
    )
    num_cmd_compact = (
        normalize_num_cmd_token(num_cmd)
        if normalize_num_cmd_token
        else re.sub(r"[^a-z0-9]", "", num_cmd)
    )
    akuma_fireball_level = (
        char_key == "akuma"
        and num_cmd_compact == "236p"
        and bool(re.search(r"\blvl\s*[23]\b", num_cmd))
    )
    return (
        "charged" in move_name
        or "charged" in cmn_name
        or "hold" in move_name
        or "hold" in cmn_name
        or "(charged" in num_cmd
        or "(hold" in num_cmd
        or akuma_fireball_level
    )


def row_is_od_variant(row):
    move_name = str(row.get("moveName", "")).lower().strip()
    cmn_name = str(row.get("cmnName", "")).lower().strip()
    num_cmd_compact = re.sub(r"[^a-z0-9]", "", str(row.get("numCmd", "")).lower())
    return (
        move_name.startswith(("od ", "ex "))
        or cmn_name.startswith(("od ", "ex "))
        or num_cmd_compact.endswith(("pp", "kk"))
    )


def row_is_ca_variant(row):
    move_name = str(row.get("moveName", "")).lower()
    cmn_name = str(row.get("cmnName", "")).lower()
    num_cmd = str(row.get("numCmd", "")).lower()
    return (
        "critical art" in move_name
        or "critical art" in cmn_name
        or bool(re.search(r"\(\s*ca\s*\)", num_cmd))
    )


def row_is_stocked_variant(row):
    move_name = str(row.get("moveName", "")).lower()
    cmn_name = str(row.get("cmnName", "")).lower()
    num_cmd = str(row.get("numCmd", "")).lower()
    combined = f"{move_name} {cmn_name} {num_cmd}"
    if re.search(r"\b0\s*stocks?\b", combined):
        return False
    return bool(
        re.search(r"\b[1-9]\d*\s*stocks?\b", combined)
        or "(stock" in move_name
        or "(stock" in cmn_name
        or "(stock" in num_cmd
        or "enhanced" in move_name
        or "enhanced" in cmn_name
        or "(enhanced" in num_cmd
        or "windclad" in move_name
        or "windclad" in cmn_name
        or ("wind stock" in cmn_name and ("(" in cmn_name or "(hold" in num_cmd))
    )


def row_is_air_move(row):
    move_name = str(row.get("moveName", "")).lower()
    cmn_name = str(row.get("cmnName", "")).lower()
    num_cmd = str(row.get("numCmd", "")).lower()
    return (
        "(air" in num_cmd
        or "air" in move_name
        or "air" in cmn_name
        or "aerial" in move_name
        or "aerial" in cmn_name
    )


def query_requests_super_art(text_lower, level, jamie_drink_level=None):
    explicit_super = bool(
        re.search(
            rf"\b(?:sa\s*{level}|super\s+art\s*(?:level\s*)?{level}|super\s*{level})\b",
            text_lower,
        )
    )
    bare_level = bool(re.search(rf"\b(?:lv|lvl|level)\s*{level}\b", text_lower))
    return explicit_super or (jamie_drink_level is None and bare_level)


def token_is_stock_hint(token, stock_hint_tokens=("stock", "stocked", "enhanced", "windclad")):
    token_norm = str(token or "").lower().strip()
    if not token_norm:
        return False
    if token_norm in stock_hint_tokens:
        return True
    return any(
        difflib.SequenceMatcher(None, token_norm, hint_token).ratio() >= 0.82
        for hint_token in stock_hint_tokens
    )


def query_requires_stocked(text_tokens, text_lower):
    stock_hint_tokens = ("stock", "stocked", "enhanced", "windclad")
    return (
        any(token in text_tokens for token in stock_hint_tokens)
        or bool(re.search(r"\bwind\s+clad\b", text_lower))
        or any(token_is_stock_hint(token, stock_hint_tokens) for token in text_tokens)
    )


def row_matches_requested_level(row, query_requests_level2, query_requests_level3):
    if not (query_requests_level2 or query_requests_level3):
        return False
    row_text = " ".join(
        str(row.get(field, "")).lower()
        for field in ("moveName", "cmnName", "numCmd")
    )
    if query_requests_level2 and re.search(r"\b(?:lv|lvl|level)\s*2\b", row_text):
        return True
    if query_requests_level3 and re.search(r"\b(?:lv|lvl|level)\s*3\b", row_text):
        return True
    return False


def query_mentions_fireball_terms(text_lower):
    return bool(re.search(r"\b(?:fireball|hadou?ken|gou\s+hadou?ken|236\s*h?p)\b", text_lower))


def row_matches_explicit_strength(row, strength_query_text, row_is_od_variant):
    row_move_name = str(row.get("moveName", "")).lower().strip()
    row_cmn_name = str(row.get("cmnName", "")).lower().strip()
    row_num_cmd = str(row.get("numCmd", "")).lower().strip()
    row_num_cmd_compact = re.sub(r"[^a-z0-9]", "", row_num_cmd)

    if re.search(r"\b(?:od|ex)\b", strength_query_text):
        return row_is_od_variant(row)

    strength_groups = [
        ({"light", "l", "lp", "lk"}, {"lp", "lk"}),
        ({"medium", "m", "mp", "mk"}, {"mp", "mk"}),
        ({"heavy", "h", "hp", "hk"}, {"hp", "hk"}),
    ]
    requested_suffixes = set()
    for token_group, suffixes in strength_groups:
        if any(re.search(rf"\b{re.escape(token)}\b", strength_query_text) for token in token_group):
            requested_suffixes.update(suffixes)
    if not requested_suffixes:
        return False
    if any(
        row_move_name.startswith(f"{suffix} ") or row_cmn_name.startswith(f"{suffix} ")
        for suffix in requested_suffixes
    ):
        return True
    if any(
        row_move_name.startswith(f"{word} ") or row_cmn_name.startswith(f"{word} ")
        for word in ("light", "medium", "heavy")
        if word[0] in {suffix[0] for suffix in requested_suffixes}
    ):
        return True
    return row_num_cmd_compact.endswith(tuple(requested_suffixes))


def apply_explicit_strength_result_filter(
    rows,
    *,
    query_has_explicit_strength,
    query_wants_od_strength,
    query_wants_non_od_strength,
    text_lower,
    row_is_od_variant,
):
    if not query_has_explicit_strength or not rows:
        return rows
    if query_wants_od_strength:
        od_rows = [row for row in rows if row_is_od_variant(row)]
        return od_rows or rows
    if query_wants_non_od_strength:
        exact_rows = [
            row for row in rows
            if row_matches_explicit_strength(row, text_lower, row_is_od_variant)
        ]
        if exact_rows:
            return exact_rows
        non_od_rows = [row for row in rows if not row_is_od_variant(row)]
        return non_od_rows or rows
    return rows

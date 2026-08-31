"""Shared helpers for SF6 parser alias collection and normal notation."""

import re

from bubbot.utils.text_utils import correct_alias_typos


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


def normalize_direction_word_motion_notation(text):
    """Convert word-based motion notation like ``down down mk`` to ``22mk``."""
    value = str(text or "")
    # Common motion shorthands
    value = re.sub(r"\bquarter\s+circle\s+forward\b", "236", value, flags=re.IGNORECASE)
    value = re.sub(r"\bqcf\b", "236", value, flags=re.IGNORECASE)
    value = re.sub(r"\bquarter\s+circle\s+back\b", "214", value, flags=re.IGNORECASE)
    value = re.sub(r"\bqcb\b", "214", value, flags=re.IGNORECASE)
    value = re.sub(r"\bhalf\s+circle\s+forward\b", "41236", value, flags=re.IGNORECASE)
    value = re.sub(r"\bhcf\b", "41236", value, flags=re.IGNORECASE)
    value = re.sub(r"\bhalf\s+circle\s+back\b", "63214", value, flags=re.IGNORECASE)
    value = re.sub(r"\bhcb\b", "63214", value, flags=re.IGNORECASE)
    value = re.sub(r"\bdragon\s+punch\b", "623", value, flags=re.IGNORECASE)
    # Diagonals before single directions (must be first)
    value = re.sub(r"\bdown\s*[-]?\s*forward\b", "3", value, flags=re.IGNORECASE)
    value = re.sub(r"\bdown\s*[-]?\s*back\b", "1", value, flags=re.IGNORECASE)
    value = re.sub(r"\bup\s*[-]?\s*forward\b", "9", value, flags=re.IGNORECASE)
    value = re.sub(r"\bup\s*[-]?\s*back\b", "7", value, flags=re.IGNORECASE)
    value = re.sub(r"\bdf\b", "3", value, flags=re.IGNORECASE)
    value = re.sub(r"\bdb\b", "1", value, flags=re.IGNORECASE)
    value = re.sub(r"\buf\b", "9", value, flags=re.IGNORECASE)
    value = re.sub(r"\bub\b", "7", value, flags=re.IGNORECASE)

    direction_word_map = {"down": "2", "up": "8", "back": "4", "forward": "6"}

    pattern = re.compile(
        r"\b((?:down|up|back|forward|[12346789])(?:\s*[,+\->]*\s*(?:down|up|back|forward|[12346789]))*)\s*\+?\s*(lp|mp|hp|lk|mk|hk|pp|kk|p|k)\b",
        re.IGNORECASE,
    )

    def _repl(match):
        dir_seq = match.group(1)
        button = match.group(2).lower()
        tokens = re.findall(r"\b(?:down|up|back|forward)\b|[12346789]", dir_seq, flags=re.IGNORECASE)
        digits = "".join(direction_word_map.get(tok.lower(), tok) for tok in tokens)
        if not digits:
            return match.group(0)
        return f"{digits}{button}"

    return pattern.sub(_repl, value)


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


def query_mentions_loaded_move_name(text_tokens, rows):
    """Return whether the query contains a distinctive move name from loaded data."""
    strength_prefix = re.compile(
        r"^(?:od|ex|lp|mp|hp|lk|mk|hk|pp|kk|light|medium|heavy|l|m|h)\s+"
    )
    candidate_sequences = []
    loaded_name_aliases = {}
    for row in rows or ():
        for field in ("moveName", "cmnName"):
            raw_name = str(row.get(field, "")).lower().split("(", 1)[0].strip()
            if raw_name:
                loaded_name_aliases[raw_name] = raw_name
            base_name = strength_prefix.sub("", raw_name).strip()
            candidate_tokens = re.findall(r"[a-z0-9]+", base_name)
            if not candidate_tokens:
                continue
            if len(candidate_tokens) == 1 and len(candidate_tokens[0]) < 4:
                continue
            candidate_sequences.append(candidate_tokens)

    def contains_candidate(tokens):
        for candidate_tokens in candidate_sequences:
            candidate_length = len(candidate_tokens)
            if any(
                tokens[index:index + candidate_length] == candidate_tokens
                for index in range(len(tokens) - candidate_length + 1)
            ):
                return True
        return False

    if contains_candidate(text_tokens):
        return True
    corrected_text = correct_alias_typos(" ".join(text_tokens), loaded_name_aliases)
    corrected_tokens = re.findall(r"[a-z0-9]+", corrected_text)
    return corrected_tokens != text_tokens and contains_candidate(corrected_tokens)


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

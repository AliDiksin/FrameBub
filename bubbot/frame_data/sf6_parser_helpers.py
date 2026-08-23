"""Shared helpers for SF6 parser alias collection and normal notation."""

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

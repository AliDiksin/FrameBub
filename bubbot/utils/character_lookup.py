import re

from bubbot.utils.text_utils import compact_key, contains_token_sequence, word_tokens


def resolve_alias_key(value, aliases, valid_keys, normalize_fn=compact_key):
    """Resolve a direct value through canonical keys and alias mappings."""
    normalized = normalize_fn(value)
    if not normalized:
        return None
    valid_key_list = list(valid_keys or [])
    valid_key_set = set(valid_key_list)
    for key in valid_key_list:
        if normalize_fn(key) == normalized:
            return key
    for alias, canonical in (aliases or {}).items():
        if canonical in valid_key_set and normalize_fn(alias) == normalized:
            return canonical
    return None


def find_aliases_in_text(text, aliases, valid_keys, *, include_positions=False, longest_first=True):
    """Find canonical aliases mentioned in text using contiguous word tokens."""
    tokens = word_tokens(text)
    if not tokens:
        return []
    valid_key_list = list(valid_keys or [])
    valid_key_set = set(valid_key_list)
    candidates = [(str(key), key) for key in valid_key_list]
    for alias, canonical in (aliases or {}).items():
        if canonical in valid_key_set:
            candidates.append((str(alias), canonical))
    if longest_first:
        candidates.sort(key=lambda item: len(word_tokens(item[0])), reverse=True)

    found = []
    seen = set()
    lowered = str(text or "").lower()
    for alias, canonical in candidates:
        alias_tokens = word_tokens(alias)
        if not contains_token_sequence(tokens, alias_tokens):
            continue
        if canonical in seen:
            continue
        seen.add(canonical)
        if include_positions:
            start = lowered.find(str(alias).lower())
            end = start + len(str(alias)) if start >= 0 else start
            found.append((canonical, start, end, alias))
        else:
            found.append(canonical)
    return found


def text_mentions_alias(text, aliases, valid_keys):
    """Return True when text mentions any valid canonical key or alias."""
    return bool(find_aliases_in_text(text, aliases, valid_keys, longest_first=False))


def find_alias_positions_in_text(text, aliases, valid_keys):
    """Find aliases with character offsets using token boundaries."""
    lowered = str(text or "").lower()
    valid_key_set = set(valid_keys or [])
    matches = []
    alias_items = sorted((aliases or {}).items(), key=lambda item: len(item[0]), reverse=True)
    for alias, canonical in alias_items:
        if canonical not in valid_key_set:
            continue
        pattern = rf"(?<![a-z0-9]){re.escape(str(alias).lower())}(?![a-z0-9])"
        match = re.search(pattern, lowered)
        if match:
            matches.append((canonical, match.start(), match.end(), alias))
    return unique_position_matches(matches)


def unique_position_matches(matches):
    deduped = []
    seen = set()
    for item in sorted(matches or [], key=lambda value: value[1]):
        if item[0] in seen:
            continue
        seen.add(item[0])
        deduped.append(item)
    return deduped

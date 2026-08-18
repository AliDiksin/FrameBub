"""Resolve and discover character aliases inside natural-language text."""

import re

from bubbot.utils.text_utils import NOISE_WORDS, compact_key, contains_token_sequence, word_tokens


FUZZY_CHARACTER_STOP_WORDS = NOISE_WORDS | {
    "active", "advantage", "air", "attack", "block", "cancel", "combo", "combos",
    "counter", "damage", "data", "drive", "fighter", "framedata", "frames", "game",
    "gatling", "gif", "gifs", "grab", "guard", "heavy", "high", "hit", "hitbox",
    "image", "invuln", "jump", "kick", "light", "low", "medium", "menu", "meter",
    "move", "moves", "notes", "overhead", "picture", "proration", "punch", "punish",
    "quiz", "range", "recovery", "risc", "route", "routes", "stance", "startup",
    "street", "stun", "super", "throw", "total",
    "sf5", "sf6", "sfv", "ggst", "ggacr", "bbcf", "cotw", "mk1", "tuco",
}


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


def find_fuzzy_aliases_in_text(text, aliases, valid_keys):
    """Find exact, compact, or unambiguous one-edit character names."""
    return [match[0] for match in find_alias_positions_in_text(text, aliases, valid_keys)]


def text_mentions_alias(text, aliases, valid_keys):
    """Return True when text mentions any valid canonical key or alias."""
    return bool(find_alias_positions_in_text(text, aliases, valid_keys))


def find_alias_positions_in_text(text, aliases, valid_keys):
    """Find exact, compact, or unambiguous one-edit aliases with offsets."""
    lowered = str(text or "").lower()
    valid_key_set = set(valid_keys or [])
    matches = []
    alias_items = [(str(key), key) for key in valid_key_set]
    alias_items.extend((str(alias), canonical) for alias, canonical in (aliases or {}).items())
    alias_items = sorted(alias_items, key=lambda item: len(item[0]), reverse=True)
    for alias, canonical in alias_items:
        if canonical not in valid_key_set:
            continue
        pattern = rf"(?<![a-z0-9]){re.escape(str(alias).lower())}(?![a-z0-9])"
        match = re.search(pattern, lowered)
        if match:
            matches.append((canonical, match.start(), match.end(), alias))
    exact_matches = unique_position_matches(matches)

    token_matches = list(re.finditer(r"[a-z0-9]+", lowered))
    candidates = {}
    for alias, canonical in alias_items:
        compact = compact_key(alias)
        if canonical in valid_key_set and len(compact) >= 3 and compact.isalpha():
            candidates.setdefault(compact, set()).add(canonical)
    max_words = max((len(word_tokens(alias)) for alias, _canonical in alias_items), default=1)
    fuzzy_matches = []
    for index in range(len(token_matches)):
        for size in range(1, min(max_words, len(token_matches) - index) + 1):
            span = token_matches[index:index + size]
            if any(span[0].start() < match[2] and span[-1].end() > match[1] for match in exact_matches):
                continue
            token = compact_key(lowered[span[0].start():span[-1].end()])
            if len(token) < 3 or not token.isalpha() or (size == 1 and token in FUZZY_CHARACTER_STOP_WORDS):
                continue
            ranked = []
            for candidate, canonicals in candidates.items():
                if token == candidate:
                    distance = 0
                elif _is_one_typo_apart(token, candidate):
                    distance = 1
                else:
                    continue
                for canonical in canonicals:
                    ranked.append((distance, -len(candidate), canonical, candidate))
            if not ranked:
                continue
            ranked.sort()
            best = ranked[0]
            tied = {item[2] for item in ranked if item[:2] == best[:2]}
            if len(tied) == 1:
                fuzzy_matches.append((best[2], span[0].start(), span[-1].end(), lowered[span[0].start():span[-1].end()]))
    return unique_position_matches([*exact_matches, *fuzzy_matches])


def _is_one_typo_apart(left, right):
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        mismatches = [index for index, pair in enumerate(zip(left, right)) if pair[0] != pair[1]]
        return len(mismatches) == 1 or (
            len(mismatches) == 2
            and mismatches[1] == mismatches[0] + 1
            and left[mismatches[0]] == right[mismatches[1]]
            and left[mismatches[1]] == right[mismatches[0]]
        )
    shorter, longer = (left, right) if len(left) < len(right) else (right, left)
    index = 0
    while index < len(shorter) and shorter[index] == longer[index]:
        index += 1
    return shorter[index:] == longer[index + 1:]


def unique_position_matches(matches):
    deduped = []
    seen = set()
    for item in sorted(matches or [], key=lambda value: value[1]):
        if item[0] in seen:
            continue
        seen.add(item[0])
        deduped.append(item)
    return deduped

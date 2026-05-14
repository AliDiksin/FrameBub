import re


COMPARISON_RE = re.compile(r"\b(?:vs|versus|compare|comparison)\b")
SPLIT_RE = re.compile(r"\b(?:vs|versus)\b")


def is_comparison_query(text, char_matches):
    return len(char_matches or []) >= 2 and bool(COMPARISON_RE.search(str(text or "").lower()))


def unique_char_matches(char_matches):
    seen = set()
    unique = []
    for match in char_matches or []:
        char_key = match[0]
        if char_key in seen:
            continue
        seen.add(char_key)
        unique.append(match)
    return unique


def remove_match_spans(text, matches):
    cleaned = str(text or "")
    spans = [match[1:3] for match in matches or [] if match[1] >= 0 and match[2] >= 0]
    for start, end in sorted(spans, reverse=True):
        cleaned = f"{cleaned[:start]} {cleaned[end:]}"
    return re.sub(r"\s+", " ", cleaned).strip()


def strip_comparison_terms(text):
    cleaned = re.sub(r"\b(?:vs|versus|compare|comparison|which|is|faster|better|and)\b", " ", str(text or "").lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def find_comparison_rows(
    text,
    char_matches,
    *,
    find_characters_in_text,
    find_rows_for_char,
):
    """Resolve same-button and side-specific character comparisons.

    `find_rows_for_char(char_key, move_text)` must return that game's normal
    matching rows for one character and one move query.
    """
    lowered = str(text or "").lower()
    ordered_matches = unique_char_matches(char_matches)
    if not is_comparison_query(lowered, ordered_matches):
        return None

    rows_by_char = {}
    disambiguation = None

    def try_add_match(char_key, move_text):
        nonlocal disambiguation
        query = strip_comparison_terms(move_text)
        if not query:
            return False
        matches = find_rows_for_char(char_key, query) or []
        if len(matches) > 1:
            disambiguation = {"char_key": char_key, "rows": matches}
            return False
        if matches:
            rows_by_char.setdefault(char_key, matches[0])
            return True
        return False

    for segment in [part.strip() for part in SPLIT_RE.split(lowered) if part.strip()]:
        segment_matches = unique_char_matches(find_characters_in_text(segment))
        if not segment_matches:
            continue
        segment_move_text = remove_match_spans(segment, segment_matches)
        for char_key, _start, _end, _alias in segment_matches:
            try_add_match(char_key, segment_move_text)
            if disambiguation:
                return {"needs_disambiguation": True, **disambiguation}

    common_move_text = remove_match_spans(lowered, ordered_matches)
    for char_key, _start, _end, _alias in ordered_matches:
        if char_key in rows_by_char:
            continue
        try_add_match(char_key, common_move_text)
        if disambiguation:
            return {"needs_disambiguation": True, **disambiguation}

    rows = [rows_by_char[match[0]] for match in ordered_matches if match[0] in rows_by_char]
    if len(rows) < 2:
        return None
    return {"rows": rows, "char_key": ordered_matches[0][0]}

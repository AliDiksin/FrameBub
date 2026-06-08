"""Prefix-boundary notation matching shared across frame-data parsers."""

from __future__ import annotations

import re
from typing import Callable, Iterable, Optional, Pattern

DEFAULT_NOTATION_SUFFIX_RE = re.compile(
    r"^(?:"
    r"lv\d+|"
    r"ex|od|pp|kk|"
    r"abc(?:foot|drill)?(?:lv\d+)?|"
    r"followup(?:od)?|hold|foot|drill|cancel|cl|far|close|air|j|"
    r"[a-d]|"
    r"[lmh]?[pk]|"
    r"sa[123]"
    r")+",
    re.IGNORECASE,
)

NOTATION_QUERY_PATTERNS: dict[str, Pattern[str]] = {
    "digit_button": re.compile(r"^(?:j)?(?:[1-9][a-z]{1,3}|[0-9]{2,8}[a-z]{1,3})$", re.IGNORECASE),
    "sf_button": re.compile(r"^(?:[1-9][0-9]{0,5})?(?:lp|mp|hp|lk|mk|hk|pp|kk)$", re.IGNORECASE),
    "motion_digits": re.compile(r"^(?:j)?[0-9]{2,8}$", re.IGNORECASE),
    "third_strike": re.compile(r"^(?:j)?(?:[1-9][0-9]{0,5})?(?:[lmh]?[pk]|sa[123])$", re.IGNORECASE),
    "mk1": re.compile(r"^(?:[bfdu]{1,3}[1-4]+|[1-4]{1,4}|[1-9]{2,8})(?:ex)?$", re.IGNORECASE),
    "ggst": re.compile(r"^(?:[1-9][0-9]{0,5})?[shpkd]$|^[1-9][0-9]{2,8}[shpkd]$", re.IGNORECASE),
}

SF6_NOTATION_STYLES = ("digit_button", "sf_button", "motion_digits")


def looks_like_sf6_notation_query(query_key: str) -> bool:
    return looks_like_notation_query(query_key, *SF6_NOTATION_STYLES)


def looks_like_notation_query(query_key: str, *styles: str) -> bool:
    text = str(query_key or "").strip()
    if not text:
        return False
    for style in styles:
        pattern = NOTATION_QUERY_PATTERNS.get(style)
        if pattern and pattern.fullmatch(text):
            return True
    return False


def notation_prefix_matches_row_key(
    query_key: str,
    row_key: str,
    *,
    suffix_pattern: Optional[Pattern[str]] = None,
) -> bool:
    query_key = str(query_key or "")
    row_key = str(row_key or "")
    if not query_key or not row_key:
        return False
    if query_key == row_key:
        return True
    if not row_key.startswith(query_key):
        return False
    suffix = row_key[len(query_key) :]
    if not suffix:
        return True
    if suffix[0].isdigit():
        return False
    pattern = suffix_pattern or DEFAULT_NOTATION_SUFFIX_RE
    return bool(pattern.match(suffix))


def row_notation_keys_from_num_cmd(num_cmd: str, normalize_fn: Callable[[str], str]) -> set[str]:
    keys: set[str] = set()
    text = str(num_cmd or "").strip()
    if not text:
        return keys
    keys.add(normalize_fn(text))
    state_stripped = re.sub(r"\[\s*w\s*\]", "", text, flags=re.IGNORECASE)
    if state_stripped != text:
        keys.add(normalize_fn(state_stripped))
    motion_match = re.match(r"^([1-9][0-9]*)([A-Za-z]+(?:/[A-Za-z]+)+)$", text)
    if motion_match:
        motion, buttons = motion_match.groups()
        for button in buttons.split("/"):
            keys.add(normalize_fn(f"{motion}{button}"))
    return {key for key in keys if key}


def find_rows_by_notation_prefix(
    rows: Iterable[dict],
    query_key: str,
    *,
    normalize_fn: Callable[[str], str],
    looks_like_fn: Callable[[str], bool],
    extra_row_keys_fn: Optional[Callable[[dict], Iterable[str]]] = None,
    suffix_pattern: Optional[Pattern[str]] = None,
) -> list[dict]:
    if not looks_like_fn(query_key):
        return []
    matches = []
    for row in rows or []:
        row_keys = row_notation_keys_from_num_cmd(row.get("numCmd", ""), normalize_fn)
        if extra_row_keys_fn:
            row_keys.update(str(key) for key in extra_row_keys_fn(row) if key)
        if any(
            notation_prefix_matches_row_key(query_key, row_key, suffix_pattern=suffix_pattern)
            for row_key in row_keys
        ):
            matches.append(row)
    return matches


def exact_row_key_matches(rows: Iterable[dict], query_key: str, row_keys_fn: Callable[[dict], set[str]]) -> list[dict]:
    return [row for row in rows or [] if query_key in row_keys_fn(row)]

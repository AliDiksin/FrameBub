"""Shared multi-row matching: notation prefix, exact keys, name haystack, fuzzy."""
# Matching stages are ordered from exact notation to fuzzy text so precise input always wins.

from __future__ import annotations

import difflib
import re
from typing import Callable, Iterable, Optional

from bubbot.utils.notation_match_utils import (
    exact_row_key_matches,
    find_rows_by_notation_prefix,
)


def normalized_query_words(query: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(query or "").lower()).strip()


def row_field_haystack(row: dict, fields: Iterable[str]) -> str:
    parts = []
    for field in fields:
        text = re.sub(r"[^a-z0-9]+", " ", str(row.get(field, "")).lower()).strip()
        if text:
            parts.append(text)
    return " ".join(parts)


def match_rows_by_name_substring(
    rows: Iterable[dict],
    query: str,
    *,
    query_key: str,
    looks_like_fn: Callable[[str], bool],
    name_fields: tuple[str, ...] = ("moveName",),
    num_cmd_field: str = "numCmd",
    include_num_cmd: Optional[bool] = None,
) -> list[dict]:
    words = normalized_query_words(query)
    if not words:
        return []
    use_num_cmd = not looks_like_fn(query_key) if include_num_cmd is None else include_num_cmd
    matches = []
    for row in rows or []:
        fields = list(name_fields)
        if use_num_cmd:
            fields.append(num_cmd_field)
        haystack = row_field_haystack(row, fields)
        if words in haystack:
            matches.append(row)
    return matches


def match_rows_by_fuzzy_keys(
    rows: Iterable[dict],
    query_key: str,
    *,
    value_fields: tuple[str, ...],
    normalize_fn: Callable[[str], str],
    cutoff: float = 0.84,
    n: int = 4,
) -> list[dict]:
    if not query_key:
        return []
    candidates = []
    for row in rows or []:
        for field in value_fields:
            key = normalize_fn(str(row.get(field, "")))
            if key:
                candidates.append((key, row))
    if not candidates:
        return []
    close_keys = difflib.get_close_matches(query_key, [key for key, _row in candidates], n=n, cutoff=cutoff)
    return [row for key, row in candidates if key in close_keys]


def find_matching_rows_standard(
    rows: Iterable[dict],
    query: str,
    query_key: str,
    *,
    normalize_fn: Callable[[str], str],
    looks_like_fn: Callable[[str], bool],
    row_keys_fn: Callable[[dict], set[str]],
    dedupe_fn: Callable[[list[dict]], list[dict]],
    name_fields: tuple[str, ...] = ("moveName",),
    include_num_cmd: Optional[bool] = None,
    fuzzy_value_fields: Optional[tuple[str, ...]] = None,
    fuzzy_cutoff: float = 0.84,
    fuzzy_n: int = 4,
    post_notation: Optional[Callable[[list[dict]], list[dict]]] = None,
    post_exact: Optional[Callable[[list[dict]], list[dict]]] = None,
    post_name: Optional[Callable[[list[dict]], list[dict]]] = None,
    extra_row_keys_fn: Optional[Callable[[dict], Iterable[str]]] = None,
) -> list[dict]:
    """Notation prefix -> exact keys -> name haystack -> fuzzy keys."""
    if not query_key:
        return []

    row_list = list(rows or [])
    fuzzy_fields = fuzzy_value_fields or (name_fields[0], "numCmd")

    notation_matches = find_rows_by_notation_prefix(
        row_list,
        query_key,
        normalize_fn=normalize_fn,
        looks_like_fn=looks_like_fn,
        extra_row_keys_fn=extra_row_keys_fn,
    )
    if notation_matches:
        if post_notation:
            notation_matches = post_notation(notation_matches)
        if notation_matches:
            return dedupe_fn(notation_matches)

    exact = exact_row_key_matches(row_list, query_key, row_keys_fn)
    if exact:
        if post_exact:
            exact = post_exact(exact)
        if exact:
            return dedupe_fn(exact)

    name_matches = match_rows_by_name_substring(
        row_list,
        query,
        query_key=query_key,
        looks_like_fn=looks_like_fn,
        name_fields=name_fields,
        include_num_cmd=include_num_cmd,
    )
    if name_matches:
        if post_name:
            name_matches = post_name(name_matches)
        if name_matches:
            return dedupe_fn(name_matches)

    fuzzy = match_rows_by_fuzzy_keys(
        row_list,
        query_key,
        value_fields=fuzzy_fields,
        normalize_fn=normalize_fn,
        cutoff=fuzzy_cutoff,
        n=fuzzy_n,
    )
    return dedupe_fn(fuzzy)

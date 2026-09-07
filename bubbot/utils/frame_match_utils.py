"""Shared multi-row matching: notation prefix, exact keys, name haystack, fuzzy."""

from __future__ import annotations

import difflib
import re
from typing import Callable, Iterable, Optional

from bubbot.utils.notation_match_utils import (
    exact_row_key_matches,
    find_rows_by_notation_prefix,
)


def query_requests_air_move(query):
    return bool(re.search(
        r"\b(?:air|aerial|airborne|jump(?:ing)?)\b|(?<![a-z0-9])j(?=[.\s(1-9])"
        r"|(?<![a-z0-9])j[a-dhklmpst]{1,2}(?![a-z])|\b[789]\s*(?:[lmh][pk]|[a-dhpkst])\b",
        str(query or ""), re.IGNORECASE,
    ))


def row_is_air_move(row):
    # Use identity fields, not notes/guard text that may describe anti-air properties.
    context = " ".join(str(row.get(field) or "") for field in (
        "numCmd", "version", "moveType", "section", "subsection",
    )).replace("_", " ")
    names = " ".join(str(row.get(field) or "") for field in ("moveName", "cmnName"))
    return query_requests_air_move(context) or bool(re.search(
        r"\(\s*air\b|\b(?:aerial|airborne|jump(?:ing)?)\b|(?<![a-z0-9])j[.\s]*[1-9]",
        names, re.IGNORECASE,
    ))


def prefer_grounded_rows(rows, query):
    """Prefer grounded candidates unless air is explicit; retain air-only moves."""
    rows = list(rows or [])
    if query_requests_air_move(query):
        return rows
    grounded = [row for row in rows if not row_is_air_move(row)]
    return grounded or rows


STRENGTH_ALIASES = (
    ("light punch", frozenset({"LP"})),
    ("medium punch", frozenset({"MP"})),
    ("heavy punch", frozenset({"HP"})),
    ("light kick", frozenset({"LK"})),
    ("medium kick", frozenset({"MK"})),
    ("heavy kick", frozenset({"HK"})),
    ("light", frozenset({"LP", "LK"})),
    ("medium", frozenset({"MP", "MK"})),
    ("heavy", frozenset({"HP", "HK"})),
    ("lp", frozenset({"LP"})),
    ("mp", frozenset({"MP"})),
    ("hp", frozenset({"HP"})),
    ("lk", frozenset({"LK"})),
    ("mk", frozenset({"MK"})),
    ("hk", frozenset({"HK"})),
    ("ex", frozenset({"EX"})),
    ("od", frozenset({"EX"})),
    ("l", frozenset({"LP", "LK"})),
    ("m", frozenset({"MP", "MK"})),
    ("h", frozenset({"HP", "HK"})),
)


def parse_strength_qualifier(query: str) -> tuple[str, Optional[frozenset[str]], bool]:
    """Return a strength-free query, requested row strengths, and embedded-notation flag."""
    text = re.sub(r"\s+", " ", str(query or "").lower()).strip()
    for alias, strengths in STRENGTH_ALIASES:
        prefix = f"{alias} "
        suffix = f" {alias}"
        if text.startswith(prefix):
            return text[len(prefix) :].strip(), strengths, False
        if text.endswith(suffix):
            return text[: -len(suffix)].strip(), strengths, False

    notation = re.fullmatch(r"((?:j)?[1-9][0-9]{0,5})(lp|mp|hp|lk|mk|hk)", text)
    if notation:
        motion, button = notation.groups()
        return f"{motion}{button[-1]}", frozenset({button.upper()}), True
    return text, None, False


def row_strengths(row: dict) -> frozenset[str]:
    """Extract an explicit strength, preferring version/name data over grouped commands."""
    marker_re = re.compile(r"(?<![A-Z0-9])(LP|MP|HP|LK|MK|HK|EX|OD)(?![A-Z0-9])", re.IGNORECASE)
    compact_buttons_re = re.compile(r"(?<![A-Z])((?:(?:LP|MP|HP|LK|MK|HK)){2,})(?![A-Z])", re.IGNORECASE)

    def markers_in(value, *, command=False):
        text = str(value or "")
        markers = [marker.upper() for marker in marker_re.findall(text)]
        for compact_buttons in compact_buttons_re.findall(text):
            markers.extend(re.findall(r"LP|MP|HP|LK|MK|HK", compact_buttons.upper()))
        if command and re.search(r"(?:^|[0-9])(?:PP|KK)(?![A-Z0-9])", text, re.IGNORECASE):
            markers.append("EX")
        return frozenset("EX" if marker == "OD" else marker for marker in markers)

    version_markers = markers_in(row.get("version", ""))
    if version_markers:
        return version_markers

    name_markers = frozenset().union(*(markers_in(row.get(field, "")) for field in ("moveName", "cmnName")))
    if name_markers:
        return name_markers

    for field in ("numCmd", "nickname", "plnCmd"):
        value = str(row.get(field, ""))
        markers = set(markers_in(value, command=field in {"numCmd", "plnCmd"}))
        markers.update(marker.upper() for marker in re.findall(r"[1-9][0-9]*(LP|MP|HP|LK|MK|HK)(?![A-Z0-9])", value, re.IGNORECASE))
        if markers:
            return frozenset(markers)
    return frozenset()


def filter_rows_by_strength(rows: Iterable[dict], strengths: Optional[frozenset[str]]) -> list[dict]:
    """Narrow strength-aware rows, retaining shared rows that encode no strength."""
    row_list = list(rows or [])
    if not strengths:
        return row_list
    marked_rows = [(row, row_strengths(row)) for row in row_list]
    matching = [row for row, markers in marked_rows if markers & strengths]
    if matching:
        return matching
    if any(markers for _row, markers in marked_rows):
        return []
    return row_list


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
    original_query: Optional[str] = None,
) -> list[dict]:
    """Notation prefix -> exact keys -> name haystack -> fuzzy keys."""
    if not query_key:
        return []

    row_list = list(rows or [])
    fuzzy_fields = fuzzy_value_fields or (name_fields[0], "numCmd")
    context = f"{original_query or ''} {query}"

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
            return dedupe_fn(prefer_grounded_rows(notation_matches, context))

    exact = exact_row_key_matches(row_list, query_key, row_keys_fn)
    if exact:
        if post_exact:
            exact = post_exact(exact)
        if exact:
            return dedupe_fn(prefer_grounded_rows(exact, context))

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
            return dedupe_fn(prefer_grounded_rows(name_matches, context))

    fuzzy = match_rows_by_fuzzy_keys(
        row_list,
        query_key,
        value_fields=fuzzy_fields,
        normalize_fn=normalize_fn,
        cutoff=fuzzy_cutoff,
        n=fuzzy_n,
    )
    return dedupe_fn(prefer_grounded_rows(fuzzy, context))

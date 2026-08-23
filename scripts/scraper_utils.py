"""Shared MediaWiki raw-page helpers for Dustloop and other wiki scrapers.

Provides template extraction, heading context, and cached raw fetches.
"""
# Scrapers share raw-page mechanics but keep game-specific extraction and schema decisions local.

from __future__ import annotations

import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

TWOKO_CHAMPIONS = (
    "Ahri",
    "Akali",
    "Blitzcrank",
    "Braum",
    "Caitlyn",
    "Darius",
    "Ekko",
    "Illaoi",
    "Jinx",
    "Senna",
    "Teemo",
    "Thresh",
    "Vi",
    "Warwick",
    "Yasuo",
)

TWOKO_MOVE_COLUMNS = (
    "char_key",
    "char_name",
    "section",
    "subsection",
    "moveName",
    "numCmd",
    "dmg",
    "guardLevel",
    "startup",
    "active",
    "recovery",
    "onBlock",
    "onHit",
    "meterGain",
    "xx",
    "invuln",
    "extraInfo",
)

DUSTLOOP_API = "https://www.dustloop.com/wiki/api.php"
USER_AGENT = "Mozilla/5.0 (compatible; Bub wiki scraper/1.0)"


@dataclass
class TemplateRecord:
    name: str
    params: dict[str, str]
    raw: str
    start: int = 0
    end: int = 0
    section: str = ""
    subsection: str = ""


def replace_wiki_templates(text: str) -> str:
    text = re.sub(
        r"\{\{clr\|[^|{}]+\|((?:[^{}]|\{[^{}]*\})+)\}\}",
        r"\1",
        text,
        flags=re.IGNORECASE,
    )

    def replacement(match: re.Match[str]) -> str:
        try:
            name, params = parse_template(match.group(0))
        except ValueError:
            return ""
        positional = [params[key] for key in sorted((key for key in params if key.isdigit()), key=int)]
        if name == "framedatanotes":
            values = positional[1:] if positional and positional[0].lower() == "ggst" else positional
            return f"{values[0]}: {'; '.join(values[1:])}" if len(values) > 1 else (values[0] if values else "")
        if name in {"clr", "keyword", "hlt"}:
            return positional[-1] if positional else ""
        if name == "!":
            return "|"
        if name.startswith("#"):
            return ""
        return params.get("label") or params.get("input") or (positional[-1] if positional else "")

    while re.search(r"\{\{[^{}]*\}\}", text):
        text = re.sub(r"\{\{[^{}]*\}\}", replacement, text)
    return text


def clean_wiki_text(value: object) -> str:
    text = str(value or "")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = replace_wiki_templates(text)
    text = re.sub(r"</?[^>]+>", "", text)
    text = re.sub(r"\[\[([^|\]]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", lambda match: match.group(1).split("/")[-1], text)
    text = re.sub(r"\[https?://[^\s\]]+\s+([^\]]+)\]", r"\1", text)
    text = text.replace("'''", "").replace("''", "")
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"^[ \t]*\*+[ \t]*", "- ", text, flags=re.MULTILINE)
    text = re.sub(r"^[ \t]*;+[ \t]*", "", text, flags=re.MULTILINE)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_template_span(text: str, start: int) -> tuple[str, int]:
    if not text.startswith("{{", start):
        raise ValueError("Template does not start at the given position")
    depth = 0
    index = start
    length = len(text)
    while index < length - 1:
        if text[index : index + 2] == "{{":
            depth += 1
            index += 2
            continue
        if text[index : index + 2] == "}}":
            depth -= 1
            index += 2
            if depth == 0:
                return text[start:index], index
            continue
        index += 1
    raise ValueError("Unclosed template")


def parse_template(span: str) -> tuple[str, dict[str, str]]:
    body = span.strip()
    if not body.startswith("{{") or not body.endswith("}}"):
        raise ValueError("Invalid template span")
    body = body[2:-2].strip()
    if not body:
        return "", {}
    parts = []
    current = []
    template_depth = 0
    link_depth = 0
    index = 0
    while index < len(body):
        pair = body[index : index + 2]
        if pair == "{{":
            template_depth += 1
            current.extend(pair)
            index += 2
            continue
        elif pair == "}}":
            template_depth -= 1
            current.extend(pair)
            index += 2
            continue
        elif pair == "[[":
            link_depth += 1
            current.extend(pair)
            index += 2
            continue
        elif pair == "]]":
            link_depth -= 1
            current.extend(pair)
            index += 2
            continue
        if body[index] == "|" and template_depth == 0 and link_depth == 0:
            parts.append("".join(current).strip())
            current = []
            index += 1
            continue
        current.append(body[index])
        index += 1
    parts.append("".join(current).strip())
    name = parts[0].strip().lower()
    params: dict[str, str] = {}
    for part in parts[1:]:
        if "=" in part:
            key, value = part.split("=", 1)
            params[key.strip().lower()] = value.strip()
        elif part:
            params[str(len(params))] = part
    return name, params


def extract_templates(text: str, names: set[str]) -> list[TemplateRecord]:
    lowered_names = {str(name or "").strip().lower() for name in names if str(name or "").strip()}
    records: list[TemplateRecord] = []
    for match in re.finditer(r"\{\{", text):
        start = match.start()
        try:
            span, end = extract_template_span(text, start)
            template_name, _params = parse_template(span)
        except ValueError:
            continue
        if template_name not in lowered_names:
            continue
        _, params = parse_template(span)
        records.append(TemplateRecord(name=template_name, params=params, raw=span, start=start, end=end))
    return records


def extract_headings(text: str) -> list[tuple[int, int, str]]:
    headings: list[tuple[int, int, str]] = []
    for match in re.finditer(r"^(=+)\s*(.+?)\s*\1\s*$", text, flags=re.MULTILINE):
        level = len(match.group(1))
        title = clean_wiki_text(match.group(2))
        if title:
            headings.append((level, match.start(), title))
    return headings


def apply_heading_context(records: list[TemplateRecord], headings: list[tuple[int, int, str]]) -> None:
    if not headings:
        return
    section = ""
    subsection = ""
    heading_index = 0
    for record in sorted(records, key=lambda item: item.start):
        while heading_index < len(headings) and headings[heading_index][1] <= record.start:
            level, _pos, title = headings[heading_index]
            if level == 2:
                section = title
                subsection = ""
            elif level == 3:
                subsection = title
            heading_index += 1
        record.section = section
        record.subsection = subsection


def cache_file_for_page(cache_dir: Path, page_title: str) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", page_title.replace("/", "__"))
    return cache_dir / f"{safe_name}.wiki"


def fetch_url(
    url: str,
    sleep_seconds: float = 0.1,
    retries: int = 2,
    retry_delay: float = 0.5,
    decode_errors: str = "strict",
) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(max(0, retries) + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read().decode("utf-8", errors=decode_errors)
            if sleep_seconds:
                time.sleep(sleep_seconds)
            return body
        except urllib.error.HTTPError as error:
            retryable = error.code == 408 or error.code == 425 or error.code == 429 or error.code >= 500
            if not retryable or attempt >= retries:
                raise
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt >= retries:
                raise
        if retry_delay:
            time.sleep(retry_delay * (2**attempt))
    raise RuntimeError(f"Unable to fetch URL: {url}")


def wiki_request(
    api_url: str,
    params: dict[str, object],
    sleep_seconds: float = 0.1,
    retries: int = 2,
    retry_delay: float = 0.5,
) -> dict:
    query = urllib.parse.urlencode(params)
    return json.loads(fetch_url(f"{api_url}?{query}", sleep_seconds=sleep_seconds, retries=retries, retry_delay=retry_delay))


def fetch_text(
    page_title: str,
    sleep_seconds: float = 0.1,
    cache_dir: Path | None = None,
    refresh: bool = False,
    api_url: str = DUSTLOOP_API,
) -> str:
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_file_for_page(cache_dir, page_title)
        if cache_path.exists() and not refresh:
            return cache_path.read_text(encoding="utf-8")
    data = wiki_request(
        api_url,
        {
            "action": "query",
            "prop": "revisions",
            "titles": page_title,
            "rvprop": "content",
            "rvslots": "main",
            "format": "json",
            "formatversion": "2",
        },
        sleep_seconds,
    )
    pages = data.get("query", {}).get("pages", []) or []
    if not pages or pages[0].get("missing"):
        raise RuntimeError(f"Missing wiki page: {page_title}")
    revisions = pages[0].get("revisions") or []
    raw = ((revisions[0].get("slots") or {}).get("main") or {}).get("content", "") if revisions else ""
    if cache_dir is not None:
        cache_file_for_page(cache_dir, page_title).write_text(raw, encoding="utf-8")
    return raw

def normalize_move_cache_key(value: object) -> str:
    text = str(value or "").lower().strip()
    text = text.replace("jumping", "j")
    text = re.sub(r"\b(?:jump|air)\s*\.?,?", "j.", text)
    text = text.replace("[", "hold")
    return re.sub(r"[^a-z0-9]+", "", text)


def dustloop_char_key(display_name: str) -> str:
    text = str(display_name or "").strip().lower().replace("'", "")
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def dustloop_page_url(page_title: str) -> str:
    return f"https://www.dustloop.com/w/{str(page_title).replace(' ', '_')}"


def split_mediawiki_files(value: object) -> list[str]:
    files: list[str] = []
    for item in re.split(r"[;\n]+", str(value or "")):
        clean = clean_wiki_text(item).strip()
        clean = re.sub(r"^(?:File|Image):", "", clean, flags=re.IGNORECASE).strip()
        if clean and re.search(r"\.(?:png|webp|gif|jpg|jpeg)$", clean, flags=re.IGNORECASE):
            files.append(clean)
    return files


def split_note_lines(value: object) -> list[str]:
    text = clean_wiki_text(value).strip()
    if not text:
        return []
    return [line.strip(" -;\t") for line in re.split(r"[;\\\n]+", text) if line.strip(" -;\t")]


def indexed_parameter_values(params: Mapping[str, object], prefix: str) -> list[object]:
    """Return an unbounded indexed parameter family in natural numeric order."""
    if not prefix:
        return []
    values: list[object] = []
    if prefix in params:
        values.append(params[prefix])
    indexed: list[tuple[int, object]] = []
    pattern = re.compile(rf"^{re.escape(prefix)}([1-9]\d*)$")
    for key, value in params.items():
        match = pattern.match(str(key))
        if match:
            indexed.append((int(match.group(1)), value))
    values.extend(value for _, value in sorted(indexed, key=lambda item: item[0]))
    return values




def resolve_file_urls(
    api_url: str,
    filenames: list[str],
    thumb_width: int = 300,
    sleep_seconds: float = 0.1,
    request_func: Callable[[str, dict[str, object], float], dict] | None = None,
) -> dict[str, str]:
    """Resolve MediaWiki file titles to thumbnail URLs in API-sized batches."""
    requester = request_func or wiki_request
    unique_names: list[str] = []
    seen: set[str] = set()
    for filename in filenames:
        clean_name = str(filename or "").strip().replace("_", " ")
        if clean_name and clean_name.lower() not in seen:
            seen.add(clean_name.lower())
            unique_names.append(clean_name)
    results: dict[str, str] = {}
    for index in range(0, len(unique_names), 20):
        batch = unique_names[index : index + 20]
        data = requester(
            api_url,
            {
                "action": "query",
                "titles": "|".join(f"File:{name}" for name in batch),
                "prop": "imageinfo",
                "iiprop": "url",
                "iiurlwidth": thumb_width,
                "format": "json",
            },
            sleep_seconds,
        )
        for page in (data.get("query", {}).get("pages", {}) or {}).values():
            title = str(page.get("title", ""))
            if page.get("missing") or not title.startswith("File:"):
                continue
            image_info = (page.get("imageinfo") or [{}])[0]
            url = image_info.get("thumburl") or image_info.get("url")
            if not url:
                continue
            filename = title.split(":", 1)[1]
            results[filename.lower()] = url
            results[filename.replace(" ", "_").lower()] = url
    return results


def file_url_for_name(urls: Mapping[str, str], filename: str) -> str:
    name = str(filename or "").strip()
    return urls.get(name.lower()) or urls.get(name.replace("_", " ").lower()) or urls.get(name.replace(" ", "_").lower()) or ""


def build_description_index(description_rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for row in description_rows:
        key = str(row.get("input") or row.get("name") or "").strip().lower()
        if key:
            index[key] = row
    return index


def parse_overview_page(
    char_key: str,
    display_name: str,
    page_title: str,
    raw_text: str,
) -> tuple[dict[str, str], list[dict[str, str]]]:
    description_rows = []
    for record in extract_templates(raw_text, {"ggst_move_card", "ggst move card"}):
        description = clean_wiki_text(record.params.get("description", ""))
        move_name = clean_wiki_text(record.params.get("name", ""))
        inputs = clean_wiki_text(record.params.get("input", ""))
        for move_input in (part.strip() for part in inputs.split(",")):
            if move_input:
                description_rows.append(
                    {"input": move_input, "name": move_name, "description_text": description}
                )
    return {"char_key": char_key, "char_name": display_name, "source_page_title": page_title}, description_rows


def parse_data_page(
    char_key: str,
    display_name: str,
    page_title: str,
    raw_text: str,
    description_index: dict[str, dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    moves = []
    records = extract_templates(raw_text, {"movedata-ggst", "movedata-ggacr", "movedata-bbcf"})
    apply_heading_context(records, extract_headings(raw_text))
    for record in records:
        params = {key: clean_wiki_text(value) for key, value in record.params.items()}
        if params.get("input") or params.get("name"):
            description = description_index.get((params.get("input") or "").lower())
            if description is None:
                description = description_index.get((params.get("name") or "").lower(), {})
            params.update(
                {
                    "section": record.section,
                    "subsection": record.subsection,
                    "description_text": description.get("description_text", ""),
                    "notes_text": params.get("notes", ""),
                    "caption_text": params.get("caption", ""),
                }
            )
            moves.append(params)
    return [], moves

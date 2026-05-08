from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd


API_URL = "https://wiki.play2xko.com/en-us/api.php"
USER_AGENT = "Mozilla/5.0 (compatible; Bub 2XKO bucket builder/1.0)"
IMAGE_THUMB_WIDTH = 300


MOVE_COLUMNS = [
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
]

CHAMPIONS = {
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
    "Vi",
    "Warwick",
    "Yasuo",
}


def sheet_name_for_char(char_name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "", char_name) or "Character"
    return f"{base}Normal"[:31]


def normalize_move_key(value: object) -> str:
    text = str(value or "").lower().strip()
    text = text.replace("+", "")
    text = text.replace(".", "")
    text = text.replace("[", "hold")
    text = text.replace("]", "")
    text = text.replace("(", "")
    text = text.replace(")", "")
    text = text.replace("~", "")
    return re.sub(r"[^a-z0-9]", "", text)


def wiki_request(params: dict[str, object], sleep_seconds: float) -> dict:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{API_URL}?{query}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
    if sleep_seconds:
        time.sleep(sleep_seconds)
    return data


def fetch_page_images(char_name: str, sleep_seconds: float) -> list[str]:
    data = wiki_request(
        {
            "action": "parse",
            "page": char_name,
            "prop": "images",
            "format": "json",
        },
        sleep_seconds,
    )
    return list((data.get("parse") or {}).get("images") or [])


def chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def resolve_file_urls(filenames: list[str], sleep_seconds: float) -> dict[str, str]:
    results: dict[str, str] = {}
    unique_names = []
    seen = set()
    for filename in filenames:
        clean_name = str(filename or "").strip().replace("_", " ")
        if not clean_name or clean_name.lower() in seen:
            continue
        seen.add(clean_name.lower())
        unique_names.append(clean_name)

    for batch in chunks(unique_names, 20):
        data = wiki_request(
            {
                "action": "query",
                "titles": "|".join(f"File:{name}" for name in batch),
                "prop": "imageinfo",
                "iiprop": "url",
                "iiurlwidth": IMAGE_THUMB_WIDTH,
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


def direct_thumb_url(filename: str, thumb_width: int = IMAGE_THUMB_WIDTH) -> str:
    encoded = urllib.parse.quote(str(filename or "").strip().replace(" ", "_"), safe="._()-'!")
    if not encoded:
        return ""
    return f"https://wiki.play2xko.com/en-us/images/thumb/{encoded}/{thumb_width}px-{encoded}"


def input_image_filename(char_name: str, input_text: str) -> str:
    clean_input = str(input_text or "").strip()
    if not clean_input:
        return ""
    return f"{char_name}_{clean_input}.png"


def filename_move_key(filename: str, char_name: str) -> tuple[str, bool]:
    stem = re.sub(r"\.(?:png|webp|gif|jpg|jpeg)$", "", str(filename or ""), flags=re.IGNORECASE)
    if not stem:
        return "", False
    if any(token in stem.lower() for token in ("video", "glyph", "icon", "square", "portrait", "promo", "concept", "kv")):
        return "", False
    hitbox = "hitbox" in stem.lower()
    text = stem.lower()
    char_token = re.sub(r"[^a-z0-9]+", "_", char_name.lower()).strip("_")
    text = re.sub(rf"^{re.escape(char_token)}_", "", text)
    text = re.sub(r"_?hitbox$", "", text)
    return normalize_move_key(text), hitbox


def build_bucket_media_cache(rows: list[dict[str, str]], output_path: Path, sleep_seconds: float) -> tuple[int, int]:
    image_cache: dict[str, dict[str, str]] = {}
    hitbox_cache: dict[str, dict[str, list[str]]] = {}
    filenames: list[str] = []
    pending: list[tuple[str, str, bool, str]] = []

    rows_by_char: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        rows_by_char.setdefault(row["char_name"], []).append(row)

    for char_name, char_rows in rows_by_char.items():
        row_keys = {normalize_move_key(row.get("numCmd")): row for row in char_rows if normalize_move_key(row.get("numCmd"))}
        try:
            page_images = fetch_page_images(char_name, sleep_seconds)
        except Exception as exc:
            print(f"[2xko-bucket-images] skipped {char_name}: {exc}", flush=True)
            continue
        for filename in page_images:
            move_key, hitbox = filename_move_key(filename, char_name)
            if not move_key or move_key not in row_keys:
                continue
            row = row_keys[move_key]
            pending.append((row["char_key"], normalize_move_key(row["numCmd"]), hitbox, filename))
            filenames.append(filename)

    urls = resolve_file_urls(filenames, sleep_seconds)
    for char_key, move_key, hitbox, filename in pending:
        url = urls.get(filename.lower()) or urls.get(filename.replace(" ", "_").lower())
        if not url:
            continue
        if hitbox:
            hitbox_cache.setdefault(char_key, {}).setdefault(move_key, [])
            if url not in hitbox_cache[char_key][move_key]:
                hitbox_cache[char_key][move_key].append(url)
        else:
            image_cache.setdefault(char_key, {})[move_key] = url

    output_path.write_text(
        "# Generated by build_tuco_from_bucket_dump.py. Do not edit by hand.\n"
        f"TUCO_MOVE_IMAGE_URLS = {json.dumps(image_cache, indent=2, sort_keys=True)}\n\n"
        f"TUCO_HITBOX_DATA = {json.dumps(hitbox_cache, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
    return sum(len(moves) for moves in image_cache.values()), sum(len(links) for moves in hitbox_cache.values() for links in moves.values())


def build_deterministic_image_cache(rows: list[dict[str, str]], output_path: Path) -> tuple[int, int]:
    image_cache: dict[str, dict[str, str]] = {}
    for row in rows:
        filename = input_image_filename(row.get("char_name", ""), row.get("numCmd", ""))
        url = direct_thumb_url(filename)
        if not url:
            continue
        image_cache.setdefault(row["char_key"], {})[normalize_move_key(row["numCmd"])] = url
    output_path.write_text(
        "# Generated by build_tuco_from_bucket_dump.py. Do not edit by hand.\n"
        f"TUCO_MOVE_IMAGE_URLS = {json.dumps(image_cache, indent=2, sort_keys=True)}\n\n"
        "TUCO_HITBOX_DATA = {}\n",
        encoding="utf-8",
    )
    return sum(len(moves) for moves in image_cache.values()), 0


def build_rows(bucket_rows: list[dict[str, object]]) -> list[dict[str, str]]:
    rows = []
    for item in bucket_rows:
        char_name = str(item.get("page_name", "")).strip()
        input_text = str(item.get("input", "")).strip()
        if not char_name or char_name not in CHAMPIONS or not input_text:
            continue
        rows.append(
            {
                "char_key": char_name.lower(),
                "char_name": char_name,
                "section": "",
                "subsection": "",
                "moveName": input_text,
                "numCmd": input_text,
                "dmg": str(item.get("damage", "") or ""),
                "guardLevel": str(item.get("guard", "") or ""),
                "startup": str(item.get("startup", "") or ""),
                "active": str(item.get("active", "") or ""),
                "recovery": str(item.get("recovery", "") or ""),
                "onBlock": str(item.get("onblock", "") or ""),
                "onHit": str(item.get("onhit", "") or ""),
                "meterGain": str(item.get("metergain", "") or ""),
                "xx": str(item.get("cancel", "") or ""),
                "invuln": str(item.get("invuln", "") or ""),
                "extraInfo": "",
            }
        )
    return rows


def build_workbook(input_path: Path, output_path: Path) -> tuple[list[dict[str, str]], int]:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    rows = build_rows(payload.get("bucket", []) or [])
    if not rows:
        raise RuntimeError(f"No bucket rows found in {input_path}")
    with pd.ExcelWriter(output_path, engine="odf") as writer:
        pd.DataFrame(rows, columns=MOVE_COLUMNS).to_excel(writer, sheet_name="Moves", index=False)
        for char_name in sorted({row["char_name"] for row in rows}):
            char_rows = [row for row in rows if row["char_name"] == char_name]
            pd.DataFrame(char_rows, columns=MOVE_COLUMNS).to_excel(
                writer,
                sheet_name=sheet_name_for_char(char_name),
                index=False,
            )
    return rows, len({row["char_key"] for row in rows})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build baseline 2XKO ODS data from a saved Bucket API JSON dump.")
    parser.add_argument("input_json")
    parser.add_argument("--output", default="2XKO Frame Data.ods")
    parser.add_argument("--output-cache", default="bubbot/data/tuco_move_images.py")
    parser.add_argument("--build-image-cache", action="store_true", help="Infer image/hitbox cache from page image lists and Bucket inputs.")
    parser.add_argument("--deterministic-image-cache", action="store_true", help="Build direct input-based image URLs without verifying page image lists.")
    parser.add_argument("--sleep", type=float, default=0.1)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows, chars = build_workbook(Path(args.input_json), Path(args.output))
    print(f"Wrote {args.output}: {len(rows)} rows, {chars} characters")
    if args.build_image_cache:
        image_count, hitbox_count = build_bucket_media_cache(rows, Path(args.output_cache), args.sleep)
        if image_count == 0 and args.deterministic_image_cache:
            print("No verified image URLs found; falling back to deterministic input-based image URLs")
            image_count, hitbox_count = build_deterministic_image_cache(rows, Path(args.output_cache))
        print(f"Wrote {args.output_cache}: {image_count} images, {hitbox_count} hitboxes")
    elif args.deterministic_image_cache:
        image_count, hitbox_count = build_deterministic_image_cache(rows, Path(args.output_cache))
        print(f"Wrote {args.output_cache}: {image_count} images, {hitbox_count} hitboxes")


if __name__ == "__main__":
    main()

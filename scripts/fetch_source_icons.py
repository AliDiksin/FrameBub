#!/usr/bin/env python3
"""Downloads and bundles embed footer source icons.
Writes PNG assets under bubbot/assets/source_icons/.
Does not overwrite dustloop.png (user-provided favicon in repo).
"""

from __future__ import annotations

import re
import urllib.request
from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parents[1] / "bubbot" / "assets" / "source_icons"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
PROTECTED = {"dustloop.png"}


def save(url: str, name: str) -> tuple[bool, str]:
    if name in PROTECTED and (OUT / name).exists():
        return False, "protected"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    data = urllib.request.urlopen(req, timeout=25).read()
    if data[:5].lower().startswith(b"<!doc") or data[:5].lower().startswith(b"<html"):
        return False, "html"
    path = OUT / name
    path.write_bytes(data)
    return True, f"{len(data)} bytes {data[:8]!r}"


def save_png_thumbnail(url: str, name: str, size: int = 96) -> tuple[bool, str]:
    if name in PROTECTED and (OUT / name).exists():
        return False, "protected"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    data = urllib.request.urlopen(req, timeout=25).read()
    if data[:5].lower().startswith(b"<!doc") or data[:5].lower().startswith(b"<html"):
        return False, "html"
    img = Image.open(__import__("io").BytesIO(data)).convert("RGBA")
    img.thumbnail((size, size), Image.Resampling.LANCZOS)
    path = OUT / name
    img.save(path, "PNG", optimize=True)
    return True, f"{img.size} {path.stat().st_size} bytes"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    targets = [
        ("https://supercombo.gg/favicon.ico", "supercombo.png", save),
        (
            "https://kombat-akademy-angular.vercel.app/assets/images/site/avatar.png",
            "kombat_akademy.png",
            save_png_thumbnail,
        ),
    ]
    for url, name, writer in targets:
        try:
            ok, detail = writer(url, name)
            print(f"{name}: {'OK' if ok else 'SKIP'} {detail}")
        except Exception as exc:
            print(f"{name}: FAIL {exc}")

    req = urllib.request.Request("https://www.dreamcancel.com/", headers={"User-Agent": UA})
    html = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "replace")
    icons = re.findall(
        r'<link[^>]+rel=["\'][^"\']*icon[^"\']*["\'][^>]+href=["\']([^"\']+)["\']',
        html,
        re.I,
    )
    icons += re.findall(
        r'href=["\']([^"\']+)["\'][^>]+rel=["\'][^"\']*icon',
        html,
        re.I,
    )
    for href in icons:
        url = href if href.startswith("http") else f"https://www.dreamcancel.com{href if href.startswith('/') else '/' + href}"
        try:
            ok, detail = save(url, "dreamcancel.png")
            if ok:
                print(f"dreamcancel.png: OK from {url} {detail}")
                break
        except Exception as exc:
            print(f"dreamcancel fail {url}: {exc}")

    for url in (
        "https://www.play2xko.com/favicon.ico",
        "https://play2xko.com/favicon.ico",
    ):
        try:
            ok, detail = save(url, "2xko.png")
            print(f"2xko.png from {url}: {'OK' if ok else 'SKIP'} {detail}")
            if ok:
                break
        except Exception as exc:
            print(f"2xko fail {url}: {exc}")

    if (OUT / "dustloop.png").exists():
        print("dustloop.png: kept bundled user favicon")
    else:
        print("dustloop.png: MISSING — add user-provided favicon manually")


if __name__ == "__main__":
    main()

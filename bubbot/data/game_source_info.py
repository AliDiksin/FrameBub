"""Attribution metadata for frame-data and combo sources (name, URL, icon)."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

_ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"


@dataclass(frozen=True)
class GameSourceInfo:
    name: str
    url: str = ""
    icon_url: str = ""


BUNDLED_SOURCE_ICONS: dict[str, str] = {
    "fat": "source_icons/fat.png",
    "supercombo": "source_icons/supercombo.png",
    "dustloop": "source_icons/dustloop.png",
    "2xko": "source_icons/2xko.png",
    "dreamcancel": "source_icons/dreamcancel.png",
    "kombat_akademy": "source_icons/kombat_akademy.png",
}

SOURCE_CATALOG: dict[str, GameSourceInfo] = {
    "fat": GameSourceInfo(
        name="FAT",
        url="https://fullmeter.com/fat/",
        icon_url="",
    ),
    "supercombo": GameSourceInfo(
        name="SuperCombo Wiki",
        url="https://wiki.supercombo.gg",
        icon_url="https://wiki.supercombo.gg/favicon.ico",
    ),
    "dustloop": GameSourceInfo(
        name="Dustloop",
        url="https://www.dustloop.com",
        icon_url="https://www.dustloop.com/favicon.ico",
    ),
    "2xko": GameSourceInfo(
        name="2XKO Wiki",
        url="https://wiki.play2xko.com/en-us/",
        icon_url="https://wiki.play2xko.com/favicon.ico",
    ),
    "dreamcancel": GameSourceInfo(
        name="DreamCancel",
        url="https://www.dreamcancel.com",
        icon_url="https://www.dreamcancel.com/favicon.ico",
    ),
    "kombat_akademy": GameSourceInfo(
        name="Kombat Akademy",
        url="https://kombat-akademy-angular.vercel.app/",
        icon_url="https://kombat-akademy-angular.vercel.app/favicon.ico",
    ),
}

FRAME_DATA_SOURCE_KEYS: dict[str, str] = {
    "sf6": "fat",
    "sfv": "fat",
    "ggst": "dustloop",
    "ggacr": "dustloop",
    "tuco": "2xko",
    "mk1": "kombat_akademy",
    "cotw": "dreamcancel",
    "bbcf": "dustloop",
    "third_strike": "supercombo",
}

COMBO_SOURCE_KEYS: dict[str, str] = {
    "sf6": "supercombo",
    "mk1": "kombat_akademy",
}


def get_frame_source_info(game: str) -> GameSourceInfo:
    key = FRAME_DATA_SOURCE_KEYS.get(str(game or "").strip().lower(), "fat")
    return SOURCE_CATALOG[key]


def get_combo_source_info(game: str) -> GameSourceInfo:
    key = COMBO_SOURCE_KEYS.get(str(game or "").strip().lower(), "fat")
    return SOURCE_CATALOG[key]


def _public_asset_base_url() -> str:
    explicit = str(os.getenv("BUB_PUBLIC_BASE_URL", "") or "").strip().rstrip("/")
    if explicit:
        return explicit
    host = str(os.getenv("BUB_PUBLIC_HOST", "143.110.170.232") or "").strip()
    port = str(os.getenv("BUB_HTTP_PORT", "8080") or "8080").strip()
    if not host:
        return ""
    return f"http://{host}:{port}"


def source_key_for_game(game: str, *, kind: str = "frame") -> str:
    game_key = str(game or "").strip().lower()
    if kind == "combo":
        return COMBO_SOURCE_KEYS.get(game_key, FRAME_DATA_SOURCE_KEYS.get(game_key, "fat"))
    return FRAME_DATA_SOURCE_KEYS.get(game_key, "fat")


def bundled_icon_path(source_key: str) -> Path | None:
    relative = BUNDLED_SOURCE_ICONS.get(str(source_key or "").strip().lower())
    if not relative:
        return None
    path = _ASSETS_DIR / relative
    return path if path.is_file() else None


def source_icon_attachment_name(source_key: str) -> str:
    return f"bub_src_{str(source_key or '').strip().lower()}.png"


def _icon_cache_token(relative: str) -> str:
    path = _ASSETS_DIR / relative
    if not path.is_file():
        return "0"
    digest = hashlib.md5(path.read_bytes()).hexdigest()
    return digest[:12]


def resolve_source_icon_url(source_key: str) -> str:
    key = str(source_key or "").strip().lower()
    relative = BUNDLED_SOURCE_ICONS.get(key)
    if relative:
        base = _public_asset_base_url()
        if base:
            token = _icon_cache_token(relative)
            return f"{base}/assets/{relative}?v={token}"
    return SOURCE_CATALOG.get(key, GameSourceInfo(name="")).icon_url or ""


def resolve_icon_for_game(game: str, *, kind: str = "frame") -> str:
    return resolve_source_icon_url(source_key_for_game(game, kind=kind))


def resolve_attachment_icon_url(game: str, *, kind: str = "frame") -> str:
    source_key = source_key_for_game(game, kind=kind)
    if bundled_icon_path(source_key):
        return f"attachment://{source_icon_attachment_name(source_key)}"
    return resolve_source_icon_url(source_key)

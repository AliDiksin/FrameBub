"""Optional local HTTP server for bundled embed assets (source icons, etc.).
Serves bubbot/assets over aiohttp when BUB_DISABLE_STATIC_ASSETS is unset.
public_base_url() builds the URL embed footers use for source attribution."""

from __future__ import annotations

import os
from pathlib import Path

_ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"
_runner = None


def assets_directory() -> Path:
    return _ASSETS_DIR


def public_base_url() -> str:
    explicit = str(os.getenv("BUB_PUBLIC_BASE_URL", "") or "").strip().rstrip("/")
    if explicit:
        return explicit
    host = str(os.getenv("BUB_PUBLIC_HOST", "143.110.170.232") or "").strip()
    port = str(os.getenv("BUB_HTTP_PORT", "8080") or "8080").strip()
    if not host:
        return ""
    return f"http://{host}:{port}"


async def start_static_asset_server() -> None:
    global _runner
    if _runner is not None:
        return
    if str(os.getenv("BUB_DISABLE_STATIC_ASSETS", "") or "").strip().lower() in {"1", "true", "yes"}:
        return
    if not _ASSETS_DIR.is_dir():
        return

    from aiohttp import web

    app = web.Application()
    app.router.add_static("/assets/", _ASSETS_DIR, show_index=False)
    _runner = web.AppRunner(app)
    await _runner.setup()
    port = int(str(os.getenv("BUB_HTTP_PORT", "8080") or "8080"))
    site = web.TCPSite(_runner, "0.0.0.0", port)
    await site.start()
    print(f"[static-assets] serving {_ASSETS_DIR} at {public_base_url()}/assets/", flush=True)

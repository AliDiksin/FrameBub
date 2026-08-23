"""Runtime constants: paths, Discord copy strings, and local hitbox GIF settings.
Env-backed values like TOKEN live here; game data workbooks are loaded elsewhere."""

import os


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TOKEN = os.getenv("DISCORD_TOKEN")

FRAME_DATA_ERROR_CONTACT_TEXT = (
    "If you think this is an error, use **Report Issue** on this message or contact yimbo3560 on Discord."
)
MISSING_HITBOX_GIF_TEXT = (
    "I have frame data for that move but no hitbox gif link yet. "
    f"{FRAME_DATA_ERROR_CONTACT_TEXT}"
)
MISSING_SCROLLS_TEXT = (
    "I don't have the scrolls for that move. "
    "Please try slash commands or the menu until it gets fixed. "
    f"{FRAME_DATA_ERROR_CONTACT_TEXT}"
)
PUBLIC_INVALID_QUERY_TEXT = MISSING_SCROLLS_TEXT
RANGE_SCROLLS_MISSING_TEXT = "the range of that move is not on the supercombo scrolls"
RANGE_MISSING_PLACEHOLDERS = {"{{{atkrange}}}"}

LOCAL_HITBOX_GIF_ROOT = os.path.join(BASE_DIR, "sf6frames", "files")
LOCAL_HITBOX_GIF_EXTENSIONS = {".webp", ".gif", ".png", ".jpg", ".jpeg"}

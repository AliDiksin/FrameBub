import os


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TOKEN = os.getenv("DISCORD_TOKEN")

SCROLLS_MAINTAINER_USER_ID = 427263312217243668
SCROLLS_FIX_REQUEST_TEXT = "please fix this or add this to my scrolls"
RANGE_SCROLLS_MISSING_TEXT = "the range of that move is not on the supercombo scrolls"
RANGE_MISSING_PLACEHOLDERS = {"{{{atkrange}}}"}

LOCAL_HITBOX_GIF_ROOT = os.path.join(BASE_DIR, "sf6frames", "files")
LOCAL_HITBOX_GIF_EXTENSIONS = {".webp", ".gif", ".png", ".jpg", ".jpeg"}

# Public builds do not include private prose generation. The value stays as a
# harmless placeholder for optional Buenavista follow-up context.

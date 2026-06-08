"""Guilty Gear Accent Core Plus R alias maps.

Reuses GGST character and move alias tables until +R-specific entries are needed.
GGST-only roster entries (Strive exclusives) are filtered out at runtime once frame data loads.
"""

import re

from bubbot.data.ggst_aliases import (
    GGST_CHARACTER_ALIASES,
    GGST_CHARACTER_MOVE_ALIASES,
    GGST_LOOKUP_WORDS,
    GGST_MOVE_ALIASES,
)

# Character aliases are rebuilt from the +R roster at load time; move aliases reuse Strive tables.
GGACR_CHARACTER_ALIASES = {}
GGACR_MOVE_ALIASES = dict(GGST_MOVE_ALIASES)
GGACR_CHARACTER_MOVE_ALIASES = dict(GGST_CHARACTER_MOVE_ALIASES)
GGACR_LOOKUP_WORDS = set(GGST_LOOKUP_WORDS)

# NL / menu game-tag detection (shared across parser, router, menu, quiz).
_GGACR_GAME_TAG_PARTS = (
    r"ggacr",
    r"ggacpr",
    r"\bacpr\b",
    r"gg\s*acpr",
    r"guilty\s+gear\s*acpr",
    r"accent\s+core(?:\s+plus\s+r|\s*\+?\s*r)?",
    r"guilty\s+gear\s*accent\s+core(?:\s+plus\s+r)?",
    r"guilty\s+gear\s*plus\s*r",
    r"guilty\s+gear\s*\+?\s*r",
    r"gg\s*accent\s+core(?:\s+plus\s+r)?",
    r"gg\s*plus\s*r",
    r"gg\s*\+?\s*r",
    r"\bplus\s*r\b",
    r"(?:^|\s)\+r(?:\s|$)",
)
GGACR_GAME_TAG_RE = re.compile(r"(?:{})".format("|".join(_GGACR_GAME_TAG_PARTS)), re.IGNORECASE)

_GGACR_GAME_ONLY_PARTS = (
    r"ggacr",
    r"ggacpr",
    r"acpr",
    r"\+r",
    r"plus\s*r",
    r"accent\s+core(?:\s+plus\s+r)?",
    r"guilty\s+gear(?:\s*accent\s+core(?:\s+plus\s+r)?|\s*plus\s*r|\s*\+?\s*r|\s*acpr)?",
    r"gg(?:\s*accent\s+core(?:\s+plus\s+r)?|\s*plus\s*r|\s*\+?\s*r|\s*acpr)?",
)
GGACR_GAME_ONLY_RE = re.compile(r"^(?:{})$".format("|".join(_GGACR_GAME_ONLY_PARTS)), re.IGNORECASE)

GGACR_GAME_TERMS = (
    "ggacr",
    "gg +r",
    "+r",
    "plus r",
    "accent core",
    "accent core plus r",
    "guilty gear +r",
    "guilty gear plus r",
    "guilty gear accent core",
    "acpr",
    "ggacpr",
)


def query_has_ggacr_game_tag(text):
    return bool(GGACR_GAME_TAG_RE.search(str(text or "")))


def match_ggacr_game_only(text):
    normalized = re.sub(r"\s+", " ", str(text or "").strip())
    if not normalized:
        return False
    return bool(GGACR_GAME_ONLY_RE.fullmatch(normalized))


def strip_ggacr_game_tags(text):
    return GGACR_GAME_TAG_RE.sub(" ", str(text or ""))


GGACR_ONLY_CHARACTER_ALIASES = {
    "justice": "justice",
    "kliff": "kliff_undersn",
    "kliff undersn": "kliff_undersn",
    "order sol": "order_sol",
    "order-sol": "order_sol",
    "ordersol": "order_sol",
    "robo ky": "robo_ky",
    "robo-ky": "robo_ky",
    "roboky": "robo_ky",
    "eddie": "eddie",
    "venom": "venom",
    "zappa": "zappa",
}

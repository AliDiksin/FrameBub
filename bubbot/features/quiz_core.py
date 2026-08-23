"""Cross-game frame-data quiz configuration, selection, and prompt construction.

Session state, answer matching, UI controls, and leaderboard persistence stay
in their dedicated sibling modules.
"""

import asyncio
import datetime
import difflib
import json
import os
import random
import re

import discord


# Persona hooks (default stubs; buenavista may override)
def sanitize_ascii_line(text):
    return re.sub(r"[^\x00-\x7F]+", "", str(text or "")).strip()


async def build_quiz_persona_intro(channel, round_num, total_rounds, mode, sanitize_ascii_func, has_hint_func):
    mode_key = str(mode or "hard").strip().lower()
    return f"Quiz question {round_num} ({mode_key}). Guess the character and move from the data."


async def build_quiz_wrong_guess_message(channel, sanitize_ascii_func, has_hint_func):
    return "Incorrect."


async def build_quiz_correct_guess_message(channel, sanitize_ascii_func):
    return "Correct."


async def build_quiz_decline_message(channel, sanitize_ascii_func):
    return "Quiz ended."


async def build_quiz_cheating_warning_message(channel, sanitize_ascii_func, has_hint_func):
    return "No framedata or gif lookups during the quiz. Answer directly."




# Runtime injection from message_router / bot startup
FRAME_DATA = {}
CHARACTER_ALIASES = {}
GAME_QUIZ_CONFIGS = {}
resolve_character_key = None
normalize_char_name = None
lookup_frame_data = None
find_moves_in_text = None
is_missing_attack_range_value = None
clean_embed_value = None
truncate_embed_value = None
build_frame_embed = None
strip_discord_mentions = None


def configure(**deps):
    global QUIZ_CHARACTER_TERMS_CACHE, QUIZ_MOVE_NAME_TERMS_CACHE, QUIZ_CHARACTER_CENSOR_PATTERNS_CACHE
    globals().update(deps)
    QUIZ_CHARACTER_TERMS_CACHE = {}
    QUIZ_MOVE_NAME_TERMS_CACHE = {}
    QUIZ_CHARACTER_CENSOR_PATTERNS_CACHE = {}
    _ensure_quiz_game_configs()


# Module state, regex intent patterns, caches
ACTIVE_QUIZZES = {}
QUIZ_PENDING_MODE = {}
QUIZ_ACTIVE_TIMEOUT_TASKS = {}
QUIZ_LEADERBOARD_FILE = os.getenv("QUIZ_LEADERBOARD_FILE", "quiz_leaderboard.json")
QUIZ_LEADERBOARD_GUILD_ID = int(os.getenv("QUIZ_LEADERBOARD_GUILD_ID", "1345474576439836802"))
QUIZ_GLOBAL_LEADERBOARD = {}
QUIZ_GLOBAL_LEADERBOARD_NAMES = {}
QUIZ_LEADERBOARD_LOCK = asyncio.Lock()
QUIZ_INTENT_RE = re.compile(
    r"\bquiz\b|\bquizz|\bguess.*\bframe|\bframe.*\bguess|\btest\s+me\b",
    re.IGNORECASE,
)
QUIZ_LEADERBOARD_REQUEST_RE = re.compile(
    r"\b(quiz\s+leaderboard|leaderboard\s+for\s+quiz|show\s+(?:the\s+)?(?:quiz\s+)?leaderboard|who\s+tops\s+(?:the\s+)?(?:quiz\s+)?leaderboard)\b",
    re.IGNORECASE,
)
QUIZ_LEADERBOARD_TOP_RE = re.compile(r"\btop\s+(\d{1,2})\b", re.IGNORECASE)
QUIZ_GUESS_AGAIN_RE = re.compile(
    r"\b(guess\s+again|again|continue|keep\s+guessing|try\s+again)\b",
    re.IGNORECASE,
)
QUIZ_REVEAL_END_RE = re.compile(
    r"\b(answer|reveal|show|tell|what'?s\s+the\s+answer|whats\s+the\s+answer|give\s+up|forfeit|forefeit|forfiet|surrender|concede|you\s+win|i\s+lose|end|stop|quit|cancel)\b",
    re.IGNORECASE,
)
QUIZ_FORFEIT_RE = re.compile(
    r"\b(give\s+up|forfeit|forefeit|forfiet|surrender|concede|you\s+win|i\s+lose)\b",
    re.IGNORECASE,
)
QUIZ_CHEAT_LOOKUP_RE = re.compile(
    r"\b(framedata|frame\s*data|gif|gifs|hit\s*box(?:es)?|hitbox(?:es)?)\b",
    re.IGNORECASE,
)
QUIZ_MODE_RE = re.compile(r"\b(easy|medium|hard)\b", re.IGNORECASE)
QUIZ_ACTIVE_TTL_SECONDS = 300
QUIZ_PENDING_MODE_TTL_SECONDS = 600
QUIZ_INTRO_BUTTON_RE = re.compile(
    r"\b(?:st|cr|j)\s*(?:lp|mp|hp|lk|mk|hk)\b|\b(?:standing|crouching|jumping)\s+(?:light|medium|heavy)\s+(?:punch|kick)\b|\b(?:[1-9]\d{0,2}(?:lp|mp|hp|lk|mk|hk))\b|\b(?:236|214|623|421|41236|63214|22|66|44)\b|\b(?:sa1|sa2|sa3|ca|level\s*[123])\b",
    re.IGNORECASE,
)
QUIZ_INTRO_DATA_TERM_RE = re.compile(
    r"\b(startup|active|recovery|on\s+hit|on\s+block|damage|range|guard|cancel|total|block\s+advantage|frame\s+advantage)\b",
    re.IGNORECASE,
)
QUIZ_CHARACTER_TERMS_CACHE = {}
QUIZ_MOVE_NAME_TERMS_CACHE = {}
QUIZ_CHARACTER_CENSOR_PATTERNS_CACHE = None
QUIZ_VALID_MODES = {"easy", "medium", "hard"}
QUIZ_START_LOCK = asyncio.Lock()


# Cross-game config and row helpers
def _ensure_quiz_game_configs():
    configs = globals().get("GAME_QUIZ_CONFIGS")
    if not isinstance(configs, dict):
        configs = {}
    sf6_config = {
        "label": "Street Fighter 6",
        "data": FRAME_DATA,
        "aliases": CHARACTER_ALIASES,
        "resolve_character_key": resolve_character_key,
        "lookup_frame_data": lookup_frame_data,
        "find_moves_in_text": find_moves_in_text,
        "build_frame_embed": build_frame_embed,
        "game_terms": ("sf6", "street fighter 6"),
    }
    merged = {"sf6": sf6_config}
    merged.update(configs)
    merged["sf6"] = {**sf6_config, **dict(merged.get("sf6") or {})}
    globals()["GAME_QUIZ_CONFIGS"] = merged
    return merged


def _quiz_game_key(game=None):
    key = str(game or "sf6").strip().lower().replace("-", "_")
    aliases = {
        "2xko": "tuco",
        "gg": "ggst",
        "guilty_gear": "ggst",
        "ggacr": "ggacr",
        "ggacpr": "ggacr",
        "acpr": "ggacr",
        "plus_r": "ggacr",
        "accent_core": "ggacr",
        "accent_core_plus_r": "ggacr",
        "sfv": "sfv",
        "sf5": "sfv",
        "street_fighter_v": "sfv",
        "street_fighter_5": "sfv",
        "3s": "third_strike",
        "thirdstrike": "third_strike",
        "third_strike": "third_strike",
        "sf3": "third_strike",
        "mk": "mk1",
        "mortal_kombat": "mk1",
        "mortal_kombat_1": "mk1",
    }
    return aliases.get(key, key if key else "sf6")


def _quiz_game_config(game=None):
    configs = _ensure_quiz_game_configs()
    key = _quiz_game_key(game)
    return configs.get(key) or configs.get("sf6") or {}


def _quiz_game_label(game=None):
    return str(_quiz_game_config(game).get("label") or _quiz_game_key(game).upper())


def _quiz_game_data(game=None):
    data = _quiz_game_config(game).get("data") or {}
    return data if isinstance(data, dict) else {}


def _quiz_game_resolve_character(game, text):
    resolver = _quiz_game_config(game).get("resolve_character_key")
    if callable(resolver):
        return resolver(text)
    aliases = _quiz_game_config(game).get("aliases") or {}
    normalized = _normalize_quiz_words(text)
    if normalized in aliases:
        return aliases[normalized]
    compact = _normalize_quiz_name(text)
    for key in _quiz_game_data(game).keys():
        if compact == _normalize_quiz_name(key):
            return key
    return None


def _quiz_extract_game_from_text(text, default="sf6"):
    from bubbot.data.ggacr_aliases import query_has_ggacr_game_tag

    lowered = str(text or "").lower()
    if query_has_ggacr_game_tag(lowered):
        return "ggacr"
    game_patterns = [
        ("third_strike", r"\b(?:3s|third\s*strike|street\s*fighter\s*(?:3|iii)|sf3|sfiii)\b"),
        ("sfv", r"\b(?:sfv|sf5|street\s*fighter\s*(?:v|5))\b"),
        ("mk1", r"\b(?:mk1|mortal\s*kombat\s*(?:1|one)?|kombat)\b"),
        ("tuco", r"\b(?:2xko|tuco)\b"),
        ("bbcf", r"\b(?:bbcf|blazblue|central\s*fiction)\b"),
        ("cotw", r"\b(?:cotw|city\s+of\s+the\s+wolves|fatal\s+fury)\b"),
        ("ggst", r"\b(?:ggst|guilty\s+gear(?!\s*(?:\+?\s*r|accent\s+core|plus\s*r|acpr))|strive)\b"),
        ("sf6", r"\b(?:sf6|street\s*fighter\s*6)\b"),
    ]
    for game, pattern in game_patterns:
        if re.search(pattern, lowered):
            return game
    return _quiz_game_key(default)


def _quiz_parser_query(game, char_key, move_text):
    terms = _quiz_game_config(game).get("game_terms") or (_quiz_game_key(game),)
    game_term = str(terms[0] if terms else _quiz_game_key(game)).strip()
    return f"{game_term} {char_key} {move_text}".strip().lower()


def _quiz_rows_for_char(game, char_key):
    return list((_quiz_game_data(game).get(char_key) or []))


def _quiz_row_identity(row):
    return (
        str((row or {}).get("numCmd", "")).strip().lower(),
        _normalize_quiz_name((row or {}).get("moveName", "")),
        _normalize_quiz_name((row or {}).get("version", "")),
        _normalize_quiz_name((row or {}).get("state_label", "")),
    )


def _quiz_rows_match(row, correct_row, correct_numcmd, allow_generic=False):
    if _quiz_row_numcmd_matches_correct(row, correct_numcmd, allow_generic=allow_generic):
        return True
    return _quiz_row_identity(row) == _quiz_row_identity(correct_row)


def _quiz_row_has_data(row):
    """Return True if a frame data row has enough real values to make a useful question."""
    numcmd = str(row.get("numCmd", "")).strip()
    if not numcmd or numcmd.lower() in ("-", "nan", ""):
        return False
    for field in ("startup", "dmg"):
        val = str(row.get(field, "")).strip()
        if val and val.lower() not in ("-", "nan", "") and re.search(r"\d", val):
            return True
    return False


def _quiz_normalize_mode(mode, default="hard"):
    mode_text = str(mode or "").strip().lower()
    if mode_text in QUIZ_VALID_MODES:
        return mode_text
    return default


def _quiz_extract_mode_from_text(text):
    match = QUIZ_MODE_RE.search(str(text or "").lower())
    if not match:
        return None
    return match.group(1).lower()


def _quiz_row_is_shared_mechanic(row, game="sf6"):
    move_type = str(row.get("moveType", "")).strip().lower()
    if move_type in {"system", "drive", "throw", "throws", "taunt", "taunts", "universal", "dodge"}:
        return True

    combined = " ".join(
        str(row.get(key, "")).lower().strip()
        for key in ("moveName", "cmnName", "numCmd", "plnCmd", "version")
    )
    return any(
        re.search(pattern, combined)
        for pattern in (
            r"\bdrive impact\b",
            r"\bdrive reversal\b",
            r"\bdrive rush\b",
            r"\bdrive parry\b",
            r"\b(?:forward|back)?\s*throw\b",
            r"\btaunt\b",
            r"\buniversal\s+overheads?\b",
        )
    )


def _quiz_row_is_jump_normal(row):
    move_type = str(row.get("moveType", "")).strip().lower()
    move_name = str(row.get("moveName", "")).lower().strip()
    cmn_name = str(row.get("cmnName", "")).lower().strip()
    num_cmd = str(row.get("numCmd", "")).lower().strip()
    pln_cmd = str(row.get("plnCmd", "")).lower().strip()
    is_jump = (
        move_type == "jumping normals"
        or move_name.startswith("jump ")
        or move_name.startswith("jumping ")
        or cmn_name.startswith("jump ")
        or cmn_name.startswith("jumping ")
        or num_cmd.startswith(("7", "8", "9", "j"))
        or pln_cmd.startswith(("u+", "ub+", "uf+", "j"))
    )
    if not is_jump:
        return False
    if "special" in move_type or "super" in move_type:
        return False
    return (
        "normal" in move_type
        or move_type in {"", "misc"}
        or bool(re.fullmatch(r"(?:j\.?|hop\s+)?[a-z0-9. ]{0,8}(?:[lmhpkabcd]|lp|mp|hp|lk|mk|hk)", num_cmd))
    )


def _quiz_move_type_category(row):
    move_type = str(row.get("moveType", "")).strip().lower()
    move_name = str(row.get("moveName", "")).strip().lower()
    num_cmd = str(row.get("numCmd", "")).strip().lower()
    combined = f"{move_type} {move_name}"
    if not move_type:
        if re.fullmatch(r"(?:[1-9]|j\.?)[lmh](?:\s+.*)?", num_cmd):
            return "normal"
        if "s" in num_cmd or re.search(r"(?:236|214|623|22|66|44|41236|63214)", num_cmd):
            return "special"
    if "normal" in combined or move_type in {"command", "command normal", "command normals", "target combos"}:
        return "normal"
    if "special" in combined or move_type in {"command-grab", "movement-special", "drive"}:
        return "special"
    if "super" in combined or "astral" in combined or "overdrive" in combined or "exceed accel" in combined:
        return "super"
    return move_type or "other"


def _quiz_row_allowed_for_mode(row, mode, game="sf6"):
    mode_key = _quiz_normalize_mode(mode)
    category = _quiz_move_type_category(row)

    if _quiz_row_is_shared_mechanic(row, game=game):
        return False

    if _quiz_row_is_jump_normal(row):
        return False

    if mode_key == "easy":
        return category == "normal"

    if mode_key == "medium":
        return category in {"normal", "special"}

    if mode_key == "hard":
        return category in {"normal", "special", "super", "other", "misc"}
    return True


def _safe_first_int(text):
    """Parse the first integer from a frame data value string like '5', '3+5', '2(2)2'."""
    m = re.search(r"\d+", str(text or ""))
    return int(m.group()) if m else None


def _compute_total_frames(row):
    """Try to compute total frames = startup + active + recovery (first integers only)."""
    s = _safe_first_int(row.get("startup", ""))
    a = _safe_first_int(row.get("active", ""))
    r = _safe_first_int(row.get("recovery", ""))
    if s is not None and a is not None and r is not None:
        return s + a + r
    return None


def _fmt_quiz_field(row, key):
    """Return a display-ready string for a row field, or '-' if empty/missing."""
    val = str(row.get(key, "")).strip()
    if not val or val.lower() in ("nan", ""):
        return "-"
    return val


def build_quiz_question_text(round_num, total_rounds, row, mode="hard"):
    """Build the quiz question message from a frame data row, hiding character and move name."""
    mode_key = _quiz_normalize_mode(mode)
    mode_label = mode_key.capitalize()
    startup   = _fmt_quiz_field(row, "startup")
    active    = _fmt_quiz_field(row, "active")
    recovery  = _fmt_quiz_field(row, "recovery")
    total     = _compute_total_frames(row)
    on_hit    = _fmt_quiz_field(row, "onHit")
    on_block  = _fmt_quiz_field(row, "onBlock")
    damage    = _fmt_quiz_field(row, "dmg")
    guard     = _fmt_quiz_field(row, "atkLvl")
    cancel    = clean_embed_value(row.get("xx", ""), default="-", strip_brackets=True) or "-"
    atk_range = _fmt_quiz_field(row, "atkRange")
    # Use existing is_missing_attack_range_value to suppress placeholder text
    if is_missing_attack_range_value(atk_range):
        atk_range = "-"

    timing_parts = [
        f"Startup: **{startup}**",
        f"Active: **{active}**",
        f"Recovery: **{recovery}**",
    ]
    if total is not None:
        timing_parts.append(f"Total: **{total}**")

    prop_parts = [
        f"Damage: **{damage}**",
        f"Guard: **{guard}**",
        f"Cancel: **{cancel}**",
    ]
    if atk_range != "-":
        prop_parts.append(f"Range: **{atk_range}**")

    lines = [
        f"**FRAME DATA QUIZ ({mode_label})**",
        "Guess the character and the move.",
        "",
        " | ".join(timing_parts),
        f"On Hit: **{on_hit}** | On Block: **{on_block}**",
        " | ".join(prop_parts),
        "",
        "Answer by mention or reply with: `Character Move`",
        "Example: `Ryu 5LP` or `Cammy spiral arrow`",
    ]
    return "\n".join(lines)


def _quiz_censor_embed_text(value, game="sf6"):
    return _quiz_censor_character_names(str(value or ""), game=game)


def build_quiz_frame_embed(row, mode="hard", show_notes=False, game="sf6"):
    """Build a quiz embed using the standard frame table format without answer identity."""
    mode_key = _quiz_normalize_mode(mode)
    mode_label = mode_key.capitalize()
    game_key = _quiz_game_key(game)
    embed_fn = _quiz_game_config(game_key).get("build_frame_embed") or build_frame_embed
    embed = embed_fn(row, show_notes=show_notes)
    embed.title = truncate_embed_value(f"{_quiz_game_label(game_key)} FRAME DATA QUIZ ({mode_label})", 256)
    embed.description = None
    embed.set_image(url=None)
    embed.set_thumbnail(url=None)

    for index, field in enumerate(list(embed.fields)):
        if str(field.name or "").startswith("Notes"):
            embed.set_field_at(
                index,
                name=field.name,
                value=truncate_embed_value(_quiz_censor_embed_text(field.value, game=game_key), 1024),
                inline=field.inline,
            )

    footer_text = getattr(getattr(embed, "footer", None), "text", "")
    if footer_text:
        censored_footer = _quiz_censor_character_names(footer_text, game=game_key)
        embed.set_footer(text=truncate_embed_value(censored_footer, 2048))

    return embed


def _quiz_row_has_notes(row, game="sf6"):
    notes_fn = _quiz_game_config(game).get("get_notes_text")
    if callable(notes_fn):
        notes = str(notes_fn(row) or "").strip()
    else:
        notes = clean_embed_value(row.get("extraInfo", ""), strip_brackets=True)
    return bool(notes)


# Question embeds and quiz UI views


def bind(**values):
    globals().update(values)


def is_deleted_message_reference_error(error):
    if isinstance(error, discord.NotFound):
        return True
    if isinstance(error, discord.HTTPException):
        text = str(error).lower()
        return "message_reference" in text and "unknown message" in text
    return False

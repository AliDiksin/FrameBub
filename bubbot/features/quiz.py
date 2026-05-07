import asyncio
import datetime
import difflib
import json
import os
import random
import re

import discord

try:
    from bubbot.features.bub_llm import (
        build_quiz_cheating_warning_message,
        build_quiz_correct_guess_message,
        build_quiz_decline_message,
        build_quiz_persona_intro,
        build_quiz_wrong_guess_message,
        classify_quiz_another_question_intent,
        classify_quiz_post_answer_choice_intent,
        sanitize_ascii_line,
    )
except ModuleNotFoundError as import_error:
    if import_error.name != "bub_llm":
        raise
    from bubbot.features.bub_llm_fallback import (
        build_quiz_cheating_warning_message,
        build_quiz_correct_guess_message,
        build_quiz_decline_message,
        build_quiz_persona_intro,
        build_quiz_wrong_guess_message,
        classify_quiz_another_question_intent,
        classify_quiz_post_answer_choice_intent,
        sanitize_ascii_line,
    )

FRAME_DATA = {}
CHARACTER_ALIASES = {}
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
    globals().update(deps)


ACTIVE_QUIZZES = {}
QUIZ_PENDING_ANOTHER = {}
QUIZ_PENDING_MODE = {}
QUIZ_ACTIVE_TIMEOUT_TASKS = {}
QUIZ_PENDING_ANOTHER_TIMEOUT_TASKS = {}
QUIZ_LEADERBOARD_FILE = os.getenv("QUIZ_LEADERBOARD_FILE", "quiz_leaderboard.json")
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
QUIZ_NAME_PREFIX_RE = re.compile(r"^\s*(?:hey\s+)?(?:korean\s+)?bub\b", re.IGNORECASE)
QUIZ_ESCAPE_REQUEST_RE = re.compile(
    r"\b(framedata|frame\s*data|gif|range|startup|damage|on\s+hit|on\s+block|bnb|oki|coach|compare|comparison|vs|versus|punish|stats?|health|reversal|cfn|remind(?:er)?|time)\b",
    re.IGNORECASE,
)
QUIZ_GUESS_AGAIN_RE = re.compile(
    r"\b(guess\s+again|again|continue|keep\s+guessing|try\s+again)\b",
    re.IGNORECASE,
)
QUIZ_REVEAL_END_RE = re.compile(
    r"\b(answer|reveal|show|tell|what'?s\s+the\s+answer|whats\s+the\s+answer|give\s+up|forfeit|forefeit|forfiet|surrender|concede|you\s+win|i\s+lose|end|stop|quit|cancel)\b",
    re.IGNORECASE,
)
QUIZ_ANOTHER_YES_RE = re.compile(
    r"\b(yes|yea|yeah|yep|yup|sure|ok|okay|another|again|continue|new\s+question)\b",
    re.IGNORECASE,
)
QUIZ_ANOTHER_NO_RE = re.compile(
    r"\b(no|nah|nope|naw|not\s+now|later|done|stop|end|quit|cancel|no\s+thanks|im\s+good|i'?m\s+good)\b",
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
QUIZ_PENDING_ANOTHER_TTL_SECONDS = 300
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
QUIZ_CHARACTER_TERMS_CACHE = None
QUIZ_MOVE_NAME_TERMS_CACHE = None
QUIZ_CHARACTER_CENSOR_PATTERNS_CACHE = None
QUIZ_VALID_MODES = {"easy", "medium", "hard"}
QUIZ_START_LOCK = asyncio.Lock()


# ==================== QUIZ FEATURE ====================

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


def _quiz_row_is_shared_mechanic(row):
    move_type = str(row.get("moveType", "")).strip().lower()
    if move_type in {"system", "drive", "throw", "taunt"}:
        return True

    combined = " ".join(
        str(row.get(key, "")).lower().strip()
        for key in ("moveName", "cmnName", "numCmd", "plnCmd")
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
        )
    )


def _quiz_row_is_jump_normal(row):
    move_type = str(row.get("moveType", "")).strip().lower()
    if move_type != "normal":
        return False

    move_name = str(row.get("moveName", "")).lower().strip()
    cmn_name = str(row.get("cmnName", "")).lower().strip()
    num_cmd = str(row.get("numCmd", "")).lower().strip()
    pln_cmd = str(row.get("plnCmd", "")).lower().strip()
    return (
        move_name.startswith("jump ")
        or cmn_name.startswith("jump ")
        or num_cmd.startswith(("7", "8", "9"))
        or pln_cmd.startswith(("u+", "ub+", "uf+", "j"))
    )


def _quiz_row_allowed_for_mode(row, mode):
    mode_key = _quiz_normalize_mode(mode)
    move_type = str(row.get("moveType", "")).strip().lower()

    if _quiz_row_is_shared_mechanic(row):
        return False

    if mode_key == "easy":
        return move_type == "normal" and not _quiz_row_is_jump_normal(row)

    if mode_key == "medium":
        return move_type in {"normal", "special", "command-grab", "movement-special"}

    if mode_key == "hard":
        return move_type in {"normal", "special", "movement-special", "command-grab", "super"}
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


def build_quiz_frame_embed(row, mode="hard"):
    """Build a quiz embed using the standard frame table format without answer identity."""
    mode_key = _quiz_normalize_mode(mode)
    mode_label = mode_key.capitalize()
    embed = build_frame_embed(row)
    embed.title = truncate_embed_value(f"FRAME DATA QUIZ ({mode_label})", 256)
    embed.description = None

    footer_text = getattr(getattr(embed, "footer", None), "text", "")
    if footer_text:
        censored_footer = _quiz_censor_character_names(footer_text)
        embed.set_footer(text=truncate_embed_value(censored_footer, 2048))

    return embed


def _normalize_quiz_words(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _get_quiz_character_terms():
    global QUIZ_CHARACTER_TERMS_CACHE
    if QUIZ_CHARACTER_TERMS_CACHE is not None:
        return QUIZ_CHARACTER_TERMS_CACHE

    terms = set()
    for name in FRAME_DATA.keys():
        normalized = _normalize_quiz_words(name)
        if normalized:
            terms.add(normalized)

    for name in CHARACTER_ALIASES.keys():
        normalized = _normalize_quiz_words(name)
        if normalized:
            terms.add(normalized)

    for name in CHARACTER_ALIASES.values():
        normalized = _normalize_quiz_words(name)
        if normalized:
            terms.add(normalized)

    QUIZ_CHARACTER_TERMS_CACHE = sorted(terms, key=len, reverse=True)
    return QUIZ_CHARACTER_TERMS_CACHE


def _get_quiz_character_censor_patterns():
    global QUIZ_CHARACTER_CENSOR_PATTERNS_CACHE
    if QUIZ_CHARACTER_CENSOR_PATTERNS_CACHE is not None:
        return QUIZ_CHARACTER_CENSOR_PATTERNS_CACHE

    patterns = []
    seen_patterns = set()
    for term in _get_quiz_character_terms():
        words = [word for word in str(term or "").split() if word]
        if not words:
            continue
        pattern_text = r"\b" + r"\W*".join(re.escape(word) for word in words) + r"\b"
        if pattern_text in seen_patterns:
            continue
        seen_patterns.add(pattern_text)
        patterns.append(re.compile(pattern_text, re.IGNORECASE))

    QUIZ_CHARACTER_CENSOR_PATTERNS_CACHE = patterns
    return QUIZ_CHARACTER_CENSOR_PATTERNS_CACHE


def _quiz_censor_character_names(text):
    raw_text = str(text or "")
    if not raw_text:
        return raw_text

    def mask_match(match):
        matched = match.group(0)
        alnum_count = len(re.sub(r"[^A-Za-z0-9]", "", matched))
        return "*" * max(1, alnum_count)

    censored = raw_text
    for pattern in _get_quiz_character_censor_patterns():
        censored = pattern.sub(mask_match, censored)
    return censored


def _get_quiz_move_name_terms():
    global QUIZ_MOVE_NAME_TERMS_CACHE
    if QUIZ_MOVE_NAME_TERMS_CACHE is not None:
        return QUIZ_MOVE_NAME_TERMS_CACHE

    terms = set()
    for rows in FRAME_DATA.values():
        for row in rows:
            normalized = _normalize_quiz_words(row.get("moveName", ""))
            if not normalized:
                continue
            words = normalized.split()
            if len(words) >= 2 or len(normalized) >= 7:
                terms.add(normalized)

    QUIZ_MOVE_NAME_TERMS_CACHE = sorted(terms, key=len, reverse=True)
    return QUIZ_MOVE_NAME_TERMS_CACHE


def _quiz_intro_has_specific_answer_hint(text):
    normalized = _normalize_quiz_words(text)
    if not normalized:
        return True

    if re.search(r"\d", normalized):
        return True
    if QUIZ_INTRO_BUTTON_RE.search(normalized):
        return True
    if QUIZ_INTRO_DATA_TERM_RE.search(normalized):
        return True

    padded = f" {normalized} "
    for term in _get_quiz_character_terms():
        if f" {term} " in padded:
            return True

    for term in _get_quiz_move_name_terms():
        if f" {term} " in padded:
            return True
    return False


async def build_quiz_question_message(channel, round_num, total_rounds, row, mode="hard"):
    """Build quiz prompt text + embed using the standard frame table layout."""
    intro = await build_quiz_persona_intro(
        channel,
        round_num,
        total_rounds,
        mode,
        sanitize_ascii_line,
        _quiz_intro_has_specific_answer_hint,
    )
    intro = _quiz_censor_character_names(intro)
    quiz_embed = build_quiz_frame_embed(row, mode=mode)
    prompt_text = f"{intro}\nAnswer by mention or reply with: `Character Move`"
    return prompt_text, quiz_embed


async def _quiz_send_thinking_message(message, text="Thinking..."):
    """Send an immediate quiz placeholder reply while longer work runs."""
    try:
        return await message.reply(text)
    except Exception as e:
        if is_deleted_message_reference_error(e):
            try:
                return await message.channel.send(text)
            except Exception as send_error:
                print(f"[quiz] thinking send error: {send_error}", flush=True)
                return None
        print(f"[quiz] thinking reply error: {e}", flush=True)
        try:
            return await message.channel.send(text)
        except Exception as send_error:
            print(f"[quiz] thinking fallback send error: {send_error}", flush=True)
            return None


async def _quiz_publish_from_placeholder(channel, placeholder_message, text, embed=None):
    """Edit placeholder message into final quiz output, or send a fallback."""
    if placeholder_message is not None:
        try:
            await placeholder_message.edit(content=text, embed=embed)
            return placeholder_message
        except Exception as e:
            print(f"[quiz] placeholder edit error: {e}", flush=True)

    try:
        return await channel.send(text, embed=embed)
    except Exception as e:
        print(f"[quiz] placeholder fallback send error: {e}", flush=True)
        return None


def _normalize_quiz_numcmd(text):
    normalized = str(text or "").strip().lower()
    normalized = re.sub(r"[\[\]\(\)\{\}]", " ", normalized)
    normalized = re.sub(r"\s+", "", normalized)
    return re.sub(r"[^a-z0-9>]", "", normalized)


def _quiz_has_explicit_strength(text):
    lowered = str(text or "").lower()
    tokens = re.findall(r"[a-z0-9]+", lowered)
    explicit_tokens = {
        "lp",
        "mp",
        "hp",
        "lk",
        "mk",
        "hk",
        "pp",
        "kk",
        "od",
        "ex",
        "light",
        "medium",
        "heavy",
    }
    if any(token in explicit_tokens for token in tokens):
        return True

    # Alex stance follow-ups like "stance 6p" or "2pp 2lplk" are exact
    # follow-up notations even though they are not regular strength words.
    if re.search(
        r"\b(?:stance|2pp)\s+(?:6p|6|4|lplk|5lplk|2lplk)\b",
        lowered,
    ):
        return True

    compact = re.sub(r"[^a-z0-9>]", "", lowered)
    return bool(re.search(r"(lp|mp|hp|lk|mk|hk|pp|kk)$", compact))


def _quiz_genericize_numcmd_suffix(numcmd):
    value = str(numcmd or "")
    qualifiers = []
    while True:
        matched_suffix = None
        for suffix in ("air", "hold", "bomb", "charged"):
            if value.endswith(suffix):
                matched_suffix = suffix
                break
        if not matched_suffix:
            break
        qualifiers.append(matched_suffix)
        value = value[: -len(matched_suffix)]

    value = re.sub(r"(lp|mp|hp)$", "p", value)
    value = re.sub(r"(lk|mk|hk)$", "k", value)
    value = re.sub(r"pp$", "p", value)
    value = re.sub(r"kk$", "k", value)

    if qualifiers:
        value = f"{value}{''.join(reversed(qualifiers))}"
    return value


def _quiz_numcmd_variant_info(numcmd):
    normalized = _normalize_quiz_numcmd(numcmd)
    if not normalized:
        return None

    main_segment = ""
    for segment in normalized.split(">"):
        if segment:
            main_segment = segment
            break
    if not main_segment:
        return None

    family_tags = []
    while True:
        matched_suffix = None
        for suffix in ("air", "hold", "bomb", "charged"):
            if main_segment.endswith(suffix):
                matched_suffix = suffix
                break
        if not matched_suffix:
            break
        family_tags.append(matched_suffix)
        main_segment = main_segment[: -len(matched_suffix)]

    if not main_segment:
        return None

    family_suffix = f"|{'|'.join(reversed(family_tags))}" if family_tags else ""

    if main_segment.endswith("pp"):
        return {
            "family": f"{main_segment[:-2]}p{family_suffix}",
            "variant": "od",
            "channel": "p",
        }
    if main_segment.endswith("kk"):
        return {
            "family": f"{main_segment[:-2]}k{family_suffix}",
            "variant": "od",
            "channel": "k",
        }

    if main_segment.endswith(("lp", "mp", "hp")):
        return {
            "family": f"{main_segment[:-2]}p{family_suffix}",
            "variant": "specific",
            "channel": "p",
        }
    if main_segment.endswith(("lk", "mk", "hk")):
        return {
            "family": f"{main_segment[:-2]}k{family_suffix}",
            "variant": "specific",
            "channel": "k",
        }

    if main_segment.endswith("p"):
        return {
            "family": f"{main_segment}{family_suffix}",
            "variant": "generic",
            "channel": "p",
        }
    if main_segment.endswith("k"):
        return {
            "family": f"{main_segment}{family_suffix}",
            "variant": "generic",
            "channel": "k",
        }

    return None


def _quiz_numcmd_family_profile(char_key, numcmd):
    info = _quiz_numcmd_variant_info(numcmd)
    if not info:
        return None

    family = info["family"]
    profile = {
        "family": family,
        "generic": 0,
        "od": 0,
        "specific": 0,
        "total": 0,
    }
    seen_numcmds = set()

    for row in FRAME_DATA.get(char_key, []):
        row_numcmd = str(row.get("numCmd", "")).strip().lower()
        if not row_numcmd or row_numcmd in seen_numcmds:
            continue

        row_info = _quiz_numcmd_variant_info(row_numcmd)
        if not row_info or row_info.get("family") != family:
            continue

        seen_numcmds.add(row_numcmd)
        row_variant = row_info.get("variant")
        if row_variant in ("generic", "od", "specific"):
            profile[row_variant] += 1
            profile["total"] += 1

    return profile


def _quiz_correct_row_allows_generic_strength(char_key, correct_numcmd):
    info = _quiz_numcmd_variant_info(correct_numcmd)
    if not info:
        return False

    profile = _quiz_numcmd_family_profile(char_key, correct_numcmd)
    if not profile:
        return False

    is_regular_od_only_family = (
        profile.get("specific") == 0
        and profile.get("generic", 0) >= 1
        and profile.get("od", 0) >= 1
    )
    return is_regular_od_only_family and info.get("variant") == "generic"


def _quiz_is_generic_numcmd_notation(text):
    compact = _normalize_quiz_numcmd(text)
    return bool(re.fullmatch(r"\d+[pk]", compact))


def _quiz_is_exact_move_name_answer(move_text, row):
    query_name = _normalize_quiz_name(move_text)
    if not query_name:
        return False
    move_name = _normalize_quiz_name((row or {}).get("moveName", ""))
    return bool(move_name) and query_name == move_name


def _quiz_numcmd_variants(numcmd, include_generic=False):
    normalized = _normalize_quiz_numcmd(numcmd)
    if not normalized:
        return set()

    variants = {normalized}
    if ">" in normalized:
        parts = [segment for segment in normalized.split(">") if segment]
        variants.update(parts)
        if parts:
            variants.add(parts[-1])

    if include_generic:
        generic_variants = {
            _quiz_genericize_numcmd_suffix(value)
            for value in list(variants)
            if value
        }
        variants.update(value for value in generic_variants if value)

    return variants


def _quiz_genericize_combo_numcmd(numcmd):
    normalized = _normalize_quiz_numcmd(numcmd)
    if not normalized:
        return ""
    parts = [part for part in normalized.split(">") if part]
    if not parts:
        return normalized
    return ">".join(_quiz_genericize_numcmd_suffix(part) for part in parts)


def _quiz_row_numcmd_matches_correct(row, correct_numcmd, allow_generic=False):
    candidate_numcmd = str((row or {}).get("numCmd", "")).strip().lower()
    if not candidate_numcmd:
        return False

    candidate_norm = _normalize_quiz_numcmd(candidate_numcmd)
    correct_norm = _normalize_quiz_numcmd(correct_numcmd)
    if ">" in correct_norm or ">" in candidate_norm:
        if candidate_norm == correct_norm:
            return True
        if not allow_generic:
            return False
        return _quiz_genericize_combo_numcmd(candidate_norm) == _quiz_genericize_combo_numcmd(correct_norm)

    candidate_strict = _quiz_numcmd_variants(candidate_numcmd, include_generic=False)
    correct_strict = _quiz_numcmd_variants(correct_numcmd, include_generic=False)
    if candidate_strict & correct_strict:
        return True

    if not allow_generic:
        return False

    candidate_generic = _quiz_numcmd_variants(candidate_numcmd, include_generic=True)
    correct_generic = _quiz_numcmd_variants(correct_numcmd, include_generic=True)
    return bool(candidate_generic & correct_generic)


def _normalize_quiz_name(text):
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


def _extract_char_and_move_from_text(text):
    """
    Try to parse (char_key, move_text) from a user answer string.
    Tries progressively longer word prefixes for the character name.
    Returns (char_key, move_text) or (None, None).
    """
    words = text.strip().lower().split()
    if not words:
        return None, None
    for prefix_len in range(min(3, len(words)), 0, -1):
        char_candidate = " ".join(words[:prefix_len])
        char_key = resolve_character_key(char_candidate)
        if char_key:
            move_text = " ".join(words[prefix_len:]).strip()
            return char_key, move_text
    return None, None


def check_quiz_answer(quiz_state, text):
    """
    Return True if `text` is a correct answer to the active quiz round.
    Checks character match, then uses lookup_frame_data to match the move.
    """
    correct_char = quiz_state["char_key"]
    correct_numcmd = quiz_state["numcmd"]
    correct_row = quiz_state.get("row") or {}
    if not correct_numcmd:
        return False

    def quiz_row_is_ca_variant(row):
        move_name = str((row or {}).get("moveName", "")).lower()
        cmn_name = str((row or {}).get("cmnName", "")).lower()
        num_cmd = str((row or {}).get("numCmd", "")).lower()
        return (
            "critical art" in move_name
            or "critical art" in cmn_name
            or bool(re.search(r"\(\s*ca\s*\)", num_cmd))
        )

    char_key, move_text = _extract_char_and_move_from_text(text)
    if not char_key or not move_text:
        return False
    if char_key != correct_char:
        return False

    user_move_compact = _normalize_quiz_numcmd(move_text)
    user_has_explicit_strength = _quiz_has_explicit_strength(move_text)
    allow_generic_strength = (
        not user_has_explicit_strength
        and _quiz_correct_row_allows_generic_strength(correct_char, correct_numcmd)
    )
    if _quiz_is_generic_numcmd_notation(move_text) and not allow_generic_strength:
        return False

    if user_move_compact:
        direct_user_row = {"numCmd": user_move_compact}
        if _quiz_row_numcmd_matches_correct(
            direct_user_row,
            correct_numcmd,
            allow_generic=allow_generic_strength,
        ):
            return True

    candidate_rows = []

    direct_row = lookup_frame_data(char_key, move_text)
    if direct_row is not None:
        candidate_rows.append(direct_row)

    if quiz_row_is_ca_variant(correct_row) and re.search(r"\b(?:ca|critical(?:\s+art)?)\b", move_text):
        ca_row = lookup_frame_data(char_key, "critical art")
        if ca_row is not None and ca_row not in candidate_rows:
            candidate_rows.append(ca_row)

    if re.search(r"\b(tc|target\s+combo|targetcombo)\b", move_text):
        parser_query = f"{char_key} {move_text}".strip().lower()
        parser_payload = find_moves_in_text(parser_query)
        parsed_rows = parser_payload.get("rows", [])
        for parsed_row in parsed_rows:
            row_char = resolve_character_key(str(parsed_row.get("char_name", "")))
            if row_char != char_key:
                continue
            if parsed_row not in candidate_rows:
                candidate_rows.append(parsed_row)

    for row in candidate_rows:
        if _quiz_row_numcmd_matches_correct(row, correct_numcmd, allow_generic=False):
            if not user_has_explicit_strength:
                row_profile = _quiz_numcmd_family_profile(correct_char, row.get("numCmd", ""))
                if row_profile and row_profile.get("specific", 0) > 0:
                    if not _quiz_is_exact_move_name_answer(move_text, row):
                        continue
            return True

        if _quiz_row_numcmd_matches_correct(
            row,
            correct_numcmd,
            allow_generic=allow_generic_strength,
        ):
            return True
    # Fuzzy match fallback for misspellings in move names/common names.
    user_move_name = str(move_text or "").strip().lower()
    if not user_move_name:
        return False

    fuzzy_name_candidates = []
    for row in FRAME_DATA.get(char_key, []):
        if not _quiz_row_has_data(row):
            continue
        if not _quiz_row_allowed_for_mode(row, quiz_state.get("mode", "hard")):
            continue
        move_name = str(row.get("moveName", "")).strip().lower()
        cmn_name = str(row.get("cmnName", "")).strip().lower()
        for candidate_name in (move_name, cmn_name):
            if len(candidate_name) < 4:
                continue
            fuzzy_name_candidates.append((candidate_name, row))

    if fuzzy_name_candidates:
        fuzzy_choices = [name for name, _ in fuzzy_name_candidates]
        close_names = difflib.get_close_matches(user_move_name, fuzzy_choices, n=2, cutoff=0.84)
        for close_name in close_names:
            for candidate_name, row in fuzzy_name_candidates:
                if candidate_name != close_name:
                    continue
                if _quiz_row_numcmd_matches_correct(
                    row,
                    correct_numcmd,
                    allow_generic=allow_generic_strength,
                ):
                    return True
    return False


def _quiz_clean_display_name(name):
    cleaned = re.sub(r"\s+", " ", str(name or "")).strip()
    return cleaned or "Unknown"


def _quiz_user_display_name(user):
    return _quiz_clean_display_name(
        getattr(user, "display_name", None) or getattr(user, "name", None)
    )


def _quiz_score_line(name, points):
    safe_name = _quiz_clean_display_name(name)
    try:
        safe_points = int(points)
    except Exception:
        safe_points = 0
    return f"{safe_name}- {safe_points}"


def _format_quiz_scores(scores, score_names=None):
    """Format leaderboard lines as `username- points` sorted by highest points."""
    if not scores:
        return "No points scored."

    score_names = score_names or {}

    def sort_key(item):
        uid, pts = item
        try:
            point_value = int(pts)
        except Exception:
            point_value = 0
        display = _quiz_clean_display_name(score_names.get(uid, f"User {uid}"))
        return (-point_value, display.lower())

    lines = []
    for uid, pts in sorted(scores.items(), key=sort_key):
        display = _quiz_clean_display_name(score_names.get(uid, f"User {uid}"))
        lines.append(_quiz_score_line(display, pts))
    return "\n".join(lines)


def _quiz_build_crown_line(scores, score_names=None):
    """Build an in-character crown line for the highest scorer(s)."""
    if not scores:
        return "No one scored this session, so the crown remains unclaimed."

    score_names = score_names or {}
    normalized_points = {}
    for uid, pts in scores.items():
        try:
            normalized_points[uid] = int(pts)
        except Exception:
            normalized_points[uid] = 0

    top_points = max(normalized_points.values())
    winners = [uid for uid, pts in normalized_points.items() if pts == top_points]
    winner_names = [
        _quiz_clean_display_name(score_names.get(uid, f"User {uid}"))
        for uid in winners
    ]

    if len(winner_names) == 1:
        return (
            f"By decree of Bub, {winner_names[0]} takes the crown with "
            f"{top_points} point{'s' if top_points != 1 else ''}."
        )

    joined_winners = ", ".join(winner_names)
    return (
        f"By decree of Bub, the crown is shared by {joined_winners} at "
        f"{top_points} point{'s' if top_points != 1 else ''} each."
    )


def _quiz_unique_rows_for_char(char_key, asked=None, mode="hard"):
    """Return mode-filtered rows whose moveName is unique within the character sheet."""
    mode_key = _quiz_normalize_mode(mode)
    asked = asked or set()
    rows = FRAME_DATA.get(char_key, [])
    if not rows:
        return []

    name_counts = {}
    for row in rows:
        if not _quiz_row_has_data(row):
            continue
        if not _quiz_row_allowed_for_mode(row, mode_key):
            continue
        name_key = _normalize_quiz_name(row.get("moveName", ""))
        if not name_key:
            continue
        name_counts[name_key] = name_counts.get(name_key, 0) + 1

    unique_rows = []
    for row in rows:
        if not _quiz_row_has_data(row):
            continue
        if not _quiz_row_allowed_for_mode(row, mode_key):
            continue
        numcmd = str(row.get("numCmd", "")).strip().lower()
        if (char_key, numcmd) in asked:
            continue
        name_key = _normalize_quiz_name(row.get("moveName", ""))
        if name_counts.get(name_key, 0) == 1:
            unique_rows.append(row)

    return unique_rows


def pick_quiz_move(asked=None, mode="hard"):
    """
    Pick a random (char_key, row) from FRAME_DATA suitable for a quiz question.
    `asked` is an optional set of (char_key, numcmd) tuples already used this session.
    """
    mode_key = _quiz_normalize_mode(mode)
    asked = asked or set()
    if not FRAME_DATA:
        return None, None
    char_keys = [k for k, rows in FRAME_DATA.items() if rows]
    if not char_keys:
        return None, None

    # Try up to 30 random picks, prioritizing rows with unique move names.
    for _ in range(30):
        char_key = random.choice(char_keys)
        rows = _quiz_unique_rows_for_char(char_key, asked=asked, mode=mode_key)
        if rows:
            return char_key, random.choice(rows)

    # Fallback 1: unique move-name rows (ignore asked dedup)
    random.shuffle(char_keys)
    for char_key in char_keys:
        rows = _quiz_unique_rows_for_char(char_key, asked=set(), mode=mode_key)
        if rows:
            return char_key, random.choice(rows)

    # Fallback 2: any valid row
    random.shuffle(char_keys)
    for char_key in char_keys:
        rows = [
            r
            for r in FRAME_DATA[char_key]
            if _quiz_row_has_data(r) and _quiz_row_allowed_for_mode(r, mode_key)
        ]
        if rows:
            return char_key, random.choice(rows)
    return None, None


async def start_quiz(
    message,
    mode="hard",
    session_scores=None,
    session_score_names=None,
    session_round=1,
    session_owner_user_id=None,
    session_message_ids=None,
):
    """Initialize and send one quiz question in the channel."""
    mode_key = _quiz_normalize_mode(mode)
    channel_id = message.channel.id
    if QUIZ_START_LOCK.locked():
        try:
            await message.reply("A quiz is already being prepared. Please wait a moment.")
        except Exception as e:
            if is_deleted_message_reference_error(e):
                try:
                    await message.channel.send("A quiz is already being prepared. Please wait a moment.")
                except Exception as send_error:
                    print(f"[quiz] locked-start send error: {send_error}", flush=True)
            else:
                print(f"[quiz] locked-start reply error: {e}", flush=True)
        return

    async with QUIZ_START_LOCK:
        if channel_id in ACTIVE_QUIZZES:
            try:
                await message.reply(
                    "A quiz is already running. Mention me and say `stop quiz` to end it."
                )
            except Exception as e:
                print(f"[quiz] already-running reply error: {e}", flush=True)
            return

        char_key, row = pick_quiz_move(mode=mode_key)
        if not char_key:
            try:
                await message.reply(f"No frame data is available for {mode_key} mode.")
            except Exception as e:
                print(f"[quiz] no-data reply error: {e}", flush=True)
            return

        normalized_scores = {}
        if isinstance(session_scores, dict):
            for raw_uid, raw_points in session_scores.items():
                try:
                    uid = int(raw_uid)
                    pts = int(raw_points)
                except Exception:
                    continue
                if pts < 0:
                    continue
                normalized_scores[uid] = pts

        normalized_score_names = {}
        if isinstance(session_score_names, dict):
            for raw_uid, raw_name in session_score_names.items():
                try:
                    uid = int(raw_uid)
                except Exception:
                    continue
                normalized_score_names[uid] = _quiz_clean_display_name(raw_name)

        for uid in normalized_scores.keys():
            if uid not in normalized_score_names:
                normalized_score_names[uid] = _quiz_clean_display_name(f"User {uid}")

        try:
            round_num = max(1, int(session_round))
        except Exception:
            round_num = 1

        try:
            owner_user_id = int(session_owner_user_id)
        except Exception:
            owner_user_id = int(message.author.id)

        normalized_message_ids = _quiz_normalize_message_ids(session_message_ids)

        numcmd = str(row.get("numCmd", "")).strip().lower()
        quiz_state = {
            "channel_id": channel_id,
            "owner_user_id": owner_user_id,
            "total_rounds": 1,
            "round": round_num,
            "scores": normalized_scores,
            "score_names": normalized_score_names,
            "char_key": char_key,
            "numcmd": numcmd,
            "row": row,
            "mode": mode_key,
            "created_at": datetime.datetime.now(datetime.timezone.utc),
            "answered": False,
            "awaiting_choice": False,
            "asked": {(char_key, numcmd)},
            "message_ids": normalized_message_ids,
        }

        answer_char = str(row.get("char_name", char_key.capitalize())).strip()
        answer_move = str(row.get("moveName", "?")).strip()
        answer_numcmd = str(row.get("numCmd", "?")).strip()
        print(
            f"[quiz] answer-key channel_id={channel_id} round={round_num} mode={mode_key} "
            f"char={answer_char} move={answer_move} numcmd={answer_numcmd}",
            flush=True,
        )

        ACTIVE_QUIZZES[channel_id] = quiz_state
        QUIZ_PENDING_ANOTHER.pop(channel_id, None)
        _quiz_cancel_pending_another_timeout(channel_id)
        QUIZ_PENDING_MODE.pop(channel_id, None)

        thinking_message = await _quiz_send_thinking_message(message)

        question_text, question_embed = await build_quiz_question_message(
            message.channel,
            round_num,
            1,
            row,
            mode=mode_key,
        )
        sent = await _quiz_publish_from_placeholder(
            message.channel,
            thinking_message,
            question_text,
            embed=question_embed,
        )
        if sent is None:
            ACTIVE_QUIZZES.pop(channel_id, None)
            _quiz_cancel_active_timeout(channel_id)
            return

        _quiz_track_message_id(quiz_state, getattr(sent, "id", None))
        _quiz_schedule_active_timeout(channel_id, message.channel, quiz_state)


async def prompt_quiz_mode_selection(
    message,
    session_mode=None,
    session_scores=None,
    session_score_names=None,
    session_round=1,
    session_owner_user_id=None,
    session_message_ids=None,
):
    """Prompt user to specify quiz difficulty and track pending mode selection."""
    channel_id = message.channel.id
    prompt_text = (
        "Specify quiz difficulty: `easy`, `medium`, or `hard`. "
        "Easy = normals only. Medium = normals + specials. Hard = everything."
    )

    stored_mode = str(session_mode or "").strip().lower()
    if stored_mode not in QUIZ_VALID_MODES:
        stored_mode = None

    try:
        owner_user_id = int(session_owner_user_id)
    except Exception:
        owner_user_id = int(message.author.id)

    normalized_message_ids = _quiz_normalize_message_ids(session_message_ids)

    pending_payload = {
        "created_at": datetime.datetime.now(datetime.timezone.utc),
        "message_id": None,
        "owner_user_id": owner_user_id,
        "mode": stored_mode,
        "scores": dict(session_scores or {}),
        "score_names": dict(session_score_names or {}),
        "round": session_round,
        "message_ids": normalized_message_ids,
    }

    try:
        sent = await message.reply(prompt_text)
        pending_payload["message_id"] = getattr(sent, "id", None)
        QUIZ_PENDING_MODE[channel_id] = pending_payload
    except Exception as e:
        if is_deleted_message_reference_error(e):
            sent = await message.channel.send(prompt_text)
            pending_payload["message_id"] = getattr(sent, "id", None)
            QUIZ_PENDING_MODE[channel_id] = pending_payload
        else:
            print(f"[quiz] mode-prompt send error: {e}", flush=True)


async def stop_quiz(message):
    """Cancel the active quiz in the channel and reveal the current answer."""
    channel_id = message.channel.id
    quiz = ACTIVE_QUIZZES.pop(channel_id, None)
    _quiz_cancel_active_timeout(channel_id)
    if not quiz:
        try:
            await message.reply("No quiz is running right now.")
        except Exception as e:
            print(f"[quiz] stop-no-quiz reply error: {e}", flush=True)
        return

    row = quiz["row"]
    char_key = quiz["char_key"]
    char_display = str(row.get("char_name", char_key.capitalize())).strip()
    move_name = str(row.get("moveName", "?")).strip()
    num_cmd = str(row.get("numCmd", "?")).strip()
    reply_text = (
        f"Quiz ended. The answer was **{char_display}'s {move_name} ({num_cmd})**.\n"
        "Would you like another question?"
    )
    try:
        sent = await message.reply(reply_text)
        QUIZ_PENDING_ANOTHER[channel_id] = {
            "created_at": datetime.datetime.now(datetime.timezone.utc),
            "message_id": getattr(sent, "id", None),
            "mode": quiz.get("mode", "hard"),
            "owner_user_id": quiz.get("owner_user_id"),
            "scores": dict(quiz.get("scores") or {}),
            "score_names": dict(quiz.get("score_names") or {}),
            "round": quiz.get("round", 1),
            "message_ids": _quiz_build_message_history(quiz, getattr(sent, "id", None)),
        }
        _quiz_schedule_pending_another_timeout(channel_id, message.channel)
    except Exception as e:
        if is_deleted_message_reference_error(e):
            sent = await message.channel.send(reply_text)
            QUIZ_PENDING_ANOTHER[channel_id] = {
                "created_at": datetime.datetime.now(datetime.timezone.utc),
                "message_id": getattr(sent, "id", None),
                "mode": quiz.get("mode", "hard"),
                "owner_user_id": quiz.get("owner_user_id"),
                "scores": dict(quiz.get("scores") or {}),
                "score_names": dict(quiz.get("score_names") or {}),
                "round": quiz.get("round", 1),
                "message_ids": _quiz_build_message_history(quiz, getattr(sent, "id", None)),
            }
            _quiz_schedule_pending_another_timeout(channel_id, message.channel)
        else:
            print(f"[quiz] stop send error: {e}", flush=True)


def _is_reply_to_quiz_msg(message):
    """True if the message replies to any tracked quiz-related bot message."""
    ref = getattr(message, "reference", None)
    if not ref:
        return False
    channel_id = message.channel.id
    quiz = ACTIVE_QUIZZES.get(channel_id)
    if not quiz:
        return False

    quiz_message_ids = quiz.get("message_ids")
    if isinstance(quiz_message_ids, list):
        try:
            ref_id = int(ref.message_id)
        except Exception:
            ref_id = ref.message_id
        if ref_id in quiz_message_ids:
            return True

    last_id = quiz.get("last_message_id")
    return last_id is not None and ref.message_id == last_id


def _quiz_track_message_id(quiz_state, message_id):
    """Track quiz-related bot message IDs so replies stay addressable."""
    if not isinstance(quiz_state, dict) or not message_id:
        return

    try:
        normalized_id = int(message_id)
    except Exception:
        return

    message_ids = quiz_state.get("message_ids")
    if not isinstance(message_ids, list):
        message_ids = []

    if normalized_id not in message_ids:
        message_ids.append(normalized_id)
    if len(message_ids) > 40:
        message_ids = message_ids[-40:]

    quiz_state["message_ids"] = message_ids
    quiz_state["last_message_id"] = normalized_id


def _quiz_normalize_message_ids(raw_message_ids):
    """Normalize and dedupe message id history while preserving order."""
    temp_state = {}
    if isinstance(raw_message_ids, list):
        for raw_id in raw_message_ids:
            _quiz_track_message_id(temp_state, raw_id)
    return list(temp_state.get("message_ids") or [])


def _quiz_build_message_history(state, appended_message_id=None):
    """Build message-id history from existing state plus an optional new message id."""
    temp_state = {
        "message_ids": _quiz_normalize_message_ids(
            (state or {}).get("message_ids", []) if isinstance(state, dict) else []
        )
    }
    if isinstance(state, dict):
        _quiz_track_message_id(temp_state, state.get("last_message_id"))
    _quiz_track_message_id(temp_state, appended_message_id)
    return list(temp_state.get("message_ids") or [])


def _is_reply_to_quiz_followup_msg(message):
    """True if message replies to the most recent 'another question' prompt."""
    ref = getattr(message, "reference", None)
    if not ref:
        return False
    pending = QUIZ_PENDING_ANOTHER.get(message.channel.id)
    if not pending:
        return False
    pending_id = pending.get("message_id")
    return pending_id is not None and ref.message_id == pending_id


def _is_reply_to_quiz_mode_prompt(message):
    """True if message replies to the most recent difficulty prompt."""
    ref = getattr(message, "reference", None)
    if not ref:
        return False
    pending = QUIZ_PENDING_MODE.get(message.channel.id)
    if not pending:
        return False
    pending_id = pending.get("message_id")
    return pending_id is not None and ref.message_id == pending_id


def _quiz_cancel_pending_another_timeout(channel_id):
    task = QUIZ_PENDING_ANOTHER_TIMEOUT_TASKS.pop(channel_id, None)
    if task and not task.done():
        task.cancel()


def _quiz_cancel_active_timeout(channel_id):
    task = QUIZ_ACTIVE_TIMEOUT_TASKS.pop(channel_id, None)
    if task and not task.done():
        task.cancel()


def _quiz_active_timeout_message(quiz_state):
    char_display, move_name, num_cmd = _quiz_answer_display(quiz_state)
    score_text = _format_quiz_scores(
        dict((quiz_state or {}).get("scores") or {}),
        dict((quiz_state or {}).get("score_names") or {}),
    )
    return (
        "Quiz timed out after 5 minutes with no correct answer.\n"
        f"The answer was **{char_display}'s {move_name} ({num_cmd})**.\n"
        f"{score_text}\n"
        "Would you like another question?"
    )


def _quiz_schedule_active_timeout(channel_id, channel, quiz_state):
    _quiz_cancel_active_timeout(channel_id)

    async def _timeout_worker():
        try:
            await asyncio.sleep(QUIZ_ACTIVE_TTL_SECONDS)
            active = ACTIVE_QUIZZES.get(channel_id)
            if active is not quiz_state:
                return

            created_at = active.get("created_at")
            if created_at:
                age = (datetime.datetime.now(datetime.timezone.utc) - created_at).total_seconds()
                remaining = QUIZ_ACTIVE_TTL_SECONDS - age
                if remaining > 0:
                    await asyncio.sleep(remaining)

            active = ACTIVE_QUIZZES.get(channel_id)
            if active is not quiz_state:
                return

            created_at = active.get("created_at")
            if created_at:
                age = (datetime.datetime.now(datetime.timezone.utc) - created_at).total_seconds()
                if age < QUIZ_ACTIVE_TTL_SECONDS:
                    return

            expired_quiz = ACTIVE_QUIZZES.pop(channel_id, None)
            if expired_quiz is not quiz_state:
                if expired_quiz:
                    ACTIVE_QUIZZES[channel_id] = expired_quiz
                return

            expiry_text = _quiz_active_timeout_message(expired_quiz)
            try:
                sent = await channel.send(expiry_text)
                QUIZ_PENDING_ANOTHER[channel_id] = {
                    "created_at": datetime.datetime.now(datetime.timezone.utc),
                    "message_id": getattr(sent, "id", None),
                    "mode": expired_quiz.get("mode", "hard"),
                    "owner_user_id": expired_quiz.get("owner_user_id"),
                    "scores": dict(expired_quiz.get("scores") or {}),
                    "score_names": dict(expired_quiz.get("score_names") or {}),
                    "round": expired_quiz.get("round", 1),
                    "message_ids": _quiz_build_message_history(expired_quiz, getattr(sent, "id", None)),
                }
                _quiz_schedule_pending_another_timeout(channel_id, channel)
            except Exception as send_error:
                print(f"[quiz] active-expiry send error: {send_error}", flush=True)
        except asyncio.CancelledError:
            return
        finally:
            tracked_task = QUIZ_ACTIVE_TIMEOUT_TASKS.get(channel_id)
            if tracked_task is asyncio.current_task():
                QUIZ_ACTIVE_TIMEOUT_TASKS.pop(channel_id, None)

    QUIZ_ACTIVE_TIMEOUT_TASKS[channel_id] = asyncio.create_task(_timeout_worker())


def _quiz_timeout_expiry_message(pending_state):
    scores = dict((pending_state or {}).get("scores") or {})
    score_names = dict((pending_state or {}).get("score_names") or {})
    crown_line = _quiz_build_crown_line(scores, score_names)
    score_text = _format_quiz_scores(scores, score_names)
    return (
        "By decree of Bub, the 5-minute window for another question has closed.\n"
        f"{crown_line}\n"
        f"{score_text}"
    )


def _quiz_schedule_pending_another_timeout(channel_id, channel):
    _quiz_cancel_pending_another_timeout(channel_id)

    async def _timeout_worker():
        try:
            await asyncio.sleep(QUIZ_PENDING_ANOTHER_TTL_SECONDS)
            pending = QUIZ_PENDING_ANOTHER.get(channel_id)
            if not pending:
                return

            created_at = pending.get("created_at")
            if created_at:
                age = (datetime.datetime.now(datetime.timezone.utc) - created_at).total_seconds()
                remaining = QUIZ_PENDING_ANOTHER_TTL_SECONDS - age
                if remaining > 0:
                    await asyncio.sleep(remaining)

            pending = QUIZ_PENDING_ANOTHER.get(channel_id)
            if not pending:
                return

            created_at = pending.get("created_at")
            if created_at:
                age = (datetime.datetime.now(datetime.timezone.utc) - created_at).total_seconds()
                if age <= QUIZ_PENDING_ANOTHER_TTL_SECONDS:
                    return

            expired_state = QUIZ_PENDING_ANOTHER.pop(channel_id, None)
            if not expired_state:
                return

            expiry_text = _quiz_timeout_expiry_message(expired_state)
            try:
                await channel.send(expiry_text)
            except Exception as send_error:
                print(f"[quiz] pending-expiry send error: {send_error}", flush=True)
        except asyncio.CancelledError:
            return
        finally:
            tracked_task = QUIZ_PENDING_ANOTHER_TIMEOUT_TASKS.get(channel_id)
            if tracked_task is asyncio.current_task():
                QUIZ_PENDING_ANOTHER_TIMEOUT_TASKS.pop(channel_id, None)

    QUIZ_PENDING_ANOTHER_TIMEOUT_TASKS[channel_id] = asyncio.create_task(_timeout_worker())


def _quiz_pending_another_active(channel_id):
    pending = QUIZ_PENDING_ANOTHER.get(channel_id)
    if not pending:
        return False
    created_at = pending.get("created_at")
    if not created_at:
        QUIZ_PENDING_ANOTHER.pop(channel_id, None)
        _quiz_cancel_pending_another_timeout(channel_id)
        return False
    age = (datetime.datetime.now(datetime.timezone.utc) - created_at).total_seconds()
    if age > QUIZ_PENDING_ANOTHER_TTL_SECONDS:
        expired_state = QUIZ_PENDING_ANOTHER.pop(channel_id, None)
        _quiz_cancel_pending_another_timeout(channel_id)
        if expired_state:
            return False
        return False
    return True


def _quiz_pending_mode_active(channel_id):
    pending = QUIZ_PENDING_MODE.get(channel_id)
    if not pending:
        return False
    created_at = pending.get("created_at")
    if not created_at:
        QUIZ_PENDING_MODE.pop(channel_id, None)
        return False
    age = (datetime.datetime.now(datetime.timezone.utc) - created_at).total_seconds()
    if age > QUIZ_PENDING_MODE_TTL_SECONDS:
        QUIZ_PENDING_MODE.pop(channel_id, None)
        return False
    return True


def _quiz_answer_display(quiz):
    row = quiz["row"]
    char_key = quiz["char_key"]
    char_display = str(row.get("char_name", char_key.capitalize())).strip()
    move_name = str(row.get("moveName", "?")).strip()
    num_cmd = str(row.get("numCmd", "?")).strip()
    return char_display, move_name, num_cmd


def _quiz_owner_user_id(state):
    if not isinstance(state, dict):
        return None
    raw_owner = state.get("owner_user_id")
    try:
        return int(raw_owner)
    except Exception:
        return None


def _quiz_user_can_end(state, user_id):
    # Quiz ending is communal: any participant can end the session.
    return True


def _quiz_owner_only_end_message(state):
    owner_id = _quiz_owner_user_id(state)
    if owner_id is None:
        return "Only the user who started this quiz can end it."
    return f"Only <@{owner_id}> can end this quiz."


def _quiz_leaderboard_file_path():
    path_text = str(QUIZ_LEADERBOARD_FILE or "quiz_leaderboard.json").strip()
    if os.path.isabs(path_text):
        return path_text
    return os.path.join(os.path.dirname(__file__), path_text)


def load_quiz_leaderboard():
    """Load persistent global quiz leaderboard from disk."""
    global QUIZ_GLOBAL_LEADERBOARD, QUIZ_GLOBAL_LEADERBOARD_NAMES

    file_path = _quiz_leaderboard_file_path()
    if not os.path.exists(file_path):
        QUIZ_GLOBAL_LEADERBOARD = {}
        QUIZ_GLOBAL_LEADERBOARD_NAMES = {}
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        print(f"[quiz] leaderboard load error: {e}", flush=True)
        QUIZ_GLOBAL_LEADERBOARD = {}
        QUIZ_GLOBAL_LEADERBOARD_NAMES = {}
        return

    if not isinstance(payload, dict):
        print("[quiz] leaderboard load warning: payload is not an object", flush=True)
        QUIZ_GLOBAL_LEADERBOARD = {}
        QUIZ_GLOBAL_LEADERBOARD_NAMES = {}
        return

    loaded_scores = {}
    loaded_names = {}
    for raw_uid, raw_pts in dict(payload.get("scores") or {}).items():
        try:
            uid = int(raw_uid)
            pts = int(raw_pts)
        except Exception:
            continue
        if pts < 0:
            continue
        loaded_scores[uid] = pts

    for raw_uid, raw_name in dict(payload.get("score_names") or {}).items():
        try:
            uid = int(raw_uid)
        except Exception:
            continue
        loaded_names[uid] = _quiz_clean_display_name(raw_name)

    for uid in loaded_scores.keys():
        if uid not in loaded_names:
            loaded_names[uid] = _quiz_clean_display_name(f"User {uid}")

    QUIZ_GLOBAL_LEADERBOARD = loaded_scores
    QUIZ_GLOBAL_LEADERBOARD_NAMES = loaded_names


def save_quiz_leaderboard():
    """Persist global quiz leaderboard to disk."""
    file_path = _quiz_leaderboard_file_path()
    payload = {
        "version": 1,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "scores": {str(uid): int(points) for uid, points in QUIZ_GLOBAL_LEADERBOARD.items()},
        "score_names": {
            str(uid): _quiz_clean_display_name(name)
            for uid, name in QUIZ_GLOBAL_LEADERBOARD_NAMES.items()
        },
    }

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=True, indent=2, sort_keys=True)
    except Exception as e:
        print(f"[quiz] leaderboard save error: {e}", flush=True)


def _quiz_extract_leaderboard_top_limit(text, default=10, maximum=25):
    match = QUIZ_LEADERBOARD_TOP_RE.search(str(text or ""))
    if not match:
        return default
    try:
        parsed = int(match.group(1))
    except Exception:
        return default
    return max(1, min(maximum, parsed))


def _quiz_is_leaderboard_request(text):
    return bool(QUIZ_LEADERBOARD_REQUEST_RE.search(str(text or "")))


def _quiz_format_global_leaderboard_reply(limit=10):
    scores = dict(QUIZ_GLOBAL_LEADERBOARD)
    names = dict(QUIZ_GLOBAL_LEADERBOARD_NAMES)
    if not scores:
        return "No global quiz wins recorded yet. Win one round and claim your first point."

    sorted_items = sorted(
        scores.items(),
        key=lambda item: (
            -int(item[1]),
            _quiz_clean_display_name(names.get(item[0], f"User {item[0]}")).lower(),
        ),
    )
    top_items = sorted_items[: max(1, int(limit))]
    top_scores = {uid: pts for uid, pts in top_items}
    score_block = _format_quiz_scores(top_scores, names)
    top_uid, top_points = top_items[0]
    top_name = _quiz_clean_display_name(names.get(top_uid, f"User {top_uid}"))
    return (
        f"Global Quiz Leaderboard (Top {len(top_items)}):\n"
        f"{score_block}\n"
        f"Top scorer right now: {top_name} with {top_points} point{'s' if int(top_points) != 1 else ''}."
    )


async def _quiz_record_global_win(user_id, display_name, points=1):
    """Record lifetime quiz points for a user and persist leaderboard."""
    try:
        uid = int(user_id)
        delta = int(points)
    except Exception:
        return
    if delta <= 0:
        return

    async with QUIZ_LEADERBOARD_LOCK:
        current_points = int(QUIZ_GLOBAL_LEADERBOARD.get(uid, 0))
        QUIZ_GLOBAL_LEADERBOARD[uid] = current_points + delta
        QUIZ_GLOBAL_LEADERBOARD_NAMES[uid] = _quiz_clean_display_name(display_name)
        save_quiz_leaderboard()


async def handle_quiz_post_answer_choice(message):
    """Handle follow-up choice after a wrong guess prompt."""
    channel_id = message.channel.id
    quiz = ACTIVE_QUIZZES.get(channel_id)
    if not quiz or not quiz.get("awaiting_choice"):
        return False

    text = strip_discord_mentions(message.content or "").strip().lower()
    if not text:
        return False

    wants_guess_again = bool(QUIZ_GUESS_AGAIN_RE.search(text))
    wants_reveal = bool(QUIZ_REVEAL_END_RE.search(text))

    if not wants_guess_again and not wants_reveal:
        inferred_intent = await classify_quiz_post_answer_choice_intent(message.channel, text)
        if inferred_intent == "guess_again":
            wants_guess_again = True
        elif inferred_intent == "reveal":
            wants_reveal = True

    if wants_guess_again:
        quiz["awaiting_choice"] = False
        try:
            sent = await message.reply("Guess again.")
            _quiz_track_message_id(quiz, getattr(sent, "id", None))
        except Exception as e:
            if is_deleted_message_reference_error(e):
                sent = await message.channel.send("Guess again.")
                _quiz_track_message_id(quiz, getattr(sent, "id", None))
            else:
                print(f"[quiz] guess-again reply error: {e}", flush=True)
        return True

    if wants_reveal:
        if not _quiz_user_can_end(quiz, message.author.id):
            deny_text = _quiz_owner_only_end_message(quiz)
            try:
                sent = await message.reply(deny_text)
                _quiz_track_message_id(quiz, getattr(sent, "id", None))
            except Exception as e:
                if is_deleted_message_reference_error(e):
                    sent = await message.channel.send(deny_text)
                    _quiz_track_message_id(quiz, getattr(sent, "id", None))
                else:
                    print(f"[quiz] owner-only reveal reply error: {e}", flush=True)
            return True

        ACTIVE_QUIZZES.pop(channel_id, None)
        _quiz_cancel_active_timeout(channel_id)
        char_display, move_name, num_cmd = _quiz_answer_display(quiz)
        score_text = _format_quiz_scores(
            dict(quiz.get("scores") or {}),
            dict(quiz.get("score_names") or {}),
        )
        reply_text = (
            f"The answer was **{char_display}'s {move_name} ({num_cmd})**.\n"
            f"{score_text}\n"
            "Would you like another question?"
        )
        try:
            sent = await message.reply(reply_text)
            QUIZ_PENDING_ANOTHER[channel_id] = {
                "created_at": datetime.datetime.now(datetime.timezone.utc),
                "message_id": getattr(sent, "id", None),
                "mode": quiz.get("mode", "hard"),
                "owner_user_id": quiz.get("owner_user_id"),
                "scores": dict(quiz.get("scores") or {}),
                "score_names": dict(quiz.get("score_names") or {}),
                "round": quiz.get("round", 1),
                "message_ids": _quiz_build_message_history(quiz, getattr(sent, "id", None)),
            }
            _quiz_schedule_pending_another_timeout(channel_id, message.channel)
        except Exception as e:
            if is_deleted_message_reference_error(e):
                sent = await message.channel.send(reply_text)
                QUIZ_PENDING_ANOTHER[channel_id] = {
                    "created_at": datetime.datetime.now(datetime.timezone.utc),
                    "message_id": getattr(sent, "id", None),
                    "mode": quiz.get("mode", "hard"),
                    "owner_user_id": quiz.get("owner_user_id"),
                    "scores": dict(quiz.get("scores") or {}),
                    "score_names": dict(quiz.get("score_names") or {}),
                    "round": quiz.get("round", 1),
                    "message_ids": _quiz_build_message_history(quiz, getattr(sent, "id", None)),
                }
                _quiz_schedule_pending_another_timeout(channel_id, message.channel)
            else:
                print(f"[quiz] reveal-end reply error: {e}", flush=True)
        return True

    return False


async def handle_quiz_answer(message):
    """
    Process a message as a potential quiz answer.
    Returns True if message was handled as a quiz answer attempt.
    Returns False when message is not a usable answer format.
    """
    channel_id = message.channel.id
    quiz = ACTIVE_QUIZZES.get(channel_id)
    if not quiz or quiz.get("answered"):
        return False

    text = strip_discord_mentions(message.content or "").strip().lower()
    if not text:
        return False

    parsed_char, parsed_move = _extract_char_and_move_from_text(text)
    if not parsed_char or not parsed_move:
        return False

    if not check_quiz_answer(quiz, text):
        quiz["awaiting_choice"] = True
        thinking_message = await _quiz_send_thinking_message(message)
        wrong_reply = await build_quiz_wrong_guess_message(
            message.channel,
            sanitize_ascii_line,
            _quiz_intro_has_specific_answer_hint,
        )
        wrong_followup = "Try again or give up and find out the answer"
        wrong_text = f"{wrong_reply}\n{wrong_followup}" if wrong_reply else wrong_followup
        sent = await _quiz_publish_from_placeholder(
            message.channel,
            thinking_message,
            wrong_text,
        )
        _quiz_track_message_id(quiz, getattr(sent, "id", None))
        return True

    scores = quiz.setdefault("scores", {})
    score_names = quiz.setdefault("score_names", {})
    winner_id = int(message.author.id)
    winner_name = _quiz_user_display_name(message.author)
    winner_points = int(scores.get(winner_id, 0)) + 1
    scores[winner_id] = winner_points
    score_names[winner_id] = winner_name
    await _quiz_record_global_win(winner_id, winner_name, points=1)

    ACTIVE_QUIZZES.pop(channel_id, None)
    _quiz_cancel_active_timeout(channel_id)
    thinking_message = await _quiz_send_thinking_message(message)
    char_display, move_name, num_cmd = _quiz_answer_display(quiz)
    correct_reply = await build_quiz_correct_guess_message(message.channel, sanitize_ascii_line)
    score_text = _format_quiz_scores(dict(scores), dict(score_names))
    result_lines = [correct_reply, score_text]
    result_lines.append(f"The answer was **{char_display}'s {move_name} ({num_cmd})**.")
    result_lines.append("Would you like another question?")
    result_text = "\n".join(result_lines)
    sent = await _quiz_publish_from_placeholder(
        message.channel,
        thinking_message,
        result_text,
    )
    if sent is None:
        print("[quiz] correct-reply send failed", flush=True)
        return True

    QUIZ_PENDING_ANOTHER[channel_id] = {
        "created_at": datetime.datetime.now(datetime.timezone.utc),
        "message_id": getattr(sent, "id", None),
        "mode": quiz.get("mode", "hard"),
        "owner_user_id": quiz.get("owner_user_id"),
        "scores": dict(scores),
        "score_names": dict(score_names),
        "round": quiz.get("round", 1),
        "message_ids": _quiz_build_message_history(quiz, getattr(sent, "id", None)),
    }
    _quiz_schedule_pending_another_timeout(channel_id, message.channel)

    return True


# ==================== END QUIZ FEATURE ====================

async def route_message(client, message, content_lower):
    # Quiz flow
    channel_id = message.channel.id
    in_quiz = channel_id in ACTIVE_QUIZZES
    quiz_state = ACTIVE_QUIZZES.get(channel_id)
    requested_quiz_mode = _quiz_extract_mode_from_text(content_lower)
    answer_is_addressed = client.user.mentioned_in(message) or _is_reply_to_quiz_msg(message)
    mode_prompt_reply = _is_reply_to_quiz_mode_prompt(message)
    command_is_addressed = (
        client.user.mentioned_in(message)
        or _is_reply_to_quiz_followup_msg(message)
        or mode_prompt_reply
    )

    if command_is_addressed and _quiz_is_leaderboard_request(content_lower):
        top_limit = _quiz_extract_leaderboard_top_limit(content_lower)
        leaderboard_reply = _quiz_format_global_leaderboard_reply(limit=top_limit)
        try:
            await message.reply(leaderboard_reply)
        except Exception as e:
            if is_deleted_message_reference_error(e):
                await message.channel.send(leaderboard_reply)
            else:
                print(f"[quiz] leaderboard reply error: {e}", flush=True)
        return

    # Follow-up after ending a quiz
    if (
        not in_quiz
        and _quiz_pending_another_active(channel_id)
        and command_is_addressed
    ):
        pending = QUIZ_PENDING_ANOTHER.get(channel_id, {})
        pending_scores = dict(pending.get("scores") or {})
        pending_score_names = dict(pending.get("score_names") or {})
        pending_owner_user_id = pending.get("owner_user_id")
        pending_message_ids = list(pending.get("message_ids") or [])
        try:
            next_round = max(1, int(pending.get("round", 1))) + 1
        except Exception:
            next_round = 2

        wants_another_no = bool(QUIZ_ANOTHER_NO_RE.search(content_lower))
        wants_another_yes = bool(QUIZ_ANOTHER_YES_RE.search(content_lower))

        if not wants_another_no and not wants_another_yes:
            inferred_followup_intent = await classify_quiz_another_question_intent(message.channel, content_lower)
            if inferred_followup_intent == "no":
                wants_another_no = True
            elif inferred_followup_intent == "yes":
                wants_another_yes = True

        if wants_another_no:
            if not _quiz_user_can_end(pending, message.author.id):
                deny_text = _quiz_owner_only_end_message(pending)
                try:
                    await message.reply(deny_text)
                except Exception as e:
                    if is_deleted_message_reference_error(e):
                        await message.channel.send(deny_text)
                    else:
                        print(f"[quiz] owner-only pending-end reply error: {e}", flush=True)
                return

            QUIZ_PENDING_ANOTHER.pop(channel_id, None)
            _quiz_cancel_pending_another_timeout(channel_id)
            QUIZ_PENDING_MODE.pop(channel_id, None)
            thinking_message = await _quiz_send_thinking_message(message)
            crown_line = _quiz_build_crown_line(pending_scores, pending_score_names)
            score_text = _format_quiz_scores(pending_scores, pending_score_names)
            decline_reply = await build_quiz_decline_message(message.channel, sanitize_ascii_line)
            final_reply = f"{crown_line}\n{score_text}\n{decline_reply}"
            await _quiz_publish_from_placeholder(
                message.channel,
                thinking_message,
                final_reply,
            )
            return

        if command_is_addressed and requested_quiz_mode in QUIZ_VALID_MODES:
            QUIZ_PENDING_ANOTHER.pop(channel_id, None)
            _quiz_cancel_pending_another_timeout(channel_id)
            await start_quiz(
                message,
                mode=requested_quiz_mode,
                session_scores=pending_scores,
                session_score_names=pending_score_names,
                session_round=next_round,
                session_owner_user_id=pending_owner_user_id,
                session_message_ids=pending_message_ids,
            )
            return

        if command_is_addressed and (wants_another_yes or QUIZ_INTENT_RE.search(content_lower)):
            followup_mode = str(requested_quiz_mode or pending.get("mode") or "").strip().lower()
            QUIZ_PENDING_ANOTHER.pop(channel_id, None)
            _quiz_cancel_pending_another_timeout(channel_id)
            if followup_mode not in QUIZ_VALID_MODES:
                await prompt_quiz_mode_selection(
                    message,
                    session_mode=pending.get("mode"),
                    session_scores=pending_scores,
                    session_score_names=pending_score_names,
                    session_round=next_round,
                    session_owner_user_id=pending_owner_user_id,
                    session_message_ids=pending_message_ids,
                )
                return
            await start_quiz(
                message,
                mode=followup_mode,
                session_scores=pending_scores,
                session_score_names=pending_score_names,
                session_round=next_round,
                session_owner_user_id=pending_owner_user_id,
                session_message_ids=pending_message_ids,
            )
            return

    # Pending difficulty selection
    if not in_quiz and _quiz_pending_mode_active(channel_id):
        pending_mode = QUIZ_PENDING_MODE.get(channel_id, {})
        pending_mode_scores = dict(pending_mode.get("scores") or {})
        pending_mode_score_names = dict(pending_mode.get("score_names") or {})
        pending_mode_round = pending_mode.get("round", 1)
        pending_mode_owner_user_id = pending_mode.get("owner_user_id")
        pending_mode_message_ids = list(pending_mode.get("message_ids") or [])

        if command_is_addressed and requested_quiz_mode in QUIZ_VALID_MODES:
            QUIZ_PENDING_MODE.pop(channel_id, None)
            await start_quiz(
                message,
                mode=requested_quiz_mode,
                session_scores=pending_mode_scores,
                session_score_names=pending_mode_score_names,
                session_round=pending_mode_round,
                session_owner_user_id=pending_mode_owner_user_id,
                session_message_ids=pending_mode_message_ids,
            )
            return

        if command_is_addressed:
            if re.search(r'\b(stop|end|quit|cancel)\b', content_lower):
                if not _quiz_user_can_end(pending_mode, message.author.id):
                    deny_text = _quiz_owner_only_end_message(pending_mode)
                    try:
                        await message.reply(deny_text)
                    except Exception as e:
                        if is_deleted_message_reference_error(e):
                            await message.channel.send(deny_text)
                        else:
                            print(f"[quiz] owner-only mode-cancel reply error: {e}", flush=True)
                    return

                QUIZ_PENDING_MODE.pop(channel_id, None)
                try:
                    await message.reply("Quiz setup cancelled.")
                except Exception as e:
                    if is_deleted_message_reference_error(e):
                        await message.channel.send("Quiz setup cancelled.")
                    else:
                        print(f"[quiz] mode-cancel reply error: {e}", flush=True)
                return

            if mode_prompt_reply or QUIZ_INTENT_RE.search(content_lower):
                await prompt_quiz_mode_selection(
                    message,
                    session_mode=pending_mode.get("mode"),
                    session_scores=pending_mode_scores,
                    session_score_names=pending_mode_score_names,
                    session_round=pending_mode_round,
                    session_owner_user_id=pending_mode_owner_user_id,
                    session_message_ids=pending_mode_message_ids,
                )
                return

    # Active quiz interactions (answer attempts require mention or reply)
    if in_quiz and answer_is_addressed:
        if re.search(r'\b(stop|end|quit|cancel)\b', content_lower):
            if not _quiz_user_can_end(quiz_state, message.author.id):
                deny_text = _quiz_owner_only_end_message(quiz_state)
                try:
                    sent = await message.reply(deny_text)
                    _quiz_track_message_id(quiz_state, getattr(sent, "id", None))
                except Exception as e:
                    if is_deleted_message_reference_error(e):
                        sent = await message.channel.send(deny_text)
                        _quiz_track_message_id(quiz_state, getattr(sent, "id", None))
                    else:
                        print(f"[quiz] owner-only stop reply error: {e}", flush=True)
                return

            await stop_quiz(message)
            return

        if quiz_state and not quiz_state.get("awaiting_choice") and QUIZ_FORFEIT_RE.search(content_lower):
            if not _quiz_user_can_end(quiz_state, message.author.id):
                deny_text = _quiz_owner_only_end_message(quiz_state)
                try:
                    sent = await message.reply(deny_text)
                    _quiz_track_message_id(quiz_state, getattr(sent, "id", None))
                except Exception as e:
                    if is_deleted_message_reference_error(e):
                        sent = await message.channel.send(deny_text)
                        _quiz_track_message_id(quiz_state, getattr(sent, "id", None))
                    else:
                        print(f"[quiz] owner-only forfeit reply error: {e}", flush=True)
                return

            await stop_quiz(message)
            return

        if QUIZ_CHEAT_LOOKUP_RE.search(content_lower):
            cheat_reply = await build_quiz_cheating_warning_message(
                message.channel,
                sanitize_ascii_line,
                _quiz_intro_has_specific_answer_hint,
            )
            try:
                sent = await message.reply(cheat_reply)
                _quiz_track_message_id(quiz_state, getattr(sent, "id", None))
            except Exception as e:
                if is_deleted_message_reference_error(e):
                    sent = await message.channel.send(cheat_reply)
                    _quiz_track_message_id(quiz_state, getattr(sent, "id", None))
                else:
                    print(f"[quiz] cheating-warning reply error: {e}", flush=True)
            return

        if quiz_state and quiz_state.get("awaiting_choice"):
            if await handle_quiz_answer(message):
                return
            if await handle_quiz_post_answer_choice(message):
                return
            if not QUIZ_INTENT_RE.search(content_lower):
                return
        else:
            if not QUIZ_INTENT_RE.search(content_lower):
                if await handle_quiz_answer(message):
                    return
                return

    # Start or stop a single-question quiz
    if command_is_addressed and QUIZ_INTENT_RE.search(content_lower):
        if re.search(r'\b(stop|end|quit|cancel)\b', content_lower):
            if in_quiz and not _quiz_user_can_end(quiz_state, message.author.id):
                deny_text = _quiz_owner_only_end_message(quiz_state)
                try:
                    sent = await message.reply(deny_text)
                    _quiz_track_message_id(quiz_state, getattr(sent, "id", None))
                except Exception as e:
                    if is_deleted_message_reference_error(e):
                        sent = await message.channel.send(deny_text)
                        _quiz_track_message_id(quiz_state, getattr(sent, "id", None))
                    else:
                        print(f"[quiz] owner-only stop-command reply error: {e}", flush=True)
                return
            await stop_quiz(message)
        else:
            if requested_quiz_mode not in QUIZ_VALID_MODES:
                await prompt_quiz_mode_selection(message)
            else:
                await start_quiz(message, mode=requested_quiz_mode)
        return
    return False

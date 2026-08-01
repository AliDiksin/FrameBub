"""Quiz answer matching and session score formatting."""

import difflib
import re


def bind(**values):
    globals().update(values)
# Answer matching: numcmd variants, move names, fuzzy recovery
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
        "l",
        "m",
        "h",
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


def _extract_char_and_move_from_text(text, game="sf6"):
    """
    Try to parse (char_key, move_text) from a user answer string.
    Tries progressively longer word prefixes for the character name.
    Returns (char_key, move_text) or (None, None).
    """
    words = text.strip().lower().split()
    if not words:
        return None, None
    for prefix_len in range(min(4, len(words)), 0, -1):
        char_candidate = " ".join(words[:prefix_len])
        char_key = _quiz_game_resolve_character(game, char_candidate)
        if char_key:
            move_text = " ".join(words[prefix_len:]).strip()
            return char_key, move_text
    return None, None


def _quiz_lookup_frame_data(game, char_key, move_text):
    lookup_fn = _quiz_game_config(game).get("lookup_frame_data")
    if callable(lookup_fn):
        return lookup_fn(char_key, move_text)
    return None


def _quiz_find_moves_in_text(game, text):
    find_fn = _quiz_game_config(game).get("find_moves_in_text")
    if callable(find_fn):
        return find_fn(text)
    return {"rows": []}


def _quiz_candidate_rows_for_answer(game, char_key, move_text):
    candidates = []
    direct_row = _quiz_lookup_frame_data(game, char_key, move_text)
    if direct_row is not None:
        candidates.append(direct_row)

    parser_payload = _quiz_find_moves_in_text(game, _quiz_parser_query(game, char_key, move_text))
    if not parser_payload.get("quiz_answer_too_broad"):
        for row in parser_payload.get("rows", []) or []:
            row_char = str(row.get("char_key", "") or "").strip().lower()
            if not row_char:
                row_char = _quiz_game_resolve_character(game, str(row.get("char_name", ""))) or ""
            if row_char and row_char != char_key:
                continue
            if row not in candidates:
                candidates.append(row)

    normalized_move = _normalize_quiz_name(move_text)
    normalized_cmd = _normalize_quiz_numcmd(move_text)
    for row in _quiz_rows_for_char(game, char_key):
        row_names = {
            _normalize_quiz_name(row.get("moveName", "")),
            _normalize_quiz_name(row.get("cmnName", "")),
            _normalize_quiz_name(row.get("numCmd", "")),
        }
        if normalized_move and normalized_move in row_names:
            if row not in candidates:
                candidates.append(row)
            continue
        if normalized_cmd and _quiz_row_numcmd_matches_correct(row, normalized_cmd, allow_generic=False):
            if row not in candidates:
                candidates.append(row)
    return candidates


def _check_quiz_answer_generic(quiz_state, text):
    game = _quiz_game_key(quiz_state.get("game", "sf6"))
    correct_char = quiz_state["char_key"]
    correct_numcmd = quiz_state["numcmd"]
    correct_row = quiz_state.get("row") or {}
    char_key, move_text = _extract_char_and_move_from_text(text, game=game)
    if not char_key or not move_text or char_key != correct_char:
        return False

    user_move_compact = _normalize_quiz_numcmd(move_text)
    if user_move_compact and _quiz_row_numcmd_matches_correct({"numCmd": user_move_compact}, correct_numcmd, allow_generic=False):
        return True

    for row in _quiz_candidate_rows_for_answer(game, char_key, move_text):
        if _quiz_rows_match(row, correct_row, correct_numcmd, allow_generic=False):
            return True

    user_move_name = str(move_text or "").strip().lower()
    if not user_move_name:
        return False
    fuzzy_name_candidates = []
    for row in _quiz_rows_for_char(game, char_key):
        if not _quiz_row_has_data(row):
            continue
        if not _quiz_row_allowed_for_mode(row, quiz_state.get("mode", "hard"), game=game):
            continue
        for candidate_name in (str(row.get("moveName", "")).strip().lower(), str(row.get("cmnName", "")).strip().lower()):
            if len(candidate_name) >= 4:
                fuzzy_name_candidates.append((candidate_name, row))
    close_names = difflib.get_close_matches(user_move_name, [name for name, _row in fuzzy_name_candidates], n=2, cutoff=0.84)
    for close_name in close_names:
        for candidate_name, row in fuzzy_name_candidates:
            if candidate_name == close_name and _quiz_rows_match(row, correct_row, correct_numcmd, allow_generic=False):
                return True
    return False


def check_quiz_answer(quiz_state, text):
    """
    Return True if `text` is a correct answer to the active quiz round.
    Checks character match, then uses lookup_frame_data to match the move.
    """
    game = _quiz_game_key(quiz_state.get("game", "sf6"))
    if game != "sf6":
        return _check_quiz_answer_generic(quiz_state, text)

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

    char_key, move_text = _extract_char_and_move_from_text(text, game=game)
    if not char_key or not move_text:
        return False
    if char_key != correct_char:
        return False

    correct_level_match = re.search(
        r"\b(?:lvl|level)\s*([23])\b",
        " ".join(
            str(correct_row.get(field, "")).lower()
            for field in ("moveName", "cmnName", "numCmd")
        ),
    )
    user_level_match = re.search(r"\b(?:lvl|level)\s*([23])\b", move_text.lower())
    if correct_level_match and user_level_match and correct_level_match.group(1) != user_level_match.group(1):
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


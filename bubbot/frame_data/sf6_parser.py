"""SF6 natural-language frame/gif query orchestration. Character-specific rules live in sf6_* helper modules."""

import re
from bubbot.utils.parser_results import parser_result

from bubbot.frame_data.sf6_character_aliases import (
    apply_character_specific_result_filters,
    collect_character_specific_rows,
    expand_character_candidate_names,
    infer_character_mentions_from_terms,
    jamie_drink_level_from_text,
    query_requires_character_variant_state,
    row_matches_character_variant_state,
    should_append_single_token_candidate,
    should_skip_keyword_input,
)
from bubbot.frame_data.sf6_character_stats import apply_stats_context
from bubbot.frame_data.sf6_parser_helpers import (
    apply_explicit_strength_result_filter as shared_apply_explicit_strength_result_filter,
    query_has_directional_normal_notation,
    query_has_grounded_normal_notation,
    query_mentions_fireball_terms as shared_query_mentions_fireball_terms,
    query_requests_super_art as shared_query_requests_super_art,
    query_requires_stocked as shared_query_requires_stocked,
    row_is_air_move as shared_row_is_air_move,
    row_is_ca_variant as shared_row_is_ca_variant,
    row_is_charged_variant as shared_row_is_charged_variant,
    row_is_od_variant as shared_row_is_od_variant,
    row_is_stocked_variant as shared_row_is_stocked_variant,
    row_matches_explicit_strength as shared_row_matches_explicit_strength,
    row_matches_requested_level as shared_row_matches_requested_level,
    normalize_button_word_notation,
)
from bubbot.frame_data.sf6_special_prompt_rules import (
    should_skip_ambiguous_special_key,
)
from bubbot.frame_data.sf6_parser_candidates import collect_sf6_candidates
from bubbot.frame_data.sf6_parser_output import format_sf6_rows
from bubbot.frame_data.sf6_parser_postprocess import (
    filter_and_inject_key_moves,
    is_missing_scrolls_query,
)



def find_moves_in_text(deps, text):
    CHARACTER_ALIASES = deps["CHARACTER_ALIASES"]
    FRAME_DATA = deps["FRAME_DATA"]
    FRAME_STATS = deps["FRAME_STATS"]
    strip_discord_mentions = deps["strip_discord_mentions"]
    normalize_jump_normal_text = deps["normalize_jump_normal_text"]
    word_tokens = deps["word_tokens"]
    contains_token_sequence = deps["contains_token_sequence"]
    has_explicit_gif_lookup_intent = deps["has_explicit_gif_lookup_intent"]
    lookup_frame_data = deps["lookup_frame_data"]
    normalize_char_name = deps["normalize_char_name"]
    resolve_character_key = deps["resolve_character_key"]
    normalize_num_cmd_token = deps["normalize_num_cmd_token"]
    is_missing_attack_range_value = deps["is_missing_attack_range_value"]
    get_attack_range_details = deps["get_attack_range_details"]
    format_attack_range_for_table = deps["format_attack_range_for_table"]
    format_frame_data = deps["format_frame_data"]
    check_punish = deps["check_punish"]
    row_is_charged_variant = shared_row_is_charged_variant
    row_is_od_variant = shared_row_is_od_variant
    row_is_ca_variant = shared_row_is_ca_variant
    row_is_stocked_variant = shared_row_is_stocked_variant
    row_is_air_move = shared_row_is_air_move
    """Extract character/move mentions and return context payload with mode."""
    found_data = []
    text_lower = strip_discord_mentions(text).lower()
    text_lower = normalize_jump_normal_text(text_lower)
    text_lower = normalize_button_word_notation(text_lower)
    text_lower = re.sub(r"\bdivekick\b", "dive kick", text_lower)

    tc_prompt_blocks = []
    special_prompt_blocks = []
    allow_explicit_special_prompt = False
    tc_ambiguous_inputs = set()
    text_tokens = word_tokens(text_lower)

    def tokens_in_haystack(haystack_tokens, needle_tokens):
        return contains_token_sequence(haystack_tokens, needle_tokens)

    def tokens_in_text(needle_tokens):
        return tokens_in_haystack(text_tokens, needle_tokens)

    # 1. Identify which characters are mentioned
    mentioned_chars = []

    # First check for character aliases and normalize them
    for alias, canonical in CHARACTER_ALIASES.items():
        alias_tokens = word_tokens(alias)
        if tokens_in_text(alias_tokens):
            if canonical in FRAME_DATA and canonical not in mentioned_chars:
                mentioned_chars.append(canonical)

    # Then check for direct character name matches
    for char in FRAME_DATA.keys():
        char_tokens = word_tokens(char)
        if tokens_in_text(char_tokens) and char not in mentioned_chars:
            mentioned_chars.append(char)

    infer_character_mentions_from_terms(text_lower, FRAME_DATA, mentioned_chars)
    jamie_drink_level = jamie_drink_level_from_text(text_lower) if "jamie" in mentioned_chars else None

    frame_keywords = [
        "frame data",
        "framedata",
        "startup",
        "start up",
        "recovery",
        "active",
        "on block",
        "on hit",
        "hitstun",
        "blockstun",
        "frames",
    ]
    gif_query = has_explicit_gif_lookup_intent(text_lower)
    air_throw_move_query = bool(
        re.search(r"\b(?:air|aerial)\s+throw\b", text_lower)
        or re.search(r"\bairthrows?\b", text_lower)
    )
    jump_normal_move_query = bool(
        re.search(r"\b[789][lmh][pk]\b", text_lower)
        or re.search(r"\bj\.?[789]?[lmh][pk]\b", text_lower)
        or re.search(r"\b(?:neutral|n)\s+j(?:ump)?\s*\.?\s*[lmh][pk]\b", text_lower)
        or re.search(r"\bjump\s+[lmh][pk]\b", text_lower)
    )
    directional_normal_move_query = query_has_directional_normal_notation(text_lower)
    grounded_normal_move_query = query_has_grounded_normal_notation(text_lower)
    startup_alias_query = bool(
        re.search(r"\bhow\s+fast\b", text_lower)
        or re.search(r"\bhow\s+quick\b", text_lower)
        or re.search(r"\bspeed\s+of\b", text_lower)
        or (
            re.search(r"\bfast\b", text_lower)
            and re.search(r"\b[1-9][0-9]*[a-zA-Z]{1,3}\b", text_lower)
        )
    )
    hitconfirm_alias_query = bool(
        re.search(r"\bhit\s*-?\s*confirm\b", text_lower)
        or re.search(r"\bhitconfirm\b", text_lower)
        or re.search(r"\bhc\b", text_lower)
        or re.search(r"\bconfirm\s+window\b", text_lower)
        or re.search(r"\bconfirm\s+timing\b", text_lower)
        or re.search(r"\bconfirmable\b", text_lower)
        or re.search(r"\bconfirm\b", text_lower)
    )
    super_gain_alias_query = bool(
        re.search(r"\bsuper\s*gain\b", text_lower)
        or re.search(r"\bsuper\s*meter\s*gain\b", text_lower)
        or re.search(r"\bmeter\s*gain\b", text_lower)
        or re.search(r"\bsuper\s*build\b", text_lower)
        or re.search(r"\bsa\s*gain\b", text_lower)
    )
    range_alias_query = bool(
        (
            re.search(r"\brange\b", text_lower)
            or re.search(r"\blength\b", text_lower)
        )
        and not re.search(r"\bin\s+range\b", text_lower)
    )
    property_alias_flags = {
        "startup": startup_alias_query
        or bool(re.search(r"\bstart\s*up\b|\bstartup\b", text_lower)),
        "active": bool(re.search(r"\bactive\b|\bactive\s+frames?\b", text_lower)),
        "recovery": bool(re.search(r"\brecovery\b", text_lower)),
        "total": bool(re.search(r"\btotal(?:\s+frames?)?\b", text_lower)),
        "on_hit": bool(re.search(r"\bon\s+hit\b", text_lower)),
        "on_block": bool(re.search(r"\bon\s+block\b|\bplus\s+on\s+block\b|\bminus\s+on\s+block\b", text_lower)),
        "cancel": bool(re.search(r"\bcancel(?:l?able)?\b", text_lower)),
        "damage": bool(re.search(r"\bdamage\b|\bdmg\b", text_lower)),
        "guard": bool(re.search(r"\bguard\b|\battack\s+level\b|\batk\s*lvl\b|\batk\s*level\b", text_lower)),
        "chip_damage": bool(re.search(r"\bchip\s+damage\b", text_lower)),
        "drive_damage": bool(re.search(r"\bdrive\s+(?:chip|dmg|damage)\b", text_lower)),
        "stun": bool(re.search(r"\bhitstun\b|\bblockstun\b|\bstun\b", text_lower)),
        "invuln": bool(re.search(r"\binvuln(?:erability)?\b|\binvul\b", text_lower)),
        "hitconfirm": hitconfirm_alias_query,
        "super_gain": super_gain_alias_query,
        "range": range_alias_query,
        "frame_advantage": bool(re.search(r"\bframe\s+adv(?:antage)?\b", text_lower)),
        "counter_hit_adv": bool(
            re.search(r"\bcounter\s*hit\s+adv(?:antage)?\b", text_lower)
            or re.search(r"\bch\s*adv\b", text_lower)
        ),
        "counter_hit": bool(
            (
                re.search(r"\bcounter\s*hit\b", text_lower)
                and not re.search(r"\bcounter\s*hit\s+adv(?:antage)?\b", text_lower)
            )
            or (
                re.search(r"\bch\b", text_lower)
                and not re.search(r"\bch\s*adv\b", text_lower)
            )
        ),
        "punish_counter": bool(
            re.search(r"\bpunish\s*counter\b", text_lower)
            or re.search(r"\bpc\b", text_lower)
        ),
    }
    if property_alias_flags.get("damage") and (
        property_alias_flags.get("chip_damage") or property_alias_flags.get("drive_damage")
    ):
        property_alias_flags["damage"] = False
    property_match_count = sum(1 for matched in property_alias_flags.values() if matched)
    table_intent_query = bool(
        re.search(r"\ball\s+frames?\b", text_lower)
        or re.search(r"\bfull\s+frames?\b", text_lower)
        or re.search(r"\bfull\s+frame\s*data\b", text_lower)
        or re.search(r"\btable\b", text_lower)
    )
    property_only_query = bool(property_match_count == 1 and not table_intent_query)
    comparison_keywords = [
        "which is better",
        "which is faster",
        "compare",
        "comparison",
        "versus",
    ]
    punish_keywords = ["punish", "punishable", "can i punish", "is it punishable"]
    target_combo_query = bool(re.search(r"\b(tc|target\s+combo|targetcombo)\b", text_lower))
    special_grab_query = bool(re.search(r"\b(command\s+grab|spd|piledriver|typhoon)\b", text_lower))
    super_level_query = bool(
        re.search(
            r"\b(?:sa\s*[123]|super\s*art\s*(?:level\s*)?[123]|super\s*[123]|lv\s*[123]|lvl\s*[123]|level\s*[123])\b",
            text_lower,
        )
    )
    wants_comparison = (
        any(kw in text_lower for kw in comparison_keywords)
        or re.search(r"\bvs\b", text_lower)
        or (len(mentioned_chars) >= 2 and re.search(r"\band\b", text_lower))
    )
    wants_frame_data = (
        any(kw in text_lower for kw in frame_keywords)
        or any(kw in text_lower for kw in punish_keywords)
        or wants_comparison
        or startup_alias_query
        or hitconfirm_alias_query
        or super_gain_alias_query
        or range_alias_query
        or property_match_count > 0
        or target_combo_query
        or super_level_query
        or gif_query
        or air_throw_move_query
        or jump_normal_move_query
        or directional_normal_move_query
        or grounded_normal_move_query
    )
    results = []
    tc_selected_combos = set()
    tc_base_tokens = set()
    query_has_explicit_strength = False
    explicit_move_attempt = False
    missing_scrolls_query = False
    comparison_char_inputs = {}
    if wants_frame_data:
        # 2. Heuristic: For each mentioned character, search for moves mentioned nearby?
        # Simpler approach: Check if any move inputs are present in the text
        # that map to these characters.

        query_requires_variant_state = query_requires_character_variant_state(text_tokens)
        query_requires_charged = any(token in text_tokens for token in ("charged", "hold", "held"))
        query_requests_level2 = jamie_drink_level is None and bool(re.search(r"\b(?:lv|lvl|level)\s*2\b", text_lower))
        query_requests_level3 = jamie_drink_level is None and bool(re.search(r"\b(?:lv|lvl|level)\s*3\b", text_lower))

        query_requests_sa1 = shared_query_requests_super_art(text_lower, 1, jamie_drink_level)
        query_requests_sa2 = shared_query_requests_super_art(text_lower, 2, jamie_drink_level)
        query_requests_sa3 = shared_query_requests_super_art(text_lower, 3, jamie_drink_level)
        query_requests_ca = bool(re.search(r"\b(?:ca|critical\s+art)\b", text_lower))
        query_requires_stocked = shared_query_requires_stocked(text_tokens, text_lower)

        def apply_explicit_strength_result_filter(rows):
            return shared_apply_explicit_strength_result_filter(
                rows,
                query_has_explicit_strength=query_has_explicit_strength,
                query_wants_od_strength=query_wants_od_strength,
                query_wants_non_od_strength=query_wants_non_od_strength,
                text_lower=text_lower,
                row_is_od_variant=row_is_od_variant,
            )

        def row_matches_requested_level(row):
            return shared_row_matches_requested_level(
                row,
                query_requests_level2,
                query_requests_level3,
            )

        def query_mentions_fireball_terms():
            return shared_query_mentions_fireball_terms(text_lower)

        def row_matches_explicit_strength(row, strength_query_text):
            return shared_row_matches_explicit_strength(
                row,
                strength_query_text,
                row_is_od_variant,
            )

        def row_matches_query_move_terms(row):
            ignored_tokens = {
                "framedata", "frame", "frames", "data", "gif", "gifs", "hitbox", "hitboxes",
                "light", "medium", "heavy", "l", "m", "h",
                "lp", "mp", "hp", "lk", "mk", "hk", "pp", "kk",
                "od", "ex", "charged", "hold", "held",
                "startup", "active", "recovery", "range",
                "on", "hit", "block", "damage", "cancel",
                "super", "art", "level", "lvl", "lv",
                "sa1", "sa2", "sa3", "lv1", "lv2", "lv3", "lvl1", "lvl2", "lvl3",
            }
            if jamie_drink_level is not None:
                ignored_tokens.update({"drink", "drinks", f"dl{jamie_drink_level}"})
            for char in mentioned_chars:
                ignored_tokens.update(re.findall(r"[a-z0-9]+", str(char).lower()))
            for alias, canonical in CHARACTER_ALIASES.items():
                if canonical in mentioned_chars:
                    ignored_tokens.update(re.findall(r"[a-z0-9]+", str(alias).lower()))

            significant_tokens = [
                token for token in text_tokens
                if token not in ignored_tokens and len(token) >= 3
            ]
            if not significant_tokens:
                return True

            row_text = " ".join(
                str(row.get(field, "")).lower()
                for field in ("moveName", "cmnName", "numCmd", "plnCmd")
            )
            row_text_compact = re.sub(r"[^a-z0-9]", "", row_text)
            for token in significant_tokens:
                token_compact = re.sub(r"[^a-z0-9]", "", token)
                if not token_compact:
                    continue
                if token in row_text or token_compact in row_text_compact:
                    continue
                return False
            return True



        candidate_state = collect_sf6_candidates(locals())
        potential_inputs = candidate_state["potential_inputs"]
        extra_inputs = candidate_state["extra_inputs"]
        query_has_explicit_strength = candidate_state["query_has_explicit_strength"]
        query_wants_od_strength = candidate_state["query_wants_od_strength"]
        query_wants_non_od_strength = candidate_state["query_wants_non_od_strength"]
        filter_state = candidate_state["filter_state"]
        query_requests_air_context = candidate_state["query_requests_air_context"]
        air_fireball_context = candidate_state["air_fireball_context"]
        air_sa1_context = candidate_state["air_sa1_context"]
        air_sa2_context = candidate_state["air_sa2_context"]
        air_sa3_context = candidate_state["air_sa3_context"]
        air_tatsu_context = candidate_state["air_tatsu_context"]
        zangief_borscht_context = candidate_state["zangief_borscht_context"]
        alex_stance_followup_context = candidate_state["alex_stance_followup_context"]
        chun_stance_followup_context = candidate_state["chun_stance_followup_context"]
        ken_run_followup_context = candidate_state["ken_run_followup_context"]
        tc_selected_combos = candidate_state["tc_selected_combos"]
        tc_base_tokens = candidate_state["tc_base_tokens"]
        explicit_move_attempt = candidate_state["explicit_move_attempt"]
        is_special_motion_num_cmd = candidate_state["is_special_motion_num_cmd"]
        get_special_canonical_base_name = candidate_state["get_special_canonical_base_name"]
        allow_explicit_special_prompt = candidate_state["allow_explicit_special_prompt"]
        strength_prefix_re = candidate_state["strength_prefix_re"]
        text_compact = candidate_state["text_compact"]
        token_matches_move_name = candidate_state["token_matches_move_name"]
        motion_button_notation_present = candidate_state["motion_button_notation_present"]

        for char in mentioned_chars:
            char_data = FRAME_DATA[char]
            for row in char_data:
                for name_key in ["cmnName", "moveName"]:
                    raw_name = str(row.get(name_key, "")).lower().strip()
                    if not raw_name:
                        continue
                    candidate_names = [raw_name]
                    stripped_name = strength_prefix_re.sub("", raw_name).strip()
                    if (
                        stripped_name
                        and stripped_name != raw_name
                        and not query_has_explicit_strength
                    ):
                        candidate_names.append(stripped_name)
                    candidate_names = expand_character_candidate_names(char, candidate_names)
                    for candidate_name in candidate_names:
                        candidate_has_strength_prefix = bool(strength_prefix_re.match(candidate_name))
                        if query_has_explicit_strength and not candidate_has_strength_prefix:
                            continue
                        candidate_tokens = re.findall(r"[a-z0-9]+", candidate_name)
                        if not candidate_tokens:
                            continue
                        if len(candidate_tokens) < 2:
                            if should_append_single_token_candidate(char, candidate_tokens, text_tokens, text_lower):
                                if candidate_name not in potential_inputs:
                                    potential_inputs.append(candidate_name)
                            continue
                        candidate_compact = re.sub(r"[^a-z0-9]", "", candidate_name)
                        if (
                            len(candidate_compact) >= 6
                            and candidate_compact in text_compact
                        ):
                            if candidate_name not in potential_inputs:
                                potential_inputs.append(candidate_name)
                            continue
                        if all(
                            any(token_matches_move_name(name_tok, query_tok) for query_tok in text_tokens)
                            for name_tok in candidate_tokens
                        ):
                            if candidate_name not in potential_inputs:
                                potential_inputs.append(candidate_name)

        # also valid simple inputs: "mp", "hk" if preceded by char?

        for char in mentioned_chars:
            char_data = FRAME_DATA[char]

            # Check against potential inputs found via regex
            char_lookup_inputs = potential_inputs
            if comparison_char_inputs.get(char):
                char_lookup_inputs = comparison_char_inputs[char]
            for inp in char_lookup_inputs:
                row = lookup_frame_data(char, inp)
                if row and row not in results:
                    results.append(row)

            # Also check strict "frame data [char] [move]" remainder if exists
            # (This handles the specific verified cases)

            # "brute force" check for short inputs if the regex missed them (like "mp")
            # only if the string looks like "ryu mp"
            def is_button_part_of_dp_motion(button):
                return bool(
                    re.search(
                        rf"\b{re.escape(char)}\s+{button}\s*(?:\+)?\s*(?:dp|srk|shoryu|shoryuken)\b",
                        text_lower,
                    )
                )

            if not special_grab_query and not motion_button_notation_present:
                if f"{char} mp" in text_lower and not is_button_part_of_dp_motion("mp"):
                    row = lookup_frame_data(char, "mp")
                    if row and row not in results:
                        results.append(row)
                if f"{char} mk" in text_lower and not is_button_part_of_dp_motion("mk"):
                    row = lookup_frame_data(char, "mk")
                    if row and row not in results:
                        results.append(row)
                if f"{char} hp" in text_lower and not is_button_part_of_dp_motion("hp"):
                    row = lookup_frame_data(char, "hp")
                    if row and row not in results:
                        results.append(row)
                if f"{char} hk" in text_lower and not is_button_part_of_dp_motion("hk"):
                    row = lookup_frame_data(char, "hk")
                    if row and row not in results:
                        results.append(row)
                if f"{char} lp" in text_lower and not is_button_part_of_dp_motion("lp"):
                    row = lookup_frame_data(char, "lp")
                    if row and row not in results:
                        results.append(row)
                if f"{char} lk" in text_lower and not is_button_part_of_dp_motion("lk"):
                    row = lookup_frame_data(char, "lk")
                    if row and row not in results:
                        results.append(row)

        collect_character_specific_rows(
            text_lower,
            mentioned_chars,
            results,
            lookup_frame_data,
            query_has_explicit_strength=query_has_explicit_strength,
            zangief_borscht_context=zangief_borscht_context,
        )

        if special_grab_query and query_has_explicit_strength and not results and mentioned_chars:
            for char in mentioned_chars:
                grab_variants = []
                for row in FRAME_DATA.get(char, []):
                    cmn_name = str(row.get("cmnName", "")).lower()
                    if "command grab" in cmn_name or re.search(r"\bspd\b", cmn_name):
                        grab_variants.append(row)
                if len(grab_variants) >= 2:
                    variant_lines = "\n".join(
                        f"{index}. {row.get('moveName', '?')} ({row.get('numCmd', '?')})"
                        for index, row in enumerate(grab_variants, start=1)
                    )
                    special_prompt_blocks.append(
                        f"**Special Strength Options ({char.capitalize()})**\n"
                        f"Command Grab variants:\n{variant_lines}\n"
                        "Reply with the option number, or make a new prompt with the exact command or move name."
                    )

        if query_requires_variant_state and results:
            state_results = [row for row in results if row_matches_character_variant_state(row)]
            results = state_results

        if query_requires_charged and results:
            charged_results = [row for row in results if row_is_charged_variant(row)]
            if charged_results:
                results = charged_results
            else:
                upgraded_charged_results = []
                for row in results:
                    row_char_key = resolve_character_key(row.get("char_name", ""))
                    if not row_char_key:
                        continue

                    row_num_cmd_base = normalize_num_cmd_token(row.get("numCmd", ""))
                    if not row_num_cmd_base:
                        continue

                    charged_match = None
                    for candidate in FRAME_DATA.get(row_char_key, []):
                        if not row_is_charged_variant(candidate):
                            continue
                        candidate_base = normalize_num_cmd_token(candidate.get("numCmd", ""))
                        if candidate_base == row_num_cmd_base:
                            charged_match = candidate
                            break

                    if charged_match and charged_match not in upgraded_charged_results:
                        upgraded_charged_results.append(charged_match)

                if upgraded_charged_results:
                    results = upgraded_charged_results

        if mentioned_chars and "akuma" in mentioned_chars and query_mentions_fireball_terms():
            akuma_charged_fireballs = [
                row for row in FRAME_DATA.get("akuma", [])
                if get_special_canonical_base_name(row) == "fireball"
                and row_is_charged_variant(row)
                and not row_is_od_variant(row)
            ]
            if query_requests_level2 or query_requests_level3:
                level_results = [row for row in akuma_charged_fireballs if row_matches_requested_level(row)]
                if level_results:
                    results = level_results
            elif query_requires_charged and query_has_explicit_strength and not query_wants_od_strength and len(akuma_charged_fireballs) > 1:
                variant_lines = "\n".join(
                    f"{index}. {row.get('moveName', '?')} ({row.get('numCmd', '?')})"
                    for index, row in enumerate(akuma_charged_fireballs, start=1)
                )
                special_prompt_blocks.append(
                    "**Special Strength Options (Akuma)**\n"
                    f"Fireball variants:\n{variant_lines}\n"
                    "Reply with the option number, or make a new prompt with the exact charged level."
                )
                allow_explicit_special_prompt = True
                results = []

        if query_has_explicit_strength and results:
            wants_od_strength = bool(re.search(r"\b(od|ex)\b", text_lower))
            wants_non_od_strength = bool(
                re.search(r"\b(lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\b", text_lower)
            )
            if wants_od_strength:
                od_results = [row for row in results if row_is_od_variant(row)]
                if od_results:
                    results = od_results
            elif wants_non_od_strength:
                non_od_results = [row for row in results if not row_is_od_variant(row)]
                if non_od_results:
                    results = non_od_results

            exact_strength_results = [
                row for row in results
                if row_matches_explicit_strength(row, text_lower)
            ]
            if exact_strength_results:
                results = exact_strength_results

            exact_term_results = [
                row for row in results
                if row_matches_query_move_terms(row)
            ]
            if exact_term_results:
                results = exact_term_results

        results = apply_character_specific_result_filters(
            text_lower,
            text_tokens,
            mentioned_chars,
            results,
            filter_state=filter_state,
            air_tatsu_context=air_tatsu_context,
            air_fireball_context=air_fireball_context,
            air_sa1_context=air_sa1_context,
            query_requests_sa3=query_requests_sa3,
            air_sa3_context=air_sa3_context,
            query_wants_od_strength=query_wants_od_strength,
            normalize_char_name=normalize_char_name,
            lookup_frame_data=lookup_frame_data,
            row_is_ca_variant=row_is_ca_variant,
            alex_stance_followup_context=alex_stance_followup_context,
            chun_stance_followup_context=chun_stance_followup_context,
            normalize_num_cmd_token=normalize_num_cmd_token,
        )

        if query_requests_ca and results:
            ca_rows = [row for row in results if row_is_ca_variant(row)]
            if ca_rows:
                results = ca_rows

        if query_requests_air_context and results:
            air_rows = []
            for row in results:
                move_name = str(row.get("moveName", "")).lower()
                cmn_name = str(row.get("cmnName", "")).lower()
                num_cmd = str(row.get("numCmd", "")).lower()
                if "air" in move_name or "air" in cmn_name or "(air)" in num_cmd:
                    air_rows.append(row)
            if air_rows:
                results = air_rows

        if query_requires_stocked and results:
            stocked_rows = [row for row in results if row_is_stocked_variant(row)]
            if stocked_rows:
                results = stocked_rows

        results = apply_explicit_strength_result_filter(results)

        if (
            not query_has_explicit_strength
            and results
            and not target_combo_query
            and not query_requires_stocked
            and not query_requests_ca
        ):
            existing_special_prompt_keys = set()

            def variant_is_air_move(row):
                move_name = str(row.get("moveName", "")).lower()
                cmn_name = str(row.get("cmnName", "")).lower()
                num_cmd = str(row.get("numCmd", "")).lower()
                return (
                    "(air" in num_cmd
                    or "air" in move_name
                    or "air" in cmn_name
                    or "aerial" in move_name
                    or "aerial" in cmn_name
                )

            for prompt_block in special_prompt_blocks:
                char_match = re.search(r"Special Strength Options \(([^)]+)\)", prompt_block)
                base_match = re.search(r"\n([^\n]+) variants:", prompt_block)
                if not char_match or not base_match:
                    continue
                prompt_char = normalize_char_name(char_match.group(1))
                prompt_base = str(base_match.group(1)).lower().strip()
                if prompt_char and prompt_base:
                    existing_special_prompt_keys.add((prompt_char, prompt_base))

            ambiguous_special_keys = set()
            for row in results:
                row_char_norm = normalize_char_name(row.get("char_name", ""))
                if not row_char_norm:
                    continue
                if mentioned_chars and row_char_norm not in {
                    normalize_char_name(char) for char in mentioned_chars
                }:
                    continue
                row_char_key = resolve_character_key(row.get("char_name", ""))
                if not row_char_key:
                    continue
                if not is_special_motion_num_cmd(row.get("numCmd", "")):
                    continue

                base_name = get_special_canonical_base_name(row)
                if not base_name:
                    continue

                if should_skip_ambiguous_special_key(row_char_norm, base_name):
                    continue

                key = (row_char_norm, base_name)
                if key in existing_special_prompt_keys or key in ambiguous_special_keys:
                    continue

                variants = []
                for candidate in FRAME_DATA.get(row_char_key, []):
                    if row_char_key == "jamie" and candidate.get("_jamie_drink_level") is not None:
                        continue
                    if not is_special_motion_num_cmd(candidate.get("numCmd", "")):
                        continue
                    if get_special_canonical_base_name(candidate) != base_name:
                        continue
                    if query_requires_variant_state and not row_matches_character_variant_state(candidate):
                        continue
                    variants.append(candidate)

                if query_requests_air_context and not any(
                    variant_is_air_move(candidate) for candidate in variants
                ):
                    continue

                if query_requests_level2 or query_requests_level3:
                    continue

                if len(variants) < 2:
                    continue

                if len(variants) == 2:
                    od_variants = [candidate for candidate in variants if row_is_od_variant(candidate)]
                    non_od_variants = [candidate for candidate in variants if not row_is_od_variant(candidate)]
                    if len(od_variants) == 1 and len(non_od_variants) == 1:
                        chosen_variant = od_variants[0] if query_wants_od_strength else non_od_variants[0]
                        if chosen_variant not in results:
                            results.append(chosen_variant)
                        continue

                variant_lines = "\n".join(
                    f"{index}. {candidate.get('moveName', '?')} ({candidate.get('numCmd', '?')})"
                    for index, candidate in enumerate(variants, start=1)
                )
                special_prompt_blocks.append(
                    f"**Special Strength Options ({row_char_key.capitalize()})**\n"
                    f"{base_name.title()} variants:\n{variant_lines}\n"
                    "Reply with the option number, or make a new prompt with the exact strength+move."
                )
                ambiguous_special_keys.add(key)

            if ambiguous_special_keys:
                filtered_results = []
                for row in results:
                    row_char = normalize_char_name(row.get("char_name", ""))
                    row_base = get_special_canonical_base_name(row)
                    row_key = (row_char, row_base)
                    if (
                        is_special_motion_num_cmd(row.get("numCmd", ""))
                        and row_key in ambiguous_special_keys
                    ):
                        continue
                    filtered_results.append(row)
                results = filtered_results

    if special_prompt_blocks and (
        allow_explicit_special_prompt
        or
        (
            not query_has_explicit_strength
            and not query_requires_stocked
            and not query_requests_ca
        )
        or (special_grab_query and not results)
    ):
        results = []

    if (
        wants_comparison
        and len(mentioned_chars) >= 2
        and len(comparison_char_inputs) >= 2
        and not special_prompt_blocks
    ):
        scoped_comparison_rows = []
        for char in mentioned_chars:
            scoped_inputs = comparison_char_inputs.get(char, [])
            for scoped_input in scoped_inputs:
                scoped_row = lookup_frame_data(char, scoped_input)
                if scoped_row and scoped_row not in scoped_comparison_rows:
                    scoped_comparison_rows.append(scoped_row)
        if scoped_comparison_rows:
            results = scoped_comparison_rows

    if target_combo_query:
        if tc_prompt_blocks and not tc_selected_combos:
            results = []
        else:
            filtered_tc_results = []
            for row in results:
                num_cmd_compact = re.sub(r"\s+", "", str(row.get("numCmd", "")).lower())
                if ">" not in num_cmd_compact:
                    continue
                if tc_selected_combos and num_cmd_compact not in tc_selected_combos:
                    continue
                if tc_base_tokens and not any(
                    num_cmd_compact.startswith(f"{base}>") for base in tc_base_tokens
                ):
                    continue
                if row not in filtered_tc_results:
                    filtered_tc_results.append(row)
            if filtered_tc_results:
                results = filtered_tc_results
            elif tc_prompt_blocks:
                results = []

    # Format the results
    formatted_blocks = []

    stats_intent, results, formatted_blocks = apply_stats_context(
        text_lower,
        mentioned_chars,
        FRAME_STATS,
        lookup_frame_data,
        results,
        formatted_blocks,
        explicit_move_attempt=explicit_move_attempt,
        wants_frame_data=wants_frame_data,
        gif_query=gif_query,
        property_only_query=property_only_query,
        startup_alias_query=startup_alias_query,
    )
    wants_stats = stats_intent.wants_stats
    stats_only = stats_intent.stats_only
    stats_char_keys = list(stats_intent.character_keys)

    results = filter_and_inject_key_moves(
        text_lower,
        mentioned_chars,
        results,
        lookup_frame_data,
        query_has_explicit_strength=query_has_explicit_strength,
        frame_data=FRAME_DATA,
        wants_frame_data=wants_frame_data,
        target_combo_query=target_combo_query,
        special_prompt_blocks=special_prompt_blocks,
        explicit_move_attempt=explicit_move_attempt,
    )

    missing_scrolls_query = is_missing_scrolls_query(
        wants_frame_data=wants_frame_data,
        mentioned_chars=mentioned_chars,
        explicit_move_attempt=explicit_move_attempt,
        results=results,
        tc_prompt_blocks=tc_prompt_blocks,
        special_prompt_blocks=special_prompt_blocks,
    )
    formatted_blocks.extend(format_sf6_rows(results, format_attack_range_for_table))


    # 5. Attach TC/special prompts, punish verdict, and mode selection
    if tc_prompt_blocks:
        formatted_blocks.extend(tc_prompt_blocks)
    if special_prompt_blocks:
        formatted_blocks.extend(special_prompt_blocks)

    sections = []
    if formatted_blocks:
        sections.append("\n\n".join(formatted_blocks))

    output = "\n\n---\n".join(sections)

    # Check for punish calculation
    punish_verdict = check_punish(text_lower, results)
    if punish_verdict:
        if output:
            output = punish_verdict + "\n\n---\n\n" + output
        else:
            output = punish_verdict

    has_frame_blocks = bool(formatted_blocks)
    has_stats_blocks = bool(wants_stats and stats_char_keys)
    if stats_only and has_stats_blocks and not results:
        mode = "stats"
    elif has_frame_blocks:
        mode = "frame"
    else:
        mode = "none"

    return parser_result(
        mode,
        results,
        output,
        stats_query=wants_stats,
        stats_only=stats_only,
        stats_char_keys=stats_char_keys,
        stats_keys=list(stats_intent.stat_keys) if stats_intent.stat_keys else None,
        startup_alias_query=startup_alias_query,
        hitconfirm_alias_query=hitconfirm_alias_query,
        super_gain_alias_query=super_gain_alias_query,
        range_alias_query=range_alias_query,
        wants_comparison=bool(wants_comparison),
        property_only_query=property_only_query,
        target_combo_query=target_combo_query,
        missing_scrolls_query=missing_scrolls_query,
        gif_query=gif_query,
        explicit_move_attempt=explicit_move_attempt,
    )

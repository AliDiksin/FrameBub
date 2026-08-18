"""SF6 query-input and target-combo candidate collection."""

import difflib
import re

from bubbot.frame_data.sf6_character_aliases import (
    adjust_character_specific_keyword_inputs,
    collect_character_followup_contexts,
    collect_character_specific_aliases,
    collect_late_character_specific_aliases,
    create_character_filter_state,
    expand_character_candidate_names,
    row_matches_character_variant_state,
    should_append_single_token_candidate,
    should_skip_keyword_input,
)
from bubbot.frame_data.sf6_cammy_followups import query_has_hooligan_followup
from bubbot.frame_data.sf6_parser_helpers import (
    collect_normal_notation_inputs,
    row_is_air_move,
)
from bubbot.frame_data.sf6_special_prompt_rules import (
    choose_character_special_variant,
    should_skip_special_prompt_base,
)




def collect_sf6_candidates(state):
    """Collect SF6 aliases, target-combo prompts, and explicit move inputs."""
    text_lower = state["text_lower"]
    text_tokens = state["text_tokens"]
    mentioned_chars = state["mentioned_chars"]
    CHARACTER_ALIASES = state["CHARACTER_ALIASES"]
    FRAME_DATA = state["FRAME_DATA"]
    normalize_char_name = state["normalize_char_name"]
    resolve_character_key = state["resolve_character_key"]
    normalize_num_cmd_token = state["normalize_num_cmd_token"]
    lookup_frame_data = state["lookup_frame_data"]
    wants_frame_data = state["wants_frame_data"]
    target_combo_query = state["target_combo_query"]
    wants_comparison = state["wants_comparison"]
    query_requests_ca = state["query_requests_ca"]
    query_requests_sa1 = state["query_requests_sa1"]
    query_requests_sa2 = state["query_requests_sa2"]
    query_requests_sa3 = state["query_requests_sa3"]
    query_requires_variant_state = state["query_requires_variant_state"]
    query_requires_charged = state["query_requires_charged"]
    query_requests_level2 = state["query_requests_level2"]
    query_requests_level3 = state["query_requests_level3"]
    query_requires_stocked = state["query_requires_stocked"]
    query_wants_od_strength = state.get("query_wants_od_strength", False)
    row_is_charged_variant = state["row_is_charged_variant"]
    row_is_od_variant = state["row_is_od_variant"]
    row_matches_requested_level = state["row_matches_requested_level"]
    tokens_in_text = state["tokens_in_text"]
    tokens_in_haystack = state["tokens_in_haystack"]
    results = state["results"]
    tc_prompt_blocks = state["tc_prompt_blocks"]
    special_prompt_blocks = state["special_prompt_blocks"]
    tc_ambiguous_inputs = state["tc_ambiguous_inputs"]
    comparison_char_inputs = state["comparison_char_inputs"]
    allow_explicit_special_prompt = state.get("allow_explicit_special_prompt", False)

    if wants_frame_data:
        # 3. Extract move inputs and aliases from query text
        move_regex = r"\b([1-9][0-9]*[a-zA-Z]+|stand\s+[a-zA-Z]+|crouch\s+[a-zA-Z]+|(?:neutral\s+|n\s+)?jump\s+[a-zA-Z]+|(?:neutral\s+|n\s+)?jump\s+[1-9][0-9]*[a-zA-Z]+|(?:neutral\s+|n\s+)?j(?:\s+|\.)[a-zA-Z]+|(?:neutral\s+|n\s+)?j(?:\s+|\.)[1-9][0-9]*[a-zA-Z]+|(?:neutral\s+|n\s+)?j\.?[1-9][0-9]*[a-zA-Z]+|(?:lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\s+[a-zA-Z]+(?:\s+[a-zA-Z]+)?|[a-zA-Z]+\s+kick|[a-zA-Z]+\s+punch)\b"
        potential_inputs = re.findall(move_regex, text_lower)
        compact_motion_inputs = []
        charge_followup_inputs = []
        for input_text in re.findall(
            r"\b(28k{1,2}\s*>\s*(?:p{1,2}|k{1,2}))\b",
            text_lower,
        ):
            compact_input = re.sub(r"\s+", "", input_text)
            if compact_input not in charge_followup_inputs:
                charge_followup_inputs.append(compact_input)
        charge_followup_bases = {input_text.split(">", 1)[0] for input_text in charge_followup_inputs}
        if charge_followup_bases:
            potential_inputs = [
                input_text
                for input_text in potential_inputs
                if re.sub(r"\s+", "", input_text) not in charge_followup_bases
            ]
        compact_motion_inputs.extend(charge_followup_inputs)
        motion_button_matches = re.findall(
            r"\b([1-9][0-9]{1,4})\s*(?:\+)?\s*(lp|mp|hp|lk|mk|hk|pp|kk|p|k)\b",
            text_lower,
        )
        for motion_digits, button_suffix in motion_button_matches:
            compact_motion = f"{motion_digits}{button_suffix}"
            if compact_motion in charge_followup_bases:
                continue
            if compact_motion not in compact_motion_inputs:
                compact_motion_inputs.append(compact_motion)

        for compact_motion in collect_normal_notation_inputs(text_lower):
            if compact_motion not in compact_motion_inputs:
                compact_motion_inputs.append(compact_motion)

        if compact_motion_inputs:
            potential_inputs = compact_motion_inputs + potential_inputs
        strength_prefix_pattern = re.compile(r"^(lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\b")
        strength_prefixes_for_filter = [
            "lp", "mp", "hp", "lk", "mk", "hk",
            "light", "medium", "heavy", "l", "m", "h",
        ]
        filtered_inputs = []
        for inp in potential_inputs:
            if not inp:
                continue
            original_inp = str(inp).strip().lower()
            cleaned_inp = re.sub(r"\s+framedata$", "", inp).strip()
            cleaned_inp = re.sub(r"\s+frame\s*data$", "", cleaned_inp).strip()
            cleaned_inp = re.sub(r"\s+frame$", "", cleaned_inp).strip()
            cleaned_inp = re.sub(
                r"\s+(?:gif|gifs|hitbox|hitboxes)(?:\s+link)?$",
                "",
                cleaned_inp,
            ).strip()
            if not cleaned_inp:
                continue
            if cleaned_inp in strength_prefixes_for_filter and re.search(
                r"\b(frame\s*data|framedata|frame|data|gif|gifs|hitbox|hitboxes|startup|recovery|active|stats|punish|punishable)\b",
                original_inp,
            ):
                continue
            if not strength_prefix_pattern.match(cleaned_inp):
                if any(
                    re.search(
                        rf"\b{re.escape(prefix)}\s+{re.escape(cleaned_inp)}\b",
                        text_lower,
                    )
                    for prefix in strength_prefixes_for_filter
                ):
                    continue
            filtered_inputs.append(cleaned_inp)
        potential_inputs = filtered_inputs
        extra_inputs = []
        query_strength_tokens = {
            "lp", "mp", "hp", "lk", "mk", "hk",
            "light", "medium", "heavy", "l", "m", "h",
            "od", "ex",
        }
        compact_strength_motion_present = bool(
            re.search(
                r"\b(?:lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\s*(?:dp|srk|shoryu|shoryuken)\b"
                r"|\b(?:dp|srk|shoryu|shoryuken)\s*(?:lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\b",
                text_lower,
            )
        )
        compact_od_motion_present = bool(
            re.search(
                r"\b(?:od|ex)\s*(?:dp|srk|shoryu|shoryuken)\b"
                r"|\b(?:dp|srk|shoryu|shoryuken)\s*(?:od|ex)\b",
                text_lower,
            )
        )
        compact_num_cmd_strength_present = bool(
            re.search(
                r"\b(?:j\.?\s*)?[1-9][0-9]{1,5}\s*(?:\+)?\s*(?:lp|mp|hp|lk|mk|hk|pp|kk)\b",
                text_lower,
            )
        )
        query_has_explicit_strength = bool(
            any(token in query_strength_tokens for token in text_tokens)
            or compact_strength_motion_present
            or compact_od_motion_present
            or compact_num_cmd_strength_present
        )
        query_wants_od_strength = bool(re.search(r"\b(od|ex)\b", text_lower))
        query_wants_non_od_strength = bool(
            re.search(r"\b(lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\b", text_lower)
        )
        filter_state = create_character_filter_state()
        query_requests_air_context = bool(re.search(r"\b(?:air|aerial)\b", text_lower))
        air_fireball_context = bool(
            re.search(
                r"\b(?:air|aerial)\s+fireball\b|\bair\s+hadoken\b",
                text_lower,
            )
        )
        air_sa1_context = bool(
            re.search(
                r"\b(?:air|aerial)\s*(?:sa\s*1|super\s*art\s*1|super\s*1|level\s*1)\b"
                r"|\b(?:sa\s*1|super\s*art\s*1|super\s*1|level\s*1)\s*(?:air|aerial)\b",
                text_lower,
            )
        )
        air_sa2_context = bool(
            re.search(
                r"\b(?:air|aerial)\s*(?:sa\s*2|super\s*art\s*2|super\s*2|level\s*2)\b"
                r"|\b(?:sa\s*2|super\s*art\s*2|super\s*2|level\s*2)\s*(?:air|aerial)\b",
                text_lower,
            )
        )
        zangief_borscht_context = bool(
            re.search(r"\bborscht\b", text_lower)
            or re.search(r"\bj\.?\s*360\s*\+?\s*k{1,2}\b", text_lower)
            or re.search(r"\bj\s+360\s*\+?\s*k{1,2}\b", text_lower)
        )
        alex_stance_followup_context = bool(
            re.search(
                r"\bstance\s+(?:lp|mp|hp|lk|mk|hk|6p|6|4|lplk|5lplk|2lplk|"
                r"exit|elbow|forward\s+dash|backward\s+dash|jab|shoulder|lariat|hop|stomp|throw|command\s+grab|hk\s+hk)\b",
                text_lower,
            )
        )
        cammy_hooligan_followup_context = bool(
            "cammy" in mentioned_chars and query_has_hooligan_followup(text_lower)
        )
        chun_stance_followup_context = bool(
            re.search(
                r"\b(?:stance|ss|serenity\s+stream|214p)\s+"
                r"(?:lp|mp|hp|lk|mk|hk|"
                r"(?:light|medium|heavy|l|m|h)\s+(?:punch|kick)|"
                r"jab|slide|overhead|low(?:\s+poke)?|sweep|launcher)\b"
                r"|\b214p\s*(?:>|\+)?\s*"
                r"(?:lp|mp|hp|lk|mk|hk|"
                r"(?:light|medium|heavy|l|m|h)\s+(?:punch|kick)|"
                r"jab|slide|overhead|low(?:\s+poke)?|sweep|launcher)\b"
                r"|\b(?:stance|ss)\s+(?:light|medium|heavy|l|m|h)\s+(?:punch|kick)\b",
                text_lower,
            )
        )
        air_sa3_context = bool(
            re.search(
                r"\b(?:air|aerial)\s*(?:sa\s*3|super\s*art\s*3|super\s*3|level\s*3|critical\s+art|ca)\b"
                r"|\b(?:sa\s*3|super\s*art\s*3|super\s*3|level\s*3|critical\s+art|ca)\s*(?:air|aerial)\b",
                text_lower,
            )
        )
        air_tatsu_context = bool(
            re.search(
                r"\b(?:air|aerial)\s+tatsu\b|\b(?:air|aerial)\s+tatsumaki\b|\btatsu\s*\(air\)\b|\bj\.?\s*214k\b",
                text_lower,
            )
        )
        followup_contexts = collect_character_followup_contexts(text_lower, mentioned_chars)
        ken_run_followup_context = bool(followup_contexts.get("run_followup"))

        character_aliases = collect_character_specific_aliases(
            text_lower,
            extra_inputs,
            potential_inputs,
            mentioned_chars=mentioned_chars,
            air_sa1_context=air_sa1_context,
            air_sa2_context=air_sa2_context,
            air_sa3_context=air_sa3_context,
            query_requires_stocked=query_requires_stocked,
            query_wants_od_strength=query_wants_od_strength,
            ken_run_followup_context=ken_run_followup_context,
        )
        filter_state = character_aliases["filter_state"]
        potential_inputs = character_aliases["potential_inputs"]

        if query_requests_ca and "critical art" not in extra_inputs:
            extra_inputs.append("critical art")
        for requested, super_input in (
            (query_requests_sa1, "super art level 1"),
            (query_requests_sa2, "super art level 2"),
            (query_requests_sa3, "super art level 3"),
        ):
            if requested and super_input not in extra_inputs:
                extra_inputs.append(super_input)


        def is_special_motion_num_cmd(num_cmd_raw):
            compact = re.sub(r"[^a-z0-9]", "", str(num_cmd_raw).lower())
            if not compact or ">" in str(num_cmd_raw):
                return False
            motion_prefixes = (
                "236", "214", "623", "421", "41236", "63214", "4268", "624", "46", "28",
                "214214", "236236", "360", "720", "22",
            )
            return compact.startswith(motion_prefixes)

        def get_special_canonical_base_name(row):
            raw_name = str(row.get("cmnName", "")).lower().strip()
            if not raw_name:
                raw_name = str(row.get("moveName", "")).lower().strip()
            if not raw_name:
                return ""
            char_key = resolve_character_key(row.get("char_name", ""))
            base_name = re.sub(r"^(od|ex)\s+", "", raw_name)
            base_name = re.sub(
                r"^(lp|mp|hp|lk|mk|hk|pp|kk|light|medium|heavy|l|m|h)\s+",
                "",
                base_name,
            ).strip()
            base_name = re.sub(r"\s*\(charged\)", "", base_name).strip()
            if char_key == "akuma" and base_name in {
                "fireball (lvl 2)",
                "red fireball (lvl 3)",
                "red fireball",
            }:
                return "fireball"
            return base_name

        command_jump_notation_present = bool(
            re.search(
                r"\b(?:neutral\s+|n\s+)?(?:jump\s+|j\.?\s*)[1-9][0-9]*(?:lp|mp|hp|lk|mk|hk|p|k)\b",
                text_lower,
            )
        )

        if (
            not query_has_explicit_strength
            and mentioned_chars
            and not target_combo_query
            and not command_jump_notation_present
            and not query_requires_stocked
            and not query_requests_ca
        ):
            seen_special_prompts = set()
            for char in mentioned_chars:
                special_base_map = {}
                for row in FRAME_DATA.get(char, []):
                    if char == "jamie" and row.get("_jamie_drink_level") is not None:
                        continue
                    if not is_special_motion_num_cmd(row.get("numCmd", "")):
                        continue
                    canonical_base = get_special_canonical_base_name(row)
                    if not canonical_base:
                        continue
                    special_base_map.setdefault(canonical_base, [])
                    if row not in special_base_map[canonical_base]:
                        special_base_map[canonical_base].append(row)

                for base_name, variants in special_base_map.items():
                    prompt_variants = variants

                    chosen_variant, handled_variant = choose_character_special_variant(
                        char=char,
                        base_name=base_name,
                        variants=variants,
                        query_requests_sa1=query_requests_sa1,
                        query_requests_sa2=query_requests_sa2,
                        query_requires_variant_state=query_requires_variant_state,
                        row_matches_variant_state=row_matches_character_variant_state,
                    )
                    if chosen_variant and chosen_variant not in results:
                        results.append(chosen_variant)
                    if handled_variant:
                        continue

                    if query_requires_variant_state:
                        state_variants = [row for row in variants if row_matches_character_variant_state(row)]
                        if state_variants:
                            prompt_variants = state_variants
                        else:
                            continue
                    if query_requires_charged:
                        charged_prompt_variants = [row for row in prompt_variants if row_is_charged_variant(row)]
                        if charged_prompt_variants:
                            prompt_variants = charged_prompt_variants
                    if query_requests_air_context:
                        air_prompt_variants = [row for row in prompt_variants if row_is_air_move(row)]
                        if air_prompt_variants:
                            prompt_variants = air_prompt_variants
                        else:
                            continue
                    base_tokens = re.findall(r"[a-z0-9]+", base_name)
                    base_in_query = tokens_in_text(base_tokens)
                    if not base_in_query and base_name == "fireball":
                        base_in_query = "hadoken" in text_tokens or "hadouken" in text_tokens
                    if not base_in_query and base_name == "upkicks":
                        base_in_query = "tensho" in text_tokens or "tenshokyaku" in text_tokens
                    if not base_in_query and base_name == "palm thrust":
                        base_in_query = "hashogeki" in text_tokens
                    if not base_in_query and base_name == "super art level 1":
                        base_in_query = query_requests_sa1
                    if not base_in_query and base_name == "super art level 2":
                        base_in_query = query_requests_sa2
                    if not base_in_query and base_name == "super art level 3":
                        base_in_query = query_requests_sa3
                    if not base_in_query and base_name == "spd":
                        base_in_query = "command" in text_tokens and "grab" in text_tokens
                    if not base_in_query and base_name in {"burn kick", "burning kick"}:
                        base_in_query = bool(
                            re.search(r"\bburnkicks?\b", text_lower)
                            or re.search(r"\bburn\s+kicks?\b", text_lower)
                            or re.search(r"\bburning\s+kicks?\b", text_lower)
                        )
                    if not base_in_query and base_name == "scissor kick":
                        base_in_query = bool(
                            re.search(r"\bscissors?\b", text_lower)
                            or re.search(r"\bscissor\s+kicks?\b", text_lower)
                        )
                    if not base_in_query:
                        continue
                    if query_requests_level2 or query_requests_level3:
                        level_variants = [row for row in prompt_variants if row_matches_requested_level(row)]
                        if level_variants:
                            for row in level_variants:
                                if row not in results:
                                    results.append(row)
                            continue
                    if len(prompt_variants) < 2:
                        continue
                    if (
                        air_fireball_context
                        and base_name == "fireball"
                        and "air fireball" in special_base_map
                    ):
                        continue
                    if len(prompt_variants) == 2:
                        od_variants = [row for row in prompt_variants if row_is_od_variant(row)]
                        non_od_variants = [row for row in prompt_variants if not row_is_od_variant(row)]
                        if len(od_variants) == 1 and len(non_od_variants) == 1:
                            chosen_variant = od_variants[0] if query_wants_od_strength else non_od_variants[0]
                            if chosen_variant not in results:
                                results.append(chosen_variant)
                            continue
                    if should_skip_special_prompt_base(
                        char=char,
                        base_name=base_name,
                        air_tatsu_context=air_tatsu_context,
                        ken_run_followup_context=ken_run_followup_context,
                        alex_stance_followup_context=alex_stance_followup_context,
                    ):
                        continue
                    prompt_key = (char, base_name)
                    if prompt_key in seen_special_prompts:
                        continue
                    seen_special_prompts.add(prompt_key)
                    variant_lines = "\n".join(
                        f"{index}. {row.get('moveName', '?')} ({row.get('numCmd', '?')})"
                        for index, row in enumerate(prompt_variants, start=1)
                    )
                    special_prompt_blocks.append(
                        f"**Special Strength Options ({char.capitalize()})**\n"
                        f"{base_name.title()} variants:\n{variant_lines}\n"
                        "Reply with the option number, or make a new prompt with the exact strength+move."
                    )
        dp_strength_inputs = []
        dp_strength_prefix_matches = re.findall(
            r"\b(lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\s*(?:\+)?\s*(dp|srk|shoryu|shoryuken)\b",
            text_lower,
        )
        for strength_token, motion_token in dp_strength_prefix_matches:
            token = f"{strength_token} {motion_token}"
            if token not in dp_strength_inputs:
                dp_strength_inputs.append(token)
        dp_strength_suffix_matches = re.findall(
            r"\b(dp|srk|shoryu|shoryuken)\s*(?:\+)?\s*(lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\b",
            text_lower,
        )
        for motion_token, strength_token in dp_strength_suffix_matches:
            token = f"{strength_token} {motion_token}"
            if token not in dp_strength_inputs:
                dp_strength_inputs.append(token)
        for token in dp_strength_inputs:
            if token not in extra_inputs:
                extra_inputs.append(token)

        dp_aliases = ["dp", "srk", "shoryu", "shoryuken", "623"]
        dp_present = False
        for token in dp_aliases:
            if re.search(rf"\b{re.escape(token)}\b", text_lower):
                if dp_strength_inputs and token in {"dp", "srk", "shoryu", "shoryuken"}:
                    dp_present = True
                    continue
                if token not in extra_inputs:
                    extra_inputs.append(token)
                dp_present = True
        if dp_present and re.search(r"\b(ex|od)\b", text_lower):
            extra_inputs.append("623pp")
            extra_inputs.append("623kk")
        if re.search(r"\b(ex|od)(dp|srk|shoryu|shoryuken)\b", text_lower):
            extra_inputs.append("623pp")
            extra_inputs.append("623kk")
        if ken_run_followup_context:
            extra_inputs = [
                token for token in extra_inputs
                if token not in {"dp", "srk", "shoryu", "shoryuken", "tatsu", "dragonlash"}
            ]
        if "sway" in text_lower:
            extra_inputs.append("sway")
        if "jus cool" in text_lower or "juscool" in text_lower:
            extra_inputs.append("jus cool")

        filter_state = collect_late_character_specific_aliases(
            text_lower,
            extra_inputs,
            filter_state,
            mentioned_chars=mentioned_chars,
        )
        sa_alias_matches = re.findall(r"\bsa\s*([123])\b", text_lower)
        for sa_level in sa_alias_matches:
            sa_token = f"sa{sa_level}"
            if sa_token not in extra_inputs:
                extra_inputs.append(sa_token)
        # 46P charge patterns (back-forward+punch)
        charge_patterns = [
            (r"\b46p\b", "46p"),
            (r"\b46lp\b", "46lp"),
            (r"\b46mp\b", "46mp"),
            (r"\b46hp\b", "46hp"),
            (r"\b46pp\b", "46pp"),
            (r"\bb,\s*f\+?p\b", "46p"),
            (r"\bb,\s*f\+?lp\b", "46lp"),
            (r"\bb,\s*f\+?mp\b", "46mp"),
            (r"\bb,\s*f\+?hp\b", "46hp"),
            (r"\bb,\s*f\+?pp\b", "46pp"),
            (r"\bbf\+?p\b", "46p"),
            (r"\bbf\+?lp\b", "46lp"),
            (r"\bbf\+?mp\b", "46mp"),
            (r"\bbf\+?hp\b", "46hp"),
            (r"\bbf\+?pp\b", "46pp"),
            (r"\bback\s*forward\+?p\b", "46p"),
            (r"\bback\s*forward\+?lp\b", "46lp"),
            (r"\bback\s*forward\+?mp\b", "46mp"),
            (r"\bback\s*forward\+?hp\b", "46hp"),
            (r"\bback\s*forward\+?pp\b", "46pp"),
            # 28K charge patterns (down-up+kick)
            (r"\b28k\b", "28k"),
            (r"\b28lk\b", "28lk"),
            (r"\b28mk\b", "28mk"),
            (r"\b28hk\b", "28hk"),
            (r"\b28kk\b", "28kk"),
            (r"\bd,\s*u\+?k\b", "28k"),
            (r"\bd,\s*u\+?lk\b", "28lk"),
            (r"\bd,\s*u\+?mk\b", "28mk"),
            (r"\bd,\s*u\+?hk\b", "28hk"),
            (r"\bd,\s*u\+?kk\b", "28kk"),
            (r"\bdu\+?k\b", "28k"),
            (r"\bdu\+?lk\b", "28lk"),
            (r"\bdu\+?mk\b", "28mk"),
            (r"\bdu\+?hk\b", "28hk"),
            (r"\bdu\+?kk\b", "28kk"),
            (r"\bdown\s*up\+?k\b", "28k"),
            (r"\bdown\s*up\+?lk\b", "28lk"),
            (r"\bdown\s*up\+?mk\b", "28mk"),
            (r"\bdown\s*up\+?hk\b", "28hk"),
            (r"\bdown\s*up\+?kk\b", "28kk"),
        ]
        for pattern, token in charge_patterns:
            if token in charge_followup_bases:
                continue
            if re.search(pattern, text_lower) and token not in extra_inputs:
                extra_inputs.append(token)
        combo_text = text_lower.replace("->", ">")
        tc_selected_combos = set()
        tc_base_tokens = set(re.findall(r"\b[1-9][0-9]*[a-z]{1,3}\b", text_lower))
        tc_pair_candidates = set()
        for base_token, follow_token in re.findall(
            r"\b([1-9][0-9]*[a-z]{1,3})\s*(?:,|>|->)\s*([a-z]{1,3}|[1-9][0-9]*[a-z]{1,3})\b",
            combo_text,
        ):
            tc_pair_candidates.add(f"{base_token}>{follow_token}")
        for base_token, follow_token in re.findall(
            r"\b([1-9][0-9]*[a-z]{1,3})\s+([a-z]{1,3})\s+(?:target\s+combo|tc)\b",
            text_lower,
        ):
            tc_pair_candidates.add(f"{base_token}>{follow_token}")

        combo_matches = re.findall(
            r"\b[0-9a-zA-Z+]+(?:\s*>\s*[0-9a-zA-Z+]+)+\b",
            combo_text,
        )
        for combo in combo_matches:
            combo_token = re.sub(r"\s+", "", combo)
            tc_selected_combos.add(combo_token)
            if combo_token not in extra_inputs:
                extra_inputs.append(combo_token)

        if target_combo_query and mentioned_chars:
            compact_text = re.sub(r"\s+", "", combo_text)
            for char in mentioned_chars:
                normalized_char = normalize_char_name(char)
                compact_text_for_char = re.sub(
                    rf"\b{re.escape(normalized_char)}\b", "", compact_text
                )
                if compact_text_for_char == compact_text:
                    compact_text_for_char = compact_text
                tc_map = {}
                for row in FRAME_DATA.get(char, []):
                    num_cmd_raw = str(row.get("numCmd", ""))
                    num_cmd = num_cmd_raw.lower()
                    if ">" not in num_cmd:
                        continue
                    base_cmd = num_cmd.split(">", 1)[0].strip()
                    base_key = re.sub(r"\s+", "", base_cmd)
                    if not base_key:
                        continue
                    tc_map.setdefault(base_key, []).append(num_cmd_raw)
                for base_key, combos in tc_map.items():
                    if base_key not in compact_text_for_char:
                        continue
                    explicit_pair_matches = [
                        pair for pair in tc_pair_candidates if pair.startswith(f"{base_key}>")
                    ]
                    if explicit_pair_matches:
                        matched_any = False
                        for combo_raw in combos:
                            combo_key = re.sub(r"\s+", "", combo_raw.lower())
                            if ">" not in combo_key:
                                continue
                            combo_follow = combo_key.split(">", 1)[1]
                            for explicit_pair in explicit_pair_matches:
                                explicit_follow = explicit_pair.split(">", 1)[1]
                                if combo_follow == explicit_follow or combo_follow.startswith(explicit_follow):
                                    tc_selected_combos.add(combo_key)
                                    if combo_key not in extra_inputs:
                                        extra_inputs.append(combo_key)
                                    matched_any = True
                        if matched_any:
                            continue
                    if len(combos) == 1:
                        combo_token = re.sub(r"\s+", "", combos[0].lower())
                        tc_selected_combos.add(combo_token)
                        if combo_token not in extra_inputs:
                            extra_inputs.append(combo_token)
                        continue
                    tc_ambiguous_inputs.add(base_key)
                    combo_list = "\n".join(f"{index}. {combo}" for index, combo in enumerate(combos, start=1))
                    tc_prompt_blocks.append(
                        f"**Target Combo Options ({char.capitalize()})**\n"
                        f"{base_key.upper()} follow-ups:\n{combo_list}\n"
                        "Reply with the option number, or make a new prompt with the exact target combo."
                    )
        keyword_inputs = [
            # 46P moves
            "air slasher",
            "sonic boom",
            "sumo headbutt",
            "psycho crusher",
            "rolling attack",
            "blanka ball",
            "bison crusher",
            "crusher",
            "fireball",
            "boom",
            "headbutt",
            "clap",
            "claps",
            "neko damashi",
            "oicho",
            "oicho throw",
            "ball",
            # 28K moves
            "vertical rolling attack",
            "upball",
            "up ball",
            "somersault kick",
            "flash kick",
            "flashkick",
            "shadow rise",
            "command jump",
            "fly",
            "jackknife maximum",
            "upkicks",
            "upkick",
            "up kicks",
            "tensho",
            "tenshokyaku",
            "tensho kick",
            "tensho kicks",
            "dive kick",
            "divekick",
            "demon flip",
            "demon raid",
            "demon low slash",
            "demon guillotine",
            "demon blade kick",
            "demon swoop",
            "demon gou zanku",
            "demon gou rasen",
            "adamant flame",
            "flaming fist",
            "flame",
            "burn kick",
            "burnkick",
            "burn kicks",
            "burnkicks",
            "burning kick",
            "burning kicks",
            "airthrow",
            "air throw",
            "air grab",
            "scissors",
            "scissor kick",
            "scissor kicks",
            "bear grab",
            "bear hug",
            "running bear grab",
            "air burn kick",
            "air burnkick",
            "air burning kick",
            "air burning kicks",
            "aerial burn kick",
            "aerial burnkick",
            "aerial burning kick",
            "teleport",
            "ashura",
            "ashura senku",
            "raging demon",
            "tenma",
            "gozanku",
            "air fireball",
            "aerial fireball",
            "air hadoken",
            "zanku",
            "air tatsu",
            "aerial tatsu",
            "air tatsumaki",
            "aerial tatsumaki",
            "air legs",
            "airlegs",
            "aerial legs",
            "air lightning legs",
            "sumo smash",
            "ass slam",
            "butt slam",
            "spinning bird kick",
            "sbk",
            # JP 22 specials
            "triglav",
            "amnesia",
            "ground spike",
            "spike",
            "pierce",
        ]
        # Strength prefixes for charge moves
        strength_prefixes = ["lp", "mp", "hp", "od", "ex", "light", "medium", "heavy", "l", "m", "h"]
        for token in keyword_inputs:
            matched_strength_for_token = False
            # Check for strength+keyword combos (e.g., "heavy fireball", "hp boom")
            for prefix in strength_prefixes:
                combo = f"{prefix} {token}"
                if combo in text_lower and combo not in extra_inputs:
                    if should_skip_keyword_input(token, text_lower):
                        continue
                    extra_inputs.append(combo)
                    matched_strength_for_token = True
            # Check for bare keyword
            if (
                not matched_strength_for_token
                and re.search(rf"\b{re.escape(token)}\b", text_lower)
                and token not in extra_inputs
            ):
                if should_skip_keyword_input(token, text_lower):
                    continue
                extra_inputs.append(token)
        extra_inputs = adjust_character_specific_keyword_inputs(text_lower, mentioned_chars, extra_inputs)
        ordered_inputs = []
        for inp in extra_inputs + potential_inputs:
            if inp and inp not in ordered_inputs:
                ordered_inputs.append(inp)
        potential_inputs = ordered_inputs

        if wants_comparison and (potential_inputs or extra_inputs) and len(mentioned_chars) >= 2:
            side_segments = [
                segment.strip()
                for segment in re.split(r"\b(?:vs|versus|and)\b", text_lower)
                if segment.strip()
            ]
            if len(side_segments) >= 2:
                assigned_chars = set()

                def segment_mentions_character(segment_text, char_key):
                    segment_tokens = re.findall(r"[a-z0-9]+", segment_text)
                    if not segment_tokens:
                        return False
                    char_tokens = re.findall(r"[a-z0-9]+", str(char_key).lower())
                    if char_tokens and tokens_in_haystack(segment_tokens, char_tokens):
                        return True
                    for alias, canonical in CHARACTER_ALIASES.items():
                        if normalize_char_name(canonical) != normalize_char_name(char_key):
                            continue
                        alias_tokens = re.findall(r"[a-z0-9]+", str(alias).lower())
                        if alias_tokens and tokens_in_haystack(segment_tokens, alias_tokens):
                            return True
                    return False

                for side_text in side_segments:
                    side_chars = [
                        char for char in mentioned_chars
                        if segment_mentions_character(side_text, char)
                    ]
                    if not side_chars:
                        continue

                    if len(side_chars) == 1:
                        target_char = side_chars[0]
                    else:
                        target_char = next(
                            (char for char in side_chars if char not in assigned_chars),
                            side_chars[0],
                        )

                    side_inputs = []
                    for inp in potential_inputs:
                        inp_norm = str(inp or "").strip().lower()
                        if not inp_norm:
                            continue
                        if re.search(rf"\b{re.escape(inp_norm)}\b", side_text):
                            if inp not in side_inputs:
                                side_inputs.append(inp)

                    if side_inputs:
                        comparison_char_inputs[target_char] = side_inputs
                        assigned_chars.add(target_char)

        explicit_move_attempt = bool(potential_inputs or extra_inputs)
        if mentioned_chars:
            stop_tokens = {
                "frame", "frames", "framedata", "data", "startup", "recovery", "active",
                "on", "hit", "block", "compare", "comparison", "versus", "vs", "which",
                "is", "faster", "better", "tc", "target", "combo", "combos", "how", "fast",
                "quick", "speed", "of", "the", "a", "an", "for", "with", "please", "show",
                "tell", "me", "about", "can", "i", "punish", "punishable", "stats",
                "send", "post", "drop", "give", "link",
                "gif", "gifs", "hitbox", "hitboxes",
                "advantage", "counter", "punish", "pc", "ch",
                "range", "length", "super", "art", "level", "lvl", "lv",
                "sa1", "sa2", "sa3", "lv1", "lv2", "lv3", "lvl1", "lvl2", "lvl3",
            }
            char_tokens = set()
            for char in mentioned_chars:
                char_tokens.update(re.findall(r"[a-z0-9]+", str(char).lower()))
                normalized_char = normalize_char_name(char)
                if normalized_char:
                    char_tokens.add(normalized_char)
            residual_tokens = [] if charge_followup_inputs else [
                tok for tok in text_tokens
                if tok not in stop_tokens and tok not in char_tokens
            ]
            if residual_tokens:
                explicit_move_attempt = True
                residual_candidate = " ".join(residual_tokens).strip()
                if residual_candidate and residual_candidate not in potential_inputs:
                    potential_inputs.append(residual_candidate)

        strength_prefix_re = re.compile(r"^(?:lp|mp|hp|lk|mk|hk|pp|kk|od|ex|light|medium|heavy|l|m|h)\s+")
        text_compact = re.sub(r"[^a-z0-9]", "", text_lower)

        def token_matches_move_name(name_token, query_token):
            if (name_token == "od" and query_token == "ex") or (name_token == "ex" and query_token == "od"):
                return True
            if name_token == query_token:
                return True
            if len(query_token) >= 3 and name_token.startswith(query_token):
                return True
            if len(name_token) >= 3 and query_token.startswith(name_token):
                return True
            return False

        motion_button_notation_present = bool(
            re.search(
                r"\b[1-9][0-9]*\s*(?:\+)?\s*(?:lp|mp|hp|lk|mk|hk|pp|kk|p|k)\b",
                text_lower,
            )
        )

    return {
        "potential_inputs": potential_inputs,
        "extra_inputs": extra_inputs,
        "query_has_explicit_strength": query_has_explicit_strength,
        "query_wants_od_strength": query_wants_od_strength,
        "query_wants_non_od_strength": query_wants_non_od_strength,
        "filter_state": filter_state,
        "query_requests_air_context": query_requests_air_context,
        "air_fireball_context": air_fireball_context,
        "air_sa1_context": air_sa1_context,
        "air_sa2_context": air_sa2_context,
        "air_sa3_context": air_sa3_context,
        "air_tatsu_context": air_tatsu_context,
        "zangief_borscht_context": zangief_borscht_context,
        "alex_stance_followup_context": alex_stance_followup_context,
        "cammy_hooligan_followup_context": cammy_hooligan_followup_context,
        "chun_stance_followup_context": chun_stance_followup_context,
        "ken_run_followup_context": ken_run_followup_context,
        "tc_selected_combos": tc_selected_combos,
        "tc_base_tokens": tc_base_tokens,
        "explicit_move_attempt": explicit_move_attempt,
        "is_special_motion_num_cmd": is_special_motion_num_cmd,
        "get_special_canonical_base_name": get_special_canonical_base_name,
        "allow_explicit_special_prompt": allow_explicit_special_prompt,
        "strength_prefix_re": strength_prefix_re,
        "text_compact": text_compact,
        "token_matches_move_name": token_matches_move_name,
        "motion_button_notation_present": motion_button_notation_present,
    }

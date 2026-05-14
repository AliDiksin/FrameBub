import difflib
import re


def find_moves_in_text(deps, text):
    CHARACTER_ALIASES = deps["CHARACTER_ALIASES"]
    FRAME_DATA = deps["FRAME_DATA"]
    FRAME_STATS = deps["FRAME_STATS"]
    BNB_DATA = deps["BNB_DATA"]
    OKI_DATA = deps["OKI_DATA"]
    CHARACTER_INFO = deps["CHARACTER_INFO"]
    strip_discord_mentions = deps["strip_discord_mentions"]
    normalize_jump_normal_text = deps["normalize_jump_normal_text"]
    word_tokens = deps["word_tokens"]
    contains_token_sequence = deps["contains_token_sequence"]
    has_explicit_gif_lookup_intent = deps["has_explicit_gif_lookup_intent"]
    lookup_frame_data = deps["lookup_frame_data"]
    normalize_char_name = deps["normalize_char_name"]
    resolve_character_key = deps["resolve_character_key"]
    is_missing_attack_range_value = deps["is_missing_attack_range_value"]
    get_attack_range_details = deps["get_attack_range_details"]
    format_attack_range_for_table = deps["format_attack_range_for_table"]
    format_frame_data = deps["format_frame_data"]
    check_punish = deps["check_punish"]
    """Extract character/move mentions and return context payload with mode."""
    found_data = []
    text_lower = strip_discord_mentions(text).lower()
    text_lower = normalize_jump_normal_text(text_lower)
    text_lower = re.sub(r"\bdivekick\b", "dive kick", text_lower)
    tc_prompt_blocks = []
    special_prompt_blocks = []
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

    if not mentioned_chars and (
        re.search(r"\braging\s+demon\b", text_lower)
        or re.search(r"\bshun\s+goku\s+satsu\b", text_lower)
    ):
        if "akuma" in FRAME_DATA:
            mentioned_chars.append("akuma")

    # Check for BNB/Combo requests
    bnb_keywords = ["combo", "combos", "bnb", "bnbs", "bread and butter", "route", "routes"]
    oki_keywords = ["oki", "okizeme", "setup", "setups", "meaty", "meaties"]
    info_keywords = [
        "playstyle",
        "gameplan",
        "archetype",
        "overview",
        "tell me about",
        "who is",
        "strengths",
        "weaknesses",
        "moveset",
        "toolkit",
        "role",
        "how to play",
        "character synopsis",
        "summary",
        "anti air",
        "anti-air",
        "neutral",
        "win condition",
    ]
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
        "on_hit": bool(re.search(r"\bon\s+hit\b", text_lower)),
        "on_block": bool(re.search(r"\bon\s+block\b|\bplus\s+on\s+block\b|\bminus\s+on\s+block\b", text_lower)),
        "cancel": bool(re.search(r"\bcancel(?:l?able)?\b", text_lower)),
        "damage": bool(re.search(r"\bdamage\b|\bdmg\b", text_lower)),
        "drive_chip": bool(re.search(r"\bdrive\s+chip\b|\bdrive\s+dmg\b|\bdrive\s+damage\b", text_lower)),
        "drive_gain": bool(re.search(r"\bdrive\s+gain\b", text_lower)),
        "stun": bool(re.search(r"\bhitstun\b|\bblockstun\b|\bstun\b", text_lower)),
        "hitconfirm": hitconfirm_alias_query,
        "super_gain": super_gain_alias_query,
        "range": range_alias_query,
    }
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
    wants_bnb = any(kw in text_lower for kw in bnb_keywords) and not target_combo_query
    wants_oki = any(kw in text_lower for kw in oki_keywords)
    wants_info = any(kw in text_lower for kw in info_keywords)
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
        or target_combo_query
        or gif_query
    )
    bnb_context = ""
    info_blocks = []
    if wants_bnb or wants_oki:
        for char in mentioned_chars:
            if wants_bnb and char in BNB_DATA:
                bnb_context += f"\n\n**{char.capitalize()} Combos:**\n{BNB_DATA[char]}"
            if (wants_bnb or wants_oki) and char in OKI_DATA:
                bnb_context += f"\n\n**{char.capitalize()} Oki/Setups:**\n{OKI_DATA[char]}"
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

        query_requires_denjin = "denjin" in text_tokens
        query_requires_charged = any(token in text_tokens for token in ("charged", "hold", "held"))
        query_requests_sa1 = bool(
            re.search(r"\b(?:sa\s*1|super\s*art\s*1|super\s*1|level\s*1)\b", text_lower)
        )
        query_requests_sa2 = bool(
            re.search(r"\b(?:sa\s*2|super\s*art\s*2|super\s*2|level\s*2)\b", text_lower)
        )
        query_requests_sa3 = bool(
            re.search(r"\b(?:sa\s*3|super\s*art\s*3|super\s*3|level\s*3)\b", text_lower)
        )
        query_requests_ca = bool(
            re.search(r"\b(?:ca|critical\s+art)\b", text_lower)
        )
        stock_hint_tokens = ("stock", "stocked", "enhanced", "windclad")

        def token_is_stock_hint(token):
            token_norm = str(token or "").lower().strip()
            if not token_norm:
                return False
            if token_norm in stock_hint_tokens:
                return True
            return any(
                difflib.SequenceMatcher(None, token_norm, hint_token).ratio() >= 0.82
                for hint_token in stock_hint_tokens
            )

        query_requires_stocked = any(
            token in text_tokens for token in ("stock", "stocked", "enhanced", "windclad")
        ) or bool(re.search(r"\bwind\s+clad\b", text_lower)) or any(
            token_is_stock_hint(token) for token in text_tokens
        )

        def row_is_denjin_variant(row):
            move_name = str(row.get("moveName", "")).lower()
            cmn_name = str(row.get("cmnName", "")).lower()
            num_cmd = str(row.get("numCmd", "")).lower()
            return (
                "denjin" in move_name
                or "denjin" in cmn_name
                or "charged" in move_name
                or "charged" in cmn_name
                or "(charged)" in num_cmd
            )

        def row_is_charged_variant(row):
            move_name = str(row.get("moveName", "")).lower()
            cmn_name = str(row.get("cmnName", "")).lower()
            num_cmd = str(row.get("numCmd", "")).lower()
            return (
                "charged" in move_name
                or "charged" in cmn_name
                or "hold" in move_name
                or "hold" in cmn_name
                or "(charged" in num_cmd
                or "(hold" in num_cmd
            )

        def row_is_od_variant(row):
            move_name = str(row.get("moveName", "")).lower().strip()
            cmn_name = str(row.get("cmnName", "")).lower().strip()
            num_cmd_compact = re.sub(r"[^a-z0-9]", "", str(row.get("numCmd", "")).lower())
            return (
                move_name.startswith(("od ", "ex "))
                or cmn_name.startswith(("od ", "ex "))
                or num_cmd_compact.endswith(("pp", "kk"))
            )

        def row_matches_explicit_strength(row, strength_query_text):
            row_move_name = str(row.get("moveName", "")).lower().strip()
            row_cmn_name = str(row.get("cmnName", "")).lower().strip()
            row_num_cmd = str(row.get("numCmd", "")).lower().strip()
            row_num_cmd_compact = re.sub(r"[^a-z0-9]", "", row_num_cmd)

            if re.search(r"\b(?:od|ex)\b", strength_query_text):
                return row_is_od_variant(row)

            strength_groups = [
                ({"light", "l", "lp", "lk"}, {"lp", "lk"}),
                ({"medium", "m", "mp", "mk"}, {"mp", "mk"}),
                ({"heavy", "h", "hp", "hk"}, {"hp", "hk"}),
            ]

            requested_suffixes = set()
            for token_group, suffixes in strength_groups:
                if any(re.search(rf"\b{re.escape(token)}\b", strength_query_text) for token in token_group):
                    requested_suffixes.update(suffixes)

            if not requested_suffixes:
                return False

            if any(row_move_name.startswith(f"{suffix} ") or row_cmn_name.startswith(f"{suffix} ") for suffix in requested_suffixes):
                return True
            if any(
                row_move_name.startswith(f"{word} ") or row_cmn_name.startswith(f"{word} ")
                for word in ("light", "medium", "heavy")
                if word[0] in {suffix[0] for suffix in requested_suffixes}
            ):
                return True
            return row_num_cmd_compact.endswith(tuple(requested_suffixes))

        def row_matches_query_move_terms(row):
            ignored_tokens = {
                "framedata", "frame", "frames", "data", "gif", "gifs", "hitbox", "hitboxes",
                "light", "medium", "heavy", "l", "m", "h",
                "lp", "mp", "hp", "lk", "mk", "hk", "pp", "kk",
                "od", "ex", "charged", "hold", "held",
                "startup", "active", "recovery", "range",
                "on", "hit", "block", "damage", "cancel",
            }
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

        def row_is_ca_variant(row):
            move_name = str(row.get("moveName", "")).lower()
            cmn_name = str(row.get("cmnName", "")).lower()
            num_cmd = str(row.get("numCmd", "")).lower()
            return (
                "critical art" in move_name
                or "critical art" in cmn_name
                or bool(re.search(r"\(\s*ca\s*\)", num_cmd))
            )

        def row_is_stocked_variant(row):
            move_name = str(row.get("moveName", "")).lower()
            cmn_name = str(row.get("cmnName", "")).lower()
            num_cmd = str(row.get("numCmd", "")).lower()
            combined = f"{move_name} {cmn_name} {num_cmd}"
            if re.search(r"\b0\s*stocks?\b", combined):
                return False

            has_stock_count = bool(re.search(r"\b[1-9]\d*\s*stocks?\b", combined))
            has_stock_tag = "(stock" in move_name or "(stock" in cmn_name or "(stock" in num_cmd
            has_enhanced_tag = (
                "enhanced" in move_name
                or "enhanced" in cmn_name
                or "(enhanced" in num_cmd
            )
            has_windclad_tag = "windclad" in move_name or "windclad" in cmn_name
            has_wind_stock_hold = "wind stock" in cmn_name and (
                "(" in cmn_name or "(hold" in num_cmd
            )
            return (
                has_stock_count
                or has_stock_tag
                or has_enhanced_tag
                or has_windclad_tag
                or has_wind_stock_hold
            )


        move_regex = r"\b([1-9][0-9]*[a-zA-Z]+|stand\s+[a-zA-Z]+|crouch\s+[a-zA-Z]+|(?:neutral\s+|n\s+)?jump\s+[a-zA-Z]+|(?:neutral\s+|n\s+)?jump\s+[1-9][0-9]*[a-zA-Z]+|(?:neutral\s+|n\s+)?j(?:\s+|\.)[a-zA-Z]+|(?:neutral\s+|n\s+)?j(?:\s+|\.)[1-9][0-9]*[a-zA-Z]+|(?:neutral\s+|n\s+)?j\.?[1-9][0-9]*[a-zA-Z]+|(?:lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\s+[a-zA-Z]+(?:\s+[a-zA-Z]+)?|[a-zA-Z]+\s+kick|[a-zA-Z]+\s+punch)\b"
        potential_inputs = re.findall(move_regex, text_lower)
        compact_motion_inputs = []
        motion_button_matches = re.findall(
            r"\b([1-9][0-9]{1,4})\s*(?:\+)?\s*(lp|mp|hp|lk|mk|hk|pp|kk|p|k)\b",
            text_lower,
        )
        for motion_digits, button_suffix in motion_button_matches:
            compact_motion = f"{motion_digits}{button_suffix}"
            if compact_motion not in compact_motion_inputs:
                compact_motion_inputs.append(compact_motion)

        boomer_normal_matches = re.findall(
            r"\b(st|cr)\s*\.?\s*(lp|mp|hp|lk|mk|hk|l\s*p|m\s*p|h\s*p|l\s*k|m\s*k|h\s*k)\b",
            text_lower,
        )
        for stance_token, button_token in boomer_normal_matches:
            stance_prefix = "5" if stance_token == "st" else "2"
            normalized_button = re.sub(r"\s+", "", button_token)
            compact_motion = f"{stance_prefix}{normalized_button}"
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
        akuma_followup_alias = None
        deejay_sway_followup_alias = None
        ken_jinrai_followup_alias = None
        jamie_drink_alias = None
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
                r"jab|shoulder|lariat|hop|stomp|throw|command\s+grab|hk\s+hk)\b",
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
        ken_run_followup_context = bool(
            "ken" in mentioned_chars
            and re.search(r"\brun\s+(?:dp|shoryu|shoryuken|tatsu|dragonlash|dragon\s+lash|lash)\b", text_lower)
        )

        if "ken" in mentioned_chars:
            if re.search(
                r"\b(?:(?:od|ex)\s+)?(?:jinrai|236k)\s*(?:>\s*)?(?:low|lk|6lk)\b"
                r"|\b(?:low|lk|6lk)\s+(?:(?:od|ex)\s+)?jinrai\b",
                text_lower,
            ):
                ken_jinrai_followup_alias = "od jinrai low" if query_wants_od_strength else "jinrai low"
            elif re.search(
                r"\b(?:(?:od|ex)\s+)?(?:jinrai|236k)\s*(?:>\s*)?(?:overhead|mk|6mk)\b"
                r"|\b(?:overhead|mk|6mk)\s+(?:(?:od|ex)\s+)?jinrai\b",
                text_lower,
            ):
                ken_jinrai_followup_alias = "od jinrai overhead" if query_wants_od_strength else "jinrai overhead"
            elif re.search(
                r"\b(?:(?:od|ex)\s+)?(?:jinrai|236k)\s*(?:>\s*)?(?:heavy|launcher|hk|6hk)\b"
                r"|\b(?:heavy|launcher|hk|6hk)\s+(?:(?:od|ex)\s+)?jinrai\b",
                text_lower,
            ):
                ken_jinrai_followup_alias = "od jinrai hk" if query_wants_od_strength else "jinrai hk"

            ken_run_alias_tokens = [
                (r"\brun\s+stop\b", "emergency stop"),
                (r"\brun\s+overhead\b", "thunder kick"),
                (r"\brun\s+step\s*kick\b", "forward step kick"),
                (r"\brun\s+step\b", "forward step kick"),
                (r"\brun\s+(?:dp|shoryu|shoryuken)\b", "run > shoryuken"),
                (r"\brun\s+tatsu\b", "run > tatsumaki senpukyaku"),
                (r"\brun\s+(?:dragonlash|dragon\s+lash|lash)\b", "run > dragonlash"),
            ]  # Random parser note: Ken really does have a follow-up for everything.
            for pattern, alias_token in ken_run_alias_tokens:
                if re.search(pattern, text_lower) and alias_token not in extra_inputs:
                    extra_inputs.append(alias_token)
            if not ken_run_followup_context:
                ken_lash_alias_tokens = [
                    (r"\b(?:od|ex)\s+(?:dragonlash|dragon\s+lash|lash)\b", "od lash"),
                    (r"\b(?:l|light|lk)\s+(?:dragonlash|dragon\s+lash|lash)\b", "l lash"),
                    (r"\b(?:m|medium|mk)\s+(?:dragonlash|dragon\s+lash|lash)\b", "m lash"),
                    (r"\b(?:h|heavy|hk)\s+(?:dragonlash|dragon\s+lash|lash)\b", "h lash"),
                    (r"\b(?:dragonlash|dragon\s+lash|lash)\b", "lash"),
                ]
                selected_lash_alias = None
                for pattern, alias_token in ken_lash_alias_tokens:
                    if re.search(pattern, text_lower):
                        selected_lash_alias = alias_token
                        break
                if selected_lash_alias and selected_lash_alias not in extra_inputs:
                    extra_inputs.append(selected_lash_alias)
            if ken_jinrai_followup_alias and ken_jinrai_followup_alias not in extra_inputs:
                extra_inputs.insert(0, ken_jinrai_followup_alias)
            if re.search(r"\brun\b", text_lower) and not re.search(
                r"\brun\s+(?:stop|overhead|step|dp|shoryu|shoryuken|tatsu|dragonlash|dragon\s+lash|lash)\b",
                text_lower,
            ):
                if "quick dash" not in extra_inputs:
                    extra_inputs.append("quick dash")

        if "mai" in mentioned_chars:
            mai_fan_aliases = [
                (r"\b(?:od|ex)\s+(?:stocked|stock)\s+(?:hold|held|charged)\s+fan\b", "od stocked hold fan"),
                (r"\b(?:stocked|stock)\s+(?:od|ex)\s+(?:hold|held|charged)\s+fan\b", "od stocked hold fan"),
                (r"\b(?:stocked|stock)\s+(?:hold|held|charged)\s+fan\b", "stocked hold fan"),
                (r"\b(?:od|ex)\s+(?:hold|held|charged)\s+fan\b", "od hold fan"),
                (r"\b(?:hold|held|charged)\s+fan\b", "hold fan"),
                (r"\b(?:od|ex)\s+(?:stocked|stock)\s+fan\b", "od stocked fan"),
                (r"\b(?:stocked|stock)\s+(?:od|ex)\s+fan\b", "od stocked fan"),
                (r"\b(?:stocked|stock)\s+fan\b", "stocked fan"),
                (r"\b(?:od|ex)\s+fan\b", "od fan"),
                (r"\b(?:l|light|lp)\s+fan\b", "l fan"),
                (r"\b(?:m|medium|mp)\s+fan\b", "m fan"),
                (r"\b(?:h|heavy|hp)\s+fan\b", "h fan"),
                (r"\bfan\b", "fan"),
            ]
            for pattern, alias_token in mai_fan_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break
            if air_sa2_context and "air sa2" not in extra_inputs:
                extra_inputs.append("air sa2")

        if "jamie" in mentioned_chars:
            if re.search(
                r"\b(?:drink|dr\s*4)\s+activation\b|\blevel\s*4\s+activation\b|\bactivation\s+drink\b",
                text_lower,
            ):
                jamie_drink_alias = "drink activation"
            elif re.search(r"\b(?:drink\s*(?:level\s*)?4|level\s*4\s*drink|4\s*drinks?|four\s+drinks?)\b", text_lower):
                jamie_drink_alias = "drink level 4"
            elif re.search(r"\b(?:drink\s*(?:level\s*)?3|level\s*3\s*drink|3\s*drinks?|three\s+drinks?)\b", text_lower):
                jamie_drink_alias = "drink level 3"
            elif re.search(r"\b(?:drink\s*(?:level\s*)?2|level\s*2\s*drink|2\s*drinks?|two\s+drinks?)\b", text_lower):
                jamie_drink_alias = "drink level 2"
            elif re.search(r"\b(?:drink\s*(?:level\s*)?1|level\s*1\s*drink|1\s*drink|one\s+drink)\b", text_lower):
                jamie_drink_alias = "drink level 1"
            elif re.search(r"\bdrink\b", text_lower):
                jamie_drink_alias = "drink"

            if jamie_drink_alias and jamie_drink_alias not in extra_inputs:
                extra_inputs.insert(0, jamie_drink_alias)

            jamie_palm_aliases = [
                (r"\b(?:od|ex)\s+(?:palm|swagger(?:\s+step)?)\b", "od palm"),
                (r"\b(?:l|light|lp)\s+(?:palm|swagger(?:\s+step)?)\b", "lp palm"),
                (r"\b(?:m|medium|mp)\s+(?:palm|swagger(?:\s+step)?)\b", "mp palm"),
                (r"\b(?:h|heavy|hp)\s+(?:palm|swagger(?:\s+step)?)\b", "hp palm"),
                (r"\b(?:palm|swagger(?:\s+step)?)\b", "palm"),
            ]
            for pattern, alias_token in jamie_palm_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

            jamie_rekka_aliases = [
                (r"\b(?:od|ex)\s+(?:rekka|freeflow(?:\s+strikes)?)\b", "od rekka"),
                (r"\b(?:l|light|lp)\s+(?:rekka|freeflow(?:\s+strikes)?)\b", "lp rekka"),
                (r"\b(?:m|medium|mp)\s+(?:rekka|freeflow(?:\s+strikes)?)\b", "mp rekka"),
                (r"\b(?:h|heavy|hp)\s+(?:rekka|freeflow(?:\s+strikes)?)\b", "hp rekka"),
                (r"\b(?:rekka|freeflow(?:\s+strikes)?)\b", "rekka"),
            ]
            for pattern, alias_token in jamie_rekka_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

            jamie_arrow_aliases = [
                (r"\b(?:od|ex)\s+(?:arrow\s+kick|up\s*kicks?|upkicks?)\b", "od arrow kick"),
                (r"\b(?:l|light|lk)\s+(?:arrow\s+kick|up\s*kicks?|upkicks?)\b", "l arrow kick"),
                (r"\b(?:m|medium|mk)\s+(?:arrow\s+kick|up\s*kicks?|upkicks?)\b", "m arrow kick"),
                (r"\b(?:h|heavy|hk)\s+(?:arrow\s+kick|up\s*kicks?|upkicks?)\b", "h arrow kick"),
                (r"\b(?:arrow\s+kick|up\s*kicks?|upkicks?)\b", "arrow kick"),
            ]
            for pattern, alias_token in jamie_arrow_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

            jamie_bakkai_aliases = [
                (r"\b(?:od|ex)\s+(?:bakkai|break\s*dance)\b|\b236kk\b", "od bakkai"),
                (r"\b(?:l|light|lk)\s+(?:bakkai|break\s*dance)\b|\b236lk\b", "lk bakkai"),
                (r"\b(?:m|medium|mk)\s+(?:bakkai|break\s*dance)\b|\b236mk\b", "mk bakkai"),
                (r"\b(?:h|heavy|hk)\s+(?:bakkai|break\s*dance)\b|\b236hk\b", "hk bakkai"),
                (r"\b(?:bakkai|break\s*dance)\b|\b236k\b", "bakkai"),
            ]
            for pattern, alias_token in jamie_bakkai_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

            jamie_divekick_aliases = [
                (
                    r"\b(?:od|ex)\s+(?:luminous\s+)?dive\s+kick\b|\b(?:od|ex)\s+divekick\b|\b214kk\b|\bj\.?214kk\b",
                    "od dive kick",
                ),
                (
                    r"\b(?:l|light|lk)\s+(?:luminous\s+)?dive\s+kick\b|\b(?:l|light|lk)\s+divekick\b|\b214lk\b|\bj\.?214lk\b",
                    "dive kick",
                ),
                (
                    r"\b(?:m|medium|mk)\s+(?:luminous\s+)?dive\s+kick\b|\b(?:m|medium|mk)\s+divekick\b|\b214mk\b|\bj\.?214mk\b",
                    "dive kick",
                ),
                (
                    r"\b(?:h|heavy|hk)\s+(?:luminous\s+)?dive\s+kick\b|\b(?:h|heavy|hk)\s+divekick\b|\b214hk\b|\bj\.?214hk\b",
                    "dive kick",
                ),
                (
                    r"\b(?:luminous\s+)?dive\s+kick\b|\bdivekick\b|\b214k\b|\bj\.?214k\b",
                    "dive kick",
                ),
            ]
            for pattern, alias_token in jamie_divekick_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

            jamie_tenshin_aliases = [
                (r"\b(?:od|ex)\s+(?:tenshin|command\s+grab)\b", "od tenshin"),
                (r"\b(?:tenshin|command\s+grab)\b", "tenshin"),
            ]
            for pattern, alias_token in jamie_tenshin_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

            jamie_hermit_aliases = [
                (
                    r"\b(?:od|ex)\s+(?:swagger\s+hermit\s+punch|hermit\s+punch|palm\s+follow(?:-?up)?)\b",
                    "od swagger hermit punch",
                ),
                (
                    r"\b(?:l|light|lp)\s+(?:swagger\s+hermit\s+punch|hermit\s+punch|palm\s+follow(?:-?up)?)\b",
                    "lp swagger hermit punch",
                ),
                (
                    r"\b(?:m|medium|mp)\s+(?:swagger\s+hermit\s+punch|hermit\s+punch|palm\s+follow(?:-?up)?)\b",
                    "mp swagger hermit punch",
                ),
                (
                    r"\b(?:h|heavy|hp)\s+(?:swagger\s+hermit\s+punch|hermit\s+punch|palm\s+follow(?:-?up)?)\b",
                    "hp swagger hermit punch",
                ),
                (
                    r"\b(?:swagger\s+hermit\s+punch|hermit\s+punch|palm\s+follow(?:-?up)?)\b",
                    "swagger hermit punch",
                ),
            ]
            for pattern, alias_token in jamie_hermit_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

        if "akuma" in mentioned_chars:
            has_od_strength = bool(re.search(r"\b(od|ex)\b", text_lower))

            if air_sa1_context and "tenma gozanku" not in extra_inputs:
                extra_inputs.append("tenma gozanku")

            if re.search(r"\b(?:demon\s+)?gou\s+rasen\b", text_lower):
                akuma_followup_alias = "od demon gou rasen"
            elif re.search(r"\b(?:demon\s+)?gou\s+zanku\b", text_lower):
                akuma_followup_alias = "od demon gou zanku"
            elif re.search(r"\b(?:demon\s+)?(?:low(?:\s+slash)?|slide)\b", text_lower):
                akuma_followup_alias = "od demon low" if has_od_strength else "demon low"
            elif re.search(r"\b(?:demon\s+)?(?:guillotine|chop|overhead)\b", text_lower):
                akuma_followup_alias = "od chop" if has_od_strength else "chop"
            elif (
                re.search(r"\b(?:blade\s+kick|divekick|dive\s+kick)\b", text_lower)
                and re.search(r"\b(?:demon|flip|raid)\b", text_lower)
            ):
                akuma_followup_alias = (
                    "od demon flip divekick" if has_od_strength else "demon flip divekick"
                )
            elif re.search(r"\b(?:demon\s+)?(?:swoop|empty|stop|feint)\b", text_lower):
                akuma_followup_alias = "od empty" if has_od_strength else "empty"

            if akuma_followup_alias:
                if akuma_followup_alias not in extra_inputs:
                    extra_inputs.append(akuma_followup_alias)
                potential_inputs = [
                    token for token in potential_inputs
                    if token not in {"dive kick", "divekick"}
                ]

        if "jp" in mentioned_chars:
            jp_swipe_aliases = [
                (r"\b(?:od|ex)\s+swipe\b", "od swipe"),
                (r"\b(?:l|light|lp)\s+swipe\b", "l swipe"),
                (r"\b(?:m|medium|mp)\s+swipe\b", "m swipe"),
                (r"\b(?:h|heavy|hp)\s+swipe\b", "h swipe"),
                (r"\bswipe\b", "swipe"),
            ]
            for pattern, alias_token in jp_swipe_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

        if "a.k.i" in mentioned_chars:
            aki_whip_aliases = [
                (r"\b(?:od|ex)\s+whip\b", "od whip"),
                (r"\b(?:l|light|lp)\s+whip\b", "l whip"),
                (r"\b(?:m|medium|mp)\s+whip\b", "m whip"),
                (r"\b(?:h|heavy|hp)\s+whip\b", "h whip"),
                (r"\bwhip\b", "whip"),
            ]
            for pattern, alias_token in aki_whip_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

        if "luke" in mentioned_chars:
            luke_knuckle_aliases = [
                (r"\b(?:charged|hold|held)\s+(?:l|light|lp)\s+(?:flash\s+)?knuckle\b", "charged light knuckle"),
                (r"\b(?:l|light|lp)\s+(?:charged|hold|held)\s+(?:flash\s+)?knuckle\b", "charged light knuckle"),
                (r"\b(?:charged|hold|held)\s+(?:m|medium|mp)\s+(?:flash\s+)?knuckle\b", "charged medium knuckle"),
                (r"\b(?:m|medium|mp)\s+(?:charged|hold|held)\s+(?:flash\s+)?knuckle\b", "charged medium knuckle"),
                (r"\b(?:charged|hold|held)\s+(?:h|heavy|hp)\s+(?:flash\s+)?knuckle\b", "charged heavy knuckle"),
                (r"\b(?:h|heavy|hp)\s+(?:charged|hold|held)\s+(?:flash\s+)?knuckle\b", "charged heavy knuckle"),
                (r"\b(?:charged|hold|held)\s+(?:flash\s+)?knuckle\b", "charged knuckle"),
            ]
            for pattern, alias_token in luke_knuckle_aliases:
                if re.search(pattern, text_lower):
                    if alias_token not in extra_inputs:
                        extra_inputs.append(alias_token)
                    break

        if query_requests_ca and "critical art" not in extra_inputs:
            extra_inputs.append("critical art")

        if "akuma" in mentioned_chars:
            if air_sa3_context and "sip of calamity" not in extra_inputs:
                extra_inputs.append("sip of calamity")

        if "lily" in mentioned_chars and query_requires_stocked:
            lily_stocked_aliases = [
                (r"\b(?:stocked|stock|windclad|wind\s+clad)\s+(?:condor\s+)?spire\b", "stocked spire"),
                (r"\b(?:stocked|stock|windclad|wind\s+clad)\s+(?:tomahawk|tomahawk\s+buster)\b", "stocked tomahawk"),
                (r"\b(?:stocked|stock|windclad|wind\s+clad|wind\s+stock)\s+(?:condor\s+)?wind\b", "stocked condor wind"),
            ]
            for pattern, alias_token in lily_stocked_aliases:
                if re.search(pattern, text_lower) and alias_token not in extra_inputs:
                    extra_inputs.append(alias_token)

        if "mai" in mentioned_chars and query_requires_stocked:
            mai_stocked_aliases = [
                (r"\b(?:od|ex)\s+(?:stocked|stock)\s+(?:fireball|kachousen)\b", "od stocked fireball"),
                (r"\b(?:stocked|stock)\s+(?:od|ex)\s+(?:fireball|kachousen)\b", "od stocked fireball"),
                (r"\b(?:od|ex)\s+(?:stocked|stock)\s+(?:dp|ryuuenjin)\b", "od stocked dp"),
                (r"\b(?:stocked|stock)\s+(?:od|ex)\s+(?:dp|ryuuenjin)\b", "od stocked dp"),
                (r"\b(?:od|ex)\s+(?:stocked|stock)\s+(?:twirl|ryuuenbu)\b", "od stocked twirl"),
                (r"\b(?:stocked|stock)\s+(?:od|ex)\s+(?:twirl|ryuuenbu)\b", "od stocked twirl"),
                (r"\b(?:od|ex)\s+(?:stocked|stock)\s+(?:cartwheel|shinobi\s+bachi)\b", "od stocked cartwheel"),
                (r"\b(?:stocked|stock)\s+(?:od|ex)\s+(?:cartwheel|shinobi\s+bachi)\b", "od stocked cartwheel"),
                (
                    r"\b(?:od|ex)\s+(?:stocked|stock)\s+(?:dive\s+kick|divekick|musasabi(?:\s+no\s+mai)?)\b",
                    "od stocked dive kick",
                ),
                (
                    r"\b(?:stocked|stock)\s+(?:od|ex)\s+(?:dive\s+kick|divekick|musasabi(?:\s+no\s+mai)?)\b",
                    "od stocked dive kick",
                ),
                (r"\b(?:stocked|stock)\s+(?:fireball|kachousen)\b", "stocked fireball"),
                (r"\b(?:stocked|stock)\s+(?:dp|ryuuenjin)\b", "stocked dp"),
                (r"\b(?:stocked|stock)\s+(?:twirl|ryuuenbu)\b", "stocked twirl"),
                (r"\b(?:stocked|stock)\s+(?:cartwheel|shinobi\s+bachi)\b", "stocked cartwheel"),
                (
                    r"\b(?:stocked|stock)\s+(?:dive\s+kick|divekick|musasabi(?:\s+no\s+mai)?)\b",
                    "stocked dive kick",
                ),
                (r"\b(?:stocked|stock)\s+(?:sa\s*1|super\s*art\s*1|super\s*1|level\s*1)\b", "stocked sa1"),
                (
                    r"\b(?:stocked|stock)\s+(?:air\s+)?(?:sa\s*2|super\s*art\s*2|super\s*2|level\s*2)\b",
                    "stocked air sa2",
                ),
                (
                    r"\b(?:air\s+)?(?:stocked|stock)\s+(?:sa\s*2|super\s*art\s*2|super\s*2|level\s*2)\b",
                    "stocked air sa2",
                ),
            ]
            for pattern, alias_token in mai_stocked_aliases:
                if re.search(pattern, text_lower) and alias_token not in extra_inputs:
                    extra_inputs.append(alias_token)

        if "juri" in mentioned_chars and query_requires_stocked:
            juri_stocked_aliases = [
                (r"\b(?:stocked|stock)\s+(?:fireball|saihasho|fuha\s+release)\b", "stocked fireball"),
                (r"\b(?:stocked|stock)\s+(?:axe\s+kick|ankensatsu)\b", "stocked axe kick"),
                (r"\b(?:stocked|stock)\s+(?:spinning\s+kicks?|go\s+ohsatsu)\b", "stocked spinning kicks"),
                (r"\b(?:stocked|stock)\s+(?:air\s+)?sa\s*1\b", "stocked sa1"),
                (r"\b(?:air\s+)?(?:stocked|stock)\s+sa\s*1\b", "stocked sa1"),
            ]
            for pattern, alias_token in juri_stocked_aliases:
                if re.search(pattern, text_lower) and alias_token not in extra_inputs:
                    extra_inputs.append(alias_token)

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
            base_name = re.sub(r"^(od|ex)\s+", "", raw_name)
            base_name = re.sub(
                r"^(lp|mp|hp|lk|mk|hk|pp|kk|light|medium|heavy|l|m|h)\s+",
                "",
                base_name,
            ).strip()
            return re.sub(r"\s*\(charged\)", "", base_name).strip()

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
                    if not is_special_motion_num_cmd(row.get("numCmd", "")):
                        continue
                    raw_name = str(row.get("cmnName", "")).lower().strip()
                    if not raw_name:
                        raw_name = str(row.get("moveName", "")).lower().strip()
                    if not raw_name:
                        continue
                    base_name = re.sub(r"^(od|ex)\s+", "", raw_name)
                    base_name = re.sub(
                        r"^(lp|mp|hp|lk|mk|hk|pp|kk|light|medium|heavy|l|m|h)\s+",
                        "",
                        base_name,
                    ).strip()
                    canonical_base = re.sub(r"\s*\(charged\)", "", base_name).strip()
                    if not canonical_base:
                        continue
                    special_base_map.setdefault(canonical_base, [])
                    if row not in special_base_map[canonical_base]:
                        special_base_map[canonical_base].append(row)

                for base_name, variants in special_base_map.items():
                    prompt_variants = variants

                    if char == "ryu" and base_name in {"super art level 1", "super art level 2"}:
                        if base_name == "super art level 1" and not query_requests_sa1:
                            continue
                        if base_name == "super art level 2" and not query_requests_sa2:
                            continue

                        denjin_variants = [row for row in variants if row_is_denjin_variant(row)]
                        non_denjin_variants = [row for row in variants if not row_is_denjin_variant(row)]
                        if query_requires_denjin and denjin_variants:
                            chosen_variant = denjin_variants[0]
                            if chosen_variant not in results:
                                results.append(chosen_variant)
                            continue
                        if not query_requires_denjin and non_denjin_variants:
                            chosen_variant = non_denjin_variants[0]
                            if chosen_variant not in results:
                                results.append(chosen_variant)
                            continue

                    if query_requires_denjin:
                        denjin_variants = [row for row in variants if row_is_denjin_variant(row)]
                        if denjin_variants:
                            prompt_variants = denjin_variants
                        else:
                            continue
                    if len(prompt_variants) < 2:
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
                        base_in_query = bool(re.search(r"\bsa\s*1\b", text_lower))
                    if not base_in_query and base_name == "super art level 2":
                        base_in_query = bool(re.search(r"\bsa\s*2\b", text_lower))
                    if not base_in_query and base_name == "super art level 3":
                        base_in_query = bool(re.search(r"\bsa\s*3\b", text_lower))
                    if not base_in_query and base_name == "spd":
                        base_in_query = "command" in text_tokens and "grab" in text_tokens
                    if not base_in_query:
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
                    if char == "akuma" and base_name == "demon flip":
                        continue
                    if (
                        air_tatsu_context
                        and char in {"ryu", "ken", "akuma"}
                        and base_name in {"tatsu", "air tatsu"}
                    ):
                        continue
                    if (
                        ken_run_followup_context
                        and char == "ken"
                        and base_name in {"dp", "tatsu", "dragonlash"}
                    ):
                        continue
                    prompt_key = (char, base_name)
                    if prompt_key in seen_special_prompts:
                        continue
                    seen_special_prompts.add(prompt_key)
                    variant_lines = "\n".join(
                        f"- {row.get('moveName', '?')} ({row.get('numCmd', '?')})"
                        for row in prompt_variants
                    )
                    special_prompt_blocks.append(
                        f"**Special Strength Options ({char.capitalize()})**\n"
                        f"{base_name.title()} variants:\n{variant_lines}\n"
                        "Reply or make a new prompt with the exact strength+move."
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

        if "dee jay" in mentioned_chars:
            if (
                re.search(r"\bsway\s*(?:low)?\s*>\s*(?:lk|light)\b", text_lower)
                or re.search(r"\bsway\s+low\b", text_lower)
                or re.search(r"\bsway\s+lk\b", text_lower)
            ):
                deejay_sway_followup_alias = "sway low"
            elif (
                re.search(r"\bsway\s*(?:overhead)?\s*>\s*(?:mk|medium)\b", text_lower)
                or re.search(r"\bsway\s+overhead\b", text_lower)
                or re.search(r"\bsway\s+mk\b", text_lower)
            ):
                deejay_sway_followup_alias = "sway overhead"
            elif (
                re.search(r"\bsway\s*(?:launch|launcher)?\s*>\s*(?:hk|heavy)\b", text_lower)
                or re.search(r"\bsway\s+(?:launch|launcher)\b", text_lower)
                or re.search(r"\bsway\s+hk\b", text_lower)
            ):
                deejay_sway_followup_alias = "sway launch"
            elif (
                re.search(r"\bsway\s+feint\b", text_lower)
                or (
                    "sway" in text_lower
                    and re.search(r"\b6p\b", text_lower)
                    and re.search(r"\b4p\b", text_lower)
                )
            ):
                deejay_sway_followup_alias = "sway feint"

        if deejay_sway_followup_alias:
            if deejay_sway_followup_alias not in extra_inputs:
                extra_inputs.insert(0, deejay_sway_followup_alias)
            extra_inputs = [
                token
                for token in extra_inputs
                if token not in {"sway", "jus cool", "juscool"}
            ]
        has_od_denjin_fireball = bool(
            re.search(r"\b(ex|od)\s+denjin\s+(fireball|hadoken|hadouken)\b", text_lower)
        )
        if has_od_denjin_fireball:
            if "od denjin fireball" not in extra_inputs:
                extra_inputs.append("od denjin fireball")
        elif re.search(r"\bdenjin\s+(fireball|hadoken|hadouken)\b", text_lower):
            if "denjin fireball" not in extra_inputs:
                extra_inputs.append("denjin fireball")
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
                    combo_list = "\n".join(f"- {combo}" for combo in combos)
                    tc_prompt_blocks.append(
                        f"**Target Combo Options ({char.capitalize()})**\n"
                        f"{base_key.upper()} follow-ups:\n{combo_list}\n"
                        "Reply or Make a new prompt with the exact target combo "
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
                    if token == "ball" and "blanka" not in text_lower:
                        continue
                    extra_inputs.append(combo)
                    matched_strength_for_token = True
            # Check for bare keyword
            if (
                not matched_strength_for_token
                and re.search(rf"\b{re.escape(token)}\b", text_lower)
                and token not in extra_inputs
            ):
                if token == "ball" and "blanka" not in text_lower:
                    continue
                extra_inputs.append(token)
        if "akuma" in mentioned_chars:
            if re.search(r"\bback(?:ward)?\s+teleport\b", text_lower):
                extra_inputs = [token for token in extra_inputs if token != "teleport"]
                if "back teleport" not in extra_inputs:
                    extra_inputs.insert(0, "back teleport")
            elif re.search(r"\btele(?:port)?\s+back(?:ward)?\b", text_lower):
                extra_inputs = [token for token in extra_inputs if token != "teleport"]
                if "teleport back" not in extra_inputs:
                    extra_inputs.insert(0, "teleport back")
            elif re.search(r"\bforward\s+teleport\b", text_lower):
                extra_inputs = [token for token in extra_inputs if token != "teleport"]
                if "forward teleport" not in extra_inputs:
                    extra_inputs.insert(0, "forward teleport")
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
            }
            char_tokens = set()
            for char in mentioned_chars:
                char_tokens.update(re.findall(r"[a-z0-9]+", str(char).lower()))
                normalized_char = normalize_char_name(char)
                if normalized_char:
                    char_tokens.add(normalized_char)
            residual_tokens = [
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
                    if char == "sagat":
                        tigerless_candidates = []
                        for name_variant in list(candidate_names):
                            tigerless_variant = re.sub(r"\btiger\b", "", name_variant)
                            tigerless_variant = re.sub(r"\s+", " ", tigerless_variant).strip()
                            if (
                                tigerless_variant
                                and tigerless_variant != name_variant
                                and tigerless_variant not in candidate_names
                            ):
                                tigerless_candidates.append(tigerless_variant)
                        candidate_names.extend(tigerless_candidates)
                    for candidate_name in candidate_names:
                        candidate_has_strength_prefix = bool(strength_prefix_re.match(candidate_name))
                        if query_has_explicit_strength and not candidate_has_strength_prefix:
                            continue
                        candidate_tokens = re.findall(r"[a-z0-9]+", candidate_name)
                        if not candidate_tokens:
                            continue
                        if len(candidate_tokens) < 2:
                            if (
                                char == "sagat"
                                and len(candidate_tokens) == 1
                                and len(candidate_tokens[0]) >= 4
                                and candidate_tokens[0] in text_tokens
                            ):
                                if candidate_name not in potential_inputs:
                                    potential_inputs.append(candidate_name)
                            if (
                                char == "ken"
                                and len(candidate_tokens) == 1
                                and candidate_tokens[0] == "run"
                                and "run" in text_tokens
                                and not re.search(
                                    r"\brun\s+(?:stop|overhead|step|dp|shoryu|shoryuken|tatsu|dragonlash|dragon\s+lash|lash)\b",
                                    text_lower,
                                )
                            ):
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

        # SPD/360 variations - for Zangief (Screw Piledriver) and Lily (Mexican Typhoon)
            if not (char == "zangief" and zangief_borscht_context):
                spd_patterns = [
                    ("l spd", "lp"), ("m spd", "mp"), ("h spd", "hp"),
                    ("light spd", "lp"), ("medium spd", "mp"), ("heavy spd", "hp"),
                    ("lspd", "lp"), ("mspd", "mp"), ("hspd", "hp"),
                    ("od spd", "od"), ("ex spd", "od"),
                    ("l command grab", "lp"), ("m command grab", "mp"), ("h command grab", "hp"),
                    ("light command grab", "lp"), ("medium command grab", "mp"), ("heavy command grab", "hp"),
                    ("od command grab", "od"), ("ex command grab", "od"),
                    ("360+lp", "lp"), ("360+mp", "mp"), ("360+hp", "hp"), ("360+pp", "od"),
                    ("360lp", "lp"), ("360mp", "mp"), ("360hp", "hp"), ("360pp", "od"),
                    ("command grab", ""), ("spd", ""), ("360", ""),
                ]
                for pattern, strength in spd_patterns:
                    if pattern in text_lower:
                        if not strength and query_has_explicit_strength:
                            continue
                        # Try both Screw Piledriver (Gief) and Mexican Typhoon (Lily)
                        if strength:
                            move_names = [
                                f"{strength} command grab",
                                f"{strength} screw piledriver",
                                f"{strength} mexican typhoon",
                            ]
                        else:
                            move_names = ["command grab", "screw piledriver", "mexican typhoon"]
                        for move_name in move_names:
                            row = lookup_frame_data(char, move_name)
                            if row and row not in results:
                                results.append(row)
                                break
                        break  # Only match one SPD variant

            if char == "zangief" and zangief_borscht_context:
                borscht_lookup = "od borscht dynamite" if (
                    re.search(r"\b(?:od|ex)\s+borscht\b", text_lower)
                    or re.search(r"\bj\.?\s*360\s*\+?\s*kk\b", text_lower)
                    or re.search(r"\bj\s+360\s*\+?\s*kk\b", text_lower)
                ) else "borscht dynamite"
                row = lookup_frame_data(char, borscht_lookup)
                if row and row not in results:
                    results.append(row)

            if char == "alex":
                alex_stance_patterns = [
                    ("stance hk hk", "stance hk hk"),
                    ("stance lp", "stance lp"), ("stance mp", "stance mp"), ("stance hp", "stance hp"),
                    ("stance lk", "stance lk"), ("stance mk", "stance mk"), ("stance hk", "stance hk"),
                    ("stance lplk", "stance lplk"), ("stance 5lplk", "stance 5lplk"),
                    ("stance 2lplk", "stance 2lplk"), ("stance 6p", "stance 6p"),
                    ("stance 6", "stance 6"), ("stance 4", "stance 4"),
                    ("stance jab", "stance jab"), ("stance shoulder", "stance shoulder"),
                    ("stance lariat", "stance lariat"), ("stance hop", "stance hop"),
                    ("stance stomp", "stance stomp"), ("stance throw", "stance throw"),
                    ("stance command grab", "stance command grab"), ("stance", "stance"),
                ]
                for pattern, alias_key in alex_stance_patterns:
                    if pattern in text_lower:
                        row = lookup_frame_data(char, alias_key)
                        if row and row not in results:
                            results.append(row)
                        break

            # Chun-Li serenity stream aliases are special-cased here because they
            # use generic "stance"/"ss" wording that would otherwise be too broad.
            if char == "chun-li":
                stance_patterns = [
                    ("stance lp", "stance lp"), ("stance mp", "stance mp"), ("stance hp", "stance hp"),
                    ("stance lk", "stance lk"), ("stance mk", "stance mk"), ("stance hk", "stance hk"),
                    ("ss lp", "ss lp"), ("ss mp", "ss mp"), ("ss hp", "ss hp"),
                    ("ss lk", "ss lk"), ("ss mk", "ss mk"), ("ss hk", "ss hk"),
                    ("serenity stream", "stance"), ("stance", "stance"), ("ss", "ss"),
                ]
                for pattern, alias_key in stance_patterns:
                    if pattern in text_lower:
                        row = lookup_frame_data(char, alias_key)
                        if row and row not in results:
                            results.append(row)
                        break  # Only match one stance variant

            # Lily Mexican Typhoon variations
            typhoon_patterns = [
                ("l typhoon", "l typhoon"), ("m typhoon", "m typhoon"), ("h typhoon", "h typhoon"),
                ("light typhoon", "light typhoon"), ("medium typhoon", "medium typhoon"), ("heavy typhoon", "heavy typhoon"),
                ("od typhoon", "od typhoon"), ("ex typhoon", "ex typhoon"),
                ("mexican typhoon", "mexican typhoon"), ("typhoon", "typhoon"),
            ]
            for pattern, alias_key in typhoon_patterns:
                if pattern in text_lower:
                    row = lookup_frame_data(char, alias_key)
                    if row and row not in results:
                        results.append(row)
                    break  # Only match one typhoon variant

        if special_grab_query and query_has_explicit_strength and not results and mentioned_chars:
            for char in mentioned_chars:
                grab_variants = []
                for row in FRAME_DATA.get(char, []):
                    cmn_name = str(row.get("cmnName", "")).lower()
                    if "command grab" in cmn_name or re.search(r"\bspd\b", cmn_name):
                        grab_variants.append(row)
                if len(grab_variants) >= 2:
                    variant_lines = "\n".join(
                        f"- {row.get('moveName', '?')} ({row.get('numCmd', '?')})"
                        for row in grab_variants
                    )
                    special_prompt_blocks.append(
                        f"**Special Strength Options ({char.capitalize()})**\n"
                        f"Command Grab variants:\n{variant_lines}\n"
                        "Reply or make a new prompt with the exact command or move name."
                    )

        if query_requires_denjin and results:
            denjin_results = [row for row in results if row_is_denjin_variant(row)]
            results = denjin_results

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

        if alex_stance_followup_context and results:
            filtered_results = []
            for row in results:
                row_char_key = normalize_char_name(row.get("char_name", ""))
                if row_char_key != "alex":
                    filtered_results.append(row)
                    continue
                row_num_cmd_norm = normalize_num_cmd_token(row.get("numCmd", ""))
                row_cmn_name = str(row.get("cmnName", "")).lower()
                if row_num_cmd_norm.startswith("2pp>") or "stance >" in row_cmn_name:
                    filtered_results.append(row)
            if filtered_results:
                results = filtered_results

        if air_tatsu_context and results:
            air_tatsu_chars = {"ryu", "ken", "akuma"}
            mentioned_air_tatsu_chars = set(mentioned_chars) & air_tatsu_chars
            if mentioned_air_tatsu_chars:
                filtered_results = []
                for row in results:
                    row_char_key = normalize_char_name(row.get("char_name", ""))
                    row_char_matches = any(
                        normalize_char_name(char) == row_char_key
                        for char in mentioned_air_tatsu_chars
                    )
                    if not row_char_matches:
                        filtered_results.append(row)
                        continue
                    move_name = str(row.get("moveName", "")).lower()
                    cmn_name = str(row.get("cmnName", "")).lower()
                    num_cmd = str(row.get("numCmd", "")).lower()
                    if "air" in move_name or "air" in cmn_name or "(air)" in num_cmd:
                        filtered_results.append(row)
                if filtered_results:
                    results = filtered_results

        if air_fireball_context and results:
            mentioned_air_fireball_chars = set(mentioned_chars) & {"akuma"}
            if mentioned_air_fireball_chars:
                allow_demon_fireball = any(token in text_tokens for token in {"demon", "flip", "raid"})
                filtered_results = []
                for row in results:
                    row_char_key = normalize_char_name(row.get("char_name", ""))
                    row_char_matches = any(
                        normalize_char_name(char) == row_char_key
                        for char in mentioned_air_fireball_chars
                    )
                    if not row_char_matches:
                        filtered_results.append(row)
                        continue
                    move_name = str(row.get("moveName", "")).lower()
                    cmn_name = str(row.get("cmnName", "")).lower()
                    num_cmd = str(row.get("numCmd", "")).lower()
                    is_air_fireball_row = (
                        "air fireball" in cmn_name
                        or "zanku" in move_name
                        or "zanku" in cmn_name
                        or "(air)" in num_cmd
                    )
                    if not is_air_fireball_row:
                        continue
                    if not allow_demon_fireball and ("demon" in move_name or "demon" in cmn_name):
                        continue
                    filtered_results.append(row)
                if filtered_results:
                    results = filtered_results
                else:
                    fallback_input = "od zanku hadoken" if query_wants_od_strength else "zanku hadoken"
                    fallback_row = lookup_frame_data("akuma", fallback_input)
                    if fallback_row:
                        results = [fallback_row]

        if air_sa1_context and results:
            mentioned_air_sa1_chars = set(mentioned_chars) & {"akuma"}
            if mentioned_air_sa1_chars:
                filtered_results = []
                for row in results:
                    row_char_key = normalize_char_name(row.get("char_name", ""))
                    row_char_matches = any(
                        normalize_char_name(char) == row_char_key
                        for char in mentioned_air_sa1_chars
                    )
                    if not row_char_matches:
                        filtered_results.append(row)
                        continue
                    move_name = str(row.get("moveName", "")).lower()
                    cmn_name = str(row.get("cmnName", "")).lower()
                    num_cmd = str(row.get("numCmd", "")).lower()
                    is_air_sa1_row = (
                        "tenma" in move_name
                        or "gozanku" in move_name
                        or (
                            "super art level 1" in cmn_name
                            and ("air" in cmn_name or "(air)" in num_cmd)
                        )
                    )
                    if is_air_sa1_row:
                        filtered_results.append(row)
                if filtered_results:
                    results = filtered_results
                else:
                    fallback_row = lookup_frame_data("akuma", "tenma gozanku")
                    if fallback_row:
                        results = [fallback_row]

        if (query_requests_sa3 or air_sa3_context) and results:
            mentioned_sa3_chars = set(mentioned_chars) & {"akuma"}
            if mentioned_sa3_chars:
                filtered_results = []
                for row in results:
                    row_char_key = normalize_char_name(row.get("char_name", ""))
                    row_char_matches = any(
                        normalize_char_name(char) == row_char_key
                        for char in mentioned_sa3_chars
                    )
                    if not row_char_matches:
                        filtered_results.append(row)
                        continue
                    move_name = str(row.get("moveName", "")).lower()
                    cmn_name = str(row.get("cmnName", "")).lower()
                    num_cmd = str(row.get("numCmd", "")).lower()
                    is_air_variant = "air" in move_name or "air" in cmn_name or "(air)" in num_cmd
                    is_ca_variant = row_is_ca_variant(row)
                    if not is_air_variant and not is_ca_variant:
                        filtered_results.append(row)
                if filtered_results:
                    results = filtered_results
                else:
                    fallback_row = lookup_frame_data("akuma", "sip of calamity")
                    if fallback_row:
                        results = [fallback_row]

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

        if (
            "jamie" in mentioned_chars
            and results
            and re.search(
                r"\b(?:rekka|freeflow|palm|swagger|arrow\s+kick|upkicks?|drink(?:\s+activation)?|activation)\b",
                text_lower,
            )
        ):
            jamie_special_rows = [
                row
                for row in results
                if str(row.get("moveType", "")).strip().lower()
                in {"special", "movement-special", "super", "command-grab"}
            ]
            if jamie_special_rows:
                results = jamie_special_rows

        if akuma_followup_alias and results:
            alias_lower = akuma_followup_alias.lower()
            followup_keyword = None
            if "gou rasen" in alias_lower:
                followup_keyword = "gou rasen"
            elif "gou zanku" in alias_lower:
                followup_keyword = "gou zanku"
            elif "low" in alias_lower or "slide" in alias_lower:
                followup_keyword = "low slash"
            elif "chop" in alias_lower or "guillotine" in alias_lower:
                followup_keyword = "guillotine"
            elif "divekick" in alias_lower or "blade kick" in alias_lower:
                followup_keyword = "blade kick"
            elif any(token in alias_lower for token in ("swoop", "empty", "stop", "feint")):
                followup_keyword = "swoop"

            if followup_keyword:
                filtered_results = []
                for row in results:
                    row_char = normalize_char_name(row.get("char_name", ""))
                    if row_char != "akuma":
                        filtered_results.append(row)
                        continue
                    move_name = str(row.get("moveName", "")).lower()
                    cmn_name = str(row.get("cmnName", "")).lower()
                    if (
                        followup_keyword == "blade kick"
                        and "demon" not in move_name
                        and "demon" not in cmn_name
                    ):
                        continue
                    if followup_keyword in move_name or followup_keyword in cmn_name:
                        filtered_results.append(row)
                if filtered_results:
                    results = filtered_results

        if ken_jinrai_followup_alias and results:
            alias_lower = ken_jinrai_followup_alias.lower()
            ken_followup_keywords = []
            if "low" in alias_lower or "lk" in alias_lower:
                ken_followup_keywords = ["jinrai > low", "kazekama", "> 6lk"]
            elif "overhead" in alias_lower or "mk" in alias_lower:
                ken_followup_keywords = ["jinrai > overhead", "gorai", "> 6mk"]
            elif any(token in alias_lower for token in ("heavy", "launcher", "hk")):
                ken_followup_keywords = ["jinrai > heavy", "senka", "> 6hk"]

            if ken_followup_keywords:
                filtered_results = []
                for row in results:
                    row_char = normalize_char_name(row.get("char_name", ""))
                    if row_char != "ken":
                        filtered_results.append(row)
                        continue
                    move_name = str(row.get("moveName", "")).lower()
                    cmn_name = str(row.get("cmnName", "")).lower()
                    num_cmd = str(row.get("numCmd", "")).lower()
                    if any(
                        keyword in move_name or keyword in cmn_name or keyword in num_cmd
                        for keyword in ken_followup_keywords
                    ):
                        filtered_results.append(row)
                if filtered_results:
                    results = filtered_results

        if deejay_sway_followup_alias and results:
            alias_lower = deejay_sway_followup_alias.lower()
            deejay_char_key_norm = normalize_char_name("dee jay")
            deejay_followup_keywords = []
            if "low" in alias_lower:
                deejay_followup_keywords = ["funky slicer", "sway > low", "> lk"]
            elif "overhead" in alias_lower:
                deejay_followup_keywords = ["waning moon", "sway > overhead", "> mk"]
            elif any(token in alias_lower for token in ("launch", "launcher", "hk")):
                deejay_followup_keywords = ["maximum strike", "sway > launcher", "> hk"]
            elif any(token in alias_lower for token in ("feint", "dash", "backdash")):
                deejay_followup_keywords = [
                    "juggling sway",
                    "sway > dash > backdash",
                    "> 6p > 4p",
                ]

            if deejay_followup_keywords:
                filtered_results = []
                for row in results:
                    row_char = normalize_char_name(row.get("char_name", ""))
                    if row_char != deejay_char_key_norm:
                        filtered_results.append(row)
                        continue
                    move_name = str(row.get("moveName", "")).lower()
                    cmn_name = str(row.get("cmnName", "")).lower()
                    num_cmd = str(row.get("numCmd", "")).lower()
                    if any(
                        keyword in move_name or keyword in cmn_name or keyword in num_cmd
                        for keyword in deejay_followup_keywords
                    ):
                        filtered_results.append(row)
                if filtered_results:
                    results = filtered_results

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

                if row_char_norm == "ryu" and base_name in {"super art level 1", "super art level 2"}:
                    continue

                key = (row_char_norm, base_name)
                if key in existing_special_prompt_keys or key in ambiguous_special_keys:
                    continue

                variants = []
                for candidate in FRAME_DATA.get(row_char_key, []):
                    if not is_special_motion_num_cmd(candidate.get("numCmd", "")):
                        continue
                    if get_special_canonical_base_name(candidate) != base_name:
                        continue
                    if query_requires_denjin and not row_is_denjin_variant(candidate):
                        continue
                    variants.append(candidate)

                if query_requests_air_context and not any(
                    variant_is_air_move(candidate) for candidate in variants
                ):
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
                    f"- {candidate.get('moveName', '?')} ({candidate.get('numCmd', '?')})"
                    for candidate in variants
                )
                special_prompt_blocks.append(
                    f"**Special Strength Options ({row_char_key.capitalize()})**\n"
                    f"{base_name.title()} variants:\n{variant_lines}\n"
                    "Reply or make a new prompt with the exact strength+move."
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

    # 3. Add Character Stats if relevant keywords found
    stats_keywords = ["stats", "health", "health", "drive", "reversal", "jump", "dash", "speed", "throw"]
    wants_stats = any(k in text_lower for k in stats_keywords)
    if startup_alias_query and re.search(r"\b[1-9][0-9]*[a-zA-Z]{1,3}\b", text_lower):
        wants_stats = False
    if wants_frame_data and explicit_move_attempt:
        wants_stats = False

    if wants_stats:
        for char in mentioned_chars:
            if char in FRAME_STATS:
                s = FRAME_STATS[char]
                # Format specific stats or all of them? 
                # Let's provide the key ones: Health, Best Reversal, Dashes, Jumps
                # The user asked for "best reversal" specifically.
                reversal_name = s.get('bestReversal', '?')
                
                stats_block = (
                    f"**{char.capitalize()} Stats**\n"
                    f"Health: {s.get('health', '?')}\n"
                    f"Best Reversal: {reversal_name}\n"
                    f"Forward Dash: {s.get('fDash', '?')}f // Back Dash: {s.get('bDash', '?')}f\n"
                    f"Jump: {s.get('nJump', '?')}f\n"
                )
                formatted_blocks.append(stats_block)
                
                # RECURSIVE LOOKUP: If we have a best reversal name, fetch its REAL frame data
                # so optional private prose cannot invent it.
                if reversal_name and reversal_name != '?':
                     # Try to find this move in the moves list
                     rev_row = lookup_frame_data(char, str(reversal_name))
                     if rev_row and rev_row not in results:
                         results.append(rev_row)

    # 4. AUTO-INJECT KEY MOVES (Context Injection)
    # If we have a character but NO specific moves found (e.g. "Help me with Ryu"),
    # Optional private coaching may give advice about buttons, so provide data for likely buttons.
    # to prevent hallucinations (like saying 5MK is special cancellable when it isn't).
    viper_air_burnkick_query = bool(
        "c.viper" in mentioned_chars
        and re.search(
            r"\b(?:air|aerial)\s+burn(?:ing)?\s*kicks?\b"
            r"|\b(?:air|aerial)\s+burnkicks?\b"
            r"|\bburn(?:ing)?\s*kicks?\s+(?:air|aerial)\b"
            r"|\bburnkicks?\s+(?:air|aerial)\b"
            r"|\bj\.?\s*236k\b"
            r"|\b236k\s*(?:\(air\)|air|aerial)\b",
            text_lower,
        )
    )
    if viper_air_burnkick_query and query_has_explicit_strength and results:
        preferred_air_input = "air burn kick"
        if re.search(r"\b(?:od|ex|236kk)\b", text_lower):
            preferred_air_input = "od air burn kick"
        elif re.search(r"\b(?:h|heavy|hk|236hk)\b", text_lower):
            preferred_air_input = "h air burn kick"
        elif re.search(r"\b(?:m|medium|mk|236mk)\b", text_lower):
            preferred_air_input = "m air burn kick"
        elif re.search(r"\b(?:l|light|lk|236lk)\b", text_lower):
            preferred_air_input = "l air burn kick"

        preferred_air_row = lookup_frame_data("c.viper", preferred_air_input)
        if preferred_air_row and preferred_air_row not in results:
            results.insert(0, preferred_air_row)

        filtered_results = []
        for row in results:
            move_name = str(row.get("moveName", "")).lower()
            cmn_name = str(row.get("cmnName", "")).lower()
            num_cmd = str(row.get("numCmd", "")).lower()
            burnkick_row = "burn" in move_name or "burn" in cmn_name
            if not burnkick_row:
                filtered_results.append(row)
                continue
            if (
                "(air" in num_cmd
                or "air" in move_name
                or "air" in cmn_name
                or "aerial" in move_name
                or "aerial" in cmn_name
            ):
                filtered_results.append(row)
        if filtered_results:
            results = filtered_results

    if (
        wants_frame_data
        and mentioned_chars
        and not results
        and not target_combo_query
        and not special_prompt_blocks
        and not explicit_move_attempt
    ):
        key_moves = ["5MP", "5MK", "2MK", "5HP", "2HP", "5HK", "2HK"]
        for char in mentioned_chars:
            for km in key_moves:
                k_row = lookup_frame_data(char, km)
                if k_row and k_row not in results:
                    results.append(k_row)

    if (
        wants_frame_data
        and mentioned_chars
        and explicit_move_attempt
        and not results
        and not tc_prompt_blocks
        and not special_prompt_blocks
    ):
        missing_scrolls_query = True

    has_results = bool(results)

    if not wants_frame_data and (
        wants_info or (mentioned_chars and not has_results and not wants_bnb and not wants_stats)
    ):
        for char in mentioned_chars:
            if char in CHARACTER_INFO:
                info_blocks.append(
                    f"**{char.capitalize()} Overview:**\n{CHARACTER_INFO[char]}"
                )

    for move_data in results:
        def clean(val):
            return str(val).replace('*', ',')

        startup = clean(move_data.get('startup', '-'))
        active = clean(move_data.get('active', '-'))
        recovery = clean(move_data.get('recovery', '-')).replace('(', ' (Whiff: ')
        cancel = clean(move_data.get('xx', '-'))
        damage = clean(move_data.get('dmg', '-'))
        guard = clean(move_data.get('atkLvl', '-'))
        atk_range = format_attack_range_for_table(move_data)
        on_hit = clean(move_data.get('onHit', '-'))
        on_block = clean(move_data.get('onBlock', '-'))
        extra_info = clean(move_data.get('extraInfo', '-')).replace('[', '').replace(']', '').replace('"', '')
        
        # New Stats (Drive/Super)
        ddoh = clean(move_data.get('DDoH', '-'))
        ddob = clean(move_data.get('DDoB', '-'))
        dgain = clean(move_data.get('DGain', '-'))
        ssoh = clean(move_data.get('SelfSoH', '-'))
        ssob = clean(move_data.get('SelfSoB', '-'))
        
        gauge_info = (
             f"Drive Dmg: Hit {ddoh} / Block {ddob} // Drive Gain: {dgain}\n"
             f"Super Gain: Hit {ssoh} / Block {ssob}\n"
        )
        
        # Hit Confirm Data (Always Included)
        hc_sp = clean(move_data.get('hcWinSpCa', '-')).strip() or '-'
        hc_tc = clean(move_data.get('hcWinTc', '-')).strip() or '-'
        hc_notes = clean(move_data.get('hcWinNotes', '-')).replace('[', '').replace(']', '').replace('"', '').strip() or '-'
        hc_info = (
            f"Hit Confirm (Sp/Su): {hc_sp} // Hit Confirm (TC): {hc_tc}\n"
            f"Hit Confirm Notes: {hc_notes}\n"
        )

        # Stun Data (Always Included)
        hstun = clean(move_data.get('hitstun', '-'))
        bstun = clean(move_data.get('blockstun', '-'))
        stun_info = f"Stun Frames: Hit {hstun} // Block {bstun}\n"

        block = (
            f"**{move_data['moveName']} ({move_data['numCmd']})**\n"
            f"Character: {move_data.get('char_name', 'Unknown')}\n"
            f"Startup: {startup} // Active: {active} // Recovery: {recovery}\n"
            f"Cancel: {cancel}\n"
            f"Damage: {damage}\n"
            f"Guard: {guard}\n"
            f"Range: {atk_range}\n"
            f"On Hit: {on_hit} // On Block: {on_block}\n"
            f"{gauge_info}"
            f"{stun_info}"
            f"{hc_info}"
            f"Notes: {extra_info}"
        )
        formatted_blocks.append(block)

    if tc_prompt_blocks:
        formatted_blocks.extend(tc_prompt_blocks)
    if special_prompt_blocks:
        formatted_blocks.extend(special_prompt_blocks)

    sections = []
    if formatted_blocks:
        sections.append("\n\n".join(formatted_blocks))
    if info_blocks:
        sections.append("\n\n".join(info_blocks))
    if bnb_context:
        sections.append(bnb_context.strip())

    output = "\n\n---\n".join(sections)

    # Check for punish calculation
    punish_verdict = check_punish(text_lower, results)
    if punish_verdict:
        if output:
            output = punish_verdict + "\n\n---\n\n" + output
        else:
            output = punish_verdict

    has_frame_blocks = bool(formatted_blocks)
    has_combo_blocks = bool(bnb_context)
    has_overview_blocks = bool(info_blocks)
    if has_frame_blocks:
        mode = "frame"
    elif has_combo_blocks:
        mode = "combo"
    elif has_overview_blocks:
        mode = "overview"
    else:
        mode = "none"

    return {
        "data": output,
        "mode": mode,
        "rows": results,
        "startup_alias_query": startup_alias_query,
        "hitconfirm_alias_query": hitconfirm_alias_query,
        "super_gain_alias_query": super_gain_alias_query,
        "range_alias_query": range_alias_query,
        "wants_comparison": bool(wants_comparison),
        "property_only_query": property_only_query,
        "target_combo_query": target_combo_query,
        "missing_scrolls_query": missing_scrolls_query,
        "gif_query": gif_query,
        "explicit_move_attempt": explicit_move_attempt,
    }



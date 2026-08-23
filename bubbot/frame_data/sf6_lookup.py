"""Single-character SF6 move lookup by numCmd, alias, or move name."""

import difflib
import re

from bubbot.frame_data.sf6_parser_helpers import (
    normalize_button_word_notation,
    normalize_charge_button_notation,
    normalize_charge_up_motion_notation,
    normalize_directional_normal_notation,
    normalize_grounded_normal_notation,
)
from bubbot.utils.notation_match_utils import find_rows_by_notation_prefix, looks_like_notation_query
from bubbot.utils.text_utils import correct_alias_typos


def lookup_frame_data(deps, character, move_input, _seen_inputs=None):
    frame_data = deps["FRAME_DATA"]
    input_aliases = deps["INPUT_ALIASES"]
    character_input_aliases = deps["CHARACTER_INPUT_ALIASES"]
    dp_prefix_exceptions = deps["DP_PREFIX_EXCEPTIONS"]
    normalize_jump_normal_text = deps["normalize_jump_normal_text"]
    compact_key = deps["compact_key"]
    compact_move_token = deps["compact_move_token"]
    extract_button_suffix = deps["extract_button_suffix"]
    normalize_num_cmd_token = deps["normalize_num_cmd_token"]
    """Search for a move in character's frame data by numCmd, plnCmd, or moveName."""
    move_input = str(move_input)
    seen_key = move_input.strip().lower()
    if _seen_inputs is None:
        _seen_inputs = set()
    if seen_key in _seen_inputs:
        return None
    _seen_inputs.add(seen_key)
    char_key = character.lower()
    if char_key not in frame_data:
        return None
    
    data = frame_data[char_key]
    move_input = normalize_jump_normal_text(move_input.lower().strip())
    move_input = normalize_charge_button_notation(move_input)
    move_input = normalize_charge_up_motion_notation(move_input)
    move_input = normalize_button_word_notation(move_input)

    move_input = normalize_directional_normal_notation(move_input)

    def normalize_strength_word_shorthand(text):
        prefix_map = {"l": "light", "m": "medium", "h": "heavy"}

        def replace_prefix(match):
            token = match.group(1)
            rest = match.group(2)
            return f"{prefix_map[token]} {rest}"

        def replace_suffix(match):
            rest = match.group(1)
            token = match.group(2)
            return f"{rest} {prefix_map[token]}"

        text = re.sub(r"^(l|m|h)\s+(.+)$", replace_prefix, text)
        text = re.sub(r"^(.+)\s+(l|m|h)$", replace_suffix, text)
        return text

    move_input = normalize_strength_word_shorthand(move_input)

    move_input = normalize_grounded_normal_notation(move_input)
    move_input = re.sub(r"^(?:7|9)\s*(lp|mp|hp|lk|mk|hk)$", r"jump \1", move_input)

    original_move_input = move_input
    query_requests_air_context = bool(re.search(r"\b(air|aerial)\b", original_move_input))

    def row_is_air_throw(row):
        num_cmd_raw = str(row.get("numCmd", "")).lower()
        move_name = str(row.get("moveName", "")).lower()
        cmn_name = str(row.get("cmnName", "")).lower()
        return bool(
            str(row.get("moveType", "")).lower() == "throw"
            and (
                "(air" in num_cmd_raw
                or "air throw" in cmn_name
                or "air throw" in move_name
            )
        )

    if query_requests_air_context and re.search(r"\bthrows?\b", original_move_input):
        air_throw_rows = [row for row in data if row_is_air_throw(row)]
        if air_throw_rows:
            return air_throw_rows[0]

    query_requests_charged = bool(re.search(r"\b(charged|hold|held)\b", original_move_input))
    query_requests_sa1 = bool(
        re.search(r"\b(?:sa\s*1|super\s*art\s*1|super\s*1|level\s*1)\b", original_move_input)
    )
    query_requests_sa3 = bool(
        re.search(r"\b(?:sa\s*3|super\s*art\s*3|super\s*3|level\s*3)\b", original_move_input)
    )
    query_requests_ca = bool(re.search(r"\b(?:ca|critical\s+art)\b", original_move_input))
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

    query_requests_stocked = bool(
        re.search(r"\b(stock|stocked|enhanced|windclad|wind\s+clad)\b", original_move_input)
    ) or any(token_is_stock_hint(token) for token in re.findall(r"[a-z0-9]+", original_move_input))

    def row_is_stocked_lookup_variant(row):
        move_name = str(row.get("moveName", "")).lower()
        cmn_name = str(row.get("cmnName", "")).lower()
        num_cmd = str(row.get("numCmd", "")).lower()
        combined = f"{move_name} {cmn_name} {num_cmd}"
        if re.search(r"\b0\s*stocks?\b", combined):
            return False
        return bool(
            re.search(r"\b[1-9]\d*\s*stocks?\b", combined)
            or "(stock" in move_name
            or "(stock" in cmn_name
            or "(stock" in num_cmd
            or "enhanced" in move_name
            or "enhanced" in cmn_name
            or "(enhanced" in num_cmd
            or "windclad" in move_name
            or "windclad" in cmn_name
            or ("wind stock" in cmn_name and ("(" in cmn_name or "(hold" in num_cmd))
        )

    data = sorted(data, key=lambda row: row_is_stocked_lookup_variant(row) != query_requests_stocked)
    neutral_tokens = []
    input_tokens = re.findall(r"[a-z0-9]+", original_move_input)
    if (
        ("neutral" in input_tokens or "n" in input_tokens or "nj" in input_tokens)
        and ("jump" in input_tokens or "j" in input_tokens or "nj" in input_tokens)
    ):
        neutral_query = original_move_input
        neutral_query = re.sub(r"\bnj\b", "n jump", neutral_query)
        neutral_query = re.sub(r"\bneutral\b", "n", neutral_query)
        neutral_query = re.sub(r"\bj\b", "jump", neutral_query)
        neutral_query = re.sub(r"[^a-z0-9]+", " ", neutral_query)
        neutral_query = re.sub(r"\s+", " ", neutral_query).strip()
        if neutral_query:
            neutral_tokens = neutral_query.split()

    move_input = re.sub(r"^ex\s+", "od ", move_input)
    move_input = re.sub(r"\bdivekick\b", "dive kick", move_input)
    if not re.match(
        r"^(jump|j)[\s\.]+(?:(?:214|236|623|421|22|46|28|41236|63214)|(?:[123]\s*(?:lp|mp|hp|lk|mk|hk|p|k)))",
        move_input,
    ):
        move_input = re.sub(r"^(jump|j)[\s\.]+", "8", move_input)
    move_input = re.sub(
        r"^([1-9][0-9]*)\s*(?:\+)?\s*(lp|mp|hp|lk|mk|hk|pp|kk|p|k)$",
        r"\1\2",
        move_input,
    )

    def get_motion_suffixes(motion_digits):
        suffixes = set()
        for row in data:
            num_cmd = re.sub(r"\s+", "", str(row.get("numCmd", "")).lower())
            if not num_cmd.startswith(motion_digits):
                continue
            for suffix in ("lp", "mp", "hp", "lk", "mk", "hk", "pp", "kk"):
                if num_cmd.startswith(f"{motion_digits}{suffix}"):
                    suffixes.add(suffix)
        return suffixes

    def resolve_623_strength_suffix(strength_token, available_suffixes):
        token = strength_token.lower()
        explicit_suffix_map = {
            "lp": "lp",
            "mp": "mp",
            "hp": "hp",
            "lk": "lk",
            "mk": "mk",
            "hk": "hk",
        }
        if token in explicit_suffix_map:
            return explicit_suffix_map[token]

        strength_letter_map = {
            "l": "l",
            "m": "m",
            "h": "h",
            "light": "l",
            "medium": "m",
            "heavy": "h",
        }
        strength_letter = strength_letter_map.get(token)
        if not strength_letter:
            return None

        preferred_suffixes = {
            "l": ["lp", "lk"],
            "m": ["mp", "mk"],
            "h": ["hp", "hk"],
        }
        for suffix in preferred_suffixes[strength_letter]:
            if suffix in available_suffixes:
                return suffix

        fallback_suffixes = {
            "l": "lp",
            "m": "mp",
            "h": "hp",
        }
        return fallback_suffixes[strength_letter]

    def normalize_motion_strength_aliases(raw_input):
        normalized = re.sub(r"\s+", " ", raw_input).strip()
        motion_digit_aliases = {
            "qcf": "236",
            "quarter circle forward": "236",
            "qcb": "214",
            "quarter circle back": "214",
            "hcf": "41236",
            "half circle forward": "41236",
            "hcb": "63214",
            "half circle back": "63214",
        }
        motion_alias_pattern = r"(dp|srk|shoryu|shoryuken)"
        strength_token_pattern = r"(lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)"
        available_623_suffixes = get_motion_suffixes("623")

        for motion_alias, motion_digits in motion_digit_aliases.items():
            escaped_motion = re.escape(motion_alias)
            motion_strength_match = re.fullmatch(
                rf"{escaped_motion}\s*(?:\+)?\s*{strength_token_pattern}",
                normalized,
            )
            if motion_strength_match:
                suffix = resolve_623_strength_suffix(
                    motion_strength_match.group(1),
                    get_motion_suffixes(motion_digits),
                )
                return f"{motion_digits}{suffix}" if suffix else normalized
            strength_motion_match = re.fullmatch(
                rf"{strength_token_pattern}\s*(?:\+)?\s*{escaped_motion}",
                normalized,
            )
            if strength_motion_match:
                suffix = resolve_623_strength_suffix(
                    strength_motion_match.group(1),
                    get_motion_suffixes(motion_digits),
                )
                return f"{motion_digits}{suffix}" if suffix else normalized

        od_motion_match = re.fullmatch(
            rf"(?:od|ex)\s*(?:\+)?\s*{motion_alias_pattern}",
            normalized,
        )
        if od_motion_match:
            if "pp" in available_623_suffixes:
                return "623pp"
            if "kk" in available_623_suffixes:
                return "623kk"
            return "623pp"

        strength_motion_match = re.fullmatch(
            rf"{strength_token_pattern}\s*(?:\+)?\s*{motion_alias_pattern}",
            normalized,
        )
        if strength_motion_match:
            strength_token = strength_motion_match.group(1)
            resolved_suffix = resolve_623_strength_suffix(
                strength_token,
                available_623_suffixes,
            )
            if resolved_suffix:
                return f"623{resolved_suffix}"
            return normalized

        motion_strength_match = re.fullmatch(
            rf"{motion_alias_pattern}\s*(?:\+)?\s*{strength_token_pattern}",
            normalized,
        )
        if motion_strength_match:
            strength_token = motion_strength_match.group(2)
            resolved_suffix = resolve_623_strength_suffix(
                strength_token,
                available_623_suffixes,
            )
            if resolved_suffix:
                return f"623{resolved_suffix}"

        return normalized

    def resolve_strength_special_input(raw_input):
        normalized = re.sub(r"\s+", " ", raw_input).strip().lower()
        if ">" in normalized or "->" in normalized:
            return normalized
        strength_map = {
            "light": ["lp", "lk"],
            "l": ["lp", "lk"],
            "medium": ["mp", "mk"],
            "m": ["mp", "mk"],
            "heavy": ["hp", "hk"],
            "h": ["hp", "hk"],
        }

        match = re.fullmatch(r"(light|medium|heavy|l|m|h)\s+(.+)", normalized)
        if not match:
            match = re.fullmatch(r"(.+)\s+(light|medium|heavy|l|m|h)", normalized)
            if not match:
                return normalized
            remainder = match.group(1).strip()
            strength_token = match.group(2)
        else:
            strength_token = match.group(1)
            remainder = match.group(2).strip()

        candidate_prefixes = strength_map.get(strength_token, [])
        if not candidate_prefixes:
            return normalized

        for prefix in candidate_prefixes:
            candidate = f"{prefix} {remainder}"
            candidate_compact = re.sub(r"[^a-z0-9]", "", candidate)
            for row in data:
                num_cmd = str(row.get("numCmd", "")).lower()
                pln_cmd = str(row.get("plnCmd", "")).lower()
                cmn_name = str(row.get("cmnName", "")).lower()
                move_name = str(row.get("moveName", "")).lower()
                if (
                    candidate == num_cmd
                    or candidate == pln_cmd
                    or candidate == cmn_name
                    or candidate in cmn_name
                    or candidate in move_name
                ):
                    return candidate
                cmn_compact = re.sub(r"[^a-z0-9]", "", cmn_name)
                move_compact = re.sub(r"[^a-z0-9]", "", move_name)
                if candidate_compact and (
                    candidate_compact in cmn_compact
                    or candidate_compact in move_compact
                ):
                    return candidate

        return normalized

    pre_strength_alias_input = move_input
    move_input = normalize_motion_strength_aliases(move_input)
    move_input = resolve_strength_special_input(move_input)

    combo_input = None
    if ">" in move_input or "->" in move_input:
        combo_input = re.sub(r"\s+", "", move_input.replace("->", ">"))

    def normalize_move_name_tokens(text):
        normalized = re.sub(r"[^a-z0-9]+", " ", str(text).lower())
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized.split() if normalized else []

    def neutral_tokens_match(query_tokens, move_name_tokens):
        if not query_tokens:
            return False
        move_name_set = set(move_name_tokens)
        for token in query_tokens:
            if token == "jump":
                if not any(t == "j" or t.startswith("jump") for t in move_name_tokens):
                    return False
                continue
            if token == "n":
                if "n" not in move_name_set and "neutral" not in move_name_set:
                    return False
                continue
            if token not in move_name_set:
                return False
        return True

    def jump_tokens_match(query_tokens, move_name_tokens):
        if "jump" not in query_tokens:
            return False
        for token in query_tokens:
            if token in ("neutral", "n"):
                continue
            if token == "jump":
                if not any(t == "j" or t.startswith("jump") for t in move_name_tokens):
                    return False
                continue
            if token not in move_name_tokens:
                return False
        return True

    if "jump" in input_tokens:
        neutral_candidate = None
        for row in data:
            move_name_tokens = normalize_move_name_tokens(row.get("moveName", ""))
            if not move_name_tokens:
                continue
            if neutral_tokens:
                if neutral_tokens_match(neutral_tokens, move_name_tokens):
                    return row
                continue
            if not jump_tokens_match(input_tokens, move_name_tokens):
                continue
            if "neutral" in move_name_tokens or "n" in move_name_tokens:
                if neutral_candidate is None:
                    neutral_candidate = row
                continue
            return row
        if neutral_candidate:
            return neutral_candidate

    def normalize_num_cmd_for_lookup(value):
        normalized = re.sub(r"[\[\]\(\)\{\}]", "", str(value or "").lower())
        normalized = re.sub(r"\s+", "", normalized)
        return re.sub(r"[^a-z0-9>]", "", normalized)

    def normalize_num_cmd_generic_for_lookup(value):
        normalized = str(value or "").lower()
        normalized = re.sub(r"\([^)]*\)", "", normalized)
        normalized = re.sub(r"\[[^\]]*\]", "", normalized)
        normalized = re.sub(r"\{[^}]*\}", "", normalized)
        normalized = re.sub(r"\s+", "", normalized)
        return re.sub(r"[^a-z0-9>]", "", normalized)
    
    char_aliases = character_input_aliases.get(char_key, {})
    alias_lookup_candidates = []
    for candidate in (pre_strength_alias_input, move_input):
        candidate = str(candidate or "").strip().lower()
        if candidate and candidate not in alias_lookup_candidates:
            alias_lookup_candidates.append(candidate)

    def resolve_input_alias_chain(raw_value):
        current = str(raw_value or "").strip().lower()
        seen_alias_values = set()
        while current and current not in seen_alias_values:
            seen_alias_values.add(current)
            next_value = None
            if current in char_aliases:
                next_value = str(char_aliases[current]).strip().lower()
            elif current in input_aliases:
                next_value = str(input_aliases[current]).strip().lower()
            if not next_value or next_value == current:
                break
            current = next_value
        return current

    for candidate in alias_lookup_candidates:
        resolved_candidate = resolve_input_alias_chain(candidate)
        if resolved_candidate != candidate or candidate in char_aliases or candidate in input_aliases:
            move_input = resolved_candidate
            break

    if (
        move_input not in char_aliases
        and move_input not in input_aliases
        and not re.fullmatch(r"[1-9][0-9]*(?:lp|mp|hp|lk|mk|hk|pp|kk|p|k)", move_input)
    ):
        corrected_move_input = correct_alias_typos(move_input, char_aliases, input_aliases)
        if corrected_move_input != move_input:
            corrected_move_input = normalize_motion_strength_aliases(corrected_move_input)
            corrected_move_input = resolve_strength_special_input(corrected_move_input)
            corrected_candidate = resolve_input_alias_chain(corrected_move_input)
            if corrected_candidate != corrected_move_input or corrected_move_input in char_aliases or corrected_move_input in input_aliases:
                move_input = corrected_candidate
            else:
                move_input = corrected_move_input

    def resolve_fuzzy_alias_target(raw_input):
        raw_compact = re.sub(r"[^a-z0-9]", "", str(raw_input or "").lower())
        if len(raw_compact) < 4:
            return None

        alias_compact_to_target = {}
        for alias_key, alias_target in char_aliases.items():
            alias_compact = re.sub(r"[^a-z0-9]", "", str(alias_key or "").lower())
            if len(alias_compact) < 4:
                continue
            if alias_compact not in alias_compact_to_target:
                alias_compact_to_target[alias_compact] = str(alias_target)

        for alias_key, alias_target in input_aliases.items():
            alias_compact = re.sub(r"[^a-z0-9]", "", str(alias_key or "").lower())
            if len(alias_compact) < 4:
                continue
            if alias_compact not in alias_compact_to_target:
                alias_compact_to_target[alias_compact] = str(alias_target)

        if not alias_compact_to_target:
            return None

        close_matches = difflib.get_close_matches(
            raw_compact,
            list(alias_compact_to_target.keys()),
            n=1,
            cutoff=0.82,
        )
        if not close_matches:
            return None
        return alias_compact_to_target.get(close_matches[0])

    def row_is_ca_variant(row):
        move_name = str(row.get("moveName", "")).lower()
        cmn_name = str(row.get("cmnName", "")).lower()
        num_cmd = str(row.get("numCmd", "")).lower()
        return (
            "critical art" in move_name
            or "critical art" in cmn_name
            or bool(re.search(r"\(\s*ca\s*\)", num_cmd))
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

    def genericize_lookup_button_suffix(num_cmd_token):
        token = str(num_cmd_token or "")
        token = re.sub(r"(lp|mp|hp)$", "p", token)
        token = re.sub(r"(lk|mk|hk)$", "k", token)
        token = re.sub(r"pp$", "p", token)
        token = re.sub(r"kk$", "k", token)
        return token

    def build_strengthless_lookup_variants(raw_input):
        variants = []
        normalized = str(raw_input or "").lower().strip()
        if not normalized:
            return variants

        collapsed_numcmd = re.sub(r"(\d+)(lp|mp|hp)\b", r"\1p", normalized)
        collapsed_numcmd = re.sub(r"(\d+)(lk|mk|hk)\b", r"\1k", collapsed_numcmd)
        collapsed_numcmd = re.sub(r"(\d+)(pp)\b", r"\1p", collapsed_numcmd)
        collapsed_numcmd = re.sub(r"(\d+)(kk)\b", r"\1k", collapsed_numcmd)
        collapsed_numcmd = re.sub(r"\s+", " ", collapsed_numcmd).strip()
        if collapsed_numcmd and collapsed_numcmd != normalized:
            variants.append(collapsed_numcmd)

        stripped_strength = re.sub(
            r"\b(?:lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\b",
            " ",
            normalized,
        )
        stripped_strength = re.sub(r"\s+", " ", stripped_strength).strip()
        if stripped_strength and stripped_strength != normalized and stripped_strength not in variants:
            variants.append(stripped_strength)

        stripped_after_collapse = re.sub(
            r"\b(?:lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\b",
            " ",
            collapsed_numcmd,
        )
        stripped_after_collapse = re.sub(r"\s+", " ", stripped_after_collapse).strip()
        if (
            stripped_after_collapse
            and stripped_after_collapse != normalized
            and stripped_after_collapse not in variants
        ):
            variants.append(stripped_after_collapse)

        return variants
    move_input_compact = re.sub(r"[^a-z0-9]", "", move_input)
    move_input_num_cmd = normalize_num_cmd_for_lookup(move_input)
    move_input_num_cmd_generic = normalize_num_cmd_generic_for_lookup(move_input)
    move_input_has_numcmd_qualifier = bool(
        re.search(r"\b(air|hold|held|bomb|charged)\b", move_input)
        or any(ch in move_input for ch in "()[]{}")
    )

    if char_key == "akuma":
        if move_input in {"air sa1", "aerial sa1", "sa1 air", "air super art 1"}:
            move_input = "tenma gozanku"
        if move_input in {"air sa3", "aerial sa3", "sa3 air", "air super art 3"}:
            move_input = "sip of calamity"

    move_input_tigerless = move_input
    move_input_tigerless_compact = move_input_compact
    if char_key == "sagat":
        move_input_tigerless = re.sub(r"\btiger\b", "", move_input)
        move_input_tigerless = re.sub(r"\s+", " ", move_input_tigerless).strip()
        move_input_tigerless_compact = re.sub(r"[^a-z0-9]", "", move_input_tigerless)

    if char_key == "akuma" and move_input_num_cmd_generic == "236236k":
        akuma_super_rows = []
        for row in data:
            row_token = normalize_num_cmd_generic_for_lookup(row.get("numCmd", ""))
            if row_token == "236236k":
                akuma_super_rows.append(row)
        if akuma_super_rows:
            ca_rows = [row for row in akuma_super_rows if row_is_ca_variant(row)]
            air_rows = [
                row
                for row in akuma_super_rows
                if "air" in str(row.get("moveName", "")).lower()
                or "air" in str(row.get("cmnName", "")).lower()
                or "(air)" in str(row.get("numCmd", "")).lower()
                or "tenma" in str(row.get("moveName", "")).lower()
            ]
            non_air_non_ca_rows = [
                row
                for row in akuma_super_rows
                if row not in air_rows and row not in ca_rows
            ]

            if query_requests_ca and ca_rows:
                return ca_rows[0]
            if query_requests_air_context or query_requests_sa1:
                if air_rows:
                    return air_rows[0]
            if query_requests_sa3 and non_air_non_ca_rows:
                return non_air_non_ca_rows[0]
            if non_air_non_ca_rows:
                return non_air_non_ca_rows[0]
    
    notation_key = move_input_num_cmd_generic or move_input_num_cmd
    if looks_like_notation_query(notation_key, "motion_digits"):
        notation_matches = find_rows_by_notation_prefix(
            data,
            notation_key,
            normalize_fn=normalize_num_cmd_generic_for_lookup,
            looks_like_fn=lambda key: looks_like_notation_query(key, "motion_digits"),
        )
        if notation_matches:
            if notation_key.isdigit() and len(notation_key) == 3 and notation_key == "623":
                exception_terms = dp_prefix_exceptions.get(char_key, [])
                if exception_terms:
                    filtered = [
                        row
                        for row in notation_matches
                        if not any(term in str(row.get("moveName", "")).lower() for term in exception_terms)
                    ]
                    if filtered:
                        return filtered[0]
            return notation_matches[0]

    # search priority: numCmd -> plnCmd -> moveName
    for row in data:
        num_cmd = str(row.get('numCmd', '')).lower()
        num_cmd_normalized = normalize_num_cmd_for_lookup(num_cmd)
        num_cmd_generic = normalize_num_cmd_generic_for_lookup(num_cmd)
        if combo_input and ">" in num_cmd:
            if any(
                re.sub(r"\s+", "", option) == combo_input
                for option in num_cmd.split("/")
            ):
                return row
        # exact match numCmd (5MP)
        if num_cmd == move_input:
            return row
        # strict normalized numCmd match (preserves annotation words)
        if move_input_num_cmd and num_cmd_normalized == move_input_num_cmd:
            return row
        # generic normalized numCmd match (drops annotation words, for convenience)
        if (
            not move_input_has_numcmd_qualifier
            and move_input_num_cmd_generic
            and num_cmd_generic == move_input_num_cmd_generic
        ):
            if query_requests_air_context:
                air_throw_matches = [
                    row for row in data
                    if row_is_air_throw(row)
                    and normalize_num_cmd_generic_for_lookup(row.get("numCmd", "")) == move_input_num_cmd_generic
                ]
                if air_throw_matches:
                    return air_throw_matches[0]
            return row
        # exact match plnCmd (MP)
        if str(row.get('plnCmd', '')).lower() == move_input:
            return row
        # exact/contains match cmnName
        cmn_name = str(row.get('cmnName', '')).lower()
        if cmn_name == move_input or (len(move_input_compact) >= 3 and cmn_name and move_input in cmn_name):
            return row
        # fuzzy match moveName ("Stand MP")
        move_name = str(row.get('moveName', '')).lower()
        cmn_name_tigerless = cmn_name
        move_name_tigerless = move_name
        if len(move_input_compact) >= 3 and move_input in move_name:
            return row
        if char_key == "sagat" and move_input_tigerless:
            cmn_name_tigerless = re.sub(r"\btiger\b", "", cmn_name)
            cmn_name_tigerless = re.sub(r"\s+", " ", cmn_name_tigerless).strip()
            move_name_tigerless = re.sub(r"\btiger\b", "", move_name)
            move_name_tigerless = re.sub(r"\s+", " ", move_name_tigerless).strip()
            if cmn_name_tigerless == move_input_tigerless or (
                len(move_input_tigerless_compact) >= 3
                and cmn_name_tigerless
                and move_input_tigerless in cmn_name_tigerless
            ):
                return row
            if (
                len(move_input_tigerless_compact) >= 3
                and move_input_tigerless in move_name_tigerless
            ):
                return row
        if len(move_input_compact) >= 6:
            cmn_compact = re.sub(r"[^a-z0-9]", "", cmn_name)
            move_name_compact = re.sub(r"[^a-z0-9]", "", move_name)
            if (
                (cmn_compact and move_input_compact in cmn_compact)
                or move_input_compact in move_name_compact
            ):
                return row
            if char_key == "sagat" and len(move_input_tigerless_compact) >= 6:
                cmn_tigerless_compact = re.sub(r"[^a-z0-9]", "", cmn_name_tigerless)
                move_tigerless_compact = re.sub(r"[^a-z0-9]", "", move_name_tigerless)
                if (
                    (cmn_tigerless_compact and move_input_tigerless_compact in cmn_tigerless_compact)
                    or move_input_tigerless_compact in move_tigerless_compact
                ):
                    return row

    if query_requests_charged:
        base_chargeless_input = re.sub(
            r"\b(?:charged|hold|held)\b",
            " ",
            move_input,
        )
        base_chargeless_input = re.sub(r"\s+", " ", base_chargeless_input).strip()
        if base_chargeless_input and base_chargeless_input != move_input:
            base_row = lookup_frame_data(deps, character, base_chargeless_input, _seen_inputs=_seen_inputs)
            if base_row:
                base_token = normalize_num_cmd_token(base_row.get("numCmd", ""))
                base_suffix = extract_button_suffix(base_token)
                charged_candidates = []
                for row in data:
                    if not row_is_charged_variant(row):
                        continue
                    row_token = normalize_num_cmd_token(row.get("numCmd", ""))
                    if row_token != base_token:
                        continue
                    charged_candidates.append(row)
                if charged_candidates:
                    if base_suffix:
                        for row in charged_candidates:
                            row_suffix = extract_button_suffix(normalize_num_cmd_token(row.get("numCmd", "")))
                            if row_suffix == base_suffix:
                                return row
                    return charged_candidates[0]

                base_generic_token = genericize_lookup_button_suffix(base_token)
                generic_channel = ""
                if base_suffix in {"lp", "mp", "hp", "pp", "p"}:
                    generic_channel = "p"
                elif base_suffix in {"lk", "mk", "hk", "kk", "k"}:
                    generic_channel = "k"

                generic_charged_candidates = []
                for row in data:
                    if not row_is_charged_variant(row):
                        continue
                    row_token = normalize_num_cmd_token(row.get("numCmd", ""))
                    if genericize_lookup_button_suffix(row_token) != base_generic_token:
                        continue
                    generic_charged_candidates.append(row)
                if generic_charged_candidates:
                    if generic_channel:
                        for row in generic_charged_candidates:
                            row_suffix = extract_button_suffix(normalize_num_cmd_token(row.get("numCmd", "")))
                            if row_suffix == generic_channel:
                                return row
                    return generic_charged_candidates[0]

    for strengthless_input in build_strengthless_lookup_variants(move_input):
        strengthless_row = lookup_frame_data(deps, character, strengthless_input, _seen_inputs=_seen_inputs)
        if strengthless_row is not None:
            return strengthless_row

    if query_requests_stocked:
        base_stockless_input = re.sub(
            r"\b(?:stocked|stock|enhanced|windclad|wind\s+clad)\b",
            " ",
            move_input,
        )
        base_stockless_input = re.sub(r"\s+", " ", base_stockless_input).strip()
        if base_stockless_input and base_stockless_input != move_input:
            base_row = lookup_frame_data(deps, character, base_stockless_input, _seen_inputs=_seen_inputs)
            if base_row:
                base_token = normalize_num_cmd_token(base_row.get("numCmd", ""))
                base_suffix = extract_button_suffix(base_token)
                stocked_candidates = []
                for row in data:
                    if not row_is_stocked_variant(row):
                        continue
                    row_token = normalize_num_cmd_token(row.get("numCmd", ""))
                    if row_token != base_token:
                        continue
                    stocked_candidates.append(row)
                if stocked_candidates:
                    if base_suffix:
                        for row in stocked_candidates:
                            row_suffix = extract_button_suffix(normalize_num_cmd_token(row.get("numCmd", "")))
                            if row_suffix == base_suffix:
                                return row
                    return stocked_candidates[0]

    if len(move_input_compact) >= 4:
        fuzzy_candidates = []
        for row in data:
            move_name = str(row.get("moveName", "")).lower()
            cmn_name = str(row.get("cmnName", "")).lower()
            for candidate in (move_name, cmn_name):
                candidate_compact = re.sub(r"[^a-z0-9]", "", candidate)
                if len(candidate_compact) >= 4:
                    fuzzy_candidates.append((candidate_compact, row))

        if fuzzy_candidates:
            choices = [candidate for candidate, _ in fuzzy_candidates]
            close = difflib.get_close_matches(move_input_compact, choices, n=1, cutoff=0.86)
            if close:
                matched = close[0]
                for candidate, row in fuzzy_candidates:
                    if candidate == matched:
                        return row

    fuzzy_alias_target = resolve_fuzzy_alias_target(move_input)
    if fuzzy_alias_target and fuzzy_alias_target != move_input:
        fuzzy_alias_row = lookup_frame_data(deps, character, fuzzy_alias_target, _seen_inputs=_seen_inputs)
        if fuzzy_alias_row is not None:
            return fuzzy_alias_row

    return None

def should_skip_special_prompt_base(
    *,
    char,
    base_name,
    air_tatsu_context,
    ken_run_followup_context,
):
    if char == "akuma" and base_name == "demon flip":
        return True
    if air_tatsu_context and char in {"ryu", "ken", "akuma"} and base_name in {"tatsu", "air tatsu"}:
        return True
    if ken_run_followup_context and char == "ken" and base_name in {"dp", "tatsu", "dragonlash"}:
        return True
    return False


def should_skip_ambiguous_special_key(row_char_norm, base_name):
    return row_char_norm == "ryu" and base_name in {"super art level 1", "super art level 2"}


def choose_ryu_super_art_variant(
    *,
    char,
    base_name,
    variants,
    query_requests_sa1,
    query_requests_sa2,
    query_requires_variant_state,
    row_matches_variant_state,
):
    if char != "ryu" or base_name not in {"super art level 1", "super art level 2"}:
        return None, False
    if base_name == "super art level 1" and not query_requests_sa1:
        return None, True
    if base_name == "super art level 2" and not query_requests_sa2:
        return None, True

    state_variants = [row for row in variants if row_matches_variant_state(row)]
    default_variants = [row for row in variants if not row_matches_variant_state(row)]
    if query_requires_variant_state and state_variants:
        return state_variants[0], True
    if not query_requires_variant_state and default_variants:
        return default_variants[0], True
    return None, False


def choose_character_special_variant(**kwargs):
    return choose_ryu_super_art_variant(**kwargs)

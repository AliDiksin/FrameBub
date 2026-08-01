"""SF6 result cleanup and optional key-move context injection."""
# Post-processing runs after candidate matching and may only narrow or enrich returned rows.

from bubbot.frame_data.sf6_character_aliases import filter_character_specific_final_results


def filter_and_inject_key_moves(
    text_lower,
    mentioned_chars,
    results,
    lookup_frame_data,
    *,
    query_has_explicit_strength,
    frame_data,
    wants_frame_data,
    target_combo_query,
    special_prompt_blocks,
    explicit_move_attempt,
):
    """Apply character filters and preserve fallback rows."""
    results = filter_character_specific_final_results(
        text_lower,
        mentioned_chars,
        results,
        lookup_frame_data,
        query_has_explicit_strength=query_has_explicit_strength,
        frame_data=frame_data,
    )
    if (
        wants_frame_data
        and mentioned_chars
        and not results
        and not target_combo_query
        and not special_prompt_blocks
        and not explicit_move_attempt
    ):
        for char in mentioned_chars:
            for move_key in ("5MP", "5MK", "2MK", "5HP", "2HP", "5HK", "2HK"):
                row = lookup_frame_data(char, move_key)
                if row and row not in results:
                    results.append(row)
    return results


def is_missing_scrolls_query(
    *,
    wants_frame_data,
    mentioned_chars,
    explicit_move_attempt,
    results,
    tc_prompt_blocks,
    special_prompt_blocks,
):
    return bool(
        wants_frame_data
        and mentioned_chars
        and explicit_move_attempt
        and not results
        and not tc_prompt_blocks
        and not special_prompt_blocks
    )

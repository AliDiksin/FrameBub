"""Shared slash-command helpers for framedata and stats embed responses."""

async def send_slash_frame_result(
    interaction,
    *,
    char_name,
    move_name,
    query,
    parse_fn,
    embed_fn,
    game,
    game_label,
    selected_row=None,
    selected_char_key=None,
    disambiguation_predicate=None,
    prompt_predicate=None,
):
    """Shared slash-command flow for one framedata lookup."""
    payload = {}
    if selected_row is not None:
        rows = [selected_row]
    else:
        payload = parse_fn(query)
        rows = payload.get("rows", []) or []
        if prompt_predicate and prompt_predicate(payload):
            await interaction.response.send_message(str(payload.get("data", ""))[:2000])
            return
        if disambiguation_predicate and disambiguation_predicate(payload):
            await interaction.response.send_message(str(payload.get("data", f"Please specify which {game_label} move you mean."))[:2000])
            return
    if not rows:
        await interaction.response.send_message(f"{char_name} with {move_name} is not a valid character/move combination for {game_label}")
        return
    row = rows[0]
    from bubbot.features.menu_system import build_frame_result_view, prepare_cotw_frame_view

    char_key = selected_char_key or payload.get("char_key") or row.get("char_key")
    view = build_frame_result_view(
        game,
        row,
        owner_id=getattr(interaction.user, "id", None),
        char_key=char_key,
        menu_locked=False,
        prompt=query,
    )
    if game == "cotw":
        await prepare_cotw_frame_view(view)
    embed = view.build_embed()
    files = view.initial_files()
    await interaction.response.send_message(embed=embed, view=view, files=files)
    from bubbot.features.failed_prompt_report import stamp_report_context_on_sent

    try:
        sent = await interaction.original_response()
        stamp_report_context_on_sent(view, sent)
    except Exception:
        pass
    try:
        from bubbot.utils.response_log import INTERACTION_SLASH, log_from_interaction, summarize_embed

        log_from_interaction(
            interaction,
            interaction_type=INTERACTION_SLASH,
            reason="slash_frame_data",
            prompt=query,
            response_text=summarize_embed(embed) or f"{char_name} {move_name}",
            response_kind="embed",
        )
    except Exception as log_error:
        print(f"Slash frame log error: {log_error}", flush=True)


async def send_slash_stats_result(
    interaction,
    *,
    char_name,
    char_key,
    stats_row,
    build_stats_embed_fn,
    stat_keys=None,
    game_label="SF6",
    query="",
):
    """Shared slash-command flow for one character stats embed."""
    if not char_key:
        await interaction.response.send_message(f"{char_name} is not a valid {game_label} character.")
        return
    if not stats_row:
        await interaction.response.send_message(f"No stats scrolls are loaded for {char_name}.")
        return
    from bubbot.features.menu_system import StatsResultView
    from bubbot.utils.embed_source_utils import apply_game_source_footer, source_icon_files

    embed = apply_game_source_footer(build_stats_embed_fn(char_key, stats_row, stat_keys), "sf6")
    view = StatsResultView(
        char_key,
        interaction.user.id,
        stat_keys=stat_keys,
        menu_locked=False,
        prompt=query or f"{char_name} stats",
    )
    await interaction.response.send_message(embed=embed, view=view, files=source_icon_files("sf6", kind="frame"))
    from bubbot.features.failed_prompt_report import stamp_report_context_on_sent

    try:
        sent = await interaction.original_response()
        stamp_report_context_on_sent(view, sent)
    except Exception:
        pass
    try:
        from bubbot.utils.response_log import INTERACTION_SLASH, log_from_interaction, summarize_embed

        log_from_interaction(
            interaction,
            interaction_type=INTERACTION_SLASH,
            reason="slash_stats",
            prompt=query or f"{char_name} stats",
            response_text=summarize_embed(embed) or f"{char_name} stats",
            response_kind="embed",
        )
    except Exception as log_error:
        print(f"Slash stats log error: {log_error}", flush=True)

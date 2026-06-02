async def send_slash_frame_result(
    interaction,
    *,
    char_name,
    move_name,
    query,
    parse_fn,
    embed_fn,
    view_fn,
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
    view = view_fn(
        row,
        owner_id=getattr(interaction.user, "id", None),
        char_key=selected_char_key or payload.get("char_key") or row.get("char_key"),
    )
    embed = view.build_embed() if hasattr(view, "build_embed") else embed_fn(row)
    files = view.initial_files() if hasattr(view, "initial_files") else []
    await interaction.response.send_message(embed=embed, view=view, files=files)


async def send_slash_stats_result(
    interaction,
    *,
    char_name,
    char_key,
    stats_row,
    build_stats_embed_fn,
    stat_keys=None,
    game_label="SF6",
):
    """Shared slash-command flow for one character stats embed."""
    if not char_key:
        await interaction.response.send_message(f"{char_name} is not a valid {game_label} character.")
        return
    if not stats_row:
        await interaction.response.send_message(f"No stats scrolls are loaded for {char_name}.")
        return
    embed = build_stats_embed_fn(char_key, stats_row, stat_keys)
    await interaction.response.send_message(embed=embed)

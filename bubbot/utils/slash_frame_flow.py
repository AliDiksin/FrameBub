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
    disambiguation_predicate=None,
    prompt_predicate=None,
):
    """Shared slash-command flow for one framedata lookup."""
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
    await interaction.response.send_message(embed=embed_fn(row), view=view_fn(row))

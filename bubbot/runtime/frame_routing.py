"""Cross-game frame-data precedence and dispatch."""

import re

import discord

client = None
buenavista_extension = None
combo_data_module = None
sf6_module = None
sfv_module = None
ggst_module = None
tuco_module = None
bbcf_module = None
ggacr_module = None
cotw_module = None
third_strike_module = None
mk1_module = None
FRAME_DATA = {}
resolve_character_from_aliases_in_text = None
text_mentions_character_from_aliases = None
find_moves_in_text = None
_fetch_referenced_message = None
_requested_property_key = None
_send_cross_game_lookup_response = None
_reply_and_log_response = None
strip_discord_mentions = lambda text: str(text or "")
_record_frame_data_ids = lambda ids, **kwargs: None


def configure(**deps):
    globals().update(deps)


async def route_cross_game(
    message,
    *,
    content_lower,
    content_no_mentions,
    directly_mentions_bot,
):
    sf6_exact_character_query = text_mentions_character_from_aliases(
        content_lower,
        CHARACTER_ALIASES,
        FRAME_DATA.keys(),
    )
    ggst_exact_character_query = text_mentions_character_from_aliases(
        content_lower,
        ggst_module.GGST_CHARACTER_ALIASES,
        ggst_module.GGST_FRAME_DATA.keys(),
    )
    sfv_exact_character_query = text_mentions_character_from_aliases(
        content_lower,
        sfv_module.SFV_CHARACTER_ALIASES,
        sfv_module.SFV_FRAME_DATA.keys(),
    )
    tuco_exact_character_query = text_mentions_character_from_aliases(
        content_lower,
        tuco_module.TUCO_CHARACTER_ALIASES,
        tuco_module.TUCO_FRAME_DATA.keys(),
    )
    bbcf_exact_character_query = text_mentions_character_from_aliases(
        content_lower,
        bbcf_module.BBCF_CHARACTER_ALIASES,
        bbcf_module.BBCF_FRAME_DATA.keys(),
    )
    ggacr_exact_character_query = text_mentions_character_from_aliases(
        content_lower,
        ggacr_module.GGACR_CHARACTER_ALIASES,
        ggacr_module.GGACR_FRAME_DATA.keys(),
    )
    explicit_ggacr_query = ggacr_module.query_has_explicit_ggacr_tag(content_lower)
    ggacr_exclusive_character_query = bool(
        ggacr_exact_character_query
        and ggacr_module.is_exclusive_character(
            resolve_character_from_aliases_in_text(
                content_lower,
                ggacr_module.GGACR_CHARACTER_ALIASES,
                ggacr_module.GGACR_FRAME_DATA.keys(),
            )
        )
    )
    cotw_exact_character_query = text_mentions_character_from_aliases(
        content_lower,
        cotw_module.COTW_CHARACTER_ALIASES,
        cotw_module.COTW_FRAME_DATA.keys(),
    )
    third_strike_exact_character_query = text_mentions_character_from_aliases(
        content_lower,
        third_strike_module.THIRD_STRIKE_CHARACTER_ALIASES,
        third_strike_module.THIRD_STRIKE_FRAME_DATA.keys(),
    )
    mk1_exact_character_query = text_mentions_character_from_aliases(
        content_lower,
        mk1_module.MK1_CHARACTER_ALIASES,
        mk1_module.MK1_FRAME_DATA.keys(),
    )
    message_replies_to_bot = False
    if message.reference:
        try:
            addressed_replied_msg = await _fetch_referenced_message(message)
            message_replies_to_bot = bool(addressed_replied_msg and addressed_replied_msg.author == client.user)
        except (discord.NotFound, discord.Forbidden):
            message_replies_to_bot = False
        except Exception as reply_check_error:
            print(f"Frame route reply check error: {reply_check_error}", flush=True)
    frame_command_is_addressed = bool(
        directly_mentions_bot
        or message_replies_to_bot
    )
    allow_implied_frame_routing = bool(
        not message.reference
        or message_replies_to_bot
        or directly_mentions_bot
    )

    # Cross-game frame routing: combos first, then per-game find_moves_in_text blocks below
    if await _try_route_combo_query(
        message,
        content_lower,
        frame_command_is_addressed=frame_command_is_addressed,
        sf6_exact_character_query=sf6_exact_character_query,
        mk1_exact_character_query=mk1_exact_character_query,
    ):
        return

    fd_context_payload = find_moves_in_text(content_lower)

    ggacr_payload = ggacr_module.find_moves_in_text(content_lower)
    ggst_payload = ggst_module.find_moves_in_text(content_lower)
    sfv_payload = sfv_module.find_moves_in_text(content_lower)
    tuco_payload = tuco_module.find_moves_in_text(content_lower)
    bbcf_payload = bbcf_module.find_moves_in_text(content_lower)
    cotw_payload = cotw_module.find_moves_in_text(content_lower)
    third_strike_payload = third_strike_module.find_moves_in_text(content_lower)
    mk1_payload = mk1_module.find_moves_in_text(content_lower)
    requested_property_key = _requested_property_key(content_lower)
    ggst_rows = ggst_payload.get("rows", [])
    ggst_lookup_intent = bool(
        ggst_payload.get("frame_query")
        or ggst_payload.get("gif_query")
        or ggst_payload.get("game_query")
        or requested_property_key
    )
    explicit_ggst_query = bool(ggst_payload.get("game_query"))
    ggst_route_allowed = bool(
        explicit_ggst_query
        and not explicit_ggacr_query
        or (
            ggst_exact_character_query
            and not sf6_exact_character_query
            and not explicit_ggacr_query
            and not ggacr_exclusive_character_query
        )
    )
    ggacr_rows = ggacr_payload.get("rows", [])
    ggacr_lookup_intent = bool(
        ggacr_payload.get("frame_query")
        or ggacr_payload.get("gif_query")
        or ggacr_payload.get("game_query")
        or ggacr_payload.get("notes_query")
        or requested_property_key
    )
    ggacr_route_allowed = bool(
        ggacr_payload.get("game_query")
        or ggacr_exclusive_character_query
        or (
            ggacr_exact_character_query
            and explicit_ggacr_query
            and ggacr_module.query_has_ggacr_notation(content_lower)
        )
        or (
            ggacr_exact_character_query
            and ggacr_rows
            and explicit_ggacr_query
            and not sf6_exact_character_query
            and not ggst_exact_character_query
            and not sfv_exact_character_query
            and not tuco_exact_character_query
            and not bbcf_exact_character_query
            and not cotw_exact_character_query
            and not third_strike_exact_character_query
            and not mk1_exact_character_query
        )
    )
    if frame_command_is_addressed and ggacr_route_allowed and ggacr_lookup_intent and ggacr_rows:
        if ggacr_payload.get("needs_disambiguation"):
            await message.reply(ggacr_payload.get("data", "Please specify which GGACR move you mean."))
        else:
            await _send_cross_game_lookup_response(message, ggacr_module, ggacr_rows, ggacr_payload, content_lower)
        return
    elif frame_command_is_addressed and ggacr_route_allowed and ggacr_lookup_intent and ggacr_payload.get("needs_disambiguation"):
        await message.reply(ggacr_payload.get("data", "Please specify which GGACR move you mean."))
        return

    if frame_command_is_addressed and ggst_route_allowed and ggst_lookup_intent and not ggst_rows:
        rewritten_ggst_query = await buenavista_extension.rewrite_ggst_lookup_query(
            content_no_mentions,
            strip_discord_mentions,
            message=message,
        )
        if rewritten_ggst_query:
            rewritten_ggst_payload = ggst_module.find_moves_in_text(rewritten_ggst_query.lower())
            rewritten_ggst_rows = rewritten_ggst_payload.get("rows", []) or []
            if rewritten_ggst_rows or rewritten_ggst_payload.get("needs_disambiguation"):
                ggst_payload = rewritten_ggst_payload
                ggst_rows = rewritten_ggst_rows
                ggst_lookup_intent = bool(
                    ggst_payload.get("frame_query")
                    or ggst_payload.get("gif_query")
                    or ggst_payload.get("game_query")
                    or requested_property_key
                )
                print(f"[ggst-parser-private] rewritten query: {rewritten_ggst_query}", flush=True)

    if frame_command_is_addressed and ggst_route_allowed and ggst_lookup_intent and ggst_rows:
        if ggst_payload.get("needs_disambiguation"):
            await message.reply(ggst_payload.get("data", "Please specify which GGST move you mean."))
        else:
            await _send_cross_game_lookup_response(message, ggst_module, ggst_rows, ggst_payload, content_lower)
        return
    elif frame_command_is_addressed and ggst_route_allowed and ggst_lookup_intent and ggst_payload.get("needs_disambiguation"):
        await message.reply(ggst_payload.get("data", "Please specify which GGST move you mean."))
        return

    sfv_rows = sfv_payload.get("rows", [])
    sfv_character_query = bool(sfv_exact_character_query or sfv_payload.get("char_found"))
    sfv_lookup_intent = bool(
        sfv_payload.get("frame_query")
        or sfv_payload.get("gif_query")
        or sfv_payload.get("game_query")
        or sfv_payload.get("notes_query")
        or requested_property_key
        or sfv_module.query_has_sfv_notation(content_lower)
    )
    sfv_route_allowed = bool(
        sfv_payload.get("game_query")
        or (
            sfv_character_query
            and sfv_module.query_has_sfv_notation(content_lower)
            and not sf6_exact_character_query
            and not ggst_exact_character_query
            and not tuco_exact_character_query
            and not bbcf_exact_character_query
            and not cotw_exact_character_query
            and not third_strike_exact_character_query
            and not mk1_exact_character_query
        )
        or (
            sfv_character_query
            and sfv_rows
            and not sf6_exact_character_query
            and not ggst_exact_character_query
            and not tuco_exact_character_query
            and not bbcf_exact_character_query
            and not cotw_exact_character_query
            and not third_strike_exact_character_query
            and not mk1_exact_character_query
        )
    )
    if frame_command_is_addressed and sfv_route_allowed and sfv_lookup_intent and sfv_rows:
        if sfv_payload.get("needs_disambiguation"):
            await message.reply(sfv_payload.get("data", "Please specify which SFV move you mean."))
        else:
            await _send_cross_game_lookup_response(message, sfv_module, sfv_rows, sfv_payload, content_lower)
        return
    elif frame_command_is_addressed and sfv_route_allowed and sfv_lookup_intent and sfv_payload.get("needs_disambiguation"):
        await message.reply(sfv_payload.get("data", "Please specify which SFV move you mean."))
        return
    elif frame_command_is_addressed and sfv_route_allowed and sfv_lookup_intent and sfv_payload.get("explicit_move_attempt"):
        char_label = sfv_module.display_char_name(sfv_payload.get("char_key"))
        await _reply_and_log_response(
            message,
            f"I have SFV scrolls for {char_label}, but I couldn't find that move.",
            "missing_scrolls",
        )
        return

    tuco_rows = tuco_payload.get("rows", [])
    tuco_lookup_intent = bool(
        tuco_payload.get("frame_query")
        or tuco_payload.get("gif_query")
        or tuco_payload.get("game_query")
        or requested_property_key
    )
    tuco_route_allowed = bool(
        tuco_payload.get("game_query")
        or (tuco_exact_character_query and not sf6_exact_character_query and not ggst_exact_character_query and not sfv_exact_character_query)
    )
    if frame_command_is_addressed and tuco_route_allowed and tuco_lookup_intent and tuco_rows:
        if tuco_payload.get("needs_disambiguation"):
            await message.reply(tuco_payload.get("data", "Please specify which 2XKO move you mean."))
        else:
            await _send_cross_game_lookup_response(message, tuco_module, tuco_rows, tuco_payload, content_lower)
        return
    elif frame_command_is_addressed and tuco_route_allowed and tuco_lookup_intent and tuco_payload.get("needs_disambiguation"):
        await message.reply(tuco_payload.get("data", "Please specify which 2XKO move you mean."))
        return

    bbcf_rows = bbcf_payload.get("rows", [])
    bbcf_lookup_intent = bool(
        bbcf_payload.get("frame_query")
        or bbcf_payload.get("gif_query")
        or bbcf_payload.get("game_query")
        or bbcf_payload.get("notes_query")
        or requested_property_key
    )
    bbcf_route_allowed = bool(
        bbcf_payload.get("game_query")
        or (
            bbcf_exact_character_query
            and bbcf_module.query_has_bbcf_notation(content_lower)
            and not third_strike_module.query_has_third_strike_notation(content_lower)
        )
        or (
            bbcf_exact_character_query
            and bbcf_rows
            and not sf6_exact_character_query
            and not ggst_exact_character_query
            and not sfv_exact_character_query
            and not tuco_exact_character_query
            and not third_strike_exact_character_query
        )
    )
    if frame_command_is_addressed and bbcf_route_allowed and bbcf_lookup_intent and bbcf_rows:
        if bbcf_payload.get("needs_disambiguation"):
            await message.reply(bbcf_payload.get("data", "Please specify which BBCF move you mean."))
        else:
            await _send_cross_game_lookup_response(message, bbcf_module, bbcf_rows, bbcf_payload, content_lower)
        return
    elif frame_command_is_addressed and bbcf_route_allowed and bbcf_lookup_intent and bbcf_payload.get("needs_disambiguation"):
        await message.reply(bbcf_payload.get("data", "Please specify which BBCF move you mean."))
        return

    cotw_rows = cotw_payload.get("rows", [])
    cotw_lookup_intent = bool(
        cotw_payload.get("frame_query")
        or cotw_payload.get("gif_query")
        or cotw_payload.get("game_query")
        or cotw_payload.get("notes_query")
        or requested_property_key
    )
    cotw_route_allowed = bool(
        cotw_payload.get("game_query")
        or (
            cotw_exact_character_query
            and cotw_module.query_has_cotw_notation(content_lower)
        )
        or (
            cotw_exact_character_query
            and cotw_rows
            and not sf6_exact_character_query
            and not ggst_exact_character_query
            and not tuco_exact_character_query
            and not bbcf_exact_character_query
        )
    )
    if frame_command_is_addressed and cotw_route_allowed and cotw_lookup_intent and cotw_rows:
        if cotw_payload.get("needs_disambiguation"):
            await message.reply(cotw_payload.get("data", "Please specify which COTW move you mean."))
        else:
            await _send_cross_game_lookup_response(message, cotw_module, cotw_rows, cotw_payload, content_lower)
        return
    elif frame_command_is_addressed and cotw_route_allowed and cotw_lookup_intent and cotw_payload.get("needs_disambiguation"):
        await message.reply(cotw_payload.get("data", "Please specify which COTW move you mean."))
        return

    third_strike_rows = third_strike_payload.get("rows", [])
    third_strike_lookup_intent = bool(
        third_strike_payload.get("frame_query")
        or third_strike_payload.get("gif_query")
        or third_strike_payload.get("game_query")
        or third_strike_payload.get("notes_query")
        or requested_property_key
        or third_strike_module.query_has_third_strike_notation(content_lower)
    )
    third_strike_route_allowed = bool(
        third_strike_payload.get("game_query")
        or (
            third_strike_exact_character_query
            and third_strike_module.query_has_third_strike_notation(content_lower)
            and not sf6_exact_character_query
        )
        or (
            third_strike_exact_character_query
            and third_strike_rows
            and not sf6_exact_character_query
            and not ggst_exact_character_query
            and not tuco_exact_character_query
            and not bbcf_exact_character_query
            and not cotw_exact_character_query
            and not mk1_exact_character_query
            and not bbcf_module.query_has_bbcf_notation(content_lower)
        )
    )
    if frame_command_is_addressed and third_strike_route_allowed and third_strike_lookup_intent and third_strike_rows:
        if third_strike_payload.get("needs_disambiguation"):
            await message.reply(third_strike_payload.get("data", "Please specify which Third Strike move you mean."))
        else:
            await _send_cross_game_lookup_response(message, third_strike_module, third_strike_rows, third_strike_payload, content_lower)
        return
    elif frame_command_is_addressed and third_strike_route_allowed and third_strike_lookup_intent and third_strike_payload.get("needs_disambiguation"):
        await message.reply(third_strike_payload.get("data", "Please specify which Third Strike move you mean."))
        return
    elif frame_command_is_addressed and third_strike_route_allowed and third_strike_lookup_intent and third_strike_payload.get("explicit_move_attempt"):
        char_label = third_strike_module.display_char_name(third_strike_payload.get("char_key"))
        await _reply_and_log_response(
            message,
            f"I have Third Strike scrolls for {char_label}, but I couldn't find that move.",
            "missing_scrolls",
        )
        return

    mk1_rows = mk1_payload.get("rows", [])
    mk1_lookup_intent = bool(
        mk1_payload.get("frame_query")
        or mk1_payload.get("gif_query")
        or mk1_payload.get("game_query")
        or mk1_payload.get("notes_query")
        or requested_property_key
        or mk1_module.query_has_mk1_notation(content_lower)
    )
    mk1_route_allowed = bool(
        mk1_payload.get("game_query")
        or (
            mk1_exact_character_query
            and mk1_module.query_has_mk1_notation(content_lower)
            and not sf6_exact_character_query
        )
        or (
            mk1_exact_character_query
            and mk1_rows
            and not sf6_exact_character_query
            and not ggst_exact_character_query
            and not sfv_exact_character_query
            and not tuco_exact_character_query
            and not bbcf_exact_character_query
            and not cotw_exact_character_query
            and not third_strike_exact_character_query
        )
    )
    if frame_command_is_addressed and mk1_route_allowed and mk1_lookup_intent and mk1_rows:
        if mk1_payload.get("needs_disambiguation"):
            await message.reply(mk1_payload.get("data", "Please specify which MK1 move you mean."))
        else:
            await _send_cross_game_lookup_response(message, mk1_module, mk1_rows, mk1_payload, content_lower)
        return
    elif frame_command_is_addressed and mk1_route_allowed and mk1_lookup_intent and mk1_payload.get("needs_disambiguation"):
        await message.reply(mk1_payload.get("data", "Please specify which MK1 move you mean."))
        return
    elif frame_command_is_addressed and mk1_route_allowed and mk1_lookup_intent and mk1_payload.get("explicit_move_attempt"):
        char_label = mk1_module.display_char_name(mk1_payload.get("char_key"))
        await _reply_and_log_response(
            message,
            f"I have MK1 scrolls for {char_label}, but I couldn't find that move.",
            "missing_scrolls",
        )
        return

    if (
        frame_command_is_addressed
        and mk1_route_allowed
        and not mk1_lookup_intent
        and allow_implied_frame_routing
        and (mk1_rows or mk1_payload.get("needs_disambiguation"))
    ):
        if mk1_payload.get("needs_disambiguation"):
            await message.reply(mk1_payload.get("data", "Please specify which MK1 move you mean."))
        else:
            _record_frame_data_ids(await mk1_module.send_frame_response(message, mk1_rows))
        return

    if (
        frame_command_is_addressed
        and sfv_route_allowed
        and not sfv_lookup_intent
        and allow_implied_frame_routing
        and (sfv_rows or sfv_payload.get("needs_disambiguation"))
    ):
        if sfv_payload.get("needs_disambiguation"):
            await message.reply(sfv_payload.get("data", "Please specify which SFV move you mean."))
        else:
            _record_frame_data_ids(await sfv_module.send_frame_response(message, sfv_rows))
        return

    if (
        frame_command_is_addressed
        and third_strike_route_allowed
        and not third_strike_lookup_intent
        and allow_implied_frame_routing
        and (third_strike_rows or third_strike_payload.get("needs_disambiguation"))
    ):
        if third_strike_payload.get("needs_disambiguation"):
            await message.reply(third_strike_payload.get("data", "Please specify which Third Strike move you mean."))
        else:
            _record_frame_data_ids(await third_strike_module.send_frame_response(message, third_strike_rows))
        return

    if (
        frame_command_is_addressed
        and tuco_route_allowed
        and not tuco_lookup_intent
        and allow_implied_frame_routing
        and (tuco_rows or tuco_payload.get("needs_disambiguation"))
    ):
        if tuco_payload.get("needs_disambiguation"):
            await message.reply(tuco_payload.get("data", "Please specify which 2XKO move you mean."))
        else:
            _record_frame_data_ids(await tuco_module.send_frame_response(message, tuco_rows))
        return

    if (
        frame_command_is_addressed
        and bbcf_route_allowed
        and not bbcf_lookup_intent
        and allow_implied_frame_routing
        and (bbcf_rows or bbcf_payload.get("needs_disambiguation"))
    ):
        if bbcf_payload.get("needs_disambiguation"):
            await message.reply(bbcf_payload.get("data", "Please specify which BBCF move you mean."))
        else:
            _record_frame_data_ids(await bbcf_module.send_frame_response(message, bbcf_rows))
        return

    if (
        frame_command_is_addressed
        and ggacr_route_allowed
        and not ggacr_lookup_intent
        and allow_implied_frame_routing
        and (ggacr_rows or ggacr_payload.get("needs_disambiguation"))
    ):
        if ggacr_payload.get("needs_disambiguation"):
            await message.reply(ggacr_payload.get("data", "Please specify which GGACR move you mean."))
        else:
            _record_frame_data_ids(await ggacr_module.send_frame_response(message, ggacr_rows))
        return

    if (
        frame_command_is_addressed
        and cotw_route_allowed
        and not cotw_lookup_intent
        and allow_implied_frame_routing
        and (cotw_rows or cotw_payload.get("needs_disambiguation"))
    ):
        if cotw_payload.get("needs_disambiguation"):
            await message.reply(cotw_payload.get("data", "Please specify which COTW move you mean."))
        else:
            _record_frame_data_ids(await cotw_module.send_frame_response(message, cotw_rows))
        return

    if (
        frame_command_is_addressed
        and ggst_route_allowed
        and not ggst_lookup_intent
        and allow_implied_frame_routing
        and (ggst_rows or ggst_payload.get("needs_disambiguation"))
    ):
        if ggst_payload.get("needs_disambiguation"):
            await message.reply(ggst_payload.get("data", "Please specify which GGST move you mean."))
        else:
            _record_frame_data_ids(await ggst_module.send_frame_response(message, ggst_rows))
        return
    return (fd_context_payload, frame_command_is_addressed, allow_implied_frame_routing)
async def _try_route_combo_query(
    message,
    content_lower,
    *,
    frame_command_is_addressed,
    sf6_exact_character_query,
    mk1_exact_character_query,
):
    """Route NL combo queries before SF6 frame parsing (avoids unrelated parser deps)."""
    if not frame_command_is_addressed:
        return False
    if not re.search(r"\b(?:combo|combos|bnb|bnbs|route|routes)\b", content_lower):
        return False

    if combo_data_module._query_has_game_tag(content_lower, "mk1"):
        combo_games = ["mk1"]
    elif combo_data_module._query_has_game_tag(content_lower, "sf6"):
        combo_games = ["sf6"]
    elif mk1_exact_character_query and not sf6_exact_character_query:
        combo_games = ["mk1"]
    elif sf6_exact_character_query and not mk1_exact_character_query:
        combo_games = ["sf6"]
    else:
        combo_games = ["sf6", "mk1"]

    for game in combo_games:
        if not combo_data_module.has_combos(game):
            continue
        combo_payload = combo_data_module.find_combo_rows_in_text(game, content_lower)
        if combo_payload.get("combo_query") and combo_payload.get("char_found"):
            nav, _details = combo_data_module.combo_entry_nav(
                game,
                combo_payload["char_key"],
                group=combo_payload.get("group"),
                rows=combo_payload.get("rows"),
            )
            if nav != "empty":
                _record_frame_data_ids(
                    await combo_data_module.send_combo_entry(
                        message,
                        game,
                        combo_payload["char_key"],
                        combo_payload,
                        owner_id=getattr(message.author, "id", None),
                        back_to="game_menu",
                    )
                )
                return True
        if combo_payload.get("combo_query") and combo_payload.get("char_found"):
            char_label = combo_data_module.display_char_name(game, combo_payload["char_key"])
            await _reply_and_log_response(
                message,
                f"No combos found for {char_label} with those filters.",
                "missing_scrolls",
            )
            return True
    return False

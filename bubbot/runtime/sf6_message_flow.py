"""SF6 frame, GIF, property, and Buenavista response flow."""

import re

import discord

client = None
buenavista_extension = None
sf6_prompt_replies = None
gif_lookup_module = None
find_moves_in_text = None
strip_discord_mentions = lambda text: str(text or "")
build_frame_embeds = None
iter_unique_frame_rows = None
send_character_stats_response = None
send_frame_table_response = None
send_gif_links_response = None
send_missing_hitbox_gif_reply = None
send_frame_embeds_with_views = None
collect_hitbox_gif_links_from_text = None
_record_frame_data_ids = lambda ids, **kwargs: None
_reply_and_log_response = None
_requested_property_key = None
_format_requested_property_reply = None
_send_property_value_reply = None
_resolve_special_strength_reply_mode = None
_sf6_prompt_reply_deps = None
format_range_only_reply = None
format_super_gain_only_reply = None
format_hitconfirm_only_reply = None
format_startup_only_reply = None
is_deleted_message_reference_error = None
send_deleted_message_failsafe = None
MISSING_SCROLLS_TEXT = ""
PUBLIC_INVALID_QUERY_TEXT = ""


def configure(**deps):
    globals().update(deps)


async def handle_sf6_message(
    message,
    *,
    content_lower,
    content_no_mentions,
    fd_context_payload,
    frame_command_is_addressed,
    allow_implied_frame_routing,
    directly_mentions_bot,
):
    # SF6 frame/gif path: unpack parser payload, optional BV LLM lookup rewrite, then respond
    check_media = False
    replied_context = None  # store bub's original message if replying to bot
    special_strength_reply_mode = None
    is_reply_to_bot = False
    
    
    # check mentions
    if directly_mentions_bot:
        check_media = True

    replied_context = None 
    

    fd_context_data = fd_context_payload.get("data", "")
    fd_context_mode = fd_context_payload.get("mode", "none")
    fd_context_rows = fd_context_payload.get("rows", [])
    startup_alias_query = bool(fd_context_payload.get("startup_alias_query"))
    hitconfirm_alias_query = bool(fd_context_payload.get("hitconfirm_alias_query"))
    super_gain_alias_query = bool(fd_context_payload.get("super_gain_alias_query"))
    range_alias_query = bool(fd_context_payload.get("range_alias_query"))
    wants_comparison = bool(fd_context_payload.get("wants_comparison"))
    property_only_query = bool(fd_context_payload.get("property_only_query"))
    target_combo_query = bool(fd_context_payload.get("target_combo_query"))
    missing_scrolls_query = bool(fd_context_payload.get("missing_scrolls_query"))
    gif_query = bool(fd_context_payload.get("gif_query"))
    explicit_move_attempt = bool(fd_context_payload.get("explicit_move_attempt"))
    fallback_reply = fd_context_data if fd_context_data else None

    def row_matches_requested_strength(row, query_text):
        move_name = str(row.get("moveName", "")).lower().strip()
        cmn_name = str(row.get("cmnName", "")).lower().strip()
        num_cmd = str(row.get("numCmd", "")).lower().strip()
        num_cmd_compact = re.sub(r"[^a-z0-9]", "", num_cmd)

        if re.search(r"\b(?:od|ex)\b", query_text):
            return (
                move_name.startswith(("od ", "ex "))
                or cmn_name.startswith(("od ", "ex "))
                or num_cmd_compact.endswith(("pp", "kk"))
            )

        strength_groups = [
            ({"light", "l", "lp", "lk"}, {"lp", "lk"}),
            ({"medium", "m", "mp", "mk"}, {"mp", "mk"}),
            ({"heavy", "h", "hp", "hk"}, {"hp", "hk"}),
        ]
        requested_suffixes = set()
        for token_group, suffixes in strength_groups:
            if any(re.search(rf"\b{re.escape(token)}\b", query_text) for token in token_group):
                requested_suffixes.update(suffixes)
        if not requested_suffixes:
            return False

        if any(
            move_name.startswith(f"{suffix} ") or cmn_name.startswith(f"{suffix} ")
            for suffix in requested_suffixes
        ):
            return True
        return num_cmd_compact.endswith(tuple(requested_suffixes))

    def row_has_explicit_strength(row):
        move_name = str(row.get("moveName", "")).lower().strip()
        cmn_name = str(row.get("cmnName", "")).lower().strip()
        num_cmd_compact = re.sub(r"[^a-z0-9]", "", str(row.get("numCmd", "")).lower())
        return (
            move_name.startswith(("lp ", "mp ", "hp ", "lk ", "mk ", "hk ", "od ", "ex "))
            or cmn_name.startswith(("lp ", "mp ", "hp ", "lk ", "mk ", "hk ", "od ", "ex "))
            or num_cmd_compact.endswith(("lp", "mp", "hp", "lk", "mk", "hk", "pp", "kk"))
        )

    query_requests_explicit_strength = bool(
        re.search(r"\b(?:od|ex|lp|mp|hp|lk|mk|hk|light|medium|heavy|l|m|h)\b", content_lower)
    )
    payload_strength_mismatch = bool(
        query_requests_explicit_strength
        and fd_context_rows
        and any(row_has_explicit_strength(row) for row in fd_context_rows)
        and not any(row_matches_requested_strength(row, content_lower) for row in fd_context_rows)
    )

    should_try_private_lookup_rewrite = bool(
        directly_mentions_bot
        and (fd_context_payload.get("gif_query") or re.search(r"\b(?:framedata|frame\s*data|frames?)\b", content_lower))
        and (not fd_context_rows or payload_strength_mismatch)
        and "Special Strength Options" not in str(fd_context_data)
        and "Target Combo Options" not in str(fd_context_data)
        and not startup_alias_query
        and not hitconfirm_alias_query
        and not super_gain_alias_query
        and not range_alias_query
    )
    if should_try_private_lookup_rewrite:
        rewritten_lookup_query = await buenavista_extension.rewrite_sf_lookup_query(
            content_no_mentions,
            strip_discord_mentions,
            message=message,
        )
        if rewritten_lookup_query:
            rewritten_payload = find_moves_in_text(rewritten_lookup_query.lower())
            rewritten_data = str(rewritten_payload.get("data", "") or "")
            rewritten_rows = rewritten_payload.get("rows", []) or []
            if (
                rewritten_rows
                or "Special Strength Options" in rewritten_data
                or "Target Combo Options" in rewritten_data
            ):
                content_no_mentions = rewritten_lookup_query
                content_lower = rewritten_lookup_query.lower()
                fd_context_payload = rewritten_payload
                fd_context_data = rewritten_payload.get("data", "")
                fd_context_mode = rewritten_payload.get("mode", "none")
                fd_context_rows = rewritten_rows
                startup_alias_query = bool(rewritten_payload.get("startup_alias_query"))
                hitconfirm_alias_query = bool(rewritten_payload.get("hitconfirm_alias_query"))
                super_gain_alias_query = bool(rewritten_payload.get("super_gain_alias_query"))
                range_alias_query = bool(rewritten_payload.get("range_alias_query"))
                wants_comparison = bool(rewritten_payload.get("wants_comparison"))
                property_only_query = bool(rewritten_payload.get("property_only_query"))
                target_combo_query = bool(rewritten_payload.get("target_combo_query"))
                missing_scrolls_query = bool(rewritten_payload.get("missing_scrolls_query"))
                gif_query = bool(rewritten_payload.get("gif_query"))
                explicit_move_attempt = bool(rewritten_payload.get("explicit_move_attempt"))
                fallback_reply = fd_context_data if fd_context_data else None
                print(f"[parser-private] rewritten query: {rewritten_lookup_query}", flush=True)

    if gif_query and not frame_command_is_addressed:
        return

    explicit_frame_request = (
        "framedata" in content_lower
        or "frame data" in content_lower
        or re.search(r"\bframes?\b", content_lower)
        or re.search(r"\bhow\s+fast\b", content_lower)
        or re.search(r"\bhow\s+quick\b", content_lower)
        or re.search(r"\bspeed\s+of\b", content_lower)
        or (
            re.search(r"\bfast\b", content_lower)
            and re.search(r"\b[1-9][0-9]*[a-zA-Z]{1,3}\b", content_lower)
        )
    )
    force_verbatim_frame_reply = bool(
        fd_context_mode == "frame"
        and not property_only_query
        and fd_context_rows
    )
    frame_reply_embeds = (
        build_frame_embeds(fd_context_rows)
        if force_verbatim_frame_reply and fd_context_rows
        else []
    )
    frame_reply_rows = (
        iter_unique_frame_rows(fd_context_rows)
        if force_verbatim_frame_reply and fd_context_rows
        else []
    )
    if frame_reply_embeds:
        print(
            "Frame embed mode active: "
            f"count={len(frame_reply_embeds)} property_only={property_only_query}",
            flush=True,
        )
    

    
    should_handle_direct_frame = (
        frame_command_is_addressed
        or ".framedata" in content_lower
    )
    combined_frame_gif_request = bool(
        gif_query
        and explicit_frame_request
        and fd_context_mode == "frame"
        and not property_only_query
        and not startup_alias_query
        and not hitconfirm_alias_query
        and not super_gain_alias_query
        and not range_alias_query
    )

    vague_move_query_without_output_intent = False
    implied_rows = []
    implied_data = ""
    if (
        frame_command_is_addressed
        and allow_implied_frame_routing
        and not gif_query
        and not explicit_frame_request
        and not property_only_query
        and not target_combo_query
        and not startup_alias_query
        and not hitconfirm_alias_query
        and not super_gain_alias_query
        and not range_alias_query
        and not re.search(
            r"\b(punish|punishable|compare|comparison|versus|vs|stats?|health|reversal|combo|bnb|oki|playstyle|overview)\b",
            content_lower,
        )
        and not buenavista_extension.should_suppress_public_implied_frame_lookup(content_lower, message=message)
    ):
        implied_frame_payload = find_moves_in_text(f"{content_lower} framedata")
        implied_data = implied_frame_payload.get("data", "")
        implied_rows = implied_frame_payload.get("rows", [])
        implied_mode = implied_frame_payload.get("mode", "none")
        implied_explicit_move_attempt = bool(implied_frame_payload.get("explicit_move_attempt"))
        implied_has_special_prompt = "Special Strength Options" in implied_data
        vague_move_query_without_output_intent = bool(
            implied_explicit_move_attempt
            and (
                (implied_mode == "frame" and implied_rows)
                or implied_has_special_prompt
            )
        )

    if (
        not vague_move_query_without_output_intent
        and frame_command_is_addressed
        and allow_implied_frame_routing
        and target_combo_query
        and explicit_move_attempt
        and fd_context_mode == "frame"
        and fd_context_rows
        and not gif_query
        and not explicit_frame_request
        and not property_only_query
        and not startup_alias_query
        and not hitconfirm_alias_query
        and not super_gain_alias_query
        and not range_alias_query
    ):
        vague_move_query_without_output_intent = True

    if should_handle_direct_frame:
        if (
            frame_command_is_addressed
            and fd_context_payload.get("stats_only")
            and fd_context_payload.get("stats_char_keys")
        ):
            stats_sent_ids = await send_character_stats_response(
                message,
                fd_context_payload.get("stats_char_keys"),
                fd_context_payload.get("stats_keys"),
            )
            _record_frame_data_ids(stats_sent_ids)
            if not stats_sent_ids:
                await message.reply("I don't have stats scrolls for that character.")
            return

        if vague_move_query_without_output_intent:
            default_rows = implied_rows or fd_context_rows
            default_data = implied_data or fd_context_data
            frame_sent_ids = await send_frame_table_response(message, default_rows, default_data)
            _record_frame_data_ids(frame_sent_ids)
            if not frame_sent_ids and default_data:
                sent = await message.reply(default_data)
                _record_frame_data_ids([sent.id], response_text=default_data)
            return

        if (
            wants_comparison
            and fd_context_mode == "frame"
            and fd_context_rows
            and explicit_move_attempt
            and not gif_query
            and not property_only_query
            and not target_combo_query
            and not startup_alias_query
            and not hitconfirm_alias_query
            and not super_gain_alias_query
            and not range_alias_query
        ):
            frame_sent_ids = await send_frame_table_response(message, fd_context_rows, fd_context_data)
            _record_frame_data_ids(frame_sent_ids)
            if not frame_sent_ids and fd_context_data:
                try:
                    sent = await message.reply(fd_context_data)
                    _record_frame_data_ids([sent.id], response_text=fd_context_data)
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Comparison frame reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Comparison frame reply error: {reply_error}", flush=True)
            return

        if combined_frame_gif_request and frame_command_is_addressed:
            if "Special Strength Options" in fd_context_data:
                try:
                    sent_prompt = await message.reply(fd_context_data)
                    sf6_prompt_replies.remember_special_strength_prompt_mode(sent_prompt.id, "both")
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Special strength options both reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Special strength options both reply error: {reply_error}", flush=True)
                return

            if not explicit_move_attempt:
                await message.reply("Tell me the exact move too, like 'aki 5hp gif framedata'.")
                return

            if missing_scrolls_query:
                try:
                    await _reply_and_log_response(message, MISSING_SCROLLS_TEXT, "missing_scrolls")
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Missing-scrolls both reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Missing-scrolls both reply error: {reply_error}", flush=True)
                return

            frame_table_already_sent = False
            if fd_context_rows:
                _record_frame_data_ids(await send_frame_table_response(message, fd_context_rows, fd_context_data))
                frame_table_already_sent = True

                gif_frame_rows = fd_context_rows
                if wants_comparison and fd_context_rows:
                    comparison_rows = []
                    seen_comparison_chars = set()
                    for row in fd_context_rows:
                        row_char = normalize_char_name(row.get("char_name", ""))
                        if not row_char or row_char in seen_comparison_chars:
                            continue
                        seen_comparison_chars.add(row_char)
                        comparison_rows.append(row)
                    if len(comparison_rows) >= 2:
                        gif_frame_rows = comparison_rows

                gif_limit = gif_lookup_module.DISCORD_ATTACHMENT_LIMIT
                if wants_comparison and gif_frame_rows:
                    gif_limit = max(gif_limit, len(gif_frame_rows))

                gif_links = collect_hitbox_gif_links_from_text(
                    content_no_mentions,
                    frame_rows=gif_frame_rows,
                    limit=gif_limit,
                    prefer_frame_rows=wants_comparison,
                )
                if gif_links:
                    _record_frame_data_ids(await send_gif_links_response(
                        message,
                        gif_links,
                        wants_comparison=wants_comparison,
                    ))
                    return

                try:
                    await send_missing_hitbox_gif_reply(
                        message,
                        fd_context_rows,
                        include_framedata_button=not frame_table_already_sent,
                        reply_and_log_response=_reply_and_log_response,
                        record_frame_data_ids=_record_frame_data_ids,
                    )
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Missing-gif both reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Missing-gif both reply error: {reply_error}", flush=True)
                return

        if gif_query and frame_command_is_addressed:
            if "Special Strength Options" in fd_context_data:
                try:
                    sent_prompt = await message.reply(fd_context_data)
                    sf6_prompt_replies.remember_special_strength_prompt_mode(sent_prompt.id, "gif")
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Special strength options gif reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Special strength options gif reply error: {reply_error}", flush=True)
                return

            if not explicit_move_attempt:
                await message.reply("Tell me the exact move too, like 'aki 5hp gif'.")
                return

            gif_frame_rows = fd_context_rows
            if wants_comparison and fd_context_rows:
                comparison_rows = []
                seen_comparison_chars = set()
                for row in fd_context_rows:
                    row_char = normalize_char_name(row.get("char_name", ""))
                    if not row_char or row_char in seen_comparison_chars:
                        continue
                    seen_comparison_chars.add(row_char)
                    comparison_rows.append(row)
                if len(comparison_rows) >= 2:
                    gif_frame_rows = comparison_rows

            gif_limit = gif_lookup_module.DISCORD_ATTACHMENT_LIMIT
            if wants_comparison and gif_frame_rows:
                gif_limit = max(gif_limit, len(gif_frame_rows))

            gif_links = collect_hitbox_gif_links_from_text(
                content_no_mentions,
                frame_rows=gif_frame_rows,
                limit=gif_limit,
                prefer_frame_rows=wants_comparison,
            )
            if gif_links:
                _record_frame_data_ids(await send_gif_links_response(
                    message,
                    gif_links,
                    wants_comparison=wants_comparison,
                ))
                return

            if fd_context_rows:
                try:
                    await send_missing_hitbox_gif_reply(
                        message,
                        fd_context_rows,
                        reply_and_log_response=_reply_and_log_response,
                        record_frame_data_ids=_record_frame_data_ids,
                    )
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Missing-gif reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Missing-gif reply error: {reply_error}", flush=True)
                return

        if missing_scrolls_query:
            try:
                await _reply_and_log_response(message, MISSING_SCROLLS_TEXT, "missing_scrolls")
            except Exception as reply_error:
                if is_deleted_message_reference_error(reply_error):
                    print("Missing-scrolls reply target deleted. Triggering failsafe.", flush=True)
                    await send_deleted_message_failsafe(message.channel)
                else:
                    print(f"Missing-scrolls reply error: {reply_error}", flush=True)
            return
        if "Target Combo Options" in fd_context_data:
            try:
                await message.reply(fd_context_data)
            except Exception as reply_error:
                if is_deleted_message_reference_error(reply_error):
                    print("Target combo options reply target deleted. Triggering failsafe.", flush=True)
                    await send_deleted_message_failsafe(message.channel)
                else:
                    print(f"Target combo options reply error: {reply_error}", flush=True)
            return
        if "Special Strength Options" in fd_context_data:
            try:
                sent_prompt = await message.reply(fd_context_data)
                sf6_prompt_replies.remember_special_strength_prompt_mode(
                    sent_prompt.id,
                    "gif" if gif_query else "frame",
                )
            except Exception as reply_error:
                if is_deleted_message_reference_error(reply_error):
                    print("Special strength options reply target deleted. Triggering failsafe.", flush=True)
                    await send_deleted_message_failsafe(message.channel)
                else:
                    print(f"Special strength options reply error: {reply_error}", flush=True)
            return
        if target_combo_query and fd_context_mode == "frame" and fd_context_rows:
            _record_frame_data_ids(await send_frame_table_response(message, fd_context_rows, fd_context_data))
            return
        requested_sf6_property_key = _requested_property_key(content_lower)
        if property_only_query and requested_sf6_property_key and fd_context_mode == "frame" and fd_context_rows:
            property_reply = _format_requested_property_reply(fd_context_rows, requested_sf6_property_key)
            if property_reply:
                try:
                    await _send_property_value_reply(message, fd_context_rows, requested_sf6_property_key, content=property_reply, game="sf6")
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Direct property reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Direct property reply error: {reply_error}", flush=True)
                return
        if range_alias_query and fd_context_mode == "frame" and fd_context_rows:
            range_reply = format_range_only_reply(fd_context_rows)
            if range_reply:
                try:
                    await _send_property_value_reply(message, fd_context_rows, "range", content=range_reply, game="sf6")
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Direct range reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Direct range reply error: {reply_error}", flush=True)
                return
        if super_gain_alias_query and fd_context_mode == "frame" and fd_context_rows:
            super_gain_reply = format_super_gain_only_reply(fd_context_rows)
            if super_gain_reply:
                try:
                    await _send_property_value_reply(message, fd_context_rows, "super_gain", content=super_gain_reply, game="sf6")
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Direct super gain reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Direct super gain reply error: {reply_error}", flush=True)
                return
        if hitconfirm_alias_query and fd_context_mode == "frame" and fd_context_rows:
            hitconfirm_reply = format_hitconfirm_only_reply(fd_context_rows)
            if hitconfirm_reply:
                try:
                    await _send_property_value_reply(message, fd_context_rows, "hitconfirm", content=hitconfirm_reply, game="sf6")
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Direct hitconfirm reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Direct hitconfirm reply error: {reply_error}", flush=True)
                return
        if startup_alias_query and fd_context_mode == "frame" and fd_context_rows:
            startup_reply = format_startup_only_reply(fd_context_rows)
            if startup_reply:
                try:
                    await _send_property_value_reply(message, fd_context_rows, "startup", content=startup_reply, game="sf6")
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Direct startup reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Direct startup reply error: {reply_error}", flush=True)
                return

        if (
            explicit_frame_request
            and fd_context_mode == "frame"
            and fd_context_rows
            and not property_only_query
            and not target_combo_query
            and not startup_alias_query
            and not hitconfirm_alias_query
            and not super_gain_alias_query
            and not range_alias_query
            and not gif_query
        ):
            frame_sent_ids = await send_frame_table_response(message, fd_context_rows, fd_context_data)
            _record_frame_data_ids(frame_sent_ids)
            if not frame_sent_ids and fd_context_data:
                try:
                    sent = await message.reply(fd_context_data)
                    _record_frame_data_ids([sent.id], response_text=fd_context_data)
                except Exception as reply_error:
                    if is_deleted_message_reference_error(reply_error):
                        print("Direct frame reply target deleted. Triggering failsafe.", flush=True)
                        await send_deleted_message_failsafe(message.channel)
                    else:
                        print(f"Direct frame reply error: {reply_error}", flush=True)
            return

        if buenavista_extension.should_handle_frame_context_request(
            content_lower=content_lower,
            fd_context_data=fd_context_data,
            message=message,
        ):
            handled = await buenavista_extension.maybe_handle_frame_context(
                client=client,
                message=message,
                content_no_mentions=content_no_mentions,
                content_lower=content_lower,
                fd_context_payload=fd_context_payload,
                fd_context_data=fd_context_data,
                fd_context_mode=fd_context_mode,
                fd_context_rows=fd_context_rows,
                property_only_query=property_only_query,
                frame_reply_embeds=frame_reply_embeds,
                frame_reply_rows=frame_reply_rows,
                fallback_reply=fallback_reply,
                strip_discord_mentions=strip_discord_mentions,
                is_deleted_message_reference_error=is_deleted_message_reference_error,
                send_frame_embeds_with_views=send_frame_embeds_with_views,
                record_frame_data_ids=_record_frame_data_ids,
            )
            if handled:
                return

    if replied_context is None and message.reference:
        try:
            if message.reference.cached_message:
                replied_msg = message.reference.cached_message
            else:
                replied_msg = await message.channel.fetch_message(message.reference.message_id)
            
            # replying to bot
            if replied_msg.author == client.user:
                check_media = True # check media on reply
                is_reply_to_bot = True
                if "Target Combo Options" in replied_msg.content:
                    replied_context = replied_msg.content  # capture only TC prompt
                elif "Special Strength Options" in replied_msg.content:
                    replied_context = replied_msg.content
                    special_strength_reply_mode = await _resolve_special_strength_reply_mode(replied_msg)

        except discord.NotFound:
            pass
        except discord.Forbidden:
            pass
        except Exception as e:
            print(f"Reply logic error: {e}")

    # SF6 target combo / special strength numbered replies
    if await sf6_prompt_replies.handle_sf6_prompt_reply(
        _sf6_prompt_reply_deps(),
        message,
        replied_context,
        content_no_mentions,
        gif_query=gif_query,
        special_strength_reply_mode=special_strength_reply_mode,
    ):
        return

    # BV LLM chat when enabled; otherwise fall through to public invalid-query notice in BV too
    should_respond = buenavista_extension.should_handle_chat_trigger(
        client=client,
        message=message,
        is_reply_to_bot=is_reply_to_bot,
        replied_context=replied_context,
    )
    if should_respond:
        handled = await buenavista_extension.maybe_handle_chat(
            client=client,
            message=message,
            content_no_mentions=content_no_mentions,
            content_lower=content_lower,
            replied_context=replied_context,
            fallback_reply=fallback_reply,
            frame_reply_embeds=frame_reply_embeds,
            frame_reply_rows=frame_reply_rows,
            strip_discord_mentions=strip_discord_mentions,
            is_deleted_message_reference_error=is_deleted_message_reference_error,
            send_frame_embeds_with_views=send_frame_embeds_with_views,
            record_frame_data_ids=_record_frame_data_ids,
        )
        if handled:
            return

    if frame_command_is_addressed and buenavista_extension.should_send_public_invalid_query_notice(message):
        await _reply_and_log_response(
            message,
            PUBLIC_INVALID_QUERY_TEXT,
            "public_invalid_query",
        )
        return

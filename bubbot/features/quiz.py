"""Compatibility facade for the split quiz modules."""

from . import quiz_answers, quiz_core, quiz_leaderboard, quiz_session, quiz_ui


def _public_values(module):
    return {
        key: value
        for key, value in vars(module).items()
        if not key.startswith("__") and key not in {"configure", "bind"}
    }


def _bind_modules():
    modules = (quiz_core, quiz_answers, quiz_leaderboard, quiz_session, quiz_ui)
    # quiz_core owns injected runtime dependencies; sibling snapshots can be
    # stale after a loader mutates or replaces one of those values.
    values = _public_values(quiz_core)
    core_keys = set(values)
    for module in modules[1:]:
        for key, value in _public_values(module).items():
            if key not in core_keys:
                values[key] = value
    for module in modules:
        module.bind(**values)
    globals().update(
        {
            key: value
            for key, value in values.items()
            if key not in {"QUIZ_GLOBAL_LEADERBOARD", "QUIZ_GLOBAL_LEADERBOARD_NAMES"}
        }
    )


def configure(**deps):
    quiz_core.configure(**deps)
    _bind_modules()


def reset_quiz_caches():
    quiz_core.QUIZ_CHARACTER_TERMS_CACHE = {}
    quiz_core.QUIZ_MOVE_NAME_TERMS_CACHE = {}
    quiz_core.QUIZ_CHARACTER_CENSOR_PATTERNS_CACHE = {}
    _bind_modules()


def __getattr__(name):
    for module in (quiz_core, quiz_answers, quiz_leaderboard, quiz_session, quiz_ui):
        if hasattr(module, name):
            return getattr(module, name)
    raise AttributeError(name)




def check_quiz_answer(quiz_state, text):
    return quiz_answers.check_quiz_answer(quiz_state, text)


def load_quiz_leaderboard():
    return quiz_leaderboard.load_quiz_leaderboard()


def save_quiz_leaderboard():
    return quiz_leaderboard.save_quiz_leaderboard()


# Quiz message activation, pending difficulty, and active-round routing.
def _quiz_message_directly_mentions_user(user, message):
    user_id = getattr(user, "id", None)
    if user_id is None:
        return False
    if any(getattr(mention, "id", None) == user_id for mention in getattr(message, "mentions", []) or []):
        return True
    return user_id in (getattr(message, "raw_mentions", []) or [])


async def route_message(client, message, content_lower):
    channel_id = message.channel.id
    in_quiz = channel_id in ACTIVE_QUIZZES
    quiz_state = ACTIVE_QUIZZES.get(channel_id)
    requested_quiz_mode = _quiz_extract_mode_from_text(content_lower)
    requested_quiz_game = _quiz_extract_game_from_text(
        content_lower,
        default=(quiz_state or {}).get("game", "sf6"),
    )
    directly_mentions_bot = _quiz_message_directly_mentions_user(client.user, message)
    answer_is_addressed = directly_mentions_bot or _is_reply_to_quiz_msg(message)
    mode_prompt_reply = _is_reply_to_quiz_mode_prompt(message)
    command_is_addressed = directly_mentions_bot or mode_prompt_reply

    if command_is_addressed and _quiz_is_leaderboard_request(content_lower):
        if not _quiz_message_in_leaderboard_guild(message):
            try:
                await message.reply("The persistent quiz leaderboard is only available in Buenavista.")
            except Exception as error:
                if is_deleted_message_reference_error(error):
                    await message.channel.send("The persistent quiz leaderboard is only available in Buenavista.")
                else:
                    print(f"[quiz] leaderboard scope reply error: {error}", flush=True)
            return
        top_limit = _quiz_extract_leaderboard_top_limit(content_lower)
        leaderboard_reply = _quiz_format_global_leaderboard_reply(limit=top_limit)
        try:
            await message.reply(leaderboard_reply)
        except Exception as error:
            if is_deleted_message_reference_error(error):
                await message.channel.send(leaderboard_reply)
            else:
                print(f"[quiz] leaderboard reply error: {error}", flush=True)
        return

    if not in_quiz and _quiz_pending_mode_active(channel_id):
        pending_mode = QUIZ_PENDING_MODE.get(channel_id, {})
        pending_mode_game = _quiz_game_key(pending_mode.get("game", requested_quiz_game))
        if command_is_addressed and requested_quiz_mode in QUIZ_VALID_MODES:
            QUIZ_PENDING_MODE.pop(channel_id, None)
            await start_quiz(
                message,
                mode=requested_quiz_mode,
                game=pending_mode_game,
                session_scores=dict(pending_mode.get("scores") or {}),
                session_score_names=dict(pending_mode.get("score_names") or {}),
                session_round=pending_mode.get("round", 1),
                session_message_ids=list(pending_mode.get("message_ids") or []),
            )
            return
        if command_is_addressed:
            if re.search(r"\b(stop|end|quit|cancel)\b", content_lower):
                QUIZ_PENDING_MODE.pop(channel_id, None)
                try:
                    await message.reply("Quiz setup cancelled.")
                except Exception as error:
                    if is_deleted_message_reference_error(error):
                        await message.channel.send("Quiz setup cancelled.")
                    else:
                        print(f"[quiz] mode-cancel reply error: {error}", flush=True)
                return
            if mode_prompt_reply or QUIZ_INTENT_RE.search(content_lower):
                await prompt_quiz_mode_selection(
                    message,
                    game=pending_mode_game,
                    session_mode=pending_mode.get("mode"),
                    session_scores=dict(pending_mode.get("scores") or {}),
                    session_score_names=dict(pending_mode.get("score_names") or {}),
                    session_round=pending_mode.get("round", 1),
                    session_message_ids=list(pending_mode.get("message_ids") or []),
                )
                return

    if in_quiz and answer_is_addressed:
        if re.search(r"\b(stop|end|quit|cancel)\b", content_lower):
            await stop_quiz(message)
            return
        if quiz_state and not quiz_state.get("awaiting_choice") and QUIZ_FORFEIT_RE.search(content_lower):
            await stop_quiz(message)
            return
        if QUIZ_CHEAT_LOOKUP_RE.search(content_lower):
            cheat_reply = await build_quiz_cheating_warning_message(
                message.channel,
                sanitize_ascii_line,
                _quiz_intro_has_specific_answer_hint,
            )
            try:
                sent = await message.reply(cheat_reply)
                _quiz_track_message_id(quiz_state, getattr(sent, "id", None))
            except Exception as error:
                if is_deleted_message_reference_error(error):
                    sent = await message.channel.send(cheat_reply)
                    _quiz_track_message_id(quiz_state, getattr(sent, "id", None))
                else:
                    print(f"[quiz] cheating-warning reply error: {error}", flush=True)
            return
        if quiz_state and quiz_state.get("awaiting_choice"):
            if await handle_quiz_answer(message) or await handle_quiz_post_answer_choice(message):
                return
            if not QUIZ_INTENT_RE.search(content_lower):
                return
        elif not QUIZ_INTENT_RE.search(content_lower):
            if await handle_quiz_answer(message):
                return
            return

    if command_is_addressed and QUIZ_INTENT_RE.search(content_lower):
        if re.search(r"\b(stop|end|quit|cancel)\b", content_lower):
            await stop_quiz(message)
        elif requested_quiz_mode not in QUIZ_VALID_MODES:
            await prompt_quiz_mode_selection(message, game=requested_quiz_game)
        else:
            await start_quiz(message, mode=requested_quiz_mode, game=requested_quiz_game)
        return
    return False

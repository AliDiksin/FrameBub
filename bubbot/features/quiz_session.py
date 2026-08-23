"""Quiz session state, transitions, timeout handling, and answer routing."""

import asyncio
import datetime
import os
import random
import re


def bind(**values):
    globals().update(values)

def _quiz_unique_rows_for_char(char_key, asked=None, mode="hard", game="sf6"):
    """Return mode-filtered rows whose moveName is unique within the character sheet."""
    mode_key = _quiz_normalize_mode(mode)
    asked = asked or set()
    game_key = _quiz_game_key(game)
    rows = _quiz_rows_for_char(game_key, char_key)
    if not rows:
        return []

    name_counts = {}
    for row in rows:
        if not _quiz_row_has_data(row):
            continue
        if not _quiz_row_allowed_for_mode(row, mode_key, game=game_key):
            continue
        name_key = _normalize_quiz_name(row.get("moveName", ""))
        if not name_key:
            continue
        name_counts[name_key] = name_counts.get(name_key, 0) + 1

    unique_rows = []
    for row in rows:
        if not _quiz_row_has_data(row):
            continue
        if not _quiz_row_allowed_for_mode(row, mode_key, game=game_key):
            continue
        numcmd = str(row.get("numCmd", "")).strip().lower()
        if (game_key, char_key, numcmd) in asked or (char_key, numcmd) in asked:
            continue
        name_key = _normalize_quiz_name(row.get("moveName", ""))
        if name_counts.get(name_key, 0) == 1:
            unique_rows.append(row)

    return unique_rows


def pick_quiz_move(asked=None, mode="hard", game="sf6"):
    """
    Pick a random (char_key, row) from FRAME_DATA suitable for a quiz question.
    `asked` is an optional set of (char_key, numcmd) tuples already used this session.
    """
    mode_key = _quiz_normalize_mode(mode)
    game_key = _quiz_game_key(game)
    asked = asked or set()
    frame_data = _quiz_game_data(game_key)
    if not frame_data:
        return None, None
    char_keys = [k for k, rows in frame_data.items() if rows]
    if not char_keys:
        return None, None

    # Try up to 30 random picks, prioritizing rows with unique move names.
    for _ in range(30):
        char_key = random.choice(char_keys)
        rows = _quiz_unique_rows_for_char(char_key, asked=asked, mode=mode_key, game=game_key)
        if rows:
            return char_key, random.choice(rows)

    # Fallback 1: unique move-name rows (ignore asked dedup)
    random.shuffle(char_keys)
    for char_key in char_keys:
        rows = _quiz_unique_rows_for_char(char_key, asked=set(), mode=mode_key, game=game_key)
        if rows:
            return char_key, random.choice(rows)

    # Fallback 2: any valid row
    random.shuffle(char_keys)
    for char_key in char_keys:
        rows = [
            r
            for r in frame_data[char_key]
            if _quiz_row_has_data(r) and _quiz_row_allowed_for_mode(r, mode_key, game=game_key)
        ]
        if rows:
            return char_key, random.choice(rows)
    return None, None


# Quiz session lifecycle (start, mode prompt, stop, next question)
async def start_quiz(
    message,
    mode="hard",
    game="sf6",
    session_scores=None,
    session_score_names=None,
    session_round=1,
    session_message_ids=None,
    *,
    reply_to_user=True,
):
    """Initialize and send one quiz question in the channel."""
    mode_key = _quiz_normalize_mode(mode)
    game_key = _quiz_game_key(game)
    channel_id = message.channel.id
    if QUIZ_START_LOCK.locked():
        try:
            await message.reply("A quiz is already being prepared. Please wait a moment.")
        except Exception as e:
            if is_deleted_message_reference_error(e):
                try:
                    await message.channel.send("A quiz is already being prepared. Please wait a moment.")
                except Exception as send_error:
                    print(f"[quiz] locked-start send error: {send_error}", flush=True)
            else:
                print(f"[quiz] locked-start reply error: {e}", flush=True)
        return

    async with QUIZ_START_LOCK:
        if channel_id in ACTIVE_QUIZZES:
            try:
                await message.reply(
                    "A quiz is already running. Mention me and say `stop quiz` to end it."
                )
            except Exception as e:
                print(f"[quiz] already-running reply error: {e}", flush=True)
            return

        char_key, row = pick_quiz_move(mode=mode_key, game=game_key)
        if not char_key:
            try:
                await message.reply(f"No {_quiz_game_label(game_key)} frame data is available for {mode_key} mode.")
            except Exception as e:
                print(f"[quiz] no-data reply error: {e}", flush=True)
            return

        normalized_scores = {}
        if isinstance(session_scores, dict):
            for raw_uid, raw_points in session_scores.items():
                try:
                    uid = int(raw_uid)
                    pts = int(raw_points)
                except Exception:
                    continue
                if pts < 0:
                    continue
                normalized_scores[uid] = pts

        normalized_score_names = {}
        if isinstance(session_score_names, dict):
            for raw_uid, raw_name in session_score_names.items():
                try:
                    uid = int(raw_uid)
                except Exception:
                    continue
                normalized_score_names[uid] = _quiz_clean_display_name(raw_name)

        for uid in normalized_scores.keys():
            if uid not in normalized_score_names:
                normalized_score_names[uid] = _quiz_clean_display_name(f"User {uid}")

        try:
            round_num = max(1, int(session_round))
        except Exception:
            round_num = 1

        normalized_message_ids = _quiz_normalize_message_ids(session_message_ids)

        numcmd = str(row.get("numCmd", "")).strip().lower()
        quiz_state = {
            "channel_id": channel_id,
            "total_rounds": 1,
            "round": round_num,
            "scores": normalized_scores,
            "score_names": normalized_score_names,
            "char_key": char_key,
            "numcmd": numcmd,
            "row": row,
            "mode": mode_key,
            "game": game_key,
            "created_at": datetime.datetime.now(datetime.timezone.utc),
            "answered": False,
            "awaiting_choice": False,
            "asked": {(game_key, char_key, numcmd)},
            "message_ids": normalized_message_ids,
        }

        answer_char = str(row.get("char_name", char_key.capitalize())).strip()
        answer_move = str(row.get("moveName", "?")).strip()
        answer_numcmd = str(row.get("numCmd", "?")).strip()
        print(
            f"[quiz] answer-key channel_id={channel_id} round={round_num} game={game_key} mode={mode_key} "
            f"char={answer_char} move={answer_move} numcmd={answer_numcmd}",
            flush=True,
        )

        ACTIVE_QUIZZES[channel_id] = quiz_state
        QUIZ_PENDING_MODE.pop(channel_id, None)

        thinking_message = await _quiz_send_thinking_message(message, reply_to_user=reply_to_user)

        question_text, question_embed, question_view = await build_quiz_question_message(
            message.channel,
            round_num,
            1,
            row,
            mode=mode_key,
            game=game_key,
        )
        sent = await _quiz_publish_from_placeholder(
            message.channel,
            thinking_message,
            question_text,
            embed=question_embed,
            view=question_view,
        )
        if sent is None:
            ACTIVE_QUIZZES.pop(channel_id, None)
            _quiz_cancel_active_timeout(channel_id)
            return

        _quiz_track_message_id(quiz_state, getattr(sent, "id", None))
        _quiz_schedule_active_timeout(channel_id, message.channel, quiz_state)


async def prompt_quiz_mode_selection(
    message,
    game="sf6",
    session_mode=None,
    session_scores=None,
    session_score_names=None,
    session_round=1,
    session_message_ids=None,
):
    """Prompt user to specify quiz difficulty and track pending mode selection."""
    channel_id = message.channel.id
    game_key = _quiz_game_key(game)
    prompt_text = (
        f"Specify quiz difficulty for {_quiz_game_label(game_key)}: `easy`, `medium`, or `hard`. "
        "Easy = normals only. Medium = normals + specials. Hard = everything."
    )

    stored_mode = str(session_mode or "").strip().lower()
    if stored_mode not in QUIZ_VALID_MODES:
        stored_mode = None

    normalized_message_ids = _quiz_normalize_message_ids(session_message_ids)

    pending_payload = {
        "created_at": datetime.datetime.now(datetime.timezone.utc),
        "message_id": None,
        "mode": stored_mode,
        "game": game_key,
        "scores": dict(session_scores or {}),
        "score_names": dict(session_score_names or {}),
        "round": session_round,
        "message_ids": normalized_message_ids,
    }

    try:
        sent = await message.reply(prompt_text)
        pending_payload["message_id"] = getattr(sent, "id", None)
        QUIZ_PENDING_MODE[channel_id] = pending_payload
    except Exception as e:
        if is_deleted_message_reference_error(e):
            sent = await message.channel.send(prompt_text)
            pending_payload["message_id"] = getattr(sent, "id", None)
            QUIZ_PENDING_MODE[channel_id] = pending_payload
        else:
            print(f"[quiz] mode-prompt send error: {e}", flush=True)


async def stop_quiz(message):
    """Cancel the active quiz in the channel and reveal the current answer."""
    channel_id = message.channel.id
    quiz = ACTIVE_QUIZZES.pop(channel_id, None)
    _quiz_cancel_active_timeout(channel_id)
    if not quiz:
        try:
            await message.reply("No quiz is running right now.")
        except Exception as e:
            print(f"[quiz] stop-no-quiz reply error: {e}", flush=True)
        return

    row = quiz["row"]
    char_key = quiz["char_key"]
    char_display = str(row.get("char_name", char_key.capitalize())).strip()
    move_name = str(row.get("moveName", "?")).strip()
    num_cmd = str(row.get("numCmd", "?")).strip()
    reply_text = (
        f"Quiz ended. The answer was **{char_display}'s {move_name} ({num_cmd})**."
    )
    try:
        await message.reply(reply_text)
    except Exception as e:
        if is_deleted_message_reference_error(e):
            await message.channel.send(reply_text)
        else:
            print(f"[quiz] stop send error: {e}", flush=True)


def _is_reply_to_quiz_msg(message):
    """True if the message replies to any tracked quiz-related bot message."""
    ref = getattr(message, "reference", None)
    if not ref:
        return False
    channel_id = message.channel.id
    quiz = ACTIVE_QUIZZES.get(channel_id)
    if not quiz:
        return False

    quiz_message_ids = quiz.get("message_ids")
    if isinstance(quiz_message_ids, list):
        try:
            ref_id = int(ref.message_id)
        except Exception:
            ref_id = ref.message_id
        if ref_id in quiz_message_ids:
            return True

    last_id = quiz.get("last_message_id")
    return last_id is not None and ref.message_id == last_id


def _quiz_track_message_id(quiz_state, message_id):
    """Track quiz-related bot message IDs so replies stay addressable."""
    if not isinstance(quiz_state, dict) or not message_id:
        return

    try:
        normalized_id = int(message_id)
    except Exception:
        return

    message_ids = quiz_state.get("message_ids")
    if not isinstance(message_ids, list):
        message_ids = []

    if normalized_id not in message_ids:
        message_ids.append(normalized_id)
    if len(message_ids) > 40:
        message_ids = message_ids[-40:]

    quiz_state["message_ids"] = message_ids
    quiz_state["last_message_id"] = normalized_id


def _quiz_normalize_message_ids(raw_message_ids):
    """Normalize and dedupe message id history while preserving order."""
    temp_state = {}
    if isinstance(raw_message_ids, list):
        for raw_id in raw_message_ids:
            _quiz_track_message_id(temp_state, raw_id)
    return list(temp_state.get("message_ids") or [])


def _quiz_build_message_history(state, appended_message_id=None):
    """Build message-id history from existing state plus an optional new message id."""
    temp_state = {
        "message_ids": _quiz_normalize_message_ids(
            (state or {}).get("message_ids", []) if isinstance(state, dict) else []
        )
    }
    if isinstance(state, dict):
        _quiz_track_message_id(temp_state, state.get("last_message_id"))
    _quiz_track_message_id(temp_state, appended_message_id)
    return list(temp_state.get("message_ids") or [])


def _quiz_reveal_reply_text(quiz):
    char_display, move_name, num_cmd = _quiz_answer_display(quiz)
    score_text = _format_quiz_scores(
        dict(quiz.get("scores") or {}),
        dict(quiz.get("score_names") or {}),
    )
    return (
        f"The answer was **{char_display}'s {move_name} ({num_cmd})**.\n"
        f"{score_text}\n"
        "Starting the next question."
    )


async def _quiz_start_next_question(message, quiz, result_message_id=None):
    try:
        next_round = max(1, int((quiz or {}).get("round", 1))) + 1
    except Exception:
        next_round = 2
    await start_quiz(
        message,
        mode=(quiz or {}).get("mode", "hard"),
        game=(quiz or {}).get("game", "sf6"),
        session_scores=dict((quiz or {}).get("scores") or {}),
        session_score_names=dict((quiz or {}).get("score_names") or {}),
        session_round=next_round,
        session_message_ids=_quiz_build_message_history(quiz, result_message_id),
        reply_to_user=False,
    )




def _is_reply_to_quiz_mode_prompt(message):
    """True if message replies to the most recent difficulty prompt."""
    ref = getattr(message, "reference", None)
    if not ref:
        return False
    pending = QUIZ_PENDING_MODE.get(message.channel.id)
    if not pending:
        return False
    pending_id = pending.get("message_id")
    return pending_id is not None and ref.message_id == pending_id


# Active-question timeout

def _quiz_cancel_active_timeout(channel_id):
    task = QUIZ_ACTIVE_TIMEOUT_TASKS.pop(channel_id, None)
    if task and not task.done():
        task.cancel()


def _quiz_active_timeout_message(quiz_state):
    char_display, move_name, num_cmd = _quiz_answer_display(quiz_state)
    score_text = _format_quiz_scores(
        dict((quiz_state or {}).get("scores") or {}),
        dict((quiz_state or {}).get("score_names") or {}),
    )
    return (
        "Quiz timed out after 5 minutes with no correct answer.\n"
        f"The answer was **{char_display}'s {move_name} ({num_cmd})**.\n"
        f"{score_text}\n"
        "Quiz ended."
    )


def _quiz_schedule_active_timeout(channel_id, channel, quiz_state):
    _quiz_cancel_active_timeout(channel_id)

    async def _timeout_worker():
        try:
            await asyncio.sleep(QUIZ_ACTIVE_TTL_SECONDS)
            active = ACTIVE_QUIZZES.get(channel_id)
            if active is not quiz_state:
                return

            created_at = active.get("created_at")
            if created_at:
                age = (datetime.datetime.now(datetime.timezone.utc) - created_at).total_seconds()
                remaining = QUIZ_ACTIVE_TTL_SECONDS - age
                if remaining > 0:
                    await asyncio.sleep(remaining)

            active = ACTIVE_QUIZZES.get(channel_id)
            if active is not quiz_state:
                return

            created_at = active.get("created_at")
            if created_at:
                age = (datetime.datetime.now(datetime.timezone.utc) - created_at).total_seconds()
                if age < QUIZ_ACTIVE_TTL_SECONDS:
                    return

            expired_quiz = ACTIVE_QUIZZES.pop(channel_id, None)
            if expired_quiz is not quiz_state:
                if expired_quiz:
                    ACTIVE_QUIZZES[channel_id] = expired_quiz
                return

            expiry_text = _quiz_active_timeout_message(expired_quiz)
            try:
                await channel.send(expiry_text)
            except Exception as send_error:
                print(f"[quiz] active-expiry send error: {send_error}", flush=True)
        except asyncio.CancelledError:
            return
        finally:
            tracked_task = QUIZ_ACTIVE_TIMEOUT_TASKS.get(channel_id)
            if tracked_task is asyncio.current_task():
                QUIZ_ACTIVE_TIMEOUT_TASKS.pop(channel_id, None)

    QUIZ_ACTIVE_TIMEOUT_TASKS[channel_id] = asyncio.create_task(_timeout_worker())




def _quiz_pending_mode_active(channel_id):
    pending = QUIZ_PENDING_MODE.get(channel_id)
    if not pending:
        return False
    created_at = pending.get("created_at")
    if not created_at:
        QUIZ_PENDING_MODE.pop(channel_id, None)
        return False
    age = (datetime.datetime.now(datetime.timezone.utc) - created_at).total_seconds()
    if age > QUIZ_PENDING_MODE_TTL_SECONDS:
        QUIZ_PENDING_MODE.pop(channel_id, None)
        return False
    return True


def _quiz_answer_display(quiz):
    row = quiz["row"]
    char_key = quiz["char_key"]
    char_display = str(row.get("char_name", char_key.capitalize())).strip()
    move_name = str(row.get("moveName", "?")).strip()
    num_cmd = str(row.get("numCmd", "?")).strip()
    return char_display, move_name, num_cmd




# Answer and post-answer follow-up handlers
async def handle_quiz_post_answer_choice(message):
    """Handle follow-up choice after a wrong guess prompt."""
    channel_id = message.channel.id
    quiz = ACTIVE_QUIZZES.get(channel_id)
    if not quiz or not quiz.get("awaiting_choice"):
        return False

    text = strip_discord_mentions(message.content or "").strip().lower()
    if not text:
        return False

    wants_guess_again = bool(QUIZ_GUESS_AGAIN_RE.search(text))
    wants_reveal = bool(QUIZ_REVEAL_END_RE.search(text))

    if not wants_guess_again and not wants_reveal:
        inferred_intent = await classify_quiz_post_answer_choice_intent(message.channel, text)
        if inferred_intent == "guess_again":
            wants_guess_again = True
        elif inferred_intent == "reveal":
            wants_reveal = True

    if wants_guess_again:
        quiz["awaiting_choice"] = False
        try:
            sent = await message.reply("Guess again.")
            _quiz_track_message_id(quiz, getattr(sent, "id", None))
        except Exception as e:
            if is_deleted_message_reference_error(e):
                sent = await message.channel.send("Guess again.")
                _quiz_track_message_id(quiz, getattr(sent, "id", None))
            else:
                print(f"[quiz] guess-again reply error: {e}", flush=True)
        return True

    if wants_reveal:

        ACTIVE_QUIZZES.pop(channel_id, None)
        _quiz_cancel_active_timeout(channel_id)
        reply_text = _quiz_reveal_reply_text(quiz)
        try:
            sent = await message.reply(reply_text)
            await _quiz_start_next_question(message, quiz, result_message_id=getattr(sent, "id", None))
        except Exception as e:
            if is_deleted_message_reference_error(e):
                sent = await message.channel.send(reply_text)
                await _quiz_start_next_question(message, quiz, result_message_id=getattr(sent, "id", None))
            else:
                print(f"[quiz] reveal-end reply error: {e}", flush=True)
        return True

    return False


async def handle_quiz_answer(message):
    """
    Process a message as a potential quiz answer.
    Returns True if message was handled as a quiz answer attempt.
    Returns False when message is not a usable answer format.
    """
    channel_id = message.channel.id
    quiz = ACTIVE_QUIZZES.get(channel_id)
    if not quiz or quiz.get("answered"):
        return False

    text = strip_discord_mentions(message.content or "").strip().lower()
    if not text:
        return False

    parsed_char, parsed_move = _extract_char_and_move_from_text(text, game=quiz.get("game", "sf6"))
    if not parsed_char or not parsed_move:
        return False

    if not check_quiz_answer(quiz, text):
        quiz["awaiting_choice"] = True
        thinking_message = await _quiz_send_thinking_message(message)
        wrong_reply = await build_quiz_wrong_guess_message(
            message.channel,
            sanitize_ascii_line,
            lambda hint: _quiz_intro_has_specific_answer_hint(hint, game=quiz.get("game", "sf6")),
        )
        wrong_followup = "Try again or give up and find out the answer"
        wrong_text = f"{wrong_reply}\n{wrong_followup}" if wrong_reply else wrong_followup
        sent = await _quiz_publish_from_placeholder(
            message.channel,
            thinking_message,
            wrong_text,
        )
        _quiz_track_message_id(quiz, getattr(sent, "id", None))
        return True

    scores = quiz.setdefault("scores", {})
    score_names = quiz.setdefault("score_names", {})
    winner_id = int(message.author.id)
    winner_name = _quiz_user_display_name(message.author)
    winner_points = int(scores.get(winner_id, 0)) + 1
    scores[winner_id] = winner_points
    score_names[winner_id] = winner_name
    await _quiz_record_global_win(message, winner_id, winner_name, points=1)

    ACTIVE_QUIZZES.pop(channel_id, None)
    _quiz_cancel_active_timeout(channel_id)
    thinking_message = await _quiz_send_thinking_message(message)
    char_display, move_name, num_cmd = _quiz_answer_display(quiz)
    correct_reply = await build_quiz_correct_guess_message(message.channel, sanitize_ascii_line)
    score_text = _format_quiz_scores(dict(scores), dict(score_names))
    result_lines = [correct_reply, score_text]
    result_lines.append(f"The answer was **{char_display}'s {move_name} ({num_cmd})**.")
    result_text = "\n".join(result_lines)
    sent = await _quiz_publish_from_placeholder(
        message.channel,
        thinking_message,
        result_text,
    )
    if sent is None:
        print("[quiz] correct-reply send failed", flush=True)
        return True

    await _quiz_start_next_question(message, quiz, result_message_id=getattr(sent, "id", None))

    return True




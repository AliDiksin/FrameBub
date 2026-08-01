"""Persistent global quiz leaderboard storage and formatting."""

import datetime
import json
import os


def bind(**values):
    globals().update(values)
# Leaderboard persistence and display
def _quiz_leaderboard_file_path():
    path_text = str(QUIZ_LEADERBOARD_FILE or "quiz_leaderboard.json").strip()
    if os.path.isabs(path_text):
        return path_text
    return os.path.join(os.path.dirname(__file__), path_text)


def _quiz_message_in_leaderboard_guild(message):
    guild = getattr(message, "guild", None)
    return bool(guild and getattr(guild, "id", None) == QUIZ_LEADERBOARD_GUILD_ID)


def load_quiz_leaderboard():
    """Load persistent global quiz leaderboard from disk."""
    global QUIZ_GLOBAL_LEADERBOARD, QUIZ_GLOBAL_LEADERBOARD_NAMES

    file_path = _quiz_leaderboard_file_path()
    if not os.path.exists(file_path):
        QUIZ_GLOBAL_LEADERBOARD = {}
        QUIZ_GLOBAL_LEADERBOARD_NAMES = {}
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        print(f"[quiz] leaderboard load error: {e}", flush=True)
        QUIZ_GLOBAL_LEADERBOARD = {}
        QUIZ_GLOBAL_LEADERBOARD_NAMES = {}
        return

    if not isinstance(payload, dict):
        print("[quiz] leaderboard load warning: payload is not an object", flush=True)
        QUIZ_GLOBAL_LEADERBOARD = {}
        QUIZ_GLOBAL_LEADERBOARD_NAMES = {}
        return

    loaded_scores = {}
    loaded_names = {}
    for raw_uid, raw_pts in dict(payload.get("scores") or {}).items():
        try:
            uid = int(raw_uid)
            pts = int(raw_pts)
        except Exception:
            continue
        if pts < 0:
            continue
        loaded_scores[uid] = pts

    for raw_uid, raw_name in dict(payload.get("score_names") or {}).items():
        try:
            uid = int(raw_uid)
        except Exception:
            continue
        loaded_names[uid] = _quiz_clean_display_name(raw_name)

    for uid in loaded_scores.keys():
        if uid not in loaded_names:
            loaded_names[uid] = _quiz_clean_display_name(f"User {uid}")

    QUIZ_GLOBAL_LEADERBOARD = loaded_scores
    QUIZ_GLOBAL_LEADERBOARD_NAMES = loaded_names


def save_quiz_leaderboard():
    """Persist global quiz leaderboard to disk."""
    file_path = _quiz_leaderboard_file_path()
    payload = {
        "version": 1,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "scores": {str(uid): int(points) for uid, points in QUIZ_GLOBAL_LEADERBOARD.items()},
        "score_names": {
            str(uid): _quiz_clean_display_name(name)
            for uid, name in QUIZ_GLOBAL_LEADERBOARD_NAMES.items()
        },
    }

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=True, indent=2, sort_keys=True)
    except Exception as e:
        print(f"[quiz] leaderboard save error: {e}", flush=True)


def _quiz_extract_leaderboard_top_limit(text, default=10, maximum=25):
    match = QUIZ_LEADERBOARD_TOP_RE.search(str(text or ""))
    if not match:
        return default
    try:
        parsed = int(match.group(1))
    except Exception:
        return default
    return max(1, min(maximum, parsed))


def _quiz_is_leaderboard_request(text):
    return bool(QUIZ_LEADERBOARD_REQUEST_RE.search(str(text or "")))


def _quiz_format_global_leaderboard_reply(limit=None):
    scores = dict(QUIZ_GLOBAL_LEADERBOARD)
    names = dict(QUIZ_GLOBAL_LEADERBOARD_NAMES)
    if not scores:
        return "No global quiz wins recorded yet. Win one round and claim your first point."

    sorted_items = sorted(
        scores.items(),
        key=lambda item: (
            -int(item[1]),
            _quiz_clean_display_name(names.get(item[0], f"User {item[0]}")).lower(),
        ),
    )
    top_items = sorted_items if limit is None else sorted_items[: max(1, int(limit))]
    top_scores = {uid: pts for uid, pts in top_items}
    score_block = _format_quiz_scores(top_scores, names)
    top_uid, top_points = top_items[0]
    top_name = _quiz_clean_display_name(names.get(top_uid, f"User {top_uid}"))
    heading = "Global Quiz Leaderboard" if limit is None else f"Global Quiz Leaderboard (Top {len(top_items)})"
    return (
        f"{heading}:\n"
        f"{score_block}\n"
        f"Top scorer right now: {top_name} with {top_points} point{'s' if int(top_points) != 1 else ''}."
    )


async def _quiz_record_global_win(message, user_id, display_name, points=1):
    """Record lifetime quiz points for a user and persist leaderboard."""
    if not _quiz_message_in_leaderboard_guild(message):
        return

    try:
        uid = int(user_id)
        delta = int(points)
    except Exception:
        return
    if delta <= 0:
        return

    async with QUIZ_LEADERBOARD_LOCK:
        current_points = int(QUIZ_GLOBAL_LEADERBOARD.get(uid, 0))
        QUIZ_GLOBAL_LEADERBOARD[uid] = current_points + delta
        QUIZ_GLOBAL_LEADERBOARD_NAMES[uid] = _quiz_clean_display_name(display_name)
        save_quiz_leaderboard()



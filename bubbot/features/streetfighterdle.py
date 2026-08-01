"""Deterministic Streetfighterdle parsing, score UI, and snapshots."""
# Score parsing stays deterministic; scheduler and Discord UI call these shared helpers.

import datetime
import json
import os
import re

import discord


def _env_bool(name, default=True):
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() not in {"0", "false", "no", "off", "disabled"}


def _env_int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _score_source_channel_id():
    runtime = __import__("sys").modules.get("bubbot.runtime.buenavista_extension")
    if runtime is not None:
        return int(getattr(runtime, "_STREETFIGHTERDLE_SCORE_SOURCE_CHANNEL_ID", 1439264736494489761))
    return _env_int("STREETFIGHTERDLE_SCORE_SOURCE_CHANNEL_ID", 1439264736494489761)

def _scores_file_path():
    runtime = __import__("sys").modules.get("bubbot.runtime.buenavista_extension")
    path_value = getattr(runtime, "_STREETFIGHTERDLE_SCORES_FILE", None) if runtime is not None else None
    path_text = str(path_value or os.getenv("STREETFIGHTERDLE_SCORES_FILE", "streetfighterdle_scores.json") or "").strip()
    if os.path.isabs(path_text):
        return path_text
    return os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "runtime", path_text))


def _truncate_message(text, limit=1800):
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def load_streetfighterdle_score_history():
    file_path = _scores_file_path()
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        print(f"[streetfighterdle] score history load error: {e}", flush=True)
        return {}
    if not isinstance(payload, dict):
        return {}
    days = payload.get("days") or {}
    return dict(days) if isinstance(days, dict) else {}


def save_streetfighterdle_score_snapshot(snapshot_date_utc, entries, source_channel_id=None):
    history = load_streetfighterdle_score_history()
    normalized_entries = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        normalized_entries.append(
            {
                "user_id": int(entry.get("user_id", 0) or 0),
                "display_name": str(entry.get("display_name", "Unknown")).strip() or "Unknown",
                "score_text": str(entry.get("score_text", "")).strip(),
                "total_points": int(entry.get("total_points", 0) or 0),
                "per_game": [int(value) for value in list(entry.get("per_game") or [])[:4]],
                "message_id": int(entry.get("message_id", 0) or 0),
                "created_at_utc": str(entry.get("created_at_utc", "")).strip(),
            }
        )

    snapshot_key = str(snapshot_date_utc)
    history[snapshot_key] = {
        "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_channel_id": int(source_channel_id or _score_source_channel_id()),
        "entries": normalized_entries,
    }
    payload = {
        "version": 1,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "days": history,
    }
    try:
        with open(_scores_file_path(), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=True, indent=2)
    except Exception as e:
        print(f"[streetfighterdle] score history save error: {e}", flush=True)


def parse_streetfighterdle_score_text(text):
    match = re.search(
        r"(?<![\d/])(\d{1,3})\s*/\s*(\d{1,3})\s*/\s*(\d{1,3})\s*/\s*(\d{1,3})(?![\d/])",
        str(text or ""),
    )
    if not match:
        return None
    per_game = [int(match.group(index)) for index in range(1, 5)]
    return {
        "score_text": "/".join(str(value) for value in per_game),
        "per_game": per_game,
        "total_points": sum(per_game),
    }


def build_streetfighterdle_leaderboard_text(entries, snapshot_date_utc):
    if not entries:
        return (
            "By decree of Bub, no Streetfighterdle scores were posted in the last 24 hours.\n"
            f"Window ending {snapshot_date_utc} UTC."
        )
    lines = [
        "By decree of Bub, the Streetfighterdle ledger for the last 24 hours stands thus.",
        f"Window ending {snapshot_date_utc} UTC. Lowest total wins.",
        "",
    ]
    for index, entry in enumerate(entries, start=1):
        lines.append(f"{index}. {entry['display_name']} - {entry['total_points']} points ({entry['score_text']})")
    return _truncate_message("\n".join(lines), limit=1800)


def build_streetfighterdle_latest_snapshot_text():
    history = load_streetfighterdle_score_history()
    if not history:
        return "No Streetfighterdle leaderboard snapshot has been recorded yet."
    latest_key = sorted(history.keys())[-1]
    snapshot = history.get(latest_key) or {}
    return build_streetfighterdle_leaderboard_text(snapshot.get("entries") or [], latest_key)


def _streetfighterdle_score_channel_text(guild=None):
    if guild is None:
        return None
    source_channel = getattr(guild, "get_channel", lambda _channel_id: None)(_score_source_channel_id())
    return getattr(source_channel, "mention", None) if source_channel is not None else None


def build_streetfighterdle_reminder_text(streetfighterdle_url, guild=None):
    source_channel_text = _streetfighterdle_score_channel_text(guild)
    score_text = (
        f"Post your score in {source_channel_text} as `x/x/x/x`."
        if source_channel_text
        else "Use **Submit Score** to post your `x/x/x/x` result."
    )
    return (
        "do streetfighterdle\n"
        f"<{streetfighterdle_url}>\n\n"
        f"{score_text} Lowest total wins the daily leaderboard."
    )


def build_streetfighterdle_reminder_embed(streetfighterdle_url, guild=None):
    embed = discord.Embed(
        title="Streetfighterdle",
        description=build_streetfighterdle_reminder_text(streetfighterdle_url, guild),
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="Scores",
        value="Use **Submit Score** to enter streetfighterdle, splash arts, quote, and character hints.",
        inline=False,
    )
    return embed


def _parse_streetfighterdle_score_fields(values):
    parsed_values = []
    for raw_value in values:
        text = str(raw_value or "").strip()
        if not re.fullmatch(r"\d{1,3}", text):
            return None
        parsed_values.append(int(text))
    score_text = "/".join(str(value) for value in parsed_values)
    return {"score_text": score_text, "per_game": parsed_values, "total_points": sum(parsed_values)}


def _parse_bot_streetfighterdle_submission(msg):
    content = str(getattr(msg, "content", "") or "")
    if not content.startswith("Streetfighterdle score for"):
        return None
    parsed_score = parse_streetfighterdle_score_text(content)
    if not parsed_score:
        return None
    mentions = getattr(msg, "mentions", None) or []
    user = mentions[0] if mentions else None
    user_id = int(getattr(user, "id", 0) or 0) if user is not None else 0
    if user_id <= 0:
        raw_mention = re.search(r"<@!?(\d{1,25})>", content)
        user_id = int(raw_mention.group(1)) if raw_mention else 0
    if user_id <= 0:
        return None
    display_name = getattr(user, "display_name", None) or getattr(user, "name", None) or f"User {user_id}"
    return user_id, str(display_name).strip() or f"User {user_id}", parsed_score


async def _resolve_streetfighterdle_display_name(guild, user_id, current_name=None, client=None):
    fallback = f"User {user_id}"
    current_name = str(current_name or "").strip()
    if current_name and current_name != fallback:
        return current_name
    if guild is None or user_id <= 0:
        return current_name or fallback
    member = None
    get_member = getattr(guild, "get_member", None)
    if callable(get_member):
        member = get_member(user_id)
    if member is None:
        fetch_member = getattr(guild, "fetch_member", None)
        if callable(fetch_member):
            try:
                member = await fetch_member(user_id)
            except Exception:
                member = None
    if member is None and client is not None:
        get_user = getattr(client, "get_user", None)
        if callable(get_user):
            member = get_user(user_id)
        if member is None:
            fetch_user = getattr(client, "fetch_user", None)
            if callable(fetch_user):
                try:
                    member = await fetch_user(user_id)
                except Exception:
                    member = None
    display_name = getattr(member, "display_name", None) or getattr(member, "name", None)
    return str(display_name or current_name or fallback).strip() or fallback


class StreetfighterdleScoreModal(discord.ui.Modal, title="Submit Streetfighterdle Score"):
    streetfighterdle = discord.ui.TextInput(label="streetfighterdle", placeholder="Example: 3", required=True, max_length=3)
    splash_arts = discord.ui.TextInput(label="splash arts", placeholder="Example: 5", required=True, max_length=3)
    quote = discord.ui.TextInput(label="quote", placeholder="Example: 2", required=True, max_length=3)
    character_hints = discord.ui.TextInput(label="character hints", placeholder="Example: 8", required=True, max_length=3)

    def __init__(self, extension):
        super().__init__()
        self.extension = extension

    async def on_submit(self, interaction: discord.Interaction):
        await self.extension.submit_streetfighterdle_score(
            interaction,
            [self.streetfighterdle.value, self.splash_arts.value, self.quote.value, self.character_hints.value],
        )


class StreetfighterdleReminderView(discord.ui.View):
    def __init__(self, extension):
        super().__init__(timeout=None)
        self.extension = extension

    @discord.ui.button(label="Play", style=discord.ButtonStyle.primary, custom_id="bv:sfdle:play")
    async def play_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self.extension.handle_streetfighterdle_play(interaction)

    @discord.ui.button(label="Submit Score", style=discord.ButtonStyle.success, custom_id="bv:sfdle:submit_score")
    async def submit_score_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.send_modal(StreetfighterdleScoreModal(self.extension))


class StreetfighterdleMixin:
    async def _streetfighterdle_score_channel(self):
        if not self._client:
            return None
        channel = self._client.get_channel(_score_source_channel_id())
        if channel is not None:
            return channel
        try:
            return await self._client.fetch_channel(_score_source_channel_id())
        except Exception as error:
            print(f"[streetfighterdle] score channel fetch error: {error}", flush=True)
            return None

    async def handle_streetfighterdle_play(self, interaction):
        try:
            await interaction.response.launch_activity()
        except Exception as error:
            print(f"[streetfighterdle] activity launch error: {error}", flush=True)
            response = interaction.response
            if response.is_done():
                await interaction.followup.send("Streetfighterdle Activity launch failed. Please try again.", ephemeral=True)
            else:
                await response.send_message("Streetfighterdle Activity launch failed. Please try again.", ephemeral=True)

    async def submit_streetfighterdle_score(self, interaction, raw_values):
        parsed = _parse_streetfighterdle_score_fields(raw_values)
        if not parsed:
            await interaction.response.send_message("Each Streetfighterdle score field must be a number from 0 to 999.", ephemeral=True)
            return
        channel = await self._streetfighterdle_score_channel()
        if channel is None:
            await interaction.response.send_message("Score submission failed: configured Streetfighterdle score channel was not found.", ephemeral=True)
            return
        user = getattr(interaction, "user", None)
        mention = getattr(user, "mention", None) or f"<@{getattr(user, 'id', 0)}>"
        await channel.send(f"Streetfighterdle score for {mention}: {parsed['score_text']}")
        await interaction.response.send_message(
            f"Recorded Streetfighterdle score: `{parsed['score_text']}` (total {parsed['total_points']}).", ephemeral=True
        )

    def _streetfighterdle_link_text(self, guild=None):
        return build_streetfighterdle_reminder_text(os.getenv("STREETFIGHTERDLE_URL", "https://www.streetfighterdle.net/"), guild)

    async def maybe_handle_streetfighterdle_message(self, *, client, message, content_lower):
        runtime = __import__("bubbot.runtime.buenavista_extension", fromlist=["_message_directly_mentions_user"])
        if not runtime._message_directly_mentions_user(client.user, message):
            return False
        if str(content_lower or "").strip() not in {"streetfighterdle", "sfdle", "street fighter dle", "street fighterdle"}:
            return False
        url = os.getenv("STREETFIGHTERDLE_URL", "https://www.streetfighterdle.net/")
        await message.reply(embed=build_streetfighterdle_reminder_embed(url, getattr(message, "guild", None)), view=StreetfighterdleReminderView(self))
        return True

    async def maybe_ack_streetfighterdle_score(self, message):
        runtime = __import__("bubbot.runtime.buenavista_extension", fromlist=["_STREETFIGHTERDLE_SCORE_ACK"])
        if not runtime._STREETFIGHTERDLE_SCORE_ACK or not runtime._message_in_buenavista_guild(message):
            return False
        if getattr(getattr(message, "author", None), "bot", False):
            return False
        if getattr(getattr(message, "channel", None), "id", None) != _score_source_channel_id():
            return False
        if not parse_streetfighterdle_score_text(getattr(message, "content", "") or ""):
            return False
        try:
            await message.add_reaction("✅")
        except Exception as error:
            print(f"[streetfighterdle] score ack reaction error: {error}", flush=True)
            return False
        return True

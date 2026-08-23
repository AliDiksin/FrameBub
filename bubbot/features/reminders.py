"""Natural-language reminders: timezone parsing, pending follow-ups, and background fire loop."""

import asyncio
import datetime
import os
import re
from datetime import date
from uuid import uuid4
from zoneinfo import ZoneInfo

from bubbot.features import reminder_store

# Timezone aliases and parsing regex
REMINDER_POLL_SECONDS = int(os.getenv("REMINDER_POLL_SECONDS", "10"))
REMINDER_PENDING_TTL_SECONDS = int(os.getenv("REMINDER_PENDING_TTL_SECONDS", "600"))
REMINDER_RETRY_SECONDS = max(1, int(os.getenv("REMINDER_RETRY_SECONDS", "300")))
TZ_ALIASES = {
    "utc": "UTC",
    "gmt": "UTC",
    "est": "America/New_York",
    "edt": "America/New_York",
    "cst": "America/Chicago",
    "cdt": "America/Chicago",
    "mst": "America/Denver",
    "mdt": "America/Denver",
    "pst": "America/Los_Angeles",
    "pdt": "America/Los_Angeles",
    "cet": "Europe/Paris",
    "cest": "Europe/Paris",
    "bst": "Europe/London",
    "ist": "Asia/Kolkata",
}
TZ_ABBREV_PATTERN = "|".join(
    sorted((re.escape(key) for key in TZ_ALIASES.keys()), key=len, reverse=True)
)
if TZ_ABBREV_PATTERN:
    tz_pattern = (
        rf"(?:utc(?:[+-]\d{{1,2}}(?::?\d{{2}})?)?"
        rf"|gmt(?:[+-]\d{{1,2}}(?::?\d{{2}})?)?"
        rf"|[A-Za-z]+/[A-Za-z_]+"
        rf"|{TZ_ABBREV_PATTERN}"
        rf"|[+-]\d{{1,2}}(?::?\d{{2}})?)"
    )
else:
    tz_pattern = (
        r"(?:utc(?:[+-]\d{1,2}(?::?\d{2})?)?"
        r"|gmt(?:[+-]\d{1,2}(?::?\d{2})?)?"
        r"|[A-Za-z]+/[A-Za-z_]+"
        r"|[+-]\d{1,2}(?::?\d{2})?)"
    )
TZ_REGEX = re.compile(rf"(?<!\w){tz_pattern}(?!\w)", re.IGNORECASE)


def message_directly_mentions_user(user, message):
    user_id = getattr(user, "id", None)
    if user_id is None:
        return False
    if any(getattr(mention, "id", None) == user_id for mention in getattr(message, "mentions", []) or []):
        return True
    return user_id in (getattr(message, "raw_mentions", []) or [])


# ReminderManager: parse requests, hold pending tz, poll and fire
class ReminderManager:
    def __init__(self, client, truncate_message_func, build_reminder_ack_text, build_reminder_fire_text):
        self.client = client
        self.truncate_message = truncate_message_func
        self.build_reminder_ack_text = build_reminder_ack_text
        self.build_reminder_fire_text = build_reminder_fire_text
        self.reminders = []
        self.pending_reminders = {}
        self._lock = asyncio.Lock()
        self._loaded = False

    def parse_timezone(self, tz_str):
        raw_tz = str(tz_str or "").strip()
        if not raw_tz:
            return None, None
        tz = TZ_ALIASES.get(raw_tz.lower(), raw_tz)
        raw_offset_match = re.fullmatch(r"([+-])(\d{1,2})(?::?(\d{2}))?", tz)
        if raw_offset_match:
            hours = int(raw_offset_match.group(2))
            minutes = int(raw_offset_match.group(3) or 0)
            if hours > 23 or minutes > 59:
                return None, None
            sign = 1 if raw_offset_match.group(1) == "+" else -1
            offset = datetime.timedelta(hours=hours, minutes=minutes) * sign
            return datetime.timezone(offset), f"UTC{raw_offset_match.group(1)}{hours:02d}:{minutes:02d}"
        offset_match = re.fullmatch(r"(?:utc|gmt)([+-])(\d{1,2})(?::?(\d{2}))?", tz, re.IGNORECASE)
        if offset_match:
            hours = int(offset_match.group(2))
            minutes = int(offset_match.group(3) or 0)
            if hours > 23 or minutes > 59:
                return None, None
            sign = 1 if offset_match.group(1) == "+" else -1
            offset = datetime.timedelta(hours=hours, minutes=minutes) * sign
            return datetime.timezone(offset), f"UTC{offset_match.group(1)}{hours:02d}:{minutes:02d}"
        if tz.upper() == "UTC":
            return datetime.timezone.utc, "UTC"
        try:
            return ZoneInfo(tz), tz
        except Exception:
            return None, None

    def is_reminder_request_text(self, text):
        return bool(re.search(r"\bremind(?:\s+me)?\b", text or "", re.IGNORECASE))

    def get_reminder_target_user_ids(self, message, existing_ids=None):
        targets = []
        if existing_ids:
            for user_id in existing_ids:
                try:
                    normalized = int(user_id)
                except (TypeError, ValueError):
                    continue
                if normalized not in targets:
                    targets.append(normalized)

        for member in message.mentions:
            if self.client.user and member.id == self.client.user.id:
                continue
            if member.id not in targets:
                targets.append(member.id)

        if not targets:
            targets.append(message.author.id)
        return targets

    def parse_reminder_request(self, text, allow_missing_tz=False):
        text = text.strip()
        if not text:
            return None, None, None, None, "I couldn't parse that. Try: 'remind me to <task> tomorrow at 2:30pm GMT'.", None

        time_match = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", text, re.IGNORECASE)
        if not time_match:
            return None, None, None, None, "I couldn't parse the time. Use: 'at 2:30pm' or 'at 14:30'.", None

        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        ampm = (time_match.group(3) or "").lower()
        if ampm:
            if hour == 12:
                hour = 0
            if ampm == "pm":
                hour += 12
        if hour > 23 or minute > 59:
            return None, None, None, None, "Time is invalid. Use formats like 2:30pm or 14:30.", None

        rel_match = re.search(r"\b(today|tomorrow)\b", text, re.IGNORECASE)
        rel = rel_match.group(1).lower() if rel_match else None
        date_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
        date_str = date_match.group(1) if date_match else None

        task = ""
        after_time = text[time_match.end():]
        to_after_time = re.search(r"\bto\s+(.+)$", after_time, re.IGNORECASE)
        if to_after_time:
            task = to_after_time.group(1).strip()
        if not task:
            task = re.sub(r"^\s*remind(?:\s+me)?\s+(?:to\s+)?", "", text, flags=re.IGNORECASE).strip()
            task = re.sub(r"\bat\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b.*$", "", task, flags=re.IGNORECASE).strip()
        task = re.sub(r"\b(?:today|tomorrow)\b\s*$", "", task, flags=re.IGNORECASE).strip(" ,.-")
        task = re.sub(r"\b\d{4}-\d{2}-\d{2}\b\s*$", "", task).strip(" ,.-")
        if not task:
            return None, None, None, None, "I couldn't find the task. Try: 'remind me to <task> at 2:30pm GMT'.", None

        tz_match = TZ_REGEX.search(text)
        if not tz_match:
            if allow_missing_tz:
                pending = {
                    "task": task,
                    "hour": hour,
                    "minute": minute,
                    "rel": rel,
                    "date_str": date_str,
                }
                return None, None, None, None, None, pending
            return None, None, None, None, "Please include a timezone (e.g., GMT, UTC+2, America/New_York).", None
        tz_str = tz_match.group(0)
        tzinfo, tz_label = self.parse_timezone(tz_str)
        if not tzinfo:
            return None, None, None, None, "Unknown timezone. Use GMT/UTC, UTC+2, or IANA like America/New_York.", None

        now_tz = datetime.datetime.now(tzinfo)
        if date_str:
            reminder_date = date.fromisoformat(date_str)
        elif rel == "tomorrow":
            reminder_date = (now_tz + datetime.timedelta(days=1)).date()
        else:
            reminder_date = now_tz.date()

        reminder_dt = datetime.datetime(
            reminder_date.year,
            reminder_date.month,
            reminder_date.day,
            hour,
            minute,
            tzinfo=tzinfo,
        )
        if reminder_dt < now_tz:
            if not date_str and rel is None:
                reminder_dt = reminder_dt + datetime.timedelta(days=1)
            else:
                return None, None, None, None, "That time has already passed. Please choose a future time.", None

        return task, reminder_dt, reminder_dt.astimezone(datetime.timezone.utc), tz_label, None, None

    async def load(self):
        if self._loaded:
            return len(self.reminders)
        async with self._lock:
            if self._loaded:
                return len(self.reminders)
            self.reminders = await asyncio.to_thread(reminder_store.load_records)
            self._loaded = True
            next_due = min((item["when_utc"] for item in self.reminders), default=None)
            print(f"[reminders] loaded {len(self.reminders)} reminders; next_due={next_due.isoformat() if next_due else 'None'}", flush=True)
            return len(self.reminders)

    async def _persist_locked(self):
        await asyncio.to_thread(reminder_store.save_records, list(self.reminders))

    async def add_reminder(self, *, user_id, channel_id, task, when_utc, notify_user_ids):
        when_utc = when_utc.replace(tzinfo=datetime.timezone.utc) if when_utc.tzinfo is None else when_utc
        target_ids = notify_user_ids or [user_id]
        record = {
            "id": str(uuid4()),
            "user_id": int(user_id),
            "channel_id": int(channel_id),
            "task": str(task).strip(),
            "when_utc": when_utc.astimezone(datetime.timezone.utc),
            "notify_user_ids": [int(value) for value in target_ids],
            "created_at_utc": datetime.datetime.now(datetime.timezone.utc),
            "attempts": 0,
            "next_attempt_utc": None,
        }
        async with self._lock:
            self.reminders.append(record)
            try:
                await self._persist_locked()
            except Exception as error:
                self.reminders.pop()
                print(f"[reminders] save failed: {error}", flush=True)
                return None
        return record

    async def remove_reminder(self, reminder_id):
        async with self._lock:
            old = self.reminders[:]
            self.reminders[:] = [item for item in self.reminders if item.get("id") != reminder_id]
            if len(old) == len(self.reminders):
                return False
            try:
                await self._persist_locked()
            except Exception as error:
                self.reminders[:] = old
                print(f"[reminders] remove save failed: {error}", flush=True)
                return False
        return True

    async def mark_delivery_failed(self, reminder_id):
        async with self._lock:
            record = next((item for item in self.reminders if item.get("id") == reminder_id), None)
            if record is None:
                return False
            previous = dict(record)
            record["attempts"] = int(record.get("attempts", 0)) + 1
            record["next_attempt_utc"] = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=REMINDER_RETRY_SECONDS)
            try:
                await self._persist_locked()
            except Exception as error:
                record.clear()
                record.update(previous)
                print(f"[reminders] retry save failed: {error}", flush=True)
                return False
        return True

    async def _deliver(self, reminder):
        try:
            try:
                channel = self.client.get_channel(reminder["channel_id"])
            except Exception as error:
                channel = None
                print(f"[reminders] channel lookup failed: {error}", flush=True)
            if channel is None:
                try:
                    channel = await self.client.fetch_channel(reminder["channel_id"])
                except Exception as error:
                    print(f"[reminders] channel fetch failed: {error}", flush=True)
            guild = getattr(channel, "guild", None)
            reminder_text = await self.build_reminder_fire_text(reminder["task"], guild, self.truncate_message)
            target_ids = reminder.get("notify_user_ids") or [reminder["user_id"]]
            delivered = False
            if channel is not None:
                try:
                    mentions = " ".join(f"<@{int(user_id)}>" for user_id in target_ids)
                    await channel.send(f"{mentions} {reminder_text}".strip())
                    delivered = True
                except Exception as error:
                    print(f"[reminders] channel delivery failed: {error}", flush=True)
            if not delivered:
                for user_id in target_ids:
                    try:
                        user = await self.client.fetch_user(int(user_id))
                        await user.send(reminder_text)
                        delivered = True
                    except Exception as error:
                        print(f"[reminders] DM delivery failed user_id={user_id}: {error}", flush=True)
            return delivered
        except Exception as error:
            print(f"[reminders] delivery preparation failed: {error}", flush=True)
            return False

    async def reminder_loop(self):
        await self.load()
        print(f"Reminder loop started. Polling every {REMINDER_POLL_SECONDS}s", flush=True)
        while not self.client.is_closed():
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            due = [
                item for item in self.reminders
                if item["when_utc"] <= now_utc and (item.get("next_attempt_utc") is None or item["next_attempt_utc"] <= now_utc)
            ]
            for reminder in due:
                if await self._deliver(reminder):
                    if not await self.remove_reminder(reminder["id"]):
                        print(f"[reminders] delivered reminder retained after persistence failure id={reminder['id']}", flush=True)
                elif not await self.mark_delivery_failed(reminder["id"]):
                    print(f"[reminders] failed reminder retry state was not persisted id={reminder['id']}", flush=True)
            await asyncio.sleep(REMINDER_POLL_SECONDS)

    # Discord message path: new reminder, pending timezone reply, or ignore
    async def handle_message(self, message, content_no_mentions, content_lower):
        pending_key = (message.author.id, message.channel.id)
        if pending_key in self.pending_reminders:
            pending = self.pending_reminders[pending_key]
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            if (now_utc - pending["created_at"]).total_seconds() > REMINDER_PENDING_TTL_SECONDS:
                del self.pending_reminders[pending_key]
                print(
                    "Pending reminder expired: user_id="
                    f"{message.author.id} channel_id={message.channel.id}",
                    flush=True,
                )
            else:
                if self.is_reminder_request_text(content_lower):
                    del self.pending_reminders[pending_key]
                else:
                    tz_match = TZ_REGEX.search(content_no_mentions)
                    if tz_match:
                        tz_str = tz_match.group(0)
                        tzinfo, tz_label = self.parse_timezone(tz_str)
                        if not tzinfo:
                            await message.reply("Unknown timezone. Use GMT/UTC, UTC+2, or IANA like America/New_York.")
                            return True
                        now_tz = datetime.datetime.now(tzinfo)
                        if pending["date_str"]:
                            reminder_date = date.fromisoformat(pending["date_str"])
                        elif pending["rel"] == "tomorrow":
                            reminder_date = (now_tz + datetime.timedelta(days=1)).date()
                        else:
                            reminder_date = now_tz.date()
                        reminder_dt = datetime.datetime(
                            reminder_date.year,
                            reminder_date.month,
                            reminder_date.day,
                            pending["hour"],
                            pending["minute"],
                            tzinfo=tzinfo,
                        )
                        if reminder_dt < now_tz and pending["rel"] is None and pending["date_str"] is None:
                            reminder_dt = reminder_dt + datetime.timedelta(days=1)
                        elif reminder_dt < now_tz:
                            await message.reply("That time has already passed. Please choose a future time.")
                            return True
                        reminder_utc = reminder_dt.astimezone(datetime.timezone.utc)
                        notify_user_ids = self.get_reminder_target_user_ids(
                            message,
                            existing_ids=pending.get("notify_user_ids"),
                        )
                        saved = await self.add_reminder(
                            user_id=message.author.id,
                            channel_id=message.channel.id,
                            task=pending["task"],
                            when_utc=reminder_utc,
                            notify_user_ids=notify_user_ids,
                        )
                        if saved is None:
                            await message.reply("I couldn't save that reminder. Please try again.")
                            return True
                        print(
                            "Pending reminder scheduled: user_id="
                            f"{message.author.id} channel_id={message.channel.id} "
                            f"when_utc={reminder_utc.isoformat()} tz={tz_label} targets={notify_user_ids}",
                            flush=True,
                        )
                        del self.pending_reminders[pending_key]
                        reply_text = await self.build_reminder_ack_text(
                            pending["task"],
                            reminder_dt,
                            tz_label,
                            message.guild,
                            self.truncate_message,
                        )
                        await message.reply(reply_text)
                        return True

        if message_directly_mentions_user(self.client.user, message) and self.is_reminder_request_text(content_lower):
            notify_user_ids = self.get_reminder_target_user_ids(message)
            task, reminder_dt, reminder_utc, tz_label, error, pending = self.parse_reminder_request(
                content_no_mentions,
                allow_missing_tz=True,
            )
            if pending:
                self.pending_reminders[pending_key] = {
                    **pending,
                    "notify_user_ids": notify_user_ids,
                    "created_at": datetime.datetime.now(datetime.timezone.utc),
                }
                print(
                    "Pending reminder created: user_id="
                    f"{message.author.id} channel_id={message.channel.id} "
                    f"task={pending['task']} time={pending['hour']:02d}:{pending['minute']:02d} "
                    f"rel={pending['rel']} date={pending['date_str']} targets={notify_user_ids}",
                    flush=True,
                )
                await message.reply("Please include a timezone (e.g., GMT, UTC+2, America/New_York).")
                return True
            if error:
                await message.reply(error)
                return True
            saved = await self.add_reminder(
                user_id=message.author.id,
                channel_id=message.channel.id,
                task=task,
                when_utc=reminder_utc,
                notify_user_ids=notify_user_ids,
            )
            if saved is None:
                await message.reply("I couldn't save that reminder. Please try again.")
                return True
            print(
                "Reminder scheduled: user_id="
                f"{message.author.id} channel_id={message.channel.id} "
                f"when_utc={reminder_utc.isoformat()} tz={tz_label} targets={notify_user_ids}",
                flush=True,
            )
            reply_text = await self.build_reminder_ack_text(
                task,
                reminder_dt,
                tz_label,
                message.guild,
                self.truncate_message,
            )
            await message.reply(reply_text)
            return True

        return False


async def datetime_async_sleep(seconds):
    import asyncio

    await asyncio.sleep(seconds)

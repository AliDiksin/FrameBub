"""Natural-language reminders with durable schedules and session-lifetime edit controls."""

import asyncio
import datetime
import os
import re
from datetime import date
from uuid import uuid4
from zoneinfo import ZoneInfo

import discord

from bubbot.features import reminder_store

# Timezone aliases and parsing regex
REMINDER_POLL_SECONDS = int(os.getenv("REMINDER_POLL_SECONDS", "10"))
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
MONTHS = {name: number for number, name in enumerate(
    "january february march april may june july august september october november december".split(), 1
)}
DATE_PATTERN = (
    rf"(?:today|tomorrow|\d{{4}}-\d{{2}}-\d{{2}}|(?:(?:{'|'.join(MONTHS)})\s+\d{{1,2}}"
    rf"|\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:{'|'.join(MONTHS)}))(?:,?\s+\d{{4}})?)"
)
TIME_PATTERN = r"\d{1,2}(?::\d{2})?\s*(?:am|pm)?"


def message_directly_mentions_user(user, message):
    user_id = getattr(user, "id", None)
    if user_id is None:
        return False
    if any(getattr(mention, "id", None) == user_id for mention in getattr(message, "mentions", []) or []):
        return True
    return user_id in (getattr(message, "raw_mentions", []) or [])


# ReminderManager: parse requests, persist, poll and fire
class ReminderManager:
    def __init__(self, client, truncate_message_func, build_reminder_ack_text, build_reminder_fire_text):
        self.client = client
        self.truncate_message = truncate_message_func
        self.build_reminder_ack_text = build_reminder_ack_text
        self.build_reminder_fire_text = build_reminder_fire_text
        self.reminders = []
        self._delivering = set()
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
        # Keep the six-value interface; the legacy pending slot is always None.
        body = re.sub(r"^\s*remind(?:\s+me)?(?:\s+to)?(?:\s+|$)", "", text.strip(), flags=re.I)
        start = re.search(rf"\b(?:{DATE_PATTERN}|at\b|on\b|(?<![\w:+-])\d{{1,2}}(?::\d{{2}}(?:\s*(?:am|pm))?|\s*(?:am|pm))\b)", body, re.I)
        task, schedule = (body[:start.start()], body[start.start():]) if start else (body, "")
        after = re.search(r"\s+to\s+(.+)$", schedule, re.I)
        if after:
            task, schedule = after.group(1), schedule[:after.start()]
        schedule = re.sub(r"^on\s+", "", schedule, flags=re.I)
        task = re.sub(r"\s+on\s*$", "", task).strip(" ,.-")
        try:
            if not task:
                raise ValueError("I couldn't find the task. Try: 'remind me to practice on september 16'.")
            date_match = re.search(rf"\b(?:on\s+)?({DATE_PATTERN})\b", schedule, re.I)
            date_text = date_match.group(1).lower() if date_match else ""
            if date_match:
                schedule = schedule[:date_match.start()] + schedule[date_match.end():]
            time_match = re.search(r"(?<![\w:+-])(?:at\s+|(?=\d{1,2}(?::\d{2}(?:\s*(?:am|pm))?|\s*(?:am|pm))\b))(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", schedule, re.I)
            hour, minute = 0, 0
            if time_match:
                hour, minute = int(time_match[1]), int(time_match[2] or 0)
                ampm = (time_match[3] or "").lower()
                if minute > 59 or (ampm and not 1 <= hour <= 12) or (not ampm and hour > 23):
                    raise ValueError("Time is invalid. Use formats like 2:30pm or 14:30.")
                if ampm:
                    hour = hour % 12 + (12 if ampm == "pm" else 0)
                schedule = schedule[:time_match.start()] + schedule[time_match.end():]
            elif re.search(r"\bat\b", schedule, re.I):
                raise ValueError("Time is invalid. Use formats like 2:30pm or 14:30.")
            # Parse the entire remaining zone, never a valid prefix of an invalid zone.
            tzinfo, tz_label = self.parse_timezone(schedule.strip(" ,.") or "UTC")
            if tzinfo is None:
                raise ValueError("Unknown timezone or schedule. Use UTC, UTC+2, or an IANA zone like America/New_York.")
            now = datetime.datetime.now(tzinfo)
            yearless = False
            try:
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_text):
                    day = date.fromisoformat(date_text)
                elif date_text in ("", "today", "tomorrow"):
                    day = now.date() + datetime.timedelta(days=date_text == "tomorrow")
                else:
                    parts = date_text.replace(",", "").split()
                    if parts[0][0].isdigit():
                        parts = [part for part in parts if part != "of"]
                        parts[:2] = [parts[1], re.sub(r"(?:st|nd|rd|th)$", "", parts[0])]
                    month, day_number = MONTHS[parts[0]], int(parts[1])
                    yearless = len(parts) == 2
                    # Leap-day requests without a year advance to the next leap year.
                    date(2000, month, day_number)
                    year = int(parts[2]) if not yearless else now.year
                    while True:
                        try:
                            day = date(year, month, day_number)
                        except ValueError:
                            if not yearless or year >= 9999:
                                raise
                            year += 1
                            continue
                        if not yearless or datetime.datetime.combine(day, datetime.time(hour, minute)) > now.replace(tzinfo=None):
                            break
                        year += 1
                local = datetime.datetime.combine(day, datetime.time(hour, minute))
                if not date_text and local <= now.replace(tzinfo=None):
                    local += datetime.timedelta(days=1)
            except (ValueError, OverflowError):
                raise ValueError("That date is invalid. Use a real date such as september 16, 2027 or 2027-09-16.") from None
            # A UTC round trip rejects spring gaps; two distinct instants identify fall folds.
            candidates = set()
            for fold in (0, 1):
                utc = local.replace(tzinfo=tzinfo, fold=fold).astimezone(datetime.timezone.utc)
                if utc.astimezone(tzinfo).replace(tzinfo=None) == local:
                    candidates.add(utc)
            if not candidates:
                raise ValueError("That local time does not exist because of daylight saving time. Choose another time.")
            if len(candidates) > 1:
                raise ValueError("That local time is ambiguous because of daylight saving time. Specify a UTC offset, such as UTC-04:00 or UTC-05:00.")
            reminder_utc = candidates.pop()
            if reminder_utc <= now.astimezone(datetime.timezone.utc):
                raise ValueError("That time has already passed. Please choose a future time.")
            return task, reminder_utc.astimezone(tzinfo), reminder_utc, tz_label, None, None
        except (ValueError, OverflowError) as error:
            return None, None, None, None, str(error), None

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
        write = asyncio.create_task(asyncio.to_thread(reminder_store.save_records, list(self.reminders)))
        try:
            await asyncio.shield(write)
        except asyncio.CancelledError:
            # Do not release the lock while the disk writer still uses these records.
            await write
            raise

    async def add_reminder(self, *, user_id, channel_id, task, when_utc, notify_user_ids):
        await self.load()
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

    async def edit_reminder(self, reminder_id, user_id, when_utc):
        async with self._lock:
            record = next((item for item in self.reminders if item["id"] == reminder_id), None)
            if record is None:
                return "This reminder has already been delivered or is no longer available."
            if record["user_id"] != user_id:
                return "Only the person who created this reminder can edit it."
            if reminder_id in self._delivering:
                return "This reminder is being delivered and can no longer be edited."
            if when_utc <= datetime.datetime.now(datetime.timezone.utc):
                return "That time has already passed. Please choose a future time."
            previous = dict(record)
            record.update(when_utc=when_utc, attempts=0, next_attempt_utc=None)
            try:
                await self._persist_locked()
            except Exception as error:
                record.clear()
                record.update(previous)
                print(f"[reminders] edit save failed: {error}", flush=True)
                return "I couldn't save that change. Your previous reminder is unchanged."
        return None

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
                # Recheck under the edit lock: a due-list entry may have been rescheduled.
                async with self._lock:
                    if (reminder not in self.reminders or reminder["id"] in self._delivering
                            or reminder["when_utc"] > now_utc
                            or (reminder.get("next_attempt_utc") is not None and reminder["next_attempt_utc"] > now_utc)):
                        continue
                    self._delivering.add(reminder["id"])
                try:
                    if await self._deliver(dict(reminder)):
                        if not await self.remove_reminder(reminder["id"]):
                            print(f"[reminders] delivered reminder retained after persistence failure id={reminder['id']}", flush=True)
                    elif not await self.mark_delivery_failed(reminder["id"]):
                        print(f"[reminders] failed reminder retry state was not persisted id={reminder['id']}", flush=True)
                finally:
                    self._delivering.discard(reminder["id"])
            await asyncio.sleep(REMINDER_POLL_SECONDS)

    # Discord message path: new reminder or ignore.
    async def handle_message(self, message, content_no_mentions, content_lower):
        if message_directly_mentions_user(self.client.user, message) and self.is_reminder_request_text(content_lower):
            task, reminder_dt, reminder_utc, tz_label, error, _ = self.parse_reminder_request(content_no_mentions)
            if error:
                await message.reply(error)
                return True
            saved = await self.add_reminder(
                user_id=message.author.id, channel_id=message.channel.id, task=task,
                when_utc=reminder_utc, notify_user_ids=self.get_reminder_target_user_ids(message),
            )
            if saved is None:
                await message.reply("I couldn't save that reminder. Please try again.")
                return True
            reply_text = await self.build_reminder_ack_text(
                task,
                reminder_dt,
                tz_label,
                message.guild,
                self.truncate_message,
            )
            await message.reply(reply_text, view=ReminderEditView(self, saved, tz_label))
            return True

        return False


class ReminderEditView(discord.ui.View):
    def __init__(self, manager, record, tz_label):
        super().__init__(timeout=None)
        self.manager = manager
        self.record = record
        self.tz_label = tz_label

    async def interaction_check(self, interaction):
        if interaction.user.id != self.record["user_id"]:
            await interaction.response.send_message("Only the person who created this reminder can edit it.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Edit reminder", style=discord.ButtonStyle.secondary)
    async def edit(self, interaction, button):
        if self.record not in self.manager.reminders or self.record["id"] in self.manager._delivering:
            await interaction.response.send_message("This reminder is being delivered or is no longer available.", ephemeral=True)
            return
        await interaction.response.send_modal(ReminderEditModal(self))


class ReminderEditModal(discord.ui.Modal, title="Edit reminder"):
    date_input = discord.ui.TextInput(label="Date", placeholder="september 16, 2027 / 2027-09-16 / tomorrow", max_length=40)
    time_input = discord.ui.TextInput(label="Time (blank = midnight)", required=False, max_length=20)
    timezone_input = discord.ui.TextInput(label="Timezone (blank = UTC)", required=False, max_length=80)

    def __init__(self, view):
        super().__init__()
        self.reminder_view = view
        tzinfo, _ = view.manager.parse_timezone(view.tz_label)
        local = view.record["when_utc"].astimezone(tzinfo)
        self.date_input.default = local.date().isoformat()
        self.time_input.default = local.strftime("%H:%M")
        self.timezone_input.default = view.tz_label

    async def on_submit(self, interaction):
        view = self.reminder_view
        if not await view.interaction_check(interaction):
            return
        date_text, time_text, zone = (str(field).strip() for field in (self.date_input, self.time_input, self.timezone_input))
        if not re.fullmatch(DATE_PATTERN, date_text, re.I):
            await interaction.response.send_message("Date is invalid. Use september 16, 2027, 2027-09-16, today, or tomorrow.", ephemeral=True)
            return
        if time_text and not re.fullmatch(TIME_PATTERN, time_text, re.I):
            await interaction.response.send_message("Time is invalid. Use 2:30pm or 14:30.", ephemeral=True)
            return
        if view.manager.parse_timezone(zone or "UTC")[0] is None:
            await interaction.response.send_message("Unknown timezone. Use UTC, UTC+2, or America/New_York.", ephemeral=True)
            return
        _, local, utc, label, error, _ = view.manager.parse_reminder_request(
            f"remind me to task {date_text} at {time_text or '00:00'} {zone or 'UTC'}"
        )
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        error = await view.manager.edit_reminder(view.record["id"], interaction.user.id, utc)
        if error:
            await interaction.followup.send(error, ephemeral=True)
            return
        view.tz_label = label
        confirmation = f"Reminder rescheduled for {local:%Y-%m-%d %H:%M} {label} (<t:{int(utc.timestamp())}:F>)."
        # The durable edit is complete even if Discord cannot update the old message.
        try:
            task = view.manager.truncate_message(view.record["task"], 140)
            await interaction.message.edit(content=f"{task}\n{confirmation}", view=view,
                                           allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            confirmation += " I couldn't update the original confirmation message."
        await interaction.followup.send(confirmation, ephemeral=True)


async def datetime_async_sleep(seconds):
    import asyncio

    await asyncio.sleep(seconds)

"""Offline reminder checks: run with python -m unittest discover -s tests -p test_reminders.py."""

import asyncio
import datetime as dt
import os
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from bubbot.features import reminder_store
from bubbot.features.reminders import ReminderEditModal, ReminderEditView, ReminderManager

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 13, 12, tzinfo=UTC)


class Clock(dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


def manager():
    return ReminderManager(SimpleNamespace(user=SimpleNamespace(id=99)), lambda text, limit: text[:limit],
                           AsyncMock(return_value="Reminder set"), AsyncMock(return_value="Reminder"))


def interaction(owner=1):
    return SimpleNamespace(user=SimpleNamespace(id=owner), response=AsyncMock(), followup=AsyncMock(),
                           message=SimpleNamespace(edit=AsyncMock()))


class ParserTests(unittest.TestCase):
    @patch("bubbot.features.reminders.datetime.datetime", Clock)
    def test_dates_defaults_and_legacy_forms(self):
        cases = [
            ("remind me to practice on september 16", "2026-09-16T00:00:00+00:00"),
            ("remind me september 16, 2027 to practice", "2027-09-16T00:00:00+00:00"),
            ("remind me to practice september 12", "2027-09-12T00:00:00+00:00"),
            ("remind me to practice september 13", "2027-09-13T00:00:00+00:00"),
            ("remind me to practice september 13 at 1pm", "2026-09-13T13:00:00+00:00"),
            ("remind me to practice february 29", "2028-02-29T00:00:00+00:00"),
            ("remind me to practice 2027-09-16", "2027-09-16T00:00:00+00:00"),
            ("remind me to practice tomorrow", "2026-09-14T00:00:00+00:00"),
            ("remind me to practice today at 14:30", "2026-09-13T14:30:00+00:00"),
            ("remind me at 2:30pm GMT to practice", "2026-09-13T14:30:00+00:00"),
            ("remind me to practice at 2:30pm on tomorrow UTC+2", "2026-09-14T12:30:00+00:00"),
            ("remind me to practice tomorrow America/New_York", "2026-09-14T04:00:00+00:00"),
            ("remind me to practice at 9am", "2026-09-14T09:00:00+00:00"),
            ("remind me to practice", "2026-09-14T00:00:00+00:00"),
            ("remind me to practice on 13 september 18:00 UTC+2", "2026-09-13T16:00:00+00:00"),
            ("remind me to practice 13th september 2027 6pm UTC+2", "2027-09-13T16:00:00+00:00"),
            ("remind me 13 of September, 2027 6pm UTC+2 to practice", "2027-09-13T16:00:00+00:00"),
            ("remind me to practice 1st of october", "2026-10-01T00:00:00+00:00"),
            ("remind me to practice 2nd october", "2026-10-02T00:00:00+00:00"),
            ("remind me to practice 3rd of october", "2026-10-03T00:00:00+00:00"),
            ("remind me to practice 29th of february", "2028-02-29T00:00:00+00:00"),
            ("remind me to practice 12 september", "2027-09-12T00:00:00+00:00"),
            ("remind me to practice september 13 18:00 UTC+2", "2026-09-13T16:00:00+00:00"),
            ("remind me to practice 2026-09-13 6pm UTC+2", "2026-09-13T16:00:00+00:00"),
            ("remind me to practice 18:00 UTC+2", "2026-09-13T16:00:00+00:00"),
            ("remind me 6pm UTC+2 to practice", "2026-09-13T16:00:00+00:00"),
            ("remind me to practice 9am", "2026-09-14T09:00:00+00:00"),
            ("remind me to practice 6:30pm UTC+2", "2026-09-13T16:30:00+00:00"),
            ("remind me to practice tomorrow UTC+02:00", "2026-09-13T22:00:00+00:00"),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                task, _, utc, _, error, pending = manager().parse_reminder_request(text)
                self.assertIsNone(error)
                self.assertIsNone(pending)
                self.assertEqual(task, "practice")
                self.assertEqual(utc.isoformat(), expected)

    @patch("bubbot.features.reminders.datetime.datetime", Clock)
    def test_invalid_inputs_and_dst(self):
        for schedule, error in [
            ("2027-02-30", "date is invalid"), ("february 30", "date is invalid"),
            ("september 16, 0000", "date is invalid"), ("2025-09-16", "already passed"),
            ("today", "already passed"), ("tomorrow at 13pm", "Time is invalid"),
            ("tomorrow at 0am", "Time is invalid"), ("tomorrow at 24:00", "Time is invalid"),
            ("tomorrow at 12:60", "Time is invalid"), ("tomorrow at noon", "Time is invalid"),
            ("tomorrow XYZ", "Unknown timezone"), ("tomorrow UTC+25", "Unknown timezone"),
            ("tomorrow UTC+2garbage", "Unknown timezone"),
            ("tomorrow America/Not_A_Zone", "Unknown timezone"),
            ("30th of february", "date is invalid"),
            ("13th of september 2026 13:00 UTC+2", "already passed"),
            ("12 september 2026 18:00 UTC+2", "already passed"),
            ("13th of september 18:00 UTC+25", "Unknown timezone"),
            ("13th of september 6pm UTC+2garbage", "Unknown timezone"),
            ("13 september 18:00 XYZ", "Unknown timezone"),
            ("tomorrow UTC+24:00", "Unknown timezone"),
            ("tomorrow 24:00 UTC", "Time is invalid"),
            ("tomorrow 13pm UTC", "Time is invalid"),
            ("2027-03-14 at 2:30am America/New_York", "does not exist"),
            ("2026-11-01 at 1:30am America/New_York", "ambiguous"),
        ]:
            with self.subTest(schedule=schedule):
                self.assertIn(error, manager().parse_reminder_request(f"remind me to practice on {schedule}")[4])
        self.assertIsNone(manager().parse_reminder_request("remind me to practice 2026-11-01 at 1:30am UTC-04:00")[4])
        for text in ("", "remind", "remind me", "remind me to", "remind me tomorrow"):
            self.assertIn("find the task", manager().parse_reminder_request(text)[4])


class ReminderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = os.path.join(temporary.name, "reminders.json")
        self.env = patch.dict(os.environ, REMINDER_STORE_FILE=self.path)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.manager = manager()
        self.future = dt.datetime.now(UTC) + dt.timedelta(days=10)
        self.record = await self.manager.add_reminder(user_id=1, channel_id=2, task="practice",
                                                     when_utc=self.future, notify_user_ids=[3, 4])

    @patch("bubbot.features.reminders.datetime",
           SimpleNamespace(datetime=Clock, time=dt.time, timedelta=dt.timedelta, timezone=dt.timezone))
    async def test_screenshot_day_first_bare_time(self):
        message = SimpleNamespace(author=SimpleNamespace(id=1), channel=SimpleNamespace(id=2),
                                  content="@bub remind me to play strive on 13th of september 18:00 UTC+2",
                                  mentions=[SimpleNamespace(id=99)], guild=None, reply=AsyncMock())
        # Discord routing removes the bot mention before calling the reminder handler.
        text = message.content.removeprefix("@bub ")
        self.assertTrue(await self.manager.handle_message(message, text, text.lower()))
        record = self.manager.reminders[-1]
        self.assertEqual(record["task"], "play strive")
        self.assertEqual(record["when_utc"], dt.datetime(2026, 9, 13, 16, tzinfo=UTC))
        self.assertIsInstance(message.reply.call_args.kwargs["view"], ReminderEditView)

    async def test_persistence_edit_and_rollback(self):
        self.record.update(attempts=2, next_attempt_utc=self.future)
        await self.manager._persist_locked()
        restored = manager()
        await restored.load()
        self.assertEqual(restored.reminders, self.manager.reminders)
        changed = self.future + dt.timedelta(days=1)
        self.assertIsNone(await restored.edit_reminder(self.record["id"], 1, changed))
        saved = reminder_store.load_records()[0]
        for key in ("id", "user_id", "channel_id", "task", "notify_user_ids", "created_at_utc"):
            self.assertEqual(saved[key], self.record[key])
        self.assertEqual(saved["when_utc"], changed)
        self.assertEqual(saved["attempts"], 0)
        self.assertIsNone(saved["next_attempt_utc"])
        with patch.object(reminder_store, "save_records", side_effect=OSError("disk full")):
            self.assertIn("unchanged", await restored.edit_reminder(self.record["id"], 1, self.future))
        self.assertEqual(restored.reminders[0], saved)
        self.assertEqual(reminder_store.load_records()[0], saved)
        self.assertIn("Only", await restored.edit_reminder(self.record["id"], 9, self.future))
        self.assertIn("passed", await restored.edit_reminder(self.record["id"], 1, NOW))

    async def test_atomic_replace_failure_keeps_previous_file(self):
        with patch.object(reminder_store.os, "replace", side_effect=OSError("replace failed")):
            error = await self.manager.edit_reminder(self.record["id"], 1, self.future + dt.timedelta(days=1))
        self.assertIn("unchanged", error)
        self.assertEqual(reminder_store.load_records(), [self.record])
        self.assertEqual(self.record["when_utc"], self.future)

    async def test_existing_records_are_loaded_before_creation(self):
        restored = manager()
        await restored.add_reminder(user_id=5, channel_id=2, task="new", when_utc=self.future,
                                    notify_user_ids=[5])
        self.assertEqual(len(reminder_store.load_records()), 2)
        self.assertEqual(restored.reminders[0], self.record)

    async def test_cancelled_edit_waits_for_disk_writer(self):
        started, release = asyncio.Event(), threading.Event()
        loop = asyncio.get_running_loop()
        save = reminder_store.save_records

        def blocked_save(records):
            loop.call_soon_threadsafe(started.set)
            if not release.wait(2):
                raise TimeoutError("test writer was not released")
            save(records)

        changed = self.future + dt.timedelta(days=1)
        with patch.object(reminder_store, "save_records", side_effect=blocked_save):
            edit = asyncio.create_task(self.manager.edit_reminder(self.record["id"], 1, changed))
            try:
                await asyncio.wait_for(started.wait(), 2)
                edit.cancel()
                await asyncio.sleep(0)
                self.assertTrue(self.manager._lock.locked())
                self.assertFalse(edit.done())
            finally:
                release.set()
            with self.assertRaises(asyncio.CancelledError):
                await edit
        self.assertFalse(self.manager._lock.locked())
        self.assertEqual(reminder_store.load_records()[0]["when_utc"], changed)
        self.assertEqual(self.record["when_utc"], changed)

    async def test_button_modal_and_owner_checks(self):
        view = ReminderEditView(self.manager, self.record, "UTC")
        stranger = interaction(9)
        self.assertFalse(await view.interaction_check(stranger))
        click = interaction()
        await view.edit.callback(click)
        self.assertIsInstance(click.response.send_modal.call_args.args[0], ReminderEditModal)
        modal = ReminderEditModal(view)
        await modal.on_submit(stranger)
        stranger.response.defer.assert_not_awaited()
        modal.date_input._value = "16th of september 2090"
        modal.time_input._value = ""
        modal.timezone_input._value = "Unknown/Zone"
        invalid = interaction()
        await modal.on_submit(invalid)
        self.assertIn("Unknown timezone", invalid.response.send_message.call_args.args[0])
        self.assertEqual(self.record["when_utc"], self.future)
        modal.timezone_input._value = ""
        for field, value, error in [
            (modal.date_input, "16th of september 2090 garbage", "Date is invalid"),
            (modal.time_input, "6pm garbage", "Time is invalid"),
            (modal.timezone_input, "UTC+2garbage", "Unknown timezone"),
        ]:
            previous = field._value
            field._value = value
            invalid = interaction()
            await modal.on_submit(invalid)
            self.assertIn(error, invalid.response.send_message.call_args.args[0])
            self.assertEqual(self.record["when_utc"], self.future)
            field._value = previous
        owner = interaction()
        await modal.on_submit(owner)
        self.assertEqual(self.record["when_utc"], dt.datetime(2090, 9, 16, tzinfo=UTC))
        owner.message.edit.assert_awaited_once()
        owner.followup.send.assert_awaited_once()
        await self.manager.remove_reminder(self.record["id"])
        await modal.on_submit(interaction())
        self.assertEqual(self.manager.reminders, [])

    async def test_addressed_creation_targets_and_no_pending_prompt(self):
        message = SimpleNamespace(author=SimpleNamespace(id=1), channel=SimpleNamespace(id=2),
                                  mentions=[SimpleNamespace(id=99), SimpleNamespace(id=3)],
                                  guild=None, reply=AsyncMock())
        text = "remind me to practice on september 16, 2090"
        self.assertTrue(await self.manager.handle_message(message, text, text))
        self.assertEqual(self.manager.reminders[-1]["notify_user_ids"], [3])
        self.assertIsInstance(message.reply.call_args.kwargs["view"], ReminderEditView)
        message.mentions = []
        self.assertFalse(await self.manager.handle_message(message, text, text))

    @patch("bubbot.features.reminders.datetime",
           SimpleNamespace(datetime=Clock, time=dt.time, timedelta=dt.timedelta, timezone=dt.timezone))
    async def test_dated_other_recipient_reminder_creation_edit_and_delivery(self):
        channel = SimpleNamespace(id=2, guild=None, send=AsyncMock())
        message = SimpleNamespace(author=SimpleNamespace(id=1), channel=channel,
                                  content="<@99> remind <@3> <@!4> to practice on september 16",
                                  mentions=[SimpleNamespace(id=99), SimpleNamespace(id=3), SimpleNamespace(id=4)],
                                  guild=None, reply=AsyncMock())
        # The router strips mention text, but passes the original message with its recipients.
        text = "remind to practice on september 16"
        self.assertTrue(await self.manager.handle_message(message, text, text.lower()))
        record = self.manager.reminders[-1]
        self.assertEqual(record["task"], "practice")
        self.assertEqual(record["notify_user_ids"], [3, 4])
        self.assertEqual(record["when_utc"], dt.datetime(2026, 9, 16, tzinfo=UTC))
        view = message.reply.call_args.kwargs["view"]
        self.assertIsInstance(view, ReminderEditView)
        message.reply.assert_awaited_once_with("Reminder set", view=view)
        self.assertIs(view.record, record)
        self.assertEqual(record["user_id"], 1)
        for recipient in (3, 4):
            self.assertFalse(await view.interaction_check(interaction(recipient)))
        owner = interaction()
        self.assertTrue(await view.interaction_check(owner))
        await view.edit.callback(owner)
        modal = owner.response.send_modal.call_args.args[0]
        self.assertIsInstance(modal, ReminderEditModal)
        modal.date_input._value = "september 17"
        modal.time_input._value = ""
        modal.timezone_input._value = ""
        await modal.on_submit(owner)
        self.assertEqual(record["when_utc"], dt.datetime(2026, 9, 17, tzinfo=UTC))
        self.assertEqual(record["task"], "practice")
        self.assertEqual(record["notify_user_ids"], [3, 4])
        self.assertEqual(reminder_store.load_records()[-1], record)
        owner.message.edit.assert_awaited_once()
        restored = manager()
        await restored.load()
        reloaded = next(item for item in restored.reminders if item["id"] == record["id"])
        self.assertEqual(reloaded["when_utc"], dt.datetime(2026, 9, 17, tzinfo=UTC))
        self.assertEqual(reloaded["task"], "practice")
        self.assertEqual(reloaded["notify_user_ids"], [3, 4])
        restored.client.get_channel = Mock(return_value=channel)
        self.assertTrue(await restored._deliver(reloaded))
        restored.client.get_channel.assert_called_once_with(2)
        restored.build_reminder_fire_text.assert_awaited_once_with("practice", None, restored.truncate_message)
        channel.send.assert_awaited_once_with("<@3> <@4> Reminder")

    async def test_edit_delivery_race_and_stale_due_list(self):
        self.record["when_utc"] = dt.datetime.now(UTC) - dt.timedelta(seconds=1)
        second = await self.manager.add_reminder(user_id=1, channel_id=2, task="second",
                                                 when_utc=self.record["when_utc"], notify_user_ids=[1])
        entered, release = asyncio.Event(), asyncio.Event()

        async def deliver(record):
            entered.set()
            await release.wait()
            return True

        self.manager.client.is_closed = Mock(side_effect=[False, True])
        self.manager._deliver = AsyncMock(side_effect=deliver)
        with patch("bubbot.features.reminders.REMINDER_POLL_SECONDS", 0):
            loop = asyncio.create_task(self.manager.reminder_loop())
            await asyncio.wait_for(entered.wait(), 2)
            self.assertIn("being delivered", await self.manager.edit_reminder(self.record["id"], 1, self.future))
            self.assertIsNone(await self.manager.edit_reminder(second["id"], 1, self.future))
            release.set()
            await asyncio.wait_for(loop, 2)
        self.manager._deliver.assert_awaited_once()
        self.assertEqual(self.manager.reminders, [second])
        self.assertEqual(reminder_store.load_records(), [second])
        self.assertFalse(self.manager._delivering)

    async def test_failed_delivery_retry_survives_reload(self):
        self.record["when_utc"] = dt.datetime.now(UTC) - dt.timedelta(seconds=1)
        self.manager.client.is_closed = Mock(side_effect=[False, True])
        self.manager._deliver = AsyncMock(return_value=False)
        with patch("bubbot.features.reminders.REMINDER_POLL_SECONDS", 0):
            await self.manager.reminder_loop()
        saved = reminder_store.load_records()[0]
        self.assertEqual(saved["attempts"], 1)
        self.assertGreater(saved["next_attempt_utc"], dt.datetime.now(UTC))
        self.assertFalse(self.manager._delivering)


if __name__ == "__main__":
    unittest.main()

import asyncio
import datetime
import random

from aiohttp import web


class SchedulerManager:
    def __init__(
        self,
        client,
        channel_id,
        daily_encouragement_messages,
        daily_damn_gg_text,
        daily_streetfighterdle_messages,
        streetfighterdle_url,
        streetfighterdle_score_source_channel_id,
        build_streetfighterdle_reminder_text,
        collect_streetfighterdle_daily_scores,
        save_streetfighterdle_score_snapshot,
        build_streetfighterdle_leaderboard_text,
        send_generated_encouragement,
        strip_discord_mentions,
        memory_file,
        memory_max_entries,
        memory_context_max_messages,
        encouragement_context_chance,
        encouragement_context_source,
    ):
        self.client = client
        self.channel_id = channel_id
        self.daily_encouragement_messages = daily_encouragement_messages
        self.daily_damn_gg_text = daily_damn_gg_text
        self.daily_streetfighterdle_messages = daily_streetfighterdle_messages
        self.streetfighterdle_url = streetfighterdle_url
        self.streetfighterdle_score_source_channel_id = streetfighterdle_score_source_channel_id
        self.build_streetfighterdle_reminder_text = build_streetfighterdle_reminder_text
        self.collect_streetfighterdle_daily_scores = collect_streetfighterdle_daily_scores
        self.save_streetfighterdle_score_snapshot = save_streetfighterdle_score_snapshot
        self.build_streetfighterdle_leaderboard_text = build_streetfighterdle_leaderboard_text
        self.send_generated_encouragement = send_generated_encouragement
        self.strip_discord_mentions = strip_discord_mentions
        self.memory_file = memory_file
        self.memory_max_entries = memory_max_entries
        self.memory_context_max_messages = memory_context_max_messages
        self.encouragement_context_chance = encouragement_context_chance
        self.encouragement_context_source = encouragement_context_source
        self.next_run_time = None
        self.next_encouragement_time = None
        self.next_video_time = None
        self.next_damn_gg_time = None
        self.next_streetfighterdle_time = None
        self.last_damn_gg_sent_date = None
        self.last_streetfighterdle_sent_date_utc = None
        self.last_streetfighterdle_leaderboard_date_utc = None
        self.last_scheduled_encouragement_sent_at = None

    async def channel_has_human_messages_since(self, channel, since_dt):
        if since_dt is None:
            return True

        try:
            async for prev_msg in channel.history(after=since_dt, oldest_first=False):
                author = getattr(prev_msg, "author", None)
                if author is None:
                    continue
                if self.client.user is not None and getattr(author, "id", None) == getattr(self.client.user, "id", None):
                    continue
                if getattr(author, "bot", False):
                    continue
                return True
        except Exception as e:
            print(f"[encouragement] human-message scan error: {e}", flush=True)
            return True

        return False

    async def send_daily_messages(self, channel):
        print("[daily-message] Dispatching 4-line batch.", flush=True)
        messages = [
            "Hello everyone",
            "How are you today?",
            "Has anyone improved?",
            "<:sponge:1416270403923480696>",
        ]
        for msg in messages:
            try:
                await channel.send(msg)
                await asyncio.sleep(1)
            except Exception as e:
                print(f"[daily-message] Dispatch error: {e}", flush=True)
        print("[daily-message] Batch dispatched successfully.", flush=True)

    async def send_daily_damn_gg(self, channel, source_label="scheduled"):
        try:
            await channel.send(self.daily_damn_gg_text)
            print(
                f"{source_label.capitalize()} literal message sent at {datetime.datetime.now().isoformat()}",
                flush=True,
            )
            return True
        except Exception as e:
            print(f"{source_label.capitalize()} literal message error: {e}", flush=True)
            return False

    def get_damn_gg_daily_slot(self, day_start):
        rng = random.Random(f"damn-gg-{day_start.date().isoformat()}")
        return day_start + datetime.timedelta(seconds=rng.randint(0, 86399))

    async def send_daily_streetfighterdle(self, channel, source_label="scheduled"):
        reminder_text = await self.build_streetfighterdle_reminder_text(channel, self.streetfighterdle_url)
        payload = f"{reminder_text}\n{self.streetfighterdle_url}"
        try:
            await channel.send(payload)
            print(
                f"[streetfighterdle] {source_label} reminder sent at {datetime.datetime.now().isoformat()}",
                flush=True,
            )
            return True
        except Exception as e:
            print(f"[streetfighterdle] {source_label} error: {e}", flush=True)
            return False

    async def send_daily_streetfighterdle_score_leaderboard(self, output_channel, source_label="scheduled", window_end_utc=None):
        source_channel = self.client.get_channel(self.streetfighterdle_score_source_channel_id)
        if not source_channel:
            try:
                source_channel = await self.client.fetch_channel(self.streetfighterdle_score_source_channel_id)
            except Exception as e:
                print(f"[streetfighterdle] leaderboard source channel error: {e}", flush=True)
                return False

        snapshot_end_utc = window_end_utc or datetime.datetime.now(datetime.timezone.utc)
        snapshot_date_utc = snapshot_end_utc.date().isoformat()
        try:
            entries = await self.collect_streetfighterdle_daily_scores(source_channel, window_end_utc=snapshot_end_utc)
            self.save_streetfighterdle_score_snapshot(
                snapshot_date_utc,
                entries,
                source_channel_id=self.streetfighterdle_score_source_channel_id,
            )
            leaderboard_text = self.build_streetfighterdle_leaderboard_text(entries, snapshot_date_utc)
            await output_channel.send(leaderboard_text)
            print(
                f"[streetfighterdle] {source_label} leaderboard sent at {datetime.datetime.now(datetime.timezone.utc).isoformat()} entries={len(entries)}",
                flush=True,
            )
            return True
        except Exception as e:
            print(f"[streetfighterdle] {source_label} leaderboard error: {e}", flush=True)
            return False

    def get_daily_random_slots(self, day_start, count, excluded_slots=None):
        excluded_seconds = set()
        for slot in excluded_slots or []:
            if slot.date() != day_start.date():
                continue
            excluded_seconds.add(int((slot - day_start).total_seconds()))

        available_seconds = [second for second in range(86400) if second not in excluded_seconds]
        if count <= 0 or not available_seconds:
            return []
        sample_count = min(count, len(available_seconds))
        second_slots = sorted(random.sample(available_seconds, sample_count))
        return [day_start + datetime.timedelta(seconds=slot) for slot in second_slots]

    async def background_task(self):
        await self.client.wait_until_ready()
        channel = self.client.get_channel(self.channel_id)
        if not channel:
            print(f"[daily-message] Could not find channel with ID {self.channel_id}", flush=True)
            return

        print("[daily-message] Scheduling started.", flush=True)

        while not self.client.is_closed():
            now = datetime.datetime.now()
            start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            random_seconds = random.randint(0, 86399)
            target_time = start_of_day + datetime.timedelta(seconds=random_seconds)

            if target_time < now:
                start_of_tomorrow = start_of_day + datetime.timedelta(days=1)
                random_seconds_tomorrow = random.randint(0, 86399)
                target_time = start_of_tomorrow + datetime.timedelta(seconds=random_seconds_tomorrow)
                print(f"[daily-message] Daily slot elapsed. Next cycle at {target_time}", flush=True)
            else:
                print(f"[daily-message] Current cycle scheduled at {target_time}", flush=True)

            self.next_run_time = target_time
            wait_seconds = (target_time - datetime.datetime.now()).total_seconds()
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            if self.client.is_closed():
                return

            await self.send_daily_messages(channel)

            next_day = (datetime.datetime.now() + datetime.timedelta(days=1)).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            seconds_until_tomorrow = (next_day - datetime.datetime.now()).total_seconds()
            print(
                f"[daily-message] Done for today. Waiting {seconds_until_tomorrow / 3600:.2f} hours until midnight regeneration.",
                flush=True,
            )
            self.next_run_time = None
            if seconds_until_tomorrow > 0:
                await asyncio.sleep(seconds_until_tomorrow)

    async def background_encouragement_task(self):
        await self.client.wait_until_ready()
        if self.daily_encouragement_messages <= 0:
            print("[encouragement] Disabled: DAILY_ENCOURAGEMENT_MESSAGES <= 0", flush=True)
            return

        channel = self.client.get_channel(self.channel_id)
        if not channel:
            print(f"[encouragement] Could not find channel with ID {self.channel_id}", flush=True)
            return

        print(
            f"[encouragement] Scheduling started. Target={self.daily_encouragement_messages} LLM messages per day. context_chance={self.encouragement_context_chance:.2f} source={self.encouragement_context_source}",
            flush=True,
        )

        while not self.client.is_closed():
            now = datetime.datetime.now()
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            day_slots = self.get_daily_random_slots(day_start, self.daily_encouragement_messages)
            remaining_slots = [slot for slot in day_slots if slot > now]

            if not remaining_slots:
                day_start = day_start + datetime.timedelta(days=1)
                remaining_slots = self.get_daily_random_slots(day_start, self.daily_encouragement_messages)

            slot_log = ", ".join(slot.strftime("%Y-%m-%d %H:%M:%S") for slot in remaining_slots)
            print(f"[encouragement] Slots ({len(remaining_slots)}): {slot_log}", flush=True)

            for index, slot_time in enumerate(remaining_slots, start=1):
                self.next_encouragement_time = slot_time
                wait_seconds = (slot_time - datetime.datetime.now()).total_seconds()
                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds)
                if self.client.is_closed():
                    return
                print(
                    f"[encouragement] Dispatching scheduled encouragement {index}/{len(remaining_slots)}.",
                    flush=True,
                )
                if self.last_scheduled_encouragement_sent_at is not None:
                    has_human_messages = await self.channel_has_human_messages_since(
                        channel,
                        self.last_scheduled_encouragement_sent_at,
                    )
                    if not has_human_messages:
                        sent_message = await channel.send("dead server")
                        self.last_scheduled_encouragement_sent_at = getattr(
                            sent_message,
                            "created_at",
                            datetime.datetime.now(datetime.timezone.utc),
                        )
                        print(
                            f"[encouragement] scheduled dead-server sent at {datetime.datetime.now().isoformat()}",
                            flush=True,
                        )
                        continue

                sent_message = await self.send_generated_encouragement(
                    channel,
                    self.strip_discord_mentions,
                    self.client.user,
                    self.memory_file,
                    self.memory_max_entries,
                    self.memory_context_max_messages,
                    source_label="scheduled",
                )
                if sent_message is not None:
                    self.last_scheduled_encouragement_sent_at = getattr(
                        sent_message,
                        "created_at",
                        datetime.datetime.now(datetime.timezone.utc),
                    )

            self.next_encouragement_time = None

    async def background_damn_gg_task(self):
        await self.client.wait_until_ready()

        print("Damn gg scheduling started.", flush=True)

        while not self.client.is_closed():
            channel = self.client.get_channel(self.channel_id)
            if not channel:
                try:
                    channel = await self.client.fetch_channel(self.channel_id)
                except Exception as e:
                    print(f"Could not find channel with ID {self.channel_id}; retrying in 5 minutes. error={e}", flush=True)
                    self.next_damn_gg_time = None
                    await asyncio.sleep(300)
                    continue

            now = datetime.datetime.now()
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_slot = self.get_damn_gg_daily_slot(day_start)

            if self.last_damn_gg_sent_date == day_start.date() or today_slot <= now:
                day_start = day_start + datetime.timedelta(days=1)
                slot_time = self.get_damn_gg_daily_slot(day_start)
            else:
                slot_time = today_slot

            self.next_damn_gg_time = slot_time
            print(f"Damn gg slot: {slot_time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)

            wait_seconds = (slot_time - datetime.datetime.now()).total_seconds()
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            if self.client.is_closed():
                return

            target_date = slot_time.date()
            if self.last_damn_gg_sent_date == target_date:
                print(f"Skipping duplicate damn gg for {target_date.isoformat()}.", flush=True)
                continue

            sent = False
            retry_attempt = 0
            while not sent and not self.client.is_closed():
                retry_attempt += 1
                sent = await self.send_daily_damn_gg(
                    channel,
                    source_label="scheduled" if retry_attempt == 1 else f"scheduled-retry-{retry_attempt}",
                )
                if sent:
                    self.last_damn_gg_sent_date = target_date
                    break
                if self.client.is_closed():
                    return
                retry_delay_seconds = min(900, 300 * retry_attempt)
                print(f"Damn gg send failed; retrying in {retry_delay_seconds} seconds.", flush=True)
                await asyncio.sleep(retry_delay_seconds)

            self.next_damn_gg_time = None

    async def background_streetfighterdle_task(self):
        await self.client.wait_until_ready()
        if self.daily_streetfighterdle_messages <= 0:
            print("[streetfighterdle] Disabled: DAILY_STREETFIGHTERDLE_MESSAGES <= 0", flush=True)
            return

        print(
            "[streetfighterdle] Scheduling started. Target=1 reminder per day at 00:00 UTC.",
            flush=True,
        )

        while not self.client.is_closed():
            channel = self.client.get_channel(self.channel_id)
            if not channel:
                try:
                    channel = await self.client.fetch_channel(self.channel_id)
                except Exception as e:
                    print(
                        f"[streetfighterdle] Could not find channel with ID {self.channel_id}; retrying in 5 minutes. error={e}",
                        flush=True,
                    )
                    self.next_streetfighterdle_time = None
                    await asyncio.sleep(300)
                    continue

            now_utc = datetime.datetime.now(datetime.timezone.utc)
            next_midnight_utc = (now_utc + datetime.timedelta(days=1)).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            self.next_streetfighterdle_time = next_midnight_utc
            print(
                f"[streetfighterdle] Next reminder scheduled for {next_midnight_utc.isoformat()}",
                flush=True,
            )

            wait_seconds = (next_midnight_utc - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            if self.client.is_closed():
                return

            target_date_utc = next_midnight_utc.date()
            if self.last_streetfighterdle_sent_date_utc == target_date_utc:
                print(
                    f"[streetfighterdle] Skipping duplicate reminder for {target_date_utc.isoformat()}.",
                    flush=True,
                )
                continue

            reminder_sent = False
            retry_attempt = 0
            while not reminder_sent and not self.client.is_closed():
                retry_attempt += 1
                reminder_sent = await self.send_daily_streetfighterdle(
                    channel,
                    source_label="scheduled" if retry_attempt == 1 else f"scheduled-retry-{retry_attempt}",
                )
                if reminder_sent:
                    self.last_streetfighterdle_sent_date_utc = target_date_utc
                    break
                if self.client.is_closed():
                    return
                retry_delay_seconds = min(900, 300 * retry_attempt)
                print(
                    f"[streetfighterdle] send failed for midnight UTC slot; retrying in {retry_delay_seconds} seconds.",
                    flush=True,
                )
                await asyncio.sleep(retry_delay_seconds)

            self.next_streetfighterdle_time = None

    async def background_streetfighterdle_leaderboard_task(self):
        await self.client.wait_until_ready()
        if self.daily_streetfighterdle_messages <= 0:
            print("[streetfighterdle] leaderboard disabled: DAILY_STREETFIGHTERDLE_MESSAGES <= 0", flush=True)
            return

        print(
            "[streetfighterdle] Leaderboard scheduling started. Target=1 leaderboard per day at 23:00 UTC.",
            flush=True,
        )

        while not self.client.is_closed():
            output_channel = self.client.get_channel(self.channel_id)
            if not output_channel:
                try:
                    output_channel = await self.client.fetch_channel(self.channel_id)
                except Exception as e:
                    print(
                        f"[streetfighterdle] leaderboard output channel error; retrying in 5 minutes. error={e}",
                        flush=True,
                    )
                    await asyncio.sleep(300)
                    continue

            now_utc = datetime.datetime.now(datetime.timezone.utc)
            today_leaderboard_utc = now_utc.replace(hour=23, minute=0, second=0, microsecond=0)

            if now_utc < today_leaderboard_utc:
                target_time_utc = today_leaderboard_utc
                target_date_utc = target_time_utc.date()
            elif (
                self.last_streetfighterdle_leaderboard_date_utc is not None
                and self.last_streetfighterdle_leaderboard_date_utc != now_utc.date()
                and now_utc < today_leaderboard_utc + datetime.timedelta(hours=1)
            ):
                target_time_utc = now_utc
                target_date_utc = now_utc.date()
            else:
                target_time_utc = today_leaderboard_utc + datetime.timedelta(days=1)
                target_date_utc = target_time_utc.date()

            wait_seconds = (target_time_utc - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
            if wait_seconds > 0:
                print(
                    f"[streetfighterdle] Next leaderboard scheduled for {target_time_utc.isoformat()}",
                    flush=True,
                )
                await asyncio.sleep(wait_seconds)
            if self.client.is_closed():
                return

            if self.last_streetfighterdle_leaderboard_date_utc == target_date_utc:
                print(
                    f"[streetfighterdle] Skipping duplicate leaderboard for {target_date_utc.isoformat()}.",
                    flush=True,
                )
                continue

            window_end_utc = datetime.datetime.combine(
                target_date_utc,
                datetime.time(hour=23, minute=0, tzinfo=datetime.timezone.utc),
            )
            leaderboard_sent = False
            retry_attempt = 0
            while not leaderboard_sent and not self.client.is_closed():
                retry_attempt += 1
                leaderboard_sent = await self.send_daily_streetfighterdle_score_leaderboard(
                    output_channel,
                    source_label="scheduled-leaderboard" if retry_attempt == 1 else f"scheduled-leaderboard-retry-{retry_attempt}",
                    window_end_utc=window_end_utc,
                )
                if leaderboard_sent:
                    self.last_streetfighterdle_leaderboard_date_utc = target_date_utc
                    break
                if self.client.is_closed():
                    return
                retry_delay_seconds = min(900, 300 * retry_attempt)
                print(
                    f"[streetfighterdle] leaderboard send failed; retrying in {retry_delay_seconds} seconds.",
                    flush=True,
                )
                await asyncio.sleep(retry_delay_seconds)

    async def time_handler(self, request):
        data = {
            "target_time": str(self.next_run_time) if self.next_run_time else None,
            "daily_message_time": str(self.next_run_time) if self.next_run_time else None,
            "encouragement_time": str(self.next_encouragement_time) if self.next_encouragement_time else None,
            "damn_gg_time": str(self.next_damn_gg_time) if self.next_damn_gg_time else None,
            "video_time": str(self.next_video_time) if self.next_video_time else None,
        }
        return web.json_response(data)

    async def start_web_server(self):
        app = web.Application()
        app.router.add_get("/time", self.time_handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", 8080)
        await site.start()
        print("Web server started on port 8080")

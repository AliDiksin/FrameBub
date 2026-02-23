# Architecture

**Analysis Date:** 2026-02-23

## Pattern Overview

**Overall:** Event-driven monolith with async workers and in-memory caches.

**Key Characteristics:**
- Keep runtime orchestration, parser logic, scheduling, quiz flow, and LLM routing in `bot.py`.
- Load authoritative SF6 data once from `FAT - SF6 Frame Data.ods` into module-level dictionaries in `bot.py`.
- Isolate external CFN/SFBuff HTTP integration in `sfbuff_integration.py` and call it from `bot.py` command handlers.

## Layers

**Runtime Orchestration Layer:**
- Purpose: Own process startup, Discord event hooks, task lifecycle, and shutdown behavior.
- Location: `bot.py`
- Contains: `on_ready`, `on_message`, background scheduler tasks, `worker`, and `if __name__ == "__main__": client.run(TOKEN)`.
- Depends on: `discord.py`, `asyncio`, environment variables loaded in `bot.py`.
- Used by: Entire application runtime.

**Data Loading and In-Memory State Layer:**
- Purpose: Build and store game data/state used by all command paths.
- Location: `bot.py`
- Contains: `load_frame_data`, `FRAME_DATA`, `FRAME_STATS`, `BNB_DATA`, `OKI_DATA`, `CHARACTER_INFO`, `HITBOX_GIF_DATA`, `RANGE_DATA`, quiz/reminder globals.
- Depends on: `pandas` ODS reads from `FAT - SF6 Frame Data.ods`.
- Used by: Parser, frame lookup, gif lookup, quiz, reminder, and response-formatting paths in `bot.py`.

**Parsing and Resolution Layer:**
- Purpose: Convert free-form user text into resolved character/move/domain intents.
- Location: `bot.py`
- Contains: `find_moves_in_text`, `lookup_frame_data`, alias normalization helpers, comparison/punish/property extraction logic.
- Depends on: In-memory data dictionaries initialized by `load_frame_data` in `bot.py`.
- Used by: Direct frame/gif handling and LLM-context construction inside `on_message` in `bot.py`.

**External Integration Layer:**
- Purpose: Encapsulate remote API/site calls and parsing outside Discord handlers.
- Location: `sfbuff_integration.py`
- Contains: `search`, `search_status`, `sync`, `rivals`, `matchups`, `matches`, `history`, HTML parsing helpers.
- Depends on: `aiohttp`, environment-driven config from `get_config` in `sfbuff_integration.py`.
- Used by: `handle_cfn_command` and `handle_cfn_site_command` in `bot.py`.

**Presentation and Response Layer:**
- Purpose: Format and publish outputs to Discord and the `/time` web endpoint.
- Location: `bot.py`
- Contains: Frame embed builders (`build_frame_embed`, `build_frame_embeds`), text formatters, reply/fallback send logic, `time_handler`.
- Depends on: Parser payloads, row dictionaries, scheduler state globals.
- Used by: `on_message`, `worker`, and `start_web_server` in `bot.py`.

## Data Flow

**Startup Flow:**

1. `if __name__ == "__main__"` in `bot.py` starts Discord client with `client.run(TOKEN)`.
2. `on_ready` in `bot.py` initializes `message_queue`, background scheduler tasks, reminder loop, and `start_web_server`.
3. `load_frame_data` in `bot.py` reads `FAT - SF6 Frame Data.ods` and populates runtime dictionaries consumed by all request paths.

**Message Handling Flow:**

1. `on_message` in `bot.py` applies routing priority: manual triggers -> CFN commands -> quiz state machine -> reminder flow -> frame/gif parsing -> LLM fallback.
2. `find_moves_in_text` in `bot.py` emits a structured payload (`mode`, `rows`, flags) used for direct responses and LLM context.
3. Direct handlers in `bot.py` send embeds/text for frame/gif/property queries or enqueue LLM work when conversational output is needed.

**LLM Queue Flow:**

1. `on_message` in `bot.py` appends prepared `llm_messages` + fallback context to `message_queue`.
2. `worker` in `bot.py` dequeues one item at a time, chooses provider via `get_llm_response`, and applies reply fallbacks.
3. Output is posted to Discord with deleted-reference failsafe handling in `bot.py`.

**State Management:**
- Use module-level dictionaries/lists in `bot.py` for authoritative runtime state (`FRAME_DATA`, `REMINDERS`, `ACTIVE_QUIZZES`, `SPECIAL_STRENGTH_PROMPT_MODE`).
- Keep external integration stateless per request in `sfbuff_integration.py` by creating request-scoped sessions.

## Key Abstractions

**Frame Row Record:**
- Purpose: Represent one move's canonical frame data and metadata.
- Examples: Row dictionaries created in `load_frame_data` and consumed by `format_frame_data` in `bot.py`.
- Pattern: `dict`-based record with keys such as `moveName`, `numCmd`, `startup`, `onHit`, `onBlock`, `atkRange` in `bot.py`.

**Parsed Context Payload:**
- Purpose: Carry parsed intent and resolved rows from text parser to routing layer.
- Examples: Return object from `find_moves_in_text` in `bot.py`.
- Pattern: Single payload dict with deterministic keys (`data`, `mode`, `rows`, `gif_query`, `missing_scrolls_query`, `property_only_query`).

**Quiz Session State:**
- Purpose: Track per-channel quiz lifecycle, scores, answer key, and reply-thread continuity.
- Examples: `ACTIVE_QUIZZES`, `QUIZ_PENDING_ANOTHER`, `QUIZ_PENDING_MODE` in `bot.py`.
- Pattern: `channel_id -> dict` state machines handled by `start_quiz`, `handle_quiz_answer`, and `stop_quiz` in `bot.py`.

**CFN Gateway Contract:**
- Purpose: Normalize CFN request/response behavior independent of Discord UX text.
- Examples: `search`, `rivals`, `matchups`, `history` in `sfbuff_integration.py`.
- Pattern: Return payload dictionaries/lists with explicit error markers (`_error`, `status`, `body`) consumed by `handle_cfn_site_command` in `bot.py`.

## Entry Points

**Process Entry Point:**
- Location: `bot.py`
- Triggers: Python runtime execution (`python bot.py`).
- Responsibilities: Validate token presence and start Discord gateway loop.

**Discord Ready Hook:**
- Location: `bot.py`
- Triggers: Discord client ready event.
- Responsibilities: Initialize queue/tasks/server and load game data for runtime queries.

**Discord Message Hook:**
- Location: `bot.py`
- Triggers: Every user-authored message visible to bot intents.
- Responsibilities: Route command types, resolve frame/gif/quiz/reminder behaviors, and enqueue conversational LLM work.

**Web Status Endpoint:**
- Location: `bot.py`
- Triggers: HTTP GET `/time` on aiohttp server.
- Responsibilities: Expose upcoming scheduler timestamps (`daily_message_time`, `encouragement_time`, `damn_gg_time`, `video_time`).

## Error Handling

**Strategy:** Defensive try/except with user-safe fallback replies and logging.

**Patterns:**
- Catch integration failures and return user-facing CFN error text in `handle_cfn_site_command` in `bot.py`.
- Detect deleted Discord reply targets with `is_deleted_message_reference_error` and publish failsafe channel messages in `bot.py`.

## Cross-Cutting Concerns

**Logging:** Print-based operational logging with feature tags (for example `[daily-message]`, `[encouragement]`, `[quiz]`) in `bot.py`.
**Validation:** Input normalization/regex guards in `find_moves_in_text`, `lookup_frame_data`, `parse_reminder_request`, and `is_valid_short_id` in `bot.py`.
**Authentication:** Environment-token authentication for Discord/LLM providers in `bot.py`; no internal user auth layer beyond Discord message context.

---

*Architecture analysis: 2026-02-23*

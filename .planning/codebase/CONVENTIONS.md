# Coding Conventions

**Analysis Date:** 2026-02-23

## Naming Patterns

**Files:**
- Use `snake_case.py` for Python modules, as seen in `bot.py`, `sfbuff_integration.py`, and `lltest.py`.
- Keep operational guidance in uppercase markdown filenames for planning docs under `.planning/codebase/` (for example `CONVENTIONS.md`, `TESTING.md`).

**Functions:**
- Use `snake_case` for regular and async functions (`find_moves_in_text`, `lookup_frame_data`, `build_quiz_question_message`) in `bot.py`.
- Use leading underscore for module-private quiz helpers (`_quiz_send_thinking_message`, `_quiz_extract_mode_from_text`) in `bot.py`.

**Variables:**
- Use `snake_case` for local and module variables (`reply_text`, `pending_scores`, `timeout_value`) in `bot.py` and `sfbuff_integration.py`.
- Keep parser tokens and alias keys lowercase, per `AGENTS.md` and usage in alias/normalization logic in `bot.py`.

**Types:**
- Use `PascalCase` for classes (`SimpleTableParser`) in `sfbuff_integration.py`.
- Keep constants in `UPPER_SNAKE_CASE` (`TOKEN`, `GEMINI_MODEL`, `TZ_ALIASES`, `RANGE_MISSING_PLACEHOLDERS`) in `bot.py`.

## Code Style

**Formatting:**
- Tool used: Not detected (no `black`, `ruff format`, `yapf`, or formatter config files in repository root).
- Key settings: Follow 4-space indentation and existing quote/line-break style documented in `AGENTS.md`; this matches the current style in `bot.py`, `sfbuff_integration.py`, and `lltest.py`.

**Linting:**
- Tool used: Not detected (no `flake8`, `ruff`, `pylint`, ESLint, or Biome config files detected).
- Key rules: Enforce style through repository guidance in `AGENTS.md` (import grouping, naming, minimal diffs, and explicit imports).

## Import Organization

**Order:**
1. Standard library imports first (`os`, `asyncio`, `datetime`, `re`) in `bot.py` and `sfbuff_integration.py`.
2. Third-party imports second (`discord`, `aiohttp`, `pandas`, `dotenv`) in `bot.py` and `sfbuff_integration.py`.
3. Local modules last (`import sfbuff_integration`) in `bot.py`.

**Path Aliases:**
- Not used; imports are direct module/file imports from repository root (`import sfbuff_integration` in `bot.py`).

## Error Handling

**Patterns:**
- Wrap external I/O and network calls in `try/except` with bounded fallbacks (`get_openrouter_response`, `get_gemini_response`, `handle_cfn_site_command`, `send_video_with_encouragement`) in `bot.py`.
- Return structured error payloads for integration requests (`{"_error": True, "status": ..., "body": ...}`) in `sfbuff_integration.py`.
- Use targeted exception types when practical (`except aiohttp.ClientError as exc`, `except (TypeError, ValueError)`) in `sfbuff_integration.py` and `bot.py`.
- Use deleted-message fallback handling via `is_deleted_message_reference_error` before retrying with `channel.send(...)` in `bot.py`.

## Logging

**Framework:** console (`print`)

**Patterns:**
- Use contextual log prefixes for subsystems (`[daily-message]`, `[encouragement]`, `[quiz]`, `[scheduler]`) in `bot.py`.
- Use `flush=True` for long-running async loops and scheduled tasks to preserve log ordering (`reminder_loop`, scheduler tasks) in `bot.py`.
- Keep operational logs short and stateful (slot counts, next run timestamps, failure reason) in `bot.py`.

## Comments

**When to Comment:**
- Use short section comments to mark control-flow boundaries in large handlers (`# Quiz flow`, `# start worker`, `# load frame data`) in `bot.py`.
- Prefer small intent comments over algorithm narration in parsing helpers and worker/scheduler sections in `bot.py`.

**JSDoc/TSDoc:**
- Not applicable (Python codebase).
- Python docstrings are used for many helper functions and quiz utilities (`build_quiz_question_text`, `build_quiz_frame_embed`, `pick_quiz_move`) in `bot.py`.

## Function Design

**Size:**
- Use small single-purpose helpers for parsing/formatting and validation (`format_score`, `parse_timezone`, `parse_ratio`) in `bot.py` and `sfbuff_integration.py`.
- Keep orchestration concentrated in event-driven async entry points (`on_message`, `worker`, scheduler loops) in `bot.py`.

**Parameters:**
- Pass raw Discord objects (`message`, `channel`) through flow handlers, and normalize text early (`content_raw`, `content_lower`) in `bot.py`.
- Use explicit optional parameters for behavior switches (`enable_search=False`, `allow_missing_tz=False`, `limit=...`) in `bot.py` and `sfbuff_integration.py`.

**Return Values:**
- Return dictionaries for parser and command payloads (`find_moves_in_text`, CFN results, reminder parse tuple-like payload) in `bot.py`.
- Return `None`/empty collections for no-match scenarios instead of raising (`lookup_frame_data`, `lookup_hitbox_gif_links_from_query`) in `bot.py`.

## Module Design

**Exports:**
- Use direct module-level function access; no explicit `__all__` export lists in `bot.py`, `sfbuff_integration.py`, or `lltest.py`.
- Keep runtime entrypoint guarded by `if __name__ == "__main__":` in `bot.py` and `lltest.py`.

**Barrel Files:**
- Not used in this repository.

---

*Convention analysis: 2026-02-23*

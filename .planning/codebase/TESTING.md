# Testing Patterns

**Analysis Date:** 2026-02-23

## Test Framework

**Runner:**
- Framework: Not detected (`pytest`, `unittest` suites, and JS test runners are not present in repository).
- Config: Not detected (no `pytest.ini`, `tox.ini`, `setup.cfg`, `jest.config.*`, or `vitest.config.*` files in repository root).

**Assertion Library:**
- Not detected; validation is command-output based and manual expectation checks defined in `AGENTS.md`.

**Run Commands:**
```bash
python -m py_compile bot.py                            # Run syntax validation for primary runtime file
python -m py_compile sfbuff_integration.py             # Run syntax validation for CFN integration module
".venv\Scripts\python.exe" -c "import bot; bot.load_frame_data(); print('chars',len(bot.FRAME_DATA))"  # Runtime smoke check
```

## Test File Organization

**Location:**
- Separate test modules are not used; validation commands are documented in `AGENTS.md` and executed from repository root against `bot.py` and `sfbuff_integration.py`.

**Naming:**
- `*.test.*` / `*.spec.*` files are not used.
- Regression checks are named by scenario headings in `AGENTS.md` (for example: teleport precedence, reminder parser, scheduler payload).

**Structure:**
```
Repository root command-driven checks
├── AGENTS.md                      # Canonical regression matrix and manual E2E scripts
├── bot.py                         # Primary module imported by smoke/regression commands
├── sfbuff_integration.py          # Integration module validated via command paths
└── lltest.py                      # Utility script with its own direct runtime path
```

## Test Structure

**Suite Organization:**
```python
# Pattern used in AGENTS.md command checks
import bot

bot.load_frame_data()
tests = ['akuma teleport framedata', 'akuma teleport gif']
for t in tests:
    p = bot.find_moves_in_text(t.lower())
    rows = p.get('rows', [])
    links = bot.collect_hitbox_gif_links_from_text(t.lower(), frame_rows=rows, limit=1)
    print('rows', [(r.get('moveName'), r.get('numCmd')) for r in rows])
    print('gif', links[0] if links else None, 'missing', p.get('missing_scrolls_query'))
```

**Patterns:**
- Setup pattern: Import runtime module and call `bot.load_frame_data()` before behavior checks.
- Teardown pattern: Not required for command-driven checks (process exits after command completion).
- Assertion pattern: Compare printed values against explicit expectations documented in `AGENTS.md`.

## Mocking

**Framework:** Not used

**Patterns:**
```python
# Lightweight inline stand-in object pattern from AGENTS.md checks
intro = asyncio.run(
    bot.build_quiz_persona_intro(
        type('C', (), {'guild': None})(),
        1,
        1,
    )
)
```

**What to Mock:**
- Use lightweight inline stand-ins only when a function requires a minimal shape (for example a context object with `guild`) in command checks.

**What NOT to Mock:**
- Do not mock frame data loading for parser/regression checks; use `FAT - SF6 Frame Data.ods` via `bot.load_frame_data()` to preserve production behavior.

## Fixtures and Factories

**Test Data:**
```python
import bot

bot.load_frame_data()
row = bot.lookup_frame_data('ryu', '5lp')
quiz = {
    'char_key': 'ryu',
    'numcmd': str(row.get('numCmd', '')).strip().lower(),
    'row': row,
}
print(bot.check_quiz_answer(quiz, 'ryu 5lp'))
```

**Location:**
- Fixtures are runtime data structures loaded from ODS and globals inside `bot.py` (`FRAME_DATA`, `FRAME_STATS`, `HITBOX_GIF_DATA`, `RANGE_DATA`).

## Coverage

**Requirements:** None enforced

**View Coverage:**
```bash
Not applicable (coverage tooling not configured)
```

## Test Types

**Unit Tests:**
- Unit-style checks are executed as targeted single commands that call focused functions (`lookup_frame_data`, `parse_timezone`, quiz helpers) from `bot.py`.

**Integration Tests:**
- Integration checks validate module interaction and external behavior through command workflows (parser + gif resolution + scheduler payload + reminder parsing) in `AGENTS.md`.

**E2E Tests:**
- Manual Discord E2E flows are required for routing-sensitive changes (`on_message`, quiz flow, mention/reply behavior, CFN commands) and are documented in `AGENTS.md`.

## Common Patterns

**Async Testing:**
```python
import asyncio
import bot

bot.load_frame_data()
response = asyncio.run(bot.time_handler(None))
print(response.text)
```

**Error Testing:**
```python
import bot

task, dt_local, dt_utc, tz_label, error, pending = bot.parse_reminder_request(
    'remind me at 2pm',
    allow_missing_tz=True,
)
print('error', error, 'pending', pending)
```

---

*Testing analysis: 2026-02-23*

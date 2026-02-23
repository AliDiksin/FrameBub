# Codebase Structure

**Analysis Date:** 2026-02-23

## Directory Layout

```text
[project-root]/
├── .planning/               # Planning artifacts and generated codebase maps
│   └── codebase/            # ARCHITECTURE.md/STRUCTURE.md and companion docs
├── .vscode/                 # Local VS Code workspace settings
├── .zed/                    # Local Zed editor task config
├── __pycache__/             # Python bytecode cache
├── bot.py                   # Main runtime: Discord events, parser, scheduler, quiz, reminders, web endpoint
├── sfbuff_integration.py    # CFN/SFBuff integration adapter and HTML parsing helpers
├── lltest.py                # One-off scraper utility that generates `sf6_move_data.csv`
├── requirements.txt         # Python dependency manifest
├── FAT - SF6 Frame Data.ods # Authoritative frame/combos/oki/source dataset
└── *.ps1                    # Deployment/setup helper scripts
```

## Directory Purposes

**Project Root (`.`):**
- Purpose: Hold executable runtime modules, source data file, deployment scripts, and service config.
- Contains: `bot.py`, `sfbuff_integration.py`, `lltest.py`, `requirements.txt`, `FAT - SF6 Frame Data.ods`, `bub.service`.
- Key files: `bot.py`, `sfbuff_integration.py`, `requirements.txt`.

**Planning Docs (`.planning/codebase/`):**
- Purpose: Store architecture/stack/conventions/testing/concerns maps consumed by orchestration commands.
- Contains: Generated markdown reference docs such as `ARCHITECTURE.md` and `STRUCTURE.md`.
- Key files: `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/STRUCTURE.md`.

**Editor Metadata (`.vscode/`, `.zed/`, `.claude/`):**
- Purpose: Local tool/editor settings, not runtime business logic.
- Contains: `.vscode/settings.json`, `.vscode/launch.json`, `.zed/tasks.json`, `.claude/settings.local.json`.
- Key files: `.vscode/settings.json`, `.zed/tasks.json`.

## Key File Locations

**Entry Points:**
- `bot.py`: Process entry (`if __name__ == "__main__"`), Discord events (`on_ready`, `on_message`), and app lifecycle.

**Configuration:**
- `requirements.txt`: Dependency declarations used for environment setup.
- `bub.service`: Systemd runtime configuration for Linux deployment.
- `quick_deploy.ps1`: Fast upload/restart script for `bot.py` + `sfbuff_integration.py`.

**Core Logic:**
- `bot.py`: Domain parser (`find_moves_in_text`), move lookup (`lookup_frame_data`), quiz/reminder flows, scheduling, LLM queue.
- `sfbuff_integration.py`: CFN network calls and HTML/table parsing for rivals/matchups/history/matches.

**Testing:**
- Not detected as a dedicated directory or framework configuration in this repository root.
- Runtime verification currently relies on direct Python commands and manual Discord checks documented in `AGENTS.md`.

## Naming Conventions

**Files:**
- Runtime modules use lowercase snake_case filenames: `bot.py`, `sfbuff_integration.py`.
- Utility and deployment scripts use descriptive snake_case names: `deploy_to_linode.ps1`, `setup_sfbuff_api.ps1`.
- Data and docs use descriptive names with spaces only for source artifacts: `FAT - SF6 Frame Data.ods`.

**Directories:**
- Operational directories use dot-prefix for tooling/config scopes: `.planning/`, `.vscode/`, `.zed/`, `.claude/`.
- Generated runtime cache directories use conventional Python naming: `__pycache__/`.

## Where to Add New Code

**New Feature:**
- Primary code: Add feature logic in `bot.py` near the related routing section (`on_message` for command routing, helper region for pure functions).
- Tests: Add a new `tests/` directory at repo root and place feature tests there; no test directory is currently present.

**New Component/Module:**
- Implementation: Add a new top-level module (for example `xyz_integration.py`) beside `sfbuff_integration.py` when the feature is an external adapter.

**Utilities:**
- Shared helpers: Place generally reusable parsing/formatting helpers in dedicated top-level modules and keep `bot.py` focused on orchestration.

## Special Directories

**`.venv/`:**
- Purpose: Local virtual environment for Python dependencies.
- Generated: Yes
- Committed: No (`.gitignore`)

**`__pycache__/`:**
- Purpose: Python bytecode cache generated during execution/compilation.
- Generated: Yes
- Committed: No (`.gitignore`)

**`.planning/codebase/`:**
- Purpose: Generated architecture/planning reference docs for GSD workflows.
- Generated: Yes
- Committed: Yes (not excluded in `.gitignore`)

---

*Structure analysis: 2026-02-23*

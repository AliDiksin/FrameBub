# FrameBub

FrameBub is a Discord bot for natural-language frame-data lookups, hitbox media, combos, quizzes, menus, reminders, and optional private LLM/voice features.

## Supported Games

- Street Fighter 6
- Street Fighter V
- Guilty Gear Strive
- Guilty Gear Accent Core Plus R
- 2XKO
- BlazBlue Central Fiction
- Fatal Fury: City of the Wolves
- Street Fighter III: Third Strike
- Mortal Kombat 1

Shared Guilty Gear characters default to Strive. Explicit +R tags and +R-exclusive characters select Accent Core.

## Architecture

- `bot.py`: compatibility launcher.
- `bubbot/runtime/`: Discord client, startup, message routing, slash commands, static assets, and optional private orchestration.
- `bubbot/frame_data/`: per-game loaders, parsers, matching, embeds, media, stats, and combos.
- `bubbot/features/`: menus, quiz, reminders, glossary, reports, optional LLM, and voice.
- `bubbot/data/`: aliases, source metadata, glossary data, and generated image caches.
- `bubbot/utils/`: shared matching, formatting, source attribution, logging, and slash helpers.
- `scripts/`: data maintenance, local wiki export, and deployment operations.

Frame-data workbooks and `mk1/*.json` are resolved from the current working directory. Run commands from the repository root.

## Local Setup

In the OpenCode environment, bootstrap with the container Python rather than PATH's host Python:

```sh
/usr/bin/python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

On Linux, `openwakeword` may need `--no-deps` when `tflite-runtime` has no compatible wheel.

## Verification

There is no configured test, lint, formatter, or typecheck suite. The focused wiring check is:

```sh
.venv/bin/python -c 'import bot; assert bot.client and bot.tree and callable(bot.main)'
```

This imports configuration but does not call `client.run`. Do not use `python bot.py` as a smoke test; it connects to Discord, synchronizes commands, starts background services, and writes runtime state.

## Live Deployment

The live service runs on Fedora from `/var/lib/bub`. Deploy verified code with:

```sh
scripts/deploy_live.sh
```

The script stages and import-checks code, protects live secrets/state/workbooks, backs up replaced files, and restarts only after a real deployable change. Useful options:

```sh
scripts/deploy_live.sh --dry-run
scripts/deploy_live.sh --no-restart
scripts/deploy_live.sh --include-workbooks
```

Workbook deployment is opt-in because the live SF6 workbook is managed by `/etc/cron.d/bub-sf6-sync`.

## LLM Wiki

Refresh the sanitized source mirror after code changes:

```sh
/usr/bin/python3.13 scripts/sync_llm_wiki_sources.py
```

The mirror excludes credentials, logs, runtime state, workbooks, media, caches, and generated move-image tables.

See `AGENTS.md` for live safety and workflow details.

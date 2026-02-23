# Technology Stack

**Analysis Date:** 2026-02-23

## Languages

**Primary:**
- Python 3.x - Core runtime and all production bot logic in `bot.py` and `sfbuff_integration.py`

**Secondary:**
- PowerShell - Deployment and server setup automation in `quick_deploy.ps1`, `deploy_to_linode.ps1`, and `setup_sfbuff_api.ps1`
- Markdown - Operational and agent guidance in `AGENTS.md` and `CLAUDE.md`

## Runtime

**Environment:**
- CPython 3 (`/usr/bin/python3`) - Production service runtime in `bub.service`
- Local virtualenv workflow (`.venv`) - Developer environment documented in `AGENTS.md` and `CLAUDE.md`

**Package Manager:**
- pip - Dependency installation flow in `AGENTS.md` and `CLAUDE.md`
- Lockfile: missing (`requirements.txt` exists, no lock file detected)

## Frameworks

**Core:**
- `discord.py` - Discord bot client and event handling in `bot.py`
- `aiohttp` - Async HTTP client calls and embedded web server in `bot.py` and `sfbuff_integration.py`
- `pandas` + ODF engine (`odfpy`) - ODS ingestion and tabular transformation in `bot.py`
- `python-dotenv` - Environment variable loading at startup in `bot.py`

**Testing:**
- Not detected - No formal Python test framework config files detected in repository root

**Build/Dev:**
- `py_compile` syntax checks - Validation workflow in `AGENTS.md`
- `systemd` service management - Runtime process control in `bub.service`

## Key Dependencies

**Critical:**
- `discord.py` - Required for bot connectivity and command handling in `bot.py`
- `aiohttp` - Required for outbound LLM/API calls and internal HTTP endpoint in `bot.py`
- `pandas` - Required for loading frame data from `FAT - SF6 Frame Data.ods` in `bot.py`
- `odfpy` - Required by pandas ODS parsing (`engine='odf'`) in `bot.py`

**Infrastructure:**
- `python-dotenv` - Loads environment variables from `.env` at startup in `bot.py`
- `openpyxl` - Present in `requirements.txt`; not detected in runtime imports in `bot.py` or `sfbuff_integration.py`

## Configuration

**Environment:**
- Config is env-var driven via `.env` (file present; contents intentionally not read)
- Required vars are `DISCORD_TOKEN` and `CHANNEL_ID` in `bot.py` and documented in `AGENTS.md`
- Optional LLM vars are read in `bot.py` (`OPENROUTER_*`, `GEMINI_*`, `LLM_CONTEXT_*`, media/reminder/scheduler settings)
- Optional SFBuff vars are read in `sfbuff_integration.py` (`SFBUFF_SITE_BASE_URL`, `SFBUFF_API_BASE_URL`, `SFBUFF_SITE_USER_AGENT`, `SFBUFF_API_TIMEOUT`)

**Build:**
- Dependency manifest: `requirements.txt`
- Runtime service config: `bub.service`
- Deployment scripts: `quick_deploy.ps1` and `deploy_to_linode.ps1`

## Platform Requirements

**Development:**
- Python 3 + pip + venv for local setup (`AGENTS.md`, `CLAUDE.md`)
- ODS data file must exist at repo root as `FAT - SF6 Frame Data.ods` for startup data load in `bot.py`

**Production:**
- Linux host with `systemd` and outbound network access (`bub.service`)
- Current deployment target is a Linode VM accessed by SSH/SCP in `quick_deploy.ps1` and `deploy_to_linode.ps1`

---

*Stack analysis: 2026-02-23*

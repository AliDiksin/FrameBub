# External Integrations

**Analysis Date:** 2026-02-23

## APIs & External Services

**Chat Platforms:**
- Discord API - Bot messaging, mentions, replies, embeds, attachments, and channel operations
  - SDK/Client: `discord.py` in `bot.py`
  - Auth: `DISCORD_TOKEN` (loaded in `bot.py`)

**LLM Providers:**
- OpenRouter Chat Completions API (`https://openrouter.ai/api/v1/chat/completions`) - Optional text generation provider
  - SDK/Client: `aiohttp.ClientSession` in `bot.py`
  - Auth: `OPENROUTER_API_KEY` in `bot.py`
- Google Gemini GenerateContent API (`https://generativelanguage.googleapis.com/v1beta`) - Primary optional LLM and multimodal provider
  - SDK/Client: `aiohttp.ClientSession` in `bot.py`
  - Auth: `GEMINI_API_KEY` in `bot.py`

**Fighting Data Services:**
- SFBuff website/API endpoints (`/fighters/search`, `/fighter_searches/{uuid}`, `/fighters/{id}/...`) - CFN search, sync, rivals, matchup, history, and matches
  - SDK/Client: custom `aiohttp` client wrapper in `sfbuff_integration.py`
  - Auth: Env-based base URL and timeout config (`SFBUFF_SITE_BASE_URL`, `SFBUFF_API_BASE_URL`, `SFBUFF_SITE_USER_AGENT`, `SFBUFF_API_TIMEOUT`) in `sfbuff_integration.py`
- SF6Frames pages (`https://sf6frames.com/...`) - One-off scraper source for move links
  - SDK/Client: `httpx` + `BeautifulSoup` in `lltest.py`
  - Auth: Not applicable

## Data Storage

**Databases:**
- Not detected for production bot runtime (`bot.py` and `sfbuff_integration.py` maintain in-memory structures)
  - Connection: Not applicable
  - Client: Not applicable

**File Storage:**
- Local filesystem data source via `FAT - SF6 Frame Data.ods` loaded in `bot.py`

**Caching:**
- In-process memory caches and globals (`FRAME_DATA`, `FRAME_STATS`, `RANGE_DATA`, quiz caches) in `bot.py`

## Authentication & Identity

**Auth Provider:**
- Discord bot token auth for platform identity in `bot.py`
  - Implementation: `load_dotenv()` + `os.getenv('DISCORD_TOKEN')` + `discord.Client(...)`
- API key auth for LLM providers in `bot.py`
  - Implementation: bearer header for OpenRouter and query-string key for Gemini

## Monitoring & Observability

**Error Tracking:**
- None detected (no Sentry/Rollbar/New Relic SDK imports in `bot.py` or `sfbuff_integration.py`)

**Logs:**
- Console logging via `print(..., flush=True)` in `bot.py` and exception-to-payload mapping in `sfbuff_integration.py`

## CI/CD & Deployment

**Hosting:**
- Linux VM deployment managed by `systemd` unit `bub.service` (working directory `/root/bub`)
- Target host is Linode-based SSH deployment in `quick_deploy.ps1` and `deploy_to_linode.ps1`

**CI Pipeline:**
- None detected (no `.github/workflows/*` or other CI config files)

## Environment Configuration

**Required env vars:**
- `DISCORD_TOKEN`, `CHANNEL_ID` in `bot.py`
- Core optional integration vars in `bot.py`: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_BASE_URL`
- Core optional SFBuff vars in `sfbuff_integration.py`: `SFBUFF_SITE_BASE_URL`, `SFBUFF_API_BASE_URL`, `SFBUFF_SITE_USER_AGENT`, `SFBUFF_API_TIMEOUT`

**Secrets location:**
- Local runtime: `.env` in repository root (present; contents intentionally not read)
- Production runtime: `EnvironmentFile=/root/bub/.env` in `bub.service`

## Webhooks & Callbacks

**Incoming:**
- Internal HTTP callback/inspection endpoint: `GET /time` served on port `8080` in `bot.py`
- No external webhook receiver routes detected beyond `/time` in `bot.py`

**Outgoing:**
- Outbound HTTPS requests to OpenRouter, Gemini, and SFBuff from `bot.py` and `sfbuff_integration.py`
- Outbound media fetches for attachment/embed processing via URL GET in `bot.py`

---

*Integration audit: 2026-02-23*

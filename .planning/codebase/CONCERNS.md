# Codebase Concerns

**Analysis Date:** 2026-02-23

## Tech Debt

**Monolithic runtime in one file:**
- Issue: `bot.py` centralizes Discord routing, parsing, scheduling, reminders, quiz state, LLM calls, and web server concerns in a single ~9k-line module.
- Files: `bot.py`
- Impact: High change coupling increases regression risk; small edits in one subsystem can unintentionally affect unrelated flows.
- Fix approach: Split `bot.py` into focused modules (`handlers`, `parsers`, `quiz`, `scheduling`, `llm`, `integrations`) and keep `on_message` as a thin orchestrator.

**Global mutable process state:**
- Issue: Core runtime state is stored in module globals (`REMINDERS`, `PENDING_REMINDERS`, `ACTIVE_QUIZZES`, `SPECIAL_STRENGTH_PROMPT_MODE`, and data maps).
- Files: `bot.py:103`, `bot.py:104`, `bot.py:6032`, `bot.py:6035`, `bot.py:941`
- Impact: State behavior is hard to reason about under long uptime and impossible to share across processes/instances.
- Fix approach: Encapsulate state in dedicated services with clear mutation APIs and add durable backing for user-impacting state.

**Unpinned dependency surface:**
- Issue: Runtime dependencies are version-unpinned.
- Files: `requirements.txt`
- Impact: Fresh installs can pull incompatible versions, causing nondeterministic runtime behavior.
- Fix approach: Pin exact versions (or at least bounded ranges) and commit a reproducible lock strategy.

## Known Bugs

**Scheduled video link expiry risk:**
- Symptoms: Daily video post can fail or send a dead link when CDN query parameters expire.
- Files: `bot.py:63`, `bot.py:5812`
- Trigger: Scheduled `send_video_with_encouragement()` runs after URL expiry window.
- Workaround: Replace the hardcoded URL manually in `bot.py` with a currently valid asset URL.

**Reminder persistence gap across restarts:**
- Symptoms: Active and pending reminders disappear after process restart.
- Files: `bot.py:103`, `bot.py:104`, `bot.py:5636`, `bot.py:8195`, `bot.py:8212`
- Trigger: Bot restart/crash before due reminder time.
- Workaround: Re-create reminders after restart; no automatic recovery is implemented.

## Security Considerations

**Plaintext secrets and credentials in deployment automation:**
- Risk: Sensitive values are embedded directly in setup automation and can be leaked through source control or logs.
- Files: `setup_sfbuff_api.ps1`, `deploy_to_linode.ps1`, `quick_deploy.ps1`
- Current mitigation: `.env` support exists in runtime (`bot.py:18`) and `.env` file is present (`.env`), but deployment scripts still contain hardcoded credential material.
- Recommendations: Remove embedded secrets from scripts, rotate exposed credentials, and load all secrets from secured environment stores.

**Root execution in production service definitions:**
- Risk: Compromise impact is full-host because services run as `root`.
- Files: `bub.service:7`, `deploy_to_linode.ps1:32`, `setup_sfbuff_api.ps1:148`, `setup_sfbuff_api.ps1:166`
- Current mitigation: Not detected in service hardening config.
- Recommendations: Run under a dedicated least-privilege user and add systemd hardening (`NoNewPrivileges`, `ProtectSystem`, `PrivateTmp`, limited write paths).

**Externally exposed status endpoint without access control:**
- Risk: `0.0.0.0:8080` endpoint discloses internal scheduler timing metadata.
- Files: `bot.py:6002`, `bot.py:6017`
- Current mitigation: Not detected in application-level auth controls.
- Recommendations: Bind to localhost behind reverse proxy auth, or gate endpoint with shared secret/token.

## Performance Bottlenecks

**Startup-heavy ODS parsing path:**
- Problem: Multiple full-sheet `pandas` reads are performed at startup across all sheet categories.
- Files: `bot.py:1010`, `bot.py:1032`, `bot.py:1046`, `bot.py:1112`, `bot.py:1153`, `bot.py:1185`, `bot.py:1196`, `bot.py:1213`
- Cause: Repeated workbook sheet scans and DataFrame materialization in a monolithic load pass.
- Improvement path: Cache preprocessed artifacts (JSON/CSV snapshots) and only rebuild from ODS when source checksum changes.

**Single-worker LLM response serialization:**
- Problem: All LLM responses are serialized through one queue worker.
- Files: `bot.py:7695`, `bot.py:7797`, `bot.py:9028`
- Cause: Single `worker()` loop consumes an unbounded `asyncio.Queue()`.
- Improvement path: Add bounded queue + backpressure and configurable worker concurrency with provider rate limiting.

**LLM and media HTTP calls without explicit request timeouts:**
- Problem: Provider and media-fetch calls can hang longer than expected under network degradation.
- Files: `bot.py:261`, `bot.py:402`, `bot.py:564`
- Cause: `aiohttp.ClientSession()` is used without explicit `ClientTimeout` in these paths.
- Improvement path: Standardize timeout/retry policy for all outbound requests.

## Fragile Areas

**Regex-driven parser and routing complexity:**
- Files: `bot.py:1231`, `bot.py:7829`
- Why fragile: Parser intent extraction and message routing combine many regex gates and branch conditions; edge cases can shift behavior unexpectedly.
- Safe modification: Add behavior-specific helper functions and targeted regression commands before/after every parser edit.
- Test coverage: No automated parser suite detected; verification currently relies on manual command matrix.

**HTML structure-coupled SFBuff scraping:**
- Files: `sfbuff_integration.py:25`, `sfbuff_integration.py:132`, `sfbuff_integration.py:165`, `sfbuff_integration.py:200`, `sfbuff_integration.py:231`
- Why fragile: Parsing depends on exact HTML table layout/captions and positional columns.
- Safe modification: Centralize schema validation per endpoint and fail loudly on shape mismatch.
- Test coverage: No contract tests detected for fixture HTML samples.

**Silent exception swallowing in media/reply flows:**
- Files: `bot.py:352`, `bot.py:353`, `bot.py:383`, `bot.py:384`, `bot.py:8665`, `bot.py:8666`
- Why fragile: Broad `except` + `pass` blocks hide operational failures and remove debugging context.
- Safe modification: Replace silent `pass` with structured logs including operation context.
- Test coverage: No automated assertions for failure-path observability detected.

## Scaling Limits

**Single-process in-memory architecture:**
- Current capacity: One Python process with in-memory state and one LLM worker.
- Limit: Horizontal scaling causes state divergence (quiz/reminder/prompt mode not shared), and queue latency grows under burst traffic.
- Scaling path: Externalize shared state (Redis/DB), introduce idempotent schedulers, and scale worker pool with centralized rate limiting.

**Scheduler fan-out in one runtime loop set:**
- Current capacity: Four perpetual scheduler loops + reminder loop in the same process.
- Limit: Loop stalls or provider latency can degrade timing accuracy for all scheduled features.
- Scaling path: Move scheduled jobs to a dedicated scheduler/worker service or durable job queue.

## Dependencies at Risk

**Third-party website dependency for CFN data:**
- Risk: Integration relies on scraping `sfbuff.site` HTML/turbo-stream behavior instead of a stable versioned API contract.
- Impact: Upstream markup changes can silently break search/rivals/matchup/history output.
- Migration plan: Prefer authenticated JSON API endpoints with schema versioning; keep scraper as fallback only.

**Broad dependency ranges in runtime libs:**
- Risk: Future upstream releases may introduce breaking changes.
- Impact: New environments can fail at import/runtime despite unchanged application code.
- Migration plan: Pin versions in `requirements.txt` and run periodic controlled upgrade windows.

## Missing Critical Features

**Durable reminder and quiz session storage:**
- Problem: User-facing state is not persisted.
- Blocks: Reliable reminder delivery after restart and resilient quiz continuity across deployments.

**Structured observability stack:**
- Problem: Logging is print-based with inconsistent metadata.
- Blocks: Fast root-cause analysis for production incidents and reliable alerting.

## Test Coverage Gaps

**No automated test suite in repository:**
- What's not tested: Parser branches, reminder scheduling, quiz lifecycle, LLM queue behavior, and integration parsing are not covered by executable tests.
- Files: `bot.py`, `sfbuff_integration.py`, `requirements.txt`
- Risk: Regressions are discovered post-deploy through manual checks.
- Priority: High

**No scraper contract fixtures:**
- What's not tested: HTML table parsing assumptions for search/rivals/matchup/matches/history endpoints.
- Files: `sfbuff_integration.py`
- Risk: Upstream HTML shifts break features silently or degrade output quality.
- Priority: High

---

*Concerns audit: 2026-02-23*

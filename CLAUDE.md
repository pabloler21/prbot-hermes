# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Operations repo (`team-agent-ops`) for **deploying and configuring Hermes Agent (Nous Research)** on an Ubuntu VPS, wiring it to GitHub (via MCP) and Discord, running durable work through **arq + Redis**, and **migrating an existing n8n bot** onto it before retiring n8n.

This is a **portfolio/demo project**: the author must be able to explain and defend every part in interviews, and **the author's stack is Python** — a binding constraint that shapes technical decisions (see ADR-0006). Prefer Python + tools the author can defend; don't introduce a stack they can't explain.

Hermes is operated as a dependency — **do not fork it**. What gets versioned here is the configuration, the business guardrails, and the arq queues/workers. `plan-1-agente-hermes.md` is the authoritative, phase-by-phase execution plan. Read it before acting.

## Current state (updated 2026-06-22)

- **Phase 0 (bootstrap):** ✅ merged to `main`.
- **Phase 1 (Hermes live on Discord):** ✅ merged to `main`.
- **Phase 2 (n8n inventory + migration map):** ✅ merged to `main`. Inventory is *invented* (realistic team workflows) — the author has no real n8n access; we build the migration as if real for a portfolio/demo. See `docs/n8n-inventory.md`.
- **Phase 3 (GitHub MVP: read MCP + approval-gated write path):** ✅ **COMPLETE, validated end-to-end on the VPS, merged to `main`** (PR #1). 3a = GitHub MCP read-only; 3b = the Python/arq write path with approval gate. Validated flow: user (DM) → Hermes → MCP tool `propose_pr_comment` → pending → Discord approval bot (✅/❌) → arq worker posts the comment to GitHub. Allowlist rejection, idempotency, and error handling confirmed live.
- **Phase 4 (next):** harden the durable queue as a production service. Per the plan this is **NOT** the n8n migration (that's Phase 6). Most of it was already built in 3b (Redis secured + worker/bot as systemd services with retries/backoff). Genuinely remaining: **dead-letter** for jobs that exhaust retries (arq has no native DLQ — we build it), **concurrency cap** (`max_jobs`) as rate-limiting, a formal **reboot-survival** test of the new services, and queue **observability/runbook**. Later: Phase 5 = issue triage + doc reading; Phase 6 = daily digest (`cron_jobs`) + n8n parity; Phase 7 = cutover.

**Known minor follow-up (non-blocking):** Hermes currently replies only in DM, not in the server channel (home-channel quirk — see `DISCORD_HOME_CHANNEL`).

**VPS:** Oracle Cloud Always Free, VM.Standard.E2.1.Micro (AMD x86, **1GB RAM** — resource-constrained, factor into every choice), Ubuntu 22.04, IP `137.131.202.213`. Connect: `ssh ubuntu@137.131.202.213`. Operator cheatsheet: `CHEATSHEET.md` (gitignored, personal).

**Demo thesis:** Hermes on Discord answers the team's questions about code/PRs/CI-failures (reads GitHub via MCP); arq+Redis runs recurring work and approval-gated GitHub writes (digests, alerts, comments), replacing n8n.

## Operating rules (from the plan — binding)

- **One phase at a time.** Don't advance past a phase without satisfying its validation checklist.
- **On closing each phase:** update `HANDOFF.md` and add/confirm an `ADR-XXXX` under `docs/adr/`. Merge to `main` only when the checklist is complete.
- **MANUAL STEPS (`PASOS MANUALES`) are done by the human, not by Claude Code.** Leave them clearly indicated and wait. These cover: provisioning the VPS, installing Hermes, creating Discord bots/tokens, generating/scoping the GitHub PAT, installing Redis (done), and decommissioning n8n.
- **If a fact is missing, assume the reasonable default and record the assumption in an ADR.** Don't stop to ask.
- **Secrets** live only in `~/.hermes/.env` (or the service environment), `chmod 600`. Never hardcoded, never committed. `deploy/.env.example` lists variable names with no values.

## Language & commit conventions

- **Code in English. Comments and docstrings in Spanish. Commit messages in English**, Conventional Commits.
- Python tooling: **uv** + **Ruff**. Lint with `uv run ruff check`; **also** `uv run ruff format` before pushing (CI runs `ruff format --check` separately — see lessons). Add deps with `uv add <pkg>` (pins the current version — never hand-write versions from memory).

## Branching

- `main` reflects the deployed configuration (now includes Phase 3).
- One **feature branch per phase**: `feat/fX-nombre`. Merge to `main` only when the checklist is complete. Every merge updates `HANDOFF.md` + ADR(s).

## Architecture (how the pieces fit)

- **Hermes Agent** = the brain. Receives Discord messages, reasons, decides, has tools (GitHub MCP read-only, the custom `hermes-queue` MCP, docs reading). Runs 24/7 as a headless gateway (systemd, non-root).
- **arq (Redis)** = the durable execution layer. Work that acts on GitHub or is recurring/critical is enqueued as an arq job. The worker consumes it with retries, exponential backoff, and idempotency (job uniqueness via custom `_job_id`), so work survives reboots, isn't duplicated, and is retried on transient failures.
- **Core pattern:** Hermes decides and **enqueues** → an **arq worker** executes (post the approved comment, build the digest) → result is logged and reported back to Discord.
- **Single scheduling mechanism:** recurring work uses **arq `cron_jobs`**, not a second cron. Avoid running Hermes-native cron and arq cron in parallel; document any exception in an ADR.

### Two guardrails that are easy to get wrong

- **Approval gate is orchestration-level, NOT Hermes-native.** Hermes' native `approvals.mode` only covers dangerous shell commands — NOT an MCP action like "post a GitHub comment." So visible actions are held **pending-approval** (Enfoque B: a Redis key `pending-approval:<id>`, **not** the arq queue); an allowlisted user approves via the Discord approval bot (✅/❌); only then is the real arq job enqueued. The arq queue therefore *structurally* only ever contains approved work. The approval decision is deterministic (a human clicking a button), never the LLM reading "yes".
- **Repo allowlist is enforced in the worker (deterministic), not in the LLM** (`config/guardrails/repo-allowlist.yaml`).

Defense-in-depth: the GitHub PAT is scoped to read + comment only (no merge/push/force-push). The idempotency key (sha256 of `repo+pr+body`, used as the arq `_job_id`) prevents a 24/7 retrying agent from duplicating actions — arq returns `None` if the id is already queued/running.

## Repo structure

```
docs/adr/          # ADR-0001..0006, one+ per phase
docs/n8n-inventory.md, docs/runbook.md
config/hermes/     # config.yaml: intent/doc artifact only (LIVE config is on the VPS)
config/guardrails/ # repo-allowlist.yaml, publish-approval policy
hermes_queue/      # arq queue layer (Python):
  settings.py        # RedisSettings from REDIS_URL
  jobs/post_comment.py  # data type + idempotency + approval gate (enqueue_pending/approve/reject)
  guardrails.py      # repo allowlist (deterministic)
  github_client.py   # POST a PR comment via GitHub REST API
  events.py          # Redis pub/sub (MCP -> approval bot)
  workers/post_comment_worker.py  # arq worker: allowlist + post + retries
  mcp_server.py      # FastMCP server: tool propose_pr_comment for Hermes
  approval_bot.py    # discord.py bot: ✅/❌ buttons (deterministic gate)
deploy/systemd/    # units: hermes-gateway, hermes-arq-worker, hermes-approval-bot
deploy/.env.example, deploy/install-notes.md
scripts/
```

## Operational facts (deployed system on the VPS)

- **Two Linux users — use the right one.** `hermes` **runs the app** (owns the repo at `/home/hermes/prbot-hermes`, the venv, and `~/.hermes/.env`; has NO sudo). `ubuntu` is for **system admin** (`sudo`, `systemctl`, `journalctl`). If `sudo` asks for a password or you see `/home/ubuntu/...: No such file`, you're on the wrong user — switch with `sudo su - hermes` / `exit`.
- **Services (all run as `hermes`, via systemd):** `hermes-gateway` (Hermes + its MCP servers), `hermes-arq-worker` (post-comment worker), `hermes-approval-bot` (Discord ✅/❌ bot), plus `redis-server`. Worker/bot units call the venv binaries directly (`.venv/bin/arq`, `.venv/bin/python`) — no `uv` needed at runtime.
- **Custom MCP registration:** the `hermes-queue` MCP is registered with `hermes mcp add hermes-queue --command /home/hermes/prbot-hermes/.venv/bin/python --env PYTHONPATH=/home/hermes/prbot-hermes REDIS_URL='${REDIS_URL}' --args -m hermes_queue.mcp_server`. The `PYTHONPATH` env is required so the spawned process finds the `hermes_queue` package (the project is not pip-installed into the venv). `${REDIS_URL}` is resolved by Hermes at runtime from `~/.hermes/.env`.
- **Approval bot** is a **separate Discord application/token** (`DISCORD_APPROVAL_BOT_TOKEN`) — Hermes isn't forked, so custom buttons live in their own bot. It posts in `DISCORD_APPROVAL_CHANNEL_ID`; approvers = `DISCORD_ALLOWED_USERS`. The bot must be **invited to the server** (OAuth2 `bot` scope) — connecting to the gateway ≠ being a server member.

## Decisions already made (do not re-litigate)

- **Worker/queue language:** **Python + arq** (ADR-0006, supersedes ADR-0005). Chosen for defensibility in the author's stack and the 1GB free VPS (arq is async, Redis-native, tiny footprint, with native cron/retries/idempotency; verified vs Celery/RQ/Dramatiq). BullMQ/TypeScript was discarded. The Python package is `hermes_queue` (not `queue`) to avoid shadowing the stdlib `queue` module.
- **LLM:** provider **OpenCode** (user's Go subscription), model **`kimi-k2.7-code`**. Key in `~/.hermes/.env` as **`OPENCODE_GO_API_KEY`** (the real var name on the VPS). OpenRouter was discarded (ADR-0002).

## Confirmed facts about Hermes (do not re-verify)

Confirmed against the docs and **reconciled against the real install on the VPS**:
- Headless VPS install via `curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash`. Binary at `/home/hermes/.hermes/hermes-agent/venv/bin/hermes`.
- **MCP servers are managed via the `hermes mcp` CLI (`add`/`configure`/`list`), NOT a `mcp_servers` block in `config.yaml`.** The GitHub MCP (`@modelcontextprotocol/server-github`) was locked to **14 read-only tools** (12 write tools disabled) so the only publish path is the approval-gated worker. Hermes spawns all registered MCPs as child processes of the gateway.
- The real generated config uses top-level keys `model:`, `discord:`, `approvals:`, `terminal:` (NOT `llm:`/`channels:`). The repo's `config/hermes/config.yaml` is an intent/doc artifact — edit the live `~/.hermes/config.yaml` deltas only, don't overwrite wholesale.
- **Discord:** user allowlist via `DISCORD_ALLOWED_USERS`. Hermes replies in **DMs and its home channel** (set with `/sethome`); after restarts it may revert to DM-only. Privileged Gateway Intents (Presence, Server Members, Message Content) must be enabled manually in the Developer Portal.
- systemd unit needs `TimeoutStopSec>=210` (Hermes `restart_drain_timeout` is 180s; the 90s default SIGKILLs mid-drain).
- `approvals.cron_mode` (deny|approve); sandbox backends `ssh`/`docker`; `approvals.mode` (manual|smart|off) covers dangerous shell commands only (NOT MCP actions).

## Mistakes not to repeat (lessons paid for in this project)

- **Never assert volatile tech facts from training memory — verify first.** Real failures: claimed BullMQ's Python port was "an immature third-party project" (it's official); would have written the GitHub API version, the FastMCP class, and library versions from stale memory. Route verification: **Context7 MCP** for library docs/capabilities/syntax; **web search** for project status, comparisons, pricing, versions. Tag claims ✅ verified (source + date) vs ⚠️ from memory. (Also in the user's global CLAUDE.md.)
- **Define the deciding criterion BEFORE evaluating options.** ADR-0005 picked TypeScript by optimizing "best queue tech," ignoring the criteria that actually bind here — Python-stack defensibility + the 1GB VPS. Surfacing those first (ADR-0006) reversed the decision. Weigh defensibility and resource cost explicitly in every tooling choice.
- **Don't fragment a cohesive subsystem across languages by feature gaps.** Split by service boundary, not by "what library X is missing" (why the Python-producer/TS-worker hybrid was rejected).
- **Don't name a Python package after a stdlib module** (`queue`, `json`, `types`, …) — it shadows the import and breaks deps subtly. Hence `hermes_queue`.
- **Scope the GitHub PAT for the actual ACTION.** A read-only PAT → `403 "Resource not accessible by personal access token"` when posting. Commenting on a PR needs **Pull requests: Read and write** (and Issues: Read and write). Fine-grained tokens can be edited in place (the token value stays the same → no `.env` change).
- **Run app commands as `hermes`, sudo as `ubuntu`.** Wrong user → `/home/ubuntu/...: No such file` or a sudo password prompt (the `hermes` user is `--disabled-password`).
- **`ruff check` (lint) ≠ `ruff format` (style).** CI runs both; run `uv run ruff format` before pushing or the `format --check` job fails even when lint passes.
- **A bot connected to the Discord gateway is not automatically in your server.** Custom bots must be invited via the OAuth2 `bot` scope URL, or they can't post in any channel.
- **The earlier `mcp_servers`-in-`config.yaml` assumption was wrong** (corrected in ADR-0004): MCP is CLI-managed. Don't reintroduce it.

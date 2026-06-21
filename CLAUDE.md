# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Operations repo (`team-agent-ops`) for **deploying and configuring Hermes Agent (Nous Research)** on an Ubuntu VPS, wiring it to GitHub (via MCP) and Discord, running durable work through **arq + Redis**, and **migrating an existing n8n bot** onto it before retiring n8n.

This is a **portfolio/demo project**: the author must be able to explain and defend every part in interviews, and **the author's stack is Python** — this is a binding constraint that shapes technical decisions (see ADR-0006).

Hermes is operated as a dependency — **do not fork it**. What gets versioned here is the configuration, the business guardrails, and the arq queues/workers. `plan-1-agente-hermes.md` is the authoritative, phase-by-phase execution plan. Read it before acting.

## Current state (updated 2026-06-21)

- **Phase 0 (bootstrap):** ✅ complete, merged to `main`.
- **Phase 1 (Hermes live on Discord):** ✅ complete, validated on VPS, merged to `main`.
- **Phase 2 (n8n inventory + migration map):** ✅ complete, merged to `main`. Inventory is *invented* (realistic team workflows) — the author has no real n8n access; we build the migration as if real for a portfolio/demo. See `docs/n8n-inventory.md`.
- **Phase 3a (GitHub MCP, read-only):** ✅ complete, validated. On branch `feat/f3-github-mvp` (NOT yet merged — Phase 3 closes only when 3b is done).
- **Redis (3b prerequisite):** ✅ installed and secured on the VPS (manual step). Bound to `127.0.0.1` + `::1` only (not internet-facing), `requirepass` set, `REDIS_URL` loaded in `~/.hermes/.env` (chmod 600). Verified: `redis-cli -u "$REDIS_URL" ping` → `PONG`.
- **Phase 3b (write path: approval-gated worker):** ⏳ IN PROGRESS, on `feat/f3-github-mvp`. The queue layer is **Python + arq** (ADR-0006, supersedes ADR-0005). Built so far in `hermes_queue/`: Redis settings (`settings.py`), the post-comment data type + idempotency, and the approval gate (`jobs/post_comment.py`: `enqueue_pending`/`approve`/`reject`, Enfoque B). **Next:** the worker (`workers/post_comment_worker.py`) — allowlist validation + GitHub comment POST + `WorkerSettings`; then the Discord bridge (yes/no buttons → approve/reject).

**VPS:** Oracle Cloud Always Free, VM.Standard.E2.1.Micro (AMD x86, **1GB RAM** — resource-constrained, factor this into every choice), Ubuntu 22.04, IP `137.131.202.213`. Connect: `ssh ubuntu@137.131.202.213`. Hermes runs as user `hermes`; binary at `/home/hermes/.hermes/hermes-agent/venv/bin/hermes`. Redis runs locally (127.0.0.1:6379, password-protected). Operator cheatsheet: `CHEATSHEET.md` (gitignored, personal).

**Demo thesis:** Hermes on Discord answers the team's questions about code/PRs/CI-failures (reads GitHub via MCP); arq+Redis runs recurring work and approval-gated GitHub writes (digests, alerts, comments), replacing n8n.

## Operating rules (from the plan — these are binding)

- **One phase at a time.** Do not advance past a phase without satisfying its validation checklist.
- **On closing each phase:** update `HANDOFF.md` and add an `ADR-XXXX` under `docs/adr/`.
- **MANUAL STEPS (`PASOS MANUALES`) are done by the human, not by Claude Code.** Leave them clearly indicated and wait — do not execute them. These cover: provisioning the VPS, installing Hermes, creating the Discord bot/token, generating the scoped GitHub PAT, installing Redis (done), and disabling/decommissioning n8n.
- **If a fact is missing, assume the reasonable default and record the assumption explicitly in an ADR.** Do not stop to ask.
- **Secrets** live only in `~/.hermes/.env` (or the service environment), `chmod 600`. Never hardcoded, never committed. `deploy/.env.example` lists variable names with no values.

## Language & commit conventions

- **Code in English. Comments and docstrings in Spanish. Commit messages in English**, following Conventional Commits.
- Python tooling uses **uv** + **Ruff**. Lint with `uv run ruff check`. Add deps with `uv add <pkg>` (pins the current version into `uv.lock` — never hand-write versions from memory).

## Branching

- `main` always reflects the deployed configuration.
- One **feature branch per phase**: `feat/fX-nombre`. Merge to `main` only when that phase's checklist is complete.
- Every merge updates `HANDOFF.md` and adds the corresponding ADR(s).

## Architecture (how the pieces fit)

- **Hermes Agent** = the brain. Receives Discord messages, reasons, decides, and has tools (GitHub MCP, docs reading). Runs as a 24/7 headless gateway on the VPS (systemd, non-root user).
- **arq (Redis)** = the durable execution layer. Any work that acts on GitHub, or is recurring/critical, is enqueued as an arq job. The worker consumes it with retries, exponential backoff, and idempotency (job uniqueness via custom `_job_id`), so work survives VPS reboots, is not duplicated, and is retried on transient failures.
- **Core pattern:** Hermes decides and **enqueues** a job → an **arq worker** executes the action (e.g. post the approved comment, build the digest) → result is logged and reported back to the Discord channel.
- **Single scheduling mechanism:** recurring work (e.g. daily digest) uses **arq `cron_jobs`**, not a second cron. Avoid running Hermes-native cron and arq cron in parallel; if a purely conversational recurring task belongs in Hermes' native cron, document that exception in an ADR.

### Two guardrails that are easy to get wrong

- **Approval gate for published actions is orchestration-level, NOT Hermes-native.** Hermes' native `approvals.mode` only covers dangerous shell commands — it does **not** cover an MCP action like "post a GitHub comment." So visible actions (comments/messages) are held in a **pending-approval** state (Enfoque B: a Redis key `pending-approval:<id>`, **not** the arq execution queue); an allowlisted user approves via Discord (yes/no); only then is the real arq job enqueued and the worker executes. The arq queue therefore *structurally* only ever contains approved work.
- **Repo allowlist is enforced in the worker (deterministic layer), not in the LLM.** Which repos may be written to is a deterministic decision, validated in the arq worker (`config/guardrails/repo-allowlist.yaml`).

Additional defense-in-depth: the GitHub PAT is scoped to read + comment only (no merge/push/force-push). The idempotency key (sha256 of `repo+pr+body`, used as the arq `_job_id`) prevents a 24/7 retrying agent from duplicating actions — arq returns `None` if the id is already queued/running.

## Repo structure

```
docs/adr/          # ADR-0001..., one+ per phase
docs/n8n-inventory.md, docs/runbook.md
config/hermes/     # config.yaml: intent/doc artifact only (the LIVE config is on the VPS)
config/guardrails/ # repo allowlist, publish-approval policy
hermes_queue/      # arq task queue (Python): settings.py, jobs/, workers/
deploy/systemd/    # units: hermes-gateway, arq worker
deploy/.env.example, deploy/install-notes.md
scripts/
```

## Decisions already made (do not re-litigate)

- **Worker/queue language:** **Python + arq** (ADR-0006, supersedes ADR-0005). Chosen for defensibility in the author's stack and the 1GB free VPS (arq is async, Redis-native, tiny footprint, with native cron/retries/idempotency). BullMQ/TypeScript was discarded; the Python package is named `hermes_queue` (not `queue`) to avoid shadowing the stdlib `queue` module.
- **LLM:** provider **OpenCode** (user's Go subscription), model **`kimi-k2.7-code`**. Key in `~/.hermes/.env` as `OPENCODE_API_KEY`. OpenRouter was discarded (ADR-0002).

## Confirmed facts about Hermes (do not re-verify)

Confirmed against the docs and **reconciled against the real install on the VPS**:
- Headless VPS install via `curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash`.
- **MCP servers are managed via the `hermes mcp` CLI (`add`/`configure`/`list`/`catalog`), NOT a `mcp_servers` block in `config.yaml`.** The PAT is passed as an env reference `--env GITHUB_PERSONAL_ACCESS_TOKEN='${GITHUB_PAT}'`; Hermes resolves `${GITHUB_PAT}` at runtime from `~/.hermes/.env` (verified), so the secret is never hardcoded. The GitHub MCP (`@modelcontextprotocol/server-github`) exposes 26 tools; **we locked it to 14 read-only tools** via `hermes mcp configure` (12 write tools disabled) so the only publish path is the approval-gated worker.
- The real generated config uses top-level keys `model:`, `discord:`, `approvals:`, `terminal:` (NOT `llm:`/`channels:`). The repo's `config/hermes/config.yaml` is an intent/doc artifact, not the live file — do not overwrite the installer-generated `~/.hermes/config.yaml` wholesale; edit deltas only.
- Discord: user allowlist via `DISCORD_ALLOWED_USERS`; native yes/no approval buttons. Without an allowlist Hermes denies everyone. Privileged Gateway Intents (Presence, Server Members, Message Content) must be enabled manually in the Discord Developer Portal.
- systemd unit needs `TimeoutStopSec>=210` (Hermes `restart_drain_timeout` is 180s; the 90s default SIGKILLs mid-drain).
- Native cron with `approvals.cron_mode` (deny|approve); sandbox backends `ssh`/`docker`; `approvals.mode` (manual|smart|off) covers dangerous shell commands only (NOT MCP actions).

## Mistakes not to repeat (lessons paid for in this project)

- **Never assert volatile tech facts from training memory — verify first.** Real failure: claimed "BullMQ's Python port is an immature third-party project" from memory; it is actually official (Taskforce.sh), and a later check showed its real gaps were different (no schedulers/retries/events). Route verification: **Context7 MCP** for library docs/capabilities/syntax; **web search** for project status, comparisons, pricing, versions. Tag claims ✅ verified (source + date) vs ⚠️ from memory.
- **Define the deciding criterion BEFORE evaluating options.** Real failure: ADR-0005 picked TypeScript by optimizing "best queue tech," ignoring the criteria that actually bind here — defensibility in the author's Python stack + the 1GB free VPS. Surfacing those first (ADR-0006) reversed the decision and avoided building a whole subsystem the author couldn't defend. For this project, weigh **Python-stack defensibility and resource cost** explicitly in every tooling choice.
- **Don't fragment a cohesive subsystem across languages by feature gaps.** Split by service boundary, not by "what library X is missing." (Why the Python-producer/TS-worker hybrid was rejected — ADR-0006.)
- **Don't name a Python package after a stdlib module** (`queue`, `json`, `types`, …). It shadows the import and breaks dependencies subtly. Hence `hermes_queue`.
- **The earlier `mcp_servers`-in-`config.yaml` assumption was wrong** (corrected in ADR-0004): MCP is CLI-managed. Don't reintroduce it.

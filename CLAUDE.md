# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Operations repo (`team-agent-ops`) for **deploying and configuring Hermes Agent (Nous Research)** on an Ubuntu VPS, wiring it to GitHub (via MCP) and Discord, running durable work through **BullMQ + Redis**, and **migrating an existing n8n bot** onto it before retiring n8n.

Hermes is operated as a dependency — **do not fork it**. What gets versioned here is the configuration, the business guardrails, and the BullMQ queues/workers. `plan-1-agente-hermes.md` is the authoritative, phase-by-phase execution plan. Read it before acting.

## Current state (updated 2026-06-19)

- **Phase 0 (bootstrap):** ✅ complete, merged to `main`.
- **Phase 1 (Hermes live on Discord):** ✅ complete, validated on VPS, merged to `main`.
- **Phase 2 (n8n inventory + migration map):** ✅ complete, merged to `main`. Inventory is *invented* (realistic team workflows) — the user has no real n8n access; we build the migration as if real for a portfolio/demo. See `docs/n8n-inventory.md`.
- **Phase 3a (GitHub MCP, read-only):** ✅ complete, validated. On branch `feat/f3-github-mvp` (NOT yet merged — Phase 3 closes only when 3b is done).
- **Phase 3b (write path: approval-gated BullMQ worker):** ⏳ blocked on Redis (manual install, Phase 4).

**VPS:** Oracle Cloud Always Free, VM.Standard.E2.1.Micro (AMD x86, 1GB RAM), Ubuntu 22.04, IP `137.131.202.213`. Connect: `ssh ubuntu@137.131.202.213`. Hermes runs as user `hermes`; binary at `/home/hermes/.hermes/hermes-agent/venv/bin/hermes`. Operator cheatsheet: `CHEATSHEET.md` (gitignored, personal).

**Demo thesis:** Hermes on Discord answers the team's questions about code/PRs/CI-failures (reads GitHub via MCP); BullMQ+Redis runs recurring work and approval-gated GitHub writes (digests, alerts, comments), replacing n8n.

## Operating rules (from the plan — these are binding)

- **One phase at a time.** Do not advance past a phase without satisfying its validation checklist.
- **On closing each phase:** update `HANDOFF.md` and add an `ADR-XXXX` under `docs/adr/`.
- **MANUAL STEPS (`PASOS MANUALES`) are done by the human, not by Claude Code.** Leave them clearly indicated and wait — do not execute them. These cover: provisioning the VPS, installing Hermes, creating the Discord bot/token, generating the scoped GitHub PAT, installing Redis, and disabling/decommissioning n8n.
- **If a fact is missing, assume the reasonable default and record the assumption explicitly in an ADR.** Do not stop to ask.
- **Secrets** live only in `~/.hermes/.env` (or the service environment), `chmod 600`. Never hardcoded, never committed. `deploy/.env.example` lists variable names with no values.

## Language & commit conventions

- **Code in English. Comments and docstrings in Spanish. Commit messages in English**, following Conventional Commits.
- Python tooling uses **uv** + **Ruff**. Lint with `uv run ruff check`.

## Branching

- `main` always reflects the deployed configuration.
- One **feature branch per phase**: `feat/fX-nombre`. Merge to `main` only when that phase's checklist is complete.
- Every merge updates `HANDOFF.md` and adds the corresponding ADR(s).

## Architecture (how the pieces fit)

- **Hermes Agent** = the brain. Receives Discord messages, reasons, decides, and has tools (GitHub MCP, docs reading). Runs as a 24/7 headless gateway on the VPS (systemd, non-root user).
- **BullMQ (Redis)** = the durable execution layer. Any work that acts on GitHub, or is recurring/critical, is enqueued as a BullMQ job. Workers consume the queue with retries, exponential backoff, deduplication, and rate limiting, so work survives VPS reboots, is not duplicated, and is retried on transient failures.
- **Core pattern:** Hermes decides and **enqueues** a job → a **BullMQ worker** executes the action (e.g. post the approved comment, build the digest) → result is logged and reported back to the Discord channel.
- **Single scheduling mechanism:** recurring work (e.g. daily digest) uses **BullMQ job schedulers**, not a second cron. Avoid running Hermes-native cron and BullMQ cron in parallel; if a purely conversational recurring task belongs in Hermes' native cron, document that exception in an ADR.

### Two guardrails that are easy to get wrong

- **Approval gate for published actions is orchestration-level, NOT Hermes-native.** Hermes' native `approvals.mode` only covers dangerous shell commands — it does **not** cover an MCP action like "post a GitHub comment." So visible actions (comments/messages) are enqueued in BullMQ in a `pending-approval` state; an allowlisted user approves via Discord (yes/no); only then does the worker execute. Do not assume Hermes approval covers MCP actions.
- **Repo allowlist is enforced in the worker (deterministic layer), not in the LLM.** Which repos may be written to is a deterministic decision, validated in the BullMQ worker.

Additional defense-in-depth: the GitHub PAT is scoped to read + comment only (no merge/push/force-push). Idempotency keys (e.g. `repo+pr+content_hash`) prevent a 24/7 retrying agent from duplicating actions.

## Intended repo structure (built out across phases)

```
docs/adr/        # ADR-0001..., one+ per phase
docs/n8n-inventory.md, docs/runbook.md
config/hermes/   # config.yaml: channels, model, mcp_servers, approvals, cron
config/guardrails/  # repo allowlist, publish-approval policy
queue/           # BullMQ: queues, workers/, jobs/ (+ idempotency keys)
deploy/systemd/  # units: hermes-gateway, redis, bullmq-workers
deploy/.env.example, deploy/install-notes.md
scripts/
```

## Open decisions to record when reached (do not pre-decide)

- **Worker language (Phase 4):** TypeScript (mature reference SDK) vs Python (homogeneous with repo tooling). Decide with rationale, record in ADR-0005. The structure stays language-agnostic until then.

## Decisions already made (do not re-litigate)

- **LLM:** provider **OpenCode** (user's Go subscription), model **`kimi-k2.7-code`**. Key in `~/.hermes/.env` as `OPENCODE_API_KEY`. OpenRouter was discarded (ADR-0002).

## Confirmed facts about Hermes (do not re-verify)

Confirmed against the docs and **reconciled against the real install on the VPS**:
- Headless VPS install via `curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash`.
- **MCP servers are managed via the `hermes mcp` CLI (`add`/`configure`/`list`/`catalog`), NOT a `mcp_servers` block in `config.yaml`.** (The earlier assumption of a config.yaml block was WRONG — corrected in ADR-0004.) The PAT is passed as an env reference `--env GITHUB_PERSONAL_ACCESS_TOKEN='${GITHUB_PAT}'`; Hermes resolves `${GITHUB_PAT}` at runtime from `~/.hermes/.env` (verified), so the secret is never hardcoded. The GitHub MCP (`@modelcontextprotocol/server-github`) exposes 26 tools; **we locked it to 14 read-only tools** via `hermes mcp configure` (12 write tools disabled) so the only publish path is the approval-gated worker.
- The real generated config uses top-level keys `model:`, `discord:`, `approvals:`, `terminal:` (NOT `llm:`/`channels:`). The repo's `config/hermes/config.yaml` is an intent/doc artifact, not the live file — do not overwrite the installer-generated `~/.hermes/config.yaml` wholesale; edit deltas only.
- Discord: user allowlist via `DISCORD_ALLOWED_USERS`; native yes/no approval buttons. Without an allowlist Hermes denies everyone. Privileged Gateway Intents (Presence, Server Members, Message Content) must be enabled manually in the Discord Developer Portal.
- systemd unit needs `TimeoutStopSec>=210` (Hermes `restart_drain_timeout` is 180s; the 90s default SIGKILLs mid-drain).
- Native cron with `approvals.cron_mode` (deny|approve); sandbox backends `ssh`/`docker`; `approvals.mode` (manual|smart|off) covers dangerous shell commands only (NOT MCP actions).

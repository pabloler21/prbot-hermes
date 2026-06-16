# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Operations repo (`team-agent-ops`) for **deploying and configuring Hermes Agent (Nous Research)** on an Ubuntu VPS, wiring it to GitHub (via MCP) and Discord, running durable work through **BullMQ + Redis**, and **migrating an existing n8n bot** onto it before retiring n8n.

Hermes is operated as a dependency — **do not fork it**. What gets versioned here is the configuration (`config.yaml`), the business guardrails, and the BullMQ queues/workers. The current state of the repo is the plan only: `plan-1-agente-hermes.md` is the authoritative, phase-by-phase execution plan. Read it before acting.

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
- **Concrete LLM model (Phase 1):** provider is OpenRouter (key in `~/.hermes/.env`); pin the specific model in Phase 1.

## Confirmed facts about Hermes (do not re-verify)

Confirmed against `https://hermes-agent.nousresearch.com/docs`:
- Headless VPS install via `curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash`.
- GitHub via the `@modelcontextprotocol/server-github` MCP server; PAT passed through the `env` of the `mcp_servers` block in `~/.hermes/config.yaml`. Hermes filters the MCP subprocess environment to only what's declared in `env`.
- OpenRouter is natively supported.
- Discord channel supported, with a user allowlist (`DISCORD_ALLOWED_USERS`) and native yes/no approval buttons. Without an allowlist Hermes denies everyone.
- Native cron with delivery to any platform; `approvals.cron_mode` (deny|approve) for headless behavior.
- Sandbox backends `ssh` and `docker` (in `docker`, dangerous-command checks are skipped because the container is the security boundary).
- `approvals.mode` (manual|smart|off) — covers dangerous shell commands only.

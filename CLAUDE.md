# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Operations repo (`team-agent-ops`) for **deploying and configuring Hermes Agent (Nous Research)** on an Ubuntu VPS, wiring it to GitHub (via MCP) and Discord, running durable work through **arq + Redis**, and **migrating an existing n8n bot** onto it before retiring n8n.

This is a **portfolio/demo project**: the author must be able to explain and defend every part in interviews, and **the author's stack is Python** — a binding constraint that shapes technical decisions (see ADR-0006). Prefer Python + tools the author can defend; don't introduce a stack they can't explain.

Hermes is operated as a dependency — **do not fork it**. What gets versioned here is the configuration, the business guardrails, and the arq queues/workers. `plan-1-agente-hermes.md` is the authoritative, phase-by-phase execution plan. Read it before acting.

## Current state (updated 2026-06-23)

- **Phase 0 (bootstrap):** ✅ merged to `main`.
- **Phase 1 (Hermes live on Discord):** ✅ merged to `main`.
- **Phase 2 (n8n inventory + migration map):** ✅ merged to `main`. Inventory is *invented* (realistic team workflows) — the author has no real n8n access; we build the migration as if real for a portfolio/demo. See `docs/n8n-inventory.md`.
- **Phase 3 (GitHub MVP: read MCP + approval-gated write path):** ✅ **COMPLETE, validated end-to-end on the VPS, merged to `main`** (PR #1). 3a = GitHub MCP read-only; 3b = the Python/arq write path with approval gate. Validated flow: user (DM) → Hermes → MCP tool `propose_pr_comment` → pending → Discord approval bot (✅/❌) → arq worker posts the comment to GitHub. Allowlist rejection, idempotency, and error handling confirmed live.
- **Phase 4 (durable-queue hardening):** ✅ **COMPLETE, validated end-to-end on the VPS, merged to `main`** (PR #3). Added a **dead-letter queue** (arq has none native — Redis list `dead-letter:post_comment`, capped, with manual requeue), a **concurrency cap** (`max_jobs=2`) as rate-limiting (arq has no QPS token-bucket; the human approval gate already throttles writes), and validated **reboot-survival** of the worker/bot services. See ADR-0007. NB: per the plan, Phase 4 was queue-infra hardening, **NOT** the n8n migration (that's Phase 6).
- **Phase 5 (issue triage + documentation reading):** ✅ **COMPLETE, validated end-to-end on the VPS, merged to `main`** (PR #5). Reactive (Discord-triggered), reuses the approval gate. Commenting on issues already worked (`propose_pr_comment` serves PR *and* issue — same endpoint); reading issues/docs already worked via the read-only MCP. The only new write action is **applying labels**: tool `propose_issue_labels` → gate → task `apply_issue_labels` in the same worker. The approval gate was **generalized to be action-agnostic** (pending record carries `{task, data}`; bot shows a pre-formatted `summary`); DLQ is now per-task (`dead-letter:<task>`). Validated live: Hermes read issue #6, proposed `bug`+`priority:high`, the approval bot showed ✅/❌, approving applied the labels via GitHub (PAT `Issues: write` confirmed, no 403). See ADR-0008. **NB: Phase 5 is reactive — it does NOT add poll workers.** The first automatic/recurring work (and the per-QPS rate-limiting revisit) is **Phase 6** (daily digest via `cron_jobs`).
- **Phase 6a (daily PR digest):** ✅ **COMPLETE, validated end-to-end on the VPS, merged to `main`** (PR #7). First **recurring** work: `daily_pr_digest` is an **arq `cron_jobs`** entry (mon-fri 09:00 UTC-3, explicit `timezone`) in the *same* worker (no new systemd service). It reads open PRs of the allowlisted repos and posts a deterministic Markdown digest to Discord via an **incoming webhook** (`discord_client.py`, `DISCORD_DIGEST_WEBHOOK_URL`, splits >2000 chars) — **no approval gate** (it only reads GitHub + posts to our own channel). Idempotent by scheduled time (`cron(unique=True)` → a restart near 09:00 doesn't double-send). Validated live: manual trigger posted the digest to `#digest` (webhook returned HTTP 204). See ADR-0009.
- **Phase 6b (next):** the other 4 n8n workflows for full parity — New Issue Alert + Deploy Notification as **poll** jobs (every 5 min, Redis cursor + idempotency `repo+issue_number` / `repo+pr_number+merged_at`), Stale PR Alert (cron 10:00), Weekly Summary (cron Fri 18:00). **This is where automatic poll work first appears** → revisit per-QPS rate-limiting (today handled by the `max_jobs` concurrency cap). Then Phase 7 = cutover (disable, observe, retire n8n).

**Known follow-ups (non-blocking):**
- Hermes currently replies only in DM, not in the server channel (home-channel quirk — see `DISCORD_HOME_CHANNEL`).
- **Approval-bot buttons don't survive a bot restart** — the `discord.py` views are in-memory and not registered as persistent (no `custom_id` + `add_view` in `setup_hook`), so clicking a button on a message posted by a previous process yields "This interaction failed". Operational rule: don't restart `hermes-approval-bot` between propose and approve. Future fix: persistent views.

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

- `main` reflects the deployed configuration (now through Phase 6a).
- One **feature branch per phase**: `feat/fX-nombre`. Merge to `main` only when the checklist is complete. Every merge updates `HANDOFF.md` + ADR(s).

## Architecture (how the pieces fit)

- **Hermes Agent** = the brain. Receives Discord messages, reasons, decides, has tools (GitHub MCP read-only, the custom `hermes-queue` MCP, docs reading). Runs 24/7 as a headless gateway (systemd, non-root).
- **arq (Redis)** = the durable execution layer. Work that acts on GitHub or is recurring/critical is enqueued as an arq job. The worker consumes it with retries, exponential backoff, and idempotency (job uniqueness via custom `_job_id`), so work survives reboots, isn't duplicated, and is retried on transient failures. Inside a task, the arq pool is available as `ctx["redis"]`. Jobs that fail permanently (4xx, repo-not-allowed) or exhaust retries go to a **Redis-list dead-letter** (`hermes_queue/deadletter.py`) instead of vanishing — arq has no native DLQ. Concurrency is capped (`max_jobs`) as rate-limiting; arq has no native per-QPS limiter. See ADR-0007.
- **Core pattern:** Hermes decides and **enqueues** → an **arq worker** executes (post the approved comment, build the digest) → result is logged and reported back to Discord.
- **Single scheduling mechanism:** recurring work uses **arq `cron_jobs`**, not a second cron. Avoid running Hermes-native cron and arq cron in parallel; document any exception in an ADR.

### Two guardrails that are easy to get wrong

- **Approval gate is orchestration-level, NOT Hermes-native.** Hermes' native `approvals.mode` only covers dangerous shell commands — NOT an MCP action like "post a GitHub comment." So visible actions are held **pending-approval** (Enfoque B: a Redis key `pending-approval:<id>`, **not** the arq queue); an allowlisted user approves via the Discord approval bot (✅/❌); only then is the real arq job enqueued. The arq queue therefore *structurally* only ever contains approved work. The approval decision is deterministic (a human clicking a button), never the LLM reading "yes".
- **Repo allowlist is enforced in the worker (deterministic), not in the LLM** (`config/guardrails/repo-allowlist.yaml`). Each approved write task (`post_comment`, `apply_issue_labels`) re-checks it; a rejection goes to that task's dead-letter.

Defense-in-depth: the GitHub PAT is scoped to read + comment + label only (`Issues`/`Pull requests: write`; no merge/push/force-push). The idempotency key (sha256 of the request content — `repo+pr+body` for comments, `repo+issue+sorted(labels)` for labels — used as the arq `_job_id` and the `pending-approval` id) prevents a 24/7 retrying agent from duplicating actions — arq returns `None` if the id is already queued/running.

## Repo structure

```
docs/adr/          # ADR-0001..0008, one+ per phase
docs/n8n-inventory.md, docs/runbook.md
config/hermes/     # config.yaml: intent/doc artifact only (LIVE config is on the VPS)
config/guardrails/ # repo-allowlist.yaml, publish-approval policy
hermes_queue/      # arq queue layer (Python):
  settings.py        # RedisSettings from REDIS_URL
  jobs/gate.py       # generic, action-agnostic approval gate (enqueue_pending/approve/reject; pending = {task, data})
  jobs/post_comment.py  # PostCommentRequest data type + idempotency key
  jobs/apply_labels.py  # ApplyLabelsRequest data type + idempotency key (Phase 5)
  jobs/digest.py     # build_pr_digest: format open PRs as Markdown (Phase 6, pure/testable)
  guardrails.py      # repo allowlist (deterministic) + allowed_repos() to iterate
  github_client.py   # PR/issue comment + add issue labels + list_open_pull_requests (GitHub REST)
  discord_client.py  # post_to_discord via incoming webhook (digest delivery, splits >2000 chars)
  events.py          # Redis pub/sub (MCP -> approval bot); publishes {kind, summary}
  deadletter.py      # per-task dead-letter (Redis list dead-letter:<task>) + manual requeue (arq has no native DLQ)
  workers/post_comment_worker.py  # arq worker: tasks post_comment + apply_issue_labels + cron daily_pr_digest (timezone UTC-3)
  mcp_server.py      # FastMCP server: tools propose_pr_comment + propose_issue_labels for Hermes
  approval_bot.py    # discord.py bot: ✅/❌ buttons (deterministic, action-agnostic gate)
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
- **Verify phase SCOPE against `plan-1-agente-hermes.md`, not memory.** Real failure: wrote "Phase 4 = migrate n8n to cron" in CLAUDE.md/HANDOFF from memory — the plan says Phase 4 = durable-queue hardening; the n8n migration is Phase 6. The anti-staleness discipline applies to *internal docs too*: the plan is the authoritative source for phase boundaries, read it before asserting what a phase is.
- **Don't assume a queue library has dead-letter / rate-limiting — verify.** Confirmed via Context7: **arq has no native dead-letter queue** (jobs past `max_tries` are marked failed and the payload is discarded) and **no per-QPS rate-limiter** (only `max_jobs` concurrency + `poll_delay`). We built the DLQ as a Redis list and use the concurrency cap as the throttle. `raise Retry` on the *last* attempt does NOT save the payload — detect the last try (`ctx["job_try"] >= max_tries`) and record to the DLQ yourself.
- **Push the feature branch before deploying it on the VPS.** `git checkout <branch>` on the VPS failed with `pathspec did not match` because the branch was still local-only. Push first, then `git fetch && git checkout` on the VPS.
- **`systemctl`/`journalctl` only exist on the VPS, not in local PowerShell.** After `sudo reboot` the SSH session drops; reconnect with `ssh ubuntu@<ip>` before running service checks (running them in the local Windows shell errors with `command not found`).
- **Check what already works before writing code.** In Phase 5, "comment on issues" and "read docs/issues" needed *zero* new code: a PR is an issue for the API (`/issues/{n}/comments` and `propose_pr_comment` already serve issues), and the read-only MCP already reads files/issues (validated in 3a). The only genuinely new thing was applying labels. Scope a phase by what's missing, not by re-listing what the plan names.
- **Generalize a gate by carrying the action, not by duplicating it.** Adding a second write action (labels) didn't fork the approval bot or the gate: the pending record now carries `{task, data}` and the bot shows a pre-formatted `summary`, so gate/bot stay action-agnostic. Adding a future action = new tool + new request type + a worker function, nothing else.
- **When a shared message format changes, restart ALL its consumers, not just the producer.** Phase 5 changed the `events.publish_pending` payload (`{repo, pr_number, body}` → `{kind, summary}`). The deploy restarted `hermes-gateway` (producer) + `hermes-arq-worker` but **not** `hermes-approval-bot` (consumer) — so the bot crashed with `KeyError` on the new payload and posted nothing. Restart the gateway, worker, **and** approval bot together after any change to the MCP↔bot↔worker contract.
- **Redis pub/sub does NOT queue — a dropped notification is gone, but the pending state isn't.** If no healthy subscriber is connected at publish time, the message is lost and never redelivered (so "it'll arrive late" is wrong). The `pending-approval:<id>` Redis key survives, though; re-emit the button by re-publishing from that key (the gate's data is intact), not by hoping the LLM re-calls the tool (it may answer "I already did that" without re-invoking).
- **`discord.py` button views are in-memory and die on bot restart.** A `timeout=None` view is not automatically persistent; without `custom_id` + `self.add_view(...)` in `setup_hook`, clicking a button on a message from a previous process gives "This interaction failed". Don't restart the approval bot between propose and approve; for true persistence, register persistent views.

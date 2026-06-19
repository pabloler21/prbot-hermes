# ADR-0004 — Guardrails de GitHub: MCP solo-lectura + allowlist de repos (Fase 3)

- **Estado:** parcial (3a confirmado; 3b — worker + approval gate — pendiente de Redis)
- **Fase:** 3
- **Fecha:** 2026-06-19

## Contexto

Primera conexión de Hermes a GitHub. Antes de cualquier feature, se establecen los
guardrails de negocio: sobre qué repos puede actuar y cómo se publica. Postear algo
incorrecto en un PR real cuesta confianza, así que los frenos van primero.

Esta fase se divide en dos sub-etapas por una dependencia de infraestructura:
- **3a (esta entrega):** Hermes LEE GitHub vía MCP, en modo solo-lectura.
- **3b (pendiente):** el camino de ESCRITURA (worker BullMQ + approval gate), que
  requiere Redis instalado (paso manual de la Fase 4).

## Decisiones

### 1. El MCP de GitHub se gestiona con el CLI `hermes mcp`, no con `config.yaml`

**Supuesto previo refutado:** se asumía (CLAUDE.md / ADR-0002) que el MCP se declaraba
en un bloque `mcp_servers` de `~/.hermes/config.yaml`. El config real generado por el
instalador **no tiene** ese bloque; Hermes gestiona los MCP con `hermes mcp add/configure/list`
y los guarda en su estado interno. Se versiona el **comando** en `install-notes.md`, no
un bloque YAML.

### 2. El PAT se guarda como referencia `${GITHUB_PAT}`, no como valor literal

El servidor MCP oficial (`@modelcontextprotocol/server-github`) espera la variable
`GITHUB_PERSONAL_ACCESS_TOKEN`. Se mapea con `--env GITHUB_PERSONAL_ACCESS_TOKEN='${GITHUB_PAT}'`
(comillas simples). Hermes resuelve `${GITHUB_PAT}` en runtime desde `~/.hermes/.env`.
**Verificado:** la conexión funcionó sin el token en el shell interactivo, confirmando
que Hermes interpola desde el `.env`. El secreto no queda en la config del MCP.

### 3. MCP en SOLO-LECTURA (guardrail a nivel de tool)

El MCP expone 26 tools, 12 de ellas de escritura/peligrosas (`merge_pull_request`,
`push_files`, `add_issue_comment`, etc.). Se desactivaron con `hermes mcp configure`,
dejando solo las 14 de lectura. Razón: según la arquitectura del proyecto, Hermes
**no publica directamente** vía MCP; el único camino de publicación es el worker de
BullMQ con approval gate. Dejar el MCP read-only hace que Hermes no pueda saltarse ese
gate ni por error del LLM.

### 4. PAT scopeado (defensa en profundidad)

El PAT no tiene permisos de merge/push/force-push. Aunque una tool de escritura
estuviera activa, GitHub la rechazaría (403). Dos capas independientes: scope del token
+ tools desactivadas.

### 5. Allowlist de repos en capa determinística

`config/guardrails/repo-allowlist.yaml` lista los repos permitidos
(`pabloler21/prbot-hermes`). Se validará en el **worker** (3b), no en el LLM: a qué repo
se escribe es una decisión de código. (En 3a, read-only, la allowlist aún no se aplica;
queda definida para 3b.)

## Tools de lectura habilitadas (14)

`search_repositories`, `get_file_contents`, `list_commits`, `list_issues`, `search_code`,
`search_issues`, `search_users`, `get_issue`, `get_pull_request`, `list_pull_requests`,
`get_pull_request_files`, `get_pull_request_status`, `get_pull_request_comments`,
`get_pull_request_reviews`.

## Validación

- [x] (3a) Hermes lee un archivo del repo vía MCP desde Discord (`get_file_contents` sobre `CLAUDE.md`).
- [x] (3a) MCP confirmado en solo-lectura (`hermes mcp list` → "14 selected").
- [x] (3a) El PAT no quedó hardcodeado (referencia `${GITHUB_PAT}` resuelta en runtime).
- [ ] (3b) Acción sobre repo fuera de la allowlist: rechazada por el worker.
- [ ] (3b) Ningún comentario se postea sin aprobación por Discord.
- [ ] (3b) Reintentar el mismo job no duplica el comentario (idempotencia).

## Consecuencias

- Hermes ya tiene contexto de GitHub (lee PRs, issues, código, checks de CI) — base para
  el PR Assistant de la Fase 5.
- El camino de escritura queda deliberadamente cerrado hasta que exista el worker con
  approval gate (3b), que depende de Redis.
- Se actualiza el supuesto de ADR-0002 sobre `mcp_servers` en `config.yaml`: es incorrecto.

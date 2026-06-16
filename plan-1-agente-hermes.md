# Plan 1 — Bot interno sobre Hermes Agent + BullMQ (despliegue + migración de n8n)

> Plan de ejecución para **Claude Code**, fase por fase. No contiene código: contiene el plan. El proyecto es **desplegar y configurar Hermes Agent (Nous Research) en un VPS**, conectarle GitHub y Discord, ejecutar el trabajo durable a través de **BullMQ**, **migrar lo que hace el bot de n8n** y luego retirarlo.
>
> **Reglas para Claude Code:**
> - Una fase a la vez. No avanzar sin cumplir el checklist de validación.
> - Al cerrar cada fase: actualizar `HANDOFF.md` y agregar un `ADR-XXXX`.
> - Los **PASOS MANUALES** los hace el humano; Claude Code no los ejecuta, solo los deja indicados y espera.
> - Si falta un dato, asumir lo razonable y dejar el supuesto explícito en el ADR; no frenar a preguntar.
> - Código en inglés, comentarios/docstrings en español, commits en inglés (Conventional Commits).
> - Secrets siempre por `~/.hermes/.env` o env del servicio. Nunca hardcodeados.

---

## Hechos verificados (base del plan, ya confirmados contra las docs de Hermes)

Estos puntos están confirmados en `https://hermes-agent.nousresearch.com/docs` y no requieren re-verificación; se documentan para que Claude Code no los trate como inciertos:

- **Headless en VPS:** Hermes se instala por CLI sin la app de escritorio (`curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash`) y corre como gateway desatendido en un VPS Linux.
- **GitHub vía MCP:** se conecta con el servidor MCP de GitHub (`@modelcontextprotocol/server-github`), pasando el PAT por la config `env` del bloque `mcp_servers` en `~/.hermes/config.yaml`. Hermes filtra el entorno de los subprocesos MCP y solo pasa lo declarado en `env`.
- **Proveedor LLM:** OpenRouter es soportado nativamente (API key en `~/.hermes/.env`).
- **Canal Discord:** soportado, con allowlist de usuarios (`DISCORD_ALLOWED_USERS`) y botones nativos yes/no para prompts de aprobación.
- **Cron nativo:** Hermes trae scheduling incorporado con entrega a cualquier plataforma, y `approvals.cron_mode` (deny|approve) para comportamiento headless.
- **Sandbox:** backends `ssh` y `docker`. En `docker` los chequeos de comando peligroso se omiten porque el contenedor es el límite de seguridad.
- **Approval nativo:** `approvals.mode` (manual|smart|off) cubre **comandos de shell peligrosos**, con flujo yes/no en Discord y timeout fail-closed.

> **Matiz clave a tener en cuenta en todo el plan:** el approval nativo de Hermes aplica a comandos de shell/terminal peligrosos, **no** a una acción "publicar comentario en GitHub" vía MCP. Por lo tanto, el approval gate para acciones visibles (comentarios/mensajes) se diseña explícitamente en este plan a nivel de orquestación (Fase 3), no se asume incluido.

---

## Arquitectura (cómo encajan las piezas)

- **Hermes Agent** = el cerebro: recibe mensajes por Discord, razona, decide, y dispone de tools (GitHub MCP, lectura de docs, etc.). Corre como gateway 24/7 en el VPS.
- **BullMQ (Redis)** = la capa de ejecución durable: todo trabajo que actúa sobre GitHub o que es recurrente/crítico se encola como job en BullMQ. Workers consumen la cola y ejecutan, con reintentos, backoff, deduplicación y rate limiting. Esto garantiza que el trabajo sobreviva reinicios del VPS, no se duplique y se reintente ante fallos transitorios.
- **Patrón:** Hermes decide y **encola** el job → un **worker BullMQ** ejecuta la acción (ej. postear el comentario aprobado, generar el digest) → el resultado se loguea y se reporta de vuelta al canal. El cron recurrente (digest) se implementa con **job schedulers de BullMQ**, no con dos mecanismos de cron en paralelo.
- **VPS Ubuntu**, acceso por SSH, todo corriendo como servicios (systemd): el gateway de Hermes, Redis, y los workers de BullMQ.

---

## Estructura del repo de operaciones

```
team-agent-ops/
├─ README.md                      # qué es, cómo se despliega, cómo se opera
├─ HANDOFF.md                     # notas de handoff, se actualiza por fase
├─ pyproject.toml                 # uv + Ruff (para scripts/tools propias en Python)
├─ docs/
│  ├─ adr/                        # ADR-0001-..., decisiones por fase
│  ├─ n8n-inventory.md            # inventario de workflows (Fase 2)
│  └─ runbook.md                  # operación: arrancar/parar, rotar secrets, ver logs
├─ config/
│  ├─ hermes/                     # config.yaml de Hermes (canales, modelo, mcp, approvals, cron)
│  └─ guardrails/                 # allowlist de repos, política de approval de publicación
├─ queue/                         # BullMQ: definición de colas, workers, schedulers
│  ├─ queues.*                    # definición de colas y conexión a Redis
│  ├─ workers/                    # workers: post-comment, triage-publish, digest
│  └─ jobs/                       # tipos de job + claves de idempotencia
├─ deploy/
│  ├─ systemd/                    # units: hermes-gateway, redis (o paquete), bullmq-workers
│  ├─ .env.example                # PAT, OpenRouter key, Discord tokens, Redis URL — sin valores
│  └─ install-notes.md            # pasos de instalación en el VPS
└─ scripts/                       # utilidades de operación
```

> **Nota de stack para BullMQ:** BullMQ es de origen Node.js y su SDK de referencia es TypeScript; también ofrece SDK de Python. **Decisión a tomar y registrar en Fase 4** (no antes): implementar los workers en TypeScript (SDK maduro, feature-completo) o en Python (homogéneo con el resto de tooling del repo). El plan deja la estructura agnóstica hasta esa fase.

---

## Estrategia de branching
- `main` siempre refleja la configuración desplegada.
- Una **feature branch por fase**: `feat/fX-nombre`. Merge a `main` solo con el checklist de la fase cumplido.
- Cada merge actualiza `HANDOFF.md` y agrega el/los ADR.

---

## Fase 0 — Bootstrap del repo de operaciones

**Objetivo:** dejar el repo `team-agent-ops` inicializado, con estructura, linting y CI mínima, listo para versionar configuración y workers.

**Qué se construye:**
- Repo con `pyproject.toml` (uv), Ruff, estructura de carpetas, pre-commit, CI mínima (lint).
- `deploy/.env.example` con las claves que el proyecto va a necesitar (sin valores): PAT de GitHub, OpenRouter API key, token de bot de Discord, `DISCORD_ALLOWED_USERS`, `REDIS_URL`.
- `docs/runbook.md` esqueleto.

**Decisiones técnicas (con el porqué):**
- **Versionar configuración y workers, no forkear Hermes:** Hermes se opera como dependencia; lo que se versiona es la config (`config.yaml`), los guardrails y las colas/workers de BullMQ. Menor superficie de mantenimiento.

**Archivos/módulos a crear o tocar:** `pyproject.toml`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, estructura de carpetas, `deploy/.env.example`, `docs/runbook.md`, `HANDOFF.md`, `docs/adr/ADR-0001-repo-bootstrap.md`.

**Entregable concreto:** repo que pasa `uv run ruff check` en CI, con estructura y `.env.example` definidos.

**Criterios de validación (checklist):**
- [ ] CI de lint pasa.
- [ ] `.env.example` lista todas las variables necesarias, sin valores.
- [ ] Estructura de carpetas creada según el plan.
- [ ] ADR-0001 commiteado; `HANDOFF.md` inicializado.

**Commit sugerido:** `chore: bootstrap team-agent-ops repo structure and tooling`

**Notas / riesgos:** ninguno relevante en esta fase.

---

## Fase 1 — Hermes vivo en el VPS por Discord (sin acciones sobre GitHub)

**Objetivo:** Hermes corriendo headless y persistente en el VPS, respondiendo por Discord, sin tocar GitHub ni BullMQ todavía.

> **PASOS MANUALES (humano):**
> - Crear el VPS Ubuntu, configurar acceso SSH, instalar dependencias del sistema.
> - Instalar Hermes (`curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash`).
> - Crear la app/bot de Discord, obtener el token, invitar el bot al servidor, y obtener el/los IDs de usuario autorizados.
> - Cargar en `~/.hermes/.env`: OpenRouter API key, token de Discord, `DISCORD_ALLOWED_USERS`.

**Qué se construye/configura:**
- `config/hermes/config.yaml`: proveedor OpenRouter + modelo elegido, canal Discord habilitado, `approvals.mode: manual`.
- Servicio systemd `hermes-gateway` con restart on failure y arranque automático.
- Allowlist de usuarios de Discord (`DISCORD_ALLOWED_USERS`); sin allow-all.

**Decisiones técnicas (con el porqué):**
- **Vivo y persistente antes de cualquier permiso:** se valida la base operativa (sobrevive reboot, responde por Discord, deniega usuarios no autorizados) antes de darle acceso a GitHub.
- **`approvals.mode: manual` desde el inicio:** postura segura por defecto, fail-closed.
- **Allowlist de usuarios explícita:** sin allowlist, Hermes deniega a todos; se configura solo a los usuarios del equipo.

**Archivos/módulos a crear o tocar:** `config/hermes/config.yaml`, `deploy/systemd/hermes-gateway.service`, `deploy/install-notes.md`, `docs/adr/ADR-0002-hermes-deploy.md`.

**Entregable concreto:** Hermes responde desde Discord a un usuario autorizado, deniega a uno no autorizado, y sobrevive un reboot del VPS.

**Criterios de validación (checklist):**
- [ ] El bot responde un mensaje desde Discord a un usuario en la allowlist.
- [ ] Un usuario fuera de la allowlist es denegado.
- [ ] `systemctl restart hermes-gateway` y un reboot del VPS recuperan el servicio sin intervención.
- [ ] Logs accesibles (`~/.hermes/logs/` y/o `journalctl`).
- [ ] Secrets solo en `~/.hermes/.env` con `chmod 600`.
- [ ] ADR-0002 commiteado.

**Commit sugerido:** `feat: deploy hermes gateway on vps with discord channel`

**Notas / riesgos:** correr el gateway como usuario no-root; fijar `terminal.cwd` para que el agente no opere desde directorios sensibles; firewall del VPS.

---

## Fase 2 — Inventario de n8n y mapa de migración

**Objetivo:** mapear todo lo que hace el bot de n8n y decidir, workflow por workflow, su destino.

> **PASO MANUAL (humano):** exportar/documentar los workflows de n8n (qué los dispara, qué hacen, su salida, frecuencia, criticidad) en `docs/n8n-inventory.md` o como JSONs exportados.

**Qué se construye:**
- `docs/n8n-inventory.md`: tabla por workflow (trigger / acción / salida / frecuencia / criticidad).
- Decisión explícita por workflow: (a) capacidad agéntica de Hermes, (b) job de BullMQ (determinístico/recurrente), o (c) descartar con justificación.
- **Criterio de cutover** (condiciones objetivas para apagar n8n) y lista de "lo que vale la pena conservar".

**Decisiones técnicas (con el porqué):**
- **Inventariar antes de migrar:** evita reimplementar features muertas y apagar n8n sin paridad.
- **Determinístico → BullMQ; criterio → Hermes:** notificaciones y plomería recurrente como jobs de BullMQ (confiable, reintentable, testeable); resumen/triage como capacidad agéntica.

**Archivos/módulos a crear o tocar:** `docs/n8n-inventory.md`, `docs/adr/ADR-0003-migration-map.md`.

**Entregable concreto:** tabla de migración cerrada + criterio de cutover escrito.

**Criterios de validación (checklist):**
- [ ] Cada workflow con destino asignado y justificado.
- [ ] Escrito qué se conserva y qué se descarta (y por qué).
- [ ] Criterio de cutover objetivo y verificable.
- [ ] ADR-0003 commiteado.

**Commit sugerido:** `docs: inventory n8n workflows and define migration map`

**Notas / riesgos:** marcar workflows desconocidos/no exportados como bloqueantes del cutover; no asumir que no existen.

---

## Fase 3 — MVP end-to-end: el agente comenta un PR (approval de publicación + allowlist de repos)

**Objetivo:** primer flujo real sobre GitHub, mínimo, con los guardrails de negocio desde el día uno.

> **PASOS MANUALES (humano):**
> - Generar el **PAT de GitHub** scopeado: lectura de repos/PRs/issues + escritura de comentarios. Sin merge/push/force-push.
> - Cargar el PAT en `~/.hermes/.env` y definir la **allowlist de repos** en `config/guardrails/`.

**Qué se construye/configura:**
- Conexión del MCP de GitHub en `config/hermes/config.yaml` (`mcp_servers.github` con el PAT por `env`).
- **Allowlist de repos** como guardrail de negocio: el agente solo actúa sobre repos de la lista. Se valida en el worker (capa determinística), no en el LLM.
- **Approval gate de publicación:** como el approval nativo de Hermes cubre comandos de shell y no la tool MCP de comentar, el comentario propuesto se encola en BullMQ en estado `pending-approval`; un usuario autorizado lo aprueba desde Discord (yes/no); recién entonces el worker ejecuta el posteo.
- **Worker `post-comment`** en BullMQ: consume el job aprobado, postea vía GitHub, con **idempotencia** (clave `repo+pr+content_hash`) y reintentos con backoff.
- **Logging** de cada acción: qué tool, sobre qué repo/PR, input, resultado.

**Decisiones técnicas (con el porqué):**
- **Approval y allowlist antes que cualquier feature:** publicar algo incorrecto en un PR real cuesta confianza; los guardrails van primero.
- **Approval de publicación a nivel de orquestación:** el approval nativo de Hermes no cubre acciones MCP, así que se implementa explícitamente vía el estado `pending-approval` en la cola.
- **PAT scopeado:** defensa en profundidad; aunque algo falle, el token no puede mergear ni pushear.
- **Allowlist en el worker, no en el LLM:** a qué repo se puede escribir es una decisión determinística.
- **Idempotencia en BullMQ desde el MVP:** un agente 24/7 con reintentos puede duplicar; la clave de idempotencia y la deduplicación de BullMQ lo previenen.

**Archivos/módulos a crear o tocar:** `config/hermes/config.yaml` (mcp github), `config/guardrails/repo-allowlist.*`, `queue/queues.*`, `queue/workers/post-comment.*`, `queue/jobs/` (tipo + idempotencia), `docs/adr/ADR-0004-github-guardrails.md`.

**Entregable concreto:** en un repo de la allowlist, el agente lee un PR, propone un comentario, espera aprobación por Discord, y un worker BullMQ lo postea; reintentar no duplica.

**Criterios de validación (checklist):**
- [ ] Acción sobre repo fuera de la allowlist: rechazada por el worker (test).
- [ ] Ningún comentario se postea sin aprobación explícita por Discord.
- [ ] Reintentar el mismo job no duplica el comentario (test de idempotencia).
- [ ] El PAT no puede mergear/pushear (verificado por scope).
- [ ] Cada acción queda logueada.
- [ ] ADR-0004 commiteado.

**Commit sugerido:** `feat: comment on prs via approval-gated bullmq worker with repo allowlist`

**Notas / riesgos:** este es el punto donde BullMQ entra; mantenerlo mínimo (una cola, un worker) y crecer después.

---

## Fase 4 — Infra de cola durable: Redis + BullMQ como servicios

**Objetivo:** formalizar BullMQ y Redis como servicios de producción en el VPS, con reintentos, backoff, rate limiting y observabilidad de la cola.

> **PASO MANUAL (humano):** instalar Redis en el VPS (o proveer una instancia gestionada) y cargar `REDIS_URL` en el entorno.

**Qué se construye/configura:**
- Servicios systemd: Redis (si es self-hosted) y `bullmq-workers`.
- Política de reintentos con **backoff exponencial** y **dead letter** para jobs que agotan intentos.
- **Rate limiting** por cola (proteger la API de GitHub y el costo de LLM).
- **Decisión registrada:** workers en TypeScript (SDK de referencia) vs Python (homogéneo con el repo). Documentar en ADR.

**Decisiones técnicas (con el porqué):**
- **Cola durable respaldada por Redis:** el trabajo sobre GitHub y lo recurrente debe sobrevivir reinicios y reintentarse ante fallos transitorios; una cola persistente lo garantiza mejor que ejecución in-process.
- **Backoff + dead letter:** un fallo transitorio (rate limit de GitHub, corte de red) no debe perder el job ni martillar la API.
- **Rate limiting por cola:** controla costo de LLM y límites de la API de GitHub de forma determinística.
- **Elección de lenguaje de workers explícita:** el SDK Python de BullMQ ha ido por detrás del de Node; se decide con criterio y se documenta, no por inercia.

**Archivos/módulos a crear o tocar:** `deploy/systemd/redis.service` (si aplica), `deploy/systemd/bullmq-workers.service`, `queue/queues.*` (retry/backoff/limiter), `queue/workers/` (dead letter), `docs/adr/ADR-0005-queue-infra.md`, `docs/runbook.md` (operación de la cola).

**Entregable concreto:** Redis + workers BullMQ corriendo como servicios; un job que falla se reintenta con backoff y, si agota intentos, va a dead letter; ambos sobreviven reboot.

**Criterios de validación (checklist):**
- [ ] Un job que falla transitoriamente se reintenta con backoff (test).
- [ ] Un job que agota intentos va a dead letter, no se pierde ni reintenta infinito.
- [ ] Rate limiting de la cola activo y verificado.
- [ ] Redis y workers sobreviven un reboot del VPS.
- [ ] ADR-0005 (incluye decisión de lenguaje de workers) commiteado.

**Commit sugerido:** `feat: run redis and bullmq workers as services with retry, backoff and rate limiting`

**Notas / riesgos:** asegurar Redis (bind local, password, no exponer puerto); el dead letter necesita un mecanismo de revisión/alerta documentado en el runbook.

---

## Fase 5 — Capacidades: triage de issues + lectura de documentación

**Objetivo:** sumar las capacidades de criterio sobre la base ya endurecida.

**Qué se construye/configura:**
- **Triage de issues:** el agente lee un issue, propone labels/prioridad y un comentario; la publicación pasa por el mismo approval-gate + worker BullMQ de la Fase 3.
- **Lectura de documentación del repo:** el agente usa la documentación como contexto, aprovechando la memoria persistente de Hermes; resumir para controlar costo/tokens.

**Decisiones técnicas (con el porqué):**
- **Después del MVP y la infra de cola:** sin approval, allowlist, idempotencia y dead letter probados, sumar criterio del LLM sería sumar riesgo.
- **Triage propone, no decide:** la publicación sigue gateada por aprobación.
- **Memoria de Hermes para docs:** se usa la capacidad nativa en vez de construir un store propio.

**Archivos/módulos a crear o tocar:** `queue/workers/triage-publish.*`, `config/hermes/config.yaml` (tool de lectura de docs / contexto), `docs/adr/ADR-0006-capabilities.md`.

**Entregable concreto:** el agente triage un issue real (con aprobación por Discord, publicado vía worker) usando la documentación del repo como contexto.

**Criterios de validación (checklist):**
- [ ] Triage y lectura de docs solo sobre repos de la allowlist.
- [ ] Toda salida visible pasa por aprobación.
- [ ] Acciones logueadas.
- [ ] ADR-0006 commiteado.

**Commit sugerido:** `feat: add issue triage and repo docs reading`

**Notas / riesgos:** controlar el tamaño de contexto al leer docs; resumir en vez de volcar todo.

---

## Fase 6 — Digest diario como job recurrente de BullMQ + paridad con n8n

**Objetivo:** cubrir la plomería recurrente que hacía n8n con **job schedulers de BullMQ**, y alcanzar paridad funcional.

**Qué se construye/configura:**
- **Digest diario** (resumen de PRs/issues del día) como **job scheduler de BullMQ** (cron expression), entregado al canal de Discord.
- Las demás notificaciones recurrentes que el inventario (Fase 2) marcó conservar, como jobs recurrentes.
- **Idempotencia del digest:** la semántica upsert/deduplicación de BullMQ evita doble-envío ante reinicios cerca de la hora de disparo.
- Verificación de **paridad** ítem por ítem contra la tabla de la Fase 2.

**Decisiones técnicas (con el porqué):**
- **Scheduling en BullMQ, un solo mecanismo:** ya que el trabajo durable vive en la cola, los recurrentes también; se evita tener cron de Hermes y cron de BullMQ en paralelo. (Si algún recurrente puramente conversacional conviene en el cron nativo de Hermes, se documenta la excepción.)
- **Paridad explícita antes del cutover:** se chequea lo que la Fase 2 marcó conservar.

**Archivos/módulos a crear o tocar:** `queue/jobs/digest.*`, `queue/workers/digest.*`, `queue/queues.*` (scheduler), `docs/adr/ADR-0007-scheduling-and-parity.md`.

**Entregable concreto:** digest diario disparándose solo en el VPS y entregado a Discord + checklist de paridad con n8n cumplido.

**Criterios de validación (checklist):**
- [ ] El digest se dispara solo a la hora configurada (zona horaria fijada explícitamente).
- [ ] Un reinicio cerca de la hora no duplica el digest del día.
- [ ] Cada ítem "a conservar" de la Fase 2 tiene su equivalente funcionando.
- [ ] ADR-0007 commiteado.

**Commit sugerido:** `feat: add daily digest as recurring bullmq job and reach n8n parity`

**Notas / riesgos:** fijar la zona horaria explícitamente (VPS vs equipo).

---

## Fase 7 — Cutover: deshabilitar n8n (sin eliminar) → baja definitiva

**Objetivo:** retirar n8n en dos tiempos para que el cutover sea reversible hasta confirmar estabilidad.

> **PASO MANUAL (humano):** primero **deshabilitar** (no eliminar) los workflows de n8n; tras el período de observación, dar de baja la instancia. Guardar un export final antes de la baja.

**Qué se hace:**
- Checklist final de cutover ejecutado y firmado en el ADR.
- **Período de observación** (definido en la Fase 2) con n8n deshabilitado pero recuperable; al final se elimina.

**Decisiones técnicas (con el porqué):**
- **Cutover en dos tiempos:** deshabilitar primero deja un rollback real durante la ventana de observación; eliminar es irreversible.
- **Por criterio objetivo:** se avanza solo cumpliendo las condiciones de la Fase 2.

**Archivos/módulos a crear o tocar:** `docs/adr/ADR-0008-cutover.md`, `HANDOFF.md`.

**Entregable concreto:** n8n deshabilitado y luego retirado; Hermes + BullMQ son el único sistema.

**Criterios de validación (checklist):**
- [ ] Criterios de cutover de la Fase 2 cumplidos y verificados.
- [ ] n8n deshabilitado (recuperable) durante la ventana de observación.
- [ ] Export final guardado antes de la baja.
- [ ] Baja sin dependencia residual.
- [ ] ADR-0008 commiteado.

**Commit sugerido:** `chore: cutover to hermes and decommission n8n`

**Notas / riesgos:** comunicar al equipo la ventana de observación y el canal para reportar fallos.

---

# Resumen de PASOS MANUALES (humano) — Claude Code NO los ejecuta
1. (Fase 1) Crear el VPS Ubuntu, SSH, instalar deps, instalar Hermes, cargar OpenRouter key.
2. (Fase 1) Crear el bot de Discord, token, invitarlo, obtener IDs de usuarios autorizados.
3. (Fase 2) Exportar/documentar los workflows de n8n.
4. (Fase 3) Generar el PAT de GitHub scopeado (lectura + comentarios; sin merge/push) y definir la allowlist de repos.
5. (Fase 4) Instalar Redis en el VPS (o proveer instancia gestionada) y cargar `REDIS_URL`.
6. (Fase 7) Deshabilitar y luego dar de baja n8n.

# Supuestos explícitos
- Proveedor de LLM: OpenRouter (API key en `~/.hermes/.env`); modelo concreto a fijar en Fase 1.
- Canal de entrada: Discord.
- Volumen: bot interno de equipo. BullMQ se usa por durabilidad y reintentos, no por throughput extremo; arranca mínimo (una cola, un worker) y crece según necesidad.
- Hermes se usa tal cual y se versiona la configuración + las colas/workers; solo se extendería Hermes si una tool de dominio lo exigiera (decisión a registrar en un ADR si ocurre).

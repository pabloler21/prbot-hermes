# Inventario de workflows de n8n

Tabla de workflows activos en n8n, con su destino en la migración a Hermes + BullMQ.

> **Nota:** los workflows fueron reconstruidos a partir del conocimiento del equipo
> (no exportados directamente desde n8n). Se consideran completos a efectos de esta fase.

---

## Tabla de workflows

| # | Nombre | Trigger | Acción | Salida | Frecuencia | Criticidad |
|---|--------|---------|--------|--------|------------|------------|
| 1 | Daily PR Digest | Cron 09:00 | Lista PRs abiertos que necesitan review en todos los repos del equipo | Mensaje en `#dev` con tabla de PRs: título, autor, días abierto, link | Diaria (lunes–viernes) | Alta — el equipo depende de esto para organizar el día |
| 2 | New Issue Alert | Poll GitHub cada 5 min | Detecta issues nuevos en repos del equipo | Mensaje en `#dev` con título, autor, labels, link | Cuasi-tiempo-real | Media — útil pero tolera demora de minutos |
| 3 | Stale PR Alert | Cron 10:00 | Detecta PRs sin actividad (sin commit, comment ni review) por más de 3 días | Mensaje en `#dev` listando los PRs estancados | Diaria (lunes–viernes) | Media — evita que PRs queden olvidados |
| 4 | Weekly Summary | Cron viernes 18:00 | Cuenta PRs mergeados e issues cerrados en la semana | Mensaje en `#dev` con resumen de la semana (métricas y links) | Semanal | Baja — informativo, no bloquea operación |
| 5 | Deploy Notification | Poll merges a `main` cada 5 min | Detecta cuando un PR es mergeado a `main` | Mensaje en `#dev` con título del PR, autor, link al merge | Cuasi-tiempo-real | Alta — el equipo necesita saber cuándo hay un deploy |

---

## Decisión de migración por workflow

### 1 · Daily PR Digest → **BullMQ job scheduler**

Trabajo completamente determinístico: consultar la API de GitHub, formatear los datos,
postear en Discord. No requiere razonamiento del LLM. Se implementa como job scheduler
de BullMQ con cron expression `0 9 * * 1-5` (lunes a viernes a las 9:00 UTC-3).

### 2 · New Issue Alert → **BullMQ job scheduler (poll)**

Sin webhook disponible (el PAT del equipo es de solo lectura; registrar un webhook
requiere permisos de admin sobre el repo). Se implementa como job recurrente que
consulta la API de GitHub cada 5 minutos y filtra issues creados desde la última
ejecución. La clave de idempotencia es `repo+issue_number` para evitar doble-notificación.

### 3 · Stale PR Alert → **BullMQ job scheduler**

Determinístico: listar PRs abiertos, filtrar por `updated_at < now - 3 días`, postear.
Cron expression `0 10 * * 1-5`. No requiere razonamiento; la definición de "estancado"
es objetiva y configurable.

### 4 · Weekly Summary → **BullMQ job scheduler**

Determinístico: consultar PRs mergeados e issues cerrados en los últimos 7 días,
agregar métricas, postear. Cron expression `0 18 * * 5` (viernes 18:00 UTC-3).
Baja criticidad; si falla un viernes se pierde ese resumen (aceptable; no se reintenta
la semana siguiente).

### 5 · Deploy Notification → **BullMQ job scheduler (poll)**

Misma razón que el New Issue Alert: sin webhook se usa poll. Job recurrente cada 5 min
que detecta PRs mergeados a `main` desde la última ejecución. Clave de idempotencia:
`repo+pr_number+merged_at`. Alta criticidad → 3 reintentos con backoff exponencial.

---

## Capacidad nueva (no viene de n8n)

### PR Assistant / CI Debug Helper → **Hermes agentivo (Fase 5)**

El equipo puede preguntarle a Hermes en Discord sobre una PR específica: leer el código,
analizar qué test falló en CI, sugerir el fix. Esto no es migración de n8n sino una
capacidad nueva que justifica el upgrade. Se implementa en Fase 5 cuando el MCP de
GitHub y los guardrails ya estén probados.

---

## Qué se conserva y qué se descarta

**Se conserva (los 5 workflows):** todos aportan valor activo al equipo. Ninguno se descarta.

**Se descarta:** ningún workflow existente. Si durante la implementación alguno resulta
redundante con la capacidad agéntica de Hermes, se documenta en el ADR de la fase
correspondiente.

---

## Criterio de cutover (condiciones para apagar n8n)

Todas las condiciones deben cumplirse antes de deshabilitar n8n:

1. Los 5 workflows equivalentes están desplegados en producción y corriendo en BullMQ.
2. Cada workflow funcionó sin errores durante **7 días calendario consecutivos**.
3. No hay falsos negativos conocidos (notificaciones que n8n enviaba y el nuevo sistema no).
4. El dead letter de BullMQ está configurado y monitoreado (jobs fallidos no se pierden silenciosamente).
5. El equipo fue notificado con al menos 48 horas de anticipación.
6. Existe un export final de los workflows de n8n guardado en `docs/n8n-export/` antes de la baja.

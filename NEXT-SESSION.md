# Cómo seguimos la próxima sesión

> Archivo personal para retomar. Leelo vos; el mensaje para Claude está abajo.

## Qué mensaje darle a Claude cuando vuelvas

Copiá y pegá esto:

> Retomamos el proyecto Hermes. Estábamos en la Fase 3: 3a (GitHub MCP solo-lectura)
> quedó completa y validada en la rama `feat/f3-github-mvp`. Falta la 3b (camino de
> escritura: worker de BullMQ + approval gate por Discord), que está bloqueada por Redis.
> Leé `HANDOFF.md` y `CLAUDE.md` para el estado actual, y arranquemos instalando Redis
> en el VPS para desbloquear la 3b. Explicame cada paso, que estoy aprendiendo.

## Dónde quedamos (resumen)

- ✅ **Fase 0** — repo bootstrapeado (mergeado a `main`).
- ✅ **Fase 1** — Hermes vivo en Discord, validado en el VPS (mergeado a `main`).
- ✅ **Fase 2** — inventario de n8n + mapa de migración (mergeado a `main`).
- ✅ **Fase 3a** — MCP de GitHub en solo-lectura, validado. Rama `feat/f3-github-mvp`
  (NO mergeada todavía: la Fase 3 cierra recién con la 3b).
- ⏳ **Fase 3b** — escritura con approval gate. **Bloqueada por: Redis no instalado.**

## Lo próximo (Fase 3b / 4) — necesita un PASO MANUAL tuyo

Para desbloquear hay que **instalar Redis en el VPS** (paso manual). Claude te va a guiar
comando por comando, pero la idea general es:

1. Instalar Redis en el VPS (`sudo apt install redis-server`).
2. Asegurarlo: bind local (127.0.0.1), con password, sin exponer el puerto afuera.
3. Cargar `REDIS_URL` en `~/.hermes/.env`.
4. Recién ahí construimos el primer worker de BullMQ (`post-comment`) con approval gate.

## Datos útiles del VPS

- Conexión: `ssh ubuntu@137.131.202.213`
- Ver estado del bot: `sudo systemctl status hermes-gateway`
- Más comandos: ver `CHEATSHEET.md`

## Estado de Git

- `main`: Fases 0, 1 y 2.
- `feat/f3-github-mvp`: Fase 3a commiteada, pendiente de completar con 3b antes de mergear.

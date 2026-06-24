# Runbook de cutover — retiro de n8n

> **Nota de alcance (importante y honesta):** en este proyecto **n8n es simulado** (el autor
> no tiene una instancia real; el inventario de la Fase 2 fue reconstruido como si fuera real
> para el portfolio). Por lo tanto este documento es el **procedimiento ejecutable** que un
> equipo seguiría con un n8n real, + la **evidencia de paridad** ya alcanzada. No se ejecuta un
> apagado fingido: el valor está en el método y en poder defenderlo. Ver ADR-0011.

El cutover se hace **en dos tiempos** para que sea **reversible** hasta confirmar estabilidad:
**deshabilitar (recuperable) → observar → dar de baja (irreversible)**.

---

## 1. Pre-requisitos: criterios de cutover (de la Fase 2)

Todos deben cumplirse **antes** de deshabilitar n8n. Estado actual:

| # | Criterio | Estado |
|---|----------|--------|
| 1 | Los 5 workflows equivalentes desplegados y corriendo en arq | ✅ Fases 6a/6b, en el VPS |
| 2 | Cada workflow corrió sin errores **7 días calendario** consecutivos | ⏳ ventana de observación (abajo) |
| 3 | Sin falsos negativos conocidos (algo que n8n avisaba y el nuevo no) | ✅ paridad ítem-por-ítem (Fase 2) |
| 4 | Dead-letter de arq configurado y monitoreado | ✅ Fase 4 (DLQ por task + runbook) |
| 5 | Equipo notificado con ≥48 h de anticipación | ⏳ paso manual (comunicación) |
| 6 | Export final de los workflows de n8n guardado en `docs/n8n-export/` | ⏳ paso manual (antes de la baja) |

**Evidencia de paridad (criterios 1 y 3):** mapeo 1-a-1 inventario → arq, todos validados en vivo:

| Workflow n8n | Equivalente en arq | Validado |
|---|---|---|
| Daily PR Digest | `daily_pr_digest` (cron lun-vie 09:00) | ✅ disparo automático |
| Stale PR Alert | `stale_pr_alert` (cron lun-vie 10:00) | ✅ (calla si no hay estancados) |
| Weekly Summary | `weekly_summary` (cron vie 18:00) | ✅ disparo manual |
| New Issue Alert | `new_issue_alert` (poll 5 min) | ✅ issue #9, una sola vez |
| Deploy Notification | `deploy_notification` (poll 5 min) | ✅ merge #8 automático |

---

## 2. Tiempo 1 — Deshabilitar n8n (reversible)

> **PASO MANUAL (humano).** Con n8n real:

1. **Comunicar al equipo** (≥48 h antes): canal, fecha/hora del cutover, y a dónde reportar si
   algo dejó de llegar (criterio #5).
2. **Guardar el export final** de todos los workflows de n8n en `docs/n8n-export/` (criterio
   #6). Es el seguro para reconstruir si hiciera falta.
3. **Deshabilitar** (no eliminar) los 5 workflows en n8n. Quedan inactivos pero **recuperables**.
4. Confirmar que arq es ahora la **única** fuente de cada notificación (no hay doble-envío de
   n8n + arq en paralelo).

**Estado deseado al final del Tiempo 1:** n8n apagado pero recuperable; arq cubriendo todo.

---

## 3. Ventana de observación (criterio #2)

**7 días calendario** con n8n deshabilitado y arq como único sistema. Durante la ventana:

- Revisar a diario que las notificaciones llegan (digest, alertas, resúmenes, deploys).
- Revisar el **dead-letter** (criterio #4): `redis-cli -u "$REDIS_URL" llen dead-letter:<task>`
  para cada task; cualquier entrada se investiga (ver `docs/runbook.md`).
- Llevar registro de cualquier falso negativo reportado por el equipo.

**Rollback (si algo falla en la ventana):** como n8n quedó *deshabilitado, no eliminado*, se
**re-habilitan** sus workflows (revertir el Tiempo 1, paso 3) y se diagnostica el equivalente
arq con calma. El rollback es inmediato porque no se borró nada.

---

## 4. Tiempo 2 — Baja definitiva (irreversible)

> **PASO MANUAL (humano).** Solo si la ventana de 7 días cerró **sin errores ni falsos
> negativos**:

1. Verificar una última vez que el export final está guardado (`docs/n8n-export/`).
2. **Dar de baja** la instancia de n8n (eliminar workflows / apagar el servicio / liberar el
   recurso).
3. Confirmar que **no quedan dependencias residuales** apuntando a n8n (crons, tokens, webhooks).
4. Anunciar al equipo que el cutover está completo.

**Estado final:** Hermes + arq/Redis son el **único** sistema. n8n retirado.

---

## 5. Checklist de cierre (firmar en el ADR)

- [ ] Criterios 1–6 de la Fase 2 cumplidos y verificados.
- [ ] n8n deshabilitado (recuperable) durante la ventana de observación.
- [ ] 7 días sin errores ni falsos negativos.
- [ ] Export final guardado en `docs/n8n-export/`.
- [ ] Baja ejecutada sin dependencias residuales.
- [ ] ADR-0011 actualizado y firmado.

> En este proyecto (n8n simulado): los pasos manuales de deshabilitar/observar/dar de baja se
> dejan **documentados como ejecutables**; lo que sí está hecho y validado es la **paridad**
> (sección 1). Si el n8n fuera real, este runbook se ejecuta tal cual.

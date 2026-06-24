# ADR-0011 — Cutover: retiro de n8n (documentado; n8n simulado)

- **Estado:** aceptado
- **Fase:** 7
- **Fecha:** 2026-06-24

> **Nota de numeración:** el plan rotula esta fase como "ADR-0008", pero 0008/0009/0010 ya
> estaban usados por la evolución real. Este toma el próximo libre, 0011.

## Contexto

Cerradas las Fases 6a/6b, los 5 workflows del inventario (Fase 2) tienen su equivalente en
arq, todos desplegados en el VPS y **validados en vivo** (varios disparándose solos). Con eso
se alcanza **paridad funcional con n8n**, que es la precondición del cutover (Fase 7).

El matiz que define esta fase: **n8n es simulado**. El autor no tiene una instancia real; el
inventario se reconstruyó como si lo fuera, para el portfolio. Por lo tanto no hay un sistema
físico que apagar.

## Decisión

**1. La Fase 7 entrega el *procedimiento* de cutover + la *evidencia* de paridad, no un apagado
fingido.** Se documenta `docs/cutover.md`: un runbook ejecutable (criterios, dos tiempos,
ventana de observación, rollback, comunicación) que un equipo seguiría con un n8n real, y la
tabla de paridad 1-a-1 con su validación. Se es **explícito** sobre la simulación: honestidad
> espectáculo.

**2. Cutover en dos tiempos (cuando sea real): deshabilitar → observar 7 días → dar de baja.**
- **Deshabilitar (no eliminar)** deja un **rollback inmediato** durante la ventana: re-habilitar
  los workflows de n8n revierte el cambio sin haber perdido nada.
- **Eliminar es irreversible** → solo tras 7 días sin errores ni falsos negativos, y con el
  **export final** guardado (`docs/n8n-export/`).

**3. Avanzar solo por criterio objetivo.** Los 6 criterios de la Fase 2 (paridad, 7 días sin
errores, sin falsos negativos, DLQ monitoreado, equipo avisado 48 h, export guardado) son la
condición de salida. Nada de "parece que anda".

## Alternativas consideradas

- **Apagar n8n de un solo tiempo (big-bang).** Más rápido pero sin red: si algo falla, no hay
  rollback barato. Descartado; el riesgo no vale el ahorro.
- **Mantener n8n y arq en paralelo indefinidamente.** Doble fuente de notificaciones (ruido,
  doble-envío) y dos sistemas que mantener. Contradice el objetivo de retirar n8n.
- **Fingir un apagado real en el demo.** Deshonesto y menos defendible que documentar el método
  y admitir la simulación. Descartado.

## Consecuencias

- Nuevo `docs/cutover.md` (runbook) + este ADR. Cierra el roadmap del plan.
- **Estado del proyecto: COMPLETO** (Fases 0–7). Hermes + arq/Redis es el sistema; el cutover
  queda documentado como ejecutable si n8n fuera real.
- Los pasos manuales reales (deshabilitar, observar, dar de baja, guardar export) quedan
  claramente marcados como **PASO MANUAL (humano)** — Claude Code no los ejecuta.
- Si en el futuro hubiera un n8n real, el runbook se corre tal cual; la paridad ya está probada.

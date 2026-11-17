# Fase 8 — Orden de trabajo (punto de entrada)

> **Para quién:** un agente que ejecute el trabajo de Fase 8 que **no** es calibración. Este
> archivo dice qué hacer, en qué orden y qué está fuera de alcance. Los detalles técnicos están
> en los documentos a los que apunta; este no los repite. Si hay conflicto de lectura entre
> este archivo y un documento referenciado, gana el documento referenciado en lo técnico y este
> en el alcance.

---

## Orden de trabajo

1. **Implementar `stop_after`** — seguir [`calibracion_stop.md`](calibracion_stop.md).
   - **Sí:** parámetro en el orquestador, `PIPELINE_STOP_AFTER_STAGE` en `config.py`, wiring en
     `pipeline_runs.py` y tests en `tests/test_pipeline.py` (ver §Cambios en código y §Pruebas).
   - **No calibrar:** no afinar P4/P5, no correr el pipeline en documentos reales, no
     interpretar resultados. Es una capacidad del orquestador, no una calibración (ver el aviso
     de alcance del propio `calibracion_stop.md`).

2. **Crear las pruebas de integración** — seguir [`fase8.md`](fase8.md).
   - **Sí:** markers + gating en `pytest.ini`, fixture de cliente Supabase real, happy path y
     caminos de error de las cuatro RPC, máquina de estados, `summary`, `delete_generation_if_final`.
   - **No:** E2E con Ollama ni pruebas del comportamiento del LLM (otra capa, fuera del alcance
     de `fase8.md`).

## Fuera de alcance (manual, después)

La **calibración misma**: ejecutar el pipeline sobre documentos reales, ajustar
`P4_MIN_CLUSTER_SIZE` / `P4_MIN_SAMPLES` / `P5_MAX_TOKENS_PER_UNIT`, comparar `by_user_story`
vs `by_cluster` y rellenar `docs/calibracion_resultados/iteracion_1.md`. Los valores de
calibración son **manuales** y quedan fuera de este encargo. Los hace un humano (o un agente
específico de calibración) usando la capacidad `stop_after` una vez exista.

## Notas

- Las tareas 1 y 2 son **independientes**: pueden intercambiarse o hacerse en paralelo. Lo fijo
  es que la calibración va al final y **no** está en este encargo.
- La tarea 2 tiene un **requisito abierto** sin resolver: el aislamiento de Supabase
  (`fase8.md` D-F8-3 — proyecto aparte o `generation_id` propios con borrado en cascade).
  Hasta decidirlo, los tests no se ejecutan contra el proyecto real; pueden quedar escritos y
  `skip` por defecto. Mientras tanto, la tarea 1 puede avanzar sin ese bloqueo.
- La tarea 1 **no tiene bloqueos**: puede empezar de inmediato.
- Cada documento tiene su sección **Criterios de cierre**: el trabajo de cada tarea termina
  cuando se cumplen los suyos y la suite rápida (`pytest`, sin flags) sigue verde.

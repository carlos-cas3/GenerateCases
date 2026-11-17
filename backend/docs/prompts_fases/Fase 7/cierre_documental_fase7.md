# Cierre documental — Fase 7 (P6 generación de casos de prueba)

> **Estado:** ✅ implementación cerrada en código y pruebas (529 tests pasan; antes de la fase
> eran 499). Pendiente **fuera de código**: la primera iteración de calibración con el pipeline
> real (Ollama + Supabase), ver §6.
> **Alcance:** T-F7-01 … T-F7-08 de [`fase7.md`](fase7.md) e [`impacto_fase7.md`](impacto_fase7.md).

---

## 1. Verificación previa

| Comprobación | Resultado |
|---|---|
| Suite completa antes de tocar código | ✅ 499 pasan |
| Contrato `P6Input / P6LlmResponse / P6Output / TestCase / P6Config` (Fase 3) | ✅ existía; se modificó en T-F7-01 |
| RPC `persist_p6_unit` en `schema.sql` | ✅ existía (desplegada 2026-11-11); faltaba el caller |
| Columna `generations.summary` en `schema.sql` | ✅ ya estaba en las migraciones aditivas |
| `PipelineContext.p6_output` | ❌ no existía → añadido |
| Env vars `P6_*` | ❌ no existían → creadas en T-F7-02 |
| `docs/calibracion_variables.md`, `docs/calibracion_resultados/` (citados como fuente) | ❌ no existían; se creó `calibracion_resultados/` con la plantilla (§6) |

---

## 2. Qué se implementó

| Tarea | Archivos | Resumen |
|---|---|---|
| T-F7-01 contrato | `pipeline/contracts/p6.py` | `P6Output.failed_units` sin `max_length=1` (sí exige `unit_id` únicos). `P6Config.on_unit_failure: Literal["continue"]`, más `failure_threshold`, `max_cases_multiplier`, `max_cases_absolute` y `max_cases_for(n)`. |
| T-F7-02 config | `config.py`, `.env`, `.env.example`, `pipeline/stages/__init__.py` | Las 5 variables `P6_*`. `build_p6_config(settings)`; `build_llm_settings(settings, stage)` compartido por P2/P6 (misma validación de `LLM_MODEL`). |
| T-F7-06 prompts | `prompts/texts/contexto.md`, `contexto_sin_clustering.md` | Reescritos para ser equivalentes (§4). `P6_PROMPT_VERSION=v2`. |
| T-F7-03 P6 | `pipeline/stages/p6_generation.py`, `pipeline/stages/llm_output.py`, `pipeline/context.py` | `GenerationStage` real + `GenerationStubStage`. Saneo de la salida del LLM (code fence, `""` en listas) extraído de P2 a `llm_output.py` y reutilizado. Ver §3. |
| T-F7-04 persistencia | `repositories/pipeline_results.py`, `supabase_pipeline_results.py`, `in_memory.py` | `persist_p6_unit` en puerto, adaptador (`_call` existente, mismos errcodes) y fake (`InMemoryStore.test_cases`, idempotente por `(generation_id, code)`, FK de `requirement_codes`, `23502` si falta `id`). |
| T-F7-05 summary | `schemas/generations.py`, `schemas/records.py`, `repositories/generations.py`, `supabase_generations.py`, `in_memory.py`, `services/pipeline_runs.py`, `services/generations.py`, `docs/openapi.yaml` | `GenerationSummary` con los 5 campos de D-F7-8 (se retiran `invalid_user_stories_count`, `validated_relations_count`, `metrics` → P7). `build_summary` / `update_summary`. `RepositoryProgressReporter` lo escribe en `pipeline_completed`. |
| T-F7-07 pruebas | `tests/test_p6_generation.py` (19), `tests/test_stages_wiring.py` (+10, 3 extendidos), `tests/test_contracts_invariants.py` (+1, 2 reescritos), `tests/test_generations_api.py` (1 extendido) | Ver §5. |
| T-F7-08 docs | `docs/pipeline_roadmap.md`, `fase7.md`, este archivo, `docs/calibracion_resultados/` | Fase 7 ✅; `PENDING_STUB_STAGE_CLASSES = (EvaluationStage,)`; comentarios de `PIPELINE_STAGES` (P1–P6 reales). |

---

## 3. Decisiones y supuestos tomados en la implementación

1. **Umbral superado → `StageError`, no `skip_remaining` (T-F7-03 paso 5).** El paso 5 del plan
   decía "`skip_remaining=True` con error `GENERATION_THRESHOLD_EXCEEDED`", pero `skip_remaining`
   deja la generación `completed`, y D-F7-2, los criterios de cierre y las pruebas exigen `failed`.
   Se lanza `StageError("GENERATION_THRESHOLD_EXCEEDED", retryable=True)`: P6 queda `failed`, P7
   `pending` y la generación `failed` (P6 es bloqueante). `details` lleva fallidas, total y umbral.
2. **Orden umbral → persistencia y numeración al persistir (D-F7-6, D-F7-7).** Se procesan todas
   las unidades con el LLM; se evalúa el umbral **antes** de persistir (si se supera no se escribe
   nada); luego se persiste unidad a unidad y el contador `CP-xxx` solo avanza cuando la RPC
   confirma. Así, si la persistencia de una unidad falla (T-F7-03 paso 6: pasa a `failed_units`),
   la siguiente reutiliza sus códigos y la numeración sigue sin saltos (`P6Output._consistent`).
   Tras fallos de persistencia el umbral se reevalúa (advertencia 11 del roadmap).
3. **Truncado antes de validar (D-F7-4).** Se parsea el JSON, se recorta `test_cases` al tope y se
   valida con `P6LlmResponse.model_validate_json(..., context={"target_codes": ...})` (R-CP-4). Un
   caso inválido más allá del tope no invalida la unidad (hay prueba).
4. **Reintentos (D-F7-5).** Igual que P2: JSON inválido o `LlmError` transitorio → reintento (con
   espera solo en errores del proveedor). Diferencia con P2: agotar reintentos **no** lanza
   `StageError`; la unidad queda en `failed_units` (`LLM_INVALID_OUTPUT` / `LLM_UNAVAILABLE`).
   `LLM_CONTEXT_LENGTH` no se reintenta y también es fallo de unidad (D-F7-1), no de etapa.
5. **Mensaje al LLM.** `system` = `.md` tal cual; `prompt` = tope de casos, RF objetivo (`code` +
   `description`), RF de contexto solo si hay (sección "no enlazar"), HU de origen (`code`,
   `original_text`, `role`, `objective`, `benefit`, `content_sections`) y el JSON Schema de
   `output_spec`. El `label` de la unidad (`"Cluster N"`) **no** se envía (advertencia heredada 4).
6. **`summary` (D-F7-8).** `build_summary(generation_id, *, failed_units=0)`: el plan definía
   `build_summary(generation_id)` y tomaba las unidades fallidas del contexto; se pasan como
   argumento porque el repositorio no ve el `PipelineContext`. Se escribe **antes** de pasar la
   generación a `completed` para que nadie la vea completada sin summary. Con `PIPELINE_STAGES=stub`
   o con P6 `skipped` (0 RF) el summary también se escribe (conteos reales, `failed_units=0`). Las
   generaciones `failed` quedan con `summary = null`. `user_stories_count` cuenta todas las filas
   de `user_stories` (incluye `invalid`), tal como define D-F7-8.
7. **`P6Config` crece.** Además de los dos cambios de T-F7-01, `P6Config` lleva el umbral y los
   topes (con los mismos defaults que las env vars) para que `build_p6_config(settings) -> P6Config`
   sea la única configuración inyectada a la etapa (R-DI-2).
8. **`uncovered_requirement_codes`.** RF objetivo de todas las unidades (también las fallidas) sin
   ningún caso persistido. Se avisa con `UNCOVERED_REQUIREMENTS` (aviso nuevo, no previsto en el
   plan). Los RF sin cluster (D-36) no llegan a P6 y no se cuentan aquí.
9. **Saneo de `requirement_codes` (issue `issue_p6_requirement_codes_sanitization.md`).** Tras
   `drop_blank_list_items` y antes de truncar y validar, `filter_requirement_codes` (en
   `llm_output.py`) quita de cada caso los RF que no son objetivo de la unidad; un caso que se
   queda sin RF se descarta (si no queda ninguno, la unidad es inválida y se reintenta). El
   contrato (`target_codes` en `TestCaseDraft`) no cambia. Para no perder observabilidad, las
   unidades exitosas con códigos filtrados generan el aviso `REQUIREMENT_CODES_FILTERED`
   (`details.units[unit_id]` = `filtered_codes`: códigos foráneos distintos y ordenados;
   `filtered_occurrences`: total de apariciones filtradas, contando el mismo código una vez por
   caso; `dropped_cases`: casos descartados por quedarse sin RF). El campo se llamaba
   `filtered_count`; se renombró por ambigüedad (ver `revisar_filtered_count.md`).
9. **`llm_runs`.** Uno por unidad (también las fallidas, con sus intentos), con `unit_id`.
10. **`P6_PROMPT_VERSION` default `v2`.** El plan proponía default `v1`, pero también pide subir la
    versión si cambia la redacción (T-F7-06). Como los prompts cambiaron, `config.py`, `.env` y
    `.env.example` usan `v2` para que el default y el `.env` no diverjan.

---

## 4. Revisión de prompts (T-F7-06, D-F7-9)

Hallazgos en la versión v1:

- `contexto_sin_clustering.md` mencionaba explícitamente "no se aplicó agrupamiento semántico: no
  hay clústeres" (incumple "no debe mencionar clustering").
- `contexto_sin_clustering.md` tenía una instrucción extra ("usa las HU como contexto; no generes
  casos para funcionalidades no cubiertas por los RF") que `contexto.md` no tenía → asimetría que
  favorecía a una variante.
- Terminología distinta ("RF objetivo" vs "RF del lote") y títulos con "(con/sin clustering)".
- `contexto.md` describía los RF de contexto como "de otras unidades del mismo clúster", cuando
  D-31 los define como RF de **otras** unidades (otros clusters) relacionados.

Versión v2: título y 7 instrucciones idénticos; la única diferencia es la viñeta de "RF de
contexto" y la mención "No enlaces RF de contexto" en la instrucción 2 de `contexto.md`. Se añadió
en ambos "No superes el número máximo de casos indicado en el mensaje" y el schema se referencia
como "entregado en el mensaje". Checklist:

- [x] Instrucciones base equivalentes (mismo grounding y restricciones).
- [x] `contexto.md` distingue RF objetivo / de contexto y prohíbe enlazar los de contexto.
- [x] `contexto_sin_clustering.md` no menciona clustering ni clusters.
- [x] Mismo formato de salida y mismo `TestCaseOutputSpec`.

---

## 5. Pruebas

`tests/test_p6_generation.py` (23): camino feliz `by_cluster` (CP consecutivos, persistencia,
`llm_runs` por unidad) y `by_user_story` (prompt sin clustering, sin sección de contexto); caso
con solo RF de contexto → descartado y unidad inválida; RF de contexto mezclado con objetivo →
filtrado, caso persistido con solo RF objetivo y aviso `REQUIREMENT_CODES_FILTERED`;
`filter_requirement_codes` (filtra foráneos, descarta caso sin RF, no toca texto no JSON); mensaje al LLM (tope, RF, HU, schema, sin label); tope desde
la configuración; 3 unidades con la 2.ª fallida con umbral 0.0 (`StageError`, nada persistido, la
3.ª igualmente procesada) y 0.5 (`completed`, CP-001…003 sin saltos, avisos); comparación estricta
del umbral; `LLM_CONTEXT_LENGTH` sin reintento; `LLM_UNAVAILABLE`; fallo de persistencia sin saltos
de numeración y contando para el umbral; truncado (`CASES_TRUNCATED`) y truncado antes de validar;
reintento por JSON inválido (`BATCH_RETRIED`); `""` en listas; guardias (`p5_output is None`,
0 unidades); fake `persist_p6_unit` idempotente con FK y `id` obligatorio.

`tests/test_stages_wiring.py`: `build_p6_config` (defaults, valores propios, `LLM_MODEL`
obligatoria, 6 valores inválidos); `build_real_stages` con P6 real; E2E HTTP P1→P6 con clustering
(3 CP persistidos, summary `1/2/1/3/0`) y sin clustering (summary con `clusters_count=0`); unidad
fallida con umbral 0.0 → generación `failed` y `summary=null`; con umbral 1.0 → `completed` con
avisos y `test_cases_failed_units=1`.

`tests/test_contracts_invariants.py`: varias unidades fallidas admitidas (no repetidas);
`on_unit_failure` solo `continue`; umbral y topes. `tests/test_generations_api.py`: summary con
ceros en modo stub.

---

## 6. Pendiente fuera de código

1. **Primera iteración de calibración** (`docs/calibracion_resultados/iteracion_1.md`). Requiere
   ejecutar el pipeline real (Ollama + Supabase) con un documento de prueba en ambas estrategias.
   Se dejó la plantilla (`plantilla.md`) y el archivo de la iteración con los campos a completar;
   **no** se inventaron resultados.
2. **Smoke test contra Supabase** de `persist_p6_unit`, `build_summary` y `update_summary`
   (confirmar que la migración `summary jsonb` está aplicada en el proyecto desplegado).
3. **Advertencia heredada 1 (RF no funcionales):** ya mitigada desde la Fase 6 por el descarte
   `is_functional=False` de P2 (D-NFR-1, aviso `NON_FUNCTIONAL_DISCARDED`); revisar en calibración.
4. **Calibrar `P5_MAX_TOKENS_PER_UNIT`, `P6_MAX_CASES_*` y `P6_FAILURE_THRESHOLD`** con documentos
   reales.

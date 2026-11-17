# Fase 8 — `stop_after`: parada limpia del pipeline para calibración

> **Estado:** 🔲 pendiente de implementar. Este archivo es la **especificación** de una
> capacidad del orquestador: detener la ejecución tras la etapa N, dejando las restantes
> `skipped` y la generación `completed` con `summary` parcial. Motivada por calibración.
> **No es una prueba** ni pertenece a la capa de integración de [`fase8.md`](fase8.md); es
> una capacidad del pipeline que la calibración (y, secundariamente, el E2E de Fase 8)
> consumirán.
> **Documentos fuente:** `ai_service/pipeline/orchestrator.py`,
> `ai_service/pipeline/catalog.py`, `ai_service/pipeline/events.py`,
> `ai_service/services/pipeline_runs.py`, `ai_service/config.py`,
> `scripts/inspect_generation.py`.

---

## Alcance de la tarea (lo que sí y lo que no)

> **La tarea es implementar la capacidad `stop_after`, no calibrar.** Quien tome este documento
> añade el parámetro al orquestador, la variable de entorno, el wiring y los tests (ver §Cambios
> en código y §Pruebas). **No** debe afinar parámetros de P4/P5, ejecutar el pipeline contra
> documentos reales ni interpretar resultados: eso es trabajo de calibración (humano o un agente
> específico de calibración) que *usará* esta capacidad una vez exista. La tabla «Por qué» solo
> justifica la capacidad, no define la tarea. Si al leer el documento parece que hay que
> calibrar, no es así.

---

## Objetivo

Poder correr un **prefijo** del pipeline (P1…N) sin ejecutar la cola (N+1…P7), de forma limpia:
las etapas no ejecutadas quedan `skipped`, la generación termina `completed` y `summary`
refleja solo lo persistido hasta N. Se inspecciona igual que una corrida completa con
`scripts/inspect_generation.py`.

```
stop_after = P4  →  P1 P2 P3 P4 completadas; P5 P6 P7 skipped; generación completed
```

---

## Por qué (beneficio, con datos reales)

Asimetría de costo del pipeline, medida en la generación `caa5f52c-…`:

| Etapa | Costo | ¿LLM? |
|---|---|---|
| P1 (heurística) | ~2 s | no |
| P2 (RF) | ~2m56s | sí (lotes) |
| P3 (embeddings) / P4 (HDBSCAN) / P5 (contexto) | ~1 s c/u | no |
| **P6 (casos)** | **~4m43s** | **sí (por unidad)** |
| **Total** | **~7m47s** | |

P6 es ~60 % del wall time. Cuando se calibra la **cabecera** (P1–P5) hoy se corre el pipeline
entero y se descartan ~5 min de P6 que ni se inspeccionan. Con `stop_after`:

| Calibrar… | `stop_after` | Cada iteración pasa de ~8 min a… | Advertencia del roadmap que cierra |
|---|---|---|---|
| Segmentación P1 | `p1` | **~2 s** (sin LLM) | nº 5 (heurística sensible a «para») |
| Extracción RF (P2) | `p2` | ~2m56s | calidad de RF atómicos |
| Clustering HDBSCAN (P4) | `p4` | ~3 min | nº 6 (`P4_MIN_CLUSTER_SIZE`/`MIN_SAMPLES`) |
| Contexto / tope de tokens (P5) | `p5` | ~3 min | nº 8 (`P5_MAX_TOKENS_PER_UNIT`) |

El caso más fuerte es **P4 (HDBSCAN)**: afinar sus parámetros exige muchas iteraciones y cada
una hoy cuesta el run completo; a ~3 min en vez de ~8 min, una sesión de calibración de
clustering pasa de horas a ~media hora.

Beneficios secundarios: **bisección** de fallos (validar el *contenido* de cada prefijo, no
solo que no erroró — el dónde ya se localiza por etapa), y **E2E parcial más fino** (un E2E
`p1→p4` que falle aísla el problema antes de P6).

---

## Diseño — decisiones

### D-CS-1 — Prefijo P1…N, no subconjunto arbitrario

`stop_after` ejecuta las etapas con `order ≤ order(stop_after)` y omite las posteriores. No
permite saltos arbitrarios (p. ej. «solo P1, P2 y P4»). Lo que la calibración necesita es
«inspeccionar hasta tal etapa», que es el prefijo. Subconjuntos serían YAGNI.

### D-CS-2 — Marca el resto `skipped`; NO reusa `skip_remaining`

`skip_remaining` significa hoy «lo de abajo es irrelevante por una condición de fallo/vacío»
(D-29, P2 sin RF). Reusarlo para una parada intencional mezclaría semánticas y confundiría los
logs. `stop_after` usa un chequeo dedicado por `order`, independiente de `skip_remaining`.

### D-CS-3 — Compatible con el guard de completitud, sin tocarlo

`PipelineRunService._ensure_all_stages_final()` exige que las 7 etapas estén `completed` o
`skipped` (P7 también admite `failed`). Como `stop_after` marca la cola `skipped`, **pasa el
guard sin cambios**: la generación se completa correctamente. `_write_summary` ya tolera
`p6_output` ausente (cuenta 0 casos), así que el `summary` es parcial de forma natural.

### D-CS-4 — Env var `PIPELINE_STOP_AFTER_STAGE`, default `None` = run completo

Para calibración basta una variable de entorno. `None` (default) deja el comportamiento
actual sin cambios — **ningún test existente se ve afectado**. La capacidad vive en el
orquestador como parámetro por instancia (testeable directo); el wiring lee la env var.

### D-CS-5 — `stop_after` no enmascara fallos

Si una etapa **anterior** al tope falla (bloqueante), el pipeline falla como hoy: `stop_after`
es irrelevante. La parada solo ocurre si se llega al tope sin fallo. Esto preserva la
observabilidad del error (ya localizada por etapa vía `StageFailed`).

---

## Cambios en código

### `ai_service/pipeline/orchestrator.py` — núcleo

`PipelineOrchestrator.__init__` recibe `stop_after: StageKey | None = None` y lo guarda. En
`run()`, calcula el `stop_order` y omite las etapas posteriores por el mismo camino de
`StageSkipped` que ya existe (sin tocar `skip_remaining`):

```python
def __init__(self, stages, reporter, *, stop_after: StageKey | None = None) -> None:
    self._stages = sorted(stages, key=lambda s: get_stage_definition(s.key).order)
    self._reporter = reporter
    self._stop_after = stop_after

async def run(self, context: PipelineContext) -> bool:
    stop_order = get_stage_definition(self._stop_after).order if self._stop_after else None
    skip_remaining = False
    for stage in self._stages:
        order = get_stage_definition(stage.key).order
        beyond_stop = stop_order is not None and order > stop_order
        if skip_remaining or self.should_skip(stage, context) or beyond_stop:
            await self._reporter.report(StageSkipped(generation_id=context.generation_id, stage_key=stage.key))
            continue
        ...  # resto sin cambios
```

`StageKey` ya se importa en `events.py`; confirmar el import en `orchestrator.py`. El
`StageSkipped` ya lo persiste `RepositoryProgressReporter` (es el camino que usan P3/P4 sin
clustering), así que la cola queda `skipped` en `generation_stages`.

### `ai_service/config.py` — variable

Añadir (junto a `pipeline_stub_fail_at_stage`):

```python
pipeline_stop_after_stage: StageKeyLiteral | None = None
```

Verificar el `field_validator` compartido de `StageKeyLiteral` en `config.py` (hoy cubre
`pipeline_stub_fail_at_stage`, `llm_base_url`, `llm_model`): si normaliza/casea estos literales,
añadir `pipeline_stop_after_stage` a su lista para que una env var como `p4` se acepte igual que
`P4`.

### `ai_service/services/pipeline_runs.py` — wiring

`PipelineRunService` recibe `stop_after` (desde `settings.pipeline_stop_after_stage` en
`main.py`) y lo pasa al orquestador en `run()`:

```python
await PipelineOrchestrator(self._stages, reporter, stop_after=self._stop_after).run(context)
```

`main.py` lo construye al armar `PipelineRunService` (donde hoy llama `build_real_stages` /
`build_stub_stages`).

### `.env` / `.env.example`

Añadir con comentario:

```ini
# Detiene el pipeline tras esta etapa (calibración). Vacío = run completo. Valores: p1..p7.
PIPELINE_STOP_AFTER_STAGE=
```

---

## Comportamiento y semántica

- **Eventos:** `stage_completed` para P1…N; `stage_skipped` para N+1…P7; `pipeline_completed`.
  Generación termina `completed`.
- **`summary`:** parcial y coherente. Parar antes de P4 → `clusters_count=0`; antes de P6 →
  `test_cases_count=0` y `test_cases_failed_units=0` (`p6_output` es `None`).
- **Límite no alcanzado:** si una etapa anterior falla (bloqueante), el pipeline falla y la
  cola queda como hoy (`pending`, ver matices en `fase8.md`/roadmap); `stop_after` no altera eso.
- **Clustering desactivado + `stop_after=p4`:** P3/P4 se omiten por `should_skip` y P5–P7 por
  `stop_after`. Neto: P1,P2 corren, P3–P7 `skipped`. Coherente (con clustering off, P4 no hace
  nada de todos modos).

---

## Pruebas (en `tests/test_pipeline.py`)

- `stop_after=p4`, clustering on: secuencia `stage_completed` p1–p4, `stage_skipped` p5–p7,
  `pipeline_completed`; `run` devuelve `True`.
- `stop_after=p1`: solo p1 `completed`, p2–p7 `skipped`.
- `stop_after=None`: comportamiento actual sin cambios (test de regresión / no rotura).
- Clustering off + `stop_after=p4`: p1,p2 `completed`; p3–p7 `skipped`.
- Fallo bloqueante antes del tope (`build_stub_stages(0, "p2")` + `stop_after=p4`): p2
  `stage_failed` y `pipeline_failed`; `run` devuelve `False` (la parada no enmascara el fallo).

Estos son unitarios del orquestador (rápidos, con stubs); no requieren Supabase ni LLM.

---

## Impacto en otros documentos

- `docs/pipeline_roadmap.md` — añadir `stop_after` como capacidad de Fase 8 y cruzar la
  referencia en las advertencias 6 (HDBSCAN) y 8 (`P5_MAX_TOKENS_PER_UNIT`) como mecanismo de
  calibración barata. (Hecho en este mismo cambio.)
- `docs/prompts_fases/Fase 8/fase8.md` — apuntar a este archivo como capacidad relacionada
  (calibración + E2E parcial), sin mezclarla con la capa de integración. (Hecho.)
- `docs/calibracion_resultados/iteracion_1.md` — al cerrar la iteración, documentar el uso de
  `PIPELINE_STOP_AFTER_STAGE` para aisnar P4/P5 cuando proceda.

---

## Criterios de cierre

- [ ] `PipelineOrchestrator` acepta `stop_after` y omite por `order` vía `StageSkipped`.
- [ ] `PIPELINE_STOP_AFTER_STAGE` leída desde `config.py` y pasada por `PipelineRunService`.
- [ ] `None` = run completo; ningún test existente cambia (suite de 533 sigue verde).
- [ ] Una corrida con `stop_after=p4` deja P5–P7 `skipped`, generación `completed` y `summary`
  con `test_cases_count=0`.
- [ ] Fallo bloqueante antes del tope sigue fallando la generación (no se enmascara).
- [ ] Pruebas del orquestador añadadas y pasando.
- [ ] `pipeline_roadmap.md` y `fase8.md` actualizados con la referencia.

---

## Referencias

- `ai_service/pipeline/orchestrator.py` — `run()` (camino de `StageSkipped` a reusar).
- `ai_service/pipeline/catalog.py` — `STAGE_CATALOG` y `get_stage_definition` (definen el `order`).
- `ai_service/services/pipeline_runs.py:150` — construcción del orquestador;
  `_ensure_all_stages_final` (acepta `skipped`, ver D-CS-3).
- `ai_service/config.py` — `pipeline_stub_fail_at_stage` como precedente; `StageKeyLiteral`.
- `scripts/inspect_generation.py` — inspección de la corrida detenida (igual que una completa).
- Generación `caa5f52c-…` — origen de las mediciones de costo de la tabla «Por qué».

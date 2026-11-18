# Guía de calibración del pipeline (P1–P6)

> **Estado:** 🟡 guía definitiva. Define la **metodología** para afinar los parámetros del
> pipeline contra datos reales, aprovechando `stop_after` para abaratar la cabecera (P1–P5) y
> reservando el costo grande de P6 para el final.
> **No es un registro de resultados.** Las corridas completas se documentan en `iteracion_N.md`
> (formato de [`plantilla.md`](plantilla.md)); los sondeos, en [`bitacora/`](bitacora). Esta guía
> dice **cómo** y **en qué orden**.
> **Documentos fuente:** [`plantilla.md`](plantilla.md), [`iteracion_1.md`](iteracion_1.md),
> [`prompts_fases/Fase 8/calibracion_stop.md`](../prompts_fases/Fase%208/calibracion_stop.md)
> (capacidad `stop_after`), `docs/pipeline_roadmap.md` (advertencias 5, 6, 8),
> `ai_service/config.py` (parámetros), `scripts/inspect_generation.py` (inspección).

---

## 1. Objetivo y alcance

Afinar los parámetros del pipeline (P1–P6) de forma **justificada**: cada valor óptimo debe
rastrearse a un sondeo que lo decidió, y cada configuración candidata se valida end-to-end en
una iteración completa. **P7 queda fuera** (es stub no bloqueante; si se desarrolla, se calibra
aparte). El producto calibrable es P1–P6.

---

## 2. Principio: sondeo vs. iteración

Dos unidades de trabajo distintas, no se mezclan:

- **Sondeo** — corrida parcial con `PIPELINE_STOP_AFTER_STAGE=pN`, barata, exploratoria, cambia
  uno o pocos parámetros. Se registra en `bitacora/pN.md` (una fila por sondeo).
  **No** crea `iteracion_N.md`.
- **Iteración** — corrida completa P1–P6 con las dos estrategias (`by_user_story` baseline +
  `by_cluster` propuesta) sobre una configuración candidata. Se documenta en `iteracion_N.md`
  con [`plantilla.md`](plantilla.md). Son **pocas** (~16 min + análisis c/u).

> **Regla de oro:** no crear `iteracion_N.md` por un cambio puntual. Solo cuando P1–P5 pasaron
> sus criterios en la bitácora y se quiere validar la configuración entera end-to-end.

---

## 3. Decisiones previas (antes de sondear)

1. **Proyecto Supabase objetivo.** La calibración corre el pipeline real, que lee `SUPABASE_URL`.
   - **Recomendada:** apuntar `SUPABASE_URL` a `pruebas-TestGen` (mismo `schema.sql`, ya
     desplegado). Aisla las generaciones de calibración y deja el proyecto real limpio.
     Requisito: crear el bucket `docs_testgen` en Storage de ese proyecto.
   - Alternativa: calibrar contra el proyecto real. Coincide 100% con producción, pero deja
     generaciones de prueba ahí (borrables con `delete_generation_if_final`).
2. **Ollama.** Levantarlo con `LLM_MODEL`. En `.env`:
   - `LLM_PROVIDER=ollama`, `LLM_BASE_URL`, `LLM_MODEL`.
   - `LLM_NUM_CTX=16384`, `LLM_TEMPERATURE=0.0`, `LLM_THINK=false`. Sin `num_ctx`/`think`
     explícitos, Ollama usa 4096 + thinking y el JSON de P2 sale **truncado** (ver `config.py`).
3. **Documento de prueba.** Representativo y con **bastantes HU/RF**. Con ≤3 RF HDBSCAN marca
   todo como ruido (`INSUFFICIENT_REQUIREMENTS`); se necesitan suficientes requerimientos para
   que el clustering sea significativo. Anotar nombre + checksum.
4. **Commit del backend.** Registrar el hash (va en §1 de la plantilla) para trazabilidad.

---

## 4. Cómo correr un sondeo (P1–P5)

1. Editar `.env`: poner `PIPELINE_STOP_AFTER_STAGE=pN` y el parámetro a sondear.
2. Reiniciar el backend con `PIPELINE_STAGES=real`.
3. `POST /api/v1/documents` con el documento de prueba (solo la primera vez; reusar el
   `document_id` luego).
4. `POST /api/v1/generations` (la estrategia no importa para P1–P5; usar `by_user_story`).
5. Esperar a que termine (`completed`) e inspeccionar con `scripts/inspect_generation.py` y
   `GET /api/v1/generations/{id}`.
6. Anotar una fila en `bitacora/pN.md`.
7. ¿Pasa el criterio de aceptación de la etapa? Si no, volver al paso 1 con otro valor.

Las etapas posteriores al tope quedan `skipped`, la generación `completed` y `summary` parcial
(p. ej. `test_cases_count=0` antes de P6). Eso es esperado, no un error.

---

## 5. Etapas de afinado (sondeos)

Cada etapa: **objetivo**, **costo**, **inspeccionar**, **criterio de aceptación** y **parámetros**.

### Etapa 1 — P1 (segmentación) · `stop_after=p1`

- **Objetivo:** segmentación de HU sana. Ojo con la **advertencia #5**: la heurística parte la
  declaración en la primera aparición de "para" ("un botón para exportar" → "un botón"). Es un
  bug de heurística, no un parámetro: si perjudica, es **fix de código aparte**, no calibración.
- **Costo:** ~2 s (sin LLM).
- **Inspeccionar:** `summary.user_stories_count`; spot-check de 5–10 HU.
- **Criterio:** `user_stories_count` ≈ conteo manual del documento; objetivos no cortados por
  "para".
- **Parámetros:** `P1_STORY_DELIMITER_PATTERN`, `P1_MAX_STORY_CHARS`, `P1_LANGUAGE`,
  `P1_RULES_VERSION`.

### Etapa 2 — P2 (extracción de RF) · `stop_after=p2`

- **Objetivo:** RF atómicos, con `source_text` que respalde, clasificaciones correctas.
- **Costo:** ~3 min (LLM en lotes).
- **Inspeccionar:** `summary.requirements_count`; leer RF y validar grounding + enlaces RF↔HU.
- **Criterio:** `requirements_count` > 0 y coherente con el nº de HU; sin JSON truncado/malformado;
  RF atómicos y con `source_text` (spot-check).
- **Parámetros:** `P2_MAX_STORIES_PER_CALL`, `P2_MAX_RETRIES`, `P2_PROMPT_VERSION` (v1). Si hay
  JSON truncado, revisar `LLM_NUM_CTX`/`LLM_THINK` (causa más frecuente).
- **Bitácora:** [`bitacora/p2.md`](bitacora/p2.md).

### Etapa 3 — P4 (HDBSCAN) · `stop_after=p4` — la más iterativa

- **Objetivo (advertencia #6):** hallar `P4_MIN_CLUSTER_SIZE` / `P4_MIN_SAMPLES` que den clusters
  con sentido en vez de "todo ruido".
- **Costo:** ~3 min/iteración (P1+P2+P3+P4; el LLM es solo P2).
- **Inspeccionar:** `summary.clusters_count`, RF sin cluster (`UNASSIGNED_REQUIREMENTS`),
  composición de cada cluster.
- **Criterio:** `clusters_count` > 0; `UNASSIGNED_REQUIREMENTS` bajo; sin
  `INSUFFICIENT_REQUIREMENTS`; clusters semánticamente coherentes.
- **Parámetros:** `P4_MIN_CLUSTER_SIZE` (default 2), `P4_MIN_SAMPLES` (default 1), `P4_METRIC`.
  P3 (embeddings) corre antes: `P3_INPUT_TEMPLATE`, `P3_BATCH_SIZE`, `EMBEDDINGS_MODEL` también
  afectan el clustering, pero su afinado es secundario.
- **Bitácora:** [`bitacora/p4.md`](bitacora/p4.md).

### Etapa 4 — P5 (contexto / tope de tokens) · `stop_after=p5`

- **Objetivo (advertencia #8):** que `P5_MAX_TOKENS_PER_UNIT` (estimado heurístico caracteres/4)
  no se desvíe del tokenizador real del modelo de P6.
- **Costo:** ~3 min.
- **Inspeccionar:** unidades P5, `UNIT_EXCEEDS_TOKEN_LIMIT`, distribución de tokens por unidad.
- **Criterio:** sin `UNIT_EXCEEDS_TOKEN_LIMIT` (o conocido y aceptado); nº de unidades
  razonable. Comparar el estimado de P5 con los tokens reales de P6 (`llm_runs`) en una corrida
  completa para validar la heurística.
- **Parámetros:** `P5_MAX_TOKENS_PER_UNIT` (default 8000), `P5_INCLUDE_PREREQUISITES`,
  `P5_INSTRUCTIONS_VERSION`.
- **Bitácora:** [`bitacora/p5.md`](bitacora/p5.md).

### Etapa 5 — P6 (casos) — solo en la corrida completa, no sondeo

P6 no se sondea con `stop_after` (es el tope más alto del producto). Se valida en la **iteración
completa** (§6). Si hay que mover sus parámetros, sondear con corridas completas en
[`bitacora/p6.md`](bitacora/p6.md) (caras; pocas) y luego nueva iteración.

- **Criterio:** `test_cases_count` > 0; `UNCOVERED_REQUIREMENTS` bajo; `test_cases_failed_units`
  bajo; sin `GENERATION_THRESHOLD_EXCEEDED` no deseado; revisar avisos `CASES_TRUNCATED`,
  `REQUIREMENT_CODES_FILTERED`, `BATCH_RETRIED`. Cualitativo: casos con pasos completos,
  grounding (vinculan los RF correctos) y resultado esperado claro.
- **Parámetros:** `P6_MAX_CASES_MULTIPLIER` (default 3), `P6_MAX_CASES_ABSOLUTE` (default 50),
  `P6_FAILURE_THRESHOLD` (default 0.0), `P6_MAX_RETRIES`, `P6_PROMPT_VERSION` (v2).

---

## 6. Etapa final — corrida completa (iteración)

Cuando P1, P2, P4 y P5 pasaron sus criterios en sus bitácoras, se arma una iteración completa.
Seguir [`iteracion_1.md`](iteracion_1.md) (o copiarlo como `iteracion_N.md`):

1. `PIPELINE_STOP_AFTER_STAGE=` (vacío, run completo), `PIPELINE_STAGES=real`.
2. `POST /api/v1/documents` (reusar el documento).
3. Dos generaciones del mismo documento:
   - `{"configuration": {"semantic_clustering_enabled": false}}` → `by_user_story` (baseline).
   - `{"configuration": {"semantic_clustering_enabled": true}}` → `by_cluster` (propuesta).
4. Copiar de `GET /api/v1/generations/{id}`: `summary`, avisos y `runtime_info`/`llm_runs` de P4,
   P5 y P6 a [`plantilla.md`](plantilla.md).
5. Validar los criterios de P6 (§5, Etapa 5). Si hay que mover parámetros de P6, sondear en
   [`bitacora/p6.md`](bitacora/p6.md) y luego crear la siguiente `iteracion_N.md`.

**Numeración:** `iteracion_1.md` es la primera corrida completa (config defaults o primer
candidato); `iteracion_2.md` el primer candidato afinado; etc. **Una por corrida completa**,
no una por cambio.

---

## 7. Cierre y justificación de la configuración óptima

Al cerrar, la configuración óptima = la última `iteracion_N.md` que validó end-to-end. La
justificación de cada parámetro:

- Cada valor **rastrea a una fila de bitácora** que muestra el sondeo que lo decidió. Si no hay
  fila, marcarlo "default, no sondeado" (honesto) o sondearlo.
- La iteración confirma la configuración **entera** (calidad de casos, conteos, sin errores).
- Documentar en §5 de la última iteración los ajustes finales y actualizar `.env`/`.env.example`
  si cambiaste defaults.
- Marcar en `docs/pipeline_roadmap.md` el estado de las advertencias #5 (P1), #6 (HDBSCAN) y #8
  (P5 tokens) según el hallazgo.

---

## 8. Costo esperado

| Etapa | `stop_after` | Costo c/iter | Iteraciones estimadas |
|---|---|---|---|
| 1 · P1 | p1 | ~2 s | 1–2 |
| 2 · P2 | p2 | ~3 min | 1–2 |
| 3 · P4 | p4 | ~3 min | varias (la que más itera) |
| 4 · P5 | p5 | ~3 min | 1–3 |
| 5 · P6 completo | — | ~8 min × 2 estrategias | 1 (+ ajustes puntuales) |

La asimetría es la idea: P1–P5 se itera barato con `stop_after`; P6, que es ~60% del wall time,
se corre caro **solo cuando lo demás ya está afinado**.

---

## 9. Advertencias del roadmap que esta guía aborda

- **#5** — Heurística de P1 sensible a "para" → Etapa 1 (y fix de código si procede).
- **#6** — Calibración de HDBSCAN pendiente → Etapa 3.
- **#8** — Calibración de `P5_MAX_TOKENS_PER_UNIT` pendiente → Etapa 4.

---

## 10. Referencias

- [`plantilla.md`](plantilla.md) — formato del registro de una iteración completa.
- [`iteracion_1.md`](iteracion_1.md) — primera corrida completa (pendiente de ejecutar).
- [`bitacora/`](bitacora) — sondeos por etapa (`p1`, `p2`, `p4`, `p5`, `p6`).
- [`prompts_fases/Fase 8/calibracion_stop.md`](../prompts_fases/Fase%208/calibracion_stop.md) —
  spec de la capacidad `stop_after`.
- `docs/pipeline_roadmap.md` — advertencias técnicas activas.
- `ai_service/config.py` — parámetros afinables.
- `scripts/inspect_generation.py` — inspección de la corrida (detenida o completa).

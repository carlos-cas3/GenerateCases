# Fase 4 — Implementación real de P1 (heurística) y P2 (LLM)

> **Estado:** 🔲 pendiente (la Fase 3 está cerrada en el commit `a4940ea`).
> **Rama de la fase anterior:** `revision_fase3`
> **Documentos fuente:** `docs/pipeline_roadmap.md`, `docs/prompts_fases/Fase 3/cierre_documental.md`,
> `docs/prompts_fases/Fase 3/tareas_pendientes_final_fase3.md`, `ai_service/pipeline/contracts/p1.py`,
> `ai_service/pipeline/contracts/p2.py`, `ai_service/clients/llm.py`, `ai_service/clients/extractor.py`.
>
> Este archivo es el **resumen de alcance y roadmap** de la fase. Sirve como guía única para no
> repetir el contexto en cada sesión. El detalle de diseño vive en los documentos referenciados.

---

## Decisiones de la fase

- **P1 — camino B (heurística, sin LLM).** Directriz del responsable: P1 **no llama al LLM**.
  Identifica las HU con regex/heurística sobre la plantilla ("Como \<rol\>, quiero \<objetivo\>
  para \<benefit\>" + delimitadores de sección). Los bloques que no encajan con la plantilla se
  marcan como **historias no identificadas** (`UnresolvedFragment` en `P1Output`, ya existe en el
  contrato). Motivo: evitar llamadas innecesarias al LLM cuando la identificación es factible con
  heurística.
  - **Supuesto de entrada:** los documentos llegan a Storage ya cumpliendo la plantilla; la
    normalización la hace un servicio externo upstream y el pipeline es agnóstico a eso. Si un
    bloque no cumple, va a `unresolved_fragments`; si ninguno cumple, P1 falla con
    `NO_STORIES_FOUND`.
  - **Implicaciones:** se elimina la tarea de prompt de P1; P1 no recibe `LlmClient` por
    constructor; el LLM queda solo para P2 (y P6 en Fase 7). Nueva tarea: spec de plantilla de HU
    (T-F4-02) que acuerdan el servicio externo y la regex de P1.

- **Aprobaciones y delegaciones del responsable:**
  - ✅ **Plantilla de HU** (`plantilla_hu.md`) — aprobada.
  - ✅ **Prompt de P2** (`prompt_p2.md`) — aprobado.
  - 🤖 **T-02 y T-04** — delegados al agente: T-02 opción (a) (rechazar duplicados con mensaje
    correcto + test); T-04 opción (b) (dejar `position` nullable + documentar el orden en openapi,
    sin datos en producción).
  - 🤖 **Hueco A (persistencia de P1)** — delegado al agente: opción (a), añadir RPC
    `persist_p1_user_stories` (consistente con `persist_p2/p4/p6`, idempotente) + caller.
  - 🤖 **Hueco B (config de `P1Config`/`P2Config`)** — delegado al agente: añadir env vars en
    `config.py` + `.env.example`.
  - 🤖 **Implementación (T-F4-04…T-F4-09)** — delegada al agente.

---

## 0. Objetivo de la fase

Que las etapas **P1** (normalización/segmentación de HU) y **P2** (clasificación + extracción de RF)
dejen de ser `StubStage` y ejecuten lógica real:

```
P1: Storage(bytes) → DocumentTextExtractor → texto → regex/heurística → P1Output → persistir HU en BD
P2: P1Output → LLM (en batches) → P2Output → persist_p2_requirements (RPC Supabase)
```

Al cerrar la fase, un documento subido produce HU + RF **reales** persistidos en la base de datos,
mientras P3–P7 siguen siendo stubs. Las decisiones técnicas pendientes de `schema.sql`
(T-01, T-02, T-04) se toman y aplican aquí, porque es cuando las etapas reales empiezan a invocar
las RPCs y los riesgos descritos pasan a ser posibles.

---

## 1. Prerequisitos — estado real

Los "prerequisitos" que el roadmap viejo listaba como trabajo de Fase 4 **ya están hechos**
(se construyeron en la Fase 3 con los commits `issue_resolver_*`). Verificar antes de empezar,
no reimplementar.

| Prerequisito | Archivo | Estado |
|---|---|---|
| Variables de entorno LLM en `config.py` | `ai_service/config.py` (`llm_provider`, `llm_api_key`, `llm_base_url`, `llm_timeout_seconds`) | ✅ hecho |
| Puerto `LlmClient` (Protocol) + DTOs | `ai_service/clients/llm.py` (`LlmRequest`, `LlmResponse`, `LlmClient`) | ✅ hecho |
| Adaptadores LLM + fake + factory | `openai_llm.py`, `anthropic_llm.py`, `ollama_llm.py`, `llm_fake.py`, `llm_factory.py` | ✅ hecho |
| Puerto `DocumentTextExtractor` (Protocol) | `ai_service/clients/extractor.py` | ✅ hecho |
| Adaptadores de extracción + fake + compuesto | `txt_extractor.py`, `pdf_extractor.py`, `docx_extractor.py`, `composite_extractor.py`, `extractor_fake.py` | ✅ hecho |
| Contratos P1 y P2 | `pipeline/contracts/p1.py`, `pipeline/contracts/p2.py` (con `to_rpc_payload()` en P2) | ✅ hecho |
| `PipelineContext` con `p1_output` / `p2_output` | `pipeline/context.py` | ✅ hecho |

> Nota: los puertos/adapters de embeddings y clustering (`embeddings.py`, `embeddings_factory.py`,
> `local_embeddings.py`, `openai_embeddings.py`, `clustering.py`, `hdbscan_clustering.py`, …)
> también están construidos, pero **no se usan en Fase 4**: pertenecen a P3/P4 (Fase 5).
>
> **P1 no usa LLM** (camino B, ver "Decisiones de la fase"). El `LlmClient` solo lo usa P2 en esta
> fase (y P6 en Fase 7). P1 depende de `DocumentStorage` + `DocumentTextExtractor` + `P1Config`.

---

## 2. Decisiones `schema.sql` que se toman al iniciar la fase

Vienen de `tareas_pendientes_final_fase3.md` (sección 4). No bloquearon el cierre de la Fase 3, pero
deben resolverse ahora porque las RPCs se invocan desde las etapas reales. Documentar la decisión
elegida en `docs/prompts_fases/Fase 4/decisiones_schema.sql.md` (ver §5).

| ID | Tema | Resumen | Impacto |
|---|---|---|---|
| **T-01** | Idempotencia de las RPCs (`persist_p2_requirements`, `persist_p4_clusters`, `persist_p6_unit`) | Hoy un reintento post-commit falla por PK duplicada y deja la generación `failed` con datos guardados. Opciones: (a) RPCs idempotentes (no-op si mismo id+contenido), (b) no reintentar RPCs desde el cliente, (c) clave de idempotencia. | `schema.sql` + repositorio |
| **T-02** | HU duplicadas en `persist_p2_requirements` | Si `user_story_code` viene repetido, el `UPDATE … FROM` actualiza una sola vez y el conteo lanza un mensaje engañoso. Recomendado: (a) rechazar duplicados explícitamente con mensaje correcto + test. | `schema.sql` + test RPC |
| **T-04** | Backfill de `position` en `user_stories` | La migración añade `position` nullable sin rellenar filas antiguas. Si no hay datos en producción, basta (b) dejar nullable + documentar el orden en openapi. | `schema.sql` + openapi |

---

## 3. Trabajo a realizar — tareas

### T-F4-01 · Decisiones de `schema.sql` (T-01, T-02, T-04)
- Revisar `supabase/schema.sql` (`persist_p2_requirements`, `persist_p4_clusters`, `persist_p6_unit`) y las advertencias activas de `pipeline_roadmap.md`.
- Elegir opción por cada tarea y aplicarla en `schema.sql` (y en `openapi.yaml` para T-04 si se documenta el orden).
- Registrar la decisión y la justificación en `decisiones_schema.sql.md`.
- Solo **T-02** es estrictamente necesaria para P1/P2; T-01 y T-04 pueden abordarse aquí pero su riesgo es bajo sin datos en producción.

> **Progreso:**
> - ✅ **T-01 (idempotencia) — decidido e implementado.** Opción (a): RPCs idempotentes por clave vía
>   `ON CONFLICT` en los 8 INSERTs de P2/P4/P6. Ver `decisiones_schema.sql.md`. Falta desplegar
>   `schema.sql` contra Supabase.
> - 🤖 **T-02 (HU duplicadas en payload) — delegado al agente.** Opción (a): rechazar duplicados
>   con mensaje correcto + test RPC.
> - 🤖 **T-04 (backfill de `position`) — delegado al agente.** Opción (b): dejar nullable +
>   documentar el orden en openapi (sin datos en producción).

### T-F4-02 · Spec de plantilla de HU (formato de entrada de P1)
- Definir el contrato de formato que acuerdan el **servicio externo upstream** (que normaliza el documento) y la **regex/heurística de P1**: delimitador de HU (ya existe `story_delimiter_pattern` en `P1Config`), marcadores de sección (`content_sections`: criterios, reglas, restricciones…), y posiciones de rol / objetivo / benefit (p. ej. "Como …, quiero …, para …").
- Sin esta spec los dos lados pueden divergir silenciosamente. Debe ser un documento versionado (p. ej. `docs/prompts_fases/Fase 4/plantilla_hu.md`) referenciado por `rules_version` de `P1Config`.
- P1 **no tiene prompt de LLM**; esta spec reemplaza la antigua tarea "prompts de P1".

> **Progreso:** ✅ **aprobada** — `plantilla_hu.md` creada y aprobada por el responsable.

### T-F4-03 · Prompts de P2 (clasificación + extracción de RF)
- Crear `ai_service/pipeline/prompts/p2.py` con el resolvedor.
- Crear el/los textos en `prompts/texts/` (p. ej. `p2_requirements.md`).
- El prompt debe pedir al LLM la estructura que `P2Output` valida: `StoryClassification`, `RequirementDraft` → `FunctionalRequirement`, evaluación de calidad, `stories_without_requirements`.
- P2 corre en **batches** (definir el tamaño del lote en `P2Config` o en settings): el prompt recibe un subconjunto de HU por llamada.

> **Progreso:** ✅ **aprobado** — `prompt_p2.md` creada y aprobada. Pendiente: mover el texto a
> `ai_service/pipeline/prompts/texts/p2_requirements.md` y crear el resolvedor `prompts/p2.py`.

### T-F4-04 · Cableado de dependencias (DI)
- `NormalizeStage` (P1) recibe `DocumentStorage` + `DocumentTextExtractor` + `P1Config` por constructor (R-DI-2). **No recibe `LlmClient`** (camino B).
- `RequirementsStage` (P2) recibe `LlmClient` + el resolvedor de prompts de P2 + el repositorio por constructor.
- Resolver en `main.py` / `api/dependencies.py` usando los factories (`LlmClientFactory` para P2; `EmbeddingsClientFactory` no aplica en esta fase) y el compuesto de extractores.
- Las etapas ya no heredan de `StubStage`: heredan de `StageBase` e implementan `run()`.

### T-F4-05 · Implementar `NormalizeStage.run()` (P1 — heurística, sin LLM)
1. Leer bytes del Storage (vía `DocumentStorage.download` / repositorio) y construir `SourceDocument` (`p1.py`).
2. Extraer texto con `DocumentTextExtractor.extract(data, file_type)`. Si sale `""` → `StageError(EMPTY_DOCUMENT)`.
3. **Segmentar con la regex** de `P1Config.story_delimiter_pattern` (parte el documento en bloques candidatos).
4. **Estructurar cada bloque con heurística** sobre la plantilla (T-F4-02): si encaja → `UserStory` (extraer `role`/`objective`/`benefit` por la plantilla, asignar `code` `HU-xxx` y `position`, fijar `validation_status` según completitud: `valid` si cumple, `valid_with_warnings` con `issues` si falta algo, `invalid` si no es procesable). Si **no encaja** → `UnresolvedFragment` ("historia no identificada").
5. Construir `P1Output` (Pydantic valida unicidad y conteos). Si todas son `invalid`/unresolved → `StageError(NO_STORIES_FOUND)`.
6. Persistir las HU en `user_stories` (code, position, contenido). Definir cómo P1 escribe — hoy no hay RPC `persist_p1_*`; confirmar si se inserta vía repositorio directo o se añade una RPC (decisión a tomar en esta tarea). `unresolved_fragments` e `issues` **no se persisten** (D-22).
7. Escribir `P1Output` en `context.p1_output`. Emitir `stage_completed` **sin `LlmRun`** (P1 no llama al LLM).
8. Tratar fallos: `DOCUMENT_UNREADABLE`, `EMPTY_DOCUMENT`, `NO_STORIES_FOUND`. (No hay `LLM_INVALID_OUTPUT` ni reintentos de LLM en P1.)

### T-F4-06 · Implementar `RequirementsStage.run()` (P2)
1. Leer `context.p1_output`. Si 0 HU procesables → comportamiento de D-29 (`skip_remaining=True`, P3–P7 `skipped`).
2. Partir las HU en batches; por cada lote, llamar al `LlmClient` con el prompt de P2.
3. Validar cada respuesta contra `P2LlmResponse` / `P2Output`. Reintentar lotes inválidos (límite configurable).
4. Consolidar todos los lotes en un único `P2Output` (códigos `RF-xxx` consecutivos, validaciones cruzadas: clasificaciones ↔ RF, HU `no_aplicable` sin RF, `stories_without_requirements` exacto).
5. Llamar a `persist_p2_requirements` (RPC) con `P2Output.to_rpc_payload()`. **Falta el método en el cliente Supabase** — ver T-F4-07.
6. Escribir `P2Output` en `context.p2_output`. Emitir `stage_completed` con los `LlmRun` agregados.

### T-F4-07 · Caller de `persist_p2_requirements` en el cliente Supabase
- `ai_service/clients/supabase.py` hoy solo expone `create_supabase_client`. Añadir el método que invoca la RPC `persist_p2_requirements` (y, en fases posteriores, `persist_p4_clusters` / `persist_p6_unit`).
- Usar `asyncio.to_thread` para el cliente síncrono (igual que el repositorio de Fase 1).
- Traducir errores SQL (errcode `23503`, etc.) a excepciones de dominio claras.

### T-F4-08 · Pruebas
- **P1:** pruebas con `DocumentTextExtractor` fake (no necesita `LlmClient` fake). Cobertura: happy path (bloques que cumplen la plantilla), bloques que no cumplen → `UnresolvedFragment`, `EMPTY_DOCUMENT`, `NO_STORIES_FOUND` (todo unresolved).
- **P2:** pruebas con `LlmClient` fake. Cobertura: happy path, `LLM_INVALID_OUTPUT` con reintento de lote, D-29 (0 RF → `skip_remaining`).
- Prueba de integración de la RPC `persist_p2_requirements` (si se eligió T-02 opción a).
- Confirmar que las pruebas de contratos siguen pasando (regresión).

### T-F4-09 · Actualizar roadmap y cierre documental
- Marcar Fase 4 como ✅ en `docs/pipeline_roadmap.md`.
- Generar `cierre_documental_fase4.md` (supuestos tomados, decisiones, advertencias nuevas).

### T-F4-10 · Persistencia de P1 (Hueco A) — delegado al agente
- **Decisión: opción (a)** — añadir una RPC `persist_p1_user_stories` en `supabase/schema.sql`,
  consistente con `persist_p2/p4/p6`, idempotente vía `ON CONFLICT (generation_id, code) DO
  UPDATE`, que inserte/actualice las HU (`code`, `position`, `original_text`, `role`, `action`,
  `goal`, `validation_status`). Recibe `generation_id` + payload.
- Añadir el **caller** en el cliente Supabase (igual que `persist_p2_requirements` en T-F4-07),
  con `asyncio.to_thread` y traducción de errcodes.
- P1 **no persiste** `unresolved_fragments` ni `issues` (D-22); solo las `user_stories`.

### T-F4-11 · Configuración de `P1Config` / `P2Config` (Hueco B) — delegado al agente
- Añadir a `ai_service/config.py` las variables de entorno que exigen los contratos:
  - `P1Config`: `P1_RULES_VERSION`, `P1_STORY_DELIMITER_PATTERN`, `P1_MAX_STORY_CHARS`.
  - `P2Config`: `LLM_MODEL` (nombre del modelo — hoy falta), `P2_PROMPT_VERSION`,
    `P2_MAX_STORIES_PER_CALL`, `P2_MAX_RETRIES`.
- Actualizar `.env.example` con los nuevos valores y defaults razonables.
- Estas variables alimentan la construcción de `P1Config` y `P2Config` en el wiring (T-F4-04).

> **Guía de implementación:** el detalle de "cómo" implementar T-F4-04 a T-F4-09 + callers está en
> `guia_implementacion.md` (sugerencias, no obligatorio).

---

## 4. Orden de ejecución sugerido

```
T-F4-01 (decisiones schema.sql)          ← primero, fija el contrato de persistencia
   │
   ├─► T-F4-02 (spec plantilla HU) ✅     ┐  aprobados; mover a código
   ├─► T-F4-03 (prompts P2) ✅            ┘
   ├─► T-F4-11 (config P1/P2)            ← Hueco B
   ├─► T-F4-10 (persist_p1 RPC)          ← Hueco A, depende de T-F4-01
   │
T-F4-07 (caller persist_p2 en Supabase)  ← depende de T-F4-01
   │
T-F4-04 (DI wiring)                       ← depende de config, prompts y callers
   │
   ├─► T-F4-05 (P1 run)  ← depende de plantilla + T-F4-10
   └─► T-F4-06 (P2 run)  ← depende de P1 (lee p1_output) y de T-F4-07
   │
T-F4-08 (pruebas)
   │
T-F4-09 (cierre documental)
```

---

## 5. Criterios de cierre

La Fase 4 está completa cuando **todos** estos puntos se cumplen:

- [ ] `NormalizeStage` y `RequirementsStage` no heredan de `StubStage` (lógica real).
- [ ] Un documento subido produce HU y RF **reales** persistidos en Supabase (P3–P7 siguen como stubs).
- [ ] Las decisiones T-01, T-02 y T-04 están registradas en `decisiones_schema.sql.md` y aplicadas en `schema.sql` (lo que corresponda).
- [ ] Existe la **spec de plantilla de HU** (P1, sin LLM) y `prompts/p2.py` + texto (P2, con LLM); cada uno lo usa su etapa.
- [ ] P1 no recibe `LlmClient`; identifica HU con heurística y marca las no identificadas como `UnresolvedFragment`.
- [ ] El cliente Supabase expone `persist_p2_requirements` (caller).
- [ ] Existe la RPC `persist_p1_user_stories` (+ caller) y P1 persiste las HU.
- [ ] `config.py` expone las variables de `P1Config`/`P2Config` (Hueco B).
- [ ] Pruebas de P1 (extractor fake) y P2 (LLM fake) pasan; la suite de contratos sin regresión.
- [ ] D-29 funciona: 0 RF en P2 → P3–P7 `skipped` y generación `completed`.
- [ ] `pipeline_roadmap.md` actualizado y `cierre_documental_fase4.md` generado.

---

## 6. Reglas del pipeline que aplican a esta fase (referencia rápida)

| Regla | Cómo aplica en Fase 4 |
|---|---|
| D-29 | Si P2 devuelve 0 RF → `skip_remaining=True`: P3–P7 quedan `skipped`. P1/P2 deben respetarlo. |
| D-22 | `UnresolvedFragment` e incidencias de validación **solo viven en memoria** (no se persisten). |
| D-27 | Las clasificaciones de HU se persisten en `user_stories.classification` / `classification_rationale` / `clarification_items` vía `persist_p2_requirements`. |
| R-AP-2 / R-AP-3 | Las etapas dependen de puertos, nunca de un adaptador concreto. P1 usa `DocumentStorage` + `DocumentTextExtractor` (sin `LlmClient`); P2 usa `LlmClient`. |
| R-DI-2 | Los puertos se inyectan por constructor; el wiring ocurre en `main.py`/`dependencies.py`. |
| R-FA-3 | Los imports de SDKs del proveedor son lazy (ya hechos en los factories). |

---

## 7. Riesgos y advertencias activas (heredadas)

1. **`dict` en modelos frozen** — `LlmSettings.parameters`, `TestData.inputs`, etc. `frozen=True` no los hace inmutables por dentro. Aparece si una etapa muta un dict del contrato.
2. **`persist_p6_unit` no guarda `validation_notes`** — no afecta a P1/P2, pero tener presente para Fase 7.
3. **Supuestos 1–11 de `cierre_documental.md` (Fase 3)** siguen "a revisar": si la implementación real de P1/P2 choca con alguno (p. ej. supuesto 3: todas las HU `invalid` → P1 no puede devolver `P1Output`), plantear el ajuste del contrato en el cierre de Fase 4.

---

## 8. Total de fases del proyecto (roadmap completo)

| Fase | Nombre | Estado |
|---|---|---|
| 1 | Infraestructura del pipeline (stubs, API, persistencia, recuperación) | ✅ |
| 1.5 | Conexión frontend–backend (CORS, polling, rehidratación) | ✅ |
| 2 | Subida de documentos (backend + frontend) | ✅ |
| 3 | Contratos P1–P6 + `PipelineContext` + prompts P6 | ✅ |
| **4** | **Implementación de P1 (heurística) y P2 (LLM)** | **🔲 actual** |
| 5 | Implementación de P3 y P4 (embeddings + clustering) | 🔲 |
| 6 | Implementación de P5 (contexto estructurado) | 🔲 |
| 7 | Implementación de P6 (generación de casos de prueba) | 🔲 |
| 8 | Implementación de P7 (evaluación) + cierre (SSE, integración E2E) | 🔲 |

Son **9 hitos** (1, 1.5, 2, 3, 4, 5, 6, 7, 8). La lógica de cada etapa del pipeline (P1–P7) se
implementa **una por fase** a partir de la Fase 4, salvo P1+P2 (juntas en Fase 4) y P3+P4 (juntas
en Fase 5) por su fuerte acoplamiento.

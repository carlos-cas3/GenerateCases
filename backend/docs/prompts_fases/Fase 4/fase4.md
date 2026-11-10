# Fase 4 — Implementación real de P1 y P2 (LLM)

> **Estado:** 🔲 pendiente (la Fase 3 está cerrada en el commit `a4940ea`).
> **Rama de la fase anterior:** `revision_fase3`
> **Documentos fuente:** `docs/pipeline_roadmap.md`, `docs/prompts_fases/Fase 3/cierre_documental.md`,
> `docs/prompts_fases/Fase 3/tareas_pendientes_final_fase3.md`, `ai_service/pipeline/contracts/p1.py`,
> `ai_service/pipeline/contracts/p2.py`, `ai_service/clients/llm.py`, `ai_service/clients/extractor.py`.
>
> Este archivo es el **resumen de alcance y roadmap** de la fase. Sirve como guía única para no
> repetir el contexto en cada sesión. El detalle de diseño vive en los documentos referenciados.

---

## 0. Objetivo de la fase

Que las etapas **P1** (normalización/segmentación de HU) y **P2** (clasificación + extracción de RF)
dejen de ser `StubStage` y ejecuten lógica real:

```
P1: Storage(bytes) → DocumentTextExtractor → texto → LLM → P1Output → persistir HU en BD
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

### T-F4-02 · Prompts de P1 (segmentación/normalización)
- Crear `ai_service/pipeline/prompts/p1.py` con el resolvedor (patrón de `p6.py`: cargar texto y exponer `resolve_p1_prompt(...)`).
- Crear el/los textos en `ai_service/pipeline/prompts/texts/` (p. ej. `p1_normalize.md`).
- El prompt debe pedir al LLM la estructura que `P1Output` valida: `UserStory` (code/id/position, secciones, incidencias de validación, `UnresolvedFragment`).
- Dejar definido el formato de salida esperado (JSON) y mapearlo a `P1Output` en la etapa.

### T-F4-03 · Prompts de P2 (clasificación + extracción de RF)
- Crear `ai_service/pipeline/prompts/p2.py` con el resolvedor.
- Crear el/los textos en `prompts/texts/` (p. ej. `p2_requirements.md`).
- El prompt debe pedir al LLM la estructura que `P2Output` valida: `StoryClassification`, `RequirementDraft` → `FunctionalRequirement`, evaluación de calidad, `stories_without_requirements`.
- P2 corre en **batches** (definir el tamaño del lote en `P2Config` o en settings): el prompt recibe un subconjunto de HU por llamada.

### T-F4-04 · Cableado de dependencias (DI)
- Inyectar `LlmClient`, `DocumentTextExtractor` y el repositorio en `NormalizeStage` y `RequirementsStage` por constructor (R-DI-2).
- Resolver en `main.py` / `api/dependencies.py` usando los factories (`LlmClientFactory`, `EmbeddingsClientFactory` no aplica aquí) y el compuesto de extractores.
- Las etapas ya no heredan de `StubStage`: heredan de `StageBase` e implementan `run()`.

### T-F4-05 · Implementar `NormalizeStage.run()` (P1)
1. Leer bytes del Storage (vía `Storage.download` / repositorio) y construir `SourceDocument` (`p1.py`).
2. Extraer texto con `DocumentTextExtractor.extract(data, file_type)`. Si sale `""` → `StageError(EMPTY_DOCUMENT)`.
3. Llamar al `LlmClient` con el prompt de P1; validar la respuesta contra `P1Output` (Pydantic lanza si no cumple).
4. Persistir las HU en la base de datos (campos `user_stories`: code, position, contenido, clasificación inicial). Definir cómo P1 escribe — hoy no hay RPC `persist_p1_*`; confirmar si se inserta vía repositorio directo o se añade una RPC (decisión a tomar en esta tarea).
5. Escribir `P1Output` en `context.p1_output`. Emitir `stage_completed` con `LlmRun` (tokens y latencia).
6. Tratar fallos: `EMPTY_DOCUMENT`, `LLM_INVALID_OUTPUT` (reintento configurable), `NO_STORIES_FOUND` (todas las HU `invalid`).

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
- Pruebas unitarias de P1 y P2 con **`LlmClient` fake** y **`DocumentTextExtractor` fake** (ya existen `llm_fake.py` y `extractor_fake.py`).
- Cobertura: happy path, `EMPTY_DOCUMENT`, `LLM_INVALID_OUTPUT` con reintento, `NO_STORIES_FOUND`, D-29 (0 RF → skip_remaining).
- Prueba de integración de la RPC `persist_p2_requirements` (si se eligió T-02 opción a).
- Confirmar que las 312 pruebas de contratos siguen pasando (regresión).

### T-F4-09 · Actualizar roadmap y cierre documental
- Marcar Fase 4 como ✅ en `docs/pipeline_roadmap.md`.
- Generar `cierre_documental_fase4.md` (supuestos tomados, decisiones, advertencias nuevas).

---

## 4. Orden de ejecución sugerido

```
T-F4-01 (decisiones schema.sql)          ← primero, fija el contrato de persistencia
   │
   ├─► T-F4-02 (prompts P1)  ┐
   ├─► T-F4-03 (prompts P2)  ┘  independientes entre sí
   │
T-F4-07 (caller persist_p2 en Supabase)  ← depende de T-F4-01
   │
T-F4-04 (DI wiring)                       ← depende de prompts y caller
   │
   ├─► T-F4-05 (P1 run)
   └─► T-F4-06 (P2 run)   ← depende de P1 (lee p1_output) y de T-F4-07
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
- [ ] `prompts/p1.py` + texto y `prompts/p2.py` + texto existen y los resuelve la etapa correspondiente.
- [ ] El cliente Supabase expone `persist_p2_requirements` (caller).
- [ ] Pruebas de P1 y P2 pasan con LLM/extractor fake; la suite de contratos (312) sin regresión.
- [ ] D-29 funciona: 0 RF en P2 → P3–P7 `skipped` y generación `completed`.
- [ ] `pipeline_roadmap.md` actualizado y `cierre_documental_fase4.md` generado.

---

## 6. Reglas del pipeline que aplican a esta fase (referencia rápida)

| Regla | Cómo aplica en Fase 4 |
|---|---|
| D-29 | Si P2 devuelve 0 RF → `skip_remaining=True`: P3–P7 quedan `skipped`. P1/P2 deben respetarlo. |
| D-22 | `UnresolvedFragment` e incidencias de validación **solo viven en memoria** (no se persisten). |
| D-27 | Las clasificaciones de HU se persisten en `user_stories.classification` / `classification_rationale` / `clarification_items` vía `persist_p2_requirements`. |
| R-AP-2 / R-AP-3 | Las etapas dependen de los puertos (`LlmClient`, `DocumentTextExtractor`), nunca de un adaptador concreto. |
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
| **4** | **Implementación de P1 y P2 (LLM)** | **🔲 actual** |
| 5 | Implementación de P3 y P4 (embeddings + clustering) | 🔲 |
| 6 | Implementación de P5 (contexto estructurado) | 🔲 |
| 7 | Implementación de P6 (generación de casos de prueba) | 🔲 |
| 8 | Implementación de P7 (evaluación) + cierre (SSE, integración E2E) | 🔲 |

Son **9 hitos** (1, 1.5, 2, 3, 4, 5, 6, 7, 8). La lógica de cada etapa del pipeline (P1–P7) se
implementa **una por fase** a partir de la Fase 4, salvo P1+P2 (juntas en Fase 4) y P3+P4 (juntas
en Fase 5) por su fuerte acoplamiento.

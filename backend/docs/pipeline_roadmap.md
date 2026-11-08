# Pipeline — Estado actual y roadmap

> Última actualización: noviembre 2026  
> Documento generado a partir de la revisión completa de `ai_service/pipeline/`.

---

## Resumen ejecutivo

El pipeline tiene **7 etapas** (P1–P7). La infraestructura de orquestación está **completamente terminada**, la capa de contratos (P1–P6) está **completamente definida y con pruebas**, y `PipelineContext` ya transporta los outputs entre etapas. Ninguna etapa tiene lógica real aún: todas son **stubs simulados**. El proyecto está listo para iniciar la **Fase 4 — implementación real de las etapas**.

---

## Arquitectura del pipeline

```
POST /api/v1/generations
  └─► GenerationsService.create()
        ├─ crea generation + 7 etapas en BD (status=queued / pending)
        └─ BackgroundTasks → PipelineRunService.run(PipelineContext)
                                 │
                                 ├─ update_generation: queued → running
                                 ├─ ProgressReporter (escribe en BD)
                                 └─ PipelineOrchestrator.run(context)
                                       │
                                       ├─ P1 NormalizeStage
                                       ├─ P2 RequirementsStage
                                       ├─ P3 EmbeddingsStage  ← omitida si clustering=false
                                       ├─ P4 ClusteringStage  ← omitida si clustering=false
                                       ├─ P5 ContextStage
                                       ├─ P6 GenerationStage
                                       └─ P7 EvaluationStage  ← no bloqueante (fallo ≠ failed)
```

### Archivos de infraestructura — todos completos ✅

| Archivo | Responsabilidad |
|---|---|
| `pipeline/catalog.py` | Registro estático de las 7 etapas: nombre, orden, `blocking` |
| `pipeline/context.py` | `PipelineContext`: payload mutable con outputs de cada etapa |
| `pipeline/events.py` | 6 tipos de eventos internos + protocolo `ProgressReporter` |
| `pipeline/orchestrator.py` | Ejecuta etapas, gestiona fallos, emite eventos, `skip_remaining` |
| `pipeline/stages/base.py` | `StageBase` (ABC), `StageResult`, `StageError`, `StubStage` |
| `services/pipeline_runs.py` | `PipelineRunService`, `RepositoryProgressReporter`, recuperación de interrupciones |

---

## Estado por etapa

| # | Clave | Nombre | Bloqueante | Contrato | Stage impl. | Prompts |
|---|---|---|---|---|---|---|
| 1 | `p1` | Procesamiento, segmentación y estructuración de HU | ✅ sí | ✅ completo | 🔴 stub | ❌ falta |
| 2 | `p2` | Clasificación de HU y extracción de RF | ✅ sí | ✅ completo | 🔴 stub | ❌ falta |
| 3 | `p3` | Generación de embeddings | ✅ sí | ✅ completo | 🔴 stub | — (sin LLM) |
| 4 | `p4` | Clustering semántico | ✅ sí | ✅ completo | 🔴 stub | — (sin LLM) |
| 5 | `p5` | Construcción de contexto estructurado | ✅ sí | ✅ completo | 🔴 stub | — (sin LLM) |
| 6 | `p6` | Generación de casos de prueba funcionales | ✅ sí | ✅ completo | 🔴 stub | ✅ completo (2 variantes) |
| 7 | `p7` | Evaluación de resultados | ❌ no | ⏸ pendiente | 🔴 stub | ⏸ pendiente |

> P3 y P4 se omiten (`skipped`) automáticamente cuando `clustering_enabled = false`.  
> P3/P4 se omiten también si P2 devuelve 0 RF (`skip_remaining = true` en P2).  
> P7 no se desarrolla en esta fase — ver sección correspondiente más abajo.

---

## `PipelineContext` — acumulador de outputs ✅

`context.py` implementa el patrón acumulador: cada etapa deposita su output en el campo
correspondiente para que las etapas posteriores lo lean. El orquestador pasa el mismo
contexto a todas las etapas sin conocer los contratos.

```
Arranque   → generation_id, document_id, configuration
P1 escribe → p1_output
P2 escribe → p2_output   (lee p1_output)
P3 escribe → p3_output   (lee p2_output)              solo si clustering=true
P4 escribe → p4_output   (lee p2_output, p3_output)   solo si clustering=true
P5 escribe → p5_output   (lee p1_output, p2_output, p4_output — p4 puede ser None)
P6 lee     → p5_output
```

Los imports de los contratos están bajo `TYPE_CHECKING` + `from __future__ import annotations`,
por lo que `context.py` no arrastra ninguna dependencia de `pipeline/contracts/` en runtime.

---

## Contratos P1–P6 — estado detallado

Todos los contratos son `ContractModel` (Pydantic, `frozen=True`, `extra="forbid"`).  
Pasan **312 pruebas** al cierre de la Fase 3.

### `contracts/common.py` ✅
Tipos base: `NonEmptyStr`, `UserStoryCode` (`HU-\d{3,}`), `RequirementCode` (`RF-\d{3,}`), `TestCaseCode` (`CP-\d{3,}`), `UnitId` (`U-\d{3,}`).  
Enums: `StoryValidationStatus`, `StoryClassificationCategory`, `RelationStatus`, `IssueSeverity`, `QualityCriterion`, `FindingKind`, `FileType`, `UnitStrategy`.  
Modelos compartidos: `SourceSpan`, `RequirementEvidence`, `LlmSettings`, `TestData`.

### `contracts/p1.py` ✅
`SourceDocument → P1Input → P1Output (tuple[UserStory])`  
Valida: conteos `valid/warning/invalid`, al menos 1 HU procesable, unicidad de `code/id/position`.

### `contracts/p2.py` ✅
`P2Input → P2LlmResponse (intermedio) → P2Output`  
Modelos clave: `StoryClassification`, `RequirementDraft`, `FunctionalRequirement`, `RequirementQualityAssessment`, `RequirementFinding`.  
`P2Output.to_rpc_payload()` → `persist_p2_requirements` (RPC Supabase, pendiente de implementar).  
Validaciones cruzadas: clasificaciones ↔ RF, HU `no_aplicable` no generan RF, `stories_without_requirements` exacto.

### `contracts/p3.py` ✅
`P3Input → P3Output (tuple[RequirementEmbedding])`  
`EmbeddingModelInfo` con dimensión; valida vectores finitos y dimensión uniforme.

### `contracts/p4.py` ✅
`P4Input → P4Output (tuple[SemanticCluster] + unassigned)`  
RF pueden estar en múltiples clusters (R6). `P4Output.to_rpc_payload()` → `persist_p4_clusters` (pendiente).

### `contracts/p5.py` ✅
`P5Input → P5Output (GenerationContext)`  
`P5Input.clustering: P4Output | None` — acepta `None` cuando el clustering está desactivado.  
`GenerationContext` valida: `by_cluster` exige `cluster_label`; `by_user_story` lo prohíbe y usa prompt diferente en P6.

### `contracts/p6.py` ✅
`P6Input (GenerationContext) → P6LlmResponse (intermedio) → P6Output`  
`TestCase`, `TestStep`, `RequirementTestCaseLink` (sale siempre `pending`).  
Valida: códigos `CP-xxx` consecutivos desde `CP-001`, máximo 1 unidad fallida (D-15).  
`P6UnitOutput.to_rpc_payload()` → `persist_p6_unit` (pendiente).

### `contracts/p7.py` — no se desarrolla en Fase 3
P7 no tiene contrato. Su diseño, dependencias de entrada y lógica se analizarán
cuando llegue su fase de implementación. Lo único definido hasta entonces es que
P7 es no bloqueante (su fallo no lleva la generación a `failed`, D-33) y que
corre siempre al final del pipeline.

---

## Prompts

| Archivo | Estado | Descripción |
|---|---|---|
| `prompts/p6.py` | ✅ completo | `resolve_p6_prompt(prompt_version, strategy)` — selecciona variante por `UnitStrategy` |
| `prompts/texts/contexto.md` | ✅ completo | Prompt P6 con clustering (`by_cluster`) |
| `prompts/texts/contexto_sin_clustering.md` | ✅ completo | Prompt P6 sin clustering (`by_user_story`) |
| `prompts/p1.py` + texto | ❌ falta | Se desarrolla en Fase 4 |
| `prompts/p2.py` + texto | ❌ falta | Se desarrolla en Fase 4 |
| `prompts/p7.py` + texto | ⏸ pendiente | Se desarrolla cuando se implemente P7 |

---

## Roadmap por fases

### ✅ Fase 1 — Infraestructura del pipeline
- Orquestador, eventos, reporter, catálogo, base de stages
- Persistencia de estado (BD) con 7 stages stub
- API de generaciones (crear, consultar, listar)
- Recuperación de arranque (`recover_interrupted_generations`)

### ✅ Fase 1.5 — Conexión frontend–backend
- CORS, manejo de errores HTTP
- Polling del progreso en el frontend (`useExecutionProgress`)
- `GenerationPage` con rehidratación por `?g=`

### ✅ Fase 3 — Contratos y contexto del pipeline
- Contratos P1–P6 completos con validaciones cruzadas (312 pruebas)
- `to_rpc_payload()` en P2, P4 y P6
- Prompts de P6 (2 variantes)
- `PipelineContext` con campos de output por etapa (`p1_output`…`p5_output`)
- Patrones verificados: Pipeline, Strategy, Dependency Injection, Adapter

### 🔲 Fase 4 — Implementación de P1 y P2 (LLM)
**Prerequisitos:** configuración LLM en `Settings`, prompts de P1 y P2.

- [ ] Variables de entorno LLM en `config.py` (proveedor, modelo, API key)
- [ ] Puerto `LlmClient` (Protocol) para desacoplar P2/P6 de la librería concreta
- [ ] Puerto `DocumentTextExtractor` (Protocol) para desacoplar P1 del storage
- [ ] Prompts para P1 (segmentación/normalización)
- [ ] Prompts para P2 (clasificación + extracción de RF)
- [ ] Implementar `NormalizeStage.run()` — extrae texto, llama al LLM, valida `P1Output`, persiste HU
- [ ] Implementar `RequirementsStage.run()` — llama al LLM en batches, valida `P2Output`, llama a `persist_p2_requirements`
- [ ] RPC `persist_p2_requirements` en el cliente Supabase

### 🔲 Fase 5 — Implementación de P3 y P4 (embeddings + clustering)
**Prerequisito:** proveedor de embeddings configurado.

- [ ] Variables de entorno para proveedor de embeddings
- [ ] Puerto `EmbeddingsClient` (Protocol)
- [ ] Implementar `EmbeddingsStage.run()` — genera vectores en batches, valida `P3Output`
- [ ] Implementar `ClusteringStage.run()` — aplica algoritmo, valida `P4Output`, llama a `persist_p4_clusters`
- [ ] RPC `persist_p4_clusters` en el cliente Supabase

### 🔲 Fase 6 — Implementación de P5 (contexto estructurado)
- [ ] Implementar `ContextStage.run()` — agrupa RF por cluster o por HU según `UnitStrategy`, construye `GenerationContext`, respeta `max_tokens_per_unit`

### 🔲 Fase 7 — Implementación de P6 (generación de casos de prueba)
- [ ] Implementar `GenerationStage.run()` — itera unidades, llama al LLM con prompt resuelto, valida `P6LlmResponse`, asigna códigos CP-xxx, llama a `persist_p6_unit`
- [ ] RPC `persist_p6_unit` en el cliente Supabase
- [ ] Poblar `summary` en la respuesta de la API (conteos HU/RF/CP)

### 🔲 Fase 8 — Implementación de P7 (evaluación) + cierre
P7 no se diseña ni implementa hasta esta fase. Lo que se sabe hasta ahora:
- Es no bloqueante (D-33): su fallo no cambia la generación a `failed`.
- Corre siempre después de P6, incluso si otras etapas fueron `skipped`.
- Sus entradas, contrato, prompts y lógica se definen al inicio de esta fase.

Otros cierres pendientes:
- [ ] SSE (`GET /api/v1/generations/{id}/events`) en sustitución del polling
- [ ] Pruebas de integración end-to-end con Supabase real

---

## Reglas clave del orquestador (referencia rápida)

| Regla | Descripción |
|---|---|
| D-15 | P6 se detiene en el primer fallo de unidad (`on_unit_failure = "fail"`) |
| D-29 | Si P2 devuelve 0 RF, activa `skip_remaining`: P3–P7 quedan `skipped` |
| D-31 | RF de otras unidades aparecen como `context_requirements` en `ContextUnit` |
| D-32 | RF sin cluster asignado no generan casos de prueba |
| D-33 | P7 es no bloqueante: su fallo no cambia la generación a `failed` |
| D-38 | P6 tiene dos variantes de prompt según `UnitStrategy` |
| D-39 | Sin clustering → `UnitStrategy.BY_USER_STORY`; con clustering → `BY_CLUSTER` |
| R6 | Un RF puede pertenecer a varios clusters; P5 decide en cuál es objetivo |

---

## Advertencias técnicas activas

1. **`dict` en modelos frozen** — Los siguientes campos tienen `dict` que `frozen=True` no hace realmente inmutable: `LlmSettings.parameters`, `TestData.inputs`, `P4Config.params`, `ClusteringAlgorithmInfo.params`, `TestCaseOutputSpec.json_schema`, `ContextUnit.requirement_to_stories`.
2. **`persist_p6_unit` no guarda `validation_notes`** — Los vínculos RF↔CP se insertan siempre `pending` y sin `validation_notes` (D-18 anotación de soporte no llega a la BD).
3. **`StageError` sin `stage_key`** — El diseño original preveía un campo `stage_key` en `StageError`, pero la implementación actual no lo incluye.

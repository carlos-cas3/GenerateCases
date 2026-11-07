# Cierre documental de la Fase 3

> **Fecha:** 2026-11-04\
> **Origen:** `decisiones_cierre_documental.txt` (decisiones del responsable) y `resultados_pipeline.md` (resultado de la implementación de los contratos P1–P6).\
> **Alcance:** solo documentación. Los cambios en contratos, tests, `openapi.yaml` y `schema.sql` van en un cambio separado, después (sección 5).

---

## 1. Decisiones cerradas

| ID | Tema | Decisión | Dónde quedó en `pipeline_design.md` |
|---|---|---|---|
| **D-36** | Con clustering, ningún RF queda asignado a un cluster | **Opción (a), solo con clustering (corregido por D-39).** P5 `completed` con aviso `INSUFFICIENT_CONTEXT` y 0 unidades; P6 y P7 `skipped`; generación `completed`. No es un fallo y no se emite `EMPTY_CONTEXT`. El contrato de P5 admite cero unidades solo con `by_cluster`. | R3, 1.4.1 (`units`), P4 (pocos RF), P5 (tabla de estados y errores), P6 y P7 (estado), 1.9 |
| **D-26** | Estructura de `test_data` | Solo `inputs` y `notes`. `preconditions` y `expected_result` son campos de primer nivel del caso. | 1.3.8, 1.4.2, P6 (invariante 9), 1.9 |
| **D-37** | Métricas de P7 v1 | `requirement_coverage` (solo `validated`), `proposed_requirement_coverage` (aparte), `story_coverage`, `cases_per_requirement`, `unassigned_ratio` (solo con clustering; sin clustering no se registra la fila). `formula_version = "v1"`. | P7 (tabla de fórmulas), 1.9 |
| **D-18** | Soporte del vínculo CP–RF | **Diferido.** Se retira `link_support_threshold` de `P6Config`; P6 no calcula score ni anota `validation_notes` en v1. | 1.3.8 (`validation_notes`), P6 (`P6Config`, invariante 6), 1.6.1, 1.9 |
| **D-38** | Variante de prompt de P6 según clustering | `contexto` con clustering (`by_cluster`); `contexto_sin_clustering` sin clustering (`by_user_story`). `P6Config.prompt_version` es la familia; la variante se resuelve por `context.strategy`. Ambas comparten `TestCaseOutputSpec`. Lo ejecutado se registra en `LlmRunInfo.prompt_version` y `runtime_info`. | 1.4.4 (`LlmRunInfo`), P6 (selección de prompt, `P6Config`), 1.9 |
| **D-39** | Unidades sin clustering | P5 agrupa los RF en lotes según `max_tokens_per_unit`; cada unidad lleva los RF objetivo del lote y sus HU de origen como contexto; `cluster_label = None`, `context_requirements = ()`. Modifica D-12. Corrige D-36: sin clustering no hay `INSUFFICIENT_CONTEXT`; P5 produce ≥ 1 unidad o falla con `EMPTY_CONTEXT`. | 1.4.1 (`GenerationContext`, `ContextUnit`, invariantes), P5 (comportamiento, errores, D-36), P6 y P7 (estado), 1.9 (D-12, D-36) |
| — | `StageError` | Se corrige el **diseño**, no el código: `StageError` no lleva `stage_key`; la etapa la aporta el orquestador. | 1.4.4 |

Otras correcciones de documentación hechas en este cierre:

- `pipeline_design.md` documenta ahora `ContextUnit.context_requirements`, `P6UnitOutput`, los sobres `P2LlmResponse` / `P6LlmResponse` y la forma real de `TestCaseOutputSpec` (`version`, `json_schema`). Lo había propuesto `resultados_pipeline.md`.
- La convención de inmutabilidad ya no dice `@dataclass(frozen=True)`: dice Pydantic v2 `frozen=True`, `extra="forbid"`.
- `decisiones_pipeline.md`: se corrige la FK de `unassigned_requirements` (T-03) y se marcan como cerrados los pendientes de `test_data` y de métricas de P7.

### 1.1 Detalle de D-37 (`formula_version = "v1"`)

| `metric_name` | Numerador | Denominador | Si no aplica / denominador 0 |
|---|---|---|---|
| `requirement_coverage` | RF con ≥ 1 vínculo `validated` | Total de RF | `metric_value = null` si no hay RF |
| `proposed_requirement_coverage` | RF con ≥ 1 vínculo `pending` o `validated` | Total de RF | Ídem |
| `story_coverage` | HU no `invalid` con ≥ 1 RF | HU no `invalid` | Ídem |
| `cases_per_requirement` | Vínculos CP–RF no `rejected` | Total de RF | Ídem |
| `unassigned_ratio` | RF en `unassigned_requirements` | Total de RF | **Sin clustering no se inserta la fila** (no es 0 ni `null`: la métrica no aplica). |

Recién terminada P6 todos los vínculos son `pending`, así que `requirement_coverage` vale 0 hasta que haya validación. Por eso existe `proposed_requirement_coverage`, que se muestra aparte y no cuenta como cobertura (R7).

### 1.2 Variantes de prompt de P6 (D-38)

| `semantic_clustering_enabled` | `strategy` | Unidad de P5 | Prompt de P6 |
|---|---|---|---|
| `true` con RF asignados | `by_cluster` | clúster / subunidad por tokens | `contexto` |
| `false` | `by_user_story` | lote de RF + HU de origen | `contexto_sin_clustering` |
| `true` sin ningún RF asignado | `by_cluster` | 0 unidades + `INSUFFICIENT_CONTEXT` (D-36) | `skipped` |
| `false` y no se puede construir ninguna unidad | `by_user_story` | `EMPTY_CONTEXT` (fallo) | `pending` |

---

## 2. Supuestos tomados al implementar los contratos (para revisión)

Vienen de la sección "Decisiones que tomé por ambigüedad" de `resultados_pipeline.md`.

| # | Supuesto | Motivo | Riesgo si es incorrecto | Estado |
|---|---|---|---|---|
| 1 | `TestCaseOutputSpec` tiene `version` y `json_schema`; el esquema se genera desde `P6LlmResponse` con `default_output_spec()`. | El diseño solo describía reglas en una tabla, sin campos. Generar el esquema desde el modelo garantiza que lo que se pide al LLM y lo que se valida coinciden. | Si un proveedor de LLM no acepta todo el JSON Schema que genera Pydantic, o si el prompt necesita un esquema distinto, habría que mantener dos esquemas y podrían divergir. | A revisar |
| 2 | `UserStory`: `valid_with_warnings` exige al menos una incidencia; una HU `valid` no puede tener incidencias de severidad `error`. | Que el estado y las incidencias no se contradigan. | Si P1 marca `valid_with_warnings` por una razón que no registra como incidencia, el contrato rechaza la salida y P1 falla. | A revisar |
| 3 | `P1Output` exige al menos una HU que no sea `invalid`. | Es justo la condición en la que P1 lanza `NO_STORIES_FOUND`. | Si todas las HU son `invalid`, P1 no puede devolver un `P1Output`: debe lanzar `StageError`. Si se quiere persistir igualmente las HU `invalid` para mostrar al usuario por qué se descartaron, el contrato lo impide. | A revisar |
| 4 | `P2Output`, comprobado de forma estricta: `stories_without_requirements` coincide exactamente con las HU clasificadas sin RF; una HU `no_aplicable` no puede generar RF; una sola evaluación de calidad por RF. | Coherencia interna y trazabilidad de por qué una HU no tiene RF. | Si el LLM genera un RF desde una HU `no_aplicable`, se rechaza la respuesta completa y se reintenta (más costo y latencia). Si en el futuro un RF se evalúa por varios métodos en registros separados, la regla de unicidad lo impide. | A revisar |
| 5 | `P5Input` solo admite las HU que originaron RF; los RF del clustering deben coincidir con los de entrada; `by_cluster` exige clustering. | Evita datos sin uso en P5 y asegura que P4 no perdió ni añadió RF. | Si P5 necesitara HU sin RF como contexto, o si se filtran RF entre P4 y P5 (por ejemplo, excluir RF `requiere_aclaracion`), el contrato rechaza la entrada. | A revisar |
| 6 | `ContextUnit` rechaza HU que ningún RF de la unidad referencia. | Que la unidad contenga solo lo relevante (invariante de 1.4.1). | Si se quiere incluir una HU solo como contexto (por ejemplo, de un prerrequisito, D-17), el contrato lo rechaza. | A revisar |
| 7 | Los vectores de embeddings rechazan también `±inf`, no solo `NaN`. | Un infinito rompe cualquier métrica de distancia igual que un `NaN`. | Bajo. Un proveedor que devuelva infinitos hace fallar P3 en lugar de propagar el dato. | A revisar |
| 8 | Un `SemanticCluster` necesita al menos un RF asignado. | Un cluster vacío no aporta nada a P5 y produciría una unidad sin objetivos. | Si un algoritmo devuelve clusters vacíos, P4 debe filtrarlos antes de construir la salida; si no lo hace, falla. | A revisar |
| 9 | `P6Output.failed_units` admite como máximo una unidad. | P6 se detiene en el primer fallo (D-15, `on_unit_failure="fail"`). | Si más adelante se permite continuar tras un fallo, hay que relajar el contrato. | A revisar |
| 10 | `P6UnitOutput.test_cases` puede venir vacío, pero `P6LlmResponse` exige al menos un caso; una respuesta sin casos es `LLM_INVALID_OUTPUT` y se reintenta. | Una unidad con RF objetivo siempre debería producir algún caso. | Si hay unidades donde legítimamente no hay nada que probar, se agotan los reintentos y la generación termina `failed` (D-15). | A revisar |
| 11 | El payload de `TestData` incluye todas las claves con sus valores por defecto (`{}`, `null`) en lugar de omitir las vacías. | Forma estable y predecible en BD y en la API. | Consultas o un frontend que distingan "sin datos de prueba" de "datos vacíos" verán siempre un objeto. Con D-26 (solo `inputs` y `notes`) falta decidir también si un caso sin datos guarda `test_data = null` o `{"inputs": {}, "notes": null}`. | **Pendiente (D-26)** |

---

## 3. Tareas y decisiones abiertas

| ID | Tema | Situación actual | Qué hay que decidir o hacer |
|---|---|---|---|
| **T-01** | Idempotencia de las RPC (`persist_p2_requirements`, `persist_p4_clusters`, `persist_p6_unit`) | No son idempotentes. Los `id` vienen en el payload, así que repetir la misma llamada falla por violación de PK o de `unique (generation_id, code)`. Si una llamada hace commit pero el cliente no recibe la respuesta (timeout) y reintenta, la etapa se marca `failed` aunque los datos estén guardados. | Elegir entre (a) idempotentes: si ya existe el mismo `id` con el mismo contenido, no hacer nada; (b) no reintentar nunca las RPC desde el cliente y documentarlo; (c) clave de idempotencia por llamada. Afecta a `schema.sql` y al repositorio. |
| **T-02** | HU duplicadas en `persist_p2_requirements` | Si `classifications` trae el mismo `user_story_code` dos veces, el `UPDATE … FROM` actualiza la fila una sola vez y el conteo no cuadra. La RPC lanza "N clasificaciones apuntan a HU inexistentes", un mensaje engañoso. El contrato `P2Output` ya impide duplicados, pero la RPC no se protege sola. | Rechazar los duplicados explícitamente en la RPC con un mensaje correcto (recomendado), o contar `distinct user_story_code`. Añadir un test RPC. |
| **T-03** | Referencia a `requirements(id)` en la documentación | `decisiones_pipeline.md` decía `REFERENCES requirements(id)`; la tabla real es `functional_requirements` con FK compuesta `(generation_id, id)`. | **Hecho en este cierre.** Queda revisar que no se repita en otros documentos fuera de `Fase 3/`. |
| **T-04** | Migración de `position` en `user_stories` | La migración aditiva (`schema.sql`, sección 5) añade `position` nullable y `unique (generation_id, position)`, pero no rellena las filas existentes. Las HU antiguas quedan con `position = null` y los listados que ordenan por `position` las devuelven en orden indefinido. | Definir el backfill (por ejemplo `row_number()` por generación, ordenando por el número de `code`) y decidir si después la columna pasa a `NOT NULL`. Documentar en el openapi cómo se ordenan las filas sin `position`. |
| **T-05** | Paso de datos entre etapas | Propuesta de `resultados_pipeline.md` (no implementada): añadir a `PipelineContext` un campo opcional por etapa (`p1: P1Output | None`, …). | Confirmar o descartar antes de implementar la lógica de las etapas. |

---

## 4. Lo que sigue sin decidir

- Supuestos 1–10 de la sección 2: pendientes de revisión del responsable.
- Supuesto 11: pendiente según D-26.
- D-38 y D-39 quedan cerradas (handoff `actualización_decisiones_incosistencia.md`).
- T-01, T-02, T-04 y T-05. T-05 sigue abierta y bloquea la implementación real de P5 (loteo de RF) y P6 (uso del prompt resuelto).
- Recomendaciones de `decisiones_pipeline.md` marcadas como "Recomendado" que siguen sin confirmar.

---

## 5. Cambio posterior: contratos, tests y API

No incluido en este cierre. Lista de lo que debe cambiar para alinear el código con las decisiones:

| Archivo | Cambio | Decisión |
|---|---|---|
| `ai_service/pipeline/contracts/p5.py` | `units` vacía solo con `by_cluster`; `by_user_story` exige ≥ 1 unidad y sin `context_requirements`. **Hecho.** | D-36, D-39 |
| `ai_service/pipeline/contracts/common.py` | `TestData` solo con `inputs` y `notes`. | D-26 |
| `ai_service/pipeline/contracts/p6.py` | Documentar `prompt_version` como familia; la variante se resuelve por `strategy`. **Hecho.** | D-38 |
| `ai_service/pipeline/contracts/p6.py` | Quitar `link_support_threshold` de `P6Config`. | D-18 |
| `ai_service/pipeline/prompts/` (nuevo) | Resolvedor `contexto` / `contexto_sin_clustering`. **Hecho.** | D-38 |
| `ai_service/pipeline/contracts/p7.py` (nuevo) | `P7Input` / `P7Output` con las métricas de D-37 y `formula_version`. | D-37 |
| Orquestador / P5 | `INSUFFICIENT_CONTEXT` y `skip_remaining` solo en D-36 (clustering sin RF asignados); sin clustering con 0 unidades → `EMPTY_CONTEXT`. Bloqueado por T-05. | D-36, D-39 |
| `docs/openapi.yaml` | Documentar D-36, la variante de prompt y el `skipped` sin clustering (**hecho**). Pendiente: esquema `TestData` solo con `inputs` y `notes`; métricas de P7 v1. | D-26, D-36, D-37, D-38 |
| `tests/` | Pruebas de `units` por estrategia y del resolvedor de prompts (**hecho**). Pendiente: `TestData` reducido, sin `link_support_threshold`, contratos de P7 y compatibilidad con el openapi. | Todas |
| `supabase/schema.sql` | Según lo que se decida en T-01, T-02 y T-04. | T-01, T-02, T-04 |

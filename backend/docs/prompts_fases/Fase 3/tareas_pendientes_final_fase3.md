# Tareas pendientes e inconsistencias — cierre de la Fase 3

> **Fecha:** 2026-11-09
> **Origen:** revisión del código contra las decisiones cerradas en `cierre_documental.md` y `decisiones_pipeline.md`.
> **Alcance:** inconsistencias detectadas en el código que no aplican las decisiones cerradas, tareas pendientes que no requieren decisión del responsable, y decisiones sobre `schema.sql` que el responsable debe tomar al iniciar la Fase 4.

---

## 1. Inconsistencias en el código (aplicables ahora)

Son cambios localizados que alinean el código con decisiones ya cerradas. No requieren nueva decisión del responsable.

### 1.1 `TestData` con 4 claves en lugar de 2 — D-26 no aplicado

**Decisión D-26:** `TestData` debe tener solo `inputs` y `notes`. `preconditions` y `expected_result` son campos de primer nivel del caso (`TestCaseDraft`, `TestCase`).

**Estado actual:**
- `ai_service/pipeline/contracts/common.py` — `TestData` tiene 4 campos: `preconditions`, `inputs`, `expected_results`, `notes`.
- `docs/openapi.yaml` (línea ~1268) — esquema `TestData` define 4 propiedades.
- `tests/test_contracts.py` (línea ~115) — construye `TestData` con 4 campos y valida que coincidan con el esquema del openapi.

Hay redundancia: `preconditions` y `expected_result` ya existen como campos de primer nivel en `TestCaseDraft` y `TestCase`.

**Cambios necesarios:**

| Archivo | Cambio |
|---|---|
| `ai_service/pipeline/contracts/common.py` | Eliminar `preconditions` y `expected_results` de `TestData`. Dejar solo `inputs` y `notes`. |
| `docs/openapi.yaml` | Eliminar las propiedades `preconditions` y `expected_results` del esquema `TestData` (~línea 1268). |
| `tests/test_contracts.py` | `test_test_data_contract_matches_openapi_schema` (~línea 112): cambiar la construcción de `TestData` a 2 campos. |

No requieren cambios: `tests/contract_factories.py` (ya usa `TestData` solo con `inputs`), ni los ejemplos del openapi (ya usan `test_data: { inputs: {...} }`).

### 1.2 `link_support_threshold` en `P6Config` — D-18 no aplicado

**Decisión D-18:** P6 no calcula score ni anota `validation_notes` en v1. Se retira `link_support_threshold` de `P6Config`.

**Estado actual:**
- `ai_service/pipeline/contracts/p6.py` (línea 174): `link_support_threshold: float | None = Field(default=None, ge=0, le=1)` sigue presente en `P6Config`.

El campo está muerto: ningún test lo referencia, no está en `schema.sql` ni en el openapi. `persist_p6_unit` ya no escribe `validation_notes` (inserta siempre `pending` sin notas).

**Cambios necesarios:**

| Archivo | Cambio |
|---|---|
| `ai_service/pipeline/contracts/p6.py` | Eliminar la línea `link_support_threshold` de `P6Config` (~línea 174). |

No hay tests que actualizar (no existen tests que referencien el campo).

### 1.3 OpenAPI: `MetricName` no documenta las 5 métricas de P7 — D-37 parcial

> **Nota:** P7 no se desarrolla en esta fase. Este punto se registra para cuando se implemente.

**Decisión D-37:** 5 métricas con `formula_version = "v1"`: `requirement_coverage`, `proposed_requirement_coverage`, `story_coverage`, `cases_per_requirement`, `unassigned_ratio` (solo con clustering).

**Estado actual:**
- `docs/openapi.yaml` — `MetricName` es `type: string` libre, no un enum. Solo aparece `requirement_coverage` como ejemplo. No hay documentación de `formula_version` ni de cuándo `unassigned_ratio` no aplica.

**Cambios necesarios (cuando se desarrolle P7):**

| Archivo | Cambio |
|---|---|
| `docs/openapi.yaml` | Enumerar las 5 métricas en `MetricName`. Documentar `formula_version = "v1"` y que `unassigned_ratio` no se registra sin clustering. |

---

## 2. Tarea ya resuelta — actualizar documentación

### 2.1 T-05: Campos de output en `PipelineContext`

**Estado documental:** `cierre_documental.md` lista T-05 como bloqueante.

**Estado real:** `ai_service/pipeline/context.py` **ya tiene** `p1_output`, `p2_output`, `p3_output`, `p4_output`, `p5_output` implementados. T-05 está resuelto.

**Acción:** marcar T-05 como cerrado en `cierre_documental.md` y `pipeline_roadmap.md`.

---

## 3. Tarea que no requiere cambios en Fase 3

### 3.1 Orquestador/P5: `INSUFFICIENT_CONTEXT` solo con clustering (D-36, D-39)

**Estado actual:** el contrato **ya está alineado**.

- `ai_service/pipeline/contracts/p5.py` — `GenerationContext._single_target` valida:
  - `by_cluster` → `units` puede ser vacía (D-36).
  - `by_user_story` → exige ≥ 1 unidad, sin `cluster_label`, sin `context_requirements` (D-39).
- `ai_service/pipeline/stages/base.py` — `StageResult` ya soporta `skip_remaining` (D-29).
- `ai_service/pipeline/context.py` — campos de output ya existen (T-05 resuelto).

La lógica real de P5 (emitir `INSUFFICIENT_CONTEXT` + `skip_remaining=True`, o `EMPTY_CONTEXT`) se implementa cuando P5 deja de ser stub en **Fase 6**. No hay nada que cambiar en Fase 3.

---

## 4. Decisiones sobre `schema.sql` — tomar al iniciar la Fase 4

Estas tareas surgieron durante la revisión de la Fase 3 (diseño de contratos y persistencia), pero **no bloquean el cierre de la Fase 3**: los contratos y el contexto ya están terminados. La decisión y la implementación deben tomarse al iniciar la **Fase 4** (implementación real de P1 y P2), porque es cuando las RPCs de `schema.sql` se invocan desde las etapas reales y los riesgos descritos pasan a ser posibles.

Se documentan aquí para que el responsable pueda revisarlas con tiempo, proponer mejoras al esquema de persistencia y, si lo considera oportuno, ajustar `schema.sql` antes de que las etapas dependan de él.

> **Guía para el responsable:** al revisar estas opciones, conviene mirar también las propias definiciones de las RPCs en `supabase/schema.sql` (`persist_p2_requirements`, `persist_p4_clusters`, `persist_p6_unit`) y el catálogo de advertencias activas en `pipeline_roadmap.md` (sección "Advertencias técnicas activas"). Si ve una forma más simple o más robusta de plantear la persistencia, este es el momento de plantearla.

### 4.1 T-01: Idempotencia de las RPCs

**RPCs afectadas:** `persist_p2_requirements`, `persist_p4_clusters`, `persist_p6_unit`.

**Problema:** Las RPCs hacen INSERTs con IDs que vienen en el payload. No son idempotentes: si se llama dos veces con el mismo payload, la segunda falla por violación de PK o `unique (generation_id, code)`.

**Escenario crítico:**

1. La etapa llama la RPC → Postgres hace commit.
2. La red cae antes de que el cliente reciba la respuesta.
3. El cliente interpreta el timeout como fallo → reintenta.
4. La segunda llamada falla por PK duplicada.
5. La etapa se marca `failed` aunque los datos ya están guardados.

**Probabilidad:** baja en desarrollo local, real en producción con red inestable o timeouts ajustados.

| Opción | Qué hace | Pros | Contras |
|---|---|---|---|
| (a) RPCs idempotentes | Si ya existe el mismo `id` con el mismo contenido, no hace nada (no-op) | Reintentos seguros, el cliente no necesita lógica especial | Más código SQL, hay que definir "mismo contenido" (comparar jsonb) |
| (b) No reintentar RPCs | La etapa marca `failed` si la RPC falla, sin reintentar la persistencia | Simple, no cambia SQL | Un timeout post-commit deja la generación `failed` con datos guardados — el usuario ve un fallo falso |
| (c) Clave de idempotencia | Cada llamada lleva un `idempotency_key`; la RPC lo guarda y si llega repetido, devuelve el resultado anterior | Solución estándar, robusta | Requiere tabla adicional de `idempotency_keys`, más infraestructura |

**Impacto:** `schema.sql` (definición de RPCs) y potencialmente el repositorio (lógica de reintento). **Decisión al iniciar Fase 4.**

---

### 4.2 T-02: HU duplicadas en `persist_p2_requirements`

**Problema:** La RPC recibe `classifications` (lista de HU con su clasificación) y hace `UPDATE ... FROM jsonb_to_recordset(...)`. Si el mismo `user_story_code` aparece dos veces:

- El `UPDATE` afecta la fila una sola vez (SQL no procesa duplicados del `FROM`).
- `v_expected` cuenta ambas entradas → `v_updated < v_expected`.
- La RPC lanza: *"N de N clasificaciones apuntan a HU inexistentes"* — un mensaje que no corresponde a la causa real.

**Probabilidad:** muy baja. El contrato `P2Output` ya valida unicidad de `user_story_code`, así que nunca llega un payload duplicado. Es un problema de defensa en profundidad.

| Opción | Qué hace | Pros | Contras |
|---|---|---|---|
| (a) Rechazar duplicados explícitamente | Antes del `UPDATE`, verificar si hay `user_story_code` repetidos y lanzar error claro ("HU-001 aparece 2 veces") | Mensaje correcto, defensa en profundidad | Más código SQL, hay que añadir un test RPC |
| (b) Contar `distinct` | Cambiar `v_expected` a `count(distinct user_story_code)` | Una línea de cambio | Silencia el problema: los duplicados se ignoran sin avisar |

**Impacto:** solo `schema.sql` (la RPC) y un test. Recomendado: opción (a). **Decisión al iniciar Fase 4.**

---

### 4.3 T-04: Backfill de `position` en `user_stories`

**Problema:** La migración aditiva añade `position` nullable con `unique (generation_id, position)`. No rellena las filas existentes — las HU antiguas quedan con `position = null` y los listados que ordenan por `position` devuelven orden indefinido.

**Probabilidad:** solo afecta a generaciones existentes antes de la migración. Las nuevas siempre traen `position` asignado por P1.

| Opción | Qué hace | Pros | Contras |
|---|---|---|---|
| (a) Backfill con `row_number()` | `UPDATE user_stories SET position = row_number() OVER (PARTITION BY generation_id ORDER BY code) WHERE position IS NULL` | Todas las filas quedan ordenadas consistentemente | El orden se infiere de `code` (texto), no del orden real de P1 — `HU-1000` queda antes que `HU-2` |
| (b) Dejar nullable + documentar | Las filas sin `position` se ordenan al final o por `code` como fallback | Simple, no requiere backfill | Orden indefinido para datos antiguos |

**Impacto:** `schema.sql` (migración) y cómo el frontend ordena los listados. **Si no hay datos en producción todavía, el problema es teórico** — basta con dejar `position` nullable y documentar el orden en el openapi (opción b).

---

## 5. Resumen

| # | Tarea | Tipo | Archivos | Bloquea Fase 3? |
|---|---|---|---|---|
| 1.1 | Reducir `TestData` a 2 campos (D-26) | Inconsistencia — aplicar | `common.py`, `openapi.yaml`, `test_contracts.py` | Sí |
| 1.2 | Eliminar `link_support_threshold` (D-18) | Inconsistencia — aplicar | `p6.py` | Sí |
| 1.3 | OpenAPI: enum de métricas P7 (D-37) | Pendiente — cuando se desarrolle P7 | `openapi.yaml` | No |
| 2.1 | Marcar T-05 como cerrado | Lag documental | `cierre_documental.md`, `pipeline_roadmap.md` | No |
| 3.1 | Orquestador/P5: `INSUFFICIENT_CONTEXT` | Ya hecho en contrato; lógica es Fase 6 | — | No |
| 4.1 | T-01: Idempotencia de RPCs | Decisión para Fase 4 (revisar `schema.sql`) | `schema.sql`, repositorios | No |
| 4.2 | T-02: HU duplicadas en RPC P2 | Decisión para Fase 4 (revisar `schema.sql`) | `schema.sql` | No |
| 4.3 | T-04: Backfill de `position` | Decisión para Fase 4 (revisar `schema.sql`) | `schema.sql` | No |

**Para cerrar la Fase 3** basta con aplicar las tareas 1.1 y 1.2 y marcar T-05 como cerrado.

**Decisiones de `schema.sql` (T-01, T-02, T-04):** se documentan aquí para que el responsable las revise con tiempo y, si lo considera oportuno, proponga mejoras al esquema de persistencia. La decisión y la implementación se toman al iniciar la Fase 4, cuando las etapas reales (P1, P2) empiezan a invocar las RPCs y los riesgos descritos pasan a ser posibles.

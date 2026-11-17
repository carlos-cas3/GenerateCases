# Impacto de la Fase 7 — qué archivos cambian y en qué orden

> Leer este archivo **antes** de empezar a implementar la Fase 7.
> Describe todos los archivos que se ven afectados, agrupados por área,
> con el orden en que deben tocarse para no bloquear el trabajo.
> El plan detallado de cada tarea está en [`fase7.md`](fase7.md).

---

## Regla de oro

No escribas una sola línea de `GenerationStage.run()` antes de haber
completado los puntos **🔴 Obligatorios**. El contrato y la configuración
son la base de todo lo demás.

---

## 🔴 Obligatorios — hacer primero

Estos dos cambios desbloquean todo lo demás. Sin ellos el contrato actual
bloquea la implementación.

### 1. `ai_service/pipeline/contracts/p6.py` — T-F7-01

Dos cambios puntuales que modifican D-15:

| Qué | Cambio |
|---|---|
| `P6Output.failed_units` | Eliminar `max_length=1` — ahora pueden fallar múltiples unidades |
| `P6Config.on_unit_failure` | Cambiar `Literal["fail"]` → `Literal["continue"]` |

Después de este cambio, correr los tests de contrato existentes y
actualizar los que fallen por `on_unit_failure="fail"` o `max_length=1`.

### 2. `ai_service/config.py` + `.env` + `.env.example` — T-F7-02

Añadir las 5 variables nuevas de P6:

| Variable | Default | Descripción |
|---|---|---|
| `P6_PROMPT_VERSION` | `v1` | Versión del prompt de P6 |
| `P6_MAX_RETRIES` | `1` | Reintentos por unidad ante JSON inválido del LLM |
| `P6_FAILURE_THRESHOLD` | `0.0` | Proporción máxima de unidades fallidas (0.0–1.0) |
| `P6_MAX_CASES_MULTIPLIER` | `3` | Tope dinámico = multiplicador × RF objetivo de la unidad |
| `P6_MAX_CASES_ABSOLUTE` | `50` | Tope absoluto de casos por unidad |

---

## 🟡 Implementación — en este orden

### 3. `ai_service/pipeline/prompts/texts/contexto.md` y `contexto_sin_clustering.md` — T-F7-06

Revisar **antes** de implementar la etapa. Los dos prompts deben ser
estructuralmente equivalentes para que el experimento de comparación
baseline vs clustering sea válido (D-F7-9). Ver checklist en `fase7.md §Revisión de prompts`.

Si se modifica alguno, actualizar `P6_PROMPT_VERSION` en `.env`.

### 4. `ai_service/pipeline/stages/p6_generation.py` — T-F7-03

Reemplazar el stub actual con:
- `GenerationStage` real (lógica de P6)
- `GenerationStubStage` al final del módulo (mismo patrón que P1–P5)

### 5. `ai_service/pipeline/stages/__init__.py` — T-F7-02 y T-F7-03

Tres cambios en este archivo:
1. Añadir `build_p6_config(settings) -> P6Config`
2. Mover `GenerationStage` fuera de `PENDING_STUB_STAGE_CLASSES` y añadir `GenerationStubStage`
3. Extender `build_real_stages()` para instanciar `GenerationStage` real con su config

### 6. `ai_service/repositories/pipeline_results.py` — T-F7-04

Añadir al puerto:
```python
async def persist_p6_unit(self, generation_id: UUID, payload: dict[str, Any]) -> None: ...
```

### 7. `ai_service/repositories/supabase_pipeline_results.py` — T-F7-04

Implementar el caller de la RPC `persist_p6_unit` (ya desplegada en Supabase).
Misma estructura que `persist_p4_clusters`: `asyncio.to_thread` + traducción de errcodes.

### 8. `ai_service/repositories/in_memory.py` — T-F7-04

Implementar `persist_p6_unit` en el fake:
- Almacenar en `InMemoryStore.test_cases`
- Idempotencia por `(generation_id, code)`
- Validar FK: los `requirement_codes` deben existir en `functional_requirements`

---

## 🟡 Summary de la API

### 9. `ai_service/schemas/generations.py` — T-F7-05

Actualizar `GenerationSummary` con los 5 campos de D-F7-8:

```python
class GenerationSummary(BaseModel):
    user_stories_count: int
    requirements_count: int
    clusters_count: int
    test_cases_count: int
    test_cases_failed_units: int
```

Los campos opcionales actuales (`invalid_user_stories_count`, `validated_relations_count`,
`metrics`) se retiran o quedan para P7.

### 10. `ai_service/repositories/generations.py` — T-F7-05

Añadir dos métodos al puerto:
```python
async def build_summary(self, generation_id: UUID) -> GenerationSummary: ...
async def update_summary(self, generation_id: UUID, summary: GenerationSummary) -> None: ...
```

### 11. Adaptador Supabase de generaciones — T-F7-05

`build_summary`: consultas de conteo a Supabase (HU, RF, clusters, casos).
`update_summary`: escribe en la columna `summary jsonb` de `generations`
(añadida en `schema.sql` con `ALTER TABLE generations ADD COLUMN IF NOT EXISTS summary jsonb`
— ya incluida en la sección de migraciones aditivas del schema).

### 12. `ai_service/repositories/in_memory.py` — T-F7-04 y T-F7-05

**T-F7-04** — añadir en `InMemoryStore`:
```python
test_cases: dict[UUID, dict[str, dict[str, Any]]] = field(default_factory=dict)
# gid → code → fila  (mismo patrón que `requirements`)
```

Implementar `persist_p6_unit` en `InMemoryPipelineResultsRepository`:
- Idempotencia por `(generation_id, code)`: ON CONFLICT DO UPDATE.
- FK: los `requirement_codes` deben existir en `store.requirements[generation_id]`.

**T-F7-05** — implementar `build_summary` y `update_summary` en
`InMemoryGenerationsRepository` contando desde `InMemoryStore`.

### 13. `ai_service/services/pipeline_runs.py` — T-F7-05

En el handler del evento `PipelineCompleted`, añadir:
```python
summary = await generations_repo.build_summary(generation_id)
await generations_repo.update_summary(generation_id, summary)
```

---

## 🟢 Tests

### 14. Tests de contrato existentes — T-F7-01

Después del cambio en `p6.py`, correr:
```
py -m pytest tests/test_contracts.py tests/test_contracts_invariants.py -v
```
Actualizar los tests que usen `on_unit_failure="fail"` o `max_length=1`.

### 15. `tests/test_p6_generation.py` — T-F7-07 (archivo nuevo)

Casos a cubrir (detalle en `fase7.md §T-F7-07`):
- Camino feliz `by_cluster` y `by_user_story`
- Fallo de unidad con threshold 0.0 y 0.5
- Truncado de casos (`CASES_TRUNCATED`)
- Reintentos por JSON inválido
- Numeración global CP-xxx sin saltos
- Guardias (`p5_output is None`)
- 0 unidades en el contexto

### 16. `tests/test_stages_wiring.py` — T-F7-07 (extensión)

Añadir tests E2E HTTP:
- Pipeline completo P1→P6 con LLM fake, clustering activo → casos generados, summary poblado
- Pipeline completo sin clustering → misma verificación
- Todas las unidades fallidas con threshold=0.0 → generación `failed`
- `GET /api/v1/generations/{id}` devuelve `summary` con los 5 campos

---

## 🟢 Documentación — al cerrar la fase

### 17. `docs/pipeline_roadmap.md` — T-F7-08
- Marcar Fase 7 como ✅
- Actualizar `PENDING_STUB_STAGE_CLASSES` (solo queda P7)
- Actualizar comentario de `PIPELINE_STAGES` (P1–P6 reales)

### 18. `docs/prompts_fases/Fase 7/cierre_documental_fase7.md` — T-F7-08
- Archivo nuevo, mismo formato que cierres anteriores

### 19. `docs/calibracion_resultados/iteracion_1.md` — T-F7-08
- Primera generación real con el pipeline completo
- Usar la plantilla de `docs/calibracion_resultados/plantilla.md`

---

## Resumen visual

```
🔴 p6.py (contrato)
🔴 config.py + .env + .env.example
        ↓
🟡 contexto.md + contexto_sin_clustering.md (revisar prompts)
        ↓
🟡 p6_generation.py (etapa real)
🟡 stages/__init__.py (wiring)
        ↓
🟡 pipeline_results.py + adaptadores (persist_p6_unit)
        ↓
🟡 schemas/generations.py (GenerationSummary)
🟡 generations.py + adaptadores (build_summary / update_summary)
🟡 pipeline_runs.py (llamar al summary en PipelineCompleted)
        ↓
🟢 tests (contrato + test_p6_generation.py + wiring)
        ↓
🟢 docs (roadmap + cierre + calibración iteración 1)
```

---

## Conteo de archivos afectados

| Categoría | Archivos | Acción |
|---|---|---|
| Contratos | 1 | Modificar |
| Configuración | 3 | Añadir variables |
| Etapa | 2 | Implementar / modificar |
| Repositorio resultados | 3 | Añadir método |
| Repositorio generaciones | 3 | Añadir métodos |
| Servicio | 1 | Extender handler |
| Schemas API | 1 | Actualizar |
| Prompts | 2 | Revisar |
| Tests | 3 | Nuevos / actualizar |
| Docs | 3 | Nuevos / actualizar |
| **Total** | **22** | |

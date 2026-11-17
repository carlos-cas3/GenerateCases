# Fase 7 — Implementación real de P6 (generación de casos de prueba)

> **Estado:** 🔲 pendiente de implementación
> **Fase anterior:** Fase 6 (P5 contexto estructurado) — ✅ cerrada (493 tests).
> Detalle en `docs/prompts_fases/Fase 6/cierre_documental_fase6.md`.
> **Documentos fuente:**
> `docs/pipeline_roadmap.md`,
> `ai_service/pipeline/contracts/p6.py`,
> `ai_service/pipeline/contracts/p5.py` (`GenerationContext`, `ContextUnit`),
> `ai_service/pipeline/prompts/texts/contexto.md`,
> `ai_service/pipeline/prompts/texts/contexto_sin_clustering.md`,
> `ai_service/pipeline/prompts/p6.py`,
> `ai_service/config.py`,
> `docs/architecture_patterns.md`,
> `docs/calibracion_variables.md`.
>
> Este archivo es el **plan de la fase**: decisiones tomadas, trabajo a realizar
> y criterios de cierre. No contiene código. El detalle de lo que se implementó
> quedará en `cierre_documental_fase7.md` al cerrar la fase.

---

## Objetivo de la fase

Que `GenerationStage` deje de ser un `StubStage` y ejecute lógica real:

```
P6: GenerationContext (unidades con RF objetivo, RF de contexto, HU)
      → por cada unidad: llama al LLM con el prompt correcto
      → valida la respuesta con P6LlmResponse
      → asigna códigos CP-xxx consecutivos globales
      → persiste con persist_p6_unit (atómico por unidad)
      → escribe context.p6_output
```

Al cerrar la fase, el pipeline completo P1→P6 produce casos de prueba reales
persistidos en Supabase. P7 sigue siendo stub.

Adicionalmente esta fase:
- Corrige el contrato `P6Output` y `P6Config` para permitir que múltiples
  unidades fallen (modifica D-15, ver §Decisiones).
- Puebla el campo `summary` en la respuesta de la API.
- Establece la base para el experimento de comparación entre la estrategia
  `by_cluster` (con clustering semántico) y el baseline `by_user_story`
  (sin clustering).

---

## Estado del código relevante al empezar

### Lo que ya existe y no se toca

| Artefacto | Archivo | Observación |
|---|---|---|
| Contrato completo `P6Input / P6LlmResponse / P6Output / TestCase / TestStep` | `pipeline/contracts/p6.py` | Escrito en Fase 3; **se modifica** en T-F7-01 (ver §Decisiones) |
| `GenerationContext` con unidades listas | `pipeline/contracts/p5.py` | Producido por P5 real (Fase 6) |
| Prompt `contexto.md` (by_cluster) | `pipeline/prompts/texts/contexto.md` | Existente; revisar antes de implementar (ver §Prompts) |
| Prompt `contexto_sin_clustering.md` (by_user_story) | `pipeline/prompts/texts/contexto_sin_clustering.md` | Existente; revisar antes de implementar (ver §Prompts) |
| `resolve_p6_prompt(prompt_version, strategy)` | `pipeline/prompts/p6.py` | Selecciona variante por `UnitStrategy`; no se modifica |
| RPC `persist_p6_unit` | `supabase/schema.sql` | Desplegada en Supabase desde 2026-11-11; idempotente por `(generation_id, code)` |
| `LlmClient` con Ollama | `clients/ollama_llm.py` | Funciona (lo usa P2); P6 lo recibe por constructor |
| `GenerationStage` (stub actual) | `pipeline/stages/p6_generation.py` | Se reemplaza en T-F7-03 |
| `PENDING_STUB_STAGE_CLASSES` | `pipeline/stages/__init__.py` | Se retira `GenerationStage`; se añade `GenerationStubStage` |

### Lo que se va a crear o modificar

| Artefacto | Archivo | Acción |
|---|---|---|
| Contrato `P6Output` y `P6Config` | `pipeline/contracts/p6.py` | Modificar en T-F7-01 (D-15 revisado) |
| Variables de entorno P6 | `config.py`, `.env`, `.env.example` | Crear en T-F7-02 |
| `build_p6_config` y wiring | `pipeline/stages/__init__.py` | Crear en T-F7-02 |
| `GenerationStage` real | `pipeline/stages/p6_generation.py` | Reemplazar stub en T-F7-03 |
| `GenerationStubStage` | `pipeline/stages/p6_generation.py` | Crear al lado de la etapa real |
| Caller `persist_p6_unit` | `repositories/pipeline_results.py` y adaptadores | Crear en T-F7-04 |
| Campo `summary` en la API | `ai_service/schemas/generations.py`, `repositories/generations.py` | Poblar en T-F7-05 |
| Prompts revisados | `pipeline/prompts/texts/contexto.md`, `contexto_sin_clustering.md` | Revisar y ajustar en T-F7-06 si es necesario |
| Pruebas de P6 | `tests/test_p6_generation.py` | Crear en T-F7-07 |
| Pruebas de wiring | `tests/test_stages_wiring.py` | Extender en T-F7-07 |
| Roadmap + cierre documental | `docs/pipeline_roadmap.md`, `cierre_documental_fase7.md` | Actualizar en T-F7-08 |

---

## Decisiones de la fase

### D-F7-1 — Revisión de D-15: procesar todas las unidades (no parar en el primero fallo)

**D-15 original:** P6 se detiene en el primer fallo de unidad (`on_unit_failure = "fail"`).

**D-15 revisado:** P6 intenta procesar **todas** las unidades. Las que fallan se registran
en `P6Output.failed_units`. Al final, si la proporción de unidades fallidas supera
`P6_FAILURE_THRESHOLD`, la generación queda `failed`; si no, queda `completed` con
los casos de las unidades exitosas y un aviso por las fallidas.

**Cambios en el contrato:**
- `P6Output.failed_units`: eliminar `max_length=1` — puede haber múltiples fallos.
- `P6Config.on_unit_failure`: cambiar el tipo de `Literal["fail"]` a
  `Literal["continue"]` — el único modo soportado ahora es continuar tras un fallo.
  El campo se mantiene para extensibilidad futura.

**Impacto:** los tests existentes del contrato que usen `max_length=1` o
`on_unit_failure="fail"` deben actualizarse.

### D-F7-2 — Umbral de fallo configurable (`P6_FAILURE_THRESHOLD`)

Una variable de entorno `P6_FAILURE_THRESHOLD` (float, 0.0–1.0, default `0.0`)
define la proporción máxima de unidades que pueden fallar sin que la generación
quede `failed`:

| Valor | Comportamiento |
|---|---|
| `0.0` (default) | Cualquier unidad fallida → generación `failed` |
| `0.5` | Hasta la mitad pueden fallar → generación `completed` con aviso |
| `1.0` | Todas pueden fallar → generación siempre `completed` |

El cálculo: `failed_units / total_units > threshold` → generación `failed`.

Con `0.0` el comportamiento es equivalente al D-15 original pero sin parar antes
de intentar las demás unidades.

### D-F7-3 — Una llamada al LLM por unidad

P6 hace **una sola llamada al LLM** por unidad de generación. El LLM recibe todos
los RF objetivo, RF de contexto y HU de la unidad en un único mensaje y devuelve
todos los casos de prueba de esa unidad en un único JSON.

Justificación: con Ollama local, una llamada por RF multiplica la latencia sin
aportar beneficio de fiabilidad con el modelo configurado. Si en el futuro un modelo
produce JSON truncado con unidades grandes, se puede introducir una llamada por RF
como modo alternativo.

### D-F7-4 — Máximo de casos por unidad configurable

Dos variables de entorno controlan el máximo de casos de prueba que P6 puede
generar por unidad:

- `P6_MAX_CASES_MULTIPLIER` (int, default `3`): el tope dinámico es
  `multiplier × len(unit.requirements)`. Una unidad con 2 RF objetivo tiene tope 6.
- `P6_MAX_CASES_ABSOLUTE` (int, default `50`): tope absoluto independiente del
  número de RF. Evita que unidades con muchos RF produzcan cientos de casos.

El tope efectivo es `min(multiplier × rf_count, absolute)`. Se comunica al LLM
en el prompt como instrucción explícita. Si el LLM devuelve más casos de los
permitidos, P6 los trunca antes de validar con `P6LlmResponse` y emite el aviso
`CASES_TRUNCATED`.

### D-F7-5 — Reintentos propios de P6 (`P6_MAX_RETRIES`)

P6 tiene su propia variable `P6_MAX_RETRIES` (int, default `1`) independiente de
`P2_MAX_RETRIES`. Mismo comportamiento que P2: reintenta el lote si el LLM devuelve
JSON inválido o falla transitoriamente. No reintenta `LLM_CONTEXT_LENGTH`.

### D-F7-6 — Numeración global de CP (`CP-xxx`)

Los códigos `CP-xxx` son globales y consecutivos en el orden de las unidades,
no por unidad. La numeración empieza en `CP-001` y continúa a través de todas
las unidades exitosas. Las unidades fallidas no consumen códigos.

Esto ya está en el contrato (`P6Output._consistent` lo valida). P6 debe mantener
un contador global que avanza al persistir cada unidad exitosa.

### D-F7-7 — Persistencia por unidad, códigos al final

P6 acumula los `P6UnitOutput` en memoria durante el procesamiento. Solo llama a
`persist_p6_unit` **al final**, una vez que todas las unidades han sido procesadas
(exitosas o fallidas). Esto simplifica la numeración global de CP y evita
persistir parcialmente en caso de que el pipeline se interrumpa a mitad de P6.

Consecuencia: si el proceso se reinicia durante P6, ninguna unidad queda a medias
en la BD. La generación queda `failed` por la recuperación de arranque y se puede
reintentar completa.

### D-F7-8 — Summary de la generación

El campo `summary` de `Generation` (hoy `null`) se puebla cuando P6 completa.
Contiene conteos objetivos del estado de la generación:

```json
"summary": {
  "user_stories_count": 2,
  "requirements_count": 12,
  "clusters_count": 3,
  "test_cases_count": 18,
  "test_cases_failed_units": 1
}
```

- `user_stories_count`: filas en `user_stories` para esta generación.
- `requirements_count`: filas en `functional_requirements`.
- `clusters_count`: filas en `clusters` (0 si `by_user_story`).
- `test_cases_count`: filas en `test_cases`.
- `test_cases_failed_units`: unidades de P6 que fallaron (de `P6Output.failed_units`).

El summary lo escribe `PipelineRunService` al recibir el evento `pipeline_completed`,
leyendo los conteos desde el repositorio.

### D-F7-9 — Propósito experimental de las dos variantes de prompt

Los dos prompts de P6 (`contexto.md` y `contexto_sin_clustering.md`) no son solo
adaptaciones técnicas: son la base del experimento de comparación entre:

- **Baseline** (`by_user_story`, sin clustering): cada unidad es una HU con sus RF.
  Sin RF de contexto. Prompt `contexto_sin_clustering.md`.
- **Propuesta** (`by_cluster`, con clustering semántico): cada unidad es un cluster
  de RF semánticamente relacionados, con RF de contexto de clusters vecinos.
  Prompt `contexto.md`.

Para que el experimento sea válido, los dos prompts deben ser **estructuralmente
equivalentes** — las mismas instrucciones base, solo diferenciadas en cómo
presentan la unidad al LLM. Revisar en T-F7-06 que no haya instrucciones que
favorezcan una variante sobre la otra.

Los resultados de ambas variantes se comparan en la fase de calibración
(ver `docs/calibracion_resultados/`): mismos documentos, mismos RF, diferente
organización de unidades. La métrica de comparación la definirá P7 (Fase 8).

---

## Revisión de prompts (T-F7-06)

Antes de implementar P6, leer `contexto.md` y `contexto_sin_clustering.md` y
verificar:

- [ ] Las instrucciones base son equivalentes en ambos prompts (mismo nivel de
      detalle, mismas restricciones de grounding).
- [ ] `contexto.md` explica claramente la diferencia entre RF objetivo y RF de
      contexto, y prohíbe enlazar RF de contexto en `requirement_codes`.
- [ ] `contexto_sin_clustering.md` no menciona clustering ni clusters (el LLM
      no debe saber que existe la otra variante).
- [ ] Ambos prompts instruyen al LLM sobre el máximo de casos (`P6_MAX_CASES_MULTIPLIER`
      y `P6_MAX_CASES_ABSOLUTE`) — esto requiere que el tope se inyecte dinámicamente
      en el texto del prompt en tiempo de ejecución, no hardcodeado.
- [ ] Ambos prompts tienen el mismo formato de salida y referencian el mismo
      `TestCaseOutputSpec`.

Si se modifica un prompt, actualizar `P6_PROMPT_VERSION` en `.env` y `.env.example`.

---

## Trabajo a realizar — tareas

### T-F7-01 · Corregir contrato `P6Output` y `P6Config`

En `ai_service/pipeline/contracts/p6.py`:

1. `P6Output.failed_units`: eliminar `max_length=1`.
2. `P6Config.on_unit_failure`: cambiar a `Literal["continue"]`.
3. Actualizar el validador `_consistent` de `P6Output` si es necesario.
4. Actualizar los tests de contrato que fallen por estos cambios.

### T-F7-02 · Variables de entorno y configuración

Añadir a `ai_service/config.py`:

```python
p6_prompt_version: str = Field(default="v1", min_length=1)
p6_max_retries: int = Field(default=1, ge=0)
p6_failure_threshold: float = Field(default=0.0, ge=0.0, le=1.0)
p6_max_cases_multiplier: int = Field(default=3, gt=0)
p6_max_cases_absolute: int = Field(default=50, gt=0)
```

Actualizar `.env` y `.env.example` con los cinco valores y comentarios explicativos.

Añadir `build_p6_config(settings) -> P6Config` en `pipeline/stages/__init__.py`.

### T-F7-03 · Implementar `GenerationStage.run()` (P6)

Pasos de la implementación:

1. **Leer el contexto.** `context.p5_output` — si es `None`, `RuntimeError`
   (invariante del orquestador).

2. **Resolver el prompt.** `resolve_p6_prompt(config.prompt_version, context.strategy)`
   donde `context.strategy = context.p5_output.context.strategy`.

3. **Procesar unidades.** Para cada `ContextUnit` en `context.p5_output.context.units`:
   - Calcular el tope de casos: `min(multiplier × len(unit.requirements), absolute)`.
   - Construir el mensaje al LLM (ver §Construcción del mensaje).
   - Llamar al LLM con reintentos (`P6_MAX_RETRIES`).
   - Si el LLM devuelve más casos del tope, truncar y emitir aviso `CASES_TRUNCATED`.
   - Validar con `P6LlmResponse(context={"target_codes": {r.code for r in unit.requirements}})`.
   - Si falla tras agotar reintentos, registrar `UnitFailure` y continuar con la siguiente.

4. **Numerar CP.** Asignar códigos `CP-001`, `CP-002`, … globalmente en orden de
   unidades exitosas. No consumir códigos para unidades fallidas.

5. **Evaluar umbral.** Si `len(failed) / len(units) > threshold` → `skip_remaining=True`
   con error `GENERATION_THRESHOLD_EXCEEDED`. Si no, continuar.

6. **Persistir.** Llamar a `persist_p6_unit` por cada unidad exitosa. Si falla la
   persistencia de una unidad, tratarla como `UnitFailure` (no como fallo global).

7. **Construir `P6Output`** y escribir `context.p6_output`.

8. **Devolver `StageResult`** con:
   - `warnings`: avisos por unidades fallidas y por casos truncados.
   - `runtime_info`: estrategia, unidades procesadas, unidades fallidas, casos
     generados, versión de prompt usada, modelo.

#### Construcción del mensaje al LLM

El mensaje `user` incluye:
- El tope de casos para esta unidad (instrucción explícita).
- Los RF objetivo con su `description`.
- Los RF de contexto con su `description` (solo en `by_cluster`).
- Las HU con `original_text` y secciones.
- El JSON Schema de `TestCaseOutputSpec` (ya incluido en `GenerationContext.output_spec`).

No hardcodear el tope en el prompt base — inyectarlo dinámicamente al construir
el mensaje por unidad.

### T-F7-04 · Caller `persist_p6_unit`

En `repositories/pipeline_results.py` (puerto):
```python
async def persist_p6_unit(self, generation_id: UUID, payload: dict) -> None: ...
```

En `repositories/supabase_pipeline_results.py` (adaptador Supabase):
- Llama a la RPC `persist_p6_unit` con `asyncio.to_thread`.
- Traduce errcodes: `23502` → `MissingIdentifierError`, `23503` →
  `InvalidReferenceError`, `23505` → `DuplicateEntryError`, resto → `PersistenceError`.

En `repositories/in_memory.py` (fake):
- Almacena los casos en `InMemoryStore.test_cases`.
- Replica idempotencia por `(generation_id, code)`.
- Valida FK: los `requirement_codes` deben existir en `functional_requirements`.

### T-F7-05 · Poblar `summary` en la API

`summary` se puebla cuando `pipeline_completed` se emite en `PipelineRunService`.
En ese momento, leer desde el repositorio:

```python
summary = await generations_repo.build_summary(generation_id)
await generations_repo.update_summary(generation_id, summary)
```

`build_summary` hace las consultas de conteo (HU, RF, clusters, casos) y toma
`test_cases_failed_units` de `P6Output.failed_units` que viaja en el contexto.

Actualizar `GenerationSummary` en `schemas/generations.py` con los 5 campos de D-F7-8.

### T-F7-06 · Revisar y ajustar prompts

Leer `contexto.md` y `contexto_sin_clustering.md` con la checklist de §Revisión de prompts.
Si se modifica alguno, registrar el cambio en el cierre documental y actualizar
`P6_PROMPT_VERSION`.

### T-F7-07 · Pruebas

Crear `tests/test_p6_generation.py` con los siguientes casos:

**Camino feliz `by_cluster`:**
- 2 unidades, LLM devuelve casos válidos → `P6Output` con CP-001… consecutivos,
  casos persistidos, `failed_units` vacío.
- RF de contexto no aparecen en `requirement_codes` de ningún caso.

**Camino feliz `by_user_story`:**
- 2 unidades sin RF de contexto → misma verificación de CP consecutivos.

**Fallo de unidad:**
- LLM falla en la segunda de 3 unidades → primera y tercera tienen casos,
  segunda en `failed_units`.
- Con `P6_FAILURE_THRESHOLD=0.0` → generación `failed`.
- Con `P6_FAILURE_THRESHOLD=0.5` → generación `completed` con aviso.

**Truncado de casos:**
- LLM devuelve más casos del tope → se truncan, aviso `CASES_TRUNCATED`.

**Reintentos:**
- LLM devuelve JSON inválido en el primer intento, válido en el segundo →
  `P6UnitOutput` correcto, aviso `BATCH_RETRIED`.

**Numeración global:**
- 3 unidades, la segunda falla → CP-001…N (primera), segunda sin CPs, CP-N+1…M (tercera).
  Los números son consecutivos sin saltos.

**Guardias:**
- `p5_output is None` → `RuntimeError`.
- 0 unidades en el contexto → `P6Output` vacío, `skip_remaining=False`.

**Wiring E2E (`test_stages_wiring.py`):**
- Pipeline completo P1→P6 con LLM fake que devuelve casos válidos.
- Con clustering → `by_cluster`, casos generados, summary poblado.
- Sin clustering → `by_user_story`, misma verificación.
- P6 con todas las unidades fallidas y threshold=0.0 → generación `failed`.

**Summary:**
- `GET /api/v1/generations/{id}` devuelve `summary` con los 5 campos poblados
  tras completar P6.

### T-F7-08 · Actualizar roadmap y cierre documental

- Marcar Fase 7 como ✅ en `docs/pipeline_roadmap.md`.
- Actualizar `PENDING_STUB_STAGE_CLASSES` para que solo liste P7.
- Actualizar comentario de `pipeline_stages` en `.env.example` (P1–P6 reales).
- Generar `cierre_documental_fase7.md`.
- Crear primera entrada en `docs/calibracion_resultados/` con el documento de
  prueba usado para verificar el pipeline completo.

---

## Orden de ejecución sugerido

```
T-F7-01 (corregir contrato P6Output/P6Config)
   │
T-F7-02 (variables de entorno P6_*)
   │
T-F7-06 (revisar prompts — antes de implementar la etapa)
   │
T-F7-03 (GenerationStage.run())
   │
T-F7-04 (caller persist_p6_unit)
   │
T-F7-05 (summary en la API)
   │
T-F7-07 (pruebas)
   │
T-F7-08 (roadmap + cierre documental + primera iteración de calibración)
```

---

## Criterios de cierre

La Fase 7 está completa cuando **todos** estos puntos se cumplen:

- [ ] `GenerationStage` no hereda de `StubStage` (lógica real implementada).
- [ ] Con clustering activo, genera casos para cada unidad `by_cluster`.
- [ ] Sin clustering, genera casos para cada unidad `by_user_story`.
- [ ] Unidades fallidas se registran en `P6Output.failed_units` sin detener el resto.
- [ ] `P6_FAILURE_THRESHOLD` controla si la generación queda `failed` o `completed`.
- [ ] Los códigos `CP-xxx` son globales y consecutivos sin saltos.
- [ ] `persist_p6_unit` se llama al final, una vez por unidad exitosa.
- [ ] `summary` en la API tiene los 5 campos poblados tras completar P6.
- [ ] Los prompts de ambas variantes son estructuralmente equivalentes (D-F7-9).
- [ ] `config.py` expone las 5 variables nuevas de P6.
- [ ] Pruebas de P6 pasan; wiring E2E actualizado; suite completa sin regresión.
- [ ] `pipeline_roadmap.md` actualizado y `cierre_documental_fase7.md` generado.
- [ ] Primera iteración de calibración documentada en `docs/calibracion_resultados/`.

---

## Reglas del pipeline que aplican a esta fase (referencia rápida)

| Regla | Cómo aplica en Fase 7 |
|---|---|
| D-15 (revisado, D-F7-1) | P6 procesa todas las unidades; el umbral decide si la generación falla |
| D-38 | P6 selecciona variante de prompt según `UnitStrategy` |
| D-12 | P5 no persiste; P6 lee `context.p5_output` directamente |
| R-PP-3 | P6 escribe `context.p6_output`; el summary lo lee `PipelineRunService` |
| R-PP-4 | `StageResult` lleva `warnings` y `runtime_info`; los casos viajan en `PipelineContext` |
| R-DI-2 | `GenerationStage` recibe `LlmClient`, resolvedor de prompt, repositorio y `P6Config` por constructor |
| R-CP-4 | `P6LlmResponse` se valida con `model_validate_json()` antes de procesar |
| R-CP-5 | `P6UnitOutput.to_rpc_payload()` construye el payload para `persist_p6_unit` |

---

## Advertencias heredadas relevantes

1. **RF no funcionales en P6** (ver `issue_resolver_p2_nfr.md`): hasta que se
   implemente el filtro `is_functional`, algunas unidades pueden contener RF no
   funcionales (restricciones técnicas, rendimiento). P6 generará casos para ellos
   igualmente. Esto distorsiona la comparación de calibración.
   **Recomendación:** implementar `issue_resolver_p2_nfr.md` antes de la primera
   iteración de calibración.

2. **RF sin cluster** (`UNASSIGNED_REQUIREMENTS`): con documentos pequeños, P4
   deja muchos RF sin asignar. Esos RF no llegan a P6 (D-32 / D-36). Verificar
   en calibración que el número de RF sin casos es aceptable.

3. **Calibración de `P5_MAX_TOKENS_PER_UNIT`**: esta fase es el primer momento
   en que se puede calibrar ese valor. Ver `docs/calibracion_variables.md`.

4. **Nombres de cluster placeholder** (`"Cluster 0"`, `"Cluster 1"`…): el LLM de
   P6 recibe esos nombres en el prompt `by_cluster`. No afecta a la calidad de
   los casos pero puede confundir al leer los resultados.

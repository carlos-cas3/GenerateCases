# Fase 8 — Pruebas de integración contra Supabase real (capa de persistencia)

> **Estado:** 🔲 pendiente de implementar. Este archivo es el **plan** de la primera workstream
> de la Fase 8: una capa de pruebas de integración que ejecuta las RPC y la máquina de estados
> de generaciones contra Postgres real, aisladamente del LLM y del pipeline.
> **Fase anterior:** Fase 7 (P6 generación de casos) — ✅ cerrada (533 tests), salvo la primera
> iteración de calibración (`docs/calibracion_resultados/iteracion_1.md`).
> **Documentos fuente:**
> `docs/pipeline_roadmap.md` (advertencias 7 y 10; pendiente «pruebas de integración E2E con
> Supabase real»),
> `supabase/schema.sql` (RPC, constraints, máquina de estados),
> `ai_service/repositories/supabase_pipeline_results.py` (`_ERRORS_BY_SQLSTATE`),
> `ai_service/repositories/supabase_generations.py` (transiciones de estado),
> `tests/test_contracts_rpc.py` (validación estática de payloads, hoy sin ejecutar),
> `scripts/inspect_generation.py` (patrón de consulta reusable).
>
> **Alcance de este documento:** solo la **capa de integración contra Supabase** (lo que el
> roadmap llama «pruebas de integración»). Quedan **fuera** de este archivo: el E2E del pipeline
> con Ollama real, las pruebas de comportamiento del LLM y el diseño/implementación de P7
> (evaluación), que también forman parte de la Fase 8 según el roadmap pero se planificarán por
> separado. El detalle de lo implementado quedará en `cierre_documental_fase8.md` al cerrar.

---

## Objetivo de la fase

Tener una capa de pruebas que verifique la **frontera de persistencia** —RPC de `persist_pN_*`,
constraints de `schema.sql`, transiciones de estado de `generations`/`generation_stages`,
escritura de `summary` y `delete_generation_if_final`— ejecutándose contra Postgres real, de
forma rápida, determinista y aislada del LLM y del orquestador.

```
Test de integración  →  cliente Supabase real  →  RPC / tablas / constraints
                     (sin LLM, sin pipeline, sin API)
```

Al cerrar, las advertencias 7 y 10 del roadmap quedan resueltas y existe la base confirmada
sobre la que montar después el E2E de Fase 8 (que solo tendrá que preocuparse del pipeline y
el LLM, no de si la persistencia falló).

### Por qué esta capa y no solo E2E

El E2E del pipeline (POST /generations → P1…P6 → filas) ejercita el **camino feliz** de la
persistencia, pero el pipeline **nunca manda datos malos** a las RPC (los contratos validan
antes: P6 chequea `target_codes`, P2 no produce duplicados, etc.). Los caminos de error de la
persistencia —FK, NOT NULL, unique, guardas de estado— solo los dispara una llamada directa
con datos malos. Además el E2E es lento (Ollama real, minutos) y da una señal gruesa; esta capa
es rápida (segundos), determinista y, al fallar, apunta directo a la RPC/schema.

---

## Estado del código relevante al empezar

### Lo que ya existe y no se toca

| Artefacto | Archivo | Observación |
|---|---|---|
| 533 pruebas unitarias, todas contra fakes | `tests/` | `conftest.py` monta la app «sin Supabase»; suite rápida |
| Validación estática de payloads RPC | `tests/test_contracts_rpc.py` | Parsea `schema.sql` con regex; **no ejecuta** contra Postgres |
| RPC + constraints + máquina de estados | `supabase/schema.sql` | Desplegado 2026-11-11; idempotente por `(generation_id, code)` |
| Adaptadores Supabase | `repositories/supabase_*.py` | `SupabasePipelineResultsRepository._ERRORS_BY_SQLSTATE` (23503/23502/23505) |
| Transiciones de estado | `repositories/supabase_generations.py` | `update_generation_status`/`update_stage` con `expected`; `delete_generation_if_final` |
| `pytest.ini` | raíz | `asyncio_mode=auto`; **sin markers**, sin gating |

### Lo que se va a crear o modificar

| Artefacto | Archivo | Acción |
|---|---|---|
| Marcadores y gating | `pytest.ini` | Añadir `markers` y `addopts` para excluir por defecto (T-F8-01) |
| Fixture de cliente Supabase real | `tests/conftest_integration.py` (nuevo) | Cliente real + skip si faltan credenciales (T-F8-01) |
| Tests de integración | `tests/integration/test_persist_rpc.py` (nuevo) | Happy path + error de las cuatro RPC (T-F8-02, T-F8-03) |
| Tests de máquina de estados | `tests/integration/test_generation_lifecycle.py` (nuevo) | Creación, transiciones, `summary`, borrado (T-F8-04 a T-F8-06) |
| Roadmap + cierre | `docs/pipeline_roadmap.md`, `cierre_documental_fase8.md` | Resolver advertencias 7 y 10; marcar progreso (T-F8-07) |

---

## Decisiones de la fase

### D-F8-1 — Alcance: solo persistencia, sin LLM ni pipeline

Esta capa prueba las RPC y la máquina de estados llamándolas directamente (con el cliente
Supabase real), sin arrancar la app ni invocar al LLM. El E2E y las pruebas de comportamiento
del LLM se planifican aparte dentro de la Fase 8.

### D-F8-2 — Gating por marcador + variable de entorno

La suite por defecto (`pytest`) no debe tocar servicios externos: sigue siendo los 533 tests
rápidos contra fakes. Las pruebas de integración se marcan `integration` y se excluyen por
defecto con `addopts`. Se ejecutan con:

```bash
RUN_SUPABASE_TESTS=1 pytest -m integration
# o, sin tocar el addopts por defecto:
pytest -m integration --override-ini="addopts="
```

Si `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` no están presentes, los tests se **saltan**
(`pytest.skip`), no fallan. Así el CI sin credenciales sigue verde.

### D-F8-3 — Aislamiento y seguridad de datos

El `.env` apunta al proyecto Supabase **real**, que contiene generaciones propias (p. ej.
`caa5f52c-…`). Probar ahí arriesga a contaminar o mutar datos. Dos opciones, en orden de
preferencia:

1. **Proyecto Supabase aparte para tests** (recomendado). Variables `SUPABASE_URL_TEST` /
   `SUPABASE_SERVICE_ROLE_KEY_TEST`; el fixture las prefiere. Esquema limpio, sin datos.
2. **Si no hay proyecto aparte**: aislamiento estricto en el real:
   - Cada test crea su propia `generation_id` (aleatoria) y la borra al final.
   - Nunca se asume nada sobre filas existentes; solo se leen/escriben filas propias.
   - Limpieza vía `delete_generation_if_final` (cascade) en un `fixture` con scope de función,
     incluso si el test falla (usar `try/finally` o `addfinalizer`).

Sin una de estas dos, **no** se ejecutan los tests contra el proyecto real.

### D-F8-4 — Qué se prueba y qué no

**Sí:** que cada RPC persiste filas correctas dados payloads válidos; que los constraints
rechazan payloads inválidos con el `sqlstate` esperado; que las transiciones de estado
exigen el `expected`; que `summary` se escribe y se lee; que la idempotencia hace `ON
CONFLICT DO UPDATE`; que `delete_generation_if_final` rechaza generaciones `in_progress`.

**No:** la lógica del pipeline, el LLM, el formato del JSON del LLM, ni la prosa de los casos.
Eso pertenece a los unitarios (ya cubiertos) o al E2E (Fase 8, aparte).

### D-F8-5 — Traducción de errcodes verificada, no asumida

El adaptador `SupabasePipelineResultsRepository` mapea `23503 → InvalidReferenceError`,
`23502 → MissingIdentifierError`, `23505 → DuplicateEntryError`. Los tests de integración
verifican que la RPC **realmente** lanza ese `sqlstate` para cada caso (no que el mapeo de
Python sea correcto —eso ya lo cubren los unitarios—). Así se detecta si un constraint falta
en el schema desplegado.

### D-F8-6 — Factories reutilizadas, no inventadas

Los payloads válidos se construyen con `tests/contract_factories.py` y los `to_rpc_payload()`
de los contratos (los mismos que ya usan `test_contracts_rpc.py`). No se duplican factories:
si un payload cambia, el test de integración y el estático se enteran a la vez.

---

## Trabajo a realizar — tareas

### T-F8-01 · Infraestructura: markers, gating y fixture

En `pytest.ini`:

```ini
markers =
    integration: pruebas que golpean Supabase real (gated)
    e2e: pipeline completo con backends reales (gated, Fase 8)
    llm: comportamiento del LLM real (gated, Fase 8)
addopts = -m "not integration and not e2e and not llm"
```

Crear `tests/conftest_integration.py` con:

- `supabase_client`: fixture que construye el cliente con `SUPABASE_URL_TEST` /
  `SUPABASE_SERVICE_ROLE_KEY_TEST` (o las de `.env` si no existen, ver D-F8-3 opción 2) y
  `pytest.skip` si faltan credenciales o `RUN_SUPABASE_TESTS` no está activo.
- `generation_factory`: crea una generación efímera vía `create_generation` y registra su
  borrado final con `delete_generation_if_final` (cascade), garantizado en `try/finally`.

Registrar `conftest_integration.py` para que se cargue solo bajo `tests/integration/` (carpeta
propia) y no afecte al path de la suite rápida.

### T-F8-02 · Happy path de las cuatro RPC

`tests/integration/test_persist_rpc.py` — un test por RPC con payload válido (de
`contract_factories` + `to_rpc_payload`):

- `persist_p1_user_stories`: las HU quedan con `code`/`position`/`objective`/`goal` correctos.
- `persist_p2_requirements`: RF con `code`/`description`/`source_text`/`user_story_codes` y sus
  `classifications`; re-leer y comparar.
- `persist_p4_clusters`: clusters y `assignments` con `similarity_to_centroid`; los RF
  `unassigned` quedan marcados.
- `persist_p6_unit`: casos con `code` (`CP-xxx`), `title`, `objective`, `preconditions`,
  `test_data`, `expected_result`, `steps`; y los vínculos en `requirement_test_cases` con los
  `requirement_codes` indicados.

Cada test relee las filas por `generation_id` y compara contra el payload enviado.

### T-F8-03 · Caminos de error y constraints

Mismas RPC, payloads inválidos craftados (no producidos por el pipeline):

- **FK (23503)**: `persist_p6_unit` con un `requirement_codes` que referencia un RF inexistente
  en la generación → `InvalidReferenceError` (sqlstate `23503`).
- **NOT NULL (23502)**: un caso de `persist_p6_unit` sin `id` → `MissingIdentifierError`.
- **Unique / T-02 (23505)**: `persist_p2_requirements` con una HU duplicada en el payload →
  `DuplicateEntryError` detectado **antes** del UPDATE que cuenta filas (verifica el orden
  que ya comprueba estáticamente `test_persist_p2_rejects_duplicate_stories_before_update`).
- **Idempotencia**: re-ejecutar `persist_p1_user_stories` con los mismos `code` no duplica
  filas (hace `ON CONFLICT (generation_id, code) DO UPDATE`).

### T-F8-04 · Máquina de estados: transiciones

`tests/integration/test_generation_lifecycle.py`:

- `create_generation` devuelve un UUID y deja la generación en `queued` con 7 etapas `pending`.
- `update_generation_status(expected=[queued], status=running)` pasa a `running`.
- Transición ilegal (p. ej. `expected=[running]` cuando ya está `completed`) →
  `InvalidStateTransition` (el UPDATE afecta 0 filas).
- `update_stage` exige `expected` por `stage_key`; transición ilegal → `InvalidStateTransition`.

### T-F8-05 · `summary` y lectura por la API de repositorio

- `update_summary` escribe los 5 conteos; `build_summary` los recalcula desde las tablas y
  coincide con lo escrito.
- `get_by_id` devuelve el `GenerationRecord` con `summary`, `stages` ordenadas y
  `document_name` (join `documents`).

### T-F8-06 · `delete_generation_if_final`

- Generación `completed` → `delete_generation_if_final` borra en cascade (HU, RF, clusters,
  casos, etapas).
- Generación `running`/`queued` → devuelve `in_progress` y **no** borra.

### T-F8-07 · Cierre

- En `docs/pipeline_roadmap.md`: marcar como resueltas las advertencias 7 y 10; desmarcar el
  pendiente «pruebas de integración … con Supabase real» (o dejarlo parcial si el E2E queda
  para después).
- Generar `cierre_documental_fase8.md` con lo implementado y los hallazgos (p. ej. constraints
  que faltaban, si los hubiera).

---

## Orden de ejecución sugerido

```
T-F8-01 (infra: markers, gating, fixture real + skip)
   │
T-F8-02 (happy path de las 4 RPC)
   │
T-F8-03 (caminos de error + constraints + idempotencia)
   │
T-F8-04 (máquina de estados: transiciones)
   │
T-F8-05 (summary + get_by_id)
   │
T-F8-06 (delete_generation_if_final)
   │
T-F8-07 (roadmap + cierre documental)
```

---

## Criterios de cierre

La capa de integración está completa cuando **todos** estos puntos se cumplen:

- [ ] `pytest` (sin flags) sigue siendo la suite rápida de 533 tests; no toca Supabase.
- [ ] `RUN_SUPABASE_TESTS=1 pytest -m integration` ejecuta la capa nueva y pasa.
- [ ] Sin credenciales o sin la variable, los tests se `skip` (no fallan).
- [ ] Las cuatro RPC tienen happy-path que relee y compara filas.
- [ ] FK / NOT NULL / unique-T-02 se rechazan con el `sqlstate` esperado.
- [ ] Idempotencia de `persist_p1_user_stories` verificada (no duplica al re-ejecutar).
- [ ] Transiciones de estado exigen `expected`; las ilegales dan `InvalidStateTransition`.
- [ ] `summary` se escribe y `build_summary` coincide; `get_by_id` lo devuelve.
- [ ] `delete_generation_if_final` borra en cascade solo si la generación es final.
- [ ] Aislamiento cumplido (proyecto aparte, o `generation_id` propios + borrado garantizado).
- [ ] Advertencias 7 y 10 del roadmap resueltas; `cierre_documental_fase8.md` generado.

---

## Advertencias heredadas relevantes

1. **Advertencia 7 (roadmap):** «Sin prueba de `persist_p4_clusters` contra Postgres real» —
   la cierra T-F8-02.
2. **Advertencia 10 (roadmap):** «Sin prueba de `persist_p6_unit` ni de `summary` contra
   Postgres real» — la cierran T-F8-02 y T-F8-05.
3. **`schema.sql` desincronizado:** `test_contracts_rpc.py` valida el archivo local, no el
   desplegado. Si al correr T-F8-02 una RPC falla por una columna que no existe, el schema
   desplegado está viejo: redesplegar antes de seguir (precedente: «schema.sql sin desplegar»).
4. **Datos reales en el proyecto del `.env`:** ver D-F8-3. No ejecutar la capa contra el
   proyecto real sin una de las dos opciones de aislamiento.

---

## Próximos pasos (fuera de este documento)

- **E2E del pipeline** (`-m e2e`): POST /generations con documento pequeño + Ollama real +
  Supabase real, en `by_user_story` y `by_cluster`. Requiere esta capa confirmada primero.
- **Comportamiento del LLM** (`-m llm`): P2/P6 contra Ollama real (JSON válido, `target_codes`,
  `LLM_CONTEXT_LENGTH`, timeout). Captura model drift.
- **P7 (evaluación):** sin contrato todavía; se diseña al inicio de su workstream dentro de
  Fase 8.
- **`stop_after` (calibración):** parada limpia tras la etapa N (prefijo P1…N) para calibrar
  P1–P5 sin pagar el LLM de P6. Capacidad del orquestador, no de la capa de integración — ver
  [`calibracion_stop.md`](calibracion_stop.md).

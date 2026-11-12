# Cierre documental — Fase 4 (P1 heurística + P2 LLM)

> **Estado:** ✅ implementación cerrada en código y pruebas. **`schema.sql` desplegado en
> Supabase (2026-11-11):** las RPCs `persist_p1_user_stories`, `persist_p2_requirements`,
> `persist_p4_clusters` y `persist_p6_unit` existen y son idempotentes.
> **Alcance:** T-F4-04 … T-F4-09 + callers (§2 de `guia_implementacion.md`). La base de §1
> (config, schema, prompts, openapi) se verificó antes de continuar (ver §1).
> **Prueba local (Ollama):** configuración de `.env` y evidencia en
> [`prueba_local_ollama.md`](prueba_local_ollama.md).

---

## 1. Verificación de lo ya aplicado (§1.1 de la guía)

| Comprobación | Resultado |
|---|---|
| `Settings()` importa y `p1_story_delimiter_pattern` compila | ✅ (`v1`, `es`, 5000, `v1`, 5, 2; `llm_model=None`) |
| `resolve_p2_prompt("v1")` carga el texto | ✅ 4688 caracteres |
| `schema.sql`: funciones / pares `$$` / `begin`–`end;` | ✅ 6 / 6 / 6–6 |
| `schema.sql`: cláusulas `on conflict` | ✅ 10 (8 idempotencia P2/P4/P6 + 1 `persist_p1` + 1 bucket) |
| T-02: chequeo de duplicados antes del `UPDATE`, errcode `23505` | ✅ (ahora cubierto por test) |
| `.env.example` con `LLM_MODEL` vacío y variables P1/P2 | ✅ |
| Nota de orden `position`/`code` en `openapi.yaml` (T-04) | ✅ |
| `pytest tests/test_contracts.py tests/test_contracts_rpc.py` | ✅ 180 pasan (antes de los cambios) |

---

## 2. Qué se implementó

| Tarea | Archivos | Resumen |
|---|---|---|
| Callers RPC (T-F4-07, T-F4-10) | `repositories/pipeline_results.py` (puerto), `repositories/supabase_pipeline_results.py` (adaptador), `repositories/in_memory.py` (`InMemoryPipelineResultsRepository`) | `persist_p1_user_stories` y `persist_p2_requirements` con `asyncio.to_thread`; errcodes `23503` → `InvalidReferenceError` (`INVALID_STORY_REFERENCE`), `23502` → `MissingIdentifierError`, `23505` → `DuplicateEntryError`, resto → `PersistenceError` (`PERSISTENCE_FAILED`). El fake replica idempotencia, T-02 y FK. |
| Payload P1 | `contracts/p1.py` (`P1Output.to_rpc_payload()`) | Análogo a `P2Output.to_rpc_payload()`. `objective`→`action`, `benefit`→`goal` (D-02). Solo HU (D-22). |
| DI (T-F4-04) | `pipeline/stages/__init__.py` (`build_real_stages`, `build_p1_config`, `build_p2_config`), `main.py`, `config.py` (`PIPELINE_STAGES`) | P1 recibe `DocumentsRepository` + `DocumentStorage` + `DocumentTextExtractor` + `PipelineResultsRepository` + `P1Config` (**sin `LlmClient`**). P2 recibe `LlmClient` + `resolve_p2_prompt` + repositorio + `P2Config`. P3–P7 siguen stubs. Sin `LLM_MODEL` → `ConfigurationError` al arrancar. |
| P1 (T-F4-05) | `pipeline/stages/p1_normalize.py` | Heurística de `plantilla_hu.md`. Ya no hereda de `StubStage` (`NormalizeStubStage` conserva el stub). |
| P2 (T-F4-06) | `pipeline/stages/p2_requirements.py` | Lotes de `max_stories_per_call`, reintentos hasta `max_retries`, consolidación `RF-xxx`, D-29. `RequirementsStubStage` conserva el stub. |
| Pruebas (T-F4-08) | `tests/test_p1_normalize.py` (13), `tests/test_p2_requirements.py` (13), `tests/test_stages_wiring.py` (7), `tests/test_contracts_rpc.py` (+4) | Ver §5. |

---

## 3. Decisiones y supuestos tomados en la implementación

1. **Modo de etapas `PIPELINE_STAGES=real|stub`** (default `real`). `build_stub_stages` sigue
   disponible para arrancar sin LLM ni RPC de resultados y para los tests del orquestador/API
   (`tests/conftest.py::make_settings` usa `stub`). Con `real`, `PIPELINE_STUB_DELAY_SECONDS` y
   `PIPELINE_STUB_FAIL_AT_STAGE` solo afectan a P3–P7.
2. **Persistencia como repositorio (puerto + adaptador)**, no como métodos en
   `clients/supabase.py`: sigue el patrón de Fase 1 (`SupabaseGenerationsRepository`) y permite el
   fake en memoria (R-DI-3/R-DI-4).
3. **P1 necesita `DocumentsRepository`** además de lo que listaba la guía: el contexto solo trae
   `document_id`; `storage_path`, `filename` y `file_type` salen de `documents`.
4. **Regex de la declaración canónica**: la aprobada en `plantilla_hu.md` con un único ajuste,
   `\b` antes de `para`, para no partir palabras como "comparar"/"separar". Insensible a
   mayúsculas. La declaración es el **primer párrafo** tras el `##` (puede abarcar varias líneas,
   porque PDF/DOCX parten líneas largas) y termina en línea en blanco o en un `#`.
5. **`max_story_chars`**: superar el límite → `valid_with_warnings` con `STORY_TOO_LONG`, **sin
   truncar** (`pipeline_design.md`: superar el límite no autoriza a descartar contenido).
6. **`position`**: las HU usan su número de orden (1, 2, 3…, igual que `HU-xxx`); los
   `UnresolvedFragment` usan la posición del bloque en el documento (preámbulo incluido). Así
   `user_stories.position` queda consecutivo.
7. **`kind` de secciones**: título `###` normalizado (sin acentos, minúsculas, `_`) omitiendo
   palabras vacías (`de`, `la`, `y`…) → `criterios_aceptacion`, `reglas_negocio`,
   `restricciones`, como sugiere `plantilla_hu.md` §4. Cada sección lleva `source_span` relativo a
   `original_text`. Secciones vacías se omiten.
8. **Errores de P1**: documento inexistente / tipo no soportado / Storage o extractor fallan →
   `DOCUMENT_UNREADABLE`; texto vacío → `EMPTY_DOCUMENT`; ningún bloque encaja →
   `NO_STORIES_FOUND`. `STORY_SEGMENTATION_FAILED` solo si `P1Output` rechazara el resultado
   (no debería ocurrir).
9. **P2 — petición al LLM**: `system` = texto de `p2_requirements.md`; `prompt` = lote en JSON
   (`code`, `original_text`, `role`, `objective`, `benefit`, `content_sections`).
   `LlmSettings.parameters` (`max_tokens`, `temperature`, resto en `extra`) se trasladan a
   `LlmRequest`; hoy el wiring los deja vacíos. Se tolera un bloque ```` ```json ```` envolvente.
10. **P2 — reintentos**: por lote, hasta `1 + max_retries` intentos. Reintentan: salida inválida
    (Pydantic con `context={"user_story_codes": lote}`), `LlmRateLimitError`,
    `LlmInvalidResponseError` y `LlmError` genérico (con espera lineal `retry_delay_seconds *
    intento` solo para errores del proveedor). **No** reintenta `LlmContextLengthError`
    (`LLM_CONTEXT_LENGTH`). Agotados: `LLM_INVALID_OUTPUT` o `LLM_UNAVAILABLE` (`retryable=True`).
    Cada lote inválido emite `logger.debug(... raw=<2000 chars> err=...)` + un `warning` sin
    contenido.
11. **P2 — consolidación**: `RF-001…` consecutivos en orden de lote; `stories_without_requirements`
    calculado; `quality` y `findings` vacíos en v1. Un `LlmRun` por lote (tokens y latencia
    sumados entre intentos).
12. **D-29**: 0 RF → aviso `NO_REQUIREMENTS_EXTRACTED`, se persisten las clasificaciones y
    `skip_remaining=True`. Avisos adicionales: `BATCH_RETRIED`, `CANDIDATE_WITHOUT_REQUIREMENTS`.
13. **Fallos de persistencia** → `StageError(<código de dominio>, retryable=True)`; como las RPC
    son idempotentes (T-01), reintentar la generación es seguro.

### Supuestos de la Fase 3 revisados

- **Supuesto 3** (todas las HU `invalid` → P1 no puede devolver `P1Output`): **confirmado sin
  cambios en el contrato**. La heurística v1 nunca produce `invalid`: lo que no encaja va a
  `unresolved_fragments`; si no queda ninguna HU, `NO_STORIES_FOUND`.

---

## 4. Advertencias nuevas

1. **~~`schema.sql` sin desplegar~~ — RESUELTO (2026-11-11):** `schema.sql` desplegado en Supabase.
   Las RPCs `persist_p1_user_stories`, `persist_p2_requirements`, `persist_p4_clusters` y
   `persist_p6_unit` existen y son idempotentes. Con `PIPELINE_STAGES=real` P1 ya no falla con
   `PERSISTENCE_FAILED`.
2. **`LLM_MODEL` obligatoria en modo `real`**: un `.env` antiguo sin `LLM_MODEL` impide arrancar.
   Usar `PIPELINE_STAGES=stub` para desarrollo sin LLM.
3. **Ambigüedad de "para"**: la declaración se parte en la primera aparición de la palabra
   "para" (`… quiero un botón para exportar, para ahorrar tiempo` → objetivo "un botón"). Es una
   limitación de la regex aprobada; el texto completo sigue en `original_text` para P2.
4. **Sin prueba de RPC contra Postgres real**: T-02 y la idempotencia se validan con tests de
   estructura del SQL (`test_contracts_rpc.py`) y con el fake en memoria, que replica la semántica.
   La validación definitiva ocurre al desplegar o contra una BD de test.
5. **Una HU sin la declaración canónica se pierde para P2** (va a `unresolved_fragments`, que no
   se persiste, D-22). Coherente con el camino B; el aviso `UNRESOLVED_FRAGMENTS` de P1 indica
   las posiciones.

---

## 5. Pruebas

```
pytest tests/test_contracts.py tests/test_contracts_rpc.py tests/test_p1_normalize.py \
       tests/test_p2_requirements.py tests/test_stages_wiring.py   → 217 passed
pytest                                                              → 427 passed
```

- **P1** (extractor fake, sin LLM): happy path con las 3 secciones y spans literales,
  `MISSING_BENEFIT`, declaración multilínea, "comparar" ≠ "para", preámbulo y bloque sin plantilla
  → `UnresolvedFragment`, `STORY_TOO_LONG` sin truncar, CRLF, `EMPTY_DOCUMENT`,
  `NO_STORIES_FOUND`, `DOCUMENT_UNREADABLE` (extractor, Storage, registro), payload de
  `persist_p1_user_stories` e idempotencia.
- **P2** (LLM fake): lotes, consolidación `RF-xxx`, persistencia y D-27, reintento por salida
  inválida con `caplog` del `debug` crudo, `LLM_INVALID_OUTPUT` agotado, referencias fuera de lote,
  D-29, rate limit reintentado, context length sin reintento, `LLM_UNAVAILABLE`,
  `INVALID_STORY_REFERENCE`, T-02 e idempotencia de `persist_p2_requirements` (fake).
- **Wiring / extremo a extremo** (HTTP + fakes): `build_real_stages`, `LLM_MODEL` obligatoria,
  documento → HU + RF persistidos, D-29 (P3–P7 `skipped`, generación `completed`), fallo de P2.
- **RPC (`test_contracts_rpc.py`)**: columnas del payload P1 = columnas de la RPC, mapeo D-02,
  `ON CONFLICT (generation_id, code)` en P1 y orden del chequeo T-02.

---

## 6. Criterios de cierre (`fase4.md` §5)

- [x] `NormalizeStage` y `RequirementsStage` no heredan de `StubStage`.
- [x] Un documento produce HU y RF reales persistidos (verificado con fakes; `schema.sql` desplegado en Supabase).
- [x] T-01, T-02, T-04 registradas en `decisiones_schema.sql.md` y aplicadas en `schema.sql`.
- [x] Spec de plantilla (P1) y `prompts/p2.py` + texto (P2), cada uno usado por su etapa.
- [x] P1 no recibe `LlmClient`; marca las no identificadas como `UnresolvedFragment`.
- [x] Caller `persist_p2_requirements`.
- [x] RPC `persist_p1_user_stories` + caller; P1 persiste las HU.
- [x] `config.py` expone las variables de `P1Config`/`P2Config`.
- [x] Pruebas de P1 y P2 pasan; contratos sin regresión.
- [x] D-29: 0 RF → P3–P7 `skipped` y generación `completed`.
- [x] `pipeline_roadmap.md` actualizado y este cierre generado.

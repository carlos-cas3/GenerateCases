# Guía de implementación — Fase 4 (P1 y P2)

> **Guía de sugerencia. No es obligatorio.** Son sugerencias concretas de "cómo" implementar las
> tareas pendientes de la Fase 4 (T-F4-04 a T-F4-09 + callers). Si consideras correcto algo,
> impleméntalo; si no, se descarta. El responsable da directrices; esta guía es el detalle para
> quien codifique.
>
> **Esto es orientación, no código aplicado.** La base ya aplicada (config, schema, prompts) está
> listada en §1.

---

## 1. Base ya aplicada (no requiere acción, solo verificar al desplegar)

| Tarea | Qué | Archivos |
|---|---|---|
| T-F4-11 (Hueco B) | Variables de `P1Config`/`P2Config` + `LLM_MODEL` | `ai_service/config.py`, `.env.example` |
| T-F4-10 (Hueco A) | RPC `persist_p1_user_stories` (idempotente) | `supabase/schema.sql` |
| T-02 | Detección de `user_story_code` duplicados en `persist_p2_requirements` | `supabase/schema.sql` |
| T-04 | Nota de orden `position`/`code` | `docs/openapi.yaml` |
| T-F4-03 | Resolvedor `prompts/p2.py` + texto `texts/p2_requirements.md` | `ai_service/pipeline/prompts/` |
| T-01 | Idempotencia `ON CONFLICT` en P2/P4/P6 | `supabase/schema.sql` |

**Pendiente de despliegue:** volver a ejecutar `schema.sql` contra Supabase (aplica T-01, T-02 y
`persist_p1_user_stories`).

### 1.1 Cómo revisar lo aplicado (verificación)

Estado verificado al cerrar esta sesión: **6** funciones `create or replace`, **6** pares `$$`,
**10** cláusulas `on conflict` (8 de idempotencia en `persist_p2/p4/p6` + 1 en `persist_p1` + 1
pre-existente del storage bucket); `config.py` y `prompts/p2.py` importan; **180** tests de
contratos pasan.

Checklist para quien revise o continúe:

**`config.py` / `.env.example` (T-F4-11)**
- [ ] `python -c "from ai_service.config import Settings; import re; s=Settings(); re.compile(s.p1_story_delimiter_pattern); print('ok')"` → importa y la regex compila.
- [ ] `LLM_MODEL` está vacío en `.env.example`; el wiring de P2 debe validar que no sea `None` al construir `P2Config` (si falta → `ConfigurationError` al arrancar).
- [ ] Defaults coherentes con contrato/plantilla: `p1_rules_version=v1`, `p1_language=es`, `p1_max_story_chars=5000`, `p2_prompt_version=v1`, `p2_max_stories_per_call=5`, `p2_max_retries=2`.

**`schema.sql` (T-01, T-02, Hueco A)**
- [ ] Balance: 6 funciones, 6 pares `$$`, 6 `begin` / 6 `end;`.
- [ ] 10 `on conflict` (8 idempotencia P2/P4/P6 + 1 `persist_p1` + 1 storage bucket).
- [ ] T-02: el bloque de duplicados en `persist_p2_requirements` va **antes** del `UPDATE`. Test sugerido: payload con `user_story_code` repetido → errcode `23505`, mensaje *"la HU % aparece 2 o más veces en el payload"*.
- [ ] Hueco A: `persist_p1_user_stories` usa `ON CONFLICT (generation_id, code) DO UPDATE` (coincide con `user_stories_generation_code_uq`). Mapeo de columnas: `objective`→`action`, `benefit`→`goal` (D-02). Test sugerido: insertar HU y reinsertar el mismo payload → sin error, fila actualizada (idempotente).
- [ ] `revoke`/`grant` de `persist_p1_user_stories` presentes.
- [ ] **Sin una BD Postgres no se valida la sintaxis PL/pgSQL**; el balance + la revisión son el proxy local. La validación real ocurre al desplegar (`create or replace`) o contra una BD de test.

**`openapi.yaml` (T-04)**
- [ ] La nota de orden `position`/`code` no rompe el openapi — `test_contracts.py` valida los modelos contra el openapi y pasa (regresión verde = openapi válido).

**`prompts/p2.py` + `texts/p2_requirements.md` (T-F4-03)**
- [ ] `python -c "from ai_service.pipeline.prompts.p2 import resolve_p2_prompt; r=resolve_p2_prompt('v1'); assert r.text; print(len(r.text))"` → carga el texto (4688 chars).
- [ ] `texts/p2_requirements.md` coincide con el cuerpo aprobado en `prompt_p2.md` (sin el encabezado de propuesta).

**Regresión general**
- [ ] `pytest tests/test_contracts.py tests/test_contracts_rpc.py -q` → 180 pasan (verificado).

---

## 2. Pendiente de implementar (sugerencias)

### 2.1 Callers de las RPC (parte de T-F4-10 + T-F4-07)

Hoy `ai_service/clients/supabase.py` solo expone `create_supabase_client`. Sugerencia: añadir un
repositorio de persistencia (o métodos en el cliente) con dos funciones:

```
async def persist_p1_user_stories(self, generation_id, payload) -> None
async def persist_p2_requirements(self, generation_id, payload) -> None
```

- Ambas: `await asyncio.to_thread(self._client.rpc, "<rpc_name>", {"p_generation_id": str(generation_id), "p_payload": payload})`.
- Traducir errcodes SQL a dominio: `23503` → referencia rota (HU/RF inexistente), `23502` → id
  faltante, `23505` → duplicado (T-02). Reutilizar el patrón del repositorio de Fase 1.
- El payload de P1 lo construye la etapa mapeando `UserStory` → `{id, code, position,
  original_text, role, action, goal, validation_status}` (recordar: `objective`→`action`,
  `benefit`→`goal`, D-02). El de P2 sale de `P2Output.to_rpc_payload()`.

### 2.2 T-F4-04 · Cableado de dependencias (DI)

En `main.py`, reemplazar `build_stub_stages(...)` por una construcción real (manteniendo
`build_stub_stages` disponible para arranque sin credenciales / tests):

- `NormalizeStage(storage=app.state.storage, extractor=app.state.extractor, config=P1Config(...))`
  — **sin `LlmClient`** (camino B).
- `RequirementsStage(llm_client=app.state.llm_client, prompt_resolver=resolve_p2_prompt,
  persist=<caller p2>, config=P2Config(...))`.
- P3–P7 siguen como `StubStage` por ahora.

Construir `P1Config` y `P2Config` desde `Settings` (las variables nuevas de T-F4-11). `P2Config`
necesita `LlmSettings(provider=llm_provider, model=llm_model, parameters={})` — validar que
`llm_model` no sea `None` al construir (si falta, fallar al arrancar con `ConfigurationError`).

### 2.3 T-F4-05 · `NormalizeStage.run()` (P1 — heurística, sin LLM)

1. `storage.download(...)` → bytes → `extractor.extract(data, file_type)` → texto. Vacío →
   `StageError(code="EMPTY_DOCUMENT")`. Error de storage/extractor →
   `StageError(code="DOCUMENT_UNREADABLE")`.
2. Segmentar el texto con `re` a partir de `config.story_delimiter_pattern` (`^##\s+.+$`),
   asignando `position` 1, 2, 3… por orden de aparición.
3. Por bloque, aplicar la regex de la declaración canónica de `plantilla_hu.md`
   (`^Como\s+(.+?),\s+quiero\s+(.+?)(?:,?\s*para\s+(.+?))?\s*\.?\s*$`):
   - Encaja completa → `UserStory` con `role`/`objective`/`benefit`, `code=HU-{n:03d}`,
     `validation_status="valid"`.
   - Encaja sin `para…` → `UserStory` `valid_with_warnings` con `ValidationIssue`
     (`rule_code="MISSING_BENEFIT"`, `severity="warning"`).
   - No encaja → `UnresolvedFragment` ("historia no identificada").
   - Generar `UserStory.id` con `uuid4()`; `original_text` = el bloque completo.
4. Construir `P1Output` (Pydantic valida unicidad y conteos). Si 0 `UserStory` →
   `StageError(code="NO_STORIES_FOUND")`.
5. Persistir vía el caller `persist_p1_user_stories`. `unresolved_fragments` e `issues` **no se
   persisten** (D-22).
6. `context.p1_output = p1_output`. Devolver
   `StageResult(warnings=(...), runtime_info={...})` — **sin `llm_runs`** (P1 no llama al LLM).
   Sugerencia de `runtime_info`: `rules_version`, `max_story_chars`, bloques_encontrados,
   hu_identificadas, hu_no_identificadas. Sugerencia de `warnings`: "N bloques no identificados
   como HU".

### 2.4 T-F4-06 · `RequirementsStage.run()` (P2 — LLM en batches)

1. Leer `context.p1_output` (las HU no `invalid`). Si 0 → `StageResult(skip_remaining=True)`
   (D-29: P3–P7 quedan `skipped`).
2. Partir las HU en lotes de `config.max_stories_per_call`.
3. Por lote: resolver el prompt con `resolve_p2_prompt(config.prompt_version)`, combinarlo con las
   HU del lote, y llamar `llm_client.complete(LlmRequest(prompt=..., model=llm_settings.model,
   system=..., ...))`.
4. Validar la respuesta con
   `P2LlmResponse.model_validate_json(raw, context={"user_story_codes": {h.code for h in lote}})`.
   Si falla:
   - **Línea de observabilidad que se pidió explícitamente:** `logger.debug(
     "P2 lote inválido generation_id=%s batch=%s raw=%s err=%s", ...)` con la salida cruda
     **truncada** y el error de Pydantic. Sin esto, un fallo `LLM_INVALID_OUTPUT` es opaco.
   - Reintentar el lote hasta `config.max_retries`. Agotados → `StageError(code="LLM_INVALID_OUTPUT",
     retryable=True)`.
   - Mapear errores del adaptador: `LlmRateLimitError` → reintentar; `LlmContextLengthError` → no
     reintentar (fallar).
5. Consolidar los lotes en un único `P2Output`: asignar códigos `RF-{n:03d}` consecutivos,
   ensamblar `classifications` + `requirements`, y calcular `stories_without_requirements` (HU
   clasificadas sin RF). `quality` y `findings` pueden quedar vacíos en v1 o generarse por reglas
   (duplicidad léxica, grounding comprobando `source_text`).
6. Persistir vía el caller `persist_p2_requirements` con `p2_output.to_rpc_payload()`.
7. `context.p2_output = p2_output`. Devolver
   `StageResult(llm_runs=(...), runtime_info={...})`. Sugerencia de `runtime_info`:
   `prompt_version`, `model`, `max_stories_per_call`, `max_retries`, lotes_totales,
   reintentos_usados, rf_count, conteos de clasificación. Sugerencia de `warnings`:
   "lote N reintentado", "HU candidata_funcional sin RF".

### 2.5 T-F4-08 · Pruebas

- **P1** (sin `LlmClient`): `DocumentTextExtractor` fake que devuelve texto con HU válidas,
  incompletas y basura. Verificar: `UserStory` generadas con `role`/`objective`/`benefit` correctos,
  `UnresolvedFragment` para los que no encajan, `EMPTY_DOCUMENT`, `NO_STORIES_FOUND` (todo
  unresolved), y que `persist_p1_user_stories` se llama con el payload correcto.
- **P2** (`LlmClient` fake): fake que devuelve JSON válido y, en otro caso, JSON inválido.
  Verificar: clasificaciones + RF generadas, reintentos de lote, D-29 (`skip_remaining=True` con 0
  RF), y que el `logger.debug` de salida cruda se emite en el caso inválido (capte el log con
  `caplog`).
- Integración de `persist_p1_user_stories` / `persist_p2_requirements` contra BD de test si existe,
  o mock del caller.
- Regresión: la suite de contratos sigue pasando.

### 2.6 T-F4-09 · Cierre

- Marcar Fase 4 como ✅ en `docs/pipeline_roadmap.md`.
- Generar `cierre_documental_fase4.md` (supuestos tomados, decisiones, advertencias nuevas — p. ej.
  si el supuesto 3 de la Fase 3 —todas las HU `invalid`→ `NO_STORIES_FOUND`— se confirmó o ajustó).
- Actualizar la tabla de prompts del roadmap: P1 = "— (sin LLM)", P2 = ✅.

---

## 3. Orden sugerido

```
2.1 callers (persist_p1 + persist_p2)   ← base para las etapas
   │
2.2 DI wiring (build_real_stages)        ← necesita config (T-F4-11) + callers
   │
   ├─► 2.3 P1 run   ← necesita plantilla (T-F4-02) + caller persist_p1
   └─► 2.4 P2 run   ← necesita prompt (T-F4-03) + caller persist_p2
   │
2.5 pruebas
   │
2.6 cierre
```

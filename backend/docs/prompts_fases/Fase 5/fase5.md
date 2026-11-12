# Fase 5 — Implementación real de P3 (embeddings) y P4 (clustering)

> **Estado:** 🔲 sin empezar — pendiente de decisiones del responsable (ver §"Decisiones de la
> fase"). Los prerequisitos (puertos, adaptadores, contratos, RPC) ya están construidos.
> **Rama de la fase anterior:** rama de trabajo de la Fase 4 (cerrada en código y pruebas;
> `schema.sql` desplegado en Supabase el 2026-11-11).
> **Documentos fuente:** `docs/pipeline_roadmap.md`,
> `docs/prompts_fases/Fase 3/issue_resolver_embeddings.md`,
> `docs/prompts_fases/Fase 3/pipeline_design.md` (P3, P4),
> `docs/prompts_fases/Fase 4/cierre_documental_fase4.md`,
> `ai_service/pipeline/contracts/p3.py`, `ai_service/pipeline/contracts/p4.py`,
> `ai_service/clients/embeddings.py`, `ai_service/clients/clustering.py`.
>
> Este archivo es el **resumen de alcance y roadmap** de la fase. Sirve como guía única para no
> repetir el contexto en cada sesión. El detalle de diseño vive en los documentos referenciados.

---

## Decisiones de la fase

Algunas requieren aprobación del responsable antes de implementar (marcadas con
**❓ PENDIENTE**); otras se delegan al agente como en la Fase 4 (**🤖 delegada**).

- **P3 no persiste (D-09).** Los embeddings viven solo en memoria (`context.p3_output`) para que
  P4 los consuma. No hay RPC de P3; `P3Output` no lleva `to_rpc_payload()`.
- **P4 sí persiste** vía `persist_p4_clusters` (una transacción: `clusters`,
  `cluster_requirements`, `unassigned_requirements`). La RPC ya existe en `schema.sql` y ya es
  idempotente (T-01, resuelta en la Fase 4); **solo falta el caller** en el repositorio.
- **R6 — un RF puede estar en varios clusters;** P5 decide en cuál es objetivo (D-31). P4 solo
  produce la pertenencia.
- **D-32 — pocos RF:** si el algoritmo no puede agrupar, todos los RF van a
  `unassigned_requirement_codes` y P4 termina `completed` con aviso `INSUFFICIENT_REQUIREMENTS`.
  **No es un error.** Lo que ocurre después en P5–P7 lo fija D-36.

### ❓ Decisiones pendientes del responsable (bloquean el inicio de la implementación)

1. **Parámetros de HDBSCAN (`min_cluster_size`, `min_samples`).** El contrato `P4Config` los
   espera en `params: dict`. **Pendiente:** cómo se configuran y con qué defaults. Opciones:
   - (a) env vars propias (`P4_MIN_CLUSTER_SIZE`, `P4_MIN_SAMPLES`) con defaults razonables.
   - (b) un único `P4_PARAMS_JSON` que se carga como dict en `P4Config.params`.
   - (c) defaults fijos en el adaptador, sin env var (menos flexible).
   **Recomendación provisional:** (a) con `min_cluster_size=2`, `min_samples=1` (coherente con
   volúmenes bajos de RF). ❓ Confirmar valores y opción.
2. **Métrica por defecto de P4** (`P4Config.metric`). El adaptador HDBSCAN ya fija
   `algorithm="generic"` cuando `metric="cosine"` (los árboles KD/Ball no admiten coseno).
   **Pendiente:** confirmar `cosine` como default (recomendado, porque los embeddings se
   normalizan L2 en P3) frente a `euclidean`. ❓ Confirmar.
3. **¿P3 reintenta lotes ante fallo del proveedor de embeddings?** Como P2 reintentaba lotes
   inválidos del LLM. Opciones:
   - (a) sí, reintentar hasta `N` veces (análogo a P2, con espera lineal) ante
     `EmbeddingsError` del proveedor; terminal si se agota.
   - (b) no: un fallo de batch es terminal → `EMBEDDINGS_FAILED`.
   **Recomendación provisional:** (a) con `P3_MAX_RETRIES` (default 2), salvo
   `EmbeddingsContextLengthError` si existiera (no reintenta). ❓ Confirmar.
4. **`input_template` de P3** (cómo se construye el texto a vectorizar por RF). El contrato
   `P3Config.input_template` lo exige. **Pendiente:** definir el default. Propuesta:
   `"{code}. {description}"` (el código da contexto sin ensuciar el contenido). ❓ Confirmar
   plantilla y si va como env var `P3_INPUT_TEMPLATE`.
5. **`normalize` de P3** (normalización L2 de vectores). Recomendado `True` (necesario para
   coseno). ❓ Confirmar default `True` y env var `P3_NORMALIZE`.

### 🤖 Delegadas al agente (no necesitan aprobación previa)

- Implementación de `EmbeddingsStage.run()` (T-F5-04) y `ClusteringStage.run()` (T-F5-05).
- Caller de `persist_p4_clusters` en el repositorio (T-F5-02).
- Cableado de dependencias (T-F5-03) y env vars que falten en `config.py` (T-F5-01).
- Pruebas (T-F5-06) con `embeddings_fake` y `clustering_fake`.
- Cierre documental y actualización del roadmap (T-F5-07).

---

## 0. Objetivo de la fase

Que las etapas **P3** (generación de embeddings) y **P4** (clustering semántico) dejen de ser
`StubStage` y ejecuten lógica real:

```
P3: P2Output(RF) → input_template → EmbeddingsClient(batches) → P3Output (solo en memoria, D-09)
P4: P2Output(RF) + P3Output(vectores) → ClusteringClient → P4Output → persist_p4_clusters (RPC)
```

Al cerrar la fase, un documento con clustering activado produce **embeddings reales** (en memoria)
y **clusters reales persistidos** en Supabase, mientras P5–P7 siguen siendo stubs. P3 y P4 se
omiten (`skipped`) cuando `clustering_enabled = false` o cuando P2 devolvió 0 RF (D-29,
`skip_remaining`).

P3 y P4 se implementan juntas por su fuerte acoplamiento (P4 lee los vectores de P3): misma
lógica que P1+P2 en la Fase 4.

---

## 1. Prerequisitos — estado real

Construidos en la Fase 3 (commits `issue_resolver_*`). Verificar antes de empezar, no
reimplementar.

| Prerequisito | Archivo | Estado |
|---|---|---|
| Puerto `EmbeddingsClient` (Protocol) + DTOs + `validate_vectors` | `ai_service/clients/embeddings.py` (`EmbeddingsRequest`, `EmbeddingsResponse`, `EmbeddingsClient`) | ✅ hecho |
| Puerto `ClusteringClient` (Protocol) + DTOs | `ai_service/clients/clustering.py` (`ClusteringRequest`, `ClusteringResult`, `ClusteringClient`) | ✅ hecho |
| Adaptadores embeddings + fake + factory | `local_embeddings.py`, `openai_embeddings.py`, `embeddings_fake.py`, `embeddings_factory.py` | ✅ hecho |
| Adaptadores clustering + fake + factory | `hdbscan_clustering.py`, `clustering_fake.py`, `clustering_factory.py` | ✅ hecho |
| Contratos P3 y P4 | `pipeline/contracts/p3.py`, `pipeline/contracts/p4.py` (`P4Output.to_rpc_payload()`) | ✅ hecho |
| `PipelineContext` con `p3_output` / `p4_output` | `pipeline/context.py` | ✅ hecho |
| RPC `persist_p4_clusters` en `schema.sql` (idempotente, T-01) | `supabase/schema.sql` | ✅ hecho y **desplegado** (2026-11-11) |
| Env vars base en `config.py` | `embeddings_provider`, `embeddings_model`, `embeddings_api_key`, `embeddings_timeout_seconds`, `clustering_algorithm` | ✅ hecho |
| `EMBEDDINGS_API_KEY` independiente de `LLM_API_KEY` | `config.py` | ✅ cerrado |
| `app.state` expone `embeddings_client` y `clustering_client` | `main.py` (construidos por factories, con `aclose()` en `AsyncExitStack`) | ✅ hecho |

> **Nota de discrepancia con el roadmap:** `pipeline_roadmap.md` lista como tareas de Fase 5
> "Puerto `EmbeddingsClient` (Protocol)" y "RPC `persist_p4_clusters` en el cliente Supabase".
> El puerto ya existe (Fase 3) y la RPC ya está desplegada; **lo que falta es el caller del
> repositorio**, no la RPC. Se corrige el roadmap en T-F5-07.

### Lo que FALTA en `config.py` para `P3Config` / `P4Config`

Hoy existen `embeddings_model` (→ `P3Config.model_name`) y `clustering_algorithm` (→
`P4Config.algorithm`). Faltan:

- **P3Config:** `normalize` (`P3_NORMALIZE`), `input_template` (`P3_INPUT_TEMPLATE`),
  `batch_size` (`P3_BATCH_SIZE`), y (si se aprueba la decisión 3) `P3_MAX_RETRIES`.
- **P4Config:** `metric` (`P4_METRIC`) y los parámetros de HDBSCAN según la decisión 1
  (`P4_MIN_CLUSTER_SIZE`, `P4_MIN_SAMPLES`, o `P4_PARAMS_JSON`).

Estos se añaden en T-F5-01 una vez cerradas las decisiones 1–5.

---

## 2. Trabajo a realizar — tareas

### T-F5-01 · Configuración de `P3Config` / `P4Config`
- Añadir a `ai_service/config.py` las env vars que exigen los contratos (ver lista arriba).
- Actualizar `.env.example` con los nuevos valores y defaults razonables.
- Construir `P3Config` y `P4Config` desde `Settings` en el wiring (T-F5-03).
- **Bloqueado por:** decisiones 1–5 del responsable.

### T-F5-02 · Caller de `persist_p4_clusters` en el repositorio
- Añadir el método al puerto `PipelineResultsRepository` + adaptador Supabase (con
  `asyncio.to_thread`) + fake en memoria (que replique idempotencia y FKs).
- Traducir errcodes: `23502` → `MissingIdentifierError`, `23503` → `InvalidReferenceError`,
  `23505` → `DuplicateEntryError`, resto → `PersistenceError` (`PERSISTENCE_FAILED`). Sigue el
  patrón de `persist_p2_requirements` de la Fase 4.
- La RPC ya existe y es idempotente; **solo falta el caller.**

### T-F5-03 · Cableado de dependencias (DI)
- `EmbeddingsStage` (P3) recibe `EmbeddingsClient` + `P3Config` por constructor (R-DI-2).
- `ClusteringStage` (P4) recibe `ClusteringClient` + `P4Config` + `PipelineResultsRepository`
  por constructor.
- `build_p3_config`, `build_p4_config` y extensión de `build_real_stages` en
  `pipeline/stages/__init__.py`. Los clientes ya están en `app.state`.
- Las etapas dejan de heredar de `StubStage`: heredan de `StageBase` e implementan `run()`
  (conservar `EmbeddingsStubStage` / `ClusteringStubStage` para `build_stub_stages`).

### T-F5-04 · Implementar `EmbeddingsStage.run()` (P3)
1. Leer `context.p2_output`. Si clustering desactivado o 0 RF → `skipped` (R2, D-29).
2. Construir los textos aplicando `P3Config.input_template` a cada RF.
3. Generar vectores en batches de `P3Config.batch_size` vía `EmbeddingsClient`. Si se aprueba la
   decisión 3, reintentar lotes fallidos del proveedor.
4. Construir `P3Output` (Pydantic valida vectores finitos y dimensión uniforme). P3 **no
   persiste** (D-09).
5. Escribir `context.p3_output`. Emitir `stage_completed` sin `LlmRun` (P3 no usa el LLM);
   reflejar `EmbeddingModelInfo` en `runtime_info` (D-34).
6. Errores: `EMBEDDINGS_FAILED` (catálogo de P3 en `pipeline_design.md`).

### T-F5-05 · Implementar `ClusteringStage.run()` (P4)
1. Leer `context.p2_output` (RF) y `context.p3_output` (vectores); `P4Input` valida
   correspondencia exacta de códigos (`_embeddings_match`).
2. Llamar a `ClusteringClient` con la métrica y parámetros de `P4Config`.
3. Construir `P4Output` (clusters + `unassigned_requirement_codes`). Reglas: **R6** (un RF en
   varios clusters), **D-32** (pocos RF → todos `unassigned`, `completed` con aviso, no error).
4. Llamar a `persist_p4_clusters` con `P4Output.to_rpc_payload()`.
5. Escribir `context.p4_output`. Emitir `stage_completed` con `algorithm_info` (D-34).
6. Errores: `CLUSTERING_FAILED` (código ya fijado en el catálogo de P4).

### T-F5-06 · Pruebas
- **P3** con `embeddings_fake` (no necesita LLM): happy path en batches, vectores NaN/inf →
  error, dimensión no uniforme, 0 RF → `skipped`, batches respetan `batch_size`, reintento si se
  aprueba la decisión 3.
- **P4** con `clustering_fake`: happy path, D-32 (pocos RF → todos `unassigned` sin error), R6
  (RF en varios clusters), fallo del algoritmo → `CLUSTERING_FAILED`, persistencia e
  idempotencia de `persist_p4_clusters` (fake), traducción de errcodes (`23502`, `23503`).
- **Wiring / extremo a extremo** (HTTP + fakes): documento → HU + RF + embeddings + clusters
  persistidos; `clustering_enabled=false` → P3/P4 `skipped`; D-29 (0 RF) → P3–P7 `skipped`.
- Confirmar que la suite de contratos sigue sin regresión.

### T-F5-07 · Actualizar roadmap y cierre documental
- Marcar Fase 5 como ✅ en `docs/pipeline_roadmap.md`.
- **Corregir** el roadmap: el puerto `EmbeddingsClient` ya existía y la RPC `persist_p4_clusters`
  ya estaba desplegada; anotar que solo se añadió el caller.
- Generar `cierre_documental_fase5.md` (supuestos, decisiones, advertencias nuevas).

---

## 3. Orden de ejecución sugerido

```
Decisiones 1–5 del responsable          ← bloquea T-F5-01
   │
T-F5-01 (config P3/P4)                  ← fija P3Config/P4Config
   │
T-F5-02 (caller persist_p4_clusters)    ← la RPC ya existe en BD
   │
T-F5-03 (DI wiring)                      ← build_p3_config, build_p4_config, build_real_stages
   │
   ├─► T-F5-04 (P3 run)  ← lee p2_output, no persiste (D-09)
   └─► T-F5-05 (P4 run)  ← lee p2_output + p3_output, persiste clusters
   │
T-F5-06 (pruebas)
   │
T-F5-07 (cierre documental + roadmap)
```

---

## 4. Criterios de cierre

La Fase 5 está completa cuando **todos** estos puntos se cumplen:

- [ ] `EmbeddingsStage` y `ClusteringStage` no heredan de `StubStage` (lógica real).
- [ ] Un documento con clustering activado produce embeddings reales (en memoria) y clusters
      reales persistidos en Supabase (P5–P7 siguen como stubs).
- [ ] El repositorio expone el caller de `persist_p4_clusters` (puerto + adaptador + fake).
- [ ] `config.py` expone las variables de `P3Config`/`P4Config` (incluidas las de la decisión 1).
- [ ] P3 no persiste (D-09); P4 persiste vía `persist_p4_clusters`.
- [ ] R6 (RF en varios clusters) y D-32 (pocos RF → `unassigned`, `completed` con aviso) funcionan.
- [ ] P3/P4 quedan `skipped` con `clustering_enabled=false` y con 0 RF (D-29).
- [ ] Pruebas de P3 (`embeddings_fake`) y P4 (`clustering_fake`) pasan; la suite de contratos
      sin regresión.
- [ ] `pipeline_roadmap.md` actualizado (y corregido) y `cierre_documental_fase5.md` generado.

---

## 5. Reglas del pipeline que aplican a esta fase (referencia rápida)

| Regla | Cómo aplica en Fase 5 |
|---|---|
| D-09 | P3 no persiste: los embeddings viven solo en `context.p3_output`. |
| D-29 | Si P2 devolvió 0 RF → `skip_remaining`: P3–P7 `skipped`. |
| D-32 | Pocos RF → todos `unassigned_requirement_codes`; P4 `completed` con aviso, no error. |
| D-34 | P3 deja `EmbeddingModelInfo` y P4 `ClusteringAlgorithmInfo` en `runtime_info`. |
| R2 | P3 y P4 se omiten (`skipped`) si `clustering_enabled = false`. |
| R6 | Un RF puede pertenecer a varios clusters; P5 decide en cuál es objetivo (D-31). |
| R-AP-2 / R-AP-3 | Las etapas dependen de puertos (`EmbeddingsClient`, `ClusteringClient`), nunca de un adaptador concreto. |
| R-DI-2 | Los puertos se inyectan por constructor; el wiring ocurre en `main.py`/`stages/__init__.py`. |
| R-FA-3 / R-FA-7 | Imports lazy en factories; `aclose()` al apagar solo para los clientes que construyó la factory. |

---

## 6. Riesgos y advertencias activas (heredadas)

1. **`dict` en modelos frozen** — `P4Config.params`, `ClusteringAlgorithmInfo.params` y
   `ContextUnit.requirement_to_stories` tienen `dict` que `frozen=True` no hace inmutable. Aparece
   si una etapa muta un dict del contrato.
2. **`sentence-transformers` (instala torch)** — declarado en `requirements.txt` para el adaptador
   local, pero los tests no lo necesitan: el adaptador local se prueba con un modelo falso
   inyectado.
3. **HDBSCAN con `metric="cosine"`** — fija `algorithm="generic"` si no viene en `params` (los
   árboles KD/Ball no admiten coseno). Los parámetros efectivos se toman de
   `estimator.get_params()` y se filtran a serializables a JSON.
4. **Sin prueba de RPC contra Postgres real para P4** — la idempotencia se valida con tests de
   estructura del SQL y el fake en memoria; la validación definitiva ocurre al desplegar o contra
   una BD de test. Como `schema.sql` ya está desplegado, conviene un smoke test contra Supabase en
   T-F5-02.

---

## 7. Total de fases del proyecto (roadmap completo)

| Fase | Nombre | Estado |
|---|---|---|
| 1 | Infraestructura del pipeline (stubs, API, persistencia, recuperación) | ✅ |
| 1.5 | Conexión frontend–backend (CORS, polling, rehidratación) | ✅ |
| 2 | Subida de documentos (backend + frontend) | ✅ |
| 3 | Contratos P1–P6 + `PipelineContext` + prompts P6 | ✅ |
| 4 | Implementación de P1 (heurística) y P2 (LLM) | ✅ |
| **5** | **Implementación de P3 (embeddings) y P4 (clustering)** | **🔲** |
| 6 | Implementación de P5 (contexto estructurado) | 🔲 |
| 7 | Implementación de P6 (generación de casos de prueba) | 🔲 |
| 8 | Implementación de P7 (evaluación) + cierre (SSE, integración E2E) | 🔲 |

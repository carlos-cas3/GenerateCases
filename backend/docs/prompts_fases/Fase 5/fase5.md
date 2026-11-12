# Fase 5 — Implementación real de P3 (embeddings) y P4 (clustering)

> **Estado:** 🔲 sin empezar — decisiones del responsable **resueltas** (ver §"Decisiones de la
> fase"); listo para implementar. Los prerequisitos (puertos, adaptadores, contratos, RPC) ya
> están construidos. Falta verificar el **prerrequisito de atomicidad de P2** antes de pasar
> documentos reales.
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
> La guía tarea a tarea está en [`guia_implementacion.md`](guia_implementacion.md).
>
> **Patrones de arquitectura.** La implementación debe seguir los patrones existentes del
> proyecto (`docs/architecture_patterns.md`): puertos/adaptadores y duck typing (R-AP-2/R-AP-3),
> adaptadores que capturan fallos de librerías y lanzan `AppError` (R-AP-4), inyección por
> constructor (R-DI-2), fakes para tests (R-DI-3/R-FA-6), factories solo en `main.py` con imports
> lazy (R-FA-3/R-FA-5) y `aclose()` solo para lo que la factory construyó (R-FA-7). **Si se
> introduce un patrón nuevo**, documentarlo en `cierre_documental_fase5.md` y en el catálogo de
> patrones.

---

## Decisiones de la fase

Resueltas con el responsable (**✅**) o delegadas al agente como en la Fase 4 (**🤖**). Las
marcadas ✅ ya no bloquean la implementación.

- **P3 no persiste (D-09).** Los embeddings viven solo en memoria (`context.p3_output`) para que
  P4 los consuma. No hay RPC de P3; `P3Output` no lleva `to_rpc_payload()`.
- **P4 sí persiste** vía `persist_p4_clusters` (una transacción: `clusters`,
  `cluster_requirements`, `unassigned_requirements`). La RPC ya existe en `schema.sql` y ya es
  idempotente (T-01, resuelta en la Fase 4); **solo falta el caller** en el repositorio.
- **D-32 — pocos RF:** si el algoritmo no puede agrupar, todos los RF van a
  `unassigned_requirement_codes` y P4 termina `completed` con aviso `INSUFFICIENT_REQUIREMENTS`.
  **No es un error.** Lo que ocurre después en P5–P7 lo fija D-36 (más abajo).

### ✅ Decisiones resueltas del responsable

1. **Parámetros de HDBSCAN — `min_cluster_size=2`, `min_samples=1`** (env vars
   `P4_MIN_CLUSTER_SIZE`, `P4_MIN_SAMPLES`, volcadas en `P4Config.params`). Son **pisos mínimos**,
   no tamaños forzados ni simetría: HDBSCAN sigue descubriendo el número y tamaño de clusters que
   dé la realidad y solo descarta los grupos más chicos que el piso. Son **valores iniciales a
   validar** con documentos reales: si salen clusters demasiado chicos, subir `min_cluster_size`;
   si queda mucho RF sin asignar, bajarlo. Ajustables por env var sin tocar código.
2. **Métrica por defecto `cosine`** (env var `P4_METRIC`). El adaptador HDBSCAN ya fija
   `algorithm="generic"` cuando `metric="cosine"`. Coherente con la normalización L2 de P3
   (decisión 5): con vectores normalizados, `cosine` y `euclidean` son equivalentes.
3. **P3 reintenta lotes** ante fallo del proveedor, hasta `P3_MAX_RETRIES` (default 2) con espera
   lineal. **Solo fallos transitorios** (timeout, rate limit → `EmbeddingsError` genérico). **No
   se reintenta** `EmbeddingsDimensionError` ni `EmbeddingsInvalidVectorError` (no son
   transitorios: el mismo modelo los reproduciría). Agotados → `EMBEDDINGS_FAILED` (P3 es
   bloqueante → la generación falla). Análogo a P2, que reintenta pero no reintenta
   `LlmContextLengthError`.
4. **`input_template` default `"{code}. {description}"`** (env var `P3_INPUT_TEMPLATE`). El
   código da anclaje sin contaminar el contenido; la descripción es el texto a vectorizar. Viaja
   en `EmbeddingModelInfo.input_template` para reproducibilidad/auditoría.
5. **`normalize` default `True`** (env var `P3_NORMALIZE`). Necesario para `cosine` y estándar en
   embeddings. Configurable; sin tocar código.

### ✅ Hallazgos resueltos durante la planificación

- **`EmbeddingModelInfo.provider` (H-2).** `P3Config` no lleva `provider`, pero `EmbeddingModelInfo`
  lo exige. **Resuelto:** se pasa `provider` (desde `settings.embeddings_provider`) como argumento
  aparte al constructor de `EmbeddingsStage`, **sin tocar el contrato de la Fase 3**.
- **R6 / membresía múltiple (H-3).** HDBSCAN es clustering duro: cada RF queda en **un solo**
  cluster (o `unassigned`). R6 ("un RF en varios clusters") **no se produce con HDBSCAN**; D-31
  ("P5 elige el cluster objetivo") queda **diferido** a un eventual algoritmo superpuesto futuro.
  P5 (Fase 6) puede asumir membresía única. La atomicidad de los RF (que un RF no abarque dos
  dominios) es **responsabilidad de P2**, no de P4/P5 (ver prerrequisito P2 más abajo).
- **Nombres de cluster (D-A).** HDBSCAN solo da labels numéricos y `clusters.name` es `NOT NULL`.
  P4 nombra cada cluster como `f"Cluster {label}"` (placeholder); P5 (Fase 6) le da el nombre con
  sentido al construir el contexto.
- **`similarity_to_centroid` (D-B).** Sí se calcula en P4 y se persiste en
  `cluster_requirements.similarity_to_centroid`. **Motivo:** P3 no persiste vectores (D-09), así
  que P4 es la última etapa que los tiene; si no los guarda aquí, ninguna etapa posterior los
  recupera. Es una medida **descriptiva** (qué tan representativo es el RF de su cluster), **no**
  decide la membresía (eso lo hace HDBSCAN por densidad, no por centroides). Útil para P5 y para
  el usuario.
- **D-36 — RF sin cluster en P5–P7.** Los RF en `unassigned_requirement_codes` se **guardan y se
  muestran**, pero **no generan casos de prueba** (coherente con el comentario del `schema.sql`:
  "por ahora no generan casos de prueba"). La generación termina `completed` con aviso, no como
  error. Regla para implementar en la Fase 6; se fija ahora.

### Prerrequisito de calidad — atomicidad de P2

La calidad del clustering depende de que P2 produzca **RF atómicos** (un comportamiento/salida
por RF). El prompt actual de P2 (`prompts/texts/p2_requirements.md`) pide "atómica" **pero su
ejemplo es compuesto** ("exportar en PDF **y** CSV"), lo que enseña al LLM a generar RFs
compuestos. Consecuencia: pueden llegar RFs que abarcan dos dominios, que HDBSCAN aplana a un
solo cluster (degradación aceptable, pero subóptima).

- **Antes de pasar documentos reales por P3/P4**, verificar que el prompt de P2 produce RF
  atómicos.
- Si no está corregido, queda como **tarea de mejora del prompt de la Fase 4**: corregir el
  ejemplo compuesto y añadir la regla *"si una HU describe dos o más comportamientos/salidas
  independientes, extráelos como RF separados"* (con un ejemplo "antes → después").
- **P4/P5 no parten RFs compuestos:** asumen atomicidad. Es una mejora de P2, no de la Fase 5.

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
| Orquestador: omite P3/P4 sin clustering y respeta `skip_remaining` (D-29) | `pipeline/orchestrator.py` (`should_skip`) | ✅ hecho |
| Catálogo: P3 y P4 **bloqueantes** (`blocking=True`) | `pipeline/catalog.py` | ✅ confirmado |

> **Prerrequisito de calidad (no en la tabla):** atomicidad del prompt de P2 — ver
> §"Decisiones de la fase" › "Prerrequisito de calidad — atomicidad de P2".

> **Nota de discrepancia con el roadmap:** `pipeline_roadmap.md` lista como tareas de Fase 5
> "Puerto `EmbeddingsClient` (Protocol)" y "RPC `persist_p4_clusters` en el cliente Supabase".
> El puerto ya existe (Fase 3) y la RPC ya está desplegada; **lo que falta es el caller del
> repositorio**, no la RPC. Se corrige el roadmap en T-F5-07.

### Lo que FALTA en `config.py` para `P3Config` / `P4Config`

Hoy existen `embeddings_model` (→ `P3Config.model_name`) y `clustering_algorithm` (→
`P4Config.algorithm`). Faltan (con los defaults resueltos):

- **P3Config:** `normalize` (`P3_NORMALIZE=True`), `input_template`
  (`P3_INPUT_TEMPLATE="{code}. {description}"`), `batch_size` (`P3_BATCH_SIZE`, >0),
  `P3_MAX_RETRIES` (default 2).
- **P4Config:** `metric` (`P4_METRIC=cosine`) y los parámetros de HDBSCAN (decisión 1):
  `P4_MIN_CLUSTER_SIZE` (2), `P4_MIN_SAMPLES` (1), volcados en `P4Config.params`.

`provider` para `EmbeddingModelInfo` **no** va en `P3Config`: se pasa aparte al stage (H-2), desde
`settings.embeddings_provider`. Estos se añaden en T-F5-01.

---

## 2. Trabajo a realizar — tareas

### T-F5-01 · Configuración de `P3Config` / `P4Config`
- Añadir a `ai_service/config.py` las env vars que exigen los contratos, con los defaults
  resueltos: `P3_NORMALIZE` (True), `P3_INPUT_TEMPLATE` (`"{code}. {description}"`),
  `P3_BATCH_SIZE` (>0), `P3_MAX_RETRIES` (2); `P4_METRIC` (`cosine`), `P4_MIN_CLUSTER_SIZE` (2),
  `P4_MIN_SAMPLES` (1).
- Actualizar `.env.example` con los nuevos valores y defaults.
- Construir `P3Config` y `P4Config` desde `Settings` en el wiring (T-F5-03). `P4Config.params`
  se arma con `min_cluster_size` y `min_samples`.
- `provider` para `EmbeddingModelInfo` se pasa aparte al stage (H-2), no en `P3Config`.

### T-F5-02 · Caller de `persist_p4_clusters` en el repositorio
- Añadir el método al puerto `PipelineResultsRepository` + adaptador Supabase (con
  `asyncio.to_thread`) + fake en memoria (que replique idempotencia y FKs).
- Traducir errcodes: `23502` → `MissingIdentifierError`, `23503` → `InvalidReferenceError`,
  `23505` → `DuplicateEntryError`, resto → `PersistenceError` (`PERSISTENCE_FAILED`). Sigue el
  patrón de `persist_p2_requirements` de la Fase 4.
- La RPC ya existe y es idempotente; **solo falta el caller.**

### T-F5-03 · Cableado de dependencias (DI)
- `EmbeddingsStage` (P3) recibe `EmbeddingsClient` + `P3Config` + `provider` (H-2) por
  constructor (R-DI-2).
- `ClusteringStage` (P4) recibe `ClusteringClient` + `P4Config` + `PipelineResultsRepository`
  por constructor.
- `build_p3_config`, `build_p4_config` y extensión de `build_real_stages` en
  `pipeline/stages/__init__.py`. Los clientes ya están en `app.state`; **hay que añadir
  `embeddings_client` y `clustering_client` a la firma de `build_real_stages`** (hoy no los
  recibe) y propagarlos desde `main.py`. Actualizar `tests/test_stages_wiring.py`.
- Las etapas dejan de heredar de `StubStage`: heredan de `StageBase` e implementan `run()`
  (conservar `EmbeddingsStubStage` / `ClusteringStubStage` para `build_stub_stages`).

### T-F5-04 · Implementar `EmbeddingsStage.run()` (P3)
1. Leer `context.p2_output`. Si clustering desactivado o 0 RF → `skipped` (R2, D-29).
2. Construir los textos aplicando `P3Config.input_template` a cada RF.
3. Generar vectores en batches de `P3Config.batch_size` vía `EmbeddingsClient`; pasar
   `extra={"batch_size": config.batch_size}` para alinear el batch de etapa con el del adaptador.
   Reintentar por lote ante `EmbeddingsError` transitorio hasta `P3_MAX_RETRIES` (decisión 3);
   **no reintentar** `EmbeddingsDimensionError` ni `EmbeddingsInvalidVectorError`.
4. Construir `P3Output` (Pydantic valida vectores finitos y dimensión uniforme). P3 **no
   persiste** (D-09).
5. Escribir `context.p3_output`. Emitir `stage_completed` sin `LlmRun` (P3 no usa el LLM);
   reflejar `EmbeddingModelInfo` (con `provider`) en `runtime_info` (D-34).
6. Errores: `EMBEDDINGS_FAILED` (catálogo de P3 en `pipeline_design.md`).

### T-F5-05 · Implementar `ClusteringStage.run()` (P4)
1. Leer `context.p2_output` (RF) y `context.p3_output` (vectores); `P4Input` valida
   correspondencia exacta de códigos (`_embeddings_match`).
2. Llamar a `ClusteringClient` con la métrica y parámetros de `P4Config`.
3. Construir `P4Output`: cada label `>=0` → `SemanticCluster` con `id=uuid4()`,
   `name=f"Cluster {label}"` (D-A), `cluster_label=label`; label `-1` → `unassigned`.
   Calcular `similarity_to_centroid` de cada RF al centroide de su cluster (D-B) — P4 es la
   última etapa con los vectores. Reglas: **R6** (con HDBSCAN → membresía única; D-31 diferido),
   **D-32** (todos label `-1` → `clusters=()`, `unassigned=todos`, `completed` con aviso
   `INSUFFICIENT_REQUIREMENTS`, no error).
4. Llamar a `persist_p4_clusters` con `P4Output.to_rpc_payload()`.
5. Escribir `context.p4_output`. Emitir `stage_completed` con `algorithm_info` (D-34).
6. Errores: `CLUSTERING_FAILED` (código ya fijado en el catálogo de P4).

### T-F5-06 · Pruebas
- **P3** con `embeddings_fake` (no necesita LLM): happy path en batches, vectores NaN/inf →
  error, dimensión no uniforme, 0 RF → `skipped`, batches respetan `batch_size`, reintento
  transitorio y **no** reintento de `EmbeddingsDimensionError` (decisión 3).
- **P4** con `clustering_fake`: happy path, D-32 (pocos RF → todos `unassigned` sin error), R6
  (membresía única con HDBSCAN; el fake puede simular solapamiento para validar el contrato),
  fallo del algoritmo → `CLUSTERING_FAILED`, persistencia e idempotencia de `persist_p4_clusters`
  (fake), traducción de errcodes (`23502`, `23503`), cálculo de `similarity_to_centroid`.
- **Wiring / extremo a extremo** (HTTP + fakes): documento → HU + RF + embeddings + clusters
  persistidos; `clustering_enabled=false` → P3/P4 `skipped`; D-29 (0 RF) → P3–P7 `skipped`.
- Confirmar que la suite de contratos sigue sin regresión.

### T-F5-07 · Actualizar roadmap y cierre documental
- Marcar Fase 5 como ✅ en `docs/pipeline_roadmap.md`.
- **Corregir** el roadmap: el puerto `EmbeddingsClient` ya existía y la RPC `persist_p4_clusters`
  ya estaba desplegada; anotar que solo se añadió el caller.
- Generar `cierre_documental_fase5.md` (supuestos, decisiones, advertencias nuevas — incluidos
  R6/D-31 diferido, D-36 y el prerrequisito de atomicidad de P2).

---

## 3. Orden de ejecución sugerido

```
Prerrequisito P2 (atomicidad del prompt de P2)   ← verificar antes; si no, mejorar el prompt (Fase 4)
   │
T-F5-01 (config P3/P4)                  ← fija P3Config/P4Config (decisiones 1–5 resueltas)
   │
T-F5-02 (caller persist_p4_clusters)    ← la RPC ya existe en BD
   │
T-F5-03 (DI wiring)                      ← build_p3_config, build_p4_config, build_real_stages (+ clientes)
   │
   ├─► T-F5-04 (P3 run)  ← lee p2_output, no persiste (D-09); provider aparte (H-2)
   └─► T-F5-05 (P4 run)  ← lee p2_output + p3_output, persiste clusters; "Cluster {label}"; similarity (D-B)
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
- [ ] P4 nombra clusters como `"Cluster {label}"` (D-A) y calcula/persiste
      `similarity_to_centroid` (D-B).
- [ ] R6 (membresía única con HDBSCAN; D-31 diferido) y D-32 (pocos RF → `unassigned`,
      `completed` con aviso) funcionan.
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
| D-36 | RF sin cluster: se guardan y se muestran, no generan casos (regla para la Fase 6). |
| R2 | P3 y P4 se omiten (`skipped`) si `clustering_enabled = false`. |
| R6 | Permitido por el contrato (RF en varios clusters), pero HDBSCAN produce membresía única. D-31 diferido a un algoritmo superpuesto futuro. La atomicidad de los RF es responsabilidad de P2. |
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
5. **Atomicidad de P2 débil** — el prompt de P2 pide RF atómicos pero su ejemplo es compuesto
   ("PDF y CSV"); pueden llegar RF que abarcan dos dominios, que HDBSCAN aplana a un cluster.
   Prerrequisito: verificar/mejorar el prompt de P2 (Fase 4) antes de correr documentos reales.

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

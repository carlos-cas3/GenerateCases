# Cierre documental — Fase 5 (P3 embeddings + P4 clustering)

> **Estado:** ✅ implementación cerrada en código y pruebas (464 tests pasan; antes de la fase
> eran 427). Pendiente **fuera de código**: smoke test de `persist_p4_clusters` contra Supabase y
> calibración de HDBSCAN con documentos reales (ver §6).
> **Alcance:** T-F5-01 … T-F5-07 de [`fase5.md`](fase5.md), siguiendo
> [`guia_implementacion.md`](guia_implementacion.md) salvo donde se indica en §3.

---

## 1. Verificación previa

| Comprobación | Resultado |
|---|---|
| Suite completa antes de tocar código | ✅ 427 pasan |
| Puertos, adaptadores, fakes y factories de embeddings/clustering (Fase 3) | ✅ existían; no se reimplementaron |
| RPC `persist_p4_clusters` en `schema.sql` (idempotente, T-01) | ✅ existía y está desplegada; solo faltaba el caller |
| Prerrequisito de atomicidad de P2 | ✅ el prompt `p2_requirements.md` ya tiene la sección "Atomicidad de los RF" con ejemplo malo → bueno (commit `85d580c`). Falta confirmarlo con documentos reales (§6). |

---

## 2. Qué se implementó

| Tarea | Archivos | Resumen |
|---|---|---|
| T-F5-01 config | `config.py`, `.env.example` | `P3_NORMALIZE` (true), `P3_INPUT_TEMPLATE` (`{description}`), `P3_BATCH_SIZE` (32), `P3_MAX_RETRIES` (2), `P4_METRIC` (cosine), `P4_MIN_CLUSTER_SIZE` (2, `ge=2`), `P4_MIN_SAMPLES` (1). La plantilla se valida al arrancar: solo `{code}`/`{description}` y `{description}` obligatoria. |
| T-F5-02 caller RPC | `repositories/pipeline_results.py` (puerto), `supabase_pipeline_results.py` (adaptador), `in_memory.py` (fake) | `persist_p4_clusters` reutiliza `_call` (errcodes `23502`/`23503`/`23505`/resto). El fake replica la RPC: id obligatorio, FK de RF, `ON CONFLICT` por cluster `id`, por `(cluster, RF)` y por RF sin cluster; guarda `similarity_to_centroid`. Nuevas colecciones en `InMemoryStore`: `clusters`, `cluster_requirements`, `unassigned_requirements`. |
| T-F5-03 DI | `pipeline/stages/__init__.py`, `main.py` | `build_p3_config`, `build_p4_config`; `build_real_stages` recibe `embeddings_client` y `clustering_client` y devuelve P1–P4 reales + P5–P7 stubs. `EmbeddingsStubStage`/`ClusteringStubStage` se conservan para `build_stub_stages`. |
| T-F5-04 P3 | `pipeline/stages/p3_embeddings.py` | Ver §3. No persiste (D-09); `runtime_info.embedding_model` con `provider` (D-34, H-2); sin `llm_runs`. |
| T-F5-05 P4 | `pipeline/stages/p4_clustering.py` | Ver §3. `"Cluster {label}"` (D-A), `similarity_to_centroid` (D-B), D-32, persistencia vía RPC, `runtime_info.algorithm_info` (D-34). |
| Corrección adaptador | `clients/hdbscan_clustering.py` | Los parámetros efectivos de HDBSCAN incluían `cluster_selection_epsilon_max=inf`, que **no es JSON válido para `jsonb`** y habría hecho fallar la escritura del `runtime_info` de P4 en Supabase. Se descartan los floats no finitos. |
| T-F5-06 pruebas | `tests/test_p3_embeddings.py` (16), `tests/test_p4_clustering.py` (16), `tests/test_stages_wiring.py` (+5), `tests/test_embeddings_clients.py` (endurecido) | Ver §5. |
| T-F5-07 docs | `docs/pipeline_roadmap.md`, `docs/architecture_patterns.md`, este archivo | Roadmap marcado ✅ y corregido (puerto y RPC ya existían). |

---

## 3. Decisiones y supuestos tomados en la implementación

1. **`max_retries` de P3 va aparte de `P3Config`**, igual que `provider` (H-2): el contrato de la
   Fase 3 no tiene ese campo y la decisión fue no tocarlo. `EmbeddingsStage(…, provider=…,
   max_retries=…)` desde `settings.embeddings_provider` y `settings.p3_max_retries`.
2. **Reintentos de P3**: solo `EmbeddingsError` genérico (transitorio), espera lineal
   (`retry_delay_seconds * intento`). `EmbeddingsDimensionError` y `EmbeddingsInvalidVectorError`
   fallan al primer intento (`retryable=False`, `details.cause` con el código original). Todos los
   fallos de P3 se reportan como `EMBEDDINGS_FAILED`. Si hubo reintentos, aviso `BATCH_RETRIED`.
3. **Validaciones extra de P3**: número de vectores ≠ número de RF del lote → `EMBEDDINGS_FAILED`;
   dimensión distinta entre lotes o vectores no finitos → `EMBEDDINGS_FAILED` (vía validación
   Pydantic de `P3Output`). `EmbeddingModelInfo` toma modelo/dimensión de la respuesta del primer lote.
4. **0 RF en P3** (no debería llegar por D-29): devuelve `skip_remaining=True` con aviso
   `NO_REQUIREMENTS`, sin construir `P3Input` (que exige ≥1 RF).
5. **D-32 sin llamar al algoritmo**: si hay menos RF que `min_cluster_size`, P4 no llama a HDBSCAN
   (no puede formar ningún cluster) y deja todos sin asignar con `INSUFFICIENT_REQUIREMENTS`. En
   ese caso `algorithm_info.params` refleja los parámetros configurados, no los efectivos.
   Si HDBSCAN corre y marca todo como ruido, el resultado es el mismo aviso.
6. **Aviso nuevo `UNASSIGNED_REQUIREMENTS`**: cuando hay clusters pero algunos RF quedan como ruido,
   P4 lo indica con los códigos afectados (refuerza D-36: se muestran pero no generarán casos).
7. **`similarity_to_centroid`** = coseno entre el vector del RF y la media de los vectores de su
   cluster, redondeado a 6 decimales y acotado a [-1, 1]. `None` si un vector es nulo.
8. **Errores de P4**: `ClusteringError`, número de labels incorrecto, vectores que no corresponden
   a los RF (`P4Input._embeddings_match`) o `P4Output` inconsistente → `CLUSTERING_FAILED`.
   `PersistenceError` → `StageError` con su propio código y `retryable=True` (como P2).
9. **Orden**: vectores y códigos se pasan al algoritmo en el orden de `p3_output.embeddings`; los
   clusters se emiten ordenados por label.

**Patrones:** no se introdujo ningún patrón nuevo. Las etapas siguen R-AP-2/R-AP-3 (dependen de
puertos), R-DI-2 (inyección por constructor), R-AP-4 (el adaptador HDBSCAN sigue capturando
excepciones de la librería) y R-FA-7 (`main.py` cierra solo lo que construyó la factory).

---

## 4. Decisiones del responsable aplicadas

| Decisión | Dónde |
|---|---|
| 1 — HDBSCAN `min_cluster_size=2`, `min_samples=1` (pisos, por env var) | `config.py`, `build_p4_config` |
| 2 — métrica `cosine` | `P4_METRIC`; el adaptador fija `algorithm="generic"` |
| 3 — reintento solo transitorio en P3 | `EmbeddingsStage._run_batch` |
| 4 — `input_template` `"{description}"` | `P3_INPUT_TEMPLATE`; viaja en `EmbeddingModelInfo.input_template`. Por defecto solo la descripción: el código del RF es un identificador sin semántica y añade ruido al embedding (el template sigue admitiendo `{code}`). |
| 5 — `normalize=True` | `P3_NORMALIZE` |
| H-2 — `provider` aparte | `EmbeddingsStage(provider=…)` |
| H-3 / R6 — membresía única con HDBSCAN; D-31 diferido | P4 asigna cada RF a un solo cluster |
| D-A — `"Cluster {label}"` | `p4_clustering._build_clusters` |
| D-B — `similarity_to_centroid` en P4 | idem; se persiste en `cluster_requirements` |
| D-09 — P3 no persiste | P3 solo escribe `context.p3_output` |
| D-32 — pocos RF → `unassigned` + aviso, no error | ver §3.5 |
| D-36 — RF sin cluster no generan casos | regla para la Fase 6 (sin código en esta fase) |

---

## 5. Pruebas

- **P3** (`test_p3_embeddings.py`): lotes y `batch_size`, texto con la plantilla, `extra["batch_size"]`,
  `EmbeddingModelInfo` con `provider`, 0 RF, falta de `p2_output`, reintento transitorio, reintentos
  agotados, no reintento de dimensión/vector inválido, número de vectores incorrecto, dimensión no
  uniforme entre lotes, NaN; defaults y validación de las env vars nuevas.
- **P4** (`test_p4_clustering.py`): happy path (nombres, membresía única, similitud calculada,
  persistencia), D-32 por ruido y por `min_cluster_size`, `CLUSTERING_FAILED` (algoritmo, labels,
  vectores ↔ RF), error de persistencia, idempotencia y FK del fake, traducción de errcodes del
  adaptador Supabase (`23502`, `23503`, `23505`, resto) y llamada a la RPC.
- **Extremo a extremo HTTP** (`test_stages_wiring.py`): documento → HU + RF + clusters persistidos;
  `semantic_clustering_enabled=false` → P3/P4 `skipped`; 1 RF → P4 `completed` con
  `INSUFFICIENT_REQUIREMENTS`; fallo del clustering → generación `failed` en P4; D-29 sin cambios.
- **Regresión:** suite completa 464 ✅ (contratos incluidos).

---

## 6. Advertencias y pendientes

1. **Calibración de HDBSCAN.** Con pocos RF HDBSCAN suele marcar todo como ruido (probado en
   local: 2 y 3 vectores → todo `-1`; 6 vectores en dos grupos → 2 clusters). Validar con
   documentos reales; ajustar `P4_MIN_CLUSTER_SIZE` / `P4_MIN_SAMPLES` por env var.
2. **Smoke test contra Supabase.** `persist_p4_clusters` se validó con el fake y con tests del
   adaptador, no contra Postgres real.
3. **Atomicidad de P2 con documentos reales.** El prompt ya está corregido; falta comprobar con
   documentos reales que los RF salen atómicos. P4/P5 no parten RF compuestos.
4. **R6 / D-31 diferido.** P5 (Fase 6) puede asumir membresía única mientras se use HDBSCAN.
5. **D-36 para la Fase 6.** Los RF en `unassigned_requirements` se muestran pero no generan casos.
6. **Primer arranque con `EMBEDDINGS_PROVIDER=local`** descarga el modelo de sentence-transformers.
7. **`dict` en modelos frozen** (heredada): `P4Config.params` y `ClusteringAlgorithmInfo.params`;
   P4 copia los dicts antes de pasarlos al cliente y al contrato.

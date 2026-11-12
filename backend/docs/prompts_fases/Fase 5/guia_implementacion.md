# Guía de implementación — Fase 5 (P3 embeddings + P4 clustering)

> **Guía de sugerencia. No es obligatoria.** Son sugerencias concretas de "cómo" implementar las
> tareas pendientes de la Fase 5 (T-F5-01 … T-F5-07). Si consideras correcto algo, impleméntalo; si
> no, se descarta. El responsable ya dio las directrices (ver
> [`fase5.md`](fase5.md) §"Decisiones de la fase"); esta guía es el detalle para quien codee.
>
> **Esto es orientación, no código aplicado.** Los prerequisitos (puertos, adaptadores,
> contratos, RPC) ya están construidos (Fase 3); aquí solo se cablean y se rellena la lógica de
> las etapas.
>
> **Patrones.** Seguir los patrones existentes (`docs/architecture_patterns.md`: R-AP-2/R-AP-3,
> R-AP-4, R-DI-2, R-DI-3/R-FA-6, R-FA-3/R-FA-5, R-FA-7). Si surge uno nuevo al implementar,
> documentarlo en `cierre_documental_fase5.md` y en el catálogo de patrones.

---

## 1. Base ya aplicada (no requiere acción, solo verificar al empezar)

Construido en la Fase 3 y verificado en la planificación de la Fase 5.

| Qué | Dónde | Notas |
|---|---|---|
| Puerto `EmbeddingsClient` + DTOs + `validate_vectors` | `ai_service/clients/embeddings.py` | `EmbeddingsRequest` lleva `texts`, `model`, `input_template`, `normalize`, `extra`. |
| Puerto `ClusteringClient` + DTOs | `ai_service/clients/clustering.py` | `ClusteringRequest` lleva `vectors`, `codes`, `metric`, `params`. |
| Adaptadores embeddings | `local_embeddings.py`, `openai_embeddings.py`, `embeddings_fake.py`, `embeddings_factory.py` | Ambos leen `extra["batch_size"]`; OpenAI renormaliza L2. |
| Adaptadores clustering | `hdbscan_clustering.py`, `clustering_fake.py`, `clustering_factory.py` | HDBSCAN fija `algorithm="generic"` con `cosine`; `params` se pasa a `HDBSCAN(**params)`. |
| Contratos P3/P4 | `pipeline/contracts/p3.py`, `pipeline/contracts/p4.py` | `P4Output.to_rpc_payload()` listo; `P3Output` sin persistencia (D-09). |
| `PipelineContext` | `pipeline/context.py` | Campos `p3_output` / `p4_output` ya existen. |
| RPC `persist_p4_clusters` | `supabase/schema.sql` | Desplegada e idempotente; `clusters.name` es `NOT NULL`. |
| Env vars base | `ai_service/config.py` | `embeddings_provider/model/api_key/timeout`, `clustering_algorithm`. |
| `app.state.embeddings_client` / `clustering_client` | `main.py` | Construidos por factories, con `aclose()` en el `AsyncExitStack`. **No se pasan hoy a `build_real_stages`.** |
| Orquestador | `pipeline/orchestrator.py` | `should_skip` omite P3/P4 sin clustering; `skip_remaining` aplica D-29. |
| Catálogo | `pipeline/catalog.py` | P3 y P4 son **bloqueantes** (`blocking=True`). |

### 1.1 Prerrequisito de calidad — atomicidad de P2 (verificar antes de correr documentos reales)

El clustering hereda la calidad de P2. El prompt actual
(`prompts/texts/p2_requirements.md`) pide RF atómicos **pero su ejemplo es compuesto** ("exportar
en PDF **y** CSV"). Antes de pasar documentos reales por P3/P4:

- [ ] Verificar con documentos reales que P2 produce RF atómicos (un comportamiento/salida por RF).
- [x] Si no, mejorar el prompt de la Fase 4 *(hecho: commit `85d580c`, sección "Atomicidad de los RF")*: corregir el ejemplo compuesto y añadir la regla
      *"si una HU describe dos o más comportamientos/salidas independientes, extráelos como RF
      separados"* (con ejemplo "antes → después").
- P4/P5 **no** parten RFs compuestos: asumen atomicidad. Es una mejora de P2, no de la Fase 5.

### 1.2 Verificación rápida de la base

```
python -c "from ai_service.config import Settings; s=Settings(); print(s.embeddings_provider, s.embeddings_model, s.clustering_algorithm)"
pytest tests/test_contracts.py tests/test_contracts_rpc.py -q
```
- `Settings()` importa sin las env vars nuevas (T-F5-01 aún no se aplica): los defaults de la
  Fase 4 deben seguir cargando.
- La suite de contratos (180+) pasa sin regresión antes de empezar.

---

## 2. Pendiente de implementar (sugerencias)

### 2.1 T-F5-01 · Configuración de `P3Config` / `P4Config`

Añadir a `ai_service/config.py` (`Settings`), junto a las `p1_*`/`p2_*` existentes:

```python
# P3 (embeddings)
p3_normalize: bool = True
p3_input_template: str = Field(default="{code}. {description}", min_length=1)
p3_batch_size: int = Field(default=32, gt=0)
p3_max_retries: int = Field(default=2, ge=0)
# P4 (clustering)
p4_metric: str = Field(default="cosine", min_length=1)
p4_min_cluster_size: int = Field(default=2, ge=2)
p4_min_samples: int = Field(default=1, ge=1)
```

- `p4_min_cluster_size` con `ge=2`: HDBSCAN no admite `min_cluster_size < 2` (un cluster de 1 no
  es cluster). Es el **piso mínimo**, no un tamaño forzado (decisión 1).
- `provider` para `EmbeddingModelInfo` **no** va aquí: se pasa aparte al stage desde
  `settings.embeddings_provider` (H-2), sin tocar el contrato `P3Config`.
- Actualizar `.env.example` con las nuevas claves y los defaults resueltos.

### 2.2 T-F5-02 · Caller de `persist_p4_clusters`

**Puerto** (`repositories/pipeline_results.py`): añadir al `Protocol`:

```python
async def persist_p4_clusters(self, generation_id: UUID, payload: dict[str, Any]) -> None:
    """Guarda clusters + asignaciones + RF sin cluster en una transacción. Idempotente."""
    ...
```

**Adaptador Supabase** (`repositories/supabase_pipeline_results.py`): una línea, porque
`_call` y `_ERRORS_BY_SQLSTATE` ya cubren `23502`/`23503`/`23505`/resto:

```python
async def persist_p4_clusters(self, generation_id: UUID, payload: dict[str, Any]) -> None:
    await self._call("persist_p4_clusters", generation_id, payload)
```

**Fake en memoria** (`repositories/in_memory.py`, `InMemoryPipelineResultsRepository`):
replicar la semántica de la RPC (siguiendo el patrón de `persist_p2_requirements`):

- `self.calls.append(("persist_p4_clusters", generation_id))`.
- Idempotencia: `clusters` por `id` (actualiza si existe), `cluster_requirements` por
  `(generation_id, cluster_id, requirement_id)` (no duplica), `unassigned_requirements` por
  `(generation_id, requirement_id)` (no duplica).
- FK: todo `requirement_code` (en `assignments` y en `unassigned_requirement_codes`) debe existir
  en `self._store.requirements[generation_id]`; si no, `InvalidReferenceError`. (La RPC usa
  errcode `23503`.)
- Guardar `similarity_to_centroid` en la fila de `cluster_requirements`.

Sugerencia: el fake puede reusar `self._store.requirements` (ya poblado por P2) para validar los
FK; almacenar clusters/asignaciones en nuevas colecciones del `InMemoryStore`.

### 2.3 T-F5-03 · Cableado de dependencias (DI)

**`pipeline/stages/__init__.py`** — extender `build_real_stages` (hoy recibe `documents`,
`storage`, `extractor`, `llm_client`, `results`):

```python
def build_real_stages(
    settings, *, documents, storage, extractor, llm_client, results,
    embeddings_client, clustering_client,
) -> list[StageBase]:
    ...
    p3 = EmbeddingsStage(embeddings_client=embeddings_client, config=build_p3_config(settings),
                         provider=settings.embeddings_provider)
    p4 = ClusteringStage(clustering_client=clustering_client, config=build_p4_config(settings),
                         results=results)
    # P5–P7 siguen como stubs:
    remaining_stubs = _stubs((ContextStage, GenerationStage, EvaluationStage),
                             settings.pipeline_stub_delay_seconds, settings.pipeline_stub_fail_at_stage)
    return [p1, p2, p3, p4, *remaining_stubs]
```

- `build_p3_config(settings)` → `P3Config(model_name=settings.embeddings_model,
  normalize=settings.p3_normalize, input_template=settings.p3_input_template,
  batch_size=settings.p3_batch_size)`.
- `build_p4_config(settings)` → `P4Config(algorithm=settings.clustering_algorithm,
  metric=settings.p4_metric, params={"min_cluster_size": settings.p4_min_cluster_size,
  "min_samples": settings.p4_min_samples})`.
- Sacar `EmbeddingsStage`/`ClusteringStage` de `PENDING_STUB_STAGE_CLASSES` (pasan a reales);
  conservar `EmbeddingsStubStage`/`ClusteringStubStage` para `build_stub_stages`.

**`main.py`** — pasar los clientes a `build_real_stages` (ya están en `app.state`):

```python
stages = build_real_stages(app_settings, documents=documents_repo, storage=storage,
    extractor=document_extractor, llm_client=llm, results=results_repo,
    embeddings_client=embeddings, clustering_client=clustering)
```

**Tests** — `tests/test_stages_wiring.py` (7 tests) se actualiza: al construir
`build_real_stages` ahora hay que inyectar `embeddings_client` y `clustering_client` (fakes).

### 2.4 T-F5-04 · `EmbeddingsStage.run()` (P3)

Nuevo `pipeline/stages/p3_embeddings.py` (reemplaza el stub; conservar `EmbeddingsStubStage`):

1. `if context.p2_output is None: raise RuntimeError("P3 requiere p2_output")`. Si 0 RF (no
   debería llegar por D-29/`skip_remaining`, defensa en profundidad): devolver `StageResult()` sin
   construir `P3Input` (que exige `min_length=1`).
2. Textos: `config.input_template.format(code=rf.code, description=rf.description)` por RF.
3. Lotes de `config.batch_size`; por lote, `EmbeddingsRequest(texts=..., model=config.model_name,
   input_template=config.input_template, normalize=config.normalize,
   extra={"batch_size": config.batch_size})`.
4. Reintento por lote (análogo a `RequirementsStage._run_batch`): bucle hasta
   `config.max_retries + 1`. Capturar `EmbeddingsError` y reintentar con espera lineal; **pero
   relanzar de inmediato** `EmbeddingsDimensionError` e `EmbeddingsInvalidVectorError` (decisión 3:
   no son transitorios). Agotado → `StageError("EMBEDDINGS_FAILED", retryable=True,
   details={"batch": n})`.
5. Ensamblar `RequirementEmbedding(requirement_code=rf.code, vector=resp.vectors[i])` por lote.
   `EmbeddingModelInfo(provider=self._provider, model_name=resp.model_name,
   model_version=resp.model_version, dimension=resp.dimension, normalized=resp.normalized,
   input_template=config.input_template)`. (`P3Output` valida que todos los vectores tengan la
   misma `dimension` y sean finitos.)
6. `context.p3_output = P3Output(model_info=..., embeddings=...)`. P3 **no persiste** (D-09).
7. Devolver `StageResult(runtime_info={"embedding_model": model_info.model_dump(mode="json"),
   "batch_size": config.batch_size, "batches": n, "retries_used": total, "requirements_count":
   len(rfs)})` — **sin `llm_runs`** (P3 no usa el LLM).

### 2.5 T-F5-05 · `ClusteringStage.run()` (P4)

Nuevo `pipeline/stages/p4_clustering.py` (reemplaza el stub; conservar `ClusteringStubStage`):

1. `if context.p2_output is None or context.p3_output is None: raise RuntimeError(...)`.
2. Construir `P4Input(generation_id, requirements=context.p2_output.requirements,
   embeddings=context.p3_output, config=self._config)` — valida `_embeddings_match` (códigos RF
   ↔ vectores coinciden exactamente).
3. Alinear vectores y códigos en el **mismo orden** (usar el de `p3_output.embeddings`):
   `codes = [e.requirement_code for e in p3_output.embeddings]`,
   `vectors = [e.vector for e in p3_output.embeddings]`.
4. `ClusteringRequest(vectors=tuple(vectors), codes=tuple(codes), metric=config.metric,
   params=config.params)` → `clustering_client.cluster(request)` → `ClusteringResult(labels, ...)`.
5. Mapear labels → clusters (HDBSCAN: label `-1` = ruido):
   - Agrupar códigos por `label` (`label >= 0`).
   - Por cluster: `SemanticCluster(id=uuid4(), label=label, name=f"Cluster {label}" (D-A),
     assignments=tuple(ClusterAssignment(requirement_code=code,
     similarity_to_centroid=<coseno al centroide>)) )`. Calcular el centroide como la media de
     los vectores de los miembros y la similitud coseno de cada miembro al centroide (D-B) — P4
     es la última etapa con los vectores.
   - Códigos con `label == -1` → `unassigned_requirement_codes`.
   - **D-32:** si no hay clusters (todos `-1`) → `clusters=()`, `unassigned=todos`, y un
     `StageWarning(code="INSUFFICIENT_REQUIREMENTS", ...)`; **no es error**.
6. `ClusteringAlgorithmInfo(name=result.algorithm, metric=result.metric,
   params=result.params, embedding_model=p3_output.model_info)` (D-34).
7. `P4Output(clusters=..., unassigned_requirement_codes=..., algorithm_info=...)`. El contrato
   valida labels/ids únicos y que asignados ∩ unassigned = ∅.
8. Persistir: `await self._results.persist_p4_clusters(context.generation_id,
   output.to_rpc_payload())` (captura `PersistenceError` → `StageError(..., retryable=True)`,
   como P2).
9. `context.p4_output = output`. Devolver `StageResult(warnings=..., runtime_info=
   {"algorithm_info": algorithm_info.model_dump(mode="json"), "clusters": len(clusters),
   "unassigned": len(unassigned)})`.
10. Errores: fallo del algoritmo (`ClusteringError`) → `StageError("CLUSTERING_FAILED",
    retryable=True)`.

### 2.6 T-F5-06 · Pruebas

- **P3** (`embeddings_fake`, sin LLM): happy path en batches (respeta `batch_size`), 0 RF →
  `skipped`, NaN/inf → `EmbeddingsInvalidVectorError` (no reintenta), dimensión no uniforme →
  `EmbeddingsDimensionError` (no reintenta), reintento ante `EmbeddingsError` genérico
  transitorio, `extra["batch_size"]` llega al fake, `runtime_info` con `embedding_model`.
- **P4** (`clustering_fake`): happy path con `SemanticCluster` (`name="Cluster {label}"`),
  `similarity_to_centroid` calculado, D-32 (todos `-1` → `unassigned` + aviso, no error), fallo →
  `CLUSTERING_FAILED`, persistencia e idempotencia de `persist_p4_clusters` (fake: reinsertar
  el mismo payload no duplica), errcodes `23502`/`23503`. El fake puede devolver un label `-1`
  solapado para validar el contrato de membresía (R6: el contrato lo permite; HDBSCAN no lo
  produce).
- **Wiring / E2E** (HTTP + fakes): `build_real_stages` con clientes fake → documento produce HU
  + RF + embeddings + clusters persistidos; `clustering_enabled=false` → P3/P4 `skipped`; D-29
  (0 RF) → P3–P7 `skipped` y generación `completed`.
- Regresión: `pytest tests/test_contracts.py tests/test_contracts_rpc.py` sin fallos.

### 2.7 T-F5-07 · Cierre

- Marcar Fase 5 como ✅ en `docs/pipeline_roadmap.md`.
- **Corregir** el roadmap: el puerto `EmbeddingsClient` ya existía (Fase 3) y la RPC
  `persist_p4_clusters` ya estaba desplegada; anotar que solo se añadió el caller del repositorio.
- Generar `cierre_documental_fase5.md`: supuestos, decisiones (las 5 + los hallazgos H-2/H-3/D-A/
  D-B/D-36), advertencias nuevas (R6/D-31 diferido, prerrequisito de atomicidad de P2).

---

## 3. Orden sugerido

```
1.1 Prerrequisito P2 (atomicidad del prompt)   ← verificar antes; si no, mejorar el prompt (Fase 4)
   │
2.1 T-F5-01 (config P3/P4)        ← fija P3Config/P4Config
   │
2.2 T-F5-02 (caller persist_p4_clusters)   ← la RPC ya existe en BD
   │
2.3 T-F5-03 (DI wiring)           ← build_real_stages + main.py + test_stages_wiring
   │
   ├─► 2.4 T-F5-04 (P3 run)   ← provider aparte (H-2); reintentos solo transitorios
   └─► 2.5 T-F5-05 (P4 run)   ← "Cluster {label}"; similarity (D-B); D-32
   │
2.6 T-F5-06 (pruebas)
   │
2.7 T-F5-07 (cierre documental + roadmap)
```

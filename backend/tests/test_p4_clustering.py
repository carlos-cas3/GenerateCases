"""P4 real (clustering) con `FakeClusteringClient` y persistencia en memoria (T-F5-05 / T-F5-06)."""

from typing import Any
from uuid import UUID, uuid4

import pytest
from postgrest.exceptions import APIError

from ai_service.clients.clustering import ClusteringResult
from ai_service.clients.clustering_fake import FakeClusteringClient
from ai_service.core.errors import (
    ClusteringError,
    DuplicateEntryError,
    InvalidReferenceError,
    MissingIdentifierError,
    PersistenceError,
)
from ai_service.pipeline.context import PipelineConfiguration, PipelineContext
from ai_service.pipeline.contracts.p3 import RequirementEmbedding
from ai_service.pipeline.contracts.p4 import P4Config
from ai_service.pipeline.stages import ClusteringStage, StageError
from ai_service.repositories.in_memory import InMemoryPipelineResultsRepository, InMemoryStore
from ai_service.repositories.supabase_pipeline_results import SupabasePipelineResultsRepository
from tests import contract_factories as f

PARAMS = {"min_cluster_size": 2, "min_samples": 1}
CONFIG = P4Config(algorithm="hdbscan", metric="cosine", params=PARAMS)

# RF-001/RF-002 casi iguales, RF-003/RF-004 casi iguales, RF-005 aislado.
VECTORS = {
    "RF-001": (1.0, 0.0, 0.0),
    "RF-002": (1.0, 0.0, 0.0),
    "RF-003": (0.0, 1.0, 0.0),
    "RF-004": (0.0, 0.8, 0.6),
    "RF-005": (0.0, 0.0, 1.0),
}


def _requirements(count: int) -> tuple:
    base = (f.requirement(), f.requirement_2())
    extra = tuple(
        f.requirement(id=uuid4(), code=f"RF-{n:03d}", description=f"El sistema hace la tarea {n}.")
        for n in range(3, count + 1)
    )
    return (base + extra)[:count]


@pytest.fixture
def results(store: InMemoryStore) -> InMemoryPipelineResultsRepository:
    return InMemoryPipelineResultsRepository(store)


async def _context(results: InMemoryPipelineResultsRepository, count: int = 5) -> PipelineContext:
    """Contexto tras P3: HU y RF ya persistidos, vectores en memoria."""
    ctx = PipelineContext(
        generation_id=uuid4(),
        document_id=f.DOCUMENT_ID,
        configuration=PipelineConfiguration(clustering_enabled=True, method_type="llm_pipeline"),
    )
    ctx.p1_output = f.p1_output()
    await results.persist_p1_user_stories(ctx.generation_id, ctx.p1_output.to_rpc_payload())
    ctx.p2_output = f.p2_output().model_copy(update={"requirements": _requirements(count)})
    await results.persist_p2_requirements(ctx.generation_id, ctx.p2_output.to_rpc_payload())
    codes = [rf.code for rf in ctx.p2_output.requirements]
    ctx.p3_output = f.p3_output(
        embeddings=tuple(RequirementEmbedding(requirement_code=c, vector=VECTORS[c]) for c in codes)
    )
    return ctx


def _result(labels: tuple[int, ...]) -> ClusteringResult:
    return ClusteringResult(labels=labels, algorithm="hdbscan", metric="cosine", params={**PARAMS, "algorithm": "generic"})


def _stage(client: FakeClusteringClient, results: Any, config: P4Config = CONFIG) -> ClusteringStage:
    return ClusteringStage(clustering_client=client, config=config, results=results)


async def test_happy_path_builds_and_persists_clusters(results, store: InMemoryStore) -> None:
    client = FakeClusteringClient([_result((0, 0, 1, 1, -1))])
    ctx = await _context(results)

    result = await _stage(client, results).run(ctx)

    request = client.requests[0]
    assert request.codes == ("RF-001", "RF-002", "RF-003", "RF-004", "RF-005")
    assert request.vectors[3] == VECTORS["RF-004"]
    assert (request.metric, request.params) == ("cosine", PARAMS)

    output = ctx.p4_output
    assert output is not None
    assert [(c.label, c.name) for c in output.clusters] == [(0, "Cluster 0"), (1, "Cluster 1")]
    assert [[a.requirement_code for a in c.assignments] for c in output.clusters] == [["RF-001", "RF-002"], ["RF-003", "RF-004"]]
    assert output.unassigned_requirement_codes == ("RF-005",)
    # R6 con HDBSCAN: cada RF en un solo cluster.
    assigned = [a.requirement_code for c in output.clusters for a in c.assignments]
    assert len(assigned) == len(set(assigned))

    # D-B: coseno al centroide. Vectores idénticos → 1.0; RF-003/RF-004 → cos(θ/2) con cos θ = 0.8.
    similarities = {a.requirement_code: a.similarity_to_centroid for c in output.clusters for a in c.assignments}
    assert similarities["RF-001"] == similarities["RF-002"] == 1.0
    assert similarities["RF-003"] == similarities["RF-004"] == pytest.approx(0.948683, abs=1e-6)

    assert output.algorithm_info.embedding_model == ctx.p3_output.model_info
    assert output.algorithm_info.params["algorithm"] == "generic"

    assert [w.code for w in result.warnings] == ["UNASSIGNED_REQUIREMENTS"]
    assert result.warnings[0].details == {"requirement_codes": ["RF-005"]}
    assert result.llm_runs == () and not result.skip_remaining
    assert (result.runtime_info["clusters"], result.runtime_info["unassigned"]) == (2, 1)
    assert result.runtime_info["algorithm_info"]["name"] == "hdbscan"

    gid = ctx.generation_id
    assert results.calls[-1] == ("persist_p4_clusters", gid)
    assert sorted(row["name"] for row in store.clusters[gid].values()) == ["Cluster 0", "Cluster 1"]
    assert {code for (_, code) in store.cluster_requirements[gid]} == {"RF-001", "RF-002", "RF-003", "RF-004"}
    assert all(row["similarity_to_centroid"] is not None for row in store.cluster_requirements[gid].values())
    assert store.unassigned_requirements[gid] == {"RF-005"}


async def test_all_noise_is_insufficient_requirements_not_an_error(results, store: InMemoryStore) -> None:
    """D-32: ningún cluster → todos sin asignar, `completed` con aviso."""
    ctx = await _context(results, count=3)

    result = await _stage(FakeClusteringClient([_result((-1, -1, -1))]), results).run(ctx)

    assert ctx.p4_output.clusters == ()
    assert ctx.p4_output.unassigned_requirement_codes == ("RF-001", "RF-002", "RF-003")
    assert [w.code for w in result.warnings] == ["INSUFFICIENT_REQUIREMENTS"]
    assert store.unassigned_requirements[ctx.generation_id] == {"RF-001", "RF-002", "RF-003"}
    assert store.clusters[ctx.generation_id] == {}


async def test_fewer_requirements_than_min_cluster_size_skip_the_algorithm(results) -> None:
    """D-32 sin llamar al algoritmo: 1 RF < min_cluster_size=2. El fake sin respuestas fallaría si se llamara."""
    client = FakeClusteringClient()
    ctx = await _context(results, count=1)

    result = await _stage(client, results).run(ctx)

    assert client.requests == []
    assert ctx.p4_output.unassigned_requirement_codes == ("RF-001",)
    assert ctx.p4_output.algorithm_info.params == PARAMS
    assert [w.code for w in result.warnings] == ["INSUFFICIENT_REQUIREMENTS"]


async def test_algorithm_failure_is_clustering_failed(results) -> None:
    ctx = await _context(results)
    with pytest.raises(StageError) as exc_info:
        await _stage(FakeClusteringClient([ClusteringError("boom")]), results).run(ctx)
    assert exc_info.value.code == "CLUSTERING_FAILED" and exc_info.value.retryable
    assert ctx.p4_output is None and results.calls[-1][0] == "persist_p2_requirements"


async def test_wrong_number_of_labels_is_clustering_failed(results) -> None:
    ctx = await _context(results)
    with pytest.raises(StageError, match="labels") as exc_info:
        await _stage(FakeClusteringClient([_result((0, 0))]), results).run(ctx)
    assert exc_info.value.code == "CLUSTERING_FAILED"


async def test_embeddings_not_matching_requirements_fail(results) -> None:
    ctx = await _context(results, count=2)
    ctx.p3_output = f.p3_output(embeddings=(RequirementEmbedding(requirement_code="RF-001", vector=(1.0, 0.0, 0.0)),))
    with pytest.raises(StageError) as exc_info:
        await _stage(FakeClusteringClient(), results).run(ctx)
    assert exc_info.value.code == "CLUSTERING_FAILED"


async def test_requires_p3_output(results) -> None:
    ctx = await _context(results)
    ctx.p3_output = None
    with pytest.raises(RuntimeError, match="p3_output"):
        await _stage(FakeClusteringClient(), results).run(ctx)


async def test_persistence_error_becomes_retryable_stage_error(results) -> None:
    """RF no persistidos en la generación → la RPC rechaza la referencia (23503)."""
    ctx = await _context(results)
    ctx.generation_id = uuid4()  # otra generación: sus RF no existen

    with pytest.raises(StageError) as exc_info:
        await _stage(FakeClusteringClient([_result((0, 0, 1, 1, -1))]), results).run(ctx)

    assert exc_info.value.code == InvalidReferenceError.code and exc_info.value.retryable
    assert ctx.p4_output is None


# ------------------------------------------------------- fake de persist_p4_clusters
async def test_fake_persist_p4_clusters_is_idempotent(results, store: InMemoryStore) -> None:
    ctx = await _context(results)
    await _stage(FakeClusteringClient([_result((0, 0, 1, 1, -1))]), results).run(ctx)
    payload = ctx.p4_output.to_rpc_payload()

    await results.persist_p4_clusters(ctx.generation_id, payload)

    gid = ctx.generation_id
    assert len(store.clusters[gid]) == 2
    assert len(store.cluster_requirements[gid]) == 4
    assert store.unassigned_requirements[gid] == {"RF-005"}


async def test_fake_persist_p4_clusters_requires_cluster_id(results) -> None:
    ctx = await _context(results)
    payload = {"clusters": [{"id": None, "name": "Cluster 0", "description": None, "cluster_label": 0, "assignments": []}]}
    with pytest.raises(MissingIdentifierError):
        await results.persist_p4_clusters(ctx.generation_id, payload)


async def test_fake_persist_p4_clusters_rejects_unknown_requirements(results) -> None:
    ctx = await _context(results, count=2)
    with pytest.raises(InvalidReferenceError, match="RF-009"):
        await results.persist_p4_clusters(ctx.generation_id, {"clusters": [], "unassigned_requirement_codes": ["RF-009"]})


# ------------------------------------------- adaptador Supabase: errcode → excepción
class _FailingRpc:
    def __init__(self, code: str | None) -> None:
        self.code = code
        self.calls: list[tuple[str, dict]] = []

    def rpc(self, name: str, params: dict) -> "_FailingRpc":
        self.calls.append((name, params))
        return self

    def execute(self) -> None:
        if self.code is not None:
            raise APIError({"code": self.code, "message": "rechazada", "details": None, "hint": None})


@pytest.mark.parametrize(
    ("sql_code", "error_cls"),
    [
        ("23502", MissingIdentifierError),
        ("23503", InvalidReferenceError),
        ("23505", DuplicateEntryError),
        ("XX000", PersistenceError),
    ],
)
async def test_supabase_persist_p4_clusters_translates_errcodes(sql_code: str, error_cls: type) -> None:
    repo = SupabasePipelineResultsRepository(_FailingRpc(sql_code))  # type: ignore[arg-type]
    with pytest.raises(error_cls) as exc_info:
        await repo.persist_p4_clusters(f.GENERATION_ID, {"clusters": []})
    assert type(exc_info.value) is error_cls
    assert exc_info.value.details["rpc"] == "persist_p4_clusters"


async def test_supabase_persist_p4_clusters_calls_the_rpc() -> None:
    client = _FailingRpc(None)
    payload = {"clusters": [], "unassigned_requirement_codes": ["RF-001"]}
    await SupabasePipelineResultsRepository(client).persist_p4_clusters(UUID(int=1), payload)  # type: ignore[arg-type]
    assert client.calls == [("persist_p4_clusters", {"p_generation_id": str(UUID(int=1)), "p_payload": payload})]

"""Clientes de embeddings y clustering: factories, fakes y adaptadores (sin red ni mocks de librería)."""

import json
import math
import subprocess
import sys
import types
from collections.abc import Callable
from typing import Any

import httpx
import numpy as np
import pytest
from openai import AsyncOpenAI

from ai_service.clients.clustering import ClusteringRequest, ClusteringResult
from ai_service.clients.clustering_factory import ClusteringClientFactory
from ai_service.clients.clustering_fake import FakeClusteringClient
from ai_service.clients.embeddings import EmbeddingsRequest, EmbeddingsResponse, validate_vectors
from ai_service.clients.embeddings_factory import EmbeddingsClientFactory
from ai_service.clients.embeddings_fake import FakeEmbeddingsClient
from ai_service.clients.hdbscan_clustering import HDBSCANClusteringClient
from ai_service.clients.local_embeddings import LocalEmbeddingsClient
from ai_service.clients.openai_embeddings import OpenAIEmbeddingsClient
from ai_service.config import Settings
from ai_service.core.errors import (
    ClusteringError,
    ConfigurationError,
    EmbeddingsDimensionError,
    EmbeddingsError,
    EmbeddingsInvalidVectorError,
)
from ai_service.main import create_app
from tests.conftest import make_settings

Handler = Callable[[httpx.Request], httpx.Response]


# --- helpers (P-4: los fakes reciben objetos completos) --------------------------------------


def embeddings_response(*vectors: tuple[float, ...], model: str = "mini") -> EmbeddingsResponse:
    return EmbeddingsResponse(
        vectors=tuple(vectors), model_name=model, model_version=None, dimension=len(vectors[0]), normalized=True
    )


def clustering_result(*labels: int) -> ClusteringResult:
    return ClusteringResult(labels=tuple(labels), algorithm="hdbscan", metric="euclidean", params={"min_cluster_size": 2})


class FakeSentenceModel:
    """Modelo con la interfaz mínima de `SentenceTransformer` que usa el adaptador local."""

    def __init__(self, vectors: list[list[float]], dimension: int | None = None, error: Exception | None = None) -> None:
        self._vectors = vectors
        self._dimension = dimension if dimension is not None else len(vectors[0])
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def get_sentence_embedding_dimension(self) -> int:
        return self._dimension

    def encode(self, sentences: list[str], **kwargs: Any) -> np.ndarray:
        self.calls.append({"sentences": sentences, **kwargs})
        if self._error is not None:
            raise self._error
        return np.asarray(self._vectors, dtype=np.float32)


def _openai(handler: Handler) -> tuple[list[httpx.Request], OpenAIEmbeddingsClient]:
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    sdk = AsyncOpenAI(api_key="k", max_retries=0, http_client=httpx.AsyncClient(transport=httpx.MockTransport(wrapped)))
    return seen, OpenAIEmbeddingsClient(sdk)


def _openai_body(vectors: list[list[float]], *, reverse: bool = False, model: str = "text-embedding-3-small") -> dict:
    data = [{"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(vectors)]
    if reverse:
        data.reverse()
    return {"object": "list", "data": data, "model": model, "usage": {"prompt_tokens": 1, "total_tokens": 1}}


# --- factories ------------------------------------------------------------------------------


def test_embeddings_factory_builds_local_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """La rama local construye el modelo con `EMBEDDINGS_MODEL` (módulo sustituido: sin torch)."""
    built: list[str] = []
    stub = types.ModuleType("sentence_transformers")
    stub.SentenceTransformer = lambda name: built.append(name) or FakeSentenceModel([[1.0]])  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", stub)

    client = EmbeddingsClientFactory.create(make_settings(embeddings_provider="local", embeddings_model="mini"))
    assert isinstance(client, LocalEmbeddingsClient)
    assert built == ["mini"]


def test_embeddings_factory_builds_openai_client() -> None:
    client = EmbeddingsClientFactory.create(make_settings(embeddings_provider="openai", embeddings_api_key="k"))
    assert isinstance(client, OpenAIEmbeddingsClient)


def test_embeddings_factory_requires_api_key_for_openai() -> None:
    with pytest.raises(ConfigurationError, match="EMBEDDINGS_API_KEY"):
        EmbeddingsClientFactory.create(make_settings(embeddings_provider="openai", embeddings_api_key=""))


def test_embeddings_factory_rejects_unknown_provider() -> None:
    with pytest.raises(ConfigurationError, match="local, openai"):
        EmbeddingsClientFactory.create(Settings.model_construct(embeddings_provider="cohere"))


def test_clustering_factory_builds_hdbscan() -> None:
    assert isinstance(ClusteringClientFactory.create(make_settings()), HDBSCANClusteringClient)


def test_clustering_factory_rejects_unknown_algorithm() -> None:
    with pytest.raises(ConfigurationError, match="hdbscan"):
        ClusteringClientFactory.create(Settings.model_construct(clustering_algorithm="kmeans"))


@pytest.mark.parametrize("field, value", [("embeddings_provider", "cohere"), ("clustering_algorithm", "kmeans")])
def test_settings_reject_unknown_values(field: str, value: str) -> None:
    with pytest.raises(ValueError):
        make_settings(**{field: value})


def test_factory_imports_are_lazy() -> None:
    """R-FA-3: importar las factories no carga adaptadores ni librerías de proveedor."""
    code = (
        "import sys; import ai_service.clients.embeddings_factory, ai_service.clients.clustering_factory; "
        "names = ('local_embeddings', 'openai_embeddings', 'hdbscan_clustering'); "
        "mods = [m for m in sys.modules if m.rsplit('.', 1)[-1] in names "
        "or m.split('.')[0] in ('sentence_transformers', 'hdbscan', 'openai')]; print(mods)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"


# --- fakes ----------------------------------------------------------------------------------


async def test_fake_embeddings_returns_programmed_responses_in_order() -> None:
    response = embeddings_response((1.0, 0.0))
    fake = FakeEmbeddingsClient([response, EmbeddingsError()])
    request = EmbeddingsRequest(texts=("a",), model="mini")

    assert await fake.embed(request) is response
    with pytest.raises(EmbeddingsError):
        await fake.embed(request)
    with pytest.raises(AssertionError):
        await fake.embed(request)
    assert fake.requests == [request] * 3
    await fake.aclose()
    assert fake.closed


async def test_fake_clustering_returns_programmed_results_in_order() -> None:
    result = clustering_result(0, -1)
    fake = FakeClusteringClient([result, ClusteringError()])
    request = ClusteringRequest(vectors=((0.0,), (1.0,)), codes=("RF-001", "RF-002"), metric="euclidean")

    assert await fake.cluster(request) is result
    with pytest.raises(ClusteringError):
        await fake.cluster(request)
    assert fake.requests == [request, request]


# --- validación de vectores -----------------------------------------------------------------


def test_validate_vectors_returns_dimension() -> None:
    assert validate_vectors([(1.0, 2.0), (3.0, 4.0)]) == 2
    assert validate_vectors([], 768) == 768


def test_validate_vectors_rejects_wrong_dimension_with_details() -> None:
    with pytest.raises(EmbeddingsDimensionError) as exc_info:
        validate_vectors([(1.0, 2.0), (3.0,)])
    assert exc_info.value.details == {"expected": 2, "received": 1, "vector_index": 1}
    assert exc_info.value.code == "EMBEDDING_DIMENSION_MISMATCH"


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_validate_vectors_rejects_non_finite_values(bad: float) -> None:
    with pytest.raises(EmbeddingsInvalidVectorError) as exc_info:
        validate_vectors([(1.0, 2.0), (bad, 0.0)])
    assert exc_info.value.details["vector_index"] == 1
    assert exc_info.value.code == "EMBEDDING_INVALID_VECTOR"


# --- adaptador local ------------------------------------------------------------------------


async def test_local_translates_request_and_response() -> None:
    model = FakeSentenceModel([[0.6, 0.8], [1.0, 0.0]])
    client = LocalEmbeddingsClient(model, "mini")

    response = await client.embed(
        EmbeddingsRequest(texts=("RF uno", "RF dos"), model="mini", normalize=True, extra={"batch_size": 8})
    )

    assert response.vectors == ((pytest.approx(0.6), pytest.approx(0.8)), (1.0, 0.0))
    assert (response.model_name, response.dimension, response.normalized) == ("mini", 2, True)
    assert model.calls[0]["sentences"] == ["RF uno", "RF dos"]
    assert model.calls[0]["batch_size"] == 8 and model.calls[0]["normalize_embeddings"] is True


async def test_local_rejects_a_model_other_than_the_loaded_one() -> None:
    with pytest.raises(EmbeddingsError, match="no es el cargado"):
        await LocalEmbeddingsClient(FakeSentenceModel([[1.0]]), "mini").embed(EmbeddingsRequest(texts=("a",), model="otro"))


async def test_local_translates_errors() -> None:
    request = EmbeddingsRequest(texts=("a",), model="mini")
    with pytest.raises(EmbeddingsError) as exc_info:
        await LocalEmbeddingsClient(FakeSentenceModel([[1.0]], error=RuntimeError("CUDA")), "mini").embed(request)
    assert type(exc_info.value) is EmbeddingsError

    with pytest.raises(EmbeddingsDimensionError):
        await LocalEmbeddingsClient(FakeSentenceModel([[1.0, 2.0]], dimension=768), "mini").embed(request)
    with pytest.raises(EmbeddingsInvalidVectorError):
        await LocalEmbeddingsClient(FakeSentenceModel([[math.nan, 1.0]]), "mini").embed(request)


# --- adaptador OpenAI -----------------------------------------------------------------------


async def test_openai_translates_request_and_orders_by_index() -> None:
    seen, client = _openai(lambda r: httpx.Response(200, json=_openai_body([[3.0, 4.0], [1.0, 0.0]], reverse=True)))

    response = await client.embed(
        EmbeddingsRequest(texts=("a", "b"), model="text-embedding-3-small", normalize=True, extra={"dimensions": 2})
    )

    body = json.loads(seen[0].content)
    assert body["model"] == "text-embedding-3-small" and body["input"] == ["a", "b"] and body["dimensions"] == 2
    assert response.vectors == ((pytest.approx(0.6), pytest.approx(0.8)), (1.0, 0.0))
    assert (response.dimension, response.normalized) == (2, True)


async def test_openai_splits_requests_by_batch_size() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        texts = json.loads(request.content)["input"]
        return httpx.Response(200, json=_openai_body([[float(len(t)), 1.0] for t in texts]))

    seen, client = _openai(handler)
    response = await client.embed(
        EmbeddingsRequest(texts=("a", "bb", "ccc"), model="m", normalize=False, extra={"batch_size": 2})
    )

    assert [json.loads(r.content)["input"] for r in seen] == [["a", "bb"], ["ccc"]]
    assert "batch_size" not in json.loads(seen[0].content)
    assert response.vectors == ((1.0, 1.0), (2.0, 1.0), (3.0, 1.0))


@pytest.mark.parametrize(
    "response, expected",
    [
        (httpx.Response(429, json={"error": {"message": "slow down", "type": "rate_limit"}}), EmbeddingsError),
        (httpx.Response(500, json={"error": {"message": "boom"}}), EmbeddingsError),
        (httpx.Response(200, json=_openai_body([[1.0, 2.0], [1.0]])), EmbeddingsDimensionError),
        (httpx.Response(200, json=_openai_body([[1.0, "NaN"]])), EmbeddingsInvalidVectorError),
    ],
)
async def test_openai_translates_errors(response: httpx.Response, expected: type[EmbeddingsError]) -> None:
    _, client = _openai(lambda r: response)
    texts = tuple(str(i) for i in range(len(json.loads(response.content).get("data", [None]))))
    with pytest.raises(expected):
        await client.embed(EmbeddingsRequest(texts=texts or ("a",), model="m"))


async def test_openai_rejects_a_vector_count_mismatch() -> None:
    _, client = _openai(lambda r: httpx.Response(200, json=_openai_body([[1.0]])))
    with pytest.raises(EmbeddingsError, match="número de vectores"):
        await client.embed(EmbeddingsRequest(texts=("a", "b"), model="m"))


# --- adaptador HDBSCAN ----------------------------------------------------------------------


def _two_groups_and_an_outlier() -> ClusteringRequest:
    group_a = [(0.0, 0.0), (0.1, 0.0), (0.0, 0.1), (0.1, 0.1)]
    group_b = [(10.0, 10.0), (10.1, 10.0), (10.0, 10.1), (10.1, 10.1)]
    vectors = (*group_a, *group_b, (50.0, -50.0))
    codes = tuple(f"RF-{i:03d}" for i in range(1, len(vectors) + 1))
    return ClusteringRequest(vectors=vectors, codes=codes, metric="euclidean", params={"min_cluster_size": 3})


async def test_hdbscan_groups_vectors_and_marks_outliers() -> None:
    result = await HDBSCANClusteringClient().cluster(_two_groups_and_an_outlier())

    labels = result.labels
    assert len(set(labels[:4])) == 1 and len(set(labels[4:8])) == 1
    assert labels[0] != labels[4] and -1 not in labels[:8]
    assert labels[8] == -1
    assert (result.algorithm, result.metric) == ("hdbscan", "euclidean")


async def test_hdbscan_reports_effective_params_not_only_requested_ones() -> None:
    result = await HDBSCANClusteringClient().cluster(_two_groups_and_an_outlier())
    assert result.params["min_cluster_size"] == 3
    assert "min_samples" in result.params and "cluster_selection_method" in result.params
    json.dumps(result.params, allow_nan=False)  # jsonb no admite Infinity/NaN (runtime_info de P4)


async def test_hdbscan_supports_cosine_metric() -> None:
    request = ClusteringRequest(
        vectors=((1.0, 0.0), (0.99, 0.01), (0.98, 0.02), (0.0, 1.0), (0.01, 0.99), (0.02, 0.98)),
        codes=tuple(f"RF-{i:03d}" for i in range(1, 7)),
        metric="cosine",
        params={"min_cluster_size": 2},
    )
    result = await HDBSCANClusteringClient().cluster(request)
    assert result.labels[0] == result.labels[1] != result.labels[3] == result.labels[4]
    assert result.params["algorithm"] == "generic"


async def test_hdbscan_translates_errors() -> None:
    request = _two_groups_and_an_outlier()
    with pytest.raises(ClusteringError) as exc_info:
        await HDBSCANClusteringClient().cluster(
            ClusteringRequest(vectors=request.vectors, codes=request.codes, metric="euclidean", params={"min_cluster_size": 0})
        )
    assert exc_info.value.code == "CLUSTERING_FAILED"

    with pytest.raises(ClusteringError, match="no coincide"):
        await HDBSCANClusteringClient().cluster(
            ClusteringRequest(vectors=request.vectors, codes=request.codes[:2], metric="euclidean")
        )


async def test_hdbscan_with_no_vectors_returns_no_labels() -> None:
    result = await HDBSCANClusteringClient().cluster(ClusteringRequest(vectors=(), codes=(), metric="euclidean"))
    assert result.labels == ()


# --- create_app -----------------------------------------------------------------------------


def test_injected_clients_are_exposed_and_not_closed(client: Any) -> None:
    state = client.app.state
    assert isinstance(state.embeddings_client, FakeEmbeddingsClient)
    assert isinstance(state.clustering_client, FakeClusteringClient)
    assert not state.embeddings_client.closed and not state.clustering_client.closed


def test_factory_built_clients_are_closed_on_shutdown(store: Any) -> None:
    from fastapi.testclient import TestClient

    from ai_service.clients.extractor_fake import FakeDocumentExtractor
    from ai_service.clients.llm_fake import FakeLlmClient
    from ai_service.repositories.in_memory import InMemoryDocumentsRepository, InMemoryGenerationsRepository
    from tests.factories import FakeDocumentStorage

    app = create_app(
        make_settings(embeddings_provider="openai", embeddings_api_key="k"),
        generations_repository=InMemoryGenerationsRepository(store),
        documents_repository=InMemoryDocumentsRepository(store),
        documents_storage=FakeDocumentStorage(),
        llm_client=FakeLlmClient(),
        extractor=FakeDocumentExtractor(),
    )
    with TestClient(app):
        embeddings = app.state.embeddings_client
        assert isinstance(embeddings, OpenAIEmbeddingsClient)
        assert isinstance(app.state.clustering_client, HDBSCANClusteringClient)
        assert not embeddings._client.is_closed()
    assert embeddings._client.is_closed()


def test_app_startup_fails_without_embeddings_configuration(store: Any) -> None:
    from fastapi.testclient import TestClient

    from ai_service.clients.llm_fake import FakeLlmClient
    from ai_service.repositories.in_memory import InMemoryDocumentsRepository, InMemoryGenerationsRepository
    from tests.factories import FakeDocumentStorage

    llm = FakeLlmClient()
    app = create_app(
        make_settings(embeddings_provider="openai", embeddings_api_key=""),
        generations_repository=InMemoryGenerationsRepository(store),
        documents_repository=InMemoryDocumentsRepository(store),
        documents_storage=FakeDocumentStorage(),
        llm_client=llm,
    )
    with pytest.raises(ConfigurationError, match="EMBEDDINGS_API_KEY"), TestClient(app):
        pass
    assert llm.closed is False  # inyectado: no lo cierra la app

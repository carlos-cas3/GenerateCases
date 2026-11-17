"""Cableado de P1–P6 reales (T-F4-04, T-F5-03, T-F6-02, T-F7-07) y flujo HTTP extremo a extremo con fakes."""

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ai_service.clients.clustering import ClusteringResult
from ai_service.clients.clustering_fake import FakeClusteringClient
from ai_service.clients.embeddings import EmbeddingsResponse
from ai_service.clients.embeddings_fake import FakeEmbeddingsClient
from ai_service.clients.extractor_fake import FakeDocumentExtractor
from ai_service.clients.llm_fake import FakeLlmClient
from ai_service.core.errors import ClusteringError, ConfigurationError
from ai_service.main import create_app
from ai_service.pipeline.stages import (
    ClusteringStage,
    ContextStage,
    EmbeddingsStage,
    GenerationStage,
    NormalizeStage,
    RequirementsStage,
    StubStage,
    build_p1_config,
    build_p2_config,
    build_p3_config,
    build_p4_config,
    build_p5_config,
    build_p6_config,
    build_real_stages,
    build_stub_stages,
)
from ai_service.repositories.in_memory import (
    InMemoryDocumentsRepository,
    InMemoryGenerationsRepository,
    InMemoryPipelineResultsRepository,
    InMemoryStore,
)
from tests.conftest import DOCUMENT_ID, DOCUMENT_NAME, make_settings
from tests.factories import FakeDocumentStorage

URL = "/api/v1/generations"

DOCUMENT = """## Iniciar sesión
Como usuario, quiero iniciar sesión, para acceder a mi panel.

### Criterios de aceptación
- Bloquear tras 3 intentos.

## Historia corporativa
La empresa se fundó en 2010.
"""


def _llm_answer(requirements: list[dict[str, Any]]) -> str:
    return json.dumps(
        {
            "classifications": [
                {"user_story_code": "HU-001", "category": "candidata_funcional", "rationale": "Acceso al sistema."}
            ],
            "requirements": requirements,
        }
    )


RF = {"description": "El sistema permite iniciar sesión.", "source_text": "quiero iniciar sesión", "user_story_codes": ["HU-001"]}
RF_LOCK = {
    "description": "El sistema bloquea la cuenta tras 3 intentos.",
    "source_text": "Bloquear tras 3 intentos.",
    "user_story_codes": ["HU-001"],
}


def _p6_answer(*requirement_codes: tuple[str, ...]) -> str:
    """Respuesta del LLM de P6: un caso por tupla de RF enlazados."""
    return json.dumps(
        {
            "test_cases": [
                {
                    "title": f"Caso {number}",
                    "steps": [{"step_number": 1, "action": "Ejecutar la acción"}],
                    "expected_result": "El sistema responde según el requisito.",
                    "requirement_codes": list(codes),
                }
                for number, codes in enumerate(requirement_codes, start=1)
            ]
        }
    )


def _embeddings(count: int) -> EmbeddingsResponse:
    return EmbeddingsResponse(
        vectors=tuple((1.0, float(i), 0.0) for i in range(count)),
        model_name="mini",
        model_version=None,
        dimension=3,
        normalized=True,
    )


def _clusters(labels: tuple[int, ...]) -> ClusteringResult:
    return ClusteringResult(labels=labels, algorithm="hdbscan", metric="cosine", params={"min_cluster_size": 2})


def test_build_p2_config_requires_llm_model() -> None:
    with pytest.raises(ConfigurationError, match="LLM_MODEL"):
        build_p2_config(make_settings(llm_model=None))


def test_build_configs_from_settings() -> None:
    settings = make_settings(llm_model="gpt-x", llm_provider="openai", p2_max_stories_per_call=3, p2_max_retries=1)
    p1 = build_p1_config(settings)
    p2 = build_p2_config(settings)

    assert (p1.rules_version, p1.language, p1.story_delimiter_pattern, p1.max_story_chars) == ("v1", "es", r"^##\s+.+$", 5000)
    assert (p2.llm.provider, p2.llm.model, p2.max_stories_per_call, p2.max_retries, p2.prompt_version) == (
        "openai", "gpt-x", 3, 1, "v1",
    )


def test_llm_settings_defaults() -> None:
    s = make_settings()
    assert (s.llm_num_ctx, s.llm_think, s.llm_temperature) == (16384, False, 0.0)


def test_build_p2_config_passes_ollama_parameters() -> None:
    settings = make_settings(llm_model="qwen", llm_provider="ollama", llm_num_ctx=8192, llm_think=True, llm_temperature=0.2)
    assert build_p2_config(settings).llm.parameters == {"temperature": 0.2, "num_ctx": 8192, "think": True}


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_build_p2_config_omits_ollama_only_parameters(provider: str) -> None:
    settings = make_settings(llm_model="m", llm_provider=provider)
    assert build_p2_config(settings).llm.parameters == {"temperature": 0.0}


def test_build_p3_and_p4_configs_from_settings() -> None:
    settings = make_settings(
        embeddings_model="mpnet", p3_normalize=False, p3_input_template="{description}", p3_batch_size=8,
        p4_metric="euclidean", p4_min_cluster_size=3, p4_min_samples=2,
    )
    p3 = build_p3_config(settings)
    p4 = build_p4_config(settings)

    assert (p3.model_name, p3.normalize, p3.input_template, p3.batch_size) == ("mpnet", False, "{description}", 8)
    assert (p4.algorithm, p4.metric, p4.params) == ("hdbscan", "euclidean", {"min_cluster_size": 3, "min_samples": 2})


def test_build_p5_config_from_settings() -> None:
    defaults = build_p5_config(make_settings())
    assert (defaults.max_tokens_per_unit, defaults.instructions_version, defaults.include_prerequisites) == (8000, "v1", False)

    custom = build_p5_config(
        make_settings(p5_max_tokens_per_unit=1200, p5_instructions_version="v2", p5_include_prerequisites=True)
    )
    assert (custom.max_tokens_per_unit, custom.instructions_version, custom.include_prerequisites) == (1200, "v2", True)


def test_build_p6_config_from_settings() -> None:
    defaults = build_p6_config(make_settings(llm_model="m", llm_provider="ollama"))
    assert (defaults.prompt_version, defaults.max_retries, defaults.failure_threshold) == ("v2", 1, 0.0)
    assert (defaults.max_cases_multiplier, defaults.max_cases_absolute, defaults.on_unit_failure) == (3, 50, "continue")
    assert (defaults.llm.provider, defaults.llm.model) == ("ollama", "m")
    assert defaults.llm.parameters == {"temperature": 0.0, "num_ctx": 16384, "think": False}

    custom = build_p6_config(
        make_settings(
            llm_model="m", p6_prompt_version="v9", p6_max_retries=0, p6_failure_threshold=0.5,
            p6_max_cases_multiplier=2, p6_max_cases_absolute=10,
        )
    )
    assert (custom.prompt_version, custom.max_retries, custom.failure_threshold) == ("v9", 0, 0.5)
    assert (custom.max_cases_multiplier, custom.max_cases_absolute) == (2, 10)


def test_build_p6_config_requires_llm_model() -> None:
    with pytest.raises(ConfigurationError, match="LLM_MODEL"):
        build_p6_config(make_settings(llm_model=None))


@pytest.mark.parametrize(
    "overrides",
    [{"p6_failure_threshold": 1.1}, {"p6_failure_threshold": -0.1}, {"p6_max_retries": -1},
     {"p6_max_cases_multiplier": 0}, {"p6_max_cases_absolute": 0}, {"p6_prompt_version": ""}],
)
def test_p6_settings_reject_invalid_values(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        make_settings(**overrides)


def test_p5_settings_reject_invalid_values() -> None:
    with pytest.raises(ValueError):
        make_settings(p5_max_tokens_per_unit=0)
    with pytest.raises(ValueError):
        make_settings(p5_instructions_version="")


def test_build_real_stages_replaces_p1_to_p6(store: InMemoryStore) -> None:
    stages = build_real_stages(
        make_settings(llm_model="m"),
        documents=InMemoryDocumentsRepository(store),
        storage=FakeDocumentStorage(),
        extractor=FakeDocumentExtractor(),
        llm_client=FakeLlmClient(),
        results=InMemoryPipelineResultsRepository(store),
        embeddings_client=FakeEmbeddingsClient(),
        clustering_client=FakeClusteringClient(),
    )

    assert [s.key.value for s in stages] == ["p1", "p2", "p3", "p4", "p5", "p6", "p7"]
    real = (NormalizeStage, RequirementsStage, EmbeddingsStage, ClusteringStage, ContextStage, GenerationStage)
    for stage, cls in zip(stages[:6], real, strict=True):
        assert isinstance(stage, cls) and not isinstance(stage, StubStage)
    assert all(isinstance(s, StubStage) for s in stages[6:])
    assert stages[2].requires_clustering and stages[3].requires_clustering


def test_stub_stages_keep_all_seven_simulated() -> None:
    stages = build_stub_stages(0)
    assert [s.key.value for s in stages] == ["p1", "p2", "p3", "p4", "p5", "p6", "p7"]
    assert all(isinstance(s, StubStage) for s in stages)
    assert stages[2].requires_clustering and stages[3].requires_clustering


def test_real_mode_without_llm_model_does_not_start(store: InMemoryStore) -> None:
    app = create_app(
        make_settings(pipeline_stages="real", llm_model=None),
        generations_repository=InMemoryGenerationsRepository(store),
        documents_repository=InMemoryDocumentsRepository(store),
        documents_storage=FakeDocumentStorage(),
        pipeline_results_repository=InMemoryPipelineResultsRepository(store),
        llm_client=FakeLlmClient(),
        embeddings_client=FakeEmbeddingsClient(),
        clustering_client=FakeClusteringClient(),
        extractor=FakeDocumentExtractor(),
    )
    with pytest.raises(ConfigurationError), TestClient(app):
        pass


@pytest.fixture
def real_client_factory(store: InMemoryStore) -> Iterator[Any]:
    opened: list[TestClient] = []
    storage = FakeDocumentStorage(objects={f"{DOCUMENT_ID}/{DOCUMENT_NAME}": DOCUMENT.encode("utf-8")})

    def factory(
        llm_answers: list[Any], embeddings: Any = (), clusterings: Any = (), **settings: Any
    ) -> TestClient:
        app = create_app(
            make_settings(pipeline_stages="real", llm_model="modelo-x", **settings),
            generations_repository=InMemoryGenerationsRepository(store),
            documents_repository=InMemoryDocumentsRepository(store),
            documents_storage=storage,
            pipeline_results_repository=InMemoryPipelineResultsRepository(store),
            llm_client=FakeLlmClient(llm_answers),
            embeddings_client=FakeEmbeddingsClient(embeddings),
            clustering_client=FakeClusteringClient(clusterings),
            extractor=FakeDocumentExtractor([DOCUMENT]),
        )
        client = TestClient(app)
        client.__enter__()
        opened.append(client)
        return client

    yield factory
    for client in opened:
        client.__exit__(None, None, None)


def _stages(body: dict) -> dict[str, dict]:
    return {stage["key"]: stage for stage in body["stages"]}


def test_document_produces_stories_requirements_and_clusters(real_client_factory, store: InMemoryStore) -> None:
    """Fases 5–7 extremo a extremo: HU, RF, clusters y casos de prueba persistidos (by_cluster)."""
    client = real_client_factory(
        [_llm_answer([RF, RF_LOCK]), _p6_answer(("RF-001",), ("RF-002",), ("RF-001", "RF-002"))],
        [_embeddings(2)],
        [_clusters((0, 0))],
    )
    generation_id = client.post(URL, json={"document_id": str(DOCUMENT_ID)}).json()["id"]

    body = client.get(f"{URL}/{generation_id}").json()

    assert body["status"] == "completed", body
    stages = _stages(body)
    assert all(stages[k]["status"] == "completed" for k in ("p1", "p2", "p3", "p4", "p5", "p6", "p7"))
    assert stages["p1"]["llm_runs"] == []
    assert [w["code"] for w in stages["p1"]["warnings"]] == ["UNRESOLVED_FRAGMENTS"]
    assert stages["p1"]["runtime_info"]["stories_identified"] == 1
    assert [(r["model"], r["attempts"]) for r in stages["p2"]["llm_runs"]] == [("modelo-x", 1)]
    assert stages["p2"]["runtime_info"]["requirements_count"] == 2
    assert stages["p3"]["llm_runs"] == []
    assert stages["p3"]["runtime_info"]["embedding_model"]["provider"] == "local"
    assert stages["p3"]["runtime_info"]["embedding_model"]["input_template"] == "{description}"
    assert stages["p4"]["warnings"] == []
    assert stages["p4"]["runtime_info"]["clusters"] == 1
    assert stages["p4"]["runtime_info"]["algorithm_info"]["embedding_model"]["model_name"] == "mini"

    gid = next(iter(store.user_stories))
    assert str(gid) == generation_id
    assert store.user_stories[gid]["HU-001"]["classification"] == "candidata_funcional"
    assert store.user_stories[gid]["HU-001"]["goal"] == "acceder a mi panel"
    assert list(store.requirements[gid]) == ["RF-001", "RF-002"]
    assert [row["name"] for row in store.clusters[gid].values()] == ["Cluster 0"]
    assert {code for (_, code) in store.cluster_requirements[gid]} == {"RF-001", "RF-002"}
    assert store.unassigned_requirements[gid] == set()
    # P5 (Fase 6): una unidad por cluster, sin persistir nada (D-12).
    assert stages["p5"]["warnings"] == []
    assert stages["p5"]["runtime_info"]["strategy"] == "by_cluster"
    assert stages["p5"]["runtime_info"]["units"] == 1
    assert stages["p5"]["runtime_info"]["requirements_covered"] == 2
    # P6 (Fase 7): una llamada por unidad, CP globales y persistidos; summary poblado (D-F7-8).
    assert stages["p6"]["warnings"] == []
    assert stages["p6"]["runtime_info"]["strategy"] == "by_cluster"
    assert stages["p6"]["runtime_info"]["prompt_version"] == "contexto@v2"
    assert stages["p6"]["runtime_info"]["test_cases_count"] == 3
    assert [(r["unit_id"], r["attempts"]) for r in stages["p6"]["llm_runs"]] == [("U-001", 1)]
    assert list(store.test_cases[gid]) == ["CP-001", "CP-002", "CP-003"]
    assert store.test_cases[gid]["CP-003"]["requirement_codes"] == ["RF-001", "RF-002"]
    assert body["summary"] == {
        "user_stories_count": 1,
        "requirements_count": 2,
        "clusters_count": 1,
        "test_cases_count": 3,
        "test_cases_failed_units": 0,
    }


def test_without_clustering_p3_and_p4_are_skipped(real_client_factory, store: InMemoryStore) -> None:
    client = real_client_factory([_llm_answer([RF]), _p6_answer(("RF-001",), ("RF-001",))])
    generation_id = client.post(
        URL, json={"document_id": str(DOCUMENT_ID), "configuration": {"semantic_clustering_enabled": False}}
    ).json()["id"]

    body = client.get(f"{URL}/{generation_id}").json()

    assert body["status"] == "completed", body
    stages = _stages(body)
    assert stages["p3"]["status"] == stages["p4"]["status"] == "skipped"
    assert all(stages[k]["status"] == "completed" for k in ("p1", "p2", "p5", "p6", "p7"))
    assert store.clusters == {}
    assert stages["p5"]["runtime_info"]["strategy"] == "by_user_story"
    assert stages["p5"]["runtime_info"]["units"] == 1
    assert stages["p6"]["runtime_info"]["strategy"] == "by_user_story"
    assert stages["p6"]["runtime_info"]["prompt_version"] == "contexto_sin_clustering@v2"
    gid = next(iter(store.test_cases))
    assert list(store.test_cases[gid]) == ["CP-001", "CP-002"]
    assert body["summary"] == {
        "user_stories_count": 1,
        "requirements_count": 1,
        "clusters_count": 0,
        "test_cases_count": 2,
        "test_cases_failed_units": 0,
    }


def test_all_p6_units_failing_with_zero_threshold_fails_generation(real_client_factory, store: InMemoryStore) -> None:
    """D-F7-2 extremo a extremo: la única unidad falla tras reintentar y el umbral 0.0 hace fallar la generación."""
    client = real_client_factory([_llm_answer([RF]), "no json", "no json"])
    generation_id = client.post(
        URL, json={"document_id": str(DOCUMENT_ID), "configuration": {"semantic_clustering_enabled": False}}
    ).json()["id"]

    body = client.get(f"{URL}/{generation_id}").json()

    assert body["status"] == "failed"
    stages = _stages(body)
    assert stages["p6"]["status"] == "failed"
    assert stages["p6"]["error_code"] == "GENERATION_THRESHOLD_EXCEEDED"
    assert stages["p7"]["status"] == "pending"
    assert body["summary"] is None
    assert store.test_cases == {}


def test_failed_unit_below_threshold_completes_with_warning(real_client_factory, store: InMemoryStore) -> None:
    """D-F7-2: con umbral 1.0 la generación completa aunque la unidad falle; el summary lo refleja."""
    client = real_client_factory([_llm_answer([RF]), "no json", "no json"], p6_failure_threshold=1.0)
    generation_id = client.post(
        URL, json={"document_id": str(DOCUMENT_ID), "configuration": {"semantic_clustering_enabled": False}}
    ).json()["id"]

    body = client.get(f"{URL}/{generation_id}").json()

    assert body["status"] == "completed", body
    stages = _stages(body)
    codes = [w["code"] for w in stages["p6"]["warnings"]]
    assert codes == ["UNIT_GENERATION_FAILED", "BATCH_RETRIED", "UNCOVERED_REQUIREMENTS"]
    assert body["summary"]["test_cases_count"] == 0
    assert body["summary"]["test_cases_failed_units"] == 1


def test_single_requirement_completes_with_insufficient_requirements(real_client_factory, store: InMemoryStore) -> None:
    """D-32 extremo a extremo: 1 RF → sin clusters, P4 `completed` con aviso, generación `completed`."""
    client = real_client_factory([_llm_answer([RF])], [_embeddings(1)])
    generation_id = client.post(URL, json={"document_id": str(DOCUMENT_ID)}).json()["id"]

    body = client.get(f"{URL}/{generation_id}").json()

    assert body["status"] == "completed", body
    stages = _stages(body)
    assert stages["p4"]["status"] == "completed"
    assert [w["code"] for w in stages["p4"]["warnings"]] == ["INSUFFICIENT_REQUIREMENTS"]
    gid = next(iter(store.unassigned_requirements))
    assert store.unassigned_requirements[gid] == {"RF-001"}
    # D-F6-3: el RF sin cluster no forma unidad; P5 avisa y la generación sigue `completed`.
    assert stages["p5"]["status"] == "completed"
    assert [w["code"] for w in stages["p5"]["warnings"]] == ["UNASSIGNED_REQUIREMENTS"]
    assert stages["p5"]["runtime_info"]["units"] == 0


def test_clustering_failure_fails_generation_at_p4(real_client_factory) -> None:
    client = real_client_factory([_llm_answer([RF, RF_LOCK])], [_embeddings(2)], [ClusteringError("boom")])
    generation_id = client.post(URL, json={"document_id": str(DOCUMENT_ID)}).json()["id"]

    body = client.get(f"{URL}/{generation_id}").json()

    assert body["status"] == "failed"
    stages = _stages(body)
    assert stages["p3"]["status"] == "completed"
    assert stages["p4"]["status"] == "failed" and stages["p4"]["error_code"] == "CLUSTERING_FAILED"
    assert all(stages[k]["status"] == "pending" for k in ("p5", "p6", "p7"))


def test_zero_requirements_completes_with_remaining_stages_skipped(real_client_factory) -> None:
    """D-29 extremo a extremo: 0 RF → P3–P7 `skipped` y generación `completed`."""
    client = real_client_factory([_llm_answer([])])
    generation_id = client.post(URL, json={"document_id": str(DOCUMENT_ID)}).json()["id"]

    body = client.get(f"{URL}/{generation_id}").json()

    assert body["status"] == "completed", body
    stages = _stages(body)
    assert stages["p1"]["status"] == stages["p2"]["status"] == "completed"
    assert [w["code"] for w in stages["p2"]["warnings"]] == ["NO_REQUIREMENTS_EXTRACTED", "CANDIDATE_WITHOUT_REQUIREMENTS"]
    assert all(stages[k]["status"] == "skipped" for k in ("p3", "p4", "p5", "p6", "p7"))


def test_invalid_llm_output_fails_generation_at_p2(real_client_factory) -> None:
    client = real_client_factory(["no json"] * 3)
    generation_id = client.post(URL, json={"document_id": str(DOCUMENT_ID)}).json()["id"]

    body = client.get(f"{URL}/{generation_id}").json()

    assert body["status"] == "failed"
    stages = _stages(body)
    assert stages["p1"]["status"] == "completed"
    assert stages["p2"]["status"] == "failed" and stages["p2"]["error_code"] == "LLM_INVALID_OUTPUT"
    assert all(stages[k]["status"] == "pending" for k in ("p3", "p4", "p5", "p6", "p7"))

"""Etapas P1–P7 y su construcción a partir de la configuración."""

from ai_service.clients.clustering import ClusteringClient
from ai_service.clients.embeddings import EmbeddingsClient
from ai_service.clients.extractor import DocumentTextExtractor
from ai_service.clients.llm import LlmClient
from ai_service.clients.storage import DocumentStorage
from ai_service.config import Settings
from ai_service.core.errors import ConfigurationError
from ai_service.pipeline.contracts.common import LlmSettings
from ai_service.pipeline.contracts.p1 import P1Config
from ai_service.pipeline.contracts.p2 import P2Config
from ai_service.pipeline.contracts.p3 import P3Config
from ai_service.pipeline.contracts.p4 import P4Config
from ai_service.pipeline.prompts.p2 import resolve_p2_prompt
from ai_service.pipeline.stages.base import StageBase, StageError, StageResult, StubStage
from ai_service.pipeline.stages.p1_normalize import NormalizeStage, NormalizeStubStage
from ai_service.pipeline.stages.p2_requirements import RequirementsStage, RequirementsStubStage
from ai_service.pipeline.stages.p3_embeddings import EmbeddingsStage, EmbeddingsStubStage
from ai_service.pipeline.stages.p4_clustering import ClusteringStage, ClusteringStubStage
from ai_service.pipeline.stages.p5_context import ContextStage
from ai_service.pipeline.stages.p6_generation import GenerationStage
from ai_service.pipeline.stages.p7_evaluation import EvaluationStage
from ai_service.repositories.documents import DocumentsRepository
from ai_service.repositories.pipeline_results import PipelineResultsRepository

# Etapas que siguen simuladas tras la Fase 5 (P5–P7).
PENDING_STUB_STAGE_CLASSES: tuple[type[StubStage], ...] = (
    ContextStage,
    GenerationStage,
    EvaluationStage,
)

STUB_STAGE_CLASSES: tuple[type[StubStage], ...] = (
    NormalizeStubStage,
    RequirementsStubStage,
    EmbeddingsStubStage,
    ClusteringStubStage,
    *PENDING_STUB_STAGE_CLASSES,
)


def _stubs(classes: tuple[type[StubStage], ...], delay_seconds: float, fail_at_stage: str | None) -> list[StageBase]:
    return [cls(delay_seconds, fail=cls.key.value == fail_at_stage) for cls in classes]


def build_stub_stages(delay_seconds: float, fail_at_stage: str | None = None) -> list[StageBase]:
    """Instancia las siete etapas simuladas en orden, inyectando el fallo si se indica."""
    return _stubs(STUB_STAGE_CLASSES, delay_seconds, fail_at_stage)


def build_p1_config(settings: Settings) -> P1Config:
    return P1Config(
        rules_version=settings.p1_rules_version,
        language=settings.p1_language,
        story_delimiter_pattern=settings.p1_story_delimiter_pattern,
        max_story_chars=settings.p1_max_story_chars,
    )


def build_p2_config(settings: Settings) -> P2Config:
    """`P2Config` desde `Settings`. Sin `LLM_MODEL` el servicio no arranca (`ConfigurationError`)."""
    if not settings.llm_model:
        raise ConfigurationError("LLM_MODEL es obligatoria para ejecutar P2 (PIPELINE_STAGES=real).")
    return P2Config(
        prompt_version=settings.p2_prompt_version,
        llm=LlmSettings(provider=settings.llm_provider, model=settings.llm_model, parameters={}),
        max_stories_per_call=settings.p2_max_stories_per_call,
        max_retries=settings.p2_max_retries,
    )


def build_p3_config(settings: Settings) -> P3Config:
    return P3Config(
        model_name=settings.embeddings_model,
        normalize=settings.p3_normalize,
        input_template=settings.p3_input_template,
        batch_size=settings.p3_batch_size,
    )


def build_p4_config(settings: Settings) -> P4Config:
    """`params` lleva los pisos mínimos de HDBSCAN (decisión 1), no tamaños forzados."""
    return P4Config(
        algorithm=settings.clustering_algorithm,
        metric=settings.p4_metric,
        params={"min_cluster_size": settings.p4_min_cluster_size, "min_samples": settings.p4_min_samples},
    )


def build_real_stages(
    settings: Settings,
    *,
    documents: DocumentsRepository,
    storage: DocumentStorage,
    extractor: DocumentTextExtractor,
    llm_client: LlmClient,
    results: PipelineResultsRepository,
    embeddings_client: EmbeddingsClient,
    clustering_client: ClusteringClient,
) -> list[StageBase]:
    """P1 (heurística), P2 (LLM), P3 (embeddings) y P4 (clustering) reales; P5–P7 stubs (Fase 5).

    P1 no recibe `LlmClient` (camino B). P3 recibe `provider` aparte de `P3Config` (H-2).
    El fallo simulado solo aplica a las etapas stub.
    """
    p1 = NormalizeStage(
        documents=documents, storage=storage, extractor=extractor, results=results, config=build_p1_config(settings)
    )
    p2 = RequirementsStage(
        llm_client=llm_client, prompt_resolver=resolve_p2_prompt, results=results, config=build_p2_config(settings)
    )
    p3 = EmbeddingsStage(
        embeddings_client=embeddings_client,
        config=build_p3_config(settings),
        provider=settings.embeddings_provider,
        max_retries=settings.p3_max_retries,
    )
    p4 = ClusteringStage(clustering_client=clustering_client, config=build_p4_config(settings), results=results)
    stubs = _stubs(
        PENDING_STUB_STAGE_CLASSES, settings.pipeline_stub_delay_seconds, settings.pipeline_stub_fail_at_stage
    )
    return [p1, p2, p3, p4, *stubs]


__all__ = [
    "StageBase",
    "StageError",
    "StageResult",
    "StubStage",
    "NormalizeStage",
    "RequirementsStage",
    "EmbeddingsStage",
    "ClusteringStage",
    "build_stub_stages",
    "build_real_stages",
    "build_p1_config",
    "build_p2_config",
    "build_p3_config",
    "build_p4_config",
    "STUB_STAGE_CLASSES",
    "PENDING_STUB_STAGE_CLASSES",
]

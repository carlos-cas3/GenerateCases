"""Etapas P1–P7 y su construcción a partir de la configuración."""

from typing import Any

from ai_service.clients.clustering import ClusteringClient
from ai_service.clients.embeddings import EmbeddingsClient
from ai_service.clients.extractor import DocumentTextExtractor
from ai_service.clients.llm import LlmClient
from ai_service.clients.storage import DocumentStorage
from ai_service.config import Settings
from ai_service.core.errors import ConfigurationError
from ai_service.pipeline.contracts.common import LlmSettings, UnitStrategy
from ai_service.pipeline.contracts.p1 import P1Config
from ai_service.pipeline.contracts.p2 import P2Config
from ai_service.pipeline.contracts.p3 import P3Config
from ai_service.pipeline.contracts.p4 import P4Config
from ai_service.pipeline.contracts.p5 import P5Config
from ai_service.pipeline.contracts.p6 import P6Config
from ai_service.pipeline.prompts.p2 import resolve_p2_prompt
from ai_service.pipeline.prompts.p6 import resolve_p6_prompt
from ai_service.pipeline.stages.base import StageBase, StageError, StageResult, StubStage
from ai_service.pipeline.stages.p1_normalize import NormalizeStage, NormalizeStubStage
from ai_service.pipeline.stages.p1_statement import SUPPORTED_RULES_VERSIONS
from ai_service.pipeline.stages.p2_requirements import RequirementsStage, RequirementsStubStage
from ai_service.pipeline.stages.p3_embeddings import EmbeddingsStage, EmbeddingsStubStage
from ai_service.pipeline.stages.p4_clustering import ClusteringStage, ClusteringStubStage
from ai_service.pipeline.stages.p5_context import ContextStage, ContextStubStage
from ai_service.pipeline.stages.p6_generation import GenerationStage, GenerationStubStage
from ai_service.pipeline.stages.p7_evaluation import EvaluationStage
from ai_service.repositories.documents import DocumentsRepository
from ai_service.repositories.pipeline_results import PipelineResultsRepository

# Etapas que siguen simuladas tras la Fase 7 (solo P7).
PENDING_STUB_STAGE_CLASSES: tuple[type[StubStage], ...] = (EvaluationStage,)

STUB_STAGE_CLASSES: tuple[type[StubStage], ...] = (
    NormalizeStubStage,
    RequirementsStubStage,
    EmbeddingsStubStage,
    ClusteringStubStage,
    ContextStubStage,
    GenerationStubStage,
    *PENDING_STUB_STAGE_CLASSES,
)


def _stubs(classes: tuple[type[StubStage], ...], delay_seconds: float, fail_at_stage: str | None) -> list[StageBase]:
    return [cls(delay_seconds, fail=cls.key.value == fail_at_stage) for cls in classes]


def build_stub_stages(delay_seconds: float, fail_at_stage: str | None = None) -> list[StageBase]:
    """Instancia las siete etapas simuladas en orden, inyectando el fallo si se indica."""
    return _stubs(STUB_STAGE_CLASSES, delay_seconds, fail_at_stage)


def build_p1_config(settings: Settings) -> P1Config:
    if settings.p1_rules_version not in SUPPORTED_RULES_VERSIONS:
        raise ConfigurationError(
            f"P1_RULES_VERSION no soportada: {settings.p1_rules_version} "
            f"(válidas: {', '.join(sorted(SUPPORTED_RULES_VERSIONS))})."
        )
    return P1Config(
        rules_version=settings.p1_rules_version,
        language=settings.p1_language,
        story_delimiter_pattern=settings.p1_story_delimiter_pattern,
        max_story_chars=settings.p1_max_story_chars,
    )


def build_llm_parameters(settings: Settings) -> dict[str, Any]:
    """Parámetros de generación del LLM (D-OLLAMA-2).

    `temperature` vale para todos los proveedores. `num_ctx` y `think` son propios de Ollama:
    OpenAI y Anthropic vuelcan `extra` tal cual en el SDK y los rechazarían.
    """
    parameters: dict[str, Any] = {"temperature": settings.llm_temperature}
    if settings.llm_provider == "ollama":
        parameters |= {"num_ctx": settings.llm_num_ctx, "think": settings.llm_think}
    return parameters


def build_llm_settings(settings: Settings, stage: str) -> LlmSettings:
    """`LlmSettings` de P2/P6. Sin `LLM_MODEL` el servicio no arranca (`ConfigurationError`)."""
    if not settings.llm_model:
        raise ConfigurationError(f"LLM_MODEL es obligatoria para ejecutar {stage} (PIPELINE_STAGES=real).")
    return LlmSettings(provider=settings.llm_provider, model=settings.llm_model, parameters=build_llm_parameters(settings))


def build_p2_config(settings: Settings) -> P2Config:
    """`P2Config` desde `Settings`. Sin `LLM_MODEL` el servicio no arranca (`ConfigurationError`)."""
    return P2Config(
        prompt_version=settings.p2_prompt_version,
        llm=build_llm_settings(settings, "P2"),
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


def build_p5_config(settings: Settings) -> P5Config:
    """`P5Config` desde `Settings`.

    El contrato exige `strategy`, pero no sale de la configuración: `ContextStage` la deriva de
    `p4_output` en cada ejecución (D-F6-2) y la sustituye con `model_copy`. Aquí va un valor
    provisional (`by_user_story`).
    """
    return P5Config(
        max_tokens_per_unit=settings.p5_max_tokens_per_unit,
        strategy=UnitStrategy.BY_USER_STORY,
        instructions_version=settings.p5_instructions_version,
        include_prerequisites=settings.p5_include_prerequisites,
    )


def build_p6_config(settings: Settings) -> P6Config:
    """`P6Config` desde `Settings` (D-F7-1 a D-F7-5). Comparte proveedor y modelo de LLM con P2."""
    return P6Config(
        prompt_version=settings.p6_prompt_version,
        llm=build_llm_settings(settings, "P6"),
        max_retries=settings.p6_max_retries,
        failure_threshold=settings.p6_failure_threshold,
        max_cases_multiplier=settings.p6_max_cases_multiplier,
        max_cases_absolute=settings.p6_max_cases_absolute,
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
    """P1 (heurística), P2 (LLM), P3 (embeddings), P4 (clustering), P5 (contexto) y P6 (LLM)
    reales; P7 stub (Fase 7).

    P1 no recibe `LlmClient` (camino B). P3 recibe `provider` aparte de `P3Config` (H-2).
    P5 solo recibe su configuración: no usa clientes externos (R-DI-2). P6 comparte `LlmClient`
    con P2 y recibe su resolvedor de prompts y el repositorio de resultados.
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
    p5 = ContextStage(config=build_p5_config(settings))
    p6 = GenerationStage(
        llm_client=llm_client, prompt_resolver=resolve_p6_prompt, results=results, config=build_p6_config(settings)
    )
    stubs = _stubs(
        PENDING_STUB_STAGE_CLASSES, settings.pipeline_stub_delay_seconds, settings.pipeline_stub_fail_at_stage
    )
    return [p1, p2, p3, p4, p5, p6, *stubs]


__all__ = [
    "StageBase",
    "StageError",
    "StageResult",
    "StubStage",
    "NormalizeStage",
    "RequirementsStage",
    "EmbeddingsStage",
    "ClusteringStage",
    "ContextStage",
    "GenerationStage",
    "build_stub_stages",
    "build_real_stages",
    "build_llm_parameters",
    "build_p1_config",
    "build_p2_config",
    "build_p3_config",
    "build_p4_config",
    "build_p5_config",
    "build_p6_config",
    "SUPPORTED_RULES_VERSIONS",
    "build_llm_settings",
    "STUB_STAGE_CLASSES",
    "PENDING_STUB_STAGE_CLASSES",
]

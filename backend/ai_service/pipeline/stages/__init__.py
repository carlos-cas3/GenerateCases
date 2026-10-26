"""Etapas P1–P7 y su construcción a partir de la configuración."""

from ai_service.pipeline.stages.base import StageBase, StubStage
from ai_service.pipeline.stages.p1_normalize import NormalizeStage
from ai_service.pipeline.stages.p2_requirements import RequirementsStage
from ai_service.pipeline.stages.p3_embeddings import EmbeddingsStage
from ai_service.pipeline.stages.p4_clustering import ClusteringStage
from ai_service.pipeline.stages.p5_context import ContextStage
from ai_service.pipeline.stages.p6_generation import GenerationStage
from ai_service.pipeline.stages.p7_evaluation import EvaluationStage

STUB_STAGE_CLASSES: tuple[type[StubStage], ...] = (
    NormalizeStage,
    RequirementsStage,
    EmbeddingsStage,
    ClusteringStage,
    ContextStage,
    GenerationStage,
    EvaluationStage,
)


def build_stub_stages(delay_seconds: float, fail_at_stage: str | None = None) -> list[StageBase]:
    """Instancia las siete etapas simuladas en orden, inyectando el fallo si se indica."""
    return [cls(delay_seconds, fail=cls.key.value == fail_at_stage) for cls in STUB_STAGE_CLASSES]


__all__ = ["StageBase", "StubStage", "build_stub_stages", "STUB_STAGE_CLASSES"]

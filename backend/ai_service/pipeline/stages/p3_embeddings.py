"""P3 — Generación de embeddings. Fase 1: stub simulado."""

from typing import ClassVar

from ai_service.pipeline.stages.base import StubStage
from ai_service.schemas.generations import StageKey


class EmbeddingsStage(StubStage):
    key: ClassVar[StageKey] = StageKey.P3
    requires_clustering: ClassVar[bool] = True

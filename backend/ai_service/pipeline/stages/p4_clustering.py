"""P4 — Clustering semántico. Fase 1: stub simulado."""

from typing import ClassVar

from ai_service.pipeline.stages.base import StubStage
from ai_service.schemas.generations import StageKey


class ClusteringStage(StubStage):
    key: ClassVar[StageKey] = StageKey.P4
    requires_clustering: ClassVar[bool] = True

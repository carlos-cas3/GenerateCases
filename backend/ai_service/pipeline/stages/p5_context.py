"""P5 — Construcción de contexto estructurado. Fase 1: stub simulado."""

from typing import ClassVar

from ai_service.pipeline.stages.base import StubStage
from ai_service.schemas.generations import StageKey


class ContextStage(StubStage):
    key: ClassVar[StageKey] = StageKey.P5

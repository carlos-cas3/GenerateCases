"""P6 — Generación de casos de prueba funcionales. Fase 1: stub simulado."""

from typing import ClassVar

from ai_service.pipeline.stages.base import StubStage
from ai_service.schemas.generations import StageKey


class GenerationStage(StubStage):
    key: ClassVar[StageKey] = StageKey.P6

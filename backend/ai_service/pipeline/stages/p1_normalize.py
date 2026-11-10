"""P1 — Procesamiento, segmentación y estructuración de HU. Fase 1: stub simulado."""

from typing import ClassVar

from ai_service.pipeline.stages.base import StubStage
from ai_service.schemas.generations import StageKey


class NormalizeStage(StubStage):
    key: ClassVar[StageKey] = StageKey.P1

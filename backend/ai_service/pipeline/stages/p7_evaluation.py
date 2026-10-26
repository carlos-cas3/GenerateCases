"""P7 — Evaluación de resultados. Sin implementar: se registra como skipped. Fase 1: stub simulado."""

from typing import ClassVar

from ai_service.pipeline.stages.base import StubStage
from ai_service.schemas.generations import StageKey


class EvaluationStage(StubStage):
    key: ClassVar[StageKey] = StageKey.P7
    implemented: ClassVar[bool] = False

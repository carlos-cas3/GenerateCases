"""Interfaz común de las etapas y stub simulado de la Fase 1."""

import asyncio
from abc import ABC, abstractmethod
from typing import ClassVar

from ai_service.pipeline.context import PipelineContext
from ai_service.schemas.generations import StageKey


class SimulatedStageError(RuntimeError):
    """Fallo inyectado mediante `PIPELINE_STUB_FAIL_AT_STAGE`."""


class StageBase(ABC):
    """Etapa del pipeline. `requires_clustering` la omite si el clustering está deshabilitado."""

    key: ClassVar[StageKey]
    implemented: ClassVar[bool] = True
    requires_clustering: ClassVar[bool] = False

    @abstractmethod
    async def run(self, context: PipelineContext) -> None:
        """Ejecuta la etapa sobre el contexto."""


class StubStage(StageBase):
    """Etapa simulada: espera `delay_seconds` y opcionalmente falla."""

    def __init__(self, delay_seconds: float, fail: bool = False) -> None:
        self._delay_seconds = delay_seconds
        self._fail = fail

    async def run(self, context: PipelineContext) -> None:
        await asyncio.sleep(self._delay_seconds)
        if self._fail:
            raise SimulatedStageError(f"Fallo simulado en {self.key.value} (generation_id={context.generation_id})")

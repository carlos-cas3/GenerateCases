"""Interfaz común de las etapas y stub simulado de la Fase 1."""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

from ai_service.pipeline.context import PipelineContext
from ai_service.schemas.generations import LlmRun, StageKey, StageWarning


class SimulatedStageError(RuntimeError):
    """Fallo inyectado mediante `PIPELINE_STUB_FAIL_AT_STAGE`."""


class StageError(Exception):
    """Fallo controlado de una etapa. `code` y `message` se persisten en `generation_stages`.

    `message` debe ser apto para mostrar: sin datos sensibles ni el texto del documento.
    Cualquier otra excepción se registra con un mensaje genérico.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details


@dataclass(frozen=True, slots=True)
class StageResult:
    """Metadatos de una etapa completada (D-35).

    `skip_remaining`: las etapas posteriores se marcan `skipped` (D-29, P2 sin requisitos).
    """

    warnings: tuple[StageWarning, ...] = ()
    llm_runs: tuple[LlmRun, ...] = ()
    runtime_info: dict[str, Any] | None = None
    skip_remaining: bool = False


class StageBase(ABC):
    """Etapa del pipeline. `requires_clustering` la omite si el clustering está deshabilitado."""

    key: ClassVar[StageKey]
    implemented: ClassVar[bool] = True
    requires_clustering: ClassVar[bool] = False

    @abstractmethod
    async def run(self, context: PipelineContext) -> StageResult | None:
        """Ejecuta la etapa sobre el contexto. `None` equivale a un `StageResult()` vacío."""


class StubStage(StageBase):
    """Etapa simulada: espera `delay_seconds` y opcionalmente falla."""

    def __init__(self, delay_seconds: float, fail: bool = False) -> None:
        self._delay_seconds = delay_seconds
        self._fail = fail

    async def run(self, context: PipelineContext) -> StageResult | None:
        await asyncio.sleep(self._delay_seconds)
        if self._fail:
            raise SimulatedStageError(f"Fallo simulado en {self.key.value} (generation_id={context.generation_id})")
        return None

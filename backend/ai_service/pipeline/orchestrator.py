"""Orquestador P1–P7. No conoce Supabase ni FastAPI: solo ejecuta etapas y emite eventos."""

import logging
from collections.abc import Sequence

from ai_service.pipeline.catalog import get_stage_definition
from ai_service.pipeline.context import PipelineContext
from ai_service.pipeline.events import (
    PipelineCompleted,
    PipelineFailed,
    ProgressReporter,
    StageCompleted,
    StageFailed,
    StageSkipped,
    StageStarted,
)
from ai_service.pipeline.stages.base import StageBase, StageError, StageResult
from ai_service.schemas.generations import StageKey

logger = logging.getLogger(__name__)

INTERNAL_STAGE_ERROR_CODE = "INTERNAL_ERROR"


class PipelineOrchestrator:
    """Recorre las etapas en orden y publica el progreso mediante un `ProgressReporter`."""

    def __init__(
        self, stages: Sequence[StageBase], reporter: ProgressReporter, *, stop_after: StageKey | None = None
    ) -> None:
        """`stop_after`: ejecuta solo el prefijo P1…N y marca `skipped` el resto (calibración).

        `None` = run completo. Es independiente de `skip_remaining` (D-CS-2) y no enmascara
        el fallo de una etapa anterior al tope (D-CS-5).
        """
        self._stages = sorted(stages, key=lambda stage: get_stage_definition(stage.key).order)
        self._reporter = reporter
        self._stop_after = stop_after

    @staticmethod
    def should_skip(stage: StageBase, context: PipelineContext) -> bool:
        """P3/P4 se omiten sin clustering; cualquier etapa sin implementar también."""
        if not stage.implemented:
            return True
        return stage.requires_clustering and not context.configuration.clustering_enabled

    async def run(self, context: PipelineContext) -> bool:
        """Ejecuta el pipeline. Devuelve `True` si la generación termina `completed`.

        Una etapa que devuelve `skip_remaining` marca `skipped` todas las posteriores (D-29).
        Con `stop_after`, las etapas posteriores al tope se marcan `skipped` (D-CS-1/D-CS-2).
        El fallo de una etapa no bloqueante (P7) se registra, pero la generación se completa.
        Los errores del `reporter` (escrituras de estado) no se capturan: se propagan.
        """
        generation_id = context.generation_id
        stop_order = get_stage_definition(self._stop_after).order if self._stop_after is not None else None
        skip_remaining = False
        for stage in self._stages:
            stage_key = stage.key
            beyond_stop = stop_order is not None and get_stage_definition(stage_key).order > stop_order
            if skip_remaining or self.should_skip(stage, context) or beyond_stop:
                logger.info("Etapa omitida generation_id=%s stage_key=%s", generation_id, stage_key.value)
                await self._reporter.report(StageSkipped(generation_id=generation_id, stage_key=stage_key))
                continue

            await self._reporter.report(StageStarted(generation_id=generation_id, stage_key=stage_key))
            logger.info("Etapa iniciada generation_id=%s stage_key=%s", generation_id, stage_key.value)
            definition = get_stage_definition(stage_key)
            try:
                result = await stage.run(context) or StageResult()
            except StageError as exc:
                logger.warning(
                    "Etapa fallida generation_id=%s stage_key=%s error_code=%s",
                    generation_id, stage_key.value, exc.code,
                )
                error_code, error_message = exc.code, exc.message
            except Exception:
                logger.exception("Etapa fallida generation_id=%s stage_key=%s", generation_id, stage_key.value)
                error_code = INTERNAL_STAGE_ERROR_CODE
                error_message = f"La etapa '{definition.name}' falló durante la ejecución."
            else:
                await self._reporter.report(
                    StageCompleted(
                        generation_id=generation_id,
                        stage_key=stage_key,
                        warnings=result.warnings,
                        llm_runs=result.llm_runs,
                        runtime_info=result.runtime_info,
                    )
                )
                logger.info("Etapa completada generation_id=%s stage_key=%s", generation_id, stage_key.value)
                skip_remaining = result.skip_remaining
                continue

            await self._reporter.report(
                StageFailed(
                    generation_id=generation_id,
                    stage_key=stage_key,
                    error_code=error_code,
                    error_message=error_message,
                )
            )
            if definition.blocking:
                await self._reporter.report(
                    PipelineFailed(
                        generation_id=generation_id,
                        error_message=f"La generación falló en la etapa '{definition.name}'.",
                    )
                )
                return False
            logger.info("Fallo no bloqueante generation_id=%s stage_key=%s", generation_id, stage_key.value)

        await self._reporter.report(PipelineCompleted(generation_id=generation_id))
        logger.info("Pipeline completado generation_id=%s", generation_id)
        return True

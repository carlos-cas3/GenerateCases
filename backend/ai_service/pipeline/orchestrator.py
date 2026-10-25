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
from ai_service.pipeline.stages.base import StageBase

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Recorre las etapas en orden y publica el progreso mediante un `ProgressReporter`."""

    def __init__(self, stages: Sequence[StageBase], reporter: ProgressReporter) -> None:
        self._stages = sorted(stages, key=lambda stage: get_stage_definition(stage.key).order)
        self._reporter = reporter

    @staticmethod
    def should_skip(stage: StageBase, context: PipelineContext) -> bool:
        """P3/P4 se omiten sin clustering; cualquier etapa sin implementar también."""
        if not stage.implemented:
            return True
        return stage.requires_clustering and not context.configuration.clustering_enabled

    async def run(self, context: PipelineContext) -> bool:
        """Ejecuta el pipeline. Devuelve `True` si terminó sin fallos de etapa.

        Los errores del `reporter` (escrituras de estado) no se capturan: se propagan.
        """
        generation_id = context.generation_id
        for stage in self._stages:
            stage_key = stage.key
            if self.should_skip(stage, context):
                logger.info("Etapa omitida generation_id=%s stage_key=%s", generation_id, stage_key.value)
                await self._reporter.report(StageSkipped(generation_id=generation_id, stage_key=stage_key))
                continue

            await self._reporter.report(StageStarted(generation_id=generation_id, stage_key=stage_key))
            logger.info("Etapa iniciada generation_id=%s stage_key=%s", generation_id, stage_key.value)
            try:
                await stage.run(context)
            except Exception:
                logger.exception("Etapa fallida generation_id=%s stage_key=%s", generation_id, stage_key.value)
                name = get_stage_definition(stage_key).name
                await self._reporter.report(
                    StageFailed(
                        generation_id=generation_id,
                        stage_key=stage_key,
                        error_message=f"La etapa '{name}' falló durante la ejecución.",
                    )
                )
                await self._reporter.report(
                    PipelineFailed(
                        generation_id=generation_id,
                        error_message=f"La generación falló en la etapa '{name}'.",
                    )
                )
                return False

            await self._reporter.report(StageCompleted(generation_id=generation_id, stage_key=stage_key))
            logger.info("Etapa completada generation_id=%s stage_key=%s", generation_id, stage_key.value)

        await self._reporter.report(PipelineCompleted(generation_id=generation_id))
        logger.info("Pipeline completado generation_id=%s", generation_id)
        return True

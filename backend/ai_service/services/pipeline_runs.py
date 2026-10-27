"""Ejecución de una generación persistida: traduce eventos del pipeline en escrituras de estado.

Tabla de transiciones aplicada (pipeline-orchestration.md §5):

| Evento             | Etapa                    | Generación                                   |
|--------------------|--------------------------|----------------------------------------------|
| inicio (implícito) | —                        | queued → running, started_at                 |
| stage_started      | pending → running        | —                                            |
| stage_completed    | running → completed      | —                                            |
| stage_skipped      | pending → skipped        | —                                            |
| stage_failed       | running → failed + error | —                                            |
| pipeline_completed | —                        | running → completed (si 7 etapas finales ok) |
| pipeline_failed    | —                        | queued|running → failed + error, completed_at|
"""

import logging
from collections.abc import Sequence
from uuid import UUID

from ai_service.core.errors import InvalidStateTransition
from ai_service.core.time import utc_now
from ai_service.pipeline.context import PipelineContext
from ai_service.pipeline.events import (
    PipelineCompleted,
    PipelineEvent,
    PipelineFailed,
    StageCompleted,
    StageFailed,
    StageSkipped,
    StageStarted,
)
from ai_service.pipeline.orchestrator import PipelineOrchestrator
from ai_service.pipeline.stages.base import StageBase
from ai_service.repositories.generations import GenerationsRepository
from ai_service.schemas.generations import (
    ACTIVE_GENERATION_STATUSES,
    GenerationStatus,
    StageStatus,
)

logger = logging.getLogger(__name__)

INTERNAL_FAILURE_MESSAGE = "La generación falló por un error interno."
INTERNAL_STAGE_FAILURE_MESSAGE = "La etapa se interrumpió por un error interno."
INTERRUPTED_MESSAGE = "Ejecución interrumpida por reinicio del servicio."

_FINAL_STAGE_STATUSES = frozenset({StageStatus.COMPLETED, StageStatus.SKIPPED})


class RepositoryProgressReporter:
    """`ProgressReporter` que persiste cada evento a través del repositorio."""

    def __init__(self, repository: GenerationsRepository, generation_id: UUID) -> None:
        self._repository = repository
        self._generation_id = generation_id

    async def report(self, event: PipelineEvent) -> None:
        repo = self._repository
        gid = self._generation_id
        match event:
            case StageStarted():
                await repo.update_stage(
                    gid, event.stage_key, expected=StageStatus.PENDING, status=StageStatus.RUNNING,
                    started_at=event.occurred_at,
                )
            case StageCompleted():
                await repo.update_stage(
                    gid, event.stage_key, expected=StageStatus.RUNNING, status=StageStatus.COMPLETED,
                    completed_at=event.occurred_at,
                )
            case StageSkipped():
                await repo.update_stage(
                    gid, event.stage_key, expected=StageStatus.PENDING, status=StageStatus.SKIPPED,
                    completed_at=event.occurred_at,
                )
            case StageFailed():
                await repo.update_stage(
                    gid, event.stage_key, expected=StageStatus.RUNNING, status=StageStatus.FAILED,
                    completed_at=event.occurred_at, error_message=event.error_message,
                )
            case PipelineCompleted():
                await self._ensure_all_stages_final()
                await repo.update_generation_status(
                    gid, expected={GenerationStatus.RUNNING}, status=GenerationStatus.COMPLETED,
                    completed_at=event.occurred_at,
                )
            case PipelineFailed():
                await repo.update_generation_status(
                    gid, expected=ACTIVE_GENERATION_STATUSES, status=GenerationStatus.FAILED,
                    completed_at=event.occurred_at, error_message=event.error_message,
                )

    async def _ensure_all_stages_final(self) -> None:
        """Una generación solo se completa si sus 7 etapas están `completed` o `skipped`."""
        record = await self._repository.get_by_id(self._generation_id)
        if record is None:
            raise InvalidStateTransition(f"generation {self._generation_id} no existe")
        pending = [s.stage_key.value for s in record.stages if s.status not in _FINAL_STAGE_STATUSES]
        if len(record.stages) != 7 or pending:
            raise InvalidStateTransition(f"generation {self._generation_id}: etapas no finales {pending}")


class PipelineRunService:
    """Adapta una generación persistida a una ejecución del orquestador."""

    def __init__(self, repository: GenerationsRepository, stages: Sequence[StageBase]) -> None:
        self._repository = repository
        self._stages = stages

    async def run(self, context: PipelineContext) -> None:
        """Ejecuta el pipeline completo. Nunca propaga excepciones (corre en segundo plano)."""
        generation_id = context.generation_id
        try:
            await self._repository.update_generation_status(
                generation_id,
                expected={GenerationStatus.QUEUED},
                status=GenerationStatus.RUNNING,
                started_at=utc_now(),
            )
            logger.info("Pipeline iniciado generation_id=%s", generation_id)
            reporter = RepositoryProgressReporter(self._repository, generation_id)
            await PipelineOrchestrator(self._stages, reporter).run(context)
        except Exception:
            logger.exception("Error no previsto en el pipeline generation_id=%s", generation_id)
            await self._fail_safely(generation_id)

    async def _fail_safely(self, generation_id: UUID) -> None:
        """Marca `failed` la generación y su etapa `running`, si aún están activas."""
        now = utc_now()
        try:
            record = await self._repository.get_by_id(generation_id)
            if record is None or record.status not in ACTIVE_GENERATION_STATUSES:
                return
            for stage in record.stages:
                if stage.status == StageStatus.RUNNING:
                    await self._repository.update_stage(
                        generation_id, stage.stage_key, expected=StageStatus.RUNNING, status=StageStatus.FAILED,
                        completed_at=now, error_message=INTERNAL_STAGE_FAILURE_MESSAGE,
                    )
            await self._repository.update_generation_status(
                generation_id, expected=ACTIVE_GENERATION_STATUSES, status=GenerationStatus.FAILED,
                completed_at=now, error_message=INTERNAL_FAILURE_MESSAGE,
            )
        except Exception:
            # Sin escritura confirmada; la recuperación de arranque la marcará como interrumpida.
            logger.exception("No se pudo registrar el fallo generation_id=%s", generation_id)


async def recover_interrupted_generations(repository: GenerationsRepository) -> list[UUID]:
    """Recuperación de arranque: asume un único proceso, así que ninguna ejecución activa sigue viva."""
    interrupted = await repository.mark_interrupted(message=INTERRUPTED_MESSAGE, at=utc_now())
    for generation_id in interrupted:
        logger.warning("Generación interrumpida marcada como failed generation_id=%s", generation_id)
    return interrupted

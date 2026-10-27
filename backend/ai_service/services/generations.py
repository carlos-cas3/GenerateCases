"""Casos de uso de generaciones: crear, consultar, listar y eliminar."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol
from uuid import UUID

from ai_service.core.errors import DocumentNotFound, GenerationNotFound
from ai_service.pipeline.catalog import get_stage_definition
from ai_service.pipeline.context import PipelineConfiguration, PipelineContext
from ai_service.repositories.documents import DocumentsRepository
from ai_service.repositories.generations import GenerationsRepository
from ai_service.schemas.generations import (
    CreateGenerationRequest,
    Generation,
    GenerationConfiguration,
    GenerationList,
    GenerationStage,
    GenerationStatus,
    Pagination,
)
from ai_service.schemas.records import GenerationRecord
from ai_service.services.pipeline_runs import PipelineRunService

logger = logging.getLogger(__name__)


class TaskScheduler(Protocol):
    """Programa trabajo en segundo plano. `fastapi.BackgroundTasks` cumple este contrato."""

    def add_task(self, func: Callable[..., Awaitable[None]], *args: Any, **kwargs: Any) -> None: ...


def to_generation(record: GenerationRecord) -> Generation:
    """Construye la respuesta pública. `summary` es `null` en la Fase 1 (sin resultados persistidos)."""
    stages = []
    for stage in record.stages:
        definition = get_stage_definition(stage.stage_key)
        stages.append(
            GenerationStage(
                key=stage.stage_key,
                name=definition.name,
                status=stage.status,
                error_message=stage.error_message,
                started_at=stage.started_at,
                completed_at=stage.completed_at,
                order=stage.stage_order,
            )
        )
    return Generation(
        id=record.id,
        document_id=record.document_id,
        document_name=record.document_name,
        status=record.status,
        configuration=GenerationConfiguration(
            semantic_clustering_enabled=record.clustering_enabled,
            method_type=record.method_type,
        ),
        stages=stages,
        summary=None,
        error_message=record.error_message,
        created_at=record.created_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
    )


class GenerationsService:
    """Coordina documentos, generaciones y la ejecución del pipeline."""

    def __init__(
        self,
        generations: GenerationsRepository,
        documents: DocumentsRepository,
        pipeline_runs: PipelineRunService,
        default_method_type: str,
    ) -> None:
        self._generations = generations
        self._documents = documents
        self._pipeline_runs = pipeline_runs
        self._default_method_type = default_method_type

    async def create(self, request: CreateGenerationRequest, scheduler: TaskScheduler) -> Generation:
        """Valida el documento, crea la generación con sus etapas y programa el pipeline."""
        if await self._documents.get_by_id(request.document_id) is None:
            raise DocumentNotFound()

        requested = request.configuration
        configuration = PipelineConfiguration(
            clustering_enabled=requested.semantic_clustering_enabled,
            method_type=requested.method_type if requested.method_type is not None else self._default_method_type,
        )
        config_snapshot = {
            "semantic_clustering_enabled": configuration.clustering_enabled,
            "method_type": configuration.method_type,
        }
        generation_id = await self._generations.create(
            document_id=request.document_id,
            clustering_enabled=configuration.clustering_enabled,
            method_type=configuration.method_type,
            config_snapshot=config_snapshot,
        )
        record = await self._generations.get_by_id(generation_id)
        if record is None:
            raise RuntimeError(f"La generación {generation_id} no se pudo leer tras crearse")

        context = PipelineContext(
            generation_id=generation_id, document_id=request.document_id, configuration=configuration
        )
        scheduler.add_task(self._pipeline_runs.run, context)
        logger.info("Generación creada y programada generation_id=%s", generation_id)
        return to_generation(record)

    async def get(self, generation_id: UUID) -> Generation:
        """Devuelve el estado persistido de una generación."""
        record = await self._generations.get_by_id(generation_id)
        if record is None:
            raise GenerationNotFound()
        return to_generation(record)

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        document_id: UUID | None = None,
        status: GenerationStatus | None = None,
    ) -> GenerationList:
        """Lista generaciones paginadas, de la más reciente a la más antigua."""
        records, total = await self._generations.list_generations(
            document_id=document_id, status=status, limit=limit, offset=offset
        )
        return GenerationList(
            items=[to_generation(record) for record in records],
            pagination=Pagination(limit=limit, offset=offset, total=total),
        )

    async def delete(self, generation_id: UUID) -> None:
        """Elimina una generación final y sus datos dependientes."""
        await self._generations.delete(generation_id)
        logger.info("Generación eliminada generation_id=%s", generation_id)

"""Controlador HTTP de generaciones. Sin reglas de negocio ni acceso a Supabase."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response

from ai_service.api.dependencies import get_generations_service
from ai_service.core.errors import FeatureNotImplemented
from ai_service.schemas.common import ErrorResponse
from ai_service.schemas.generations import CreateGenerationRequest, Generation, GenerationList, GenerationStatus
from ai_service.services.generations import GenerationsService

router = APIRouter(prefix="/generations", tags=["Generations"])

Service = Annotated[GenerationsService, Depends(get_generations_service)]

_ERRORS: dict[int | str, dict] = {
    400: {"model": ErrorResponse, "description": "Parámetros o cuerpo inválidos."},
    500: {"model": ErrorResponse, "description": "Error interno inesperado."},
}
_NOT_FOUND: dict[int | str, dict] = {404: {"model": ErrorResponse, "description": "No existe la generación."}}


@router.post(
    "",
    status_code=202,
    response_model=Generation,
    operation_id="createGeneration",
    responses={**_ERRORS, 404: {"model": ErrorResponse, "description": "No existe el documento."}},
)
async def create_generation(
    body: CreateGenerationRequest, background_tasks: BackgroundTasks, service: Service
) -> Generation:
    """Crea una generación (`queued`) y programa el pipeline P1–P7."""
    return await service.create(body, background_tasks)


@router.get("", response_model=GenerationList, operation_id="listGenerations", responses=_ERRORS)
async def list_generations(
    service: Service,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    document_id: Annotated[UUID | None, Query()] = None,
    status: Annotated[GenerationStatus | None, Query()] = None,
) -> GenerationList:
    """Lista generaciones por `created_at` descendente."""
    return await service.list(limit=limit, offset=offset, document_id=document_id, status=status)


@router.get(
    "/{generation_id}",
    response_model=Generation,
    operation_id="getGeneration",
    responses={**_ERRORS, **_NOT_FOUND},
)
async def get_generation(generation_id: UUID, service: Service) -> Generation:
    """Devuelve estado, configuración y etapas. Es el punto de polling."""
    return await service.get(generation_id)


@router.delete(
    "/{generation_id}",
    status_code=204,
    response_class=Response,
    operation_id="deleteGeneration",
    responses={
        **_ERRORS,
        **_NOT_FOUND,
        409: {"model": ErrorResponse, "description": "La generación está en procesamiento."},
    },
)
async def delete_generation(generation_id: UUID, service: Service) -> Response:
    """Elimina una generación final y sus datos dependientes."""
    await service.delete(generation_id)
    return Response(status_code=204)


@router.get(
    "/{generation_id}/events",
    operation_id="getGenerationEvents",
    responses={501: {"model": ErrorResponse, "description": "SSE aún no implementado."}},
)
async def get_generation_events(generation_id: UUID) -> None:
    """Reservado para SSE; responde 501 hasta que exista una implementación real."""
    raise FeatureNotImplemented(
        "La transmisión de eventos SSE está planificada. Use polling sobre GET /api/v1/generations/{generation_id}."
    )

"""Controlador HTTP de documentos. Sin reglas de negocio ni acceso a Supabase."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, UploadFile

from ai_service.api.dependencies import get_documents_service
from ai_service.schemas.common import ErrorResponse
from ai_service.schemas.documents import Document, DocumentList
from ai_service.services.documents import DocumentsService

router = APIRouter(prefix="/documents", tags=["Documents"])

Service = Annotated[DocumentsService, Depends(get_documents_service)]

_ERRORS: dict[int | str, dict] = {
    400: {"model": ErrorResponse, "description": "Parámetros o cuerpo inválidos."},
    500: {"model": ErrorResponse, "description": "Error interno inesperado."},
}
_NOT_FOUND: dict[int | str, dict] = {404: {"model": ErrorResponse, "description": "No existe el documento."}}


@router.post(
    "",
    status_code=201,
    response_model=Document,
    operation_id="createDocument",
    responses={
        **_ERRORS,
        413: {"model": ErrorResponse, "description": "El archivo supera el tamaño máximo."},
        415: {"model": ErrorResponse, "description": "Tipo de archivo no soportado."},
    },
)
async def create_document(file: UploadFile, service: Service) -> Document:
    """Sube un TXT, PDF o DOCX (campo multipart `file`) y registra sus metadatos."""
    return await service.upload(file)


@router.get("", response_model=DocumentList, operation_id="listDocuments", responses=_ERRORS)
async def list_documents(
    service: Service,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentList:
    """Lista documentos por `uploaded_at` descendente."""
    return await service.list(limit=limit, offset=offset)


@router.get(
    "/{document_id}",
    response_model=Document,
    operation_id="getDocument",
    responses={**_ERRORS, **_NOT_FOUND},
)
async def get_document(document_id: UUID, service: Service) -> Document:
    """Devuelve los metadatos de un documento."""
    return await service.get(document_id)


@router.delete(
    "/{document_id}",
    status_code=204,
    response_class=Response,
    operation_id="deleteDocument",
    responses={
        **_ERRORS,
        **_NOT_FOUND,
        409: {"model": ErrorResponse, "description": "El documento tiene generaciones que dependen de él."},
    },
)
async def delete_document(document_id: UUID, service: Service) -> Response:
    """Elimina el documento y su archivo si ninguna generación depende de él."""
    await service.delete(document_id)
    return Response(status_code=204)

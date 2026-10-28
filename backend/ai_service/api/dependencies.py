"""Dependencias HTTP reutilizables."""

from fastapi import Request

from ai_service.services.documents import DocumentsService
from ai_service.services.generations import GenerationsService


def get_generations_service(request: Request) -> GenerationsService:
    """Servicio de generaciones construido en el `lifespan` de la aplicación."""
    return request.app.state.generations_service


def get_documents_service(request: Request) -> DocumentsService:
    """Servicio de documentos construido en el `lifespan` de la aplicación."""
    return request.app.state.documents_service

"""Dependencias HTTP reutilizables."""

from fastapi import Request

from ai_service.services.generations import GenerationsService


def get_generations_service(request: Request) -> GenerationsService:
    """Servicio de generaciones construido en el `lifespan` de la aplicación."""
    return request.app.state.generations_service

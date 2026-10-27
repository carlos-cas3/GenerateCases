"""Endpoint de salud."""

from fastapi import APIRouter

from ai_service.schemas.common import Health

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=Health, operation_id="getHealth")
async def get_health() -> Health:
    """Comprueba que el servicio responde."""
    return Health()

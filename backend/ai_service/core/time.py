"""Utilidades de fecha. Todas las marcas de tiempo son UTC."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Devuelve la fecha y hora actual con zona UTC."""
    return datetime.now(UTC)

"""Esquemas comunes: salud y formato de error."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class Health(BaseModel):
    status: Literal["ok"] = "ok"


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | list[Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Formato común `{"error": {"code", "message", "details"}}`."""

    error: ErrorDetail

"""Modelos internos de persistencia (filas de Supabase). No se exponen en HTTP."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ai_service.schemas.generations import GenerationStatus, StageKey, StageStatus


class DocumentRecord(BaseModel):
    """Fila de `documents` (sin `storage_path`, que la Fase 1 no necesita)."""

    model_config = ConfigDict(extra="ignore")

    id: UUID
    filename: str
    file_type: str
    size_bytes: int
    checksum: str
    uploaded_at: datetime


class StageRecord(BaseModel):
    """Fila de `generation_stages`."""

    model_config = ConfigDict(extra="ignore")

    stage_key: StageKey
    stage_order: int
    status: StageStatus
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class GenerationRecord(BaseModel):
    """Fila de `generations` + `documents.filename` + sus etapas ordenadas."""

    model_config = ConfigDict(extra="ignore")

    id: UUID
    document_id: UUID
    document_name: str
    status: GenerationStatus
    clustering_enabled: bool
    method_type: str
    config_snapshot: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    stages: list[StageRecord] = Field(default_factory=list)

"""Esquemas HTTP de documentos, alineados con `docs/openapi.yaml`."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from ai_service.schemas.generations import Pagination

FileType = Literal["txt", "pdf", "docx"]


class Document(BaseModel):
    """Metadatos públicos de un documento. `storage_path` nunca se expone."""

    id: UUID
    filename: str
    file_type: FileType
    size_bytes: int
    checksum: str
    uploaded_at: datetime


class DocumentList(BaseModel):
    items: list[Document]
    pagination: Pagination

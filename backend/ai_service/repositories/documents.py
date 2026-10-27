"""Repositorio de documentos (Fase 1: solo lectura por id)."""

import asyncio
from typing import Protocol
from uuid import UUID

from supabase import Client

from ai_service.schemas.records import DocumentRecord

_COLUMNS = "id, filename, file_type, size_bytes, checksum, uploaded_at"


class DocumentsRepository(Protocol):
    """Contrato de acceso a `documents`."""

    async def get_by_id(self, document_id: UUID) -> DocumentRecord | None:
        """Devuelve el documento o `None` si no existe."""
        ...


class SupabaseDocumentsRepository:
    """Implementación sobre Supabase. El cliente síncrono se ejecuta en un hilo."""

    def __init__(self, client: Client) -> None:
        self._client = client

    async def get_by_id(self, document_id: UUID) -> DocumentRecord | None:
        def _query() -> list[dict]:
            response = (
                self._client.table("documents").select(_COLUMNS).eq("id", str(document_id)).limit(1).execute()
            )
            return response.data or []

        rows = await asyncio.to_thread(_query)
        return DocumentRecord.model_validate(rows[0]) if rows else None

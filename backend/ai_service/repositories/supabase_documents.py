"""Adaptador Supabase para el repositorio de documentos."""

import asyncio
from datetime import datetime
from typing import Any
from uuid import UUID

from postgrest.exceptions import APIError
from postgrest.types import CountMethod
from supabase import Client

from ai_service.core.errors import DocumentInUse, DocumentNotFound
from ai_service.schemas.records import DocumentRecord

_COLUMNS = "id, filename, file_type, size_bytes, storage_path, checksum, uploaded_at"
_FK_VIOLATION = "23503"
_RANGE_NOT_SATISFIABLE = "PGRST103"


class SupabaseDocumentsRepository:
    """Implementación de `DocumentsRepository` sobre Supabase.

    El cliente síncrono de supabase-py se ejecuta en un hilo para no bloquear
    el event loop.  Los errores de postgrest se traducen a excepciones de dominio.
    """

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

    async def create(
        self,
        *,
        document_id: UUID,
        filename: str,
        file_type: str,
        size_bytes: int,
        storage_path: str,
        checksum: str,
        uploaded_at: datetime,
    ) -> None:
        row = {
            "id": str(document_id),
            "filename": filename,
            "file_type": file_type,
            "size_bytes": size_bytes,
            "storage_path": storage_path,
            "checksum": checksum,
            "uploaded_at": uploaded_at.isoformat(),
        }
        await asyncio.to_thread(lambda: self._client.table("documents").insert(row).execute())

    async def list_documents(self, *, limit: int, offset: int) -> tuple[list[DocumentRecord], int]:
        def _page() -> Any:
            return (
                self._client.table("documents")
                .select(_COLUMNS, count=CountMethod.exact)
                .order("uploaded_at", desc=True)
                .order("id", desc=True)
                .range(offset, offset + limit - 1)
                .execute()
            )

        try:
            response = await asyncio.to_thread(_page)
        except APIError as exc:
            # PostgREST responde 416 si el offset supera el total: página vacía.
            if exc.code != _RANGE_NOT_SATISFIABLE:
                raise
            count_response = await asyncio.to_thread(
                lambda: self._client.table("documents").select("id", count=CountMethod.exact, head=True).execute()
            )
            return [], count_response.count or 0
        return [DocumentRecord.model_validate(row) for row in response.data or []], response.count or 0

    async def delete(self, document_id: UUID) -> None:
        try:
            response = await asyncio.to_thread(
                lambda: self._client.table("documents").delete().eq("id", str(document_id)).execute()
            )
        except APIError as exc:
            # Red de seguridad: una generación apareció entre la comprobación y el borrado.
            if exc.code == _FK_VIOLATION:
                raise DocumentInUse() from exc
            raise
        if not response.data:
            raise DocumentNotFound()

"""Adaptador Supabase para el almacenamiento de archivos."""

import asyncio
from uuid import UUID

from storage3.exceptions import StorageException
from supabase import Client

from ai_service.clients.storage import build_storage_path
from ai_service.core.errors import StoredDocumentUnavailable


class SupabaseDocumentStorage:
    """Implementación de `DocumentStorage` sobre Supabase Storage.

    El cliente síncrono de supabase-py se ejecuta en un hilo para no bloquear
    el event loop.
    """

    def __init__(self, client: Client, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    async def upload(self, *, document_id: UUID, filename: str, content_type: str, data: bytes) -> str:
        storage_path = build_storage_path(document_id, filename)
        await asyncio.to_thread(
            lambda: self._client.storage.from_(self._bucket).upload(
                storage_path, data, {"content-type": content_type, "upsert": "false"}
            )
        )
        return storage_path

    async def download(self, storage_path: str) -> bytes:
        try:
            return await asyncio.to_thread(lambda: self._client.storage.from_(self._bucket).download(storage_path))
        except StorageException as exc:
            raise StoredDocumentUnavailable() from exc

    async def remove(self, storage_path: str) -> None:
        await asyncio.to_thread(lambda: self._client.storage.from_(self._bucket).remove([storage_path]))

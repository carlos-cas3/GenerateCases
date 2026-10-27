"""Almacenamiento de los archivos subidos (bucket privado de Supabase Storage)."""

import asyncio
import re
import unicodedata
from typing import Protocol
from uuid import UUID

from supabase import Client

CONTENT_TYPE_BY_EXTENSION: dict[str, str] = {
    "txt": "text/plain",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# Storage rechaza claves con caracteres fuera de este conjunto (acentos, espacios raros, etc.).
_UNSAFE_KEY_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


class DocumentStorage(Protocol):
    """Contrato de almacenamiento. Lo cumplen Supabase y el fake de los tests."""

    async def upload(self, *, document_id: UUID, filename: str, content_type: str, data: bytes) -> str:
        """Guarda el archivo y devuelve su `storage_path`."""
        ...

    async def remove(self, storage_path: str) -> None:
        """Elimina el objeto. Una clave inexistente no es un error."""
        ...


def sanitize_filename(filename: str) -> str:
    """Nombre seguro como clave de Storage: sin separadores de ruta ni caracteres no ASCII."""
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    stem, dot, extension = name.rpartition(".")
    if not dot:
        stem, extension = extension, ""
    stem = _UNSAFE_KEY_CHARS.sub("_", stem).strip("._") or "archivo"
    extension = _UNSAFE_KEY_CHARS.sub("", extension)
    return f"{stem}.{extension}" if extension else stem


def build_storage_path(document_id: UUID, filename: str) -> str:
    return f"{document_id}/{sanitize_filename(filename)}"


class SupabaseDocumentStorage:
    """Implementación sobre Supabase Storage. El cliente síncrono se ejecuta en un hilo."""

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

    async def remove(self, storage_path: str) -> None:
        await asyncio.to_thread(lambda: self._client.storage.from_(self._bucket).remove([storage_path]))

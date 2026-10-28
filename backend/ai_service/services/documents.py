"""Casos de uso de documentos: subir, consultar, listar y eliminar."""

import hashlib
import logging
from pathlib import PurePath
from uuid import UUID, uuid4

from fastapi import UploadFile

from ai_service.clients.storage import CONTENT_TYPE_BY_EXTENSION, DocumentStorage
from ai_service.core.errors import (
    DocumentInUse,
    DocumentNotFound,
    InvalidDocumentUpload,
    PayloadTooLarge,
    UnsupportedMediaType,
)
from ai_service.core.time import utc_now
from ai_service.repositories.documents import DocumentsRepository
from ai_service.repositories.generations import GenerationsRepository
from ai_service.schemas.documents import Document, DocumentList
from ai_service.schemas.generations import ACTIVE_GENERATION_STATUSES, Pagination
from ai_service.schemas.records import DocumentRecord

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 1024 * 1024
_MAX_REPORTED_GENERATION_IDS = 50


def to_document(record: DocumentRecord) -> Document:
    """Construye la respuesta pública, sin `storage_path`."""
    return Document(
        id=record.id,
        filename=record.filename,
        file_type=record.file_type,
        size_bytes=record.size_bytes,
        checksum=record.checksum,
        uploaded_at=record.uploaded_at,
    )


def _extension(filename: str) -> str:
    return PurePath(filename.replace("\\", "/")).suffix.lstrip(".").lower()


class DocumentsService:
    """Coordina el registro en `documents` y el archivo en Storage."""

    def __init__(
        self,
        documents: DocumentsRepository,
        generations: GenerationsRepository,
        storage: DocumentStorage,
        max_upload_size_bytes: int,
    ) -> None:
        self._documents = documents
        self._generations = generations
        self._storage = storage
        self._max_upload_size_bytes = max_upload_size_bytes

    async def upload(self, file: UploadFile) -> Document:
        """Valida tipo (extensión), tamaño y contenido; guarda en Storage y registra los metadatos."""
        filename = file.filename or ""
        file_type = _extension(filename)
        if file_type not in CONTENT_TYPE_BY_EXTENSION:
            raise UnsupportedMediaType()

        data = await self._read_limited(file)
        if not data:
            raise InvalidDocumentUpload(details=[{"path": "file", "message": "El archivo está vacío."}])

        document_id = uuid4()
        checksum = hashlib.sha256(data).hexdigest()
        storage_path = await self._storage.upload(
            document_id=document_id,
            filename=filename,
            content_type=CONTENT_TYPE_BY_EXTENSION[file_type],
            data=data,
        )
        record = DocumentRecord(
            id=document_id,
            filename=filename,
            file_type=file_type,
            size_bytes=len(data),
            storage_path=storage_path,
            checksum=checksum,
            uploaded_at=utc_now(),
        )
        try:
            await self._documents.create(
                document_id=record.id,
                filename=record.filename,
                file_type=record.file_type,
                size_bytes=record.size_bytes,
                storage_path=record.storage_path,
                checksum=record.checksum,
                uploaded_at=record.uploaded_at,
            )
        except Exception:
            await self._remove_quietly(storage_path)
            raise
        logger.info("Documento subido document_id=%s size_bytes=%s", document_id, record.size_bytes)
        return to_document(record)

    async def list(self, *, limit: int, offset: int) -> DocumentList:
        """Lista documentos paginados, del más reciente al más antiguo."""
        records, total = await self._documents.list_documents(limit=limit, offset=offset)
        return DocumentList(
            items=[to_document(record) for record in records],
            pagination=Pagination(limit=limit, offset=offset, total=total),
        )

    async def get(self, document_id: UUID) -> Document:
        record = await self._documents.get_by_id(document_id)
        if record is None:
            raise DocumentNotFound()
        return to_document(record)

    async def delete(self, document_id: UUID) -> None:
        """Elimina el documento solo si ninguna generación (activa o final) depende de él."""
        record = await self._documents.get_by_id(document_id)
        if record is None:
            raise DocumentNotFound()

        active_ids, active_total = await self._generations.ids_by_document(
            document_id, statuses=ACTIVE_GENERATION_STATUSES, limit=_MAX_REPORTED_GENERATION_IDS
        )
        if active_total:
            raise DocumentInUse(
                "El documento tiene generaciones activas y no puede eliminarse.",
                details={"generation_ids": active_ids},
            )
        all_ids, total = await self._generations.ids_by_document(
            document_id, statuses=None, limit=_MAX_REPORTED_GENERATION_IDS
        )
        if total:
            raise DocumentInUse(
                "El documento tiene generaciones asociadas y no puede eliminarse.",
                details={"generation_ids": all_ids},
            )

        await self._documents.delete(document_id)
        await self._remove_quietly(record.storage_path)
        logger.info("Documento eliminado document_id=%s", document_id)

    async def _read_limited(self, file: UploadFile) -> bytes:
        """Lee por tramos sin pasar de `max + 1` bytes; no confía en `Content-Length`."""
        limit = self._max_upload_size_bytes
        buffer = bytearray()
        while chunk := await file.read(_CHUNK_SIZE):
            buffer.extend(chunk)
            if len(buffer) > limit:
                raise PayloadTooLarge(f"El archivo supera el tamaño máximo de {limit / (1024 * 1024):g} MiB.")
        return bytes(buffer)

    async def _remove_quietly(self, storage_path: str) -> None:
        """Purga best-effort: un fallo de Storage deja un objeto huérfano, no un error HTTP."""
        try:
            await self._storage.remove(storage_path)
        except Exception:
            logger.exception("No se pudo eliminar el objeto de Storage (huérfano) storage_path=%s", storage_path)

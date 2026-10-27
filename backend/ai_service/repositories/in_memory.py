"""Repositorios FAKE en memoria para tests. Replican la semántica de las RPC y las guardas."""

import itertools
import logging
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from ai_service.core.errors import DocumentInUse, DocumentNotFound, GenerationInProgress, GenerationNotFound, InvalidStateTransition
from ai_service.core.time import utc_now
from ai_service.schemas.generations import (
    ACTIVE_GENERATION_STATUSES,
    GenerationStatus,
    StageKey,
    StageStatus,
)
from ai_service.schemas.records import DocumentRecord, GenerationRecord, StageRecord

logger = logging.getLogger(__name__)


@dataclass
class InMemoryStore:
    """Estado compartido por los repositorios en memoria."""

    documents: dict[UUID, DocumentRecord] = field(default_factory=dict)
    generations: dict[UUID, GenerationRecord] = field(default_factory=dict)
    insertion_order: dict[UUID, int] = field(default_factory=dict)
    document_order: dict[UUID, int] = field(default_factory=dict)
    _sequence: itertools.count = field(default_factory=itertools.count)

    def add_generation(self, record: GenerationRecord) -> None:
        """Inserta una generación ya construida (útil para preparar escenarios)."""
        self.generations[record.id] = record.model_copy(deep=True)
        self.insertion_order[record.id] = next(self._sequence)


class InMemoryDocumentsRepository:
    """Fake de `DocumentsRepository`."""

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def get_by_id(self, document_id: UUID) -> DocumentRecord | None:
        document = self._store.documents.get(document_id)
        return document.model_copy(deep=True) if document else None

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
        self._store.documents[document_id] = DocumentRecord(
            id=document_id,
            filename=filename,
            file_type=file_type,
            size_bytes=size_bytes,
            storage_path=storage_path,
            checksum=checksum,
            uploaded_at=uploaded_at,
        )
        self._store.document_order[document_id] = next(self._store._sequence)

    async def list_documents(self, *, limit: int, offset: int) -> tuple[list[DocumentRecord], int]:
        # Los documentos sembrados directamente en el store no tienen orden de inserción (-1).
        matches = sorted(
            self._store.documents.values(),
            key=lambda d: (d.uploaded_at, self._store.document_order.get(d.id, -1)),
            reverse=True,
        )
        page = matches[offset : offset + limit]
        return [document.model_copy(deep=True) for document in page], len(matches)

    async def delete(self, document_id: UUID) -> None:
        if document_id not in self._store.documents:
            raise DocumentNotFound()
        # Replica la FK `on delete restrict` de `generations.document_id`.
        if any(record.document_id == document_id for record in self._store.generations.values()):
            raise DocumentInUse()
        del self._store.documents[document_id]
        self._store.document_order.pop(document_id, None)


class InMemoryGenerationsRepository:
    """Fake de `GenerationsRepository`."""

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def create(
        self,
        *,
        document_id: UUID,
        clustering_enabled: bool,
        method_type: str,
        config_snapshot: dict[str, Any],
    ) -> UUID:
        document = self._store.documents.get(document_id)
        if document is None:
            raise DocumentNotFound()
        record = GenerationRecord(
            id=uuid4(),
            document_id=document_id,
            document_name=document.filename,
            status=GenerationStatus.QUEUED,
            clustering_enabled=clustering_enabled,
            method_type=method_type,
            config_snapshot=dict(config_snapshot),
            created_at=utc_now(),
            stages=[
                StageRecord(stage_key=key, stage_order=order, status=StageStatus.PENDING)
                for order, key in enumerate(StageKey, start=1)
            ],
        )
        self._store.add_generation(record)
        return record.id

    async def get_by_id(self, generation_id: UUID) -> GenerationRecord | None:
        record = self._store.generations.get(generation_id)
        return record.model_copy(deep=True) if record else None

    async def list_generations(
        self,
        *,
        document_id: UUID | None,
        status: GenerationStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[GenerationRecord], int]:
        matches = [
            record
            for record in self._store.generations.values()
            if (document_id is None or record.document_id == document_id)
            and (status is None or record.status == status)
        ]
        matches.sort(key=lambda r: (r.created_at, self._store.insertion_order[r.id]), reverse=True)
        page = matches[offset : offset + limit]
        return [record.model_copy(deep=True) for record in page], len(matches)

    async def ids_by_document(
        self,
        document_id: UUID,
        *,
        statuses: Collection[GenerationStatus] | None,
        limit: int,
    ) -> tuple[list[UUID], int]:
        matches = [
            record
            for record in self._store.generations.values()
            if record.document_id == document_id and (statuses is None or record.status in statuses)
        ]
        matches.sort(key=lambda r: (r.created_at, self._store.insertion_order[r.id]), reverse=True)
        return [record.id for record in matches[:limit]], len(matches)

    async def update_generation_status(
        self,
        generation_id: UUID,
        *,
        expected: Collection[GenerationStatus],
        status: GenerationStatus,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
    ) -> None:
        record = self._store.generations.get(generation_id)
        if record is None or record.status not in expected:
            logger.warning(
                "Transición de generación rechazada generation_id=%s target=%s", generation_id, status.value
            )
            raise InvalidStateTransition(f"generation {generation_id} -> {status.value}")
        record.status = status
        if started_at is not None:
            record.started_at = started_at
        if completed_at is not None:
            record.completed_at = completed_at
        if error_message is not None:
            record.error_message = error_message

    async def update_stage(
        self,
        generation_id: UUID,
        stage_key: StageKey,
        *,
        expected: StageStatus,
        status: StageStatus,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
    ) -> None:
        record = self._store.generations.get(generation_id)
        stage = next((s for s in record.stages if s.stage_key == stage_key), None) if record else None
        if stage is None or stage.status != expected:
            logger.warning(
                "Transición de etapa rechazada generation_id=%s stage_key=%s target=%s",
                generation_id,
                stage_key.value,
                status.value,
            )
            raise InvalidStateTransition(f"stage {generation_id}/{stage_key.value} -> {status.value}")
        stage.status = status
        if started_at is not None:
            stage.started_at = started_at
        if completed_at is not None:
            stage.completed_at = completed_at
        if error_message is not None:
            stage.error_message = error_message

    async def delete(self, generation_id: UUID) -> None:
        record = self._store.generations.get(generation_id)
        if record is None:
            raise GenerationNotFound()
        if record.status in ACTIVE_GENERATION_STATUSES:
            raise GenerationInProgress()
        del self._store.generations[generation_id]
        del self._store.insertion_order[generation_id]

    async def mark_interrupted(self, *, message: str, at: datetime) -> list[UUID]:
        interrupted: list[UUID] = []
        for record in self._store.generations.values():
            if record.status not in ACTIVE_GENERATION_STATUSES:
                continue
            for stage in record.stages:
                if stage.status == StageStatus.RUNNING:
                    stage.status = StageStatus.FAILED
                    stage.error_message = message
                    stage.completed_at = at
            record.status = GenerationStatus.FAILED
            record.error_message = message
            record.completed_at = at
            interrupted.append(record.id)
        return interrupted

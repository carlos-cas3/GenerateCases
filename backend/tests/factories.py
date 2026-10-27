"""Constructores de escenarios: generaciones en estados concretos y Storage falso."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from ai_service.clients.storage import build_storage_path
from ai_service.repositories.in_memory import InMemoryStore
from ai_service.schemas.generations import GenerationStatus, StageKey, StageStatus
from ai_service.schemas.records import GenerationRecord, StageRecord

BASE_TIME = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)


def add_generation(
    store: InMemoryStore,
    *,
    document_id: UUID,
    status: GenerationStatus,
    stage_statuses: dict[StageKey, StageStatus] | None = None,
    minutes: int = 0,
) -> UUID:
    """Inserta una generación con estados de etapa explícitos (por defecto todas `pending`)."""
    statuses = stage_statuses or {}
    document = store.documents[document_id]
    record = GenerationRecord(
        id=uuid4(),
        document_id=document_id,
        document_name=document.filename,
        status=status,
        clustering_enabled=True,
        method_type="llm_pipeline",
        config_snapshot={"semantic_clustering_enabled": True, "method_type": "llm_pipeline"},
        created_at=BASE_TIME + timedelta(minutes=minutes),
        stages=[
            StageRecord(stage_key=key, stage_order=order, status=statuses.get(key, StageStatus.PENDING))
            for order, key in enumerate(StageKey, start=1)
        ],
    )
    store.add_generation(record)
    return record.id


@dataclass
class FakeDocumentStorage:
    """Fake de `DocumentStorage`: objetos en memoria y registro de llamadas para asertar."""

    objects: dict[str, bytes] = field(default_factory=dict)
    uploads: list[str] = field(default_factory=list)
    removes: list[str] = field(default_factory=list)

    async def upload(self, *, document_id: UUID, filename: str, content_type: str, data: bytes) -> str:
        storage_path = build_storage_path(document_id, filename)
        self.objects[storage_path] = data
        self.uploads.append(storage_path)
        return storage_path

    async def remove(self, storage_path: str) -> None:
        self.removes.append(storage_path)
        self.objects.pop(storage_path, None)

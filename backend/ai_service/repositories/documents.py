"""Puerto de acceso a documentos — solo el contrato, sin infraestructura."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from ai_service.schemas.records import DocumentRecord


class DocumentsRepository(Protocol):
    """Contrato de acceso a `documents`. Lo cumplen Supabase y el fake en memoria."""

    async def get_by_id(self, document_id: UUID) -> DocumentRecord | None:
        """Devuelve el documento o `None` si no existe."""
        ...

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
        """Inserta el documento con el `id` indicado."""
        ...

    async def list_documents(self, *, limit: int, offset: int) -> tuple[list[DocumentRecord], int]:
        """Lista por `uploaded_at` descendente y devuelve también el total exacto."""
        ...

    async def delete(self, document_id: UUID) -> None:
        """Elimina el documento. Lanza `DocumentNotFound` o `DocumentInUse` (FK)."""
        ...

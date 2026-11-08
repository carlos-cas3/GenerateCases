"""Puerto de acceso a generaciones — solo el contrato, sin infraestructura."""

from collections.abc import Collection, Sequence
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from ai_service.schemas.generations import (
    GenerationStatus,
    LlmRun,
    StageKey,
    StageStatus,
    StageWarning,
)
from ai_service.schemas.records import GenerationRecord


class GenerationsRepository(Protocol):
    """Contrato de persistencia de generaciones. Lo cumplen Supabase y el fake en memoria."""

    async def create(
        self,
        *,
        document_id: UUID,
        clustering_enabled: bool,
        method_type: str,
        config_snapshot: dict[str, Any],
    ) -> UUID:
        """Crea la generación (`queued`) y sus 7 etapas (`pending`) de forma atómica."""
        ...

    async def get_by_id(self, generation_id: UUID) -> GenerationRecord | None:
        """Devuelve la generación con `document_name` y etapas ordenadas, o `None`."""
        ...

    async def list_generations(
        self,
        *,
        document_id: UUID | None,
        status: GenerationStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[GenerationRecord], int]:
        """Lista por `created_at` descendente y devuelve también el total exacto."""
        ...

    async def ids_by_document(
        self,
        document_id: UUID,
        *,
        statuses: Collection[GenerationStatus] | None,
        limit: int,
    ) -> tuple[list[UUID], int]:
        """Ids de generaciones del documento (filtradas por estado si se indica) y total."""
        ...

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
        """Actualiza el estado solo si el actual está en `expected`; si no, `InvalidStateTransition`."""
        ...

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
        error_code: str | None = None,
        warnings: Sequence[StageWarning] | None = None,
        llm_runs: Sequence[LlmRun] | None = None,
        runtime_info: dict[str, Any] | None = None,
    ) -> None:
        """Actualiza una etapa solo si su estado actual es `expected`; si no, `InvalidStateTransition`.

        Los campos en `None` no se modifican.
        """
        ...

    async def delete(self, generation_id: UUID) -> None:
        """Elimina una generación final. Lanza `GenerationNotFound` o `GenerationInProgress`."""
        ...

    async def mark_interrupted(self, *, message: str, code: str, at: datetime) -> list[UUID]:
        """Marca `failed` las generaciones activas y su etapa `running` (con `code`). Devuelve sus ids."""
        ...

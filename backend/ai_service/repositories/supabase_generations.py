"""Adaptador Supabase para el repositorio de generaciones."""

import asyncio
import logging
from collections.abc import Callable, Collection, Sequence
from datetime import datetime
from typing import Any, TypeVar
from uuid import UUID

from postgrest.exceptions import APIError
from postgrest.types import CountMethod
from pydantic import BaseModel
from supabase import Client

from ai_service.core.errors import DocumentNotFound, GenerationInProgress, GenerationNotFound, InvalidStateTransition
from ai_service.schemas.generations import (
    ACTIVE_GENERATION_STATUSES,
    GenerationStatus,
    LlmRun,
    StageKey,
    StageStatus,
    StageWarning,
)
from ai_service.schemas.records import GenerationRecord

logger = logging.getLogger(__name__)

T = TypeVar("T")

_SELECT = "*, documents(filename), generation_stages(*)"
_FK_VIOLATION = "23503"
_RANGE_NOT_SATISFIABLE = "PGRST103"


def _payload(**fields: Any) -> dict[str, Any]:
    """Construye el cuerpo de un UPDATE omitiendo `None`.

    Fechas en ISO 8601; dicts y secuencias de modelos como JSON (columnas `jsonb`);
    el resto como texto.
    """
    result: dict[str, Any] = {}
    for name, value in fields.items():
        if value is None:
            continue
        if isinstance(value, datetime):
            result[name] = value.isoformat()
        elif isinstance(value, dict):
            result[name] = value
        elif isinstance(value, (list, tuple)):
            result[name] = [item.model_dump(mode="json") if isinstance(item, BaseModel) else item for item in value]
        else:
            result[name] = str(value)
    return result


def _to_record(row: dict[str, Any]) -> GenerationRecord:
    document = row.get("documents") or {}
    stages = sorted(row.get("generation_stages") or [], key=lambda stage: stage["stage_order"])
    return GenerationRecord.model_validate({**row, "document_name": document.get("filename"), "stages": stages})


class SupabaseGenerationsRepository:
    """Implementación de `GenerationsRepository` sobre Supabase.

    El cliente síncrono de supabase-py se ejecuta en un hilo para no bloquear
    el event loop.  Los errores de postgrest se traducen a excepciones de dominio.
    """

    def __init__(self, client: Client) -> None:
        self._client = client

    @staticmethod
    async def _run(fn: Callable[[], T]) -> T:
        return await asyncio.to_thread(fn)

    async def create(
        self,
        *,
        document_id: UUID,
        clustering_enabled: bool,
        method_type: str,
        config_snapshot: dict[str, Any],
    ) -> UUID:
        params = {
            "p_document_id": str(document_id),
            "p_clustering_enabled": clustering_enabled,
            "p_method_type": method_type,
            "p_config_snapshot": config_snapshot,
        }
        try:
            response = await self._run(lambda: self._client.rpc("create_generation", params).execute())
        except APIError as exc:
            if exc.code == _FK_VIOLATION:
                raise DocumentNotFound() from exc
            raise
        return UUID(str(response.data))

    async def get_by_id(self, generation_id: UUID) -> GenerationRecord | None:
        response = await self._run(
            lambda: self._client.table("generations").select(_SELECT).eq("id", str(generation_id)).limit(1).execute()
        )
        rows = response.data or []
        return _to_record(rows[0]) if rows else None

    async def list_generations(
        self,
        *,
        document_id: UUID | None,
        status: GenerationStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[GenerationRecord], int]:
        def _filtered(columns: str, head: bool = False) -> Any:
            query = self._client.table("generations").select(columns, count=CountMethod.exact, head=head)
            if document_id is not None:
                query = query.eq("document_id", str(document_id))
            if status is not None:
                query = query.eq("status", status.value)
            return query

        def _page() -> Any:
            return (
                _filtered(_SELECT)
                .order("created_at", desc=True)
                .order("id", desc=True)
                .range(offset, offset + limit - 1)
                .execute()
            )

        try:
            response = await self._run(_page)
        except APIError as exc:
            # PostgREST responde 416 si el offset supera el total: página vacía.
            if exc.code != _RANGE_NOT_SATISFIABLE:
                raise
            count_response = await self._run(lambda: _filtered("id", head=True).execute())
            return [], count_response.count or 0
        return [_to_record(row) for row in response.data or []], response.count or 0

    async def ids_by_document(
        self,
        document_id: UUID,
        *,
        statuses: Collection[GenerationStatus] | None,
        limit: int,
    ) -> tuple[list[UUID], int]:
        def _query() -> Any:
            query = (
                self._client.table("generations")
                .select("id", count=CountMethod.exact)
                .eq("document_id", str(document_id))
            )
            if statuses is not None:
                query = query.in_("status", [value.value for value in statuses])
            return query.order("created_at", desc=True).limit(limit).execute()

        response = await self._run(_query)
        return [UUID(row["id"]) for row in response.data or []], response.count or 0

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
        payload = _payload(
            status=status.value, started_at=started_at, completed_at=completed_at, error_message=error_message
        )
        expected_values = [value.value for value in expected]
        response = await self._run(
            lambda: self._client.table("generations")
            .update(payload)
            .eq("id", str(generation_id))
            .in_("status", expected_values)
            .execute()
        )
        if not response.data:
            logger.warning(
                "Transición de generación rechazada generation_id=%s expected=%s target=%s",
                generation_id,
                expected_values,
                status.value,
            )
            raise InvalidStateTransition(f"generation {generation_id}: {expected_values} -> {status.value}")

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
        payload = _payload(
            status=status.value,
            started_at=started_at,
            completed_at=completed_at,
            error_message=error_message,
            error_code=error_code,
            warnings=warnings,
            llm_runs=llm_runs,
            runtime_info=runtime_info,
        )
        response = await self._run(
            lambda: self._client.table("generation_stages")
            .update(payload)
            .eq("generation_id", str(generation_id))
            .eq("stage_key", stage_key.value)
            .eq("status", expected.value)
            .execute()
        )
        if not response.data:
            logger.warning(
                "Transición de etapa rechazada generation_id=%s stage_key=%s expected=%s target=%s",
                generation_id,
                stage_key.value,
                expected.value,
                status.value,
            )
            raise InvalidStateTransition(f"stage {generation_id}/{stage_key.value}: {expected.value} -> {status.value}")

    async def delete(self, generation_id: UUID) -> None:
        response = await self._run(
            lambda: self._client.rpc("delete_generation_if_final", {"p_id": str(generation_id)}).execute()
        )
        result = response.data
        if result == "not_found":
            raise GenerationNotFound()
        if result == "in_progress":
            raise GenerationInProgress()
        if result != "deleted":
            raise RuntimeError(f"Resultado inesperado de delete_generation_if_final: {result!r}")

    async def mark_interrupted(self, *, message: str, code: str, at: datetime) -> list[UUID]:
        active = [value.value for value in ACTIVE_GENERATION_STATUSES]
        response = await self._run(
            lambda: self._client.table("generations").select("id").in_("status", active).execute()
        )
        ids = [row["id"] for row in response.data or []]
        if not ids:
            return []

        failed = _payload(error_message=message, completed_at=at)
        await self._run(
            lambda: self._client.table("generation_stages")
            .update({"status": StageStatus.FAILED.value, "error_code": code, **failed})
            .in_("generation_id", ids)
            .eq("status", StageStatus.RUNNING.value)
            .execute()
        )
        updated = await self._run(
            lambda: self._client.table("generations")
            .update({"status": GenerationStatus.FAILED.value, **failed})
            .in_("id", ids)
            .in_("status", active)
            .execute()
        )
        return [UUID(row["id"]) for row in updated.data or []]

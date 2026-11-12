"""Adaptador Supabase para la persistencia de resultados del pipeline (RPC `persist_pN_*`)."""

import asyncio
import logging
from typing import Any
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client

from ai_service.core.errors import (
    DuplicateEntryError,
    InvalidReferenceError,
    MissingIdentifierError,
    PersistenceError,
)

logger = logging.getLogger(__name__)

# errcode SQL → excepción de dominio. El resto se reporta como `PersistenceError` genérico.
_ERRORS_BY_SQLSTATE: dict[str, type[PersistenceError]] = {
    "23503": InvalidReferenceError,  # FK / HU o RF inexistente
    "23502": MissingIdentifierError,  # NOT NULL / id faltante
    "23505": DuplicateEntryError,  # unique / HU duplicada en el payload (T-02)
}


class SupabasePipelineResultsRepository:
    """Implementación de `PipelineResultsRepository` sobre las RPC de Supabase.

    El cliente síncrono de supabase-py se ejecuta en un hilo para no bloquear el event loop.
    """

    def __init__(self, client: Client) -> None:
        self._client = client

    async def persist_p1_user_stories(self, generation_id: UUID, payload: list[dict[str, Any]]) -> None:
        await self._call("persist_p1_user_stories", generation_id, payload)

    async def persist_p2_requirements(self, generation_id: UUID, payload: dict[str, Any]) -> None:
        await self._call("persist_p2_requirements", generation_id, payload)

    async def _call(self, rpc_name: str, generation_id: UUID, payload: Any) -> None:
        params = {"p_generation_id": str(generation_id), "p_payload": payload}
        try:
            await asyncio.to_thread(lambda: self._client.rpc(rpc_name, params).execute())
        except APIError as exc:
            logger.warning(
                "RPC rechazada rpc=%s generation_id=%s code=%s message=%s",
                rpc_name, generation_id, exc.code, exc.message,
            )
            error_cls = _ERRORS_BY_SQLSTATE.get(exc.code or "", PersistenceError)
            # El mensaje de la BD puede incluir códigos HU-xxx (útiles), nunca texto del documento.
            raise error_cls(details={"rpc": rpc_name, "sql_code": exc.code, "sql_message": exc.message}) from exc

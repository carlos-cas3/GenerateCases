"""Puerto de persistencia de resultados del pipeline — solo el contrato, sin infraestructura.

Cada método invoca una RPC transaccional e idempotente de `supabase/schema.sql`
(`persist_p1_user_stories`, `persist_p2_requirements`, `persist_p4_clusters`). Los payloads los construyen los
contratos (`P1Output`, `P2Output`, `P4Output` → `to_rpc_payload()`); el repositorio solo
los envía y traduce los errores SQL a excepciones de dominio (`PersistenceError` y subtipos).
"""

from typing import Any, Protocol
from uuid import UUID


class PipelineResultsRepository(Protocol):
    """Contrato de persistencia de resultados de etapa. Lo cumplen Supabase y el fake en memoria."""

    async def persist_p1_user_stories(self, generation_id: UUID, payload: list[dict[str, Any]]) -> None:
        """Inserta o actualiza (por `generation_id` + `code`) las HU de P1. Idempotente."""
        ...

    async def persist_p2_requirements(self, generation_id: UUID, payload: dict[str, Any]) -> None:
        """Guarda clasificaciones, RF y vínculos HU↔RF de P2 en una transacción. Idempotente.

        Lanza `DuplicateEntryError` si una HU se clasifica dos veces (T-02) e
        `InvalidReferenceError` si se referencian HU inexistentes.
        """
        ...

    async def persist_p4_clusters(self, generation_id: UUID, payload: dict[str, Any]) -> None:
        """Guarda clusters, asignaciones RF↔cluster y RF sin cluster en una transacción. Idempotente.

        Lanza `MissingIdentifierError` si un cluster no trae `id` e `InvalidReferenceError` si se
        referencian RF inexistentes en la generación.
        """
        ...

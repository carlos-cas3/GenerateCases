"""Fixtures de la capa de integración contra Supabase real (Fase 8, T-F8-01).

Gating (D-F8-2): los tests se marcan `integration` y `pytest.ini` los excluye por defecto.
Aunque se pidan con `-m integration`, se **saltan** si `RUN_SUPABASE_TESTS` no está activo o
faltan credenciales.

Aislamiento (D-F8-3), decisión aún abierta. Se soportan las dos opciones del plan:

1. Proyecto aparte (recomendado): `SUPABASE_URL_TEST` / `SUPABASE_SERVICE_ROLE_KEY_TEST`.
2. Proyecto del `.env` (con datos reales): solo si además `SUPABASE_TESTS_ALLOW_SHARED_PROJECT=1`.
   Cada test usa su propio documento y `generation_id`, solo toca filas propias y las borra
   en el teardown (cascade vía `delete_generation_if_final`), aunque el test falle.

Sin ninguna de las dos, los tests no se ejecutan (skip).
"""

from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from ai_service.repositories.supabase_generations import SupabaseGenerationsRepository
from ai_service.repositories.supabase_pipeline_results import SupabasePipelineResultsRepository

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
TEST_DOCUMENT_PREFIX = "fase8-integration"


class IntegrationSettings(BaseSettings):
    """Variables de la capa de integración (entorno o `.env`)."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True
    )

    run_supabase_tests: bool = False
    supabase_url_test: str | None = None
    supabase_service_role_key_test: SecretStr | None = None
    supabase_tests_allow_shared_project: bool = False
    supabase_url: str | None = None
    supabase_service_role_key: SecretStr | None = None

    def credentials(self) -> tuple[str, str] | None:
        """(url, key) según D-F8-3, o `None` si no hay una opción de aislamiento válida."""
        if self.supabase_url_test and self.supabase_service_role_key_test:
            return self.supabase_url_test, self.supabase_service_role_key_test.get_secret_value()
        if self.supabase_tests_allow_shared_project and self.supabase_url and self.supabase_service_role_key:
            return self.supabase_url, self.supabase_service_role_key.get_secret_value()
        return None


@pytest.fixture(scope="session")
def supabase_client() -> Any:
    """Cliente Supabase real, o `skip` si la capa no está habilitada (D-F8-2/D-F8-3)."""
    settings = IntegrationSettings()
    if not settings.run_supabase_tests:
        pytest.skip("RUN_SUPABASE_TESTS no está activo")
    credentials = settings.credentials()
    if credentials is None:
        pytest.skip(
            "Sin credenciales de integración: define SUPABASE_URL_TEST/SUPABASE_SERVICE_ROLE_KEY_TEST "
            "o SUPABASE_TESTS_ALLOW_SHARED_PROJECT=1 (D-F8-3)"
        )
    from supabase import create_client

    return create_client(*credentials)


@pytest.fixture
def generations_repo(supabase_client: Any) -> SupabaseGenerationsRepository:
    return SupabaseGenerationsRepository(supabase_client)


@pytest.fixture
def results_repo(supabase_client: Any) -> SupabasePipelineResultsRepository:
    return SupabasePipelineResultsRepository(supabase_client)


@pytest.fixture
def integration_document(supabase_client: Any) -> Iterator[UUID]:
    """Documento propio (solo la fila; sin objeto en Storage). Se borra al final del test."""
    document_id = uuid4()
    filename = f"{TEST_DOCUMENT_PREFIX}-{document_id}.txt"
    supabase_client.table("documents").insert(
        {
            "id": str(document_id),
            "filename": filename,
            "file_type": "txt",
            "size_bytes": 0,
            "storage_path": f"{TEST_DOCUMENT_PREFIX}/{filename}",
            "checksum": "0" * 32,
        }
    ).execute()
    try:
        yield document_id
    finally:
        supabase_client.table("documents").delete().eq("id", str(document_id)).execute()


class GenerationTracker:
    """Crea generaciones efímeras y registra las creadas por otras vías para borrarlas."""

    def __init__(self, repo: SupabaseGenerationsRepository, document_id: UUID) -> None:
        self._repo = repo
        self.document_id = document_id
        self.created: list[UUID] = []

    async def create(self, *, clustering_enabled: bool = True) -> UUID:
        generation_id = await self._repo.create(
            document_id=self.document_id,
            clustering_enabled=clustering_enabled,
            method_type="llm_pipeline",
            config_snapshot={"source": TEST_DOCUMENT_PREFIX},
        )
        self.track(generation_id)
        return generation_id

    def track(self, generation_id: UUID) -> UUID:
        self.created.append(generation_id)
        return generation_id


def _force_cleanup(client: Any, generation_id: UUID) -> None:
    """Borra la generación aunque haya quedado activa: la pasa a `failed` y aplica cascade."""
    client.table("generations").update({"status": "failed"}).eq("id", str(generation_id)).in_(
        "status", ["queued", "running"]
    ).execute()
    client.rpc("delete_generation_if_final", {"p_id": str(generation_id)}).execute()


@pytest.fixture
async def generation_factory(
    supabase_client: Any, generations_repo: SupabaseGenerationsRepository, integration_document: UUID
) -> AsyncIterator[GenerationTracker]:
    """Generaciones propias del test, borradas en cascade en el teardown aunque el test falle."""
    tracker = GenerationTracker(generations_repo, integration_document)
    try:
        yield tracker
    finally:
        for generation_id in tracker.created:
            _force_cleanup(supabase_client, generation_id)


RowsReader = Callable[[str, UUID], list[dict[str, Any]]]


@pytest.fixture
def read_rows(supabase_client: Any) -> RowsReader:
    """Lee todas las filas de una tabla para una generación (relectura tras las RPC)."""

    def _read(table: str, generation_id: UUID) -> list[dict[str, Any]]:
        return supabase_client.table(table).select("*").eq("generation_id", str(generation_id)).execute().data or []

    return _read


__all__ = [
    "GenerationTracker",
    "IntegrationSettings",
    "RowsReader",
    "generation_factory",
    "generations_repo",
    "read_rows",
    "results_repo",
    "supabase_client",
    "integration_document",
]

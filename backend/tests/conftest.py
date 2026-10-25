"""Fixtures: app con repositorios en memoria, delay 0 y sin Supabase."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from ai_service.config import Settings
from ai_service.main import create_app
from ai_service.repositories.in_memory import (
    InMemoryDocumentsRepository,
    InMemoryGenerationsRepository,
    InMemoryStore,
)
from ai_service.schemas.records import DocumentRecord

DOCUMENT_ID = UUID("6f9d1c2e-0a4b-4c8d-9e1f-2b3c4d5e6f70")
DOCUMENT_NAME = "historias-release-1.txt"


@pytest.fixture
def store() -> InMemoryStore:
    store = InMemoryStore()
    store.documents[DOCUMENT_ID] = DocumentRecord(
        id=DOCUMENT_ID,
        filename=DOCUMENT_NAME,
        file_type="txt",
        size_bytes=4821,
        checksum="9b74c9897bac770ffc029102a200c5de",
        uploaded_at=datetime(2026, 10, 25, 12, 0, tzinfo=UTC),
    )
    return store


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {"pipeline_stub_delay_seconds": 0, **overrides}
    return Settings(_env_file=None, **values)


ClientFactory = Callable[..., TestClient]


@pytest.fixture
def client_factory(store: InMemoryStore) -> Iterator[ClientFactory]:
    """Crea clientes con ajustes opcionales; se cierran al terminar el test."""
    opened: list[TestClient] = []

    def factory(*, raise_server_exceptions: bool = True, generations_repository: Any = None, **overrides: Any) -> TestClient:
        app = create_app(
            make_settings(**overrides),
            generations_repository=generations_repository or InMemoryGenerationsRepository(store),
            documents_repository=InMemoryDocumentsRepository(store),
        )
        client = TestClient(app, raise_server_exceptions=raise_server_exceptions)
        client.__enter__()
        opened.append(client)
        return client

    yield factory
    for client in opened:
        client.__exit__(None, None, None)


@pytest.fixture
def client(client_factory: ClientFactory) -> TestClient:
    return client_factory()

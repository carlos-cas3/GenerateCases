"""Flujo HTTP de documentos con repositorios en memoria y Storage falso (Fase 2)."""

import hashlib
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from ai_service.clients.storage import sanitize_filename
from ai_service.repositories.in_memory import InMemoryStore
from ai_service.schemas.generations import GenerationStatus
from tests.conftest import DOCUMENT_ID, ClientFactory
from tests.factories import FakeDocumentStorage, add_generation
from tests.test_generations_api import assert_error

URL = "/api/v1/documents"
DOCUMENT_FIELDS = {"id", "filename", "file_type", "size_bytes", "checksum", "uploaded_at"}


def upload(client: TestClient, filename: str, content: bytes = b"Como usuario quiero...") -> object:
    return client.post(URL, files={"file": (filename, content, "application/octet-stream")})


# 1 ---------------------------------------------------------------------------
def test_upload_txt_returns_201(client: TestClient, storage: FakeDocumentStorage, store: InMemoryStore) -> None:
    content = b"Como usuario quiero iniciar sesion."
    response = upload(client, "historias.txt", content)

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == DOCUMENT_FIELDS
    assert body["filename"] == "historias.txt"
    assert body["file_type"] == "txt"
    assert body["size_bytes"] == len(content)
    assert body["checksum"] == hashlib.sha256(content).hexdigest()

    storage_path = f"{body['id']}/historias.txt"
    assert storage.uploads == [storage_path]
    assert storage.objects[storage_path] == content
    assert store.documents[UUID(body["id"])].storage_path == storage_path
    assert body["id"] in [item["id"] for item in client.get(URL).json()["items"]]


def test_upload_type_is_taken_from_extension(client: TestClient) -> None:
    body = upload(client, "Requisitos.DOCX").json()
    assert body["file_type"] == "docx"
    assert upload(client, "informe.pdf").json()["file_type"] == "pdf"


# 2 ---------------------------------------------------------------------------
def test_upload_unsupported_extension_returns_415(client: TestClient, storage: FakeDocumentStorage) -> None:
    assert_error(upload(client, "imagen.png"), 415, "UNSUPPORTED_MEDIA_TYPE")
    assert_error(upload(client, "sin_extension"), 415, "UNSUPPORTED_MEDIA_TYPE")
    assert storage.uploads == []


# 3 ---------------------------------------------------------------------------
def test_upload_too_large_returns_413(client_factory: ClientFactory, storage: FakeDocumentStorage) -> None:
    client = client_factory(max_upload_size_bytes=64)

    assert_error(upload(client, "grande.txt", b"x" * 65), 413, "PAYLOAD_TOO_LARGE")
    assert storage.uploads == []
    assert upload(client, "justo.txt", b"x" * 64).status_code == 201


# 4 ---------------------------------------------------------------------------
def test_upload_empty_file_returns_400(client: TestClient, storage: FakeDocumentStorage) -> None:
    error = assert_error(upload(client, "vacio.txt", b""), 400, "VALIDATION_ERROR")
    assert error["details"][0]["path"] == "file"
    assert storage.uploads == []


# 5 ---------------------------------------------------------------------------
def test_upload_without_file_field_returns_400(client: TestClient) -> None:
    response = client.post(URL, files={"otro": ("a.txt", b"hola", "text/plain")})
    error = assert_error(response, 400, "VALIDATION_ERROR")
    assert error["details"][0]["path"] == "file"


def test_failed_insert_removes_uploaded_object(
    client_factory: ClientFactory, store: InMemoryStore, storage: FakeDocumentStorage, monkeypatch
) -> None:
    client = client_factory(raise_server_exceptions=False)

    async def broken_create(self, **kwargs) -> None:
        raise RuntimeError("fallo de base de datos")

    from ai_service.repositories.in_memory import InMemoryDocumentsRepository

    monkeypatch.setattr(InMemoryDocumentsRepository, "create", broken_create)
    response = upload(client, "notas.txt")

    assert_error(response, 500, "INTERNAL_ERROR")
    assert len(storage.uploads) == 1
    assert storage.removes == storage.uploads
    assert storage.objects == {}
    assert list(store.documents) == [DOCUMENT_ID]


def test_storage_path_is_sanitized() -> None:
    assert sanitize_filename("..\\carpeta/historias de usuario.txt") == "historias_de_usuario.txt"
    assert sanitize_filename("Requisitos_versión_ñ.pdf") == "Requisitos_version_n.pdf"
    assert sanitize_filename("/") == "archivo"
    assert sanitize_filename("ñ.docx") == "n.docx"
    assert sanitize_filename("€.docx") == "archivo.docx"


# 6 ---------------------------------------------------------------------------
def test_list_orders_by_uploaded_at_and_paginates(client: TestClient) -> None:
    first = upload(client, "a.txt").json()["id"]
    second = upload(client, "b.txt").json()["id"]

    body = client.get(URL).json()
    assert [item["id"] for item in body["items"]] == [second, first, str(DOCUMENT_ID)]
    assert body["pagination"] == {"limit": 20, "offset": 0, "total": 3}

    body = client.get(URL, params={"limit": 1, "offset": 1}).json()
    assert [item["id"] for item in body["items"]] == [first]
    assert body["pagination"] == {"limit": 1, "offset": 1, "total": 3}

    body = client.get(URL, params={"offset": 10}).json()
    assert body["items"] == [] and body["pagination"]["total"] == 3

    assert_error(client.get(URL, params={"limit": 0}), 400, "VALIDATION_ERROR")


# 7 ---------------------------------------------------------------------------
def test_get_document(client: TestClient) -> None:
    response = client.get(f"{URL}/{DOCUMENT_ID}")
    assert response.status_code == 200
    assert set(response.json()) == DOCUMENT_FIELDS
    assert response.json()["id"] == str(DOCUMENT_ID)

    assert_error(client.get(f"{URL}/{uuid4()}"), 404, "DOCUMENT_NOT_FOUND")
    assert_error(client.get(f"{URL}/no-es-uuid"), 400, "VALIDATION_ERROR")


# 8 ---------------------------------------------------------------------------
def test_delete_without_generations_returns_204(client: TestClient, storage: FakeDocumentStorage) -> None:
    document_id = upload(client, "borrar.txt").json()["id"]
    storage_path = storage.uploads[0]

    response = client.delete(f"{URL}/{document_id}")

    assert response.status_code == 204
    assert response.content == b""
    assert_error(client.get(f"{URL}/{document_id}"), 404, "DOCUMENT_NOT_FOUND")
    assert storage.removes == [storage_path]
    assert storage_path not in storage.objects


def test_delete_seed_document_without_storage_object(client: TestClient, storage: FakeDocumentStorage) -> None:
    """El objeto del seed no existe en Storage: la purga best-effort lo tolera."""
    assert client.delete(f"{URL}/{DOCUMENT_ID}").status_code == 204
    assert storage.removes == [f"{DOCUMENT_ID}/historias-release-1.txt"]


def test_delete_storage_failure_still_returns_204(
    client: TestClient, store: InMemoryStore, storage: FakeDocumentStorage, monkeypatch
) -> None:
    async def broken_remove(storage_path: str) -> None:
        raise RuntimeError("Storage caído")

    monkeypatch.setattr(storage, "remove", broken_remove)

    assert client.delete(f"{URL}/{DOCUMENT_ID}").status_code == 204
    assert DOCUMENT_ID not in store.documents


# 9 ---------------------------------------------------------------------------
def test_delete_with_active_generation_returns_409(
    client: TestClient, store: InMemoryStore, storage: FakeDocumentStorage
) -> None:
    finished = add_generation(store, document_id=DOCUMENT_ID, status=GenerationStatus.COMPLETED, minutes=0)
    active = add_generation(store, document_id=DOCUMENT_ID, status=GenerationStatus.RUNNING, minutes=1)

    error = assert_error(client.delete(f"{URL}/{DOCUMENT_ID}"), 409, "DOCUMENT_IN_USE")

    assert error["message"] == "El documento tiene generaciones activas y no puede eliminarse."
    assert error["details"] == {"generation_ids": [str(active)]}
    assert finished in store.generations
    assert DOCUMENT_ID in store.documents
    assert storage.removes == []


# 10 --------------------------------------------------------------------------
def test_delete_with_only_final_generations_returns_409(
    client: TestClient, store: InMemoryStore, storage: FakeDocumentStorage
) -> None:
    completed = add_generation(store, document_id=DOCUMENT_ID, status=GenerationStatus.COMPLETED, minutes=0)
    failed = add_generation(store, document_id=DOCUMENT_ID, status=GenerationStatus.FAILED, minutes=1)

    error = assert_error(client.delete(f"{URL}/{DOCUMENT_ID}"), 409, "DOCUMENT_IN_USE")

    assert error["message"] == "El documento tiene generaciones asociadas y no puede eliminarse."
    assert error["details"] == {"generation_ids": [str(failed), str(completed)]}
    assert DOCUMENT_ID in store.documents
    assert storage.removes == []


# 11 --------------------------------------------------------------------------
def test_delete_missing_document_returns_404(client: TestClient) -> None:
    assert_error(client.delete(f"{URL}/{uuid4()}"), 404, "DOCUMENT_NOT_FOUND")


# 12 --------------------------------------------------------------------------
def test_delete_after_removing_generations_returns_204(client: TestClient, store: InMemoryStore) -> None:
    generation_id = add_generation(store, document_id=DOCUMENT_ID, status=GenerationStatus.COMPLETED)
    assert client.delete(f"{URL}/{DOCUMENT_ID}").status_code == 409

    assert client.delete(f"/api/v1/generations/{generation_id}").status_code == 204
    assert client.delete(f"{URL}/{DOCUMENT_ID}").status_code == 204
    assert_error(client.delete(f"{URL}/{DOCUMENT_ID}"), 404, "DOCUMENT_NOT_FOUND")


def test_uploaded_document_can_start_generation(client: TestClient) -> None:
    document_id = upload(client, "nuevo.txt").json()["id"]

    response = client.post("/api/v1/generations", json={"document_id": document_id})

    assert response.status_code == 202
    assert response.json()["document_name"] == "nuevo.txt"

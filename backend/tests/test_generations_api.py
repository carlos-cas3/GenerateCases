"""Flujo HTTP de generaciones con el repositorio en memoria (criterios 1–8)."""

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from ai_service.pipeline.catalog import STAGE_CATALOG
from ai_service.repositories.in_memory import InMemoryGenerationsRepository, InMemoryStore
from ai_service.schemas.generations import GenerationStatus, StageKey, StageStatus
from ai_service.schemas.records import DocumentRecord
from tests.conftest import DOCUMENT_ID, DOCUMENT_NAME, ClientFactory
from tests.factories import BASE_TIME, add_generation

URL = "/api/v1/generations"


def _stages(body: dict) -> dict[str, dict]:
    return {stage["key"]: stage for stage in body["stages"]}


def assert_error(response, status_code: int, code: str) -> dict:
    assert response.status_code == status_code, response.text
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    return body["error"]


def test_health(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# 1 ---------------------------------------------------------------------------
def test_create_returns_202_with_pending_stages(client: TestClient) -> None:
    response = client.post(URL, json={"document_id": str(DOCUMENT_ID)})

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["document_id"] == str(DOCUMENT_ID)
    assert body["document_name"] == DOCUMENT_NAME
    assert body["configuration"] == {"semantic_clustering_enabled": True, "method_type": "llm_pipeline"}
    assert body["summary"] is None
    for field in ("error_message", "started_at", "completed_at"):
        assert field in body and body[field] is None
    assert [(s["key"], s["name"], s["order"]) for s in body["stages"]] == [
        (d.key.value, d.name, d.order) for d in STAGE_CATALOG
    ]
    for stage in body["stages"]:
        assert stage["status"] == "pending"
        assert stage["error_message"] is None and stage["started_at"] is None and stage["completed_at"] is None


def test_create_keeps_explicit_configuration(client: TestClient, store: InMemoryStore) -> None:
    payload = {
        "document_id": str(DOCUMENT_ID),
        "configuration": {"semantic_clustering_enabled": False, "method_type": "baseline"},
    }
    body = client.post(URL, json=payload).json()

    assert body["configuration"] == {"semantic_clustering_enabled": False, "method_type": "baseline"}
    record = store.generations[UUID(body["id"])]
    assert record.config_snapshot == {"semantic_clustering_enabled": False, "method_type": "baseline"}


# 2 ---------------------------------------------------------------------------
def test_happy_path_completes_with_p7_skipped(client: TestClient) -> None:
    generation_id = client.post(URL, json={"document_id": str(DOCUMENT_ID)}).json()["id"]

    body = client.get(f"{URL}/{generation_id}").json()

    assert body["status"] == "completed"
    assert body["started_at"] is not None and body["completed_at"] is not None
    assert body["error_message"] is None
    stages = _stages(body)
    for key in ("p1", "p2", "p3", "p4", "p5", "p6"):
        assert stages[key]["status"] == "completed"
        assert stages[key]["started_at"] is not None and stages[key]["completed_at"] is not None
    assert stages["p7"]["status"] == "skipped"
    assert stages["p7"]["started_at"] is None and stages["p7"]["completed_at"] is not None


# 3 ---------------------------------------------------------------------------
def test_clustering_disabled_skips_p3_p4(client: TestClient) -> None:
    payload = {"document_id": str(DOCUMENT_ID), "configuration": {"semantic_clustering_enabled": False}}
    generation_id = client.post(URL, json=payload).json()["id"]

    body = client.get(f"{URL}/{generation_id}").json()

    assert body["status"] == "completed"
    stages = _stages(body)
    for key in ("p3", "p4", "p7"):
        assert stages[key]["status"] == "skipped"
        assert stages[key]["started_at"] is None
        assert stages[key]["completed_at"] is not None
    for key in ("p1", "p2", "p5", "p6"):
        assert stages[key]["status"] == "completed"


# 4 ---------------------------------------------------------------------------
def test_injected_failure_at_p4(client_factory: ClientFactory) -> None:
    client = client_factory(pipeline_stub_fail_at_stage="p4")
    generation_id = client.post(URL, json={"document_id": str(DOCUMENT_ID)}).json()["id"]

    body = client.get(f"{URL}/{generation_id}").json()

    assert body["status"] == "failed"
    assert body["error_message"]
    assert body["completed_at"] is not None
    stages = _stages(body)
    assert [stages[k]["status"] for k in ("p1", "p2", "p3")] == ["completed"] * 3
    assert stages["p4"]["status"] == "failed"
    assert stages["p4"]["error_message"]
    assert "Traceback" not in stages["p4"]["error_message"]
    assert "Fallo simulado" not in stages["p4"]["error_message"]
    assert stages["p4"]["completed_at"] is not None
    for key in ("p5", "p6", "p7"):
        assert stages[key]["status"] == "pending"
        assert stages[key]["started_at"] is None and stages[key]["completed_at"] is None


# 5 ---------------------------------------------------------------------------
@pytest.mark.parametrize("status", [GenerationStatus.QUEUED, GenerationStatus.RUNNING])
def test_delete_active_generation_returns_409(client: TestClient, store: InMemoryStore, status) -> None:
    generation_id = add_generation(store, document_id=DOCUMENT_ID, status=status)

    response = client.delete(f"{URL}/{generation_id}")

    assert_error(response, 409, "GENERATION_IN_PROGRESS")
    assert generation_id in store.generations


@pytest.mark.parametrize("status", [GenerationStatus.COMPLETED, GenerationStatus.FAILED])
def test_delete_final_generation_returns_204(client: TestClient, store: InMemoryStore, status) -> None:
    generation_id = add_generation(store, document_id=DOCUMENT_ID, status=status)

    response = client.delete(f"{URL}/{generation_id}")

    assert response.status_code == 204
    assert response.content == b""
    assert generation_id not in store.generations
    assert DOCUMENT_ID in store.documents
    assert_error(client.get(f"{URL}/{generation_id}"), 404, "GENERATION_NOT_FOUND")


def test_delete_missing_generation_returns_404(client: TestClient) -> None:
    assert_error(client.delete(f"{URL}/{uuid4()}"), 404, "GENERATION_NOT_FOUND")


# 6 ---------------------------------------------------------------------------
def test_list_filters_order_and_pagination(client: TestClient, store: InMemoryStore) -> None:
    other_id = uuid4()
    store.documents[other_id] = DocumentRecord(
        id=other_id,
        filename="otro.pdf",
        file_type="pdf",
        size_bytes=10,
        storage_path=f"{other_id}/otro.pdf",
        checksum="x",
        uploaded_at=BASE_TIME,
    )
    g0 = add_generation(store, document_id=DOCUMENT_ID, status=GenerationStatus.COMPLETED, minutes=0)
    g1 = add_generation(store, document_id=DOCUMENT_ID, status=GenerationStatus.FAILED, minutes=1)
    g2 = add_generation(store, document_id=other_id, status=GenerationStatus.COMPLETED, minutes=2)
    g3 = add_generation(store, document_id=DOCUMENT_ID, status=GenerationStatus.COMPLETED, minutes=3)

    body = client.get(URL).json()
    assert [item["id"] for item in body["items"]] == [str(g) for g in (g3, g2, g1, g0)]
    assert body["pagination"] == {"limit": 20, "offset": 0, "total": 4}
    assert len(body["items"][0]["stages"]) == 7

    body = client.get(URL, params={"limit": 2, "offset": 1}).json()
    assert [item["id"] for item in body["items"]] == [str(g2), str(g1)]
    assert body["pagination"] == {"limit": 2, "offset": 1, "total": 4}

    body = client.get(URL, params={"document_id": str(DOCUMENT_ID)}).json()
    assert [item["id"] for item in body["items"]] == [str(g) for g in (g3, g1, g0)]
    assert body["pagination"]["total"] == 3

    body = client.get(URL, params={"status": "completed", "document_id": str(DOCUMENT_ID)}).json()
    assert [item["id"] for item in body["items"]] == [str(g3), str(g0)]
    assert body["pagination"]["total"] == 2

    body = client.get(URL, params={"offset": 10}).json()
    assert body["items"] == [] and body["pagination"]["total"] == 4


# 7 ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"document_id": "no-es-uuid"},
        {"document_id": str(DOCUMENT_ID), "extra": 1},
        {"document_id": str(DOCUMENT_ID), "configuration": {"semantic_clustering_enabled": "si"}},
        {"document_id": str(DOCUMENT_ID), "configuration": {"method_type": None}},
        {"document_id": str(DOCUMENT_ID), "configuration": {"unknown": True}},
        {"document_id": str(DOCUMENT_ID), "configuration": None},
    ],
)
def test_invalid_body_returns_400(client: TestClient, payload: dict) -> None:
    error = assert_error(client.post(URL, json=payload), 400, "VALIDATION_ERROR")
    assert isinstance(error["details"], list) and error["details"]
    for detail in error["details"]:
        assert set(detail) == {"path", "message"}


def test_malformed_json_returns_400(client: TestClient) -> None:
    response = client.post(URL, content=b"{no json", headers={"content-type": "application/json"})
    assert_error(response, 400, "VALIDATION_ERROR")


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"status": "done"}])
def test_invalid_query_returns_400(client: TestClient, params: dict) -> None:
    error = assert_error(client.get(URL, params=params), 400, "VALIDATION_ERROR")
    assert error["details"][0]["path"] in params


@pytest.mark.parametrize("method", ["get", "delete"])
def test_malformed_uuid_returns_400(client: TestClient, method: str) -> None:
    error = assert_error(getattr(client, method)(f"{URL}/no-es-uuid"), 400, "VALIDATION_ERROR")
    assert error["details"][0]["path"] == "generation_id"


def test_unknown_document_returns_404(client: TestClient, store: InMemoryStore) -> None:
    assert_error(client.post(URL, json={"document_id": str(uuid4())}), 404, "DOCUMENT_NOT_FOUND")
    assert store.generations == {}


def test_unknown_generation_returns_404(client: TestClient) -> None:
    assert_error(client.get(f"{URL}/{uuid4()}"), 404, "GENERATION_NOT_FOUND")


def test_unexpected_error_returns_500_without_trace(client_factory: ClientFactory, store: InMemoryStore) -> None:
    class BrokenRepository(InMemoryGenerationsRepository):
        async def list_generations(self, **kwargs):
            raise RuntimeError("secreto: postgres://user:pass@host")

    client = client_factory(raise_server_exceptions=False, generations_repository=BrokenRepository(store))
    response = client.get(URL)

    error = assert_error(response, 500, "INTERNAL_ERROR")
    assert "secreto" not in response.text and "Traceback" not in response.text
    assert error["details"] == {}


# 8 ---------------------------------------------------------------------------
def test_events_returns_501(client: TestClient) -> None:
    assert_error(client.get(f"{URL}/{uuid4()}/events"), 501, "NOT_IMPLEMENTED")


def test_stage_keys_are_complete() -> None:
    assert [d.key for d in STAGE_CATALOG] == list(StageKey)
    assert StageStatus.SKIPPED.value == "skipped"

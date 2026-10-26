"""Recuperación de ejecuciones interrumpidas al arrancar (criterio 9)."""

from ai_service.schemas.generations import GenerationStatus, StageKey, StageStatus
from ai_service.services.pipeline_runs import INTERRUPTED_MESSAGE
from tests.conftest import DOCUMENT_ID, ClientFactory
from tests.factories import add_generation


def test_startup_marks_active_generations_failed(client_factory: ClientFactory, store) -> None:
    running = add_generation(
        store,
        document_id=DOCUMENT_ID,
        status=GenerationStatus.RUNNING,
        stage_statuses={StageKey.P1: StageStatus.COMPLETED, StageKey.P2: StageStatus.RUNNING},
    )
    queued = add_generation(store, document_id=DOCUMENT_ID, status=GenerationStatus.QUEUED)
    completed = add_generation(
        store,
        document_id=DOCUMENT_ID,
        status=GenerationStatus.COMPLETED,
        stage_statuses={key: StageStatus.COMPLETED for key in StageKey},
    )

    client = client_factory()  # el lifespan ejecuta la recuperación

    body = client.get(f"/api/v1/generations/{running}").json()
    assert body["status"] == "failed"
    assert body["error_message"] == INTERRUPTED_MESSAGE
    assert body["completed_at"] is not None
    stages = {s["key"]: s for s in body["stages"]}
    assert stages["p1"]["status"] == "completed"
    assert stages["p2"]["status"] == "failed"
    assert stages["p2"]["error_message"] == INTERRUPTED_MESSAGE
    assert stages["p2"]["completed_at"] is not None
    assert all(stages[k]["status"] == "pending" for k in ("p3", "p4", "p5", "p6", "p7"))

    body = client.get(f"/api/v1/generations/{queued}").json()
    assert body["status"] == "failed"
    assert body["error_message"] == INTERRUPTED_MESSAGE
    assert all(s["status"] == "pending" for s in body["stages"])

    assert client.get(f"/api/v1/generations/{completed}").json()["status"] == "completed"

    # Tras la recuperación, la generación ya es final y puede eliminarse.
    assert client.delete(f"/api/v1/generations/{running}").status_code == 204

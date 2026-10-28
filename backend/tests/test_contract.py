"""Las respuestas cumplen los esquemas de `docs/openapi.yaml` (criterio 10)."""

from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from ai_service.schemas.generations import GenerationStatus
from tests.conftest import DOCUMENT_ID, ClientFactory
from tests.factories import add_generation

SPEC_PATH = Path(__file__).resolve().parents[1] / "docs" / "openapi.yaml"
SPEC_URI = "urn:testgen:openapi"
URL = "/api/v1/generations"
DOCUMENTS_URL = "/api/v1/documents"


@pytest.fixture(scope="module")
def validate():
    spec = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    registry = Registry().with_resource(SPEC_URI, Resource.from_contents(spec, default_specification=DRAFT202012))

    def _validate(instance: object, schema_name: str) -> None:
        schema = {"$ref": f"{SPEC_URI}#/components/schemas/{schema_name}"}
        validator = Draft202012Validator(
            schema, registry=registry, format_checker=Draft202012Validator.FORMAT_CHECKER
        )
        errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
        assert not errors, "\n".join(f"{list(e.path)}: {e.message}" for e in errors)

    return _validate


def test_health_contract(client: TestClient, validate) -> None:
    validate(client.get("/api/v1/health").json(), "Health")


def test_generation_contracts(client: TestClient, validate) -> None:
    created = client.post(URL, json={"document_id": str(DOCUMENT_ID)})
    validate(created.json(), "Generation")

    validate(client.get(f"{URL}/{created.json()['id']}").json(), "Generation")
    validate(client.get(URL).json(), "GenerationList")


def test_document_contracts(client: TestClient, validate) -> None:
    created = client.post(DOCUMENTS_URL, files={"file": ("notas.txt", b"Como usuario quiero...", "text/plain")})
    assert created.status_code == 201
    validate(created.json(), "Document")

    validate(client.get(f"{DOCUMENTS_URL}/{created.json()['id']}").json(), "Document")
    validate(client.get(DOCUMENTS_URL).json(), "DocumentList")


def test_failed_generation_contract(client_factory: ClientFactory, validate) -> None:
    client = client_factory(pipeline_stub_fail_at_stage="p2")
    generation_id = client.post(URL, json={"document_id": str(DOCUMENT_ID)}).json()["id"]
    validate(client.get(f"{URL}/{generation_id}").json(), "Generation")


def test_error_contracts(client: TestClient, store, validate) -> None:
    active = add_generation(store, document_id=DOCUMENT_ID, status=GenerationStatus.RUNNING)
    responses = [
        client.post(URL, json={}),
        client.get(URL, params={"limit": 0}),
        client.get(f"{URL}/no-es-uuid"),
        client.post(URL, json={"document_id": str(uuid4())}),
        client.get(f"{URL}/{uuid4()}"),
        client.delete(f"{URL}/{active}"),
        client.get(f"{URL}/{uuid4()}/events"),
        client.post(DOCUMENTS_URL, files={"file": ("vacio.txt", b"", "text/plain")}),
        client.post(DOCUMENTS_URL, files={"file": ("imagen.png", b"png", "image/png")}),
        client.get(f"{DOCUMENTS_URL}/{uuid4()}"),
        client.delete(f"{DOCUMENTS_URL}/{DOCUMENT_ID}"),
    ]
    assert [r.status_code for r in responses] == [400, 400, 400, 404, 404, 409, 501, 400, 415, 404, 409]
    for response in responses:
        validate(response.json(), "Error")

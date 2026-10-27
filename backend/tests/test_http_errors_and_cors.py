"""Fase 1.5: errores HTTP del framework en formato estándar y CORS configurable."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from tests.conftest import ClientFactory, make_settings

ALLOWED_ORIGIN = "http://localhost:5173"


def _assert_standard_error(body: dict, code: str) -> None:
    assert "detail" not in body
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    assert "details" in body["error"]


def test_unknown_route_returns_standard_404(client: TestClient) -> None:
    response = client.get("/api/v1/ruta-inexistente")
    assert response.status_code == 404
    _assert_standard_error(response.json(), "NOT_FOUND")


def test_wrong_method_returns_standard_405_with_allow_header(client: TestClient) -> None:
    response = client.post("/api/v1/health")
    assert response.status_code == 405
    _assert_standard_error(response.json(), "METHOD_NOT_ALLOWED")
    assert "GET" in response.headers["allow"]


def test_domain_error_codes_are_preserved(client: TestClient) -> None:
    response = client.get(f"/api/v1/generations/{uuid4()}")
    assert response.status_code == 404
    _assert_standard_error(response.json(), "GENERATION_NOT_FOUND")

    response = client.get(f"/api/v1/generations/{uuid4()}/events")
    assert response.status_code == 501
    _assert_standard_error(response.json(), "NOT_IMPLEMENTED")


def test_preflight_from_allowed_origin(client: TestClient) -> None:
    response = client.options(
        "/api/v1/generations",
        headers={"Origin": ALLOWED_ORIGIN, "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "access-control-allow-credentials" not in response.headers


def test_preflight_from_disallowed_origin(client: TestClient) -> None:
    response = client.options(
        "/api/v1/generations",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in response.headers


def test_simple_request_from_allowed_origin(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"Origin": ALLOWED_ORIGIN})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN


def test_origins_configurable_from_comma_separated_string(client_factory: ClientFactory) -> None:
    client = client_factory(frontend_origins="https://app.example.com, https://admin.example.com/")
    response = client.options(
        "/api/v1/generations",
        headers={"Origin": "https://admin.example.com", "Access-Control-Request-Method": "GET"},
    )
    assert response.headers["access-control-allow-origin"] == "https://admin.example.com"

    response = client.options(
        "/api/v1/generations",
        headers={"Origin": ALLOWED_ORIGIN, "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in response.headers


def test_origins_reject_wildcard() -> None:
    with pytest.raises(ValidationError):
        make_settings(frontend_origins="*")


def test_origins_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRONTEND_ORIGINS", "https://a.example.com,https://b.example.com")
    assert make_settings().frontend_origins == ["https://a.example.com", "https://b.example.com"]

"""Cliente LLM: factory, fake y adaptadores (transporte HTTP simulado, sin red ni mocks de librería)."""

import json
import sys
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from ai_service.clients.anthropic_llm import DEFAULT_MAX_TOKENS, AnthropicLlmClient
from ai_service.clients.llm import LlmRequest
from ai_service.clients.llm_factory import LlmClientFactory
from ai_service.clients.llm_fake import FakeLlmClient
from ai_service.clients.ollama_llm import OllamaLlmClient
from ai_service.clients.openai_llm import OpenAILlmClient
from ai_service.config import Settings
from ai_service.core.errors import (
    ConfigurationError,
    LlmContextLengthError,
    LlmError,
    LlmInvalidResponseError,
    LlmRateLimitError,
)
from ai_service.main import create_app
from tests.conftest import make_settings

Handler = Callable[[httpx.Request], httpx.Response]

REQUEST = LlmRequest(prompt="Genera casos", model="modelo-x", system="Eres QA", max_tokens=100, temperature=0.2)


def _recording(handler: Handler) -> tuple[list[httpx.Request], httpx.MockTransport]:
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return seen, httpx.MockTransport(wrapped)


def _openai(handler: Handler) -> tuple[list[httpx.Request], OpenAILlmClient]:
    seen, transport = _recording(handler)
    sdk = AsyncOpenAI(api_key="k", max_retries=0, http_client=httpx.AsyncClient(transport=transport))
    return seen, OpenAILlmClient(sdk)


def _anthropic(handler: Handler) -> tuple[list[httpx.Request], AnthropicLlmClient]:
    seen, transport = _recording(handler)
    sdk = AsyncAnthropic(api_key="k", max_retries=0, http_client=httpx.AsyncClient(transport=transport))
    return seen, AnthropicLlmClient(sdk)


def _ollama(handler: Handler) -> tuple[list[httpx.Request], OllamaLlmClient]:
    seen, transport = _recording(handler)
    return seen, OllamaLlmClient(httpx.AsyncClient(base_url="http://ollama.test", transport=transport))


def _body(request: httpx.Request) -> dict[str, Any]:
    return json.loads(request.content)


# --- Factory -----------------------------------------------------------------


def test_factory_builds_each_provider() -> None:
    cases = {
        "openai": (make_settings(llm_provider="openai", llm_api_key="k"), OpenAILlmClient),
        "anthropic": (make_settings(llm_provider="anthropic", llm_api_key="k"), AnthropicLlmClient),
        "ollama": (make_settings(llm_provider="ollama", llm_base_url="http://localhost:11434"), OllamaLlmClient),
    }
    for settings, expected in cases.values():
        assert isinstance(LlmClientFactory.create(settings), expected)


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_factory_requires_api_key(provider: str) -> None:
    with pytest.raises(ConfigurationError, match="LLM_API_KEY"):
        LlmClientFactory.create(make_settings(llm_provider=provider, llm_api_key=""))


def test_factory_requires_base_url_for_ollama() -> None:
    with pytest.raises(ConfigurationError, match="LLM_BASE_URL"):
        LlmClientFactory.create(make_settings(llm_provider="ollama", llm_base_url=""))


def test_factory_rejects_unknown_provider() -> None:
    settings = Settings.model_construct(llm_provider="gemini")
    with pytest.raises(ConfigurationError, match="openai, anthropic, ollama"):
        LlmClientFactory.create(settings)


def test_settings_reject_unknown_provider() -> None:
    with pytest.raises(ValueError):
        make_settings(llm_provider="gemini")


def test_factory_imports_are_lazy() -> None:
    """R-FA-3: importar la factory no carga ningún adaptador concreto."""
    code = (
        "import sys; import ai_service.clients.llm_factory; "
        "mods = [m for m in sys.modules if m.endswith('_llm') or m.split('.')[0] in ('openai', 'anthropic')]; "
        "print(mods)"
    )
    import subprocess

    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"


def test_app_startup_fails_without_llm_configuration(store: Any) -> None:
    from fastapi.testclient import TestClient

    from ai_service.repositories.in_memory import InMemoryDocumentsRepository, InMemoryGenerationsRepository
    from tests.factories import FakeDocumentStorage

    app = create_app(
        make_settings(llm_provider="openai", llm_api_key=""),
        generations_repository=InMemoryGenerationsRepository(store),
        documents_repository=InMemoryDocumentsRepository(store),
        documents_storage=FakeDocumentStorage(),
    )
    with pytest.raises(ConfigurationError), TestClient(app):
        pass


def test_injected_llm_client_is_exposed_and_not_closed(client: Any) -> None:
    llm = client.app.state.llm_client
    assert isinstance(llm, FakeLlmClient)
    assert llm.closed is False


# --- Fake --------------------------------------------------------------------


async def test_fake_returns_programmed_responses_in_order() -> None:
    fake = FakeLlmClient(["uno", LlmRateLimitError(), "dos"])
    assert (await fake.complete(REQUEST)).text == "uno"
    with pytest.raises(LlmRateLimitError):
        await fake.complete(REQUEST)
    assert (await fake.complete(REQUEST)).text == "dos"
    assert fake.requests == [REQUEST, REQUEST, REQUEST]
    with pytest.raises(AssertionError, match="no quedan respuestas"):
        await fake.complete(REQUEST)


# --- OpenAI ------------------------------------------------------------------


def _openai_ok(_: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "c1",
            "object": "chat.completion",
            "created": 0,
            "model": "modelo-x",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": '{"ok":1}'}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
        },
    )


async def test_openai_translates_request_and_response() -> None:
    seen, llm = _openai(_openai_ok)
    response = await llm.complete(REQUEST)
    body = _body(seen[0])
    assert body["model"] == "modelo-x"
    assert body["messages"] == [{"role": "system", "content": "Eres QA"}, {"role": "user", "content": "Genera casos"}]
    assert body["max_completion_tokens"] == 100
    assert body["temperature"] == 0.2
    assert (response.text, response.input_tokens, response.output_tokens) == ('{"ok":1}', 12, 5)
    assert response.latency_ms is not None


async def test_openai_passes_extra_parameters() -> None:
    seen, llm = _openai(_openai_ok)
    await llm.complete(LlmRequest(prompt="p", model="m", extra={"seed": 7}))
    body = _body(seen[0])
    assert body["seed"] == 7
    assert "max_completion_tokens" not in body and "temperature" not in body
    assert body["messages"] == [{"role": "user", "content": "p"}]


@pytest.mark.parametrize(
    ("status", "error", "expected"),
    [
        (429, {"message": "slow down", "type": "rate_limit"}, LlmRateLimitError),
        (400, {"message": "too long", "type": "invalid_request_error", "code": "context_length_exceeded"}, LlmContextLengthError),
        (400, {"message": "bad", "type": "invalid_request_error", "code": "other"}, LlmError),
        (500, {"message": "boom", "type": "server_error"}, LlmError),
    ],
)
async def test_openai_translates_errors(status: int, error: dict[str, str], expected: type[LlmError]) -> None:
    _, llm = _openai(lambda _: httpx.Response(status, json={"error": error}))
    with pytest.raises(expected) as info:
        await llm.complete(REQUEST)
    assert type(info.value) is expected


# --- Anthropic ---------------------------------------------------------------


def _anthropic_ok(_: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "m1",
            "type": "message",
            "role": "assistant",
            "model": "modelo-x",
            "content": [{"type": "text", "text": '{"ok":'}, {"type": "text", "text": "1}"}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 20, "output_tokens": 4},
        },
    )


async def test_anthropic_translates_request_and_response() -> None:
    seen, llm = _anthropic(_anthropic_ok)
    response = await llm.complete(REQUEST)
    body = _body(seen[0])
    assert body["system"] == "Eres QA"
    assert body["messages"] == [{"role": "user", "content": "Genera casos"}]
    assert (body["max_tokens"], body["temperature"]) == (100, 0.2)
    assert (response.text, response.input_tokens, response.output_tokens) == ('{"ok":1}', 20, 4)


async def test_anthropic_defaults_max_tokens_and_omits_system() -> None:
    seen, llm = _anthropic(_anthropic_ok)
    await llm.complete(LlmRequest(prompt="p", model="m"))
    body = _body(seen[0])
    assert body["max_tokens"] == DEFAULT_MAX_TOKENS
    assert "system" not in body and "temperature" not in body


@pytest.mark.parametrize(
    ("status", "message", "expected"),
    [
        (429, "rate limited", LlmRateLimitError),
        (400, "prompt is too long: 300000 tokens > 200000 maximum", LlmContextLengthError),
        (413, "request too large", LlmContextLengthError),
        (400, "bad request", LlmError),
        (529, "overloaded", LlmError),
    ],
)
async def test_anthropic_translates_errors(status: int, message: str, expected: type[LlmError]) -> None:
    payload = {"type": "error", "error": {"type": "x", "message": message}}
    _, llm = _anthropic(lambda _: httpx.Response(status, json=payload))
    with pytest.raises(expected) as info:
        await llm.complete(REQUEST)
    assert type(info.value) is expected


# --- Ollama ------------------------------------------------------------------


async def test_ollama_translates_request_and_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "modelo-x",
                "message": {"role": "assistant", "content": '{"ok":1}'},
                "done": True,
                "total_duration": 250_000_000,
                "prompt_eval_count": 30,
                "eval_count": 6,
            },
        )

    seen, llm = _ollama(handler)
    response = await llm.complete(LlmRequest(prompt="p", model="modelo-x", system="s", max_tokens=50, extra={"top_p": 0.9}))
    assert seen[0].url.path == "/api/chat"
    body = _body(seen[0])
    assert body["stream"] is False
    assert body["messages"][0] == {"role": "system", "content": "s"}
    assert body["options"] == {"top_p": 0.9, "num_predict": 50}
    assert (response.text, response.input_tokens, response.output_tokens, response.latency_ms) == ('{"ok":1}', 30, 6, 250)


async def test_ollama_unavailable_is_llm_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    _, llm = _ollama(handler)
    with pytest.raises(LlmError, match="Ollama no está disponible"):
        await llm.complete(REQUEST)


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (httpx.Response(429, json={"error": "busy"}), LlmRateLimitError),
        (httpx.Response(404, json={"error": "model not found"}), LlmError),
        (httpx.Response(200, text="no json"), LlmInvalidResponseError),
        (httpx.Response(200, json={"done": True}), LlmInvalidResponseError),
    ],
)
async def test_ollama_translates_errors(response: httpx.Response, expected: type[LlmError]) -> None:
    _, llm = _ollama(lambda _: response)
    with pytest.raises(expected) as info:
        await llm.complete(REQUEST)
    assert type(info.value) is expected

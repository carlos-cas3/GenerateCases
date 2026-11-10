"""Adaptador Ollama de `LlmClient` (`POST /api/chat` con `httpx`, D-LLM-2)."""

import time
from typing import Any

import httpx

from ai_service.clients.llm import LlmRequest, LlmResponse
from ai_service.core.errors import LlmError, LlmInvalidResponseError, LlmRateLimitError

_NS_PER_MS = 1_000_000


class OllamaLlmClient:
    """Implementación de `LlmClient` sobre un servidor Ollama local.

    Recibe un `httpx.AsyncClient` con `base_url` y `timeout` ya configurados
    (lo crea `LlmClientFactory`). `max_tokens`, `temperature` y `extra` van en
    `options` (`num_predict`, `temperature`, …), que es donde Ollama los espera.
    """

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def complete(self, request: LlmRequest) -> LlmResponse:
        messages: list[dict[str, str]] = []
        if request.system is not None:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})

        options: dict[str, Any] = dict(request.extra)
        if request.max_tokens is not None:
            options["num_predict"] = request.max_tokens
        if request.temperature is not None:
            options["temperature"] = request.temperature
        body: dict[str, Any] = {"model": request.model, "messages": messages, "stream": False}
        if options:
            body["options"] = options

        started = time.monotonic()
        try:
            response = await self._client.post("/api/chat", json=body)
            response.raise_for_status()
        except httpx.ConnectError as exc:
            raise LlmError(f"Ollama no está disponible en {self._client.base_url}.") from exc
        except httpx.TimeoutException as exc:
            raise LlmError("Ollama no respondió dentro del tiempo límite.") from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                raise LlmRateLimitError() from exc
            raise LlmError(
                f"Ollama rechazó la solicitud (HTTP {exc.response.status_code}): {_error_text(exc.response)}"
            ) from exc
        except httpx.HTTPError as exc:
            raise LlmError(f"Falló la llamada a Ollama: {exc}") from exc
        measured_ms = int((time.monotonic() - started) * 1000)

        try:
            payload = response.json()
            text = payload["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise LlmInvalidResponseError("Ollama devolvió una respuesta con formato inesperado.") from exc
        if not isinstance(text, str):
            raise LlmInvalidResponseError("Ollama devolvió una respuesta sin texto.")

        total_ns = payload.get("total_duration")
        return LlmResponse(
            text=text,
            input_tokens=payload.get("prompt_eval_count"),
            output_tokens=payload.get("eval_count"),
            latency_ms=total_ns // _NS_PER_MS if isinstance(total_ns, int) else measured_ms,
        )

    async def aclose(self) -> None:
        await self._client.aclose()


def _error_text(response: httpx.Response) -> str:
    try:
        return str(response.json().get("error", response.text))
    except ValueError:
        return response.text

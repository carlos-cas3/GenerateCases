"""Adaptador Anthropic de `LlmClient` (Messages API sobre `AsyncAnthropic`)."""

import time
from typing import Any

import anthropic
from anthropic import AsyncAnthropic

from ai_service.clients.llm import LlmRequest, LlmResponse
from ai_service.core.errors import LlmContextLengthError, LlmError, LlmInvalidResponseError, LlmRateLimitError

# La Messages API exige `max_tokens`; se usa este valor si la solicitud no lo fija.
DEFAULT_MAX_TOKENS = 4096

# Fragmento del mensaje con el que Anthropic rechaza (400) un prompt demasiado largo.
_CONTEXT_LENGTH_HINT = "prompt is too long"


class AnthropicLlmClient:
    """Implementación de `LlmClient` sobre la API de Anthropic.

    `LlmRequest.system` va al parámetro `system` de la API (D-LLM-1); el prompt
    va como único mensaje `user`.
    """

    def __init__(self, client: AsyncAnthropic) -> None:
        self._client = client

    async def complete(self, request: LlmRequest) -> LlmResponse:
        params: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_tokens if request.max_tokens is not None else DEFAULT_MAX_TOKENS,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        if request.system is not None:
            params["system"] = request.system
        if request.temperature is not None:
            params["temperature"] = request.temperature
        params.update(request.extra)

        started = time.monotonic()
        try:
            response = await self._client.messages.create(**params)
        except anthropic.RateLimitError as exc:
            raise LlmRateLimitError() from exc
        except anthropic.BadRequestError as exc:
            if _CONTEXT_LENGTH_HINT in str(exc.message).lower():
                raise LlmContextLengthError() from exc
            raise LlmError(f"Anthropic rechazó la solicitud: {exc.message}") from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code == 413:  # request_too_large
                raise LlmContextLengthError() from exc
            raise LlmError(f"Falló la llamada a Anthropic (HTTP {exc.status_code}).") from exc
        except anthropic.APITimeoutError as exc:
            raise LlmError("Anthropic no respondió dentro del tiempo límite.") from exc
        except anthropic.AnthropicError as exc:
            raise LlmError(f"Falló la llamada a Anthropic: {exc}") from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        text = "".join(block.text for block in response.content if block.type == "text")
        if not text:
            raise LlmInvalidResponseError("Anthropic devolvió una respuesta sin texto.")
        return LlmResponse(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=latency_ms,
        )

    async def aclose(self) -> None:
        await self._client.close()

"""Adaptador OpenAI de `LlmClient` (Chat Completions sobre `AsyncOpenAI`)."""

import time
from typing import Any

import openai
from openai import AsyncOpenAI

from ai_service.clients.llm import LlmRequest, LlmResponse
from ai_service.core.errors import LlmContextLengthError, LlmError, LlmInvalidResponseError, LlmRateLimitError

_CONTEXT_LENGTH_CODE = "context_length_exceeded"


class OpenAILlmClient:
    """Implementación de `LlmClient` sobre la API de OpenAI.

    Recibe el `AsyncOpenAI` ya construido (lo crea `LlmClientFactory`), así que
    los tests pueden pasarle un cliente con transporte simulado.
    """

    def __init__(self, client: AsyncOpenAI) -> None:
        self._client = client

    async def complete(self, request: LlmRequest) -> LlmResponse:
        messages: list[dict[str, str]] = []
        if request.system is not None:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})

        params: dict[str, Any] = {"model": request.model, "messages": messages}
        if request.max_tokens is not None:
            params["max_completion_tokens"] = request.max_tokens
        if request.temperature is not None:
            params["temperature"] = request.temperature
        params.update(request.extra)

        started = time.monotonic()
        try:
            response = await self._client.chat.completions.create(**params)
        except openai.RateLimitError as exc:
            raise LlmRateLimitError() from exc
        except openai.BadRequestError as exc:
            if exc.code == _CONTEXT_LENGTH_CODE:
                raise LlmContextLengthError() from exc
            raise LlmError(f"OpenAI rechazó la solicitud: {exc.message}") from exc
        except openai.APITimeoutError as exc:
            raise LlmError("OpenAI no respondió dentro del tiempo límite.") from exc
        except openai.OpenAIError as exc:
            raise LlmError(f"Falló la llamada a OpenAI: {exc}") from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        if not response.choices or response.choices[0].message.content is None:
            raise LlmInvalidResponseError("OpenAI devolvió una respuesta sin texto.")
        usage = response.usage
        return LlmResponse(
            text=response.choices[0].message.content,
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
            latency_ms=latency_ms,
        )

    async def aclose(self) -> None:
        await self._client.close()

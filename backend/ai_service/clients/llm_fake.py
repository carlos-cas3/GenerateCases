"""Fake determinista de `LlmClient` para tests (R-DI-3). No pasa por la factory (R-FA-6)."""

from collections.abc import Iterable

from ai_service.clients.llm import LlmRequest, LlmResponse
from ai_service.core.errors import LlmError


class FakeLlmClient:
    """Devuelve, en orden, las respuestas con las que se construyó.

    Cada elemento puede ser un texto (respuesta correcta) o una `LlmError`
    (se lanza al llegar su turno), para probar reintentos y fallos sin mocks.
    Las solicitudes recibidas quedan en `requests` para inspeccionarlas.
    """

    def __init__(self, responses: Iterable[str | LlmError] = ()) -> None:
        self._responses = list(responses)
        self.requests: list[LlmRequest] = []
        self.closed = False

    async def complete(self, request: LlmRequest) -> LlmResponse:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("FakeLlmClient: no quedan respuestas programadas.")
        item = self._responses.pop(0)
        if isinstance(item, LlmError):
            raise item
        return LlmResponse(
            text=item,
            input_tokens=len(request.prompt) // 4,  # estimación burda
            output_tokens=len(item) // 4,
            latency_ms=0,
        )

    async def aclose(self) -> None:
        self.closed = True

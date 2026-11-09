"""Fake determinista de `EmbeddingsClient` para tests (R-DI-3). No pasa por la factory (R-FA-6)."""

from collections.abc import Iterable

from ai_service.clients.embeddings import EmbeddingsRequest, EmbeddingsResponse
from ai_service.core.errors import EmbeddingsError


class FakeEmbeddingsClient:
    """Devuelve, en orden, las respuestas con las que se construyó.

    Cada elemento es un `EmbeddingsResponse` completo o una `EmbeddingsError` (se lanza al
    llegar su turno). A diferencia de `FakeLlmClient`, no recibe strings: la respuesta tiene
    campos (vectores, dimensión, modelo) que no se pueden inferir (P-4).
    Las solicitudes recibidas quedan en `requests` para inspeccionarlas.
    """

    def __init__(self, responses: Iterable[EmbeddingsResponse | EmbeddingsError] = ()) -> None:
        self._responses = list(responses)
        self.requests: list[EmbeddingsRequest] = []
        self.closed = False

    async def embed(self, request: EmbeddingsRequest) -> EmbeddingsResponse:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("FakeEmbeddingsClient: no quedan respuestas programadas.")
        item = self._responses.pop(0)
        if isinstance(item, EmbeddingsError):
            raise item
        return item

    async def aclose(self) -> None:
        self.closed = True

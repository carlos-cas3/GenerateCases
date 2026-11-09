"""Fake determinista de `ClusteringClient` para tests (R-DI-3). No pasa por la factory (R-FA-6)."""

from collections.abc import Iterable

from ai_service.clients.clustering import ClusteringRequest, ClusteringResult
from ai_service.core.errors import ClusteringError


class FakeClusteringClient:
    """Devuelve, en orden, los resultados con los que se construyó.

    Cada elemento es un `ClusteringResult` completo o una `ClusteringError` (se lanza al
    llegar su turno), por la misma razón que `FakeEmbeddingsClient` (P-4).
    Las solicitudes recibidas quedan en `requests` para inspeccionarlas.
    """

    def __init__(self, responses: Iterable[ClusteringResult | ClusteringError] = ()) -> None:
        self._responses = list(responses)
        self.requests: list[ClusteringRequest] = []
        self.closed = False

    async def cluster(self, request: ClusteringRequest) -> ClusteringResult:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("FakeClusteringClient: no quedan respuestas programadas.")
        item = self._responses.pop(0)
        if isinstance(item, ClusteringError):
            raise item
        return item

    async def aclose(self) -> None:
        self.closed = True

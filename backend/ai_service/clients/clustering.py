"""Puerto del cliente de clustering — contrato y DTOs, sin infraestructura (R-AP-2).

Lo usa P4 (ver `issue_resolver_embeddings.md`). Permite cambiar de algoritmo sin tocar
P4; lo implementan `hdbscan_clustering.py` y el fake (`clustering_fake.py`).
"""

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ClusteringRequest:
    """Solicitud de clustering. La construye P4 a partir de `P3Output` y `P4Config`."""

    vectors: tuple[tuple[float, ...], ...]  # vectores a agrupar (uno por RF)
    codes: tuple[str, ...]  # código RF correspondiente a cada vector
    metric: str  # métrica de distancia (cosine, euclidean...)
    # Parámetros específicos del algoritmo (min_cluster_size, min_samples, etc.).
    # dict: `frozen` no lo hace inmutable por dentro.
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ClusteringResult:
    """Resultado del clustering. Un label por vector; -1 indica outlier (sin cluster)."""

    labels: tuple[int, ...]  # label por vector, en el mismo orden que la solicitud
    algorithm: str  # nombre del algoritmo aplicado
    metric: str  # métrica usada
    # Parámetros efectivos aplicados (no solo los solicitados). Obligatorio a propósito (P-3).
    # dict: `frozen` no lo hace inmutable por dentro.
    params: dict[str, Any]


class ClusteringClient(Protocol):
    """Puerto de clustering semántico. Lo implementan los adaptadores y el fake."""

    async def cluster(self, request: ClusteringRequest) -> ClusteringResult:
        """Agrupa los vectores. Lanza `ClusteringError` ante fallos."""
        ...

    async def aclose(self) -> None:
        """Libera recursos. `main.py` lo llama al apagar (R-FA-7)."""
        ...

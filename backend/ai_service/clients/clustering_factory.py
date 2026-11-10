"""Factory del cliente de clustering (sección 6 de `architecture_patterns.md`, D-CLU-3).

Solo la llama `main.py` (R-FA-5); P4 recibe el `ClusteringClient` ya construido.
Imports lazy (R-FA-3). Solo falla si el algoritmo no es reconocido (D-CLU-4).
"""

from ai_service.clients.clustering import ClusteringClient
from ai_service.config import Settings
from ai_service.core.errors import ConfigurationError

SUPPORTED_ALGORITHMS: tuple[str, ...] = ("hdbscan",)


class ClusteringClientFactory:
    """Construye el `ClusteringClient` correcto según `Settings.clustering_algorithm`."""

    @staticmethod
    def create(settings: Settings) -> ClusteringClient:
        match settings.clustering_algorithm:
            case "hdbscan":
                from ai_service.clients.hdbscan_clustering import HDBSCANClusteringClient

                return HDBSCANClusteringClient()
            case _:
                raise ConfigurationError(
                    f"Algoritmo de clustering no soportado: {settings.clustering_algorithm!r}. "
                    f"Valores válidos: {', '.join(SUPPORTED_ALGORITHMS)}."
                )

"""Adaptador HDBSCAN de `ClusteringClient` (D-CLU-2). Label -1 = outlier (RF sin cluster)."""

import asyncio
from typing import Any

import hdbscan
import numpy as np

from ai_service.clients.clustering import ClusteringRequest, ClusteringResult
from ai_service.core.errors import ClusteringError

ALGORITHM_NAME = "hdbscan"

# Los árboles KD/Ball de hdbscan no admiten coseno: con esa métrica hace falta el algoritmo genérico.
_METRICS_REQUIRING_GENERIC = frozenset({"cosine"})

_JSON_SCALARS = (str, int, float, bool, type(None))


class HDBSCANClusteringClient:
    """Implementación de `ClusteringClient` con la librería `hdbscan`.

    Sin estado entre llamadas: cada `cluster()` crea su estimador con la métrica y los
    parámetros de la solicitud. La librería es síncrona y consume CPU: se ejecuta en un hilo.
    """

    async def cluster(self, request: ClusteringRequest) -> ClusteringResult:
        if len(request.vectors) != len(request.codes):
            raise ClusteringError(
                "El número de vectores no coincide con el de códigos RF.",
                details={"vectors": len(request.vectors), "codes": len(request.codes)},
            )
        if not request.vectors:
            return ClusteringResult(labels=(), algorithm=ALGORITHM_NAME, metric=request.metric, params=dict(request.params))
        return await asyncio.to_thread(_cluster_sync, request)

    async def aclose(self) -> None:
        """No-op: el adaptador no mantiene recursos."""


def _cluster_sync(request: ClusteringRequest) -> ClusteringResult:
    params: dict[str, Any] = dict(request.params)
    if request.metric in _METRICS_REQUIRING_GENERIC:
        params.setdefault("algorithm", "generic")
    try:
        estimator = hdbscan.HDBSCAN(metric=request.metric, **params)
        data = np.asarray(request.vectors, dtype=np.float64)
        labels = estimator.fit_predict(data)
    except Exception as exc:  # hdbscan/sklearn lanzan ValueError, TypeError… (R-AP-4)
        raise ClusteringError(
            "Falló el algoritmo HDBSCAN.", details={"metric": request.metric, "reason": str(exc)}
        ) from exc
    return ClusteringResult(
        labels=tuple(int(label) for label in labels),
        algorithm=ALGORITHM_NAME,
        metric=request.metric,
        params=_effective_params(estimator),
    )


def _effective_params(estimator: Any) -> dict[str, Any]:
    """Parámetros efectivos tras el ajuste (P-3), solo los serializables a JSON."""
    return {
        name: value
        for name, value in estimator.get_params(deep=False).items()
        if isinstance(value, _JSON_SCALARS) and name != "metric"
    }

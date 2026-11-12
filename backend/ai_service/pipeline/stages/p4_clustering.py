"""P4 — Clustering semántico de los RF (Fase 5).

1. Lee los RF (`context.p2_output`) y sus vectores (`context.p3_output`); `P4Input` valida que
   se correspondan exactamente.
2. Agrupa los vectores vía `ClusteringClient` con la métrica y parámetros de `P4Config`.
3. Cada label `>= 0` → `SemanticCluster` llamado `"Cluster {label}"` (D-A; P5 le da el nombre con
   sentido). Label `-1` → `unassigned_requirement_codes`. Con HDBSCAN la membresía es única (R6;
   D-31 diferido).
4. Calcula `similarity_to_centroid` (coseno de cada RF al centroide de su cluster, D-B): P4 es la
   última etapa con los vectores (D-09). Es descriptiva; no decide la membresía.
5. D-32: si no se forma ningún cluster (o hay menos RF que el piso `min_cluster_size`), todos
   los RF quedan sin asignar y la etapa termina `completed` con aviso `INSUFFICIENT_REQUIREMENTS`.
6. Persiste con `persist_p4_clusters` y deja el resultado en `context.p4_output`.
"""

import logging
import math
from collections import defaultdict
from collections.abc import Sequence
from typing import Any, ClassVar
from uuid import uuid4

from pydantic import ValidationError

from ai_service.clients.clustering import ClusteringClient, ClusteringRequest, ClusteringResult
from ai_service.core.errors import ClusteringError, PersistenceError
from ai_service.pipeline.context import PipelineContext
from ai_service.pipeline.contracts.p4 import (
    ClusterAssignment,
    ClusteringAlgorithmInfo,
    P4Config,
    P4Input,
    P4Output,
    SemanticCluster,
)
from ai_service.pipeline.stages.base import StageBase, StageError, StageResult, StubStage
from ai_service.repositories.pipeline_results import PipelineResultsRepository
from ai_service.schemas.generations import StageKey, StageWarning

logger = logging.getLogger(__name__)

ERROR_CODE = "CLUSTERING_FAILED"
NOISE_LABEL = -1
SIMILARITY_DECIMALS = 6


class ClusteringStage(StageBase):
    """P4 real. Recibe `ClusteringClient`, su configuración y el repositorio por constructor (R-DI-2)."""

    key: ClassVar[StageKey] = StageKey.P4
    requires_clustering: ClassVar[bool] = True

    def __init__(
        self,
        *,
        clustering_client: ClusteringClient,
        config: P4Config,
        results: PipelineResultsRepository,
    ) -> None:
        self._client = clustering_client
        self._config = config
        self._results = results

    async def run(self, context: PipelineContext) -> StageResult:
        if context.p2_output is None or context.p3_output is None:
            raise RuntimeError("P4 requiere p2_output y p3_output: P2 o P3 no se ejecutaron")
        try:
            p4_input = P4Input(
                generation_id=context.generation_id,
                requirements=context.p2_output.requirements,
                embeddings=context.p3_output,
                config=self._config,
            )
        except ValidationError as exc:
            raise StageError(
                ERROR_CODE, "Los vectores de P3 no corresponden a los RF de P2.", details={"errors": exc.error_count()}
            ) from exc

        # Mismo orden para vectores y códigos: el de P3.
        codes = tuple(item.requirement_code for item in p4_input.embeddings.embeddings)
        vectors = tuple(item.vector for item in p4_input.embeddings.embeddings)

        min_cluster_size = self._config.params.get("min_cluster_size")
        if isinstance(min_cluster_size, int) and len(codes) < min_cluster_size:
            # D-32: con menos RF que el piso no se puede formar ningún cluster; no se llama al algoritmo.
            labels = (NOISE_LABEL,) * len(codes)
            algorithm, metric, params = self._config.algorithm, self._config.metric, dict(self._config.params)
        else:
            result = await self._cluster(vectors, codes)
            labels, algorithm, metric, params = result.labels, result.algorithm, result.metric, dict(result.params)

        clusters, unassigned = _build_clusters(codes, vectors, labels)
        algorithm_info = ClusteringAlgorithmInfo(
            name=algorithm, metric=metric, params=params, embedding_model=p4_input.embeddings.model_info
        )
        try:
            output = P4Output(clusters=clusters, unassigned_requirement_codes=unassigned, algorithm_info=algorithm_info)
        except ValidationError as exc:
            raise StageError(
                ERROR_CODE, "El resultado del clustering no es consistente.", details={"errors": exc.error_count()}
            ) from exc

        try:
            await self._results.persist_p4_clusters(context.generation_id, output.to_rpc_payload())
        except PersistenceError as exc:
            raise StageError(exc.code, exc.message, retryable=True, details=exc.details or None) from exc

        context.p4_output = output
        logger.info(
            "P4 completada generation_id=%s clusters=%s sin_cluster=%s",
            context.generation_id, len(clusters), len(unassigned),
        )
        return StageResult(
            warnings=_warnings(clusters, unassigned, len(codes), min_cluster_size),
            runtime_info={
                "algorithm_info": algorithm_info.model_dump(mode="json"),
                "requirements_count": len(codes),
                "clusters": len(clusters),
                "unassigned": len(unassigned),
                "cluster_sizes": {cluster.name: len(cluster.assignments) for cluster in clusters},
            },
        )

    async def _cluster(self, vectors: tuple[tuple[float, ...], ...], codes: tuple[str, ...]) -> ClusteringResult:
        request = ClusteringRequest(
            vectors=vectors, codes=codes, metric=self._config.metric, params=dict(self._config.params)
        )
        try:
            result = await self._client.cluster(request)
        except ClusteringError as exc:
            raise StageError(ERROR_CODE, exc.message, retryable=True, details=exc.details or None) from exc
        if len(result.labels) != len(codes):
            raise StageError(
                ERROR_CODE, "El algoritmo de clustering devolvió un número de labels inesperado.",
                details={"expected": len(codes), "received": len(result.labels)},
            )
        return result


def _build_clusters(
    codes: Sequence[str], vectors: Sequence[Sequence[float]], labels: Sequence[int]
) -> tuple[tuple[SemanticCluster, ...], tuple[str, ...]]:
    members: dict[int, list[int]] = defaultdict(list)
    unassigned: list[str] = []
    for index, label in enumerate(labels):
        if label < 0:  # HDBSCAN: -1 = ruido (RF sin cluster)
            unassigned.append(codes[index])
        else:
            members[label].append(index)

    clusters: list[SemanticCluster] = []
    for label in sorted(members):
        indexes = members[label]
        centroid = _centroid([vectors[i] for i in indexes])
        clusters.append(
            SemanticCluster(
                id=uuid4(),
                label=label,
                name=f"Cluster {label}",  # D-A: placeholder; P5 le da el nombre con sentido
                assignments=tuple(
                    ClusterAssignment(
                        requirement_code=codes[i], similarity_to_centroid=_cosine(vectors[i], centroid)
                    )
                    for i in indexes
                ),
            )
        )
    return tuple(clusters), tuple(unassigned)


def _centroid(vectors: Sequence[Sequence[float]]) -> tuple[float, ...]:
    count = len(vectors)
    return tuple(sum(components) / count for components in zip(*vectors, strict=True))


def _cosine(a: Sequence[float], b: Sequence[float]) -> float | None:
    """Similitud coseno (D-B). `None` si algún vector es nulo (no hay dirección que comparar)."""
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    if norm == 0:
        return None
    value = sum(x * y for x, y in zip(a, b, strict=True)) / norm
    return round(max(-1.0, min(1.0, value)), SIMILARITY_DECIMALS)


def _warnings(
    clusters: Sequence[SemanticCluster], unassigned: Sequence[str], total: int, min_cluster_size: Any
) -> tuple[StageWarning, ...]:
    if not clusters:
        return (
            StageWarning(
                code="INSUFFICIENT_REQUIREMENTS",
                message="No se pudo formar ningún cluster: todos los RF quedan sin cluster.",
                details={"requirements_count": total, "min_cluster_size": min_cluster_size},
            ),
        )
    if unassigned:
        # D-36: se guardan y se muestran, pero no generarán casos de prueba.
        return (
            StageWarning(
                code="UNASSIGNED_REQUIREMENTS",
                message=f"{len(unassigned)} RF no pertenecen a ningún cluster.",
                details={"requirement_codes": list(unassigned)},
            ),
        )
    return ()


class ClusteringStubStage(StubStage):
    """P4 simulada (Fase 1). Se usa con `PIPELINE_STAGES=stub` y en tests del orquestador."""

    key: ClassVar[StageKey] = StageKey.P4
    requires_clustering: ClassVar[bool] = True

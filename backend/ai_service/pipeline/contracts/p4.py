"""Contratos de P4 — Clustering semántico (`pipeline_design.md`, P4)."""

import math
from typing import Any
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from ai_service.pipeline.contracts.common import ContractModel, NonEmptyStr, RequirementCode, ensure_unique
from ai_service.pipeline.contracts.p2 import FunctionalRequirement
from ai_service.pipeline.contracts.p3 import EmbeddingModelInfo, P3Output


class ClusterAssignment(ContractModel):
    """Pertenencia de un RF a un cluster (`cluster_requirements`). No implica cobertura ni duplicidad."""

    requirement_code: RequirementCode
    similarity_to_centroid: float | None = None

    @field_validator("similarity_to_centroid")
    @classmethod
    def _finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("similarity_to_centroid debe ser finita")
        return value


class SemanticCluster(ContractModel):
    """Grupo semántico. Lo produce P4; lo consume P5. Tablas `clusters` + `cluster_requirements`.

    `label` → columna `cluster_label`. `id` es obligatorio: `persist_p4_clusters` lo exige.
    """

    id: UUID
    label: int
    name: NonEmptyStr
    description: str | None = None
    assignments: tuple[ClusterAssignment, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique(self) -> "SemanticCluster":
        ensure_unique((item.requirement_code for item in self.assignments), f"RF del cluster {self.label}")
        return self


class ClusteringAlgorithmInfo(ContractModel):
    """Algoritmo aplicado, para reproducibilidad. Se refleja en `runtime_info` de P4 (D-34)."""

    name: NonEmptyStr
    metric: NonEmptyStr
    # dict: `frozen` no lo hace inmutable por dentro.
    params: dict[str, Any] = Field(default_factory=dict)
    embedding_model: EmbeddingModelInfo


class P4Config(ContractModel):
    """Configuración de P4 (servidor, R8)."""

    algorithm: NonEmptyStr
    metric: NonEmptyStr
    # dict: `frozen` no lo hace inmutable por dentro.
    params: dict[str, Any] = Field(default_factory=dict)


class P4Input(ContractModel):
    """Entrada de P4: RF de P2Output y vectores de P3Output, que deben corresponderse exactamente."""

    generation_id: UUID
    requirements: tuple[FunctionalRequirement, ...] = Field(min_length=1)
    embeddings: P3Output
    config: P4Config

    @model_validator(mode="after")
    def _embeddings_match(self) -> "P4Input":
        ensure_unique((item.code for item in self.requirements), "códigos de RF")
        requirement_codes = {item.code for item in self.requirements}
        embedding_codes = {item.requirement_code for item in self.embeddings.embeddings}
        if requirement_codes != embedding_codes:
            raise ValueError(
                "EMBEDDING_REQUIREMENT_MISMATCH: "
                f"sin vector {sorted(requirement_codes - embedding_codes)}, "
                f"vector sin RF {sorted(embedding_codes - requirement_codes)}"
            )
        return self


class P4Output(ContractModel):
    """Salida de P4. La consume P5. Se persiste con `persist_p4_clusters` (ver `to_rpc_payload`).

    Un RF puede estar en varios clusters (R6); P5 elige en cuál es objetivo (D-31). Los RF sin
    cluster van en `unassigned_requirement_codes` (D-32) y no generan casos de prueba.
    Que todo RF de la entrada aparezca en alguno de los dos lados lo garantiza la etapa.
    """

    clusters: tuple[SemanticCluster, ...] = ()
    unassigned_requirement_codes: tuple[RequirementCode, ...] = ()
    algorithm_info: ClusteringAlgorithmInfo

    @model_validator(mode="after")
    def _consistent(self) -> "P4Output":
        ensure_unique((item.label for item in self.clusters), "labels de cluster")
        ensure_unique((item.id for item in self.clusters), "ids de cluster")
        ensure_unique(self.unassigned_requirement_codes, "unassigned_requirement_codes")
        both = self.assigned_requirement_codes() & set(self.unassigned_requirement_codes)
        if both:
            raise ValueError(f"RF asignados y sin asignar a la vez: {sorted(both)}")
        return self

    def assigned_requirement_codes(self) -> set[str]:
        """Códigos de RF que pertenecen a algún cluster."""
        return {item.requirement_code for cluster in self.clusters for item in cluster.assignments}

    def to_rpc_payload(self) -> dict[str, Any]:
        """`p_payload` de `persist_p4_clusters`. `generation_id` va aparte (`p_generation_id`)."""
        return {
            "clusters": [
                {
                    "id": str(cluster.id),
                    "name": cluster.name,
                    "description": cluster.description,
                    "cluster_label": cluster.label,
                    "assignments": [item.model_dump(mode="json") for item in cluster.assignments],
                }
                for cluster in self.clusters
            ],
            "unassigned_requirement_codes": list(self.unassigned_requirement_codes),
        }

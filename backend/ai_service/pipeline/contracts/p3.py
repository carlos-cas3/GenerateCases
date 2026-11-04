"""Contratos de P3 — Generación de embeddings (`pipeline_design.md`, P3). Sin tabla (D-09)."""

import math
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from ai_service.pipeline.contracts.common import ContractModel, NonEmptyStr, RequirementCode, ensure_unique
from ai_service.pipeline.contracts.p2 import FunctionalRequirement


class EmbeddingModelInfo(ContractModel):
    """Modelo de embeddings usado. Se refleja en `generation_stages.runtime_info` de P3 (D-34)."""

    provider: NonEmptyStr
    model_name: NonEmptyStr
    model_version: str | None = None
    dimension: int = Field(gt=0)
    normalized: bool
    input_template: NonEmptyStr


class RequirementEmbedding(ContractModel):
    """Vector de un RF. Lo produce P3; lo consume P4. Solo en memoria."""

    requirement_code: RequirementCode
    vector: tuple[float, ...] = Field(min_length=1)

    @field_validator("vector")
    @classmethod
    def _finite(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if not all(math.isfinite(component) for component in value):
            raise ValueError("el vector contiene NaN o infinitos")
        return value


class P3Config(ContractModel):
    """Configuración de P3 (servidor, R8)."""

    model_name: NonEmptyStr
    normalize: bool
    input_template: NonEmptyStr
    batch_size: int = Field(gt=0)


class P3Input(ContractModel):
    """Entrada de P3: los RF de P2Output. P3 está `skipped` sin clustering o sin RF (R2, D-29)."""

    generation_id: UUID
    requirements: tuple[FunctionalRequirement, ...] = Field(min_length=1)
    config: P3Config

    @model_validator(mode="after")
    def _unique(self) -> "P3Input":
        ensure_unique((item.code for item in self.requirements), "códigos de RF")
        return self


class P3Output(ContractModel):
    """Salida de P3 (el `EmbeddingSet` del diseño): un vector por RF. La consume P4."""

    model_info: EmbeddingModelInfo
    embeddings: tuple[RequirementEmbedding, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _uniform(self) -> "P3Output":
        ensure_unique((item.requirement_code for item in self.embeddings), "embeddings de RF")
        wrong = [e.requirement_code for e in self.embeddings if len(e.vector) != self.model_info.dimension]
        if wrong:
            raise ValueError(f"vectores con dimensión distinta de {self.model_info.dimension}: {wrong}")
        return self

"""Esquemas HTTP de generaciones, alineados con `docs/openapi.yaml`."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GenerationStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class StageKey(StrEnum):
    P1 = "p1"
    P2 = "p2"
    P3 = "p3"
    P4 = "p4"
    P5 = "p5"
    P6 = "p6"
    P7 = "p7"


ACTIVE_GENERATION_STATUSES: frozenset[GenerationStatus] = frozenset(
    {GenerationStatus.QUEUED, GenerationStatus.RUNNING}
)


class GenerationConfiguration(BaseModel):
    """Parámetros de la ejecución (`clustering_enabled`, `method_type`, `config_snapshot`)."""

    model_config = ConfigDict(extra="forbid")

    semantic_clustering_enabled: bool = Field(default=True, strict=True)
    method_type: str | None = Field(
        default=None,
        description="Método de generación. Si se omite se aplica el valor por defecto del servidor.",
    )

    @field_validator("method_type", mode="before")
    @classmethod
    def _reject_explicit_null(cls, value: object) -> object:
        """El contrato define `method_type` como string: `null` explícito no es válido."""
        if value is None:
            raise ValueError("method_type debe ser un texto.")
        return value


class CreateGenerationRequest(BaseModel):
    """Cuerpo de `POST /api/v1/generations`."""

    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    configuration: GenerationConfiguration = Field(default_factory=GenerationConfiguration)


class GenerationStage(BaseModel):
    """Etapa P1–P7. `name` proviene del catálogo del código."""

    key: StageKey
    name: str
    status: StageStatus
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    order: int = Field(ge=1, le=7)


class MetricSummary(BaseModel):
    metric_name: str
    metric_value: float | None
    formula_version: str


class GenerationSummary(BaseModel):
    """Conteos calculados desde datos persistidos. No se usa en la Fase 1 (`summary = null`)."""

    user_stories_count: int | None = None
    requirements_count: int | None = None
    clusters_count: int | None = None
    test_cases_count: int | None = None
    validated_relations_count: int | None = None
    metrics: list[MetricSummary] = Field(default_factory=list)


class Generation(BaseModel):
    """Generación con su configuración y sus siete etapas."""

    id: UUID
    document_id: UUID
    document_name: str
    status: GenerationStatus
    configuration: GenerationConfiguration
    stages: list[GenerationStage]
    summary: GenerationSummary | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class Pagination(BaseModel):
    limit: int
    offset: int
    total: int


class GenerationList(BaseModel):
    items: list[Generation]
    pagination: Pagination

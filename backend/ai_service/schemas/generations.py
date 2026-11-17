"""Esquemas HTTP de generaciones, alineados con `docs/openapi.yaml`."""

from datetime import datetime
from enum import StrEnum
from typing import Any
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


class StageWarning(BaseModel):
    """Aviso no bloqueante de una etapa (`generation_stages.warnings`)."""

    model_config = ConfigDict(frozen=True)

    code: str
    message: str
    details: dict[str, Any] | None = None


class LlmRun(BaseModel):
    """Una llamada al LLM (`generation_stages.llm_runs`). Solo P2 y P6."""

    model_config = ConfigDict(frozen=True)

    provider: str
    model: str
    prompt_version: str
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    attempts: int = Field(ge=1)
    latency_ms: int | None = Field(default=None, ge=0)
    unit_id: str | None = None


class GenerationStage(BaseModel):
    """Etapa P1–P7. `name` proviene del catálogo del código."""

    key: StageKey
    name: str
    status: StageStatus
    error_message: str | None
    error_code: str | None = None
    warnings: list[StageWarning] = Field(default_factory=list)
    llm_runs: list[LlmRun] = Field(default_factory=list)
    runtime_info: dict[str, Any] | None = None
    started_at: datetime | None
    completed_at: datetime | None
    order: int = Field(ge=1, le=7)


class GenerationSummary(BaseModel):
    """Conteos de la generación (D-F7-8). Se escribe al completar el pipeline; `null` hasta entonces.

    - `user_stories_count`, `requirements_count`, `clusters_count`, `test_cases_count`: filas
      persistidas de la generación (`clusters_count` es 0 con `by_user_story`).
    - `test_cases_failed_units`: unidades de P6 en `P6Output.failed_units`.

    Los conteos de relaciones validadas y las métricas quedan para P7 (Fase 8).
    """

    user_stories_count: int = Field(ge=0)
    requirements_count: int = Field(ge=0)
    clusters_count: int = Field(ge=0)
    test_cases_count: int = Field(ge=0)
    test_cases_failed_units: int = Field(ge=0)


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

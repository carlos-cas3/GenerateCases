"""Eventos internos de progreso del pipeline (no son mensajes HTTP)."""

from datetime import datetime
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ai_service.core.time import utc_now
from ai_service.schemas.generations import StageKey


class _Event(BaseModel):
    model_config = ConfigDict(frozen=True)

    generation_id: UUID
    occurred_at: datetime = Field(default_factory=utc_now)


class StageStarted(_Event):
    type: Literal["stage_started"] = "stage_started"
    stage_key: StageKey


class StageCompleted(_Event):
    type: Literal["stage_completed"] = "stage_completed"
    stage_key: StageKey


class StageSkipped(_Event):
    type: Literal["stage_skipped"] = "stage_skipped"
    stage_key: StageKey


class StageFailed(_Event):
    type: Literal["stage_failed"] = "stage_failed"
    stage_key: StageKey
    error_message: str


class PipelineCompleted(_Event):
    type: Literal["pipeline_completed"] = "pipeline_completed"


class PipelineFailed(_Event):
    type: Literal["pipeline_failed"] = "pipeline_failed"
    error_message: str


PipelineEvent = Annotated[
    StageStarted | StageCompleted | StageSkipped | StageFailed | PipelineCompleted | PipelineFailed,
    Field(discriminator="type"),
]


class ProgressReporter(Protocol):
    """Receptor de eventos. Si `report` lanza, el orquestador se detiene (escritura no registrada)."""

    async def report(self, event: PipelineEvent) -> None: ...

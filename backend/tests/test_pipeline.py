"""Pruebas unitarias del orquestador y del servicio de ejecución."""

from uuid import uuid4

from ai_service.core.errors import InvalidStateTransition
from ai_service.pipeline.context import PipelineConfiguration, PipelineContext
from ai_service.pipeline.events import PipelineEvent
from ai_service.pipeline.orchestrator import PipelineOrchestrator
from ai_service.pipeline.stages import StageBase, StageError, StageResult, build_stub_stages
from ai_service.repositories.in_memory import InMemoryGenerationsRepository
from ai_service.schemas.generations import GenerationStatus, LlmRun, StageKey, StageStatus, StageWarning
from ai_service.services.pipeline_runs import INTERNAL_FAILURE_MESSAGE, PipelineRunService
from tests.conftest import DOCUMENT_ID
from tests.factories import add_generation


class RecordingReporter:
    def __init__(self) -> None:
        self.events: list[PipelineEvent] = []

    async def report(self, event: PipelineEvent) -> None:
        self.events.append(event)


def _context(clustering: bool = True) -> PipelineContext:
    return PipelineContext(
        generation_id=uuid4(),
        document_id=DOCUMENT_ID,
        configuration=PipelineConfiguration(clustering_enabled=clustering, method_type="llm_pipeline"),
    )


def _summary(events: list[PipelineEvent]) -> list[str]:
    return [f"{e.type}:{getattr(e, 'stage_key', '')}" for e in events]


async def test_orchestrator_event_sequence_without_clustering() -> None:
    reporter = RecordingReporter()
    ok = await PipelineOrchestrator(build_stub_stages(0), reporter).run(_context(clustering=False))

    assert ok is True
    assert _summary(reporter.events) == [
        "stage_started:p1", "stage_completed:p1",
        "stage_started:p2", "stage_completed:p2",
        "stage_skipped:p3", "stage_skipped:p4",
        "stage_started:p5", "stage_completed:p5",
        "stage_started:p6", "stage_completed:p6",
        "stage_started:p7", "stage_completed:p7",
        "pipeline_completed:",
    ]


async def test_orchestrator_stops_after_failure() -> None:
    reporter = RecordingReporter()
    ok = await PipelineOrchestrator(build_stub_stages(0, "p2"), reporter).run(_context())

    assert ok is False
    assert _summary(reporter.events) == [
        "stage_started:p1", "stage_completed:p1", "stage_started:p2", "stage_failed:p2", "pipeline_failed:",
    ]


class FlakyRepository(InMemoryGenerationsRepository):
    """Falla la escritura que marca `running` la etapa P3."""

    async def update_stage(self, generation_id, stage_key, **kwargs):
        if stage_key.value == "p3" and kwargs["status"] == StageStatus.RUNNING:
            raise ConnectionError("supabase caído")
        await super().update_stage(generation_id, stage_key, **kwargs)


async def test_failed_state_write_marks_generation_failed(store) -> None:
    repo = FlakyRepository(store)
    generation_id = add_generation(store, document_id=DOCUMENT_ID, status=GenerationStatus.QUEUED)
    context = _context()
    context.generation_id = generation_id

    await PipelineRunService(repo, build_stub_stages(0)).run(context)

    record = await repo.get_by_id(generation_id)
    assert record.status == GenerationStatus.FAILED
    assert record.error_message == INTERNAL_FAILURE_MESSAGE
    assert record.completed_at is not None
    statuses = {s.stage_key.value: s.status for s in record.stages}
    assert statuses["p2"] == StageStatus.COMPLETED
    assert statuses["p3"] == StageStatus.PENDING


async def test_guarded_update_rejects_invalid_transition(store) -> None:
    repo = InMemoryGenerationsRepository(store)
    generation_id = add_generation(store, document_id=DOCUMENT_ID, status=GenerationStatus.COMPLETED)

    try:
        await repo.update_generation_status(
            generation_id, expected={GenerationStatus.RUNNING}, status=GenerationStatus.FAILED
        )
    except InvalidStateTransition:
        pass
    else:
        raise AssertionError("se esperaba InvalidStateTransition")
    assert (await repo.get_by_id(generation_id)).status == GenerationStatus.COMPLETED


async def test_run_does_not_reopen_final_generation(store) -> None:
    repo = InMemoryGenerationsRepository(store)
    generation_id = add_generation(store, document_id=DOCUMENT_ID, status=GenerationStatus.FAILED)
    context = _context()
    context.generation_id = generation_id

    await PipelineRunService(repo, build_stub_stages(0)).run(context)

    record = await repo.get_by_id(generation_id)
    assert record.status == GenerationStatus.FAILED
    assert all(s.status == StageStatus.PENDING for s in record.stages)


class _P2Without(StageBase):
    """P2 que no extrae requisitos (D-29) o que falla con un `StageError` controlado."""

    key = StageKey.P2

    def __init__(self, *, error: StageError | None = None) -> None:
        self._error = error

    async def run(self, context):
        if self._error is not None:
            raise self._error
        return StageResult(
            warnings=(StageWarning(code="NO_REQUIREMENTS_EXTRACTED", message="Ninguna HU produjo requisitos."),),
            llm_runs=(LlmRun(provider="fake", model="m", prompt_version="v1", attempts=1),),
            runtime_info={"model": "m"},
            skip_remaining=True,
        )


def _stages_with(p2: StageBase) -> list[StageBase]:
    return [p2 if stage.key.value == "p2" else stage for stage in build_stub_stages(0)]


async def test_zero_requirements_skips_remaining_stages(store) -> None:
    repo = InMemoryGenerationsRepository(store)
    generation_id = add_generation(store, document_id=DOCUMENT_ID, status=GenerationStatus.QUEUED)
    context = _context()
    context.generation_id = generation_id

    await PipelineRunService(repo, _stages_with(_P2Without())).run(context)

    record = await repo.get_by_id(generation_id)
    assert record.status == GenerationStatus.COMPLETED
    stages = {s.stage_key.value: s for s in record.stages}
    assert stages["p1"].status == stages["p2"].status == StageStatus.COMPLETED
    assert all(stages[k].status == StageStatus.SKIPPED for k in ("p3", "p4", "p5", "p6", "p7"))
    assert [w.code for w in stages["p2"].warnings] == ["NO_REQUIREMENTS_EXTRACTED"]
    assert stages["p2"].llm_runs[0].model == "m"
    assert stages["p2"].runtime_info == {"model": "m"}


async def test_stage_error_code_and_message_are_persisted(store) -> None:
    repo = InMemoryGenerationsRepository(store)
    generation_id = add_generation(store, document_id=DOCUMENT_ID, status=GenerationStatus.QUEUED)
    context = _context()
    context.generation_id = generation_id
    error = StageError("LLM_INVALID_OUTPUT", "La respuesta del LLM no cumple el formato esperado.")

    await PipelineRunService(repo, _stages_with(_P2Without(error=error))).run(context)

    record = await repo.get_by_id(generation_id)
    assert record.status == GenerationStatus.FAILED
    p2 = next(s for s in record.stages if s.stage_key.value == "p2")
    assert p2.status == StageStatus.FAILED
    assert p2.error_code == "LLM_INVALID_OUTPUT"
    assert p2.error_message == error.message
    assert all(s.status == StageStatus.PENDING for s in record.stages if s.stage_order > 2)

"""Ciclo de vida de `generations`/`generation_stages` contra Supabase real (T-F8-04 a T-F8-06)."""

from typing import Any
from uuid import UUID

import pytest

from ai_service.core.errors import GenerationInProgress, InvalidStateTransition
from ai_service.core.time import utc_now
from ai_service.repositories.supabase_generations import SupabaseGenerationsRepository
from ai_service.repositories.supabase_pipeline_results import SupabasePipelineResultsRepository
from ai_service.schemas.generations import GenerationStatus, GenerationSummary, StageKey, StageStatus
from tests.conftest_integration import GenerationTracker, RowsReader
from tests.integration import payloads

pytestmark = pytest.mark.integration

_CHILD_TABLES = (
    "generation_stages",
    "user_stories",
    "functional_requirements",
    "user_story_requirements",
    "clusters",
    "cluster_requirements",
    "unassigned_requirements",
    "test_cases",
    "test_steps",
    "requirement_test_cases",
)


async def _complete(repo: SupabaseGenerationsRepository, generation_id: UUID) -> None:
    """Lleva la generación a `completed` por las transiciones guardadas."""
    await repo.update_generation_status(
        generation_id, expected={GenerationStatus.QUEUED}, status=GenerationStatus.RUNNING, started_at=utc_now()
    )
    await repo.update_generation_status(
        generation_id, expected={GenerationStatus.RUNNING}, status=GenerationStatus.COMPLETED, completed_at=utc_now()
    )


async def _persist_all(results: SupabasePipelineResultsRepository, generation_id: UUID) -> None:
    await results.persist_p1_user_stories(generation_id, payloads.p1_payload())
    await results.persist_p2_requirements(generation_id, payloads.p2_payload())
    await results.persist_p4_clusters(generation_id, payloads.p4_payload())
    await results.persist_p6_unit(generation_id, payloads.p6_payload())


# ------------------------------------------------------------------ T-F8-04 · transiciones


async def test_create_generation_is_queued_with_seven_pending_stages(
    generation_factory: GenerationTracker, generations_repo: SupabaseGenerationsRepository
) -> None:
    generation_id = await generation_factory.create(clustering_enabled=False)

    record = await generations_repo.get_by_id(generation_id)

    assert isinstance(generation_id, UUID)
    assert record is not None
    assert record.status == GenerationStatus.QUEUED
    assert record.clustering_enabled is False
    assert [stage.stage_key for stage in record.stages] == list(StageKey)
    assert [stage.stage_order for stage in record.stages] == list(range(1, 8))
    assert all(stage.status == StageStatus.PENDING for stage in record.stages)


async def test_generation_status_transition_requires_expected(
    generation_factory: GenerationTracker, generations_repo: SupabaseGenerationsRepository
) -> None:
    generation_id = await generation_factory.create()

    await generations_repo.update_generation_status(
        generation_id, expected={GenerationStatus.QUEUED}, status=GenerationStatus.RUNNING, started_at=utc_now()
    )
    assert (await generations_repo.get_by_id(generation_id)).status == GenerationStatus.RUNNING

    await generations_repo.update_generation_status(
        generation_id, expected={GenerationStatus.RUNNING}, status=GenerationStatus.COMPLETED, completed_at=utc_now()
    )
    with pytest.raises(InvalidStateTransition):
        await generations_repo.update_generation_status(
            generation_id, expected={GenerationStatus.RUNNING}, status=GenerationStatus.FAILED
        )
    assert (await generations_repo.get_by_id(generation_id)).status == GenerationStatus.COMPLETED


async def test_stage_transition_requires_expected(
    generation_factory: GenerationTracker, generations_repo: SupabaseGenerationsRepository
) -> None:
    generation_id = await generation_factory.create()

    await generations_repo.update_stage(
        generation_id, StageKey.P1, expected=StageStatus.PENDING, status=StageStatus.RUNNING, started_at=utc_now()
    )
    # Ilegal: P1 ya no está `pending`, y P2 no está `running`.
    with pytest.raises(InvalidStateTransition):
        await generations_repo.update_stage(
            generation_id, StageKey.P1, expected=StageStatus.PENDING, status=StageStatus.SKIPPED
        )
    with pytest.raises(InvalidStateTransition):
        await generations_repo.update_stage(
            generation_id, StageKey.P2, expected=StageStatus.RUNNING, status=StageStatus.COMPLETED
        )

    stages = {stage.stage_key: stage.status for stage in (await generations_repo.get_by_id(generation_id)).stages}
    assert stages[StageKey.P1] == StageStatus.RUNNING
    assert stages[StageKey.P2] == StageStatus.PENDING


# ------------------------------------------------------------------ T-F8-05 · summary y get_by_id


async def test_summary_is_written_and_matches_build_summary(
    generation_factory: GenerationTracker,
    generations_repo: SupabaseGenerationsRepository,
    results_repo: SupabasePipelineResultsRepository,
) -> None:
    generation_id = await generation_factory.create()
    await _persist_all(results_repo, generation_id)

    built = await generations_repo.build_summary(generation_id, failed_units=2)
    assert built == GenerationSummary(
        user_stories_count=3, requirements_count=2, clusters_count=1, test_cases_count=1, test_cases_failed_units=2
    )

    await generations_repo.update_summary(generation_id, built)

    record = await generations_repo.get_by_id(generation_id)
    assert record is not None
    assert GenerationSummary.model_validate(record.summary) == built
    assert record.document_name.startswith("fase8-integration-")
    assert record.document_id == generation_factory.document_id
    assert [stage.stage_order for stage in record.stages] == list(range(1, 8))


# ------------------------------------------------------------------ T-F8-06 · delete_generation_if_final


async def test_delete_final_generation_cascades(
    generation_factory: GenerationTracker,
    generations_repo: SupabaseGenerationsRepository,
    results_repo: SupabasePipelineResultsRepository,
    read_rows: RowsReader,
) -> None:
    generation_id = await generation_factory.create()
    await _persist_all(results_repo, generation_id)
    await _complete(generations_repo, generation_id)
    populated = {table: len(read_rows(table, generation_id)) for table in _CHILD_TABLES}
    assert all(count > 0 for count in populated.values()), populated

    await generations_repo.delete(generation_id)

    assert await generations_repo.get_by_id(generation_id) is None
    remaining: dict[str, Any] = {table: read_rows(table, generation_id) for table in _CHILD_TABLES}
    assert all(rows == [] for rows in remaining.values()), remaining


@pytest.mark.parametrize("status", [GenerationStatus.QUEUED, GenerationStatus.RUNNING])
async def test_delete_active_generation_is_rejected(
    status: GenerationStatus,
    generation_factory: GenerationTracker,
    generations_repo: SupabaseGenerationsRepository,
    results_repo: SupabasePipelineResultsRepository,
    read_rows: RowsReader,
) -> None:
    generation_id = await generation_factory.create()
    await results_repo.persist_p1_user_stories(generation_id, payloads.p1_payload())
    if status == GenerationStatus.RUNNING:
        await generations_repo.update_generation_status(
            generation_id, expected={GenerationStatus.QUEUED}, status=GenerationStatus.RUNNING, started_at=utc_now()
        )

    with pytest.raises(GenerationInProgress):
        await generations_repo.delete(generation_id)

    record = await generations_repo.get_by_id(generation_id)
    assert record is not None and record.status == status
    assert len(read_rows("user_stories", generation_id)) == 3

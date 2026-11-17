"""RPC `persist_pN_*` contra Supabase real: happy path (T-F8-02) y caminos de error (T-F8-03).

Cada test crea su propia generación y relee las filas por `generation_id` (D-F8-3).
"""

from typing import Any
from uuid import UUID

import pytest

from ai_service.core.errors import DuplicateEntryError, InvalidReferenceError, MissingIdentifierError
from ai_service.repositories.supabase_pipeline_results import SupabasePipelineResultsRepository
from tests.conftest_integration import GenerationTracker, RowsReader
from tests.integration import payloads

pytestmark = pytest.mark.integration


async def _generation_with_p1(tracker: GenerationTracker, results: SupabasePipelineResultsRepository) -> UUID:
    generation_id = await tracker.create()
    await results.persist_p1_user_stories(generation_id, payloads.p1_payload())
    return generation_id


async def _generation_with_p2(
    tracker: GenerationTracker, results: SupabasePipelineResultsRepository
) -> tuple[UUID, dict[str, Any]]:
    generation_id = await _generation_with_p1(tracker, results)
    p2 = payloads.p2_payload()
    await results.persist_p2_requirements(generation_id, p2)
    return generation_id, p2


def _by(rows: list[dict[str, Any]], key: str) -> dict[Any, dict[str, Any]]:
    return {row[key]: row for row in rows}


# ------------------------------------------------------------------ T-F8-02 · happy path


async def test_persist_p1_user_stories(
    generation_factory: GenerationTracker, results_repo: SupabasePipelineResultsRepository, read_rows: RowsReader
) -> None:
    generation_id = await generation_factory.create()
    payload = payloads.p1_payload()

    await results_repo.persist_p1_user_stories(generation_id, payload)

    rows = _by(read_rows("user_stories", generation_id), "code")
    assert set(rows) == {story["code"] for story in payload}
    for story in payload:
        row = rows[story["code"]]
        for column in ("id", "position", "original_text", "role", "action", "goal", "validation_status"):
            assert row[column] == story[column], column


async def test_persist_p2_requirements(
    generation_factory: GenerationTracker, results_repo: SupabasePipelineResultsRepository, read_rows: RowsReader
) -> None:
    generation_id, payload = await _generation_with_p2(generation_factory, results_repo)

    requirements = _by(read_rows("functional_requirements", generation_id), "code")
    assert set(requirements) == {item["code"] for item in payload["requirements"]}
    for item in payload["requirements"]:
        row = requirements[item["code"]]
        assert (row["id"], row["description"], row["source_text"]) == (
            item["id"], item["description"], item["source_text"]
        )

    stories = _by(read_rows("user_stories", generation_id), "code")
    for item in payload["classifications"]:
        row = stories[item["user_story_code"]]
        assert row["classification"] == item["classification"]
        assert row["classification_rationale"] == item["classification_rationale"]
        assert row["clarification_items"] == item["clarification_items"]

    story_code_by_id = {row["id"]: code for code, row in stories.items()}
    requirement_code_by_id = {row["id"]: code for code, row in requirements.items()}
    links = {
        (requirement_code_by_id[link["requirement_id"]], story_code_by_id[link["user_story_id"]])
        for link in read_rows("user_story_requirements", generation_id)
    }
    expected = {(item["code"], code) for item in payload["requirements"] for code in item["user_story_codes"]}
    assert links == expected


async def test_persist_p4_clusters(
    generation_factory: GenerationTracker, results_repo: SupabasePipelineResultsRepository, read_rows: RowsReader
) -> None:
    generation_id, _ = await _generation_with_p2(generation_factory, results_repo)
    payload = payloads.p4_payload()

    await results_repo.persist_p4_clusters(generation_id, payload)

    clusters = _by(read_rows("clusters", generation_id), "id")
    assert set(clusters) == {cluster["id"] for cluster in payload["clusters"]}
    for cluster in payload["clusters"]:
        row = clusters[cluster["id"]]
        assert (row["name"], row["description"], row["cluster_label"]) == (
            cluster["name"], cluster["description"], cluster["cluster_label"]
        )

    code_by_id = {row["id"]: row["code"] for row in read_rows("functional_requirements", generation_id)}
    assignments = {
        (row["cluster_id"], code_by_id[row["requirement_id"]]): row["similarity_to_centroid"]
        for row in read_rows("cluster_requirements", generation_id)
    }
    expected = {
        (cluster["id"], item["requirement_code"]): item["similarity_to_centroid"]
        for cluster in payload["clusters"]
        for item in cluster["assignments"]
    }
    assert assignments == pytest.approx(expected)

    unassigned = {code_by_id[row["requirement_id"]] for row in read_rows("unassigned_requirements", generation_id)}
    assert unassigned == set(payload["unassigned_requirement_codes"])


async def test_persist_p6_unit(
    generation_factory: GenerationTracker, results_repo: SupabasePipelineResultsRepository, read_rows: RowsReader
) -> None:
    generation_id, _ = await _generation_with_p2(generation_factory, results_repo)
    payload = payloads.p6_payload()

    await results_repo.persist_p6_unit(generation_id, payload)

    cases = _by(read_rows("test_cases", generation_id), "code")
    assert set(cases) == {case["code"] for case in payload["test_cases"]}
    steps = read_rows("test_steps", generation_id)
    links = read_rows("requirement_test_cases", generation_id)
    code_by_id = {row["id"]: row["code"] for row in read_rows("functional_requirements", generation_id)}
    for case in payload["test_cases"]:
        row = cases[case["code"]]
        for column in ("id", "title", "objective", "preconditions", "test_data", "expected_result"):
            assert row[column] == case[column], column

        stored_steps = sorted(
            (
                {key: step[key] for key in ("step_number", "action", "expected_result")}
                for step in steps
                if step["test_case_id"] == case["id"]
            ),
            key=lambda step: step["step_number"],
        )
        assert stored_steps == [
            {"step_number": s["step_number"], "action": s["action"], "expected_result": s.get("expected_result")}
            for s in case["steps"]
        ]

        case_links = [link for link in links if link["test_case_id"] == case["id"]]
        assert {code_by_id[link["requirement_id"]] for link in case_links} == set(case["requirement_codes"])
        assert all(link["relation_status"] == "pending" for link in case_links)


# ------------------------------------------------------------------ T-F8-03 · errores y constraints


async def test_persist_p6_unit_unknown_requirement_is_fk_error(
    generation_factory: GenerationTracker, results_repo: SupabasePipelineResultsRepository, read_rows: RowsReader
) -> None:
    generation_id, _ = await _generation_with_p2(generation_factory, results_repo)
    payload = payloads.p6_payload()
    payload["test_cases"][0]["requirement_codes"] = ["RF-999"]

    with pytest.raises(InvalidReferenceError) as exc_info:
        await results_repo.persist_p6_unit(generation_id, payload)

    assert exc_info.value.details["sql_code"] == "23503"
    assert read_rows("test_cases", generation_id) == []  # todo o nada (D-15)


async def test_persist_p6_unit_case_without_id_is_not_null_error(
    generation_factory: GenerationTracker, results_repo: SupabasePipelineResultsRepository, read_rows: RowsReader
) -> None:
    generation_id, _ = await _generation_with_p2(generation_factory, results_repo)
    payload = payloads.p6_payload()
    del payload["test_cases"][0]["id"]

    with pytest.raises(MissingIdentifierError) as exc_info:
        await results_repo.persist_p6_unit(generation_id, payload)

    assert exc_info.value.details["sql_code"] == "23502"
    assert read_rows("test_cases", generation_id) == []


async def test_persist_p2_duplicate_story_is_rejected_before_update(
    generation_factory: GenerationTracker, results_repo: SupabasePipelineResultsRepository, read_rows: RowsReader
) -> None:
    generation_id = await _generation_with_p1(generation_factory, results_repo)
    payload = payloads.p2_payload()
    payload["classifications"].append(dict(payload["classifications"][0]))

    with pytest.raises(DuplicateEntryError) as exc_info:
        await results_repo.persist_p2_requirements(generation_id, payload)

    assert exc_info.value.details["sql_code"] == "23505"
    # El rechazo ocurre antes del UPDATE: ninguna HU quedó clasificada ni hay RF.
    assert all(row["classification"] is None for row in read_rows("user_stories", generation_id))
    assert read_rows("functional_requirements", generation_id) == []


async def test_persist_p1_is_idempotent_by_code(
    generation_factory: GenerationTracker, results_repo: SupabasePipelineResultsRepository, read_rows: RowsReader
) -> None:
    generation_id = await generation_factory.create()
    payload = payloads.p1_payload()
    await results_repo.persist_p1_user_stories(generation_id, payload)

    # Mismos `code`, otro texto e id: ON CONFLICT (generation_id, code) DO UPDATE, sin duplicar.
    replay = payloads.p1_payload()
    replay[0]["original_text"] = "Texto actualizado en el reintento."
    await results_repo.persist_p1_user_stories(generation_id, replay)

    rows = _by(read_rows("user_stories", generation_id), "code")
    assert len(rows) == len(payload)
    first = rows[payload[0]["code"]]
    assert first["original_text"] == "Texto actualizado en el reintento."
    assert first["id"] == payload[0]["id"]  # el UPDATE no cambia la clave

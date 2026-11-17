"""P6 real (generación de casos de prueba, T-F7-03 / T-F7-07). LLM fake y repositorio en memoria."""

import json
from typing import Any
from uuid import uuid4

import pytest

from ai_service.clients.llm_fake import FakeLlmClient
from ai_service.core.errors import LlmContextLengthError, LlmError, PersistenceError
from ai_service.pipeline.context import PipelineConfiguration, PipelineContext
from ai_service.pipeline.contracts.common import UnitStrategy
from ai_service.pipeline.contracts.p5 import ContextRequirement, ContextUnit, ContextUserStory, GenerationContext, P5Output
from ai_service.pipeline.contracts.p6 import P6Config
from ai_service.pipeline.prompts.p6 import resolve_p6_prompt
from ai_service.pipeline.stages import GenerationStage, StageError
from ai_service.pipeline.stages.llm_output import filter_requirement_codes, filter_requirement_codes_with_stats
from ai_service.pipeline.stages.p6_generation import build_user_message
from ai_service.repositories.in_memory import InMemoryPipelineResultsRepository, InMemoryStore
from tests import contract_factories as f

CONFIG = P6Config(prompt_version="v2", llm=f.LLM, max_retries=1)


def _rq(number: int) -> ContextRequirement:
    return ContextRequirement(code=f"RF-{number:03d}", description=f"El sistema hace la tarea {number}.")


def _unit(number: int, targets: tuple[int, ...], context: tuple[int, ...] = (), *, clustered: bool = True) -> ContextUnit:
    story = ContextUserStory(code=f"HU-{number:03d}", original_text=f"Como usuario, quiero la función {number}.")
    return ContextUnit(
        unit_id=f"U-{number:03d}",
        label=f"Cluster {number}" if clustered else f"HU-{number:03d}",
        cluster_label=number if clustered else None,
        requirements=tuple(_rq(n) for n in targets),
        context_requirements=tuple(_rq(n) for n in context),
        user_stories=(story,),
        requirement_to_stories={f"RF-{n:03d}": (story.code,) for n in (*targets, *context)},
        token_estimate=100,
    )


def _context(units: tuple[ContextUnit, ...], strategy: UnitStrategy = UnitStrategy.BY_CLUSTER) -> PipelineContext:
    generation_id = uuid4()
    ctx = PipelineContext(
        generation_id=generation_id,
        document_id=f.DOCUMENT_ID,
        configuration=PipelineConfiguration(clustering_enabled=strategy == UnitStrategy.BY_CLUSTER, method_type="llm_pipeline"),
    )
    ctx.p5_output = P5Output(
        context=GenerationContext(
            generation_id=generation_id, output_spec=f.output_spec(), instructions_version="v1", strategy=strategy, units=units
        )
    )
    return ctx


def _store_with_requirements(ctx: PipelineContext) -> InMemoryStore:
    """Siembra los RF de las unidades: `persist_p6_unit` valida la FK de `requirement_codes`."""
    store = InMemoryStore()
    codes = {item.code for unit in ctx.p5_output.context.units for item in (*unit.requirements, *unit.context_requirements)}
    store.requirements[ctx.generation_id] = {code: {"id": uuid4(), "code": code} for code in codes}
    return store


def _answer(*links: tuple[str, ...]) -> str:
    return json.dumps(
        {
            "test_cases": [
                {
                    "title": f"Caso {number}",
                    "steps": [{"step_number": 1, "action": "Ejecutar"}, {"step_number": 2, "action": "Verificar"}],
                    "expected_result": "Resultado esperado.",
                    "requirement_codes": list(codes),
                }
                for number, codes in enumerate(links, start=1)
            ]
        }
    )


def _stage(llm: FakeLlmClient, store: InMemoryStore, **config: Any) -> tuple[GenerationStage, InMemoryPipelineResultsRepository]:
    results = InMemoryPipelineResultsRepository(store)
    stage = GenerationStage(
        llm_client=llm,
        prompt_resolver=resolve_p6_prompt,
        results=results,
        config=CONFIG.model_copy(update=config),
        retry_delay_seconds=0,
    )
    return stage, results


def _codes(ctx: PipelineContext) -> list[str]:
    return [case.code for case in ctx.p6_output.test_cases]


def _warning_codes(result: Any) -> list[str]:
    return [warning.code for warning in result.warnings]


# --------------------------------------------------------------- camino feliz
async def test_by_cluster_happy_path_numbers_and_persists_every_unit() -> None:
    ctx = _context((_unit(1, (1, 2), context=(3,)), _unit(2, (3,), context=(1,))))
    store = _store_with_requirements(ctx)
    llm = FakeLlmClient([_answer(("RF-001",), ("RF-001", "RF-002")), _answer(("RF-003",))])
    stage, results = _stage(llm, store)

    result = await stage.run(ctx)

    output = ctx.p6_output
    assert _codes(ctx) == ["CP-001", "CP-002", "CP-003"]
    assert [unit.unit_id for unit in output.units] == ["U-001", "U-002"]
    assert output.failed_units == () and output.uncovered_requirement_codes == ()
    assert results.calls == [("persist_p6_unit", ctx.generation_id)] * 2
    assert list(store.test_cases[ctx.generation_id]) == ["CP-001", "CP-002", "CP-003"]
    assert all(link.status == "pending" for case in output.test_cases for link in case.requirement_links)
    assert result.warnings == () and result.skip_remaining is False
    assert [(run.unit_id, run.attempts, run.prompt_version) for run in result.llm_runs] == [
        ("U-001", 1, "contexto@v2"), ("U-002", 1, "contexto@v2"),
    ]
    info = result.runtime_info
    assert (info["strategy"], info["units"], info["units_failed"], info["test_cases_count"]) == ("by_cluster", 2, 0, 3)
    assert info["model"] == "modelo-x"


async def test_by_cluster_context_requirements_are_never_linked() -> None:
    """Un caso cuyos RF son todos de contexto se descarta; si la unidad queda sin casos, se reintenta y falla."""
    ctx = _context((_unit(1, (1,), context=(2,)), _unit(2, (2,), context=(1,))))
    store = _store_with_requirements(ctx)
    llm = FakeLlmClient([_answer(("RF-002",)), _answer(("RF-002",)), _answer(("RF-002",))])
    stage, _ = _stage(llm, store, failure_threshold=0.5)

    result = await stage.run(ctx)

    assert [item.unit_id for item in ctx.p6_output.failed_units] == ["U-001"]
    assert ctx.p6_output.failed_units[0].error_code == "LLM_INVALID_OUTPUT"
    linked = {code for case in ctx.p6_output.test_cases for code in case.requirement_codes()}
    assert linked == {"RF-002"}
    assert ctx.p6_output.uncovered_requirement_codes == ("RF-001",)
    assert "UNIT_GENERATION_FAILED" in _warning_codes(result)
    assert "REQUIREMENT_CODES_FILTERED" not in _warning_codes(result)  # solo cuenta en unidades exitosas


async def test_context_requirements_are_filtered_and_the_case_is_persisted() -> None:
    """Issue de saneo P6: un RF de contexto en `requirement_codes` se filtra en vez de invalidar la unidad."""
    ctx = _context((_unit(1, (1, 2), context=(3,)), _unit(2, (3,), context=(1,))))
    store = _store_with_requirements(ctx)
    llm = FakeLlmClient(
        [_answer(("RF-001", "RF-003"), ("RF-002", "RF-003"), ("RF-003",)), _answer(("RF-003",))]
    )
    stage, _ = _stage(llm, store)

    result = await stage.run(ctx)

    assert len(llm.requests) == 2  # sin reintentos
    assert [list(case.requirement_codes()) for case in ctx.p6_output.units[0].test_cases] == [["RF-001"], ["RF-002"]]
    assert _codes(ctx) == ["CP-001", "CP-002", "CP-003"]
    assert store.test_cases[ctx.generation_id]["CP-001"]["requirement_codes"] == ["RF-001"]
    assert _warning_codes(result) == ["REQUIREMENT_CODES_FILTERED"]
    assert result.warnings[0].details == {
        "units": {"U-001": {"filtered_codes": ["RF-003"], "filtered_occurrences": 3, "dropped_cases": 1}}
    }


async def test_by_user_story_happy_path_uses_prompt_without_clustering() -> None:
    units = (_unit(1, (1,), clustered=False), _unit(2, (2, 3), clustered=False))
    ctx = _context(units, UnitStrategy.BY_USER_STORY)
    store = _store_with_requirements(ctx)
    llm = FakeLlmClient([_answer(("RF-001",)), _answer(("RF-002",), ("RF-003",))])
    stage, _ = _stage(llm, store)

    result = await stage.run(ctx)

    assert _codes(ctx) == ["CP-001", "CP-002", "CP-003"]
    assert result.runtime_info["strategy"] == "by_user_story"
    assert result.runtime_info["prompt_version"] == "contexto_sin_clustering@v2"
    assert llm.requests[0].system == resolve_p6_prompt("v2", UnitStrategy.BY_USER_STORY).text
    assert all("RF de contexto" not in request.prompt for request in llm.requests)


# --------------------------------------------------------------- mensaje al LLM
def test_user_message_carries_the_cap_requirements_stories_and_schema() -> None:
    ctx = _context((_unit(1, (1, 2), context=(3,)),))
    generation = ctx.p5_output.context

    message = build_user_message(generation, generation.units[0], 6)

    assert message.startswith("Genera como máximo 6 casos de prueba para esta unidad.")
    assert '"RF-001"' in message and '"RF-002"' in message
    assert "## RF de contexto (no enlazar)" in message and '"RF-003"' in message
    assert "Como usuario, quiero la función 1." in message
    assert json.dumps(generation.output_spec.json_schema, ensure_ascii=False) in message
    assert "Cluster 1" not in message  # el nombre placeholder del cluster no llega al LLM


async def test_cap_reaches_the_llm_from_the_configuration() -> None:
    ctx = _context((_unit(1, (1, 2)),))
    llm = FakeLlmClient([_answer(("RF-001",))])
    stage, _ = _stage(llm, _store_with_requirements(ctx), max_cases_multiplier=2, max_cases_absolute=3)

    await stage.run(ctx)

    assert llm.requests[0].prompt.startswith("Genera como máximo 3 casos de prueba")
    assert llm.requests[0].model == "modelo-x"


# --------------------------------------------------------------- fallos de unidad
def _three_units_second_fails() -> tuple[PipelineContext, FakeLlmClient]:
    ctx = _context((_unit(1, (1,)), _unit(2, (2,)), _unit(3, (3,))))
    llm = FakeLlmClient([_answer(("RF-001",), ("RF-001",)), "no json", "tampoco", _answer(("RF-003",))])
    return ctx, llm


async def test_failed_unit_with_zero_threshold_fails_the_stage_without_persisting() -> None:
    ctx, llm = _three_units_second_fails()
    store = _store_with_requirements(ctx)
    stage, results = _stage(llm, store, failure_threshold=0.0)

    with pytest.raises(StageError) as exc_info:
        await stage.run(ctx)

    assert exc_info.value.code == "GENERATION_THRESHOLD_EXCEEDED"
    assert exc_info.value.details == {"failed_units": 1, "total_units": 3, "threshold": 0.0}
    assert len(llm.requests) == 4  # la tercera unidad se procesó igualmente (D-F7-1)
    assert results.calls == [] and store.test_cases == {}
    assert ctx.p6_output is None


async def test_failed_unit_below_threshold_completes_with_warning_and_global_numbering() -> None:
    ctx, llm = _three_units_second_fails()
    store = _store_with_requirements(ctx)
    stage, results = _stage(llm, store, failure_threshold=0.5)

    result = await stage.run(ctx)

    output = ctx.p6_output
    assert [unit.unit_id for unit in output.units] == ["U-001", "U-003"]
    assert [(item.unit_id, item.error_code) for item in output.failed_units] == [("U-002", "LLM_INVALID_OUTPUT")]
    # Numeración global sin saltos: la unidad fallida no consume códigos (D-F7-6).
    assert [case.code for case in output.units[0].test_cases] == ["CP-001", "CP-002"]
    assert [case.code for case in output.units[1].test_cases] == ["CP-003"]
    assert output.uncovered_requirement_codes == ("RF-002",)
    assert len(results.calls) == 2
    assert _warning_codes(result) == ["UNIT_GENERATION_FAILED", "BATCH_RETRIED", "UNCOVERED_REQUIREMENTS"]
    assert result.runtime_info["units_failed"] == 1
    assert [run.unit_id for run in result.llm_runs] == ["U-001", "U-002", "U-003"]


async def test_threshold_is_compared_strictly() -> None:
    """1 de 2 unidades fallidas = 0.5: con umbral 0.5 no se supera; con 0.49 sí."""
    for threshold, fails in ((0.5, False), (0.49, True)):
        ctx = _context((_unit(1, (1,)), _unit(2, (2,))))
        llm = FakeLlmClient([_answer(("RF-001",)), "x", "x"])
        stage, _ = _stage(llm, _store_with_requirements(ctx), failure_threshold=threshold)
        if fails:
            with pytest.raises(StageError, match="1 de 2"):
                await stage.run(ctx)
        else:
            await stage.run(ctx)
            assert len(ctx.p6_output.failed_units) == 1


async def test_context_length_error_is_not_retried() -> None:
    ctx = _context((_unit(1, (1,)), _unit(2, (2,))))
    llm = FakeLlmClient([LlmContextLengthError(), _answer(("RF-002",))])
    stage, _ = _stage(llm, _store_with_requirements(ctx), max_retries=3, failure_threshold=1.0)

    result = await stage.run(ctx)

    assert len(llm.requests) == 2
    assert ctx.p6_output.failed_units[0].error_code == "LLM_CONTEXT_LENGTH"
    assert result.llm_runs[0].attempts == 1


async def test_provider_failure_after_retries_is_reported_as_unavailable() -> None:
    ctx = _context((_unit(1, (1,)),))
    llm = FakeLlmClient([LlmError(), LlmError()])
    stage, _ = _stage(llm, _store_with_requirements(ctx), failure_threshold=1.0)

    result = await stage.run(ctx)

    assert ctx.p6_output.failed_units[0].error_code == "LLM_UNAVAILABLE"
    assert ctx.p6_output.units == ()
    assert result.runtime_info["retries_used"] == 1


async def test_persistence_failure_marks_the_unit_failed_without_gaps() -> None:
    """Si la RPC rechaza una unidad, pasa a `failed_units` y la siguiente reutiliza sus códigos."""
    ctx = _context((_unit(1, (1,)), _unit(2, (2,)), _unit(3, (3,))))
    store = _store_with_requirements(ctx)
    llm = FakeLlmClient([_answer(("RF-001",)), _answer(("RF-002",)), _answer(("RF-003",))])
    stage, results = _stage(llm, store, failure_threshold=0.5)
    original = results.persist_p6_unit

    async def flaky(generation_id: Any, payload: dict[str, Any]) -> None:
        if payload["test_cases"][0]["requirement_codes"] == ["RF-002"]:
            raise PersistenceError("fallo de red")
        await original(generation_id, payload)

    results.persist_p6_unit = flaky  # type: ignore[method-assign]

    await stage.run(ctx)

    output = ctx.p6_output
    assert [(item.unit_id, item.error_code) for item in output.failed_units] == [("U-002", "PERSISTENCE_FAILED")]
    assert _codes(ctx) == ["CP-001", "CP-002"]
    assert list(store.test_cases[ctx.generation_id]) == ["CP-001", "CP-002"]
    assert store.test_cases[ctx.generation_id]["CP-002"]["requirement_codes"] == ["RF-003"]


async def test_persistence_failures_count_towards_the_threshold() -> None:
    ctx = _context((_unit(1, (1,)),))
    store = InMemoryStore()  # sin RF sembrados: la FK de persist_p6_unit falla
    llm = FakeLlmClient([_answer(("RF-001",))])
    stage, _ = _stage(llm, store)

    with pytest.raises(StageError) as exc_info:
        await stage.run(ctx)

    assert exc_info.value.code == "GENERATION_THRESHOLD_EXCEEDED"


# --------------------------------------------------------------- truncado y reintentos
async def test_cases_above_the_cap_are_truncated_with_warning() -> None:
    ctx = _context((_unit(1, (1,)),))
    llm = FakeLlmClient([_answer(*[("RF-001",)] * 5)])
    stage, _ = _stage(llm, _store_with_requirements(ctx), max_cases_multiplier=2)

    result = await stage.run(ctx)

    assert _codes(ctx) == ["CP-001", "CP-002"]
    assert _warning_codes(result) == ["CASES_TRUNCATED"]
    assert result.warnings[0].details == {"units": {"U-001": {"received": 5, "max_cases": 2}}}


async def test_truncation_happens_before_validation() -> None:
    """Un caso inválido más allá del tope no invalida la unidad: se descarta antes de validar."""
    ctx = _context((_unit(1, (1,)),))
    payload = json.loads(_answer(("RF-001",), ("RF-001",), ("RF-001",), ("RF-001",)))
    payload["test_cases"][3]["steps"] = []
    llm = FakeLlmClient([json.dumps(payload)])
    stage, _ = _stage(llm, _store_with_requirements(ctx))

    result = await stage.run(ctx)

    assert _codes(ctx) == ["CP-001", "CP-002", "CP-003"]
    assert _warning_codes(result) == ["CASES_TRUNCATED"]


async def test_invalid_json_then_valid_is_retried_with_warning() -> None:
    ctx = _context((_unit(1, (1,)),))
    llm = FakeLlmClient(["no json", "```json\n" + _answer(("RF-001",)) + "\n```"])
    stage, _ = _stage(llm, _store_with_requirements(ctx))

    result = await stage.run(ctx)

    assert _codes(ctx) == ["CP-001"]
    assert _warning_codes(result) == ["BATCH_RETRIED"]
    assert result.warnings[0].details == {"units": {"U-001": ["LLM_INVALID_OUTPUT"]}}
    assert result.llm_runs[0].attempts == 2
    assert result.runtime_info["retries_used"] == 1


async def test_blank_list_items_are_dropped_before_validation() -> None:
    ctx = _context((_unit(1, (1,)),))
    payload = json.loads(_answer(("RF-001",)))
    payload["test_cases"][0]["preconditions"] = [""]
    llm = FakeLlmClient([json.dumps(payload)])
    stage, _ = _stage(llm, _store_with_requirements(ctx))

    await stage.run(ctx)

    assert ctx.p6_output.test_cases[0].preconditions == ()


# --------------------------------------------------------------- guardias
async def test_missing_p5_output_is_an_orchestrator_bug() -> None:
    ctx = _context((_unit(1, (1,)),))
    ctx.p5_output = None
    stage, _ = _stage(FakeLlmClient(), InMemoryStore())

    with pytest.raises(RuntimeError, match="p5_output"):
        await stage.run(ctx)


async def test_zero_units_produce_an_empty_output() -> None:
    ctx = _context(())
    llm = FakeLlmClient()
    stage, results = _stage(llm, InMemoryStore())

    result = await stage.run(ctx)

    assert ctx.p6_output.units == () and ctx.p6_output.failed_units == ()
    assert result.skip_remaining is False
    assert llm.requests == [] and results.calls == []
    assert result.runtime_info["units"] == 0


# --------------------------------------------------------------- repositorio en memoria
async def test_in_memory_persist_p6_unit_is_idempotent_and_checks_references() -> None:
    from ai_service.core.errors import InvalidReferenceError, MissingIdentifierError

    gid = uuid4()
    store = InMemoryStore()
    store.requirements[gid] = {"RF-001": {"id": uuid4(), "code": "RF-001"}}
    repo = InMemoryPipelineResultsRepository(store)
    payload = f.unit_output().to_rpc_payload()

    await repo.persist_p6_unit(gid, payload)
    await repo.persist_p6_unit(gid, payload)

    assert list(store.test_cases[gid]) == ["CP-001"]
    assert len(store.test_cases[gid]["CP-001"]["steps"]) == 2
    assert store.test_cases[gid]["CP-001"]["requirement_codes"] == ["RF-001"]
    with pytest.raises(InvalidReferenceError):
        await repo.persist_p6_unit(uuid4(), payload)
    with pytest.raises(MissingIdentifierError):
        await repo.persist_p6_unit(gid, {"test_cases": [{**payload["test_cases"][0], "id": None}]})


# --------------------------------------------------------------- saneo de requirement_codes
def test_filter_requirement_codes_drops_foreign_codes_and_keeps_valid_ones() -> None:
    raw = _answer(("RF-001", "RF-003"), ("RF-002",))

    data = json.loads(filter_requirement_codes(raw, {"RF-001", "RF-002"}))

    assert [case["requirement_codes"] for case in data["test_cases"]] == [["RF-001"], ["RF-002"]]
    assert data["test_cases"][0]["title"] == "Caso 1" and data["test_cases"][0]["steps"]


def test_filter_requirement_codes_drops_the_case_when_every_code_is_foreign() -> None:
    raw = _answer(("RF-003",), ("RF-001", "RF-003"))

    filtered, codes, dropped = filter_requirement_codes_with_stats(raw, {"RF-001"})

    assert [case["requirement_codes"] for case in json.loads(filtered)["test_cases"]] == [["RF-001"]]
    assert (codes, dropped) == (["RF-003", "RF-003"], 1)


def test_filter_requirement_codes_leaves_non_json_and_clean_answers_untouched() -> None:
    assert filter_requirement_codes("no json", {"RF-001"}) == "no json"
    clean = _answer(("RF-001",))
    assert filter_requirement_codes(clean, {"RF-001"}) == clean

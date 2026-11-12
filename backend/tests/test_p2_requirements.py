"""P2 real (LLM en lotes) con `FakeLlmClient` y persistencia en memoria."""

import json
import logging
from typing import Any
from uuid import uuid4

import pytest

from ai_service.clients.llm_fake import FakeLlmClient
from ai_service.core.errors import DuplicateEntryError, LlmContextLengthError, LlmError, LlmRateLimitError
from ai_service.pipeline.context import PipelineConfiguration, PipelineContext
from ai_service.pipeline.contracts.common import LlmSettings
from ai_service.pipeline.contracts.p2 import P2Config
from ai_service.pipeline.prompts.p2 import resolve_p2_prompt
from ai_service.pipeline.stages import RequirementsStage, StageError
from ai_service.repositories.in_memory import InMemoryPipelineResultsRepository, InMemoryStore
from tests import contract_factories as f

HU1_CLASSIFICATION = {
    "user_story_code": "HU-001",
    "category": "candidata_funcional",
    "rationale": "Describe un acceso al sistema.",
}
HU2_NO_APLICABLE = {
    "user_story_code": "HU-002",
    "category": "no_aplicable",
    "rationale": "Es texto informativo.",
}
RF_LOGIN = {
    "description": "El sistema permite iniciar sesión.",
    "source_text": "quiero iniciar sesión",
    "user_story_codes": ["HU-001"],
    "evidence": [{"user_story_code": "HU-001", "text": "quiero iniciar sesión", "attribute": "description"}],
}
RF_LOCK = {
    "description": "El sistema bloquea la cuenta tras 3 intentos fallidos.",
    "source_text": "bloquear tras 3 intentos",
    "user_story_codes": ["HU-001"],
    "business_rules": ["bloquear tras 3 intentos"],
}


def _json(classifications: list[dict[str, Any]], requirements: list[dict[str, Any]] = ()) -> str:
    return json.dumps({"classifications": classifications, "requirements": list(requirements)}, ensure_ascii=False)


HU1_OK = _json([HU1_CLASSIFICATION], [RF_LOGIN, RF_LOCK])
HU2_OK = _json([HU2_NO_APLICABLE])


def _config(**overrides: Any) -> P2Config:
    values = {
        "prompt_version": "v1",
        "llm": LlmSettings(provider="fake", model="modelo-x", parameters={"temperature": 0}),
        "max_stories_per_call": 1,
        "max_retries": 2,
        **overrides,
    }
    return P2Config(**values)


@pytest.fixture
def results(store: InMemoryStore) -> InMemoryPipelineResultsRepository:
    return InMemoryPipelineResultsRepository(store)


@pytest.fixture
async def context(results: InMemoryPipelineResultsRepository) -> PipelineContext:
    """Contexto tras P1: HU-001 (valid), HU-002 (valid_with_warnings), HU-003 (invalid), ya persistidas."""
    ctx = PipelineContext(
        generation_id=uuid4(),
        document_id=f.DOCUMENT_ID,
        configuration=PipelineConfiguration(clustering_enabled=True, method_type="llm_pipeline"),
    )
    ctx.p1_output = f.p1_output()
    await results.persist_p1_user_stories(ctx.generation_id, ctx.p1_output.to_rpc_payload())
    return ctx


def _stage(llm: FakeLlmClient, results, **config: Any) -> RequirementsStage:
    return RequirementsStage(
        llm_client=llm,
        prompt_resolver=resolve_p2_prompt,
        results=results,
        config=_config(**config),
        retry_delay_seconds=0,
    )


async def test_happy_path_batches_consolidates_and_persists(context, results, store) -> None:
    llm = FakeLlmClient([f"```json\n{HU1_OK}\n```", HU2_OK])  # el primer lote viene con code fence

    result = await _stage(llm, results).run(context)

    # Un lote por HU procesable; la HU invalid (HU-003) no se envía.
    assert len(llm.requests) == 2
    assert '"HU-001"' in llm.requests[0].prompt and '"HU-002"' not in llm.requests[0].prompt
    assert '"HU-002"' in llm.requests[1].prompt
    assert all('"HU-003"' not in r.prompt for r in llm.requests)
    request = llm.requests[0]
    assert request.system == resolve_p2_prompt("v1").text
    assert request.model == "modelo-x" and request.temperature == 0 and request.extra == {}

    output = context.p2_output
    assert [c.user_story_code for c in output.classifications] == ["HU-001", "HU-002"]
    assert [r.code for r in output.requirements] == ["RF-001", "RF-002"]
    assert output.requirements[1].business_rules == ("bloquear tras 3 intentos",)
    assert output.stories_without_requirements == ("HU-002",)

    assert result.skip_remaining is False
    assert [(run.model, run.prompt_version, run.attempts) for run in result.llm_runs] == [("modelo-x", "v1", 1)] * 2
    assert result.warnings == ()
    info = result.runtime_info
    assert (info["batches"], info["retries_used"], info["requirements_count"]) == (2, 0, 2)
    assert info["classification_counts"] == {"candidata_funcional": 1, "requiere_aclaracion": 0, "no_aplicable": 1}

    # Persistencia vía persist_p2_requirements (D-27: clasificación en user_stories).
    assert results.calls[-1] == ("persist_p2_requirements", context.generation_id)
    stories = store.user_stories[context.generation_id]
    assert stories["HU-001"]["classification"] == "candidata_funcional"
    assert stories["HU-002"]["classification"] == "no_aplicable"
    assert sorted(store.requirements[context.generation_id]) == ["RF-001", "RF-002"]
    assert store.story_requirements[context.generation_id] == {("HU-001", "RF-001"), ("HU-001", "RF-002")}


async def test_batches_respect_max_stories_per_call(context, results) -> None:
    llm = FakeLlmClient([_json([HU1_CLASSIFICATION, HU2_NO_APLICABLE], [RF_LOGIN])])

    result = await _stage(llm, results, max_stories_per_call=5).run(context)

    assert len(llm.requests) == 1
    assert result.runtime_info["batches"] == 1
    assert [r.code for r in context.p2_output.requirements] == ["RF-001"]


async def test_invalid_batch_is_retried_and_raw_output_logged(context, results, caplog) -> None:
    invalid = _json([HU1_CLASSIFICATION, HU2_NO_APLICABLE])  # clasifica una HU fuera del lote
    llm = FakeLlmClient(["esto no es json", invalid, HU1_OK, HU2_OK])

    with caplog.at_level(logging.DEBUG, logger="ai_service.pipeline.stages.p2_requirements"):
        result = await _stage(llm, results).run(context)

    debug = [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG and "P2 lote inválido" in r.getMessage()]
    assert len(debug) == 2
    assert "raw=esto no es json" in debug[0] and "batch=1" in debug[0]
    assert [run.attempts for run in result.llm_runs] == [3, 1]
    assert result.runtime_info["retries_used"] == 2
    assert [w.code for w in result.warnings] == ["BATCH_RETRIED"]
    assert result.warnings[0].details == {"batches": {"1": ["LLM_INVALID_OUTPUT", "LLM_INVALID_OUTPUT"]}}


async def test_invalid_output_after_retries_fails(context, results) -> None:
    llm = FakeLlmClient(["{}", "{}", "{}"])

    with pytest.raises(StageError) as info:
        await _stage(llm, results).run(context)

    assert info.value.code == "LLM_INVALID_OUTPUT"
    assert info.value.retryable is True
    assert len(llm.requests) == 3  # 1 + max_retries
    assert context.p2_output is None
    assert ("persist_p2_requirements", context.generation_id) not in results.calls


async def test_requirement_referencing_story_outside_batch_is_invalid(context, results) -> None:
    rf_other = {**RF_LOGIN, "user_story_codes": ["HU-002"], "evidence": []}
    llm = FakeLlmClient([_json([HU1_CLASSIFICATION], [rf_other])])

    with pytest.raises(StageError) as info:
        await _stage(llm, results, max_retries=0).run(context)
    assert info.value.code == "LLM_INVALID_OUTPUT"


async def test_zero_requirements_skips_remaining(context, results, store) -> None:
    """D-29: sin RF, P2 completa con aviso y `skip_remaining`; las clasificaciones se persisten."""
    llm = FakeLlmClient([_json([{**HU1_CLASSIFICATION, "category": "requiere_aclaracion",
                                 "clarification_items": ["¿Qué credenciales?"]}]), HU2_OK])

    result = await _stage(llm, results).run(context)

    assert result.skip_remaining is True
    assert [w.code for w in result.warnings] == ["NO_REQUIREMENTS_EXTRACTED"]
    assert context.p2_output.requirements == ()
    assert context.p2_output.stories_without_requirements == ("HU-001", "HU-002")
    assert store.user_stories[context.generation_id]["HU-001"]["clarification_items"] == ["¿Qué credenciales?"]
    assert store.requirements[context.generation_id] == {}


async def test_candidate_without_requirements_warns(context, results) -> None:
    llm = FakeLlmClient([_json([HU1_CLASSIFICATION]), _json([{**HU2_NO_APLICABLE, "category": "candidata_funcional"}], [
        {**RF_LOGIN, "user_story_codes": ["HU-002"], "evidence": []}
    ])])

    result = await _stage(llm, results).run(context)

    assert [w.code for w in result.warnings] == ["CANDIDATE_WITHOUT_REQUIREMENTS"]
    assert result.warnings[0].details == {"user_story_codes": ["HU-001"]}


async def test_rate_limit_is_retried(context, results) -> None:
    llm = FakeLlmClient([LlmRateLimitError(), HU1_OK, HU2_OK])

    result = await _stage(llm, results).run(context)

    assert [run.attempts for run in result.llm_runs] == [2, 1]
    assert result.warnings[0].details == {"batches": {"1": ["LLM_RATE_LIMIT"]}}


async def test_context_length_is_not_retried(context, results) -> None:
    llm = FakeLlmClient([LlmContextLengthError(), HU1_OK])

    with pytest.raises(StageError) as info:
        await _stage(llm, results).run(context)

    assert info.value.code == "LLM_CONTEXT_LENGTH"
    assert len(llm.requests) == 1


async def test_provider_unavailable_after_retries(context, results) -> None:
    llm = FakeLlmClient([LlmError(), LlmError(), LlmError()])

    with pytest.raises(StageError) as info:
        await _stage(llm, results).run(context)

    assert info.value.code == "LLM_UNAVAILABLE"
    assert info.value.retryable is True


async def test_persistence_rejects_unknown_stories(results) -> None:
    """Sin las HU de P1 persistidas, la RPC (fake) rechaza la referencia → INVALID_STORY_REFERENCE."""
    ctx = PipelineContext(
        generation_id=uuid4(),
        document_id=f.DOCUMENT_ID,
        configuration=PipelineConfiguration(clustering_enabled=False, method_type="llm_pipeline"),
    )
    ctx.p1_output = f.p1_output()

    with pytest.raises(StageError) as info:
        await _stage(FakeLlmClient([HU1_OK, HU2_OK]), results).run(ctx)

    assert info.value.code == "INVALID_STORY_REFERENCE"
    assert ctx.p2_output is None


async def test_persist_p2_rejects_duplicate_classifications(context, results) -> None:
    """T-02 (fake replicando la RPC): una HU repetida en el payload falla con mensaje correcto."""
    payload = f.p2_output().to_rpc_payload()
    payload["classifications"].append(payload["classifications"][0])

    with pytest.raises(DuplicateEntryError, match="HU-001 aparece 2 o más veces"):
        await results.persist_p2_requirements(context.generation_id, payload)


async def test_persist_p2_is_idempotent(context, results, store) -> None:
    await _stage(FakeLlmClient([HU1_OK, HU2_OK]), results).run(context)
    payload = context.p2_output.to_rpc_payload()
    before = {code: row["id"] for code, row in store.requirements[context.generation_id].items()}

    await results.persist_p2_requirements(context.generation_id, payload)

    assert {code: row["id"] for code, row in store.requirements[context.generation_id].items()} == before
    assert len(store.story_requirements[context.generation_id]) == 2

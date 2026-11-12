"""P3 real (embeddings en lotes) con `FakeEmbeddingsClient` (T-F5-04 / T-F5-06)."""

from typing import Any
from uuid import uuid4

import pytest

from ai_service.clients.embeddings import EmbeddingsResponse
from ai_service.clients.embeddings_fake import FakeEmbeddingsClient
from ai_service.config import Settings
from ai_service.core.errors import (
    EmbeddingsDimensionError,
    EmbeddingsError,
    EmbeddingsInvalidVectorError,
)
from ai_service.pipeline.context import PipelineConfiguration, PipelineContext
from ai_service.pipeline.contracts.p3 import P3Config
from ai_service.pipeline.stages import EmbeddingsStage, StageError
from tests import contract_factories as f

TEMPLATE = "{code}. {description}"


def _requirements(count: int) -> tuple:
    base = (f.requirement(), f.requirement_2())
    extra = tuple(
        f.requirement(id=uuid4(), code=f"RF-{n:03d}", description=f"El sistema hace la tarea {n}.")
        for n in range(3, count + 1)
    )
    return (base + extra)[:count]


def _context(count: int = 2) -> PipelineContext:
    ctx = PipelineContext(
        generation_id=uuid4(),
        document_id=f.DOCUMENT_ID,
        configuration=PipelineConfiguration(clustering_enabled=True, method_type="llm_pipeline"),
    )
    # model_copy sin validar: solo interesa la lista de RF.
    ctx.p2_output = f.p2_output().model_copy(update={"requirements": _requirements(count)})
    return ctx


def _response(count: int, dimension: int = 3, **overrides: Any) -> EmbeddingsResponse:
    values: dict[str, Any] = {
        "vectors": tuple(tuple(float(i + j) for j in range(dimension)) for i in range(count)),
        "model_name": "mini",
        "model_version": "1.0",
        "dimension": dimension,
        "normalized": True,
        **overrides,
    }
    return EmbeddingsResponse(**values)


def _stage(client: FakeEmbeddingsClient, *, batch_size: int = 32, max_retries: int = 2) -> EmbeddingsStage:
    config = P3Config(model_name="mini", normalize=True, input_template=TEMPLATE, batch_size=batch_size)
    return EmbeddingsStage(
        embeddings_client=client, config=config, provider="local", max_retries=max_retries, retry_delay_seconds=0
    )


async def test_happy_path_in_batches_builds_p3_output() -> None:
    client = FakeEmbeddingsClient([_response(2), _response(1)])
    ctx = _context(3)

    result = await _stage(client, batch_size=2).run(ctx)

    assert [len(r.texts) for r in client.requests] == [2, 1]
    first = client.requests[0]
    assert first.texts[0] == "RF-001. El sistema permite iniciar sesión con credenciales válidas."
    assert (first.model, first.input_template, first.normalize, first.extra) == ("mini", TEMPLATE, True, {"batch_size": 2})

    output = ctx.p3_output
    assert output is not None
    assert [e.requirement_code for e in output.embeddings] == ["RF-001", "RF-002", "RF-003"]
    assert output.embeddings[2].vector == (0.0, 1.0, 2.0)
    info = output.model_info
    assert (info.provider, info.model_name, info.model_version, info.dimension, info.input_template) == (
        "local", "mini", "1.0", 3, TEMPLATE,
    )

    assert result.llm_runs == () and result.warnings == () and not result.skip_remaining
    assert result.runtime_info["embedding_model"]["provider"] == "local"
    assert {k: result.runtime_info[k] for k in ("batch_size", "batches", "retries_used", "requirements_count")} == {
        "batch_size": 2, "batches": 2, "retries_used": 0, "requirements_count": 3,
    }


async def test_zero_requirements_skips_remaining_without_calling_provider() -> None:
    client = FakeEmbeddingsClient()
    ctx = _context()
    ctx.p2_output = ctx.p2_output.model_copy(update={"requirements": ()})

    result = await _stage(client).run(ctx)

    assert result.skip_remaining and client.requests == [] and ctx.p3_output is None


async def test_requires_p2_output() -> None:
    ctx = _context()
    ctx.p2_output = None
    with pytest.raises(RuntimeError, match="p2_output"):
        await _stage(FakeEmbeddingsClient()).run(ctx)


async def test_transient_error_is_retried() -> None:
    client = FakeEmbeddingsClient([EmbeddingsError("timeout"), _response(2)])
    ctx = _context()

    result = await _stage(client).run(ctx)

    assert len(client.requests) == 2 and ctx.p3_output is not None
    assert result.runtime_info["retries_used"] == 1
    assert [w.code for w in result.warnings] == ["BATCH_RETRIED"]


async def test_exhausted_retries_fail_with_embeddings_failed() -> None:
    client = FakeEmbeddingsClient([EmbeddingsError("timeout")] * 3)

    with pytest.raises(StageError) as exc_info:
        await _stage(client, max_retries=2).run(_context())

    assert len(client.requests) == 3
    assert exc_info.value.code == "EMBEDDINGS_FAILED" and exc_info.value.retryable
    assert exc_info.value.details == {"batch": 1, "errors": ["EMBEDDING_PROVIDER_UNAVAILABLE"] * 3}


@pytest.mark.parametrize("error", [EmbeddingsDimensionError(), EmbeddingsInvalidVectorError()])
async def test_non_transient_errors_are_not_retried(error: EmbeddingsError) -> None:
    client = FakeEmbeddingsClient([error, _response(2)])

    with pytest.raises(StageError) as exc_info:
        await _stage(client).run(_context())

    assert len(client.requests) == 1
    assert exc_info.value.code == "EMBEDDINGS_FAILED" and not exc_info.value.retryable
    assert exc_info.value.details["cause"] == error.code


async def test_vector_count_mismatch_fails() -> None:
    with pytest.raises(StageError, match="número de vectores") as exc_info:
        await _stage(FakeEmbeddingsClient([_response(1)])).run(_context(2))
    assert exc_info.value.code == "EMBEDDINGS_FAILED"


async def test_non_uniform_dimension_across_batches_fails() -> None:
    client = FakeEmbeddingsClient([_response(1, dimension=3), _response(1, dimension=4)])
    with pytest.raises(StageError) as exc_info:
        await _stage(client, batch_size=1).run(_context(2))
    assert exc_info.value.code == "EMBEDDINGS_FAILED"


async def test_non_finite_vector_fails() -> None:
    client = FakeEmbeddingsClient([_response(2, vectors=((1.0, 0.0, 0.0), (float("nan"), 0.0, 0.0)))])
    with pytest.raises(StageError) as exc_info:
        await _stage(client).run(_context(2))
    assert exc_info.value.code == "EMBEDDINGS_FAILED"


# ------------------------------------------------------------ configuración (T-F5-01)
def test_settings_defaults_for_p3_and_p4() -> None:
    s = Settings(_env_file=None)
    assert (s.p3_normalize, s.p3_input_template, s.p3_batch_size, s.p3_max_retries) == (True, TEMPLATE, 32, 2)
    assert (s.p4_metric, s.p4_min_cluster_size, s.p4_min_samples) == ("cosine", 2, 1)


@pytest.mark.parametrize("template", ["{code}", "{otro}", "{description", "{0}"])
def test_invalid_input_template_is_rejected(template: str) -> None:
    with pytest.raises(ValueError, match="P3_INPUT_TEMPLATE"):
        Settings(_env_file=None, p3_input_template=template)


def test_min_cluster_size_below_two_is_rejected() -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, p4_min_cluster_size=1)

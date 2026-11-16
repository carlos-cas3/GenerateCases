"""P5 real (construcción del contexto estructurado, T-F6-03 / T-F6-04). Sin dependencias externas."""

from typing import Any
from uuid import uuid4

import pytest

from ai_service.pipeline.context import PipelineConfiguration, PipelineContext
from ai_service.pipeline.contracts.common import UnitStrategy
from ai_service.pipeline.contracts.p1 import UserStory
from ai_service.pipeline.contracts.p2 import FunctionalRequirement
from ai_service.pipeline.contracts.p4 import ClusterAssignment, P4Output, SemanticCluster
from ai_service.pipeline.contracts.p5 import P5Config
from ai_service.pipeline.stages import ContextStage, StageError
from tests import contract_factories as f

CONFIG = P5Config(max_tokens_per_unit=8000, strategy=UnitStrategy.BY_USER_STORY, instructions_version="v1")


def _story(number: int, text: str | None = None, **overrides: Any) -> UserStory:
    return f.user_story(
        id=uuid4(), code=f"HU-{number:03d}", position=number, content_sections=(),
        original_text=text or f"Como usuario, quiero la función {number}.", **overrides,
    )


def _rf(number: int, *stories: int, description: str | None = None) -> FunctionalRequirement:
    return f.requirement(
        id=uuid4(), code=f"RF-{number:03d}", description=description or f"El sistema hace la tarea {number}.",
        user_story_codes=tuple(f"HU-{s:03d}" for s in stories),
    )


def _cluster(label: int, *requirements: int) -> SemanticCluster:
    return SemanticCluster(
        id=uuid4(), label=label, name=f"Cluster {label}",
        assignments=tuple(ClusterAssignment(requirement_code=f"RF-{n:03d}") for n in requirements),
    )


def _clustering(clusters: tuple[SemanticCluster, ...], unassigned: tuple[int, ...] = ()) -> P4Output:
    return f.p4_output(clusters=clusters, unassigned_requirement_codes=tuple(f"RF-{n:03d}" for n in unassigned))


def _context(
    stories: tuple[UserStory, ...], requirements: tuple[FunctionalRequirement, ...], clustering: P4Output | None = None
) -> PipelineContext:
    ctx = PipelineContext(
        generation_id=uuid4(),
        document_id=f.DOCUMENT_ID,
        configuration=PipelineConfiguration(clustering_enabled=clustering is not None, method_type="llm_pipeline"),
    )
    ctx.p1_output = f.p1_output().model_copy(update={"user_stories": stories})
    ctx.p2_output = f.p2_output().model_copy(update={"requirements": requirements})
    ctx.p4_output = clustering
    return ctx


def _stage(**overrides: Any) -> ContextStage:
    return ContextStage(config=CONFIG.model_copy(update=overrides))


def _codes(items: Any) -> list[str]:
    return [item.code for item in items]


# ---------------------------------------------------------------- by_cluster
async def test_by_cluster_happy_path_with_shared_story_context() -> None:
    # HU-001 origina RF-001 (cluster 0) y RF-003 (cluster 1): se dan contexto mutuamente.
    stories = (_story(1), _story(2), _story(3))
    requirements = (_rf(1, 1), _rf(2, 2), _rf(3, 1), _rf(4, 3))
    ctx = _context(stories, requirements, _clustering((_cluster(1, 3, 4), _cluster(0, 1, 2))))

    result = await _stage().run(ctx)

    generation = ctx.p5_output.context
    assert generation.strategy == UnitStrategy.BY_CLUSTER
    assert generation.generation_id == ctx.generation_id
    assert generation.instructions_version == generation.output_spec.version == "v1"
    first, second = generation.units
    assert (first.unit_id, first.label, first.cluster_label) == ("U-001", "Cluster 0", 0)
    assert (second.unit_id, second.label, second.cluster_label) == ("U-002", "Cluster 1", 1)
    assert _codes(first.requirements) == ["RF-001", "RF-002"]
    assert _codes(first.context_requirements) == ["RF-003"]
    assert _codes(first.user_stories) == ["HU-001", "HU-002"]
    assert first.requirement_to_stories == {"RF-001": ("HU-001",), "RF-002": ("HU-002",), "RF-003": ("HU-001",)}
    assert _codes(second.requirements) == ["RF-003", "RF-004"]
    assert _codes(second.context_requirements) == ["RF-001"]
    assert _codes(second.user_stories) == ["HU-001", "HU-003"]
    assert all(unit.prerequisites == () for unit in generation.units)
    assert result.warnings == ()
    assert result.runtime_info["strategy"] == "by_cluster"
    assert result.runtime_info["units"] == 2
    assert result.runtime_info["requirements_covered"] == 4
    assert result.runtime_info["unassigned_requirements"] == 0
    assert result.runtime_info["instructions_version"] == "v1"


async def test_by_cluster_without_shared_stories_has_no_context_requirements() -> None:
    ctx = _context((_story(1), _story(2)), (_rf(1, 1), _rf(2, 2)), _clustering((_cluster(0, 1), _cluster(1, 2))))

    await _stage().run(ctx)

    assert all(unit.context_requirements == () for unit in ctx.p5_output.context.units)


async def test_by_cluster_copies_user_story_fields() -> None:
    story = f.user_story()
    ctx = _context((story,), (_rf(1, 1),), _clustering((_cluster(0, 1),)))

    await _stage().run(ctx)

    context_story = ctx.p5_output.context.units[0].user_stories[0]
    assert (context_story.code, context_story.original_text) == (story.code, story.original_text)
    assert (context_story.role, context_story.objective, context_story.benefit) == (
        story.role, story.objective, story.benefit,
    )
    assert context_story.content_sections == story.content_sections


async def test_unassigned_requirements_do_not_form_units() -> None:
    ctx = _context((_story(1), _story(2)), (_rf(1, 1), _rf(2, 1), _rf(3, 2)), _clustering((_cluster(0, 1, 2),), (3,)))

    result = await _stage().run(ctx)

    units = ctx.p5_output.context.units
    assert len(units) == 1
    assert _codes(units[0].requirements) == ["RF-001", "RF-002"]
    # RF-003 sin cluster: ni objetivo ni contexto, aunque su HU no comparta nada.
    assert all("RF-003" not in unit.requirement_to_stories for unit in units)
    assert [w.code for w in result.warnings] == ["UNASSIGNED_REQUIREMENTS"]
    assert result.warnings[0].details == {"requirement_codes": ["RF-003"]}
    assert result.runtime_info["unassigned_requirements"] == 1


async def test_unassigned_requirement_is_not_context_even_sharing_a_story() -> None:
    ctx = _context((_story(1),), (_rf(1, 1), _rf(2, 1), _rf(3, 1)), _clustering((_cluster(0, 1, 2),), (3,)))

    await _stage().run(ctx)

    assert ctx.p5_output.context.units[0].context_requirements == ()


async def test_all_requirements_unassigned_gives_no_units() -> None:
    ctx = _context((_story(1),), (_rf(1, 1), _rf(2, 1)), _clustering((), (1, 2)))

    result = await _stage().run(ctx)

    assert ctx.p5_output.context.strategy == UnitStrategy.BY_CLUSTER
    assert ctx.p5_output.context.units == ()
    assert [w.code for w in result.warnings] == ["UNASSIGNED_REQUIREMENTS"]
    assert result.skip_remaining is False


async def test_unit_exceeding_token_limit_is_flagged_not_split() -> None:
    # 400 + 36 caracteres de HU + RF → estimado 109 tokens con límite 100.
    ctx = _context(
        (_story(1, "x" * 400),), (_rf(1, 1, description="d" * 36),), _clustering((_cluster(0, 1),))
    )

    result = await _stage(max_tokens_per_unit=100).run(ctx)

    unit = ctx.p5_output.context.units[0]
    assert (unit.token_estimate, unit.exceeds_limit) == (109, True)
    assert len(unit.requirements) == 1
    assert [w.code for w in result.warnings] == ["UNIT_EXCEEDS_TOKEN_LIMIT"]
    assert result.warnings[0].details == {"unit_id": "U-001", "token_estimate": 109, "max_tokens_per_unit": 100}
    assert result.runtime_info["units_exceeding_limit"] == ["U-001"]


async def test_unit_within_token_limit_is_not_flagged() -> None:
    ctx = _context(
        (_story(1, "x" * 400),), (_rf(1, 1, description="d" * 36),), _clustering((_cluster(0, 1),))
    )

    result = await _stage(max_tokens_per_unit=109).run(ctx)

    unit = ctx.p5_output.context.units[0]
    assert (unit.token_estimate, unit.exceeds_limit) == (109, False)
    assert result.warnings == ()


async def test_token_estimate_counts_context_requirements() -> None:
    stories = (_story(1, "h" * 40),)
    requirements = (_rf(1, 1, description="a" * 20), _rf(2, 1, description="b" * 20))
    ctx = _context(stories, requirements, _clustering((_cluster(0, 1), _cluster(1, 2))))

    await _stage().run(ctx)

    # 20 (objetivo) + 20 (contexto) + 40 (HU) = 80 caracteres → 20 tokens.
    assert [unit.token_estimate for unit in ctx.p5_output.context.units] == [20, 20]


# ---------------------------------------------------------------- by_user_story
async def test_by_user_story_happy_path() -> None:
    stories = (_story(1), _story(2), _story(3))
    requirements = (_rf(1, 1), _rf(2, 2), _rf(3, 3), _rf(4, 1))
    ctx = _context(stories, requirements)

    result = await _stage().run(ctx)

    generation = ctx.p5_output.context
    assert generation.strategy == UnitStrategy.BY_USER_STORY
    assert [(u.unit_id, u.label) for u in generation.units] == [("U-001", "HU-001"), ("U-002", "HU-002"), ("U-003", "HU-003")]
    assert [_codes(u.requirements) for u in generation.units] == [["RF-001", "RF-004"], ["RF-002"], ["RF-003"]]
    assert all(u.cluster_label is None and u.context_requirements == () for u in generation.units)
    assert all(u.prerequisites == () for u in generation.units)
    assert result.warnings == ()
    assert result.runtime_info["strategy"] == "by_user_story"
    assert result.runtime_info["requirements_covered"] == 4
    assert "unassigned_requirements" not in result.runtime_info


async def test_requirement_with_several_stories_goes_to_lowest_position() -> None:
    # RF-002 cita HU-003 antes que HU-002: manda la posición, no el orden de la tupla.
    stories = (_story(1), _story(2), _story(3))
    ctx = _context(stories, (_rf(1, 1), _rf(2, 3, 2), _rf(3, 3)))

    await _stage().run(ctx)

    units = ctx.p5_output.context.units
    assert [(u.label, _codes(u.requirements)) for u in units] == [
        ("HU-001", ["RF-001"]), ("HU-002", ["RF-002"]), ("HU-003", ["RF-003"]),
    ]
    assert _codes(units[1].user_stories) == ["HU-002", "HU-003"]
    assert units[1].requirement_to_stories == {"RF-002": ("HU-003", "HU-002")}


async def test_story_without_requirements_has_no_unit() -> None:
    ctx = _context((_story(1), _story(2), _story(3)), (_rf(1, 1), _rf(2, 3)))

    await _stage().run(ctx)

    units = ctx.p5_output.context.units
    assert [u.label for u in units] == ["HU-001", "HU-003"]
    assert [u.unit_id for u in units] == ["U-001", "U-002"]
    assert all("HU-002" not in _codes(u.user_stories) for u in units)


async def test_invalid_story_without_requirements_is_ignored() -> None:
    stories = (_story(1), _story(2, validation_status="invalid"))
    ctx = _context(stories, (_rf(1, 1),))

    await _stage().run(ctx)

    assert _codes(ctx.p5_output.context.units[0].user_stories) == ["HU-001"]


async def test_requirement_from_invalid_story_fails_context_build() -> None:
    stories = (_story(1), _story(2, validation_status="invalid"))
    ctx = _context(stories, (_rf(1, 1), _rf(2, 2)))

    with pytest.raises(StageError) as exc_info:
        await _stage().run(ctx)

    assert exc_info.value.code == "CONTEXT_BUILD_FAILED"
    assert ctx.p5_output is None


# ---------------------------------------------------------------- guardias comunes
async def test_missing_p1_output_raises_runtime_error() -> None:
    ctx = _context((_story(1),), (_rf(1, 1),))
    ctx.p1_output = None
    with pytest.raises(RuntimeError, match="p1_output"):
        await _stage().run(ctx)


async def test_missing_p2_output_raises_runtime_error() -> None:
    ctx = _context((_story(1),), (_rf(1, 1),))
    ctx.p2_output = None
    with pytest.raises(RuntimeError, match="p2_output"):
        await _stage().run(ctx)


async def test_strategy_comes_from_p4_output_not_from_config_or_flag() -> None:
    # Config provisional by_cluster y clustering_enabled=True, pero sin p4_output → by_user_story.
    ctx = _context((_story(1),), (_rf(1, 1),))
    ctx.configuration = PipelineConfiguration(clustering_enabled=True, method_type="llm_pipeline")

    await _stage(strategy=UnitStrategy.BY_CLUSTER).run(ctx)

    assert ctx.p5_output.context.strategy == UnitStrategy.BY_USER_STORY


async def test_present_p4_output_selects_by_cluster() -> None:
    ctx = _context((_story(1),), (_rf(1, 1),), _clustering((_cluster(0, 1),)))
    ctx.configuration = PipelineConfiguration(clustering_enabled=False, method_type="llm_pipeline")

    await _stage(strategy=UnitStrategy.BY_USER_STORY).run(ctx)

    assert ctx.p5_output.context.strategy == UnitStrategy.BY_CLUSTER


async def test_clustering_inconsistent_with_requirements_fails_context_build() -> None:
    # P4 no conoce RF-002: P5Input lo rechaza.
    ctx = _context((_story(1),), (_rf(1, 1), _rf(2, 1)), _clustering((_cluster(0, 1),)))

    with pytest.raises(StageError) as exc_info:
        await _stage().run(ctx)

    assert exc_info.value.code == "CONTEXT_BUILD_FAILED"


async def test_stage_config_is_not_mutated_between_runs() -> None:
    stage = _stage()
    await stage.run(_context((_story(1),), (_rf(1, 1),), _clustering((_cluster(0, 1),))))
    ctx = _context((_story(1),), (_rf(1, 1),))

    await stage.run(ctx)

    assert ctx.p5_output.context.strategy == UnitStrategy.BY_USER_STORY

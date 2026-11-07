"""Invariantes del diseño expresadas en los contratos P1–P6."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from ai_service.pipeline.contracts import common, p1, p2, p3, p4, p5, p6
from tests import contract_factories as f


# ---------------------------------------------------------------- common
@pytest.mark.parametrize("code", ["", "HU-1", "hu-001", "RF-001", "HU-001 "])
def test_user_story_code_format(code: str) -> None:
    with pytest.raises(ValidationError):
        f.user_story(code=code)


def test_blank_text_is_rejected() -> None:
    with pytest.raises(ValidationError, match="vacío"):
        p1.StorySection(kind="  ", text="x")


def test_source_span_must_be_ordered() -> None:
    with pytest.raises(ValidationError, match="end debe ser"):
        common.SourceSpan(user_story_code="HU-001", start=5, end=2)


def test_unknown_enum_value_is_rejected() -> None:
    with pytest.raises(ValidationError):
        f.user_story(validation_status="otra")


# ---------------------------------------------------------------- P1
def test_story_without_template_components_is_valid() -> None:
    story = f.user_story(role=None, objective=None, benefit=None, content_sections=())
    assert story.validation_status == common.StoryValidationStatus.VALID


def test_valid_with_warnings_requires_an_issue() -> None:
    with pytest.raises(ValidationError, match="al menos una incidencia"):
        f.user_story(validation_status="valid_with_warnings", issues=())


def test_valid_story_cannot_have_error_issues() -> None:
    issue = p1.ValidationIssue(rule_code="X", severity="error", message="m")
    with pytest.raises(ValidationError, match="severidad error"):
        f.user_story(issues=(issue,))


def test_p1_output_counts_must_match() -> None:
    with pytest.raises(ValidationError, match="conteos"):
        f.p1_output(valid_count=2)


def test_p1_output_needs_a_processable_story() -> None:
    with pytest.raises(ValidationError, match="procesable"):
        f.p1_output(user_stories=(f.invalid_story(),), valid_count=0, warning_count=0, invalid_count=1)


def test_p1_output_rejects_duplicate_positions() -> None:
    with pytest.raises(ValidationError, match="posiciones"):
        f.p1_output(user_stories=(f.user_story(), f.user_story(id=uuid4(), code="HU-009", content_sections=())), valid_count=2,
                    warning_count=0, invalid_count=0)


def test_p1_config_rejects_invalid_regex() -> None:
    with pytest.raises(ValidationError, match="regular"):
        p1.P1Config(rules_version="v1", story_delimiter_pattern="(", max_story_chars=10)


# ---------------------------------------------------------------- P2
def test_p2_input_rejects_invalid_stories() -> None:
    with pytest.raises(ValidationError, match="invalid no entran"):
        p2.P2Input(generation_id=f.GENERATION_ID, user_stories=(f.user_story(), f.invalid_story()),
                   config=f.p2_config())


def test_p2_output_allows_zero_requirements() -> None:
    output = f.p2_output(requirements=(), quality=(), findings=(), stories_without_requirements=("HU-001", "HU-002"))
    assert output.requirements == ()
    assert output.to_rpc_payload()["requirements"] == []


def test_p2_output_requires_one_classification_per_story() -> None:
    duplicated = f.classifications() + (f.classifications()[0],)
    with pytest.raises(ValidationError, match="clasificaciones de HU repetidos"):
        f.p2_output(classifications=duplicated)


def test_requirement_must_reference_a_classified_story() -> None:
    with pytest.raises(ValidationError, match="no tiene clasificación"):
        f.p2_output(requirements=(f.requirement(user_story_codes=("HU-007",)),))


def test_no_aplicable_story_cannot_produce_requirements() -> None:
    with pytest.raises(ValidationError, match="no_aplicable"):
        f.p2_output(requirements=(f.requirement(user_story_codes=("HU-002",)),), stories_without_requirements=("HU-001",))


def test_stories_without_requirements_must_be_exact() -> None:
    with pytest.raises(ValidationError, match="stories_without_requirements"):
        f.p2_output(stories_without_requirements=())


def test_requirement_codes_unique_in_p2_output() -> None:
    with pytest.raises(ValidationError, match="códigos de RF"):
        f.p2_output(requirements=(f.requirement(), f.requirement(id=uuid4())), findings=())


def test_requirement_needs_a_source_story() -> None:
    with pytest.raises(ValidationError):
        f.requirement(user_story_codes=())
    with pytest.raises(ValidationError, match="user_story_codes repetidos"):
        f.requirement(user_story_codes=("HU-001", "HU-001"))


def test_requirement_evidence_must_come_from_its_stories() -> None:
    evidence = common.RequirementEvidence(user_story_code="HU-002", text="x")
    with pytest.raises(ValidationError, match="evidencia"):
        f.requirement(evidence=(evidence,))


def test_requirement_without_literal_source_text_is_allowed() -> None:
    assert f.requirement(source_text=None).source_text is None


def test_duplicate_finding_needs_two_requirements() -> None:
    with pytest.raises(ValidationError, match="al menos 2"):
        p2.RequirementFinding(kind="potential_duplicate", requirement_codes=("RF-001",), detected_by="rule")


def test_needs_review_follows_flags() -> None:
    criterion = p2.CriterionAssessment(criterion="ambiguity", flagged=True, method="llm")
    with pytest.raises(ValidationError, match="needs_review"):
        p2.RequirementQualityAssessment(requirement_code="RF-001", criteria=(criterion,), needs_review=False)


# ---------------------------------------------------------------- P3 / P4
def test_embeddings_must_have_uniform_dimension() -> None:
    bad = p3.RequirementEmbedding(requirement_code="RF-002", vector=(1.0, 0.0))
    with pytest.raises(ValidationError, match="dimensión"):
        f.p3_output(embeddings=(f.p3_output().embeddings[0], bad))


@pytest.mark.parametrize("component", [float("nan"), float("inf")])
def test_embeddings_reject_non_finite_values(component: float) -> None:
    with pytest.raises(ValidationError, match="NaN"):
        p3.RequirementEmbedding(requirement_code="RF-001", vector=(component, 0.0, 0.0))


def test_p4_input_requires_one_vector_per_requirement() -> None:
    with pytest.raises(ValidationError, match="EMBEDDING_REQUIREMENT_MISMATCH"):
        p4.P4Input(generation_id=f.GENERATION_ID, requirements=(f.requirement(),), embeddings=f.p3_output(),
                   config=f.p4_config())


def test_requirement_may_belong_to_several_clusters() -> None:
    second = f.cluster(id=uuid4(), label=1, name="Grupo 1")
    assert len(f.p4_output(clusters=(f.cluster(), second)).clusters) == 2


def test_requirement_cannot_be_assigned_and_unassigned() -> None:
    with pytest.raises(ValidationError, match="a la vez"):
        f.p4_output(unassigned_requirement_codes=("RF-001",))


def test_cluster_labels_are_unique() -> None:
    with pytest.raises(ValidationError, match="labels"):
        f.p4_output(clusters=(f.cluster(), f.cluster(id=uuid4())))


def test_cluster_requires_id() -> None:
    with pytest.raises(ValidationError, match="id"):
        p4.SemanticCluster(label=0, name="G", assignments=f.cluster().assignments)


# ---------------------------------------------------------------- P5
def test_unit_distinguishes_targets_from_context() -> None:
    unit = f.context_unit(
        context_requirements=(p5.ContextRequirement(code="RF-002", description="Bloqueo."),),
        requirement_to_stories={"RF-001": ("HU-001",), "RF-002": ("HU-001",)},
    )
    assert unit.target_codes() == {"RF-001"}


def test_requirement_cannot_be_target_and_context_in_the_same_unit() -> None:
    with pytest.raises(ValidationError, match="RF de la unidad"):
        f.context_unit(context_requirements=(p5.ContextRequirement(code="RF-001", description="x"),))


def test_requirement_is_target_in_a_single_unit() -> None:
    second = f.context_unit(unit_id="U-002")
    with pytest.raises(ValidationError, match="RF objetivo entre unidades"):
        f.generation_context(units=(f.context_unit(), second))


def test_unit_requires_story_mapping_for_every_requirement() -> None:
    with pytest.raises(ValidationError, match="sin relación"):
        f.context_unit(requirement_to_stories={})


def test_unit_rejects_unreferenced_stories() -> None:
    extra = p5.ContextUserStory(code="HU-002", original_text="x")
    with pytest.raises(ValidationError, match="HU sin RF"):
        f.context_unit(user_stories=f.context_unit().user_stories + (extra,))


def test_generation_context_allows_empty_units_only_with_clustering() -> None:
    assert f.generation_context(units=()).units == ()
    with pytest.raises(ValidationError, match="al menos una unidad"):
        f.generation_context_without_clustering(units=())


def test_by_user_story_rejects_context_requirements() -> None:
    unit = f.context_unit_without_clustering(
        context_requirements=(p5.ContextRequirement(code="RF-002", description="Bloqueo."),),
        requirement_to_stories={"RF-001": ("HU-001",), "RF-002": ("HU-001",)},
    )
    with pytest.raises(ValidationError, match="context_requirements"):
        f.generation_context_without_clustering(units=(unit,))


def test_by_user_story_units_have_no_cluster() -> None:
    with pytest.raises(ValidationError, match="by_user_story"):
        f.generation_context(strategy="by_user_story")


def test_p5_input_strategy_must_match_clustering() -> None:
    with pytest.raises(ValidationError, match="strategy"):
        f.p5_input(clustering=None)
    assert f.p5_input(clustering=None, config=f.p5_config(strategy="by_user_story")).clustering is None


def test_p5_input_only_accepts_stories_that_originated_requirements() -> None:
    with pytest.raises(ValidationError, match="sobran"):
        f.p5_input(user_stories=(f.user_story(), f.warning_story()))


# ---------------------------------------------------------------- P6
def test_test_case_requirement_codes_have_no_duplicates() -> None:
    link = p6.RequirementTestCaseLink(requirement_code="RF-001")
    with pytest.raises(ValidationError, match="requirement_codes repetidos"):
        f.sample_test_case(requirement_links=(link, link))
    raw = {"title": "t", "steps": [{"step_number": 1, "action": "a"}], "expected_result": "r",
           "requirement_codes": ["RF-001", "RF-001"]}
    with pytest.raises(ValidationError, match="requirement_codes repetidos"):
        p6.TestCaseDraft.model_validate(raw)


@pytest.mark.parametrize("numbers", [(2,), (1, 3), (1, 1)])
def test_steps_are_consecutive_from_one(numbers: tuple[int, ...]) -> None:
    steps = tuple(p6.TestStep(step_number=n, action="a") for n in numbers)
    with pytest.raises(ValidationError, match="consecutivamente"):
        f.sample_test_case(steps=steps)


def test_test_case_requires_steps_and_links() -> None:
    with pytest.raises(ValidationError):
        f.sample_test_case(steps=())
    with pytest.raises(ValidationError):
        f.sample_test_case(requirement_links=())


def test_links_leave_p6_as_pending_without_method() -> None:
    validated = p6.RequirementTestCaseLink(requirement_code="RF-001", status="validated", validation_method="manual")
    with pytest.raises(ValidationError, match="pending"):
        f.unit_output(test_cases=(f.sample_test_case(requirement_links=(validated,)),))


def test_test_case_codes_are_global_and_consecutive() -> None:
    second = f.unit_output(unit_id="U-002", test_cases=(f.sample_test_case(id=uuid4(), code="CP-003"),))
    with pytest.raises(ValidationError, match="consecutivos"):
        f.p6_output(units=(f.unit_output(), second))
    ok = f.unit_output(unit_id="U-002", test_cases=(f.sample_test_case(id=uuid4(), code="CP-002"),))
    assert [case.code for case in f.p6_output(units=(f.unit_output(), ok)).test_cases] == ["CP-001", "CP-002"]


def test_p6_stops_at_the_first_failed_unit() -> None:
    failure = p6.UnitFailure(unit_id="U-002", error_code="UNIT_GENERATION_FAILED", message="m")
    assert f.p6_output(failed_units=(failure,)).failed_units == (failure,)
    with pytest.raises(ValidationError):
        f.p6_output(failed_units=(failure, failure.model_copy(update={"unit_id": "U-003"})))
    with pytest.raises(ValidationError, match="fallida"):
        f.p6_output(failed_units=(failure.model_copy(update={"unit_id": "U-001"}),))


def test_uncovered_requirements_have_no_cases() -> None:
    with pytest.raises(ValidationError, match="sin cubrir"):
        f.p6_output(uncovered_requirement_codes=("RF-001",))


def test_p6_input_context_belongs_to_the_generation() -> None:
    with pytest.raises(ValidationError, match="otra generación"):
        p6.P6Input(generation_id=uuid4(), context=f.generation_context(), config=f.p6_config())


def test_p6_config_only_supports_failing_the_stage() -> None:
    with pytest.raises(ValidationError):
        p6.P6Config(prompt_version="v", llm=f.LLM, max_retries=1, on_unit_failure="continue")

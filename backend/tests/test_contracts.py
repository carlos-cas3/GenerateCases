"""Propiedades comunes de los contratos P1–P6: inmutables, sin extras, salida del LLM y openapi."""

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from ai_service.pipeline.contracts import common, p2, p6
from tests import contract_factories as f

CONTRACTS = f.all_contracts()
SPEC = yaml.safe_load((Path(__file__).resolve().parents[1] / "docs" / "openapi.yaml").read_text(encoding="utf-8"))


def _first_field(instance: common.ContractModel) -> str:
    return next(iter(type(instance).model_fields))


@pytest.mark.parametrize("name", CONTRACTS)
def test_contract_is_frozen(name: str) -> None:
    instance = CONTRACTS[name]
    with pytest.raises(ValidationError, match="frozen"):
        setattr(instance, _first_field(instance), getattr(instance, _first_field(instance)))


@pytest.mark.parametrize("name", CONTRACTS)
def test_contract_rejects_unknown_fields(name: str) -> None:
    instance = CONTRACTS[name]
    data = instance.model_dump()
    data["campo_desconocido"] = 1
    with pytest.raises(ValidationError, match="extra"):
        type(instance).model_validate(data)


@pytest.mark.parametrize("name", CONTRACTS)
def test_contract_round_trips_through_json(name: str) -> None:
    instance = CONTRACTS[name]
    assert type(instance).model_validate_json(instance.model_dump_json()) == instance


def test_every_contract_inherits_from_the_common_base() -> None:
    assert all(isinstance(instance, common.ContractModel) for instance in CONTRACTS.values())
    assert common.ContractModel.model_config["frozen"] is True
    assert common.ContractModel.model_config["extra"] == "forbid"
    assert not common.ContractModel.model_config.get("strict", False)


# ---------------------------------------------------------------- salida del LLM
@pytest.mark.parametrize("model", [p2.P2LlmResponse, p2.RequirementDraft, p2.StoryClassification,
                                   p6.P6LlmResponse, p6.TestCaseDraft])
def test_llm_contracts_produce_json_schema(model) -> None:
    schema = model.model_json_schema()
    Draft202012Validator.check_schema(schema)
    json.dumps(schema)


def test_p2_llm_response_validates_with_context() -> None:
    parsed = p2.P2LlmResponse.model_validate_json(f.P2_LLM_JSON, context={"user_story_codes": {"HU-001", "HU-002"}})
    assert parsed.requirements[0].user_story_codes == ("HU-001",)

    with pytest.raises(ValidationError, match="faltan"):
        p2.P2LlmResponse.model_validate_json(f.P2_LLM_JSON, context={"user_story_codes": {"HU-001", "HU-002", "HU-004"}})
    with pytest.raises(ValidationError, match="HU inexistentes"):
        p2.P2LlmResponse.model_validate_json(f.P2_LLM_JSON, context={"user_story_codes": {"HU-002"}})


def test_p2_llm_response_cannot_assign_codes() -> None:
    raw = json.loads(f.P2_LLM_JSON)
    raw["requirements"][0]["code"] = "RF-001"
    with pytest.raises(ValidationError, match="extra"):
        p2.P2LlmResponse.model_validate(raw)


def test_p6_llm_response_validates_with_unit_targets() -> None:
    parsed = p6.P6LlmResponse.model_validate_json(f.P6_LLM_JSON, context={"target_codes": {"RF-001"}})
    assert parsed.test_cases[0].test_data.inputs == {"email": "a@b.c"}

    with pytest.raises(ValidationError, match="no son objetivo"):
        p6.P6LlmResponse.model_validate_json(f.P6_LLM_JSON, context={"target_codes": {"RF-002"}})


def test_p6_llm_response_rejects_malformed_test_data() -> None:
    raw = json.loads(f.P6_LLM_JSON)
    raw["test_cases"][0]["test_data"] = {"email": "a@b.c"}  # falta `inputs`: clave desconocida
    with pytest.raises(ValidationError, match="extra"):
        p6.P6LlmResponse.model_validate(raw)


def test_output_spec_embeds_the_llm_schema() -> None:
    spec = p6.default_output_spec("p6-v1")
    assert spec.json_schema == p6.P6LlmResponse.model_json_schema()


# ---------------------------------------------------------------- openapi
def _openapi_schema(name: str) -> dict:
    return SPEC["components"]["schemas"][name]


def _enum(schema: dict) -> set[str]:
    return {value for value in schema["enum"] if value is not None}


def test_openapi_test_data_example_is_a_valid_test_data() -> None:
    example = SPEC["paths"]["/api/v1/generations/{generation_id}/test-cases/{test_case_id}"]["get"]["responses"][
        "200"]["content"]["application/json"]["example"]["test_data"]
    assert common.TestData.model_validate(example).inputs == example["inputs"]


def test_test_data_contract_matches_openapi_schema() -> None:
    schema = _openapi_schema("TestData")
    assert set(common.TestData.model_fields) == set(schema["properties"])
    full = common.TestData(preconditions=("a",), inputs={"k": "v"}, expected_results=("b",), notes="n")
    Draft202012Validator(schema).validate(full.model_dump(mode="json"))


def test_enums_match_openapi() -> None:
    user_story = _openapi_schema("UserStory")["properties"]
    assert _enum(user_story["validation_status"]) == {item.value for item in common.StoryValidationStatus}
    assert _enum(user_story["classification"]) == {item.value for item in common.StoryClassificationCategory}
    assert _enum(_openapi_schema("RelationStatus")) == {item.value for item in common.RelationStatus}
    assert _enum(_openapi_schema("FindingSeverity")) == {item.value for item in common.IssueSeverity}
    assert _enum(_openapi_schema("Document")["properties"]["file_type"]) == {item.value for item in common.FileType}


def test_cluster_list_unassigned_field_has_a_counterpart_in_p4() -> None:
    assert "unassigned_requirement_ids" in _openapi_schema("ClusterList")["required"]
    assert f.p4_output().unassigned_requirement_codes == ("RF-002",)

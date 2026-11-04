"""Instancias válidas y coherentes de los contratos P1–P6 para las pruebas.

Escenario: HU-001 (valid) origina RF-001 y RF-002; HU-002 (valid_with_warnings) es no_aplicable;
HU-003 es invalid. P4 agrupa RF-001 en el cluster 0 y deja RF-002 sin asignar. P6 genera CP-001.
"""

from typing import Any
from uuid import UUID

from ai_service.pipeline.contracts import common, p1, p2, p3, p4, p5, p6

GENERATION_ID = UUID("b7a2f9c4-8e31-4f6a-9d2c-1a5e7f0b3c88")
DOCUMENT_ID = UUID("6f9d1c2e-0a4b-4c8d-9e1f-2b3c4d5e6f70")
HU1_ID = UUID("00000000-0000-4000-8000-000000000001")
HU2_ID = UUID("00000000-0000-4000-8000-000000000002")
HU3_ID = UUID("00000000-0000-4000-8000-000000000003")
RF1_ID = UUID("00000000-0000-4000-8000-000000000011")
RF2_ID = UUID("00000000-0000-4000-8000-000000000012")
CLUSTER_ID = UUID("00000000-0000-4000-8000-000000000021")
CP1_ID = UUID("00000000-0000-4000-8000-000000000031")

HU1_TEXT = "Como usuario, quiero iniciar sesión para acceder a mi panel. Criterio: bloquear tras 3 intentos."

LLM = common.LlmSettings(provider="fake", model="modelo-x", parameters={"temperature": 0})


# ---------------------------------------------------------------- P1
def source_document(**overrides: Any) -> p1.SourceDocument:
    values = {"document_id": DOCUMENT_ID, "filename": "historias.txt", "file_type": "txt", "text": HU1_TEXT}
    return p1.SourceDocument(**{**values, **overrides})


def p1_config() -> p1.P1Config:
    return p1.P1Config(rules_version="v1", story_delimiter_pattern=r"^---$", max_story_chars=4000)


def user_story(**overrides: Any) -> p1.UserStory:
    values: dict[str, Any] = {
        "id": HU1_ID,
        "code": "HU-001",
        "original_text": HU1_TEXT,
        "role": "usuario",
        "objective": "iniciar sesión",
        "benefit": "acceder a mi panel",
        "validation_status": "valid",
        "position": 1,
        "content_sections": (
            p1.StorySection(
                kind="acceptance_criteria",
                text="bloquear tras 3 intentos",
                source_span=common.SourceSpan(user_story_code="HU-001", start=71, end=95),
            ),
        ),
    }
    return p1.UserStory(**{**values, **overrides})


def warning_story() -> p1.UserStory:
    return p1.UserStory(
        id=HU2_ID, code="HU-002", original_text="El sistema existe desde 2010.", validation_status="valid_with_warnings",
        position=2,
        issues=(p1.ValidationIssue(rule_code="UNCERTAIN_BOUNDARY", severity="warning", message="Límite incierto."),),
    )


def invalid_story() -> p1.UserStory:
    return p1.UserStory(
        id=HU3_ID, code="HU-003", original_text="��", validation_status="invalid", position=3,
        issues=(p1.ValidationIssue(rule_code="CORRUPTED_TEXT", severity="error", message="Texto ilegible."),),
    )


def p1_input() -> p1.P1Input:
    return p1.P1Input(generation_id=GENERATION_ID, document=source_document(), config=p1_config())


def p1_output(**overrides: Any) -> p1.P1Output:
    values: dict[str, Any] = {
        "user_stories": (user_story(), warning_story(), invalid_story()),
        "unresolved_fragments": (p1.UnresolvedFragment(text="Notas sueltas", position=4, reason="sin HU"),),
        "valid_count": 1,
        "warning_count": 1,
        "invalid_count": 1,
    }
    return p1.P1Output(**{**values, **overrides})


# ---------------------------------------------------------------- P2
def classifications() -> tuple[p2.StoryClassification, ...]:
    return (
        p2.StoryClassification(
            user_story_code="HU-001", category="candidata_funcional", rationale="Describe un acceso al sistema.",
            evidence=(common.RequirementEvidence(user_story_code="HU-001", text="quiero iniciar sesión"),),
        ),
        p2.StoryClassification(
            user_story_code="HU-002", category="no_aplicable", rationale="Texto informativo.",
        ),
    )


def requirement(**overrides: Any) -> p2.FunctionalRequirement:
    values: dict[str, Any] = {
        "id": RF1_ID,
        "code": "RF-001",
        "description": "El sistema permite iniciar sesión con credenciales válidas.",
        "source_text": "quiero iniciar sesión",
        "user_story_codes": ("HU-001",),
        "actor": "usuario",
        "unspecified_information": ("Formato de las credenciales",),
    }
    return p2.FunctionalRequirement(**{**values, **overrides})


def requirement_2() -> p2.FunctionalRequirement:
    return requirement(
        id=RF2_ID, code="RF-002", description="El sistema bloquea la cuenta tras 3 intentos fallidos.",
        source_text="bloquear tras 3 intentos", acceptance_criteria=("bloquear tras 3 intentos",),
    )


def p2_config() -> p2.P2Config:
    return p2.P2Config(prompt_version="p2-v1", llm=LLM, max_stories_per_call=10, max_retries=2)


def p2_input() -> p2.P2Input:
    return p2.P2Input(generation_id=GENERATION_ID, user_stories=(user_story(), warning_story()), config=p2_config())


def p2_output(**overrides: Any) -> p2.P2Output:
    values: dict[str, Any] = {
        "classifications": classifications(),
        "requirements": (requirement(), requirement_2()),
        "quality": (
            p2.RequirementQualityAssessment(
                requirement_code="RF-001",
                criteria=(p2.CriterionAssessment(criterion="grounding", value=1.0, flagged=False, method="rule"),),
                needs_review=False,
            ),
        ),
        "findings": (
            p2.RequirementFinding(kind="potential_duplicate", requirement_codes=("RF-001", "RF-002"), detected_by="lexical"),
        ),
        "stories_without_requirements": ("HU-002",),
    }
    return p2.P2Output(**{**values, **overrides})


P2_LLM_JSON = """{
  "classifications": [
    {"user_story_code": "HU-001", "category": "candidata_funcional", "rationale": "Acceso al sistema."},
    {"user_story_code": "HU-002", "category": "no_aplicable", "rationale": "Informativo."}
  ],
  "requirements": [
    {"description": "El sistema permite iniciar sesión.", "source_text": "quiero iniciar sesión",
     "user_story_codes": ["HU-001"], "preconditions": [], "unspecified_information": ["Formato de credenciales"]}
  ]
}"""


# ---------------------------------------------------------------- P3
def embedding_model() -> p3.EmbeddingModelInfo:
    return p3.EmbeddingModelInfo(
        provider="local", model_name="mini", dimension=3, normalized=True, input_template="{description}"
    )


def p3_config() -> p3.P3Config:
    return p3.P3Config(model_name="mini", normalize=True, input_template="{description}", batch_size=32)


def p3_input() -> p3.P3Input:
    return p3.P3Input(generation_id=GENERATION_ID, requirements=(requirement(), requirement_2()), config=p3_config())


def p3_output(**overrides: Any) -> p3.P3Output:
    values: dict[str, Any] = {
        "model_info": embedding_model(),
        "embeddings": (
            p3.RequirementEmbedding(requirement_code="RF-001", vector=(1.0, 0.0, 0.0)),
            p3.RequirementEmbedding(requirement_code="RF-002", vector=(0.0, 1.0, 0.0)),
        ),
    }
    return p3.P3Output(**{**values, **overrides})


# ---------------------------------------------------------------- P4
def p4_config() -> p4.P4Config:
    return p4.P4Config(algorithm="hdbscan", metric="cosine", params={"min_cluster_size": 2})


def p4_input() -> p4.P4Input:
    return p4.P4Input(
        generation_id=GENERATION_ID, requirements=(requirement(), requirement_2()), embeddings=p3_output(),
        config=p4_config(),
    )


def cluster(**overrides: Any) -> p4.SemanticCluster:
    values: dict[str, Any] = {
        "id": CLUSTER_ID,
        "label": 0,
        "name": "Grupo 0",
        "assignments": (p4.ClusterAssignment(requirement_code="RF-001", similarity_to_centroid=0.92),),
    }
    return p4.SemanticCluster(**{**values, **overrides})


def p4_output(**overrides: Any) -> p4.P4Output:
    values: dict[str, Any] = {
        "clusters": (cluster(),),
        "unassigned_requirement_codes": ("RF-002",),
        "algorithm_info": p4.ClusteringAlgorithmInfo(
            name="hdbscan", metric="cosine", params={"min_cluster_size": 2}, embedding_model=embedding_model()
        ),
    }
    return p4.P4Output(**{**values, **overrides})


# ---------------------------------------------------------------- P5
def output_spec() -> p5.TestCaseOutputSpec:
    return p6.default_output_spec("p6-v1")


def p5_config(**overrides: Any) -> p5.P5Config:
    values = {"max_tokens_per_unit": 6000, "strategy": "by_cluster", "instructions_version": "i-v1"}
    return p5.P5Config(**{**values, **overrides})


def p5_input(**overrides: Any) -> p5.P5Input:
    values: dict[str, Any] = {
        "generation_id": GENERATION_ID,
        "user_stories": (user_story(),),
        "requirements": (requirement(), requirement_2()),
        "clustering": p4_output(),
        "output_spec": output_spec(),
        "config": p5_config(),
    }
    return p5.P5Input(**{**values, **overrides})


def context_unit(**overrides: Any) -> p5.ContextUnit:
    values: dict[str, Any] = {
        "unit_id": "U-001",
        "label": "Grupo 0",
        "cluster_label": 0,
        "requirements": (p5.ContextRequirement(code="RF-001", description="Iniciar sesión."),),
        "user_stories": (p5.ContextUserStory(code="HU-001", original_text=HU1_TEXT, objective="iniciar sesión"),),
        "requirement_to_stories": {"RF-001": ("HU-001",)},
        "token_estimate": 350,
    }
    return p5.ContextUnit(**{**values, **overrides})


def generation_context(**overrides: Any) -> p5.GenerationContext:
    values: dict[str, Any] = {
        "generation_id": GENERATION_ID,
        "output_spec": output_spec(),
        "instructions_version": "i-v1",
        "strategy": "by_cluster",
        "units": (context_unit(),),
    }
    return p5.GenerationContext(**{**values, **overrides})


def p5_output() -> p5.P5Output:
    return p5.P5Output(context=generation_context())


# ---------------------------------------------------------------- P6
def sample_test_case(**overrides: Any) -> p6.TestCase:
    values: dict[str, Any] = {
        "id": CP1_ID,
        "code": "CP-001",
        "title": "Inicio de sesión con credenciales válidas",
        "preconditions": ("El usuario está registrado",),
        "test_data": common.TestData(inputs={"email": "usuario@ejemplo.com"}),
        "steps": (
            p6.TestStep(step_number=1, action="Ingresar correo y contraseña"),
            p6.TestStep(step_number=2, action="Pulsar «Iniciar sesión»", expected_result="Se muestra el panel"),
        ),
        "expected_result": "El sistema muestra el panel principal.",
        "requirement_links": (p6.RequirementTestCaseLink(requirement_code="RF-001"),),
    }
    return p6.TestCase(**{**values, **overrides})


def unit_output(**overrides: Any) -> p6.P6UnitOutput:
    values: dict[str, Any] = {"unit_id": "U-001", "test_cases": (sample_test_case(),)}
    return p6.P6UnitOutput(**{**values, **overrides})


def p6_config() -> p6.P6Config:
    return p6.P6Config(prompt_version="p6-v1", llm=LLM, max_retries=2)


def p6_input() -> p6.P6Input:
    return p6.P6Input(generation_id=GENERATION_ID, context=generation_context(), config=p6_config())


def p6_output(**overrides: Any) -> p6.P6Output:
    values: dict[str, Any] = {"units": (unit_output(),), "uncovered_requirement_codes": ("RF-002",)}
    return p6.P6Output(**{**values, **overrides})


P6_LLM_JSON = """{
  "test_cases": [
    {"title": "Login válido", "preconditions": ["Usuario registrado"],
     "test_data": {"inputs": {"email": "a@b.c"}, "notes": null},
     "steps": [{"step_number": 1, "action": "Ingresar credenciales"}, {"step_number": 2, "action": "Enviar"}],
     "expected_result": "Se muestra el panel.", "requirement_codes": ["RF-001"]}
  ]
}"""


def all_contracts() -> dict[str, common.ContractModel]:
    """Una instancia válida de cada contrato (para las pruebas genéricas)."""
    return {
        "SourceSpan": common.SourceSpan(user_story_code="HU-001", start=0, end=5),
        "RequirementEvidence": common.RequirementEvidence(user_story_code="HU-001", text="x"),
        "LlmSettings": LLM,
        "TestData": common.TestData(),
        "SourceDocument": source_document(),
        "StorySection": p1.StorySection(kind="rules", text="regla"),
        "UnresolvedFragment": p1.UnresolvedFragment(text="x", position=1, reason="y"),
        "ValidationIssue": p1.ValidationIssue(rule_code="R", severity="info", message="m"),
        "UserStory": user_story(),
        "P1Config": p1_config(),
        "P1Input": p1_input(),
        "P1Output": p1_output(),
        "StoryClassification": classifications()[0],
        "RequirementDraft": p2.RequirementDraft(description="d", user_story_codes=("HU-001",)),
        "FunctionalRequirement": requirement(),
        "CriterionAssessment": p2.CriterionAssessment(criterion="atomicity", flagged=True, method="llm"),
        "RequirementQualityAssessment": p2_output().quality[0],
        "RequirementFinding": p2_output().findings[0],
        "P2Config": p2_config(),
        "P2Input": p2_input(),
        "P2LlmResponse": p2.P2LlmResponse.model_validate_json(P2_LLM_JSON),
        "P2Output": p2_output(),
        "EmbeddingModelInfo": embedding_model(),
        "RequirementEmbedding": p3_output().embeddings[0],
        "P3Config": p3_config(),
        "P3Input": p3_input(),
        "P3Output": p3_output(),
        "ClusterAssignment": cluster().assignments[0],
        "SemanticCluster": cluster(),
        "ClusteringAlgorithmInfo": p4_output().algorithm_info,
        "P4Config": p4_config(),
        "P4Input": p4_input(),
        "P4Output": p4_output(),
        "TestCaseOutputSpec": output_spec(),
        "ContextRequirement": context_unit().requirements[0],
        "ContextUserStory": context_unit().user_stories[0],
        "ContextUnit": context_unit(),
        "GenerationContext": generation_context(),
        "P5Config": p5_config(),
        "P5Input": p5_input(),
        "P5Output": p5_output(),
        "TestStep": sample_test_case().steps[0],
        "TestCaseDraft": p6.P6LlmResponse.model_validate_json(P6_LLM_JSON).test_cases[0],
        "P6LlmResponse": p6.P6LlmResponse.model_validate_json(P6_LLM_JSON),
        "RequirementTestCaseLink": sample_test_case().requirement_links[0],
        "TestCase": sample_test_case(),
        "P6UnitOutput": unit_output(),
        "UnitFailure": p6.UnitFailure(unit_id="U-002", error_code="LLM_INVALID_OUTPUT", message="m"),
        "P6Config": p6_config(),
        "P6Input": p6_input(),
        "P6Output": p6_output(),
    }

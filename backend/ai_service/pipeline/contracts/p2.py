"""Contratos de P2 — Clasificación de HU y extracción de RF (`pipeline_design.md`, P2)."""

from typing import Any, Literal
from uuid import UUID

from pydantic import Field, ValidationInfo, model_validator

from ai_service.pipeline.contracts.common import (
    ContractModel,
    FindingKind,
    LlmSettings,
    NonEmptyStr,
    QualityCriterion,
    RequirementCode,
    RequirementEvidence,
    SourceSpan,
    StoryClassificationCategory,
    StoryValidationStatus,
    UserStoryCode,
    ensure_unique,
)
from ai_service.pipeline.contracts.p1 import UserStory


class StoryClassification(ContractModel):
    """Clasificación funcional de una HU. La produce P2 (el LLM la devuelve tal cual).

    Se persiste en `user_stories.classification`, `classification_rationale` y
    `clarification_items` con `persist_p2_requirements` (D-27); `evidence` solo vive en memoria.
    """

    user_story_code: UserStoryCode
    category: StoryClassificationCategory
    rationale: NonEmptyStr
    clarification_items: tuple[NonEmptyStr, ...] = ()
    evidence: tuple[RequirementEvidence, ...] = ()


class _RequirementContent(ContractModel):
    """Campos que comparten el borrador del LLM y el RF registrado (1.3.4 y 1.4.3)."""

    description: NonEmptyStr
    source_text: str | None = None
    user_story_codes: tuple[UserStoryCode, ...] = Field(min_length=1)
    actor: str | None = None
    objective: str | None = None
    preconditions: tuple[NonEmptyStr, ...] = ()
    business_rules: tuple[NonEmptyStr, ...] = ()
    expected_outcomes: tuple[NonEmptyStr, ...] = ()
    acceptance_criteria: tuple[NonEmptyStr, ...] = ()
    conditions: tuple[NonEmptyStr, ...] = ()
    unspecified_information: tuple[NonEmptyStr, ...] = ()
    evidence: tuple[RequirementEvidence, ...] = ()

    @model_validator(mode="after")
    def _story_references(self) -> "_RequirementContent":
        ensure_unique(self.user_story_codes, "user_story_codes")
        unknown = {item.user_story_code for item in self.evidence} - set(self.user_story_codes)
        if unknown:
            raise ValueError(f"evidencia de HU que no originan el RF: {sorted(unknown)}")
        return self


class RequirementDraft(_RequirementContent):
    """RF tal como lo devuelve el LLM en P2, sin `id` ni `code` (los asigna el pipeline, 1.2).

    Validación opcional con contexto: `context={"user_story_codes": {...}}` exige que todas las HU
    referenciadas existan en P2Input.
    """

    @model_validator(mode="after")
    def _known_stories(self, info: ValidationInfo) -> "RequirementDraft":
        allowed = (info.context or {}).get("user_story_codes")
        if allowed is not None:
            unknown = set(self.user_story_codes) - set(allowed)
            if unknown:
                raise ValueError(f"HU inexistentes en la entrada de P2: {sorted(unknown)}")
        return self


class FunctionalRequirement(_RequirementContent):
    """RF registrado. Lo produce P2; lo consumen P3, P4, P5 y P6.

    Tablas `functional_requirements` + `user_story_requirements` (vía `persist_p2_requirements`).
    Solo `id`, `code`, `description`, `source_text` y `user_story_codes` tienen columna.
    """

    id: UUID
    code: RequirementCode
    source_span: SourceSpan | None = None
    depends_on: tuple[RequirementCode, ...] = ()  # D-17: vacío en v1

    @model_validator(mode="after")
    def _dependencies(self) -> "FunctionalRequirement":
        ensure_unique(self.depends_on, "depends_on")
        if self.code in self.depends_on:
            raise ValueError("un RF no puede depender de sí mismo")
        if self.source_span is not None and self.source_span.user_story_code not in self.user_story_codes:
            raise ValueError("source_span apunta a una HU que no origina el RF")
        return self


class CriterionAssessment(ContractModel):
    """Evaluación de un criterio de calidad de un RF. `value` es heurístico, no una probabilidad."""

    criterion: QualityCriterion
    value: float | None = None
    flagged: bool
    rationale: str | None = None
    method: Literal["llm", "rule"]


class RequirementQualityAssessment(ContractModel):
    """Evaluación de calidad de un RF. La produce P2; informativa. Sin tabla (D-06)."""

    requirement_code: RequirementCode
    criteria: tuple[CriterionAssessment, ...] = Field(min_length=1)
    needs_review: bool

    @model_validator(mode="after")
    def _review_flag(self) -> "RequirementQualityAssessment":
        ensure_unique((item.criterion for item in self.criteria), "criterios")
        if self.needs_review != any(item.flagged for item in self.criteria):
            raise ValueError("needs_review debe ser True si y solo si algún criterio está marcado")
        return self


class RequirementFinding(ContractModel):
    """Hallazgo informativo sobre RF (duplicado, descomposición…). Lo produce P2. Sin tabla (D-06)."""

    kind: FindingKind
    requirement_codes: tuple[RequirementCode, ...] = Field(min_length=1)
    detected_by: Literal["llm", "rule", "lexical", "embedding"]
    score: float | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _arity(self) -> "RequirementFinding":
        ensure_unique(self.requirement_codes, "requirement_codes")
        if self.kind == FindingKind.POTENTIAL_DUPLICATE and len(self.requirement_codes) < 2:
            raise ValueError("un posible duplicado necesita al menos 2 RF")
        return self


class P2Config(ContractModel):
    """Configuración de P2 (servidor, R8)."""

    prompt_version: NonEmptyStr
    llm: LlmSettings
    max_stories_per_call: int = Field(gt=0)
    max_retries: int = Field(ge=0)


class P2Input(ContractModel):
    """Entrada de P2: las HU procesables de P1Output (nunca las `invalid`)."""

    generation_id: UUID
    user_stories: tuple[UserStory, ...] = Field(min_length=1)
    config: P2Config

    @model_validator(mode="after")
    def _processable(self) -> "P2Input":
        ensure_unique((story.code for story in self.user_stories), "códigos de HU")
        invalid = [s.code for s in self.user_stories if s.validation_status == StoryValidationStatus.INVALID]
        if invalid:
            raise ValueError(f"las HU invalid no entran en P2: {invalid}")
        return self


def _check_classification_rules(
    classifications: tuple[StoryClassification, ...], requirements: tuple[_RequirementContent, ...]
) -> None:
    """Una clasificación por HU; los RF solo referencian HU clasificadas y nunca `no_aplicable`."""
    ensure_unique((item.user_story_code for item in classifications), "clasificaciones de HU")
    categories = {item.user_story_code: item.category for item in classifications}
    for requirement in requirements:
        for code in requirement.user_story_codes:
            if code not in categories:
                raise ValueError(f"el RF referencia la HU {code}, que no tiene clasificación")
            if categories[code] == StoryClassificationCategory.NO_APLICABLE:
                raise ValueError(f"la HU {code} es no_aplicable y no puede generar RF")


class P2LlmResponse(ContractModel):
    """Respuesta cruda del LLM en P2 (modelo intermedio). Se valida con `model_validate_json`.

    Con `context={"user_story_codes": {...}}` exige además una clasificación por cada HU enviada.
    """

    classifications: tuple[StoryClassification, ...] = Field(min_length=1)
    requirements: tuple[RequirementDraft, ...] = ()

    @model_validator(mode="after")
    def _consistent(self, info: ValidationInfo) -> "P2LlmResponse":
        _check_classification_rules(self.classifications, self.requirements)
        expected = (info.context or {}).get("user_story_codes")
        if expected is not None:
            classified = {item.user_story_code for item in self.classifications}
            if classified != set(expected):
                missing, extra = set(expected) - classified, classified - set(expected)
                raise ValueError(f"clasificaciones incompletas: faltan {sorted(missing)}, sobran {sorted(extra)}")
        return self


class P2Output(ContractModel):
    """Salida de P2. La consumen P3/P4/P5. `requirements` puede ir vacía (D-29).

    Se persiste con `persist_p2_requirements` (ver `to_rpc_payload`).
    """

    classifications: tuple[StoryClassification, ...] = Field(min_length=1)
    requirements: tuple[FunctionalRequirement, ...] = ()
    quality: tuple[RequirementQualityAssessment, ...] = ()
    findings: tuple[RequirementFinding, ...] = ()
    stories_without_requirements: tuple[UserStoryCode, ...] = ()

    @model_validator(mode="after")
    def _consistent(self) -> "P2Output":
        _check_classification_rules(self.classifications, self.requirements)
        ensure_unique((item.code for item in self.requirements), "códigos de RF")
        ensure_unique((item.id for item in self.requirements), "ids de RF")
        codes = {item.code for item in self.requirements}
        for requirement in self.requirements:
            unknown = set(requirement.depends_on) - codes
            if unknown:
                raise ValueError(f"{requirement.code} depende de RF inexistentes: {sorted(unknown)}")
        referenced = set().union(*(item.requirement_codes for item in self.findings)) | {
            item.requirement_code for item in self.quality
        }
        if referenced - codes:
            raise ValueError(f"calidad/hallazgos de RF inexistentes: {sorted(referenced - codes)}")
        ensure_unique((item.requirement_code for item in self.quality), "evaluaciones de calidad")
        covered = {code for item in self.requirements for code in item.user_story_codes}
        expected = {item.user_story_code for item in self.classifications} - covered
        ensure_unique(self.stories_without_requirements, "stories_without_requirements")
        if set(self.stories_without_requirements) != expected:
            raise ValueError(f"stories_without_requirements debe ser {sorted(expected)}")
        return self

    def to_rpc_payload(self) -> dict[str, Any]:
        """`p_payload` de `persist_p2_requirements`. `generation_id` va aparte (`p_generation_id`)."""
        return {
            "classifications": [
                {
                    "user_story_code": item.user_story_code,
                    "classification": item.category.value,
                    "classification_rationale": item.rationale,
                    "clarification_items": list(item.clarification_items),
                }
                for item in self.classifications
            ],
            "requirements": [
                item.model_dump(mode="json", include={"id", "code", "description", "source_text", "user_story_codes"})
                for item in self.requirements
            ],
        }

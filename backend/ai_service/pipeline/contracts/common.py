"""Base y tipos compartidos de los contratos P1–P6 (`pipeline_design.md`, 1.3 y 1.4).

Los contratos son estructuras de datos validadas: sin BD, sin LLM y sin lógica de etapa.
Los enums replican los `check` de `supabase/schema.sql` y los `enum` de `docs/openapi.yaml`.
"""

from collections.abc import Hashable, Iterable
from enum import StrEnum
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, model_validator


class ContractModel(BaseModel):
    """Base de todos los contratos: inmutables y sin campos desconocidos. No es `strict`."""

    model_config = ConfigDict(frozen=True, extra="forbid")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class StoryValidationStatus(StrEnum):
    """`user_stories.validation_status` (check en BD, enum en `UserStory`)."""

    VALID = "valid"
    VALID_WITH_WARNINGS = "valid_with_warnings"
    INVALID = "invalid"


class StoryClassificationCategory(StrEnum):
    """`user_stories.classification` (D-27)."""

    CANDIDATA_FUNCIONAL = "candidata_funcional"
    REQUIERE_ACLARACION = "requiere_aclaracion"
    NO_APLICABLE = "no_aplicable"


class RelationStatus(StrEnum):
    """`requirement_test_cases.relation_status`. Solo `validated` cuenta como cobertura (R7)."""

    PENDING = "pending"
    VALIDATED = "validated"
    REJECTED = "rejected"


class IssueSeverity(StrEnum):
    """Alineado con `metric_findings.severity`."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class QualityCriterion(StrEnum):
    ATOMICITY = "atomicity"
    AMBIGUITY = "ambiguity"
    TESTABILITY = "testability"
    SPECIFICITY = "specificity"
    DUPLICITY = "duplicity"
    TRACEABILITY = "traceability"
    GROUNDING = "grounding"


class FindingKind(StrEnum):
    POTENTIAL_DUPLICATE = "potential_duplicate"
    DECOMPOSITION_CANDIDATE = "decomposition_candidate"
    UNGROUNDED = "ungrounded"
    UNCOVERED_FRAGMENT = "uncovered_fragment"


class FileType(StrEnum):
    """`documents.file_type`."""

    TXT = "txt"
    PDF = "pdf"
    DOCX = "docx"


class UnitStrategy(StrEnum):
    """Estrategia de unidades de generación de P5 (D-12)."""

    BY_CLUSTER = "by_cluster"
    BY_USER_STORY = "by_user_story"


# ---------------------------------------------------------------------------
# Tipos anotados
# ---------------------------------------------------------------------------
def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("no puede estar vacío")
    return value


NonEmptyStr = Annotated[str, AfterValidator(_not_blank)]

# Códigos asignados por el pipeline, nunca por el LLM (1.2).
UserStoryCode = Annotated[str, StringConstraints(pattern=r"^HU-\d{3,}$")]
RequirementCode = Annotated[str, StringConstraints(pattern=r"^RF-\d{3,}$")]
TestCaseCode = Annotated[str, StringConstraints(pattern=r"^CP-\d{3,}$")]
UnitId = Annotated[str, StringConstraints(pattern=r"^U-\d{3,}$")]


def ensure_unique(values: Iterable[Hashable], what: str) -> None:
    """Lanza `ValueError` si `values` contiene repetidos."""
    seen: set[Hashable] = set()
    repeated: set[Hashable] = set()
    for value in values:
        if value in seen:
            repeated.add(value)
        seen.add(value)
    if repeated:
        raise ValueError(f"{what} repetidos: {sorted(map(str, repeated))}")


def code_number(code: str) -> int:
    """Parte numérica de un código `XX-001`."""
    return int(code.split("-", 1)[1])


# ---------------------------------------------------------------------------
# Tipos compartidos
# ---------------------------------------------------------------------------
class SourceSpan(ContractModel):
    """Posición `[start, end)` de un fragmento dentro de una HU. Solo en memoria."""

    user_story_code: UserStoryCode
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def _ordered(self) -> "SourceSpan":
        if self.end < self.start:
            raise ValueError("end debe ser >= start")
        return self


class RequirementEvidence(ContractModel):
    """Fragmento de una HU que respalda un RF, un atributo del RF o una clasificación (P2)."""

    user_story_code: UserStoryCode
    text: NonEmptyStr
    attribute: str | None = None
    source_span: SourceSpan | None = None


class LlmSettings(ContractModel):
    """Proveedor, modelo y parámetros del LLM de P2/P6. Sale de la configuración del servidor (R8)."""

    provider: NonEmptyStr
    model: NonEmptyStr
    # dict: `frozen` no lo hace inmutable por dentro.
    parameters: dict[str, Any] = Field(default_factory=dict)


class TestData(ContractModel):
    """`test_cases.test_data` (D-26, esquema `TestData` del openapi). Todas las claves son opcionales.

    Solo `inputs` y `notes`: `preconditions` y `expected_result` son campos de primer
    nivel del caso (`TestCaseDraft`, `TestCase`).

    Lo produce P6 (vía `TestCaseDraft`) y se persiste con `persist_p6_unit`.
    """

    __test__ = False  # no es una clase de pytest

    # dict: `frozen` no lo hace inmutable por dentro.
    inputs: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None

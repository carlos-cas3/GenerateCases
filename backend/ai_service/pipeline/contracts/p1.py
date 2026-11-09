"""Contratos de P1 — Procesamiento, segmentación y estructuración de HU (`pipeline_design.md`, P1)."""

import re
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator, model_validator

from ai_service.pipeline.contracts.common import (
    ContractModel,
    FileType,
    IssueSeverity,
    NonEmptyStr,
    SourceSpan,
    StoryValidationStatus,
    UserStoryCode,
    ensure_unique,
)


class SourceDocument(ContractModel):
    """Archivo crudo leído del Storage (D-01, `issue_resolver_correccionP1.md`).

    Objeto de entrada interno de P1, no un contrato compartido entre etapas: P1 lee
    los bytes del Storage, construye este objeto y extrae el texto con
    `DocumentTextExtractor`. El texto extraído vive en memoria dentro de P1; no tiene
    campo aquí ni en `PipelineContext`. Si sale vacío, P1 falla con `EMPTY_DOCUMENT`.
    """

    # Los bytes de un PDF/DOCX no son UTF-8: en JSON viajan en base64.
    model_config = ConfigDict(ser_json_bytes="base64", val_json_bytes="base64")

    document_id: UUID
    filename: NonEmptyStr
    file_type: FileType
    data: bytes  # bytes crudos del archivo


class StorySection(ContractModel):
    """Sección reconocida de una HU (criterios, reglas, restricciones…). Texto literal; solo en memoria."""

    kind: NonEmptyStr
    text: NonEmptyStr
    source_span: SourceSpan | None = None


class UnresolvedFragment(ContractModel):
    """Fragmento que P1 no pudo asociar a una HU. Se conserva en P1Output; no se persiste (D-22)."""

    text: NonEmptyStr
    position: int = Field(ge=1)
    reason: NonEmptyStr


class ValidationIssue(ContractModel):
    """Incidencia de segmentación/normalización de una HU. Solo en memoria (D-22)."""

    rule_code: NonEmptyStr
    severity: IssueSeverity
    message: NonEmptyStr
    field: str | None = None


class UserStory(ContractModel):
    """HU estructurada. La produce P1; la consumen P2 y P5. Tabla `user_stories`.

    `objective` → columna `action` y `benefit` → columna `goal` (D-02).
    `normalized_text`, `issues` y `content_sections` no tienen columna.
    """

    id: UUID
    code: UserStoryCode
    original_text: str = Field(min_length=1)
    role: str | None = None
    objective: str | None = None
    benefit: str | None = None
    normalized_text: str | None = None
    validation_status: StoryValidationStatus
    issues: tuple[ValidationIssue, ...] = ()
    position: int = Field(ge=1)
    content_sections: tuple[StorySection, ...] = ()

    @model_validator(mode="after")
    def _status_matches_issues(self) -> "UserStory":
        severities = {issue.severity for issue in self.issues}
        if self.validation_status == StoryValidationStatus.VALID_WITH_WARNINGS and not self.issues:
            raise ValueError("valid_with_warnings exige al menos una incidencia")
        if self.validation_status == StoryValidationStatus.VALID and IssueSeverity.ERROR in severities:
            raise ValueError("una HU valid no puede tener incidencias de severidad error")
        for section in self.content_sections:
            if section.source_span is not None and section.source_span.user_story_code != self.code:
                raise ValueError(f"la sección {section.kind!r} apunta a otra HU")
        return self


class P1Config(ContractModel):
    """Configuración de P1 (sale de la configuración del servidor, R8)."""

    rules_version: NonEmptyStr
    language: str = "es"
    story_delimiter_pattern: NonEmptyStr
    max_story_chars: int = Field(gt=0)

    @field_validator("story_delimiter_pattern")
    @classmethod
    def _compiles(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"expresión regular inválida: {exc}") from exc
        return value


class P1Input(ContractModel):
    """Entrada de P1. La construye P1 a partir del documento de la generación (`context.document_id`)."""

    generation_id: UUID
    document: SourceDocument
    config: P1Config


class P1Output(ContractModel):
    """Salida de P1. La consumen P2 (HU no `invalid`) y P5. Se persiste en `user_stories`.

    P1 falla con `NO_STORIES_FOUND` si no hay ninguna HU procesable, así que el contrato la exige.
    """

    user_stories: tuple[UserStory, ...] = Field(min_length=1)
    unresolved_fragments: tuple[UnresolvedFragment, ...] = ()
    valid_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    invalid_count: int = Field(ge=0)

    @model_validator(mode="after")
    def _consistent(self) -> "P1Output":
        ensure_unique((story.code for story in self.user_stories), "códigos de HU")
        ensure_unique((story.id for story in self.user_stories), "ids de HU")
        ensure_unique((story.position for story in self.user_stories), "posiciones de HU")
        counts = {status: 0 for status in StoryValidationStatus}
        for story in self.user_stories:
            counts[story.validation_status] += 1
        expected = (
            counts[StoryValidationStatus.VALID],
            counts[StoryValidationStatus.VALID_WITH_WARNINGS],
            counts[StoryValidationStatus.INVALID],
        )
        if (self.valid_count, self.warning_count, self.invalid_count) != expected:
            raise ValueError(f"los conteos no coinciden con las HU: se esperaba {expected}")
        if counts[StoryValidationStatus.INVALID] == len(self.user_stories):
            raise ValueError("debe haber al menos una HU procesable (no invalid)")
        return self

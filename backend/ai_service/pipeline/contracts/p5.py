"""Contratos de P5 — Construcción del contexto estructurado (`pipeline_design.md`, P5).

El contexto es derivado y no se persiste (D-12).
"""

from typing import Any
from uuid import UUID

from pydantic import Field, model_validator

from ai_service.pipeline.contracts.common import (
    ContractModel,
    NonEmptyStr,
    RequirementCode,
    StoryValidationStatus,
    UnitId,
    UnitStrategy,
    UserStoryCode,
    ensure_unique,
)
from ai_service.pipeline.contracts.p1 import StorySection, UserStory
from ai_service.pipeline.contracts.p2 import FunctionalRequirement
from ai_service.pipeline.contracts.p4 import P4Output


class TestCaseOutputSpec(ContractModel):
    """Estructura que el LLM de P6 debe devolver (1.4.2). Común a todas las unidades.

    `json_schema` es el esquema de `P6LlmResponse` (ver `p6.default_output_spec`).
    """

    __test__ = False  # no es una clase de pytest

    version: NonEmptyStr
    # dict: `frozen` no lo hace inmutable por dentro.
    json_schema: dict[str, Any]


class ContextRequirement(ContractModel):
    """RF dentro de una unidad: solo código y descripción (sin repetir el resto del RF)."""

    code: RequirementCode
    description: NonEmptyStr


class ContextUserStory(ContractModel):
    """HU de origen de los RF de una unidad, con el contenido pertinente para generar casos."""

    code: UserStoryCode
    original_text: str = Field(min_length=1)
    role: str | None = None
    objective: str | None = None
    benefit: str | None = None
    content_sections: tuple[StorySection, ...] = ()


class ContextUnit(ContractModel):
    """Unidad de generación: una solicitud independiente al LLM en P6.

    - `requirements`: RF **objetivo**; los únicos que los casos pueden enlazar.
    - `context_requirements`: RF objetivo de otra unidad que aquí solo dan contexto (D-31).
    - `prerequisites`: RF prerrequisito, solo contexto (D-17; vacío en v1).
    """

    unit_id: UnitId
    label: NonEmptyStr
    cluster_label: int | None = None
    requirements: tuple[ContextRequirement, ...] = Field(min_length=1)
    context_requirements: tuple[ContextRequirement, ...] = ()
    user_stories: tuple[ContextUserStory, ...] = Field(min_length=1)
    # dict: `frozen` no lo hace inmutable por dentro.
    requirement_to_stories: dict[RequirementCode, tuple[UserStoryCode, ...]]
    prerequisites: tuple[ContextRequirement, ...] = ()
    token_estimate: int = Field(ge=0)
    exceeds_limit: bool = False

    def target_codes(self) -> set[str]:
        """Códigos de los RF objetivo de la unidad."""
        return {item.code for item in self.requirements}

    @model_validator(mode="after")
    def _references(self) -> "ContextUnit":
        targets = [item.code for item in self.requirements]
        context = [item.code for item in self.context_requirements]
        prerequisites = [item.code for item in self.prerequisites]
        ensure_unique(targets + context + prerequisites, f"RF de la unidad {self.unit_id}")
        story_codes = [item.code for item in self.user_stories]
        ensure_unique(story_codes, f"HU de la unidad {self.unit_id}")

        missing = set(targets + context) - set(self.requirement_to_stories)
        if missing:
            raise ValueError(f"RF sin relación con HU en requirement_to_stories: {sorted(missing)}")
        foreign = set(self.requirement_to_stories) - set(targets + context + prerequisites)
        if foreign:
            raise ValueError(f"requirement_to_stories referencia RF ajenos a la unidad: {sorted(foreign)}")
        referenced: set[str] = set()
        for code, stories in self.requirement_to_stories.items():
            if not stories:
                raise ValueError(f"{code} no tiene HU de origen")
            ensure_unique(stories, f"HU de {code}")
            referenced.update(stories)
        if referenced - set(story_codes):
            raise ValueError(f"HU referenciadas que no están en la unidad: {sorted(referenced - set(story_codes))}")
        if set(story_codes) - referenced:
            raise ValueError(f"HU sin RF en la unidad: {sorted(set(story_codes) - referenced)}")
        return self


class GenerationContext(ContractModel):
    """Contexto de generación. Lo produce P5; lo consume P6. No se persiste (D-12)."""

    generation_id: UUID
    output_spec: TestCaseOutputSpec
    instructions_version: NonEmptyStr
    strategy: UnitStrategy
    units: tuple[ContextUnit, ...] = Field(min_length=1)  # D-36 pendiente

    @model_validator(mode="after")
    def _single_target(self) -> "GenerationContext":
        ensure_unique((unit.unit_id for unit in self.units), "unit_id")
        ensure_unique((code for unit in self.units for code in unit.target_codes()), "RF objetivo entre unidades")
        if self.strategy == UnitStrategy.BY_CLUSTER and any(u.cluster_label is None for u in self.units):
            raise ValueError("con by_cluster toda unidad debe tener cluster_label")
        if self.strategy == UnitStrategy.BY_USER_STORY and any(u.cluster_label is not None for u in self.units):
            raise ValueError("con by_user_story ninguna unidad tiene cluster_label")
        return self


class P5Config(ContractModel):
    """Configuración de P5 (servidor, R8)."""

    max_tokens_per_unit: int = Field(gt=0)
    strategy: UnitStrategy
    instructions_version: NonEmptyStr
    include_prerequisites: bool = False


class P5Input(ContractModel):
    """Entrada de P5. `clustering` es `None` cuando P3/P4 se omitieron (R2)."""

    generation_id: UUID
    user_stories: tuple[UserStory, ...] = Field(min_length=1)
    requirements: tuple[FunctionalRequirement, ...] = Field(min_length=1)
    clustering: P4Output | None = None
    output_spec: TestCaseOutputSpec
    config: P5Config

    @model_validator(mode="after")
    def _consistent(self) -> "P5Input":
        story_codes = [story.code for story in self.user_stories]
        ensure_unique(story_codes, "códigos de HU")
        requirement_codes = {item.code for item in self.requirements}
        ensure_unique((item.code for item in self.requirements), "códigos de RF")
        if any(story.validation_status == StoryValidationStatus.INVALID for story in self.user_stories):
            raise ValueError("las HU invalid no entran en P5")
        origin = {code for item in self.requirements for code in item.user_story_codes}
        if origin - set(story_codes):
            raise ValueError(f"RF con HU de origen ausentes: {sorted(origin - set(story_codes))}")
        if set(story_codes) - origin:
            raise ValueError(f"solo entran las HU que originaron RF; sobran {sorted(set(story_codes) - origin)}")
        clustered = self.clustering is not None
        if clustered != (self.config.strategy == UnitStrategy.BY_CLUSTER):
            raise ValueError("strategy by_cluster exige clustering y by_user_story lo excluye")
        if self.clustering is not None:
            known = self.clustering.assigned_requirement_codes() | set(self.clustering.unassigned_requirement_codes)
            if known != requirement_codes:
                raise ValueError("los RF del clustering no coinciden con los RF de entrada")
        return self


class P5Output(ContractModel):
    """Salida de P5. La consume P6."""

    context: GenerationContext

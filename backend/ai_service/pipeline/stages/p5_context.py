"""P5 — Construcción del contexto estructurado (Fase 6).

1. Lee las HU (`context.p1_output`), los RF (`context.p2_output`) y los clusters
   (`context.p4_output`, `None` si P3/P4 se omitieron).
2. La estrategia sale de `p4_output` y nunca de `clustering_enabled` (R-ST-4, D-F6-2):
   `None` → `by_user_story`; con valor → `by_cluster`.
3. Valida la entrada con `P5Input` (R-CP-3) y agrupa los RF en unidades de generación:
   - `by_cluster`: una unidad por cluster; los RF de otros clusters que comparten HU de origen
     van como `context_requirements` (D-31, D-F6-4). Los RF sin cluster no forman unidad
     (D-32 / D-36) y se avisan con `UNASSIGNED_REQUIREMENTS`.
   - `by_user_story`: una unidad por HU con RF; cada RF va a la HU de menor posición entre sus
     `user_story_codes` (D-F6-9), sin duplicar RF entre unidades.
4. Estima los tokens de cada unidad (caracteres / 4) y marca `exceeds_limit` con aviso
   `UNIT_EXCEEDS_TOKEN_LIMIT`; no parte ni descarta unidades (D-F6-6).
5. Deja el `GenerationContext` en `context.p5_output`. No persiste nada (D-12, D-F6-1).
"""

import logging
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import ClassVar

from pydantic import ValidationError

from ai_service.pipeline.context import PipelineContext
from ai_service.pipeline.contracts.common import StoryValidationStatus, UnitStrategy, code_number
from ai_service.pipeline.contracts.p1 import UserStory
from ai_service.pipeline.contracts.p2 import FunctionalRequirement
from ai_service.pipeline.contracts.p4 import P4Output
from ai_service.pipeline.contracts.p5 import (
    ContextRequirement,
    ContextUnit,
    ContextUserStory,
    GenerationContext,
    P5Config,
    P5Input,
    P5Output,
)
from ai_service.pipeline.contracts.p6 import default_output_spec
from ai_service.pipeline.stages.base import StageBase, StageError, StageResult, StubStage
from ai_service.schemas.generations import StageKey, StageWarning

logger = logging.getLogger(__name__)

ERROR_CODE = "CONTEXT_BUILD_FAILED"
CHARS_PER_TOKEN = 4  # heurística para español/inglés (D-F6-6): señal de alerta, no conteo exacto


class ContextStage(StageBase):
    """P5 real. Recibe solo `P5Config` por constructor: no usa clientes externos (R-DI-2).

    `config.strategy` es un valor provisional del wiring: la etapa lo sustituye en cada
    ejecución por la estrategia derivada de `p4_output` (`model_copy`).
    """

    key: ClassVar[StageKey] = StageKey.P5

    def __init__(self, *, config: P5Config) -> None:
        self._config = config

    async def run(self, context: PipelineContext) -> StageResult:
        if context.p1_output is None or context.p2_output is None:
            raise RuntimeError("P5 requiere p1_output y p2_output: P1 o P2 no se ejecutaron")

        clustering = context.p4_output
        strategy = UnitStrategy.BY_USER_STORY if clustering is None else UnitStrategy.BY_CLUSTER
        config = self._config.model_copy(update={"strategy": strategy})

        requirements = context.p2_output.requirements
        origin = {code for item in requirements for code in item.user_story_codes}
        # Solo HU no invalid que originaron algún RF (P5Input rechaza el resto).
        stories = tuple(
            story
            for story in context.p1_output.user_stories
            if story.validation_status != StoryValidationStatus.INVALID and story.code in origin
        )
        try:
            p5_input = P5Input(
                generation_id=context.generation_id,
                user_stories=stories,
                requirements=requirements,
                clustering=clustering,
                output_spec=default_output_spec(config.instructions_version),
                config=config,
            )
        except ValidationError as exc:
            raise StageError(
                ERROR_CODE, "Las HU, los RF o los clusters no son coherentes entre sí.",
                details={"errors": exc.error_count()},
            ) from exc

        if p5_input.clustering is not None:
            units = self._build_by_cluster(p5_input, p5_input.clustering)
        else:
            units = self._build_by_user_story(p5_input)

        try:
            generation_context = GenerationContext(
                generation_id=p5_input.generation_id,
                output_spec=p5_input.output_spec,
                instructions_version=config.instructions_version,
                strategy=strategy,
                units=units,
            )
        except ValidationError as exc:
            raise StageError(
                ERROR_CODE, "El contexto de generación no es consistente.", details={"errors": exc.error_count()}
            ) from exc

        context.p5_output = P5Output(context=generation_context)

        unassigned = p5_input.clustering.unassigned_requirement_codes if p5_input.clustering else ()
        covered = sum(len(unit.requirements) for unit in units)
        logger.info(
            "P5 completada generation_id=%s estrategia=%s unidades=%s rf_cubiertos=%s sin_cluster=%s",
            context.generation_id, strategy.value, len(units), covered, len(unassigned),
        )
        runtime_info: dict[str, object] = {
            "strategy": strategy.value,
            "instructions_version": config.instructions_version,
            "units": len(units),
            "requirements_covered": covered,
            "max_tokens_per_unit": config.max_tokens_per_unit,
            "units_exceeding_limit": [unit.unit_id for unit in units if unit.exceeds_limit],
        }
        if strategy == UnitStrategy.BY_CLUSTER:
            runtime_info["unassigned_requirements"] = len(unassigned)
        return StageResult(warnings=_warnings(units, unassigned, config.max_tokens_per_unit), runtime_info=runtime_info)

    def _build_by_cluster(self, p5_input: P5Input, clustering: P4Output) -> tuple[ContextUnit, ...]:
        """Una unidad por cluster, en orden de `label` (D-F6-7). Membresía única asumida (R6)."""
        requirements = {item.code: item for item in p5_input.requirements}
        stories = {story.code: story for story in p5_input.user_stories}
        units: list[ContextUnit] = []
        for number, cluster in enumerate(sorted(clustering.clusters, key=lambda c: c.label), start=1):
            own = {item.requirement_code for item in cluster.assignments}
            targets = _sorted_by_code(requirements[code] for code in own)
            origin = {code for item in targets for code in item.user_story_codes}
            # D-31 / D-F6-4: RF objetivo de otros clusters que comparten alguna HU de origen.
            context_items = _sorted_by_code(
                requirements[code]
                for other in clustering.clusters
                if other.label != cluster.label
                for code in (item.requirement_code for item in other.assignments)
                if code not in own and origin.intersection(requirements[code].user_story_codes)
            )
            units.append(
                _unit(
                    number, label=cluster.name, cluster_label=cluster.label, targets=targets,
                    context_items=context_items, stories=stories, max_tokens=p5_input.config.max_tokens_per_unit,
                )
            )
        return tuple(units)

    def _build_by_user_story(self, p5_input: P5Input) -> tuple[ContextUnit, ...]:
        """Una unidad por HU con RF, en orden de posición de la HU (D-F6-7, D-F6-9)."""
        stories = {story.code: story for story in p5_input.user_stories}
        groups: dict[str, list[FunctionalRequirement]] = defaultdict(list)
        for item in p5_input.requirements:
            owner = min(item.user_story_codes, key=lambda code: stories[code].position)
            groups[owner].append(item)

        units: list[ContextUnit] = []
        owners = sorted(groups, key=lambda code: stories[code].position)
        for number, owner in enumerate(owners, start=1):
            units.append(
                _unit(
                    number, label=owner, cluster_label=None, targets=_sorted_by_code(groups[owner]),
                    context_items=(), stories=stories, max_tokens=p5_input.config.max_tokens_per_unit,
                )
            )
        return tuple(units)


def _sorted_by_code(items: Iterable[FunctionalRequirement]) -> tuple[FunctionalRequirement, ...]:
    unique = {item.code: item for item in items}
    return tuple(sorted(unique.values(), key=lambda item: code_number(item.code)))


def _unit(
    number: int,
    *,
    label: str,
    cluster_label: int | None,
    targets: Sequence[FunctionalRequirement],
    context_items: Sequence[FunctionalRequirement],
    stories: Mapping[str, UserStory],
    max_tokens: int,
) -> ContextUnit:
    every = (*targets, *context_items)
    # Dict recién construido: `frozen` no protege su interior (advertencia heredada 4).
    requirement_to_stories = {item.code: tuple(item.user_story_codes) for item in every}
    story_codes = {code for item in every for code in item.user_story_codes}
    unit_stories = tuple(
        _context_story(story) for story in sorted((stories[c] for c in story_codes), key=lambda s: s.position)
    )
    requirements = tuple(ContextRequirement(code=item.code, description=item.description) for item in targets)
    context_requirements = tuple(
        ContextRequirement(code=item.code, description=item.description) for item in context_items
    )
    token_estimate = _token_estimate((*requirements, *context_requirements), unit_stories)
    return ContextUnit(
        unit_id=f"U-{number:03d}",
        label=label,
        cluster_label=cluster_label,
        requirements=requirements,
        context_requirements=context_requirements,
        user_stories=unit_stories,
        requirement_to_stories=requirement_to_stories,
        prerequisites=(),  # D-17 / D-F6-5: vacío en v1
        token_estimate=token_estimate,
        exceeds_limit=token_estimate > max_tokens,
    )


def _context_story(story: UserStory) -> ContextUserStory:
    return ContextUserStory(
        code=story.code,
        original_text=story.original_text,
        role=story.role,
        objective=story.objective,
        benefit=story.benefit,
        content_sections=story.content_sections,
    )


def _token_estimate(requirements: Iterable[ContextRequirement], stories: Iterable[ContextUserStory]) -> int:
    """Caracteres de las descripciones de RF y del texto original de las HU, entre 4 (D-F6-6)."""
    chars = sum(len(item.description) for item in requirements) + sum(len(story.original_text) for story in stories)
    return chars // CHARS_PER_TOKEN


def _warnings(
    units: Sequence[ContextUnit], unassigned: Sequence[str], max_tokens: int
) -> tuple[StageWarning, ...]:
    warnings: list[StageWarning] = []
    if unassigned:
        # D-32 / D-36: no forman unidad, P6 no los verá.
        warnings.append(
            StageWarning(
                code="UNASSIGNED_REQUIREMENTS",
                message=f"{len(unassigned)} RF sin cluster no generarán casos de prueba.",
                details={"requirement_codes": list(unassigned)},
            )
        )
    for unit in units:
        if unit.exceeds_limit:
            warnings.append(
                StageWarning(
                    code="UNIT_EXCEEDS_TOKEN_LIMIT",
                    message=f"La unidad {unit.unit_id} supera el límite estimado de tokens.",
                    details={
                        "unit_id": unit.unit_id,
                        "token_estimate": unit.token_estimate,
                        "max_tokens_per_unit": max_tokens,
                    },
                )
            )
    return tuple(warnings)


class ContextStubStage(StubStage):
    """P5 simulada (Fase 1). Se usa con `PIPELINE_STAGES=stub` y en tests del orquestador."""

    key: ClassVar[StageKey] = StageKey.P5

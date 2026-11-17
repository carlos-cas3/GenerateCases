"""P6 — Generación de casos de prueba funcionales (Fase 7).

1. Lee `context.p5_output` (el `GenerationContext` de P5; no se persiste, D-12) y lo valida con
   `P6Input` (R-CP-3).
2. Resuelve la variante de prompt por `GenerationContext.strategy` (D-38): `contexto` con
   `by_cluster`, `contexto_sin_clustering` con `by_user_story`.
3. Una llamada al LLM por unidad (D-F7-3). El `.md` del prompt va tal cual como `system`; el
   mensaje de usuario se arma aquí con el tope de casos, los RF objetivo, los RF de contexto (si
   hay), las HU de origen y el JSON Schema de salida (§Construcción del mensaje).
4. Antes de validar se filtran de `requirement_codes` los RF que no son objetivo de la unidad
   (un caso que se queda sin RF se descarta; aviso `REQUIREMENT_CODES_FILTERED`). Si el LLM
   devuelve más casos del tope `min(multiplier × RF, absolute)` se truncan antes de validar
   (aviso `CASES_TRUNCATED`, D-F7-4). La respuesta se valida con `P6LlmResponse` y
   `target_codes`: un caso solo puede enlazar RF objetivo de su unidad.
5. Reintenta la unidad hasta `P6Config.max_retries` veces si la salida es inválida o el proveedor
   falla transitoriamente (D-F7-5); `LLM_CONTEXT_LENGTH` no se reintenta. Una unidad que agota
   los reintentos queda en `failed_units` y P6 sigue con la siguiente (D-F7-1).
6. Con todas las unidades procesadas evalúa el umbral (D-F7-2): si
   `fallidas / total > failure_threshold` la etapa falla con `GENERATION_THRESHOLD_EXCEEDED` y no
   persiste nada. Si no, persiste al final cada unidad exitosa con `persist_p6_unit` (D-F7-7),
   numerando `CP-xxx` globalmente al persistir (D-F7-6): una unidad cuya persistencia falla pasa a
   `failed_units` sin consumir códigos, y el umbral se vuelve a evaluar.
7. Deja el `P6Output` en `context.p6_output` (lo lee `PipelineRunService` para el summary).
"""

import asyncio
import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar
from uuid import uuid4

from pydantic import ValidationError

from ai_service.clients.llm import LlmClient, LlmRequest, LlmResponse
from ai_service.core.errors import LlmContextLengthError, LlmError, PersistenceError
from ai_service.pipeline.context import PipelineContext
from ai_service.pipeline.contracts.common import UnitStrategy
from ai_service.pipeline.contracts.p5 import ContextRequirement, ContextUnit, GenerationContext
from ai_service.pipeline.contracts.p6 import (
    P6Config,
    P6Input,
    P6LlmResponse,
    P6Output,
    P6UnitOutput,
    RequirementTestCaseLink,
    TestCase,
    UnitFailure,
)
from ai_service.pipeline.prompts.p6 import ResolvedP6Prompt
from ai_service.pipeline.stages.base import StageBase, StageError, StageResult, StubStage
from ai_service.pipeline.stages.llm_output import (
    RAW_LOG_LIMIT,
    add_optional,
    drop_blank_list_items,
    filter_requirement_codes_with_stats,
    strip_code_fence,
)
from ai_service.repositories.pipeline_results import PipelineResultsRepository
from ai_service.schemas.generations import LlmRun, StageKey, StageWarning

logger = logging.getLogger(__name__)

PromptResolver = Callable[[str, UnitStrategy], ResolvedP6Prompt]

THRESHOLD_EXCEEDED_CODE = "GENERATION_THRESHOLD_EXCEEDED"


@dataclass(slots=True)
class _UnitResult:
    """Resultado de procesar una unidad con el LLM: `response` o `failure`, nunca ambos."""

    unit: ContextUnit
    max_cases: int
    run: LlmRun | None = None
    response: P6LlmResponse | None = None
    failure: UnitFailure | None = None
    errors: list[str] = field(default_factory=list)
    truncated_from: int | None = None
    filtered_codes: list[str] = field(default_factory=list)
    dropped_cases: int = 0

    @property
    def retries(self) -> int:
        return self.run.attempts - 1 if self.run is not None else 0


class GenerationStage(StageBase):
    """P6 real. Recibe `LlmClient`, el resolvedor de prompts, el repositorio y `P6Config` (R-DI-2)."""

    key: ClassVar[StageKey] = StageKey.P6

    def __init__(
        self,
        *,
        llm_client: LlmClient,
        prompt_resolver: PromptResolver,
        results: PipelineResultsRepository,
        config: P6Config,
        retry_delay_seconds: float = 1.0,
    ) -> None:
        self._llm = llm_client
        self._resolve_prompt = prompt_resolver
        self._results = results
        self._config = config
        self._retry_delay_seconds = retry_delay_seconds

    async def run(self, context: PipelineContext) -> StageResult:
        if context.p5_output is None:
            raise RuntimeError("P6 requiere p5_output: P5 no se ejecutó")
        p6_input = P6Input(generation_id=context.generation_id, context=context.p5_output.context, config=self._config)
        generation_context = p6_input.context
        prompt = self._resolve_prompt(self._config.prompt_version, generation_context.strategy)
        units = generation_context.units

        results = [await self._run_unit(context, prompt, generation_context, unit) for unit in units]

        failures = [result.failure for result in results if result.failure is not None]
        self._check_threshold(len(failures), len(units))
        outputs, persistence_failures = await self._persist(context, [r for r in results if r.failure is None])
        if persistence_failures:
            failures.extend(persistence_failures)
            self._check_threshold(len(failures), len(units))

        order = {unit.unit_id: index for index, unit in enumerate(units)}
        failures.sort(key=lambda item: order[item.unit_id])
        output = P6Output(
            units=tuple(outputs),
            uncovered_requirement_codes=_uncovered(units, outputs),
            failed_units=tuple(failures),
        )
        context.p6_output = output
        logger.info(
            "P6 completada generation_id=%s estrategia=%s unidades=%s fallidas=%s casos=%s",
            context.generation_id, generation_context.strategy.value, len(units), len(failures), len(output.test_cases),
        )
        return StageResult(
            warnings=self._warnings(output, results),
            llm_runs=tuple(result.run for result in results if result.run is not None),
            runtime_info={
                "strategy": generation_context.strategy.value,
                "prompt_version": prompt.prompt_version,
                "provider": self._config.llm.provider,
                "model": self._config.llm.model,
                "max_retries": self._config.max_retries,
                "failure_threshold": self._config.failure_threshold,
                "max_cases_multiplier": self._config.max_cases_multiplier,
                "max_cases_absolute": self._config.max_cases_absolute,
                "units": len(units),
                "units_succeeded": len(output.units),
                "units_failed": len(output.failed_units),
                "test_cases_count": len(output.test_cases),
                "retries_used": sum(result.retries for result in results),
                "uncovered_requirements": len(output.uncovered_requirement_codes),
            },
        )

    # ------------------------------------------------------------- unidades
    async def _run_unit(
        self, context: PipelineContext, prompt: ResolvedP6Prompt, generation_context: GenerationContext, unit: ContextUnit
    ) -> _UnitResult:
        max_cases = self._config.max_cases_for(len(unit.requirements))
        result = _UnitResult(unit=unit, max_cases=max_cases)
        request = self._build_request(prompt, generation_context, unit, max_cases)
        targets = unit.target_codes()
        attempts = 0
        input_tokens: int | None = None
        output_tokens: int | None = None
        latency_ms: int | None = None
        max_attempts = self._config.max_retries + 1

        def run() -> LlmRun:
            return LlmRun(
                provider=self._config.llm.provider,
                model=self._config.llm.model,
                prompt_version=prompt.prompt_version,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                attempts=attempts,
                latency_ms=latency_ms,
                unit_id=unit.unit_id,
            )

        def fail(code: str, message: str) -> _UnitResult:
            logger.warning(
                "P6 unidad fallida generation_id=%s unit_id=%s attempts=%s code=%s",
                context.generation_id, unit.unit_id, attempts, code,
            )
            result.run = run()
            result.failure = UnitFailure(unit_id=unit.unit_id, error_code=code, message=message)
            return result

        while attempts < max_attempts:
            attempts += 1
            try:
                response = await self._llm.complete(request)
            except LlmContextLengthError as exc:
                result.errors.append(exc.code)
                return fail(exc.code, f"La unidad {unit.unit_id} excede el contexto del modelo de lenguaje.")
            except LlmError as exc:
                result.errors.append(exc.code)
                logger.warning(
                    "P6 fallo del LLM generation_id=%s unit_id=%s attempt=%s code=%s",
                    context.generation_id, unit.unit_id, attempts, exc.code,
                )
                if attempts >= max_attempts:
                    code = "LLM_INVALID_OUTPUT" if exc.code == "LLM_INVALID_OUTPUT" else "LLM_UNAVAILABLE"
                    return fail(code, f"El modelo de lenguaje falló en la unidad {unit.unit_id} tras {attempts} intento(s).")
                await asyncio.sleep(self._retry_delay_seconds * attempts)
                continue

            input_tokens = add_optional(input_tokens, response.input_tokens)
            output_tokens = add_optional(output_tokens, response.output_tokens)
            latency_ms = add_optional(latency_ms, response.latency_ms)
            parsed = self._parse(context, response, unit, targets, max_cases, attempts)
            if parsed is not None:
                result.run = run()
                result.response, result.truncated_from, result.filtered_codes, result.dropped_cases = parsed
                return result
            result.errors.append("LLM_INVALID_OUTPUT")

        return fail(
            "LLM_INVALID_OUTPUT",
            f"La respuesta del modelo de lenguaje no es válida en la unidad {unit.unit_id} tras {attempts} intento(s).",
        )

    def _parse(
        self,
        context: PipelineContext,
        response: LlmResponse,
        unit: ContextUnit,
        targets: set[str],
        max_cases: int,
        attempt: int,
    ) -> tuple[P6LlmResponse, int | None, list[str], int] | None:
        """Valida la respuesta; `None` si es inválida.

        Antes de validar se filtran los RF que no son objetivo de la unidad (issue P6 de saneo de
        `requirement_codes`) y luego se truncan los casos que exceden el tope (D-F7-4). Devuelve la
        respuesta, el nº de casos recibidos si se truncó, los códigos filtrados y los casos
        descartados por quedarse sin RF.
        """
        raw, filtered, dropped = filter_requirement_codes_with_stats(
            drop_blank_list_items(strip_code_fence(response.text)), targets
        )
        if filtered:
            logger.info(
                "P6 RF no objetivo filtrados generation_id=%s unit_id=%s attempt=%s codigos=%s casos_descartados=%s",
                context.generation_id, unit.unit_id, attempt, sorted(set(filtered)), dropped,
            )
        truncated_from: int | None = None
        try:
            data = json.loads(raw)
        except ValueError:
            data = None
        if isinstance(data, dict) and isinstance(data.get("test_cases"), list) and len(data["test_cases"]) > max_cases:
            truncated_from = len(data["test_cases"])
            data["test_cases"] = data["test_cases"][:max_cases]
            raw = json.dumps(data, ensure_ascii=False)
        try:
            validated = P6LlmResponse.model_validate_json(raw, context={"target_codes": targets})
        except ValidationError as exc:
            logger.debug(
                "P6 unidad inválida generation_id=%s unit_id=%s attempt=%s raw=%s err=%s",
                context.generation_id, unit.unit_id, attempt, response.text[:RAW_LOG_LIMIT], exc,
            )
            logger.warning(
                "P6 unidad inválida generation_id=%s unit_id=%s attempt=%s errores=%s",
                context.generation_id, unit.unit_id, attempt, exc.error_count(),
            )
            return None
        return validated, truncated_from, filtered, dropped

    def _build_request(
        self, prompt: ResolvedP6Prompt, generation_context: GenerationContext, unit: ContextUnit, max_cases: int
    ) -> LlmRequest:
        parameters = dict(self._config.llm.parameters)
        return LlmRequest(
            prompt=build_user_message(generation_context, unit, max_cases),
            model=self._config.llm.model,
            system=prompt.text,
            max_tokens=parameters.pop("max_tokens", None),
            temperature=parameters.pop("temperature", None),
            extra=parameters,
        )

    # --------------------------------------------------- umbral y persistencia
    def _check_threshold(self, failed: int, total: int) -> None:
        """D-F7-2: `fallidas / total > failure_threshold` → la generación queda `failed`."""
        if total and failed / total > self._config.failure_threshold:
            raise StageError(
                THRESHOLD_EXCEEDED_CODE,
                f"{failed} de {total} unidad(es) fallaron; el umbral admitido es "
                f"{self._config.failure_threshold:.0%}.",
                retryable=True,
                details={"failed_units": failed, "total_units": total, "threshold": self._config.failure_threshold},
            )

    async def _persist(
        self, context: PipelineContext, results: Sequence[_UnitResult]
    ) -> tuple[list[P6UnitOutput], list[UnitFailure]]:
        """Persiste al final, unidad a unidad (D-F7-7). El contador de CP solo avanza al persistir (D-F7-6)."""
        outputs: list[P6UnitOutput] = []
        failures: list[UnitFailure] = []
        next_number = 1
        for result in results:
            assert result.response is not None
            unit_output = _unit_output(result.unit.unit_id, result.response, next_number)
            try:
                await self._results.persist_p6_unit(context.generation_id, unit_output.to_rpc_payload())
            except PersistenceError as exc:
                logger.warning(
                    "P6 persistencia fallida generation_id=%s unit_id=%s code=%s",
                    context.generation_id, result.unit.unit_id, exc.code,
                )
                failures.append(UnitFailure(unit_id=result.unit.unit_id, error_code=exc.code, message=exc.message))
                continue
            outputs.append(unit_output)
            next_number += len(unit_output.test_cases)
        return outputs, failures

    # --------------------------------------------------------------- avisos
    @staticmethod
    def _warnings(output: P6Output, results: Sequence[_UnitResult]) -> tuple[StageWarning, ...]:
        warnings: list[StageWarning] = []
        if output.failed_units:
            warnings.append(
                StageWarning(
                    code="UNIT_GENERATION_FAILED",
                    message=f"{len(output.failed_units)} unidad(es) no produjeron casos de prueba.",
                    details={"units": [item.model_dump(mode="json") for item in output.failed_units]},
                )
            )
        truncated = {
            r.unit.unit_id: {"received": r.truncated_from, "max_cases": r.max_cases}
            for r in results
            if r.truncated_from is not None and r.failure is None
        }
        if truncated:
            warnings.append(
                StageWarning(
                    code="CASES_TRUNCATED",
                    message=f"{len(truncated)} unidad(es) devolvieron más casos del tope y se truncaron.",
                    details={"units": truncated},
                )
            )
        filtered = {
            r.unit.unit_id: {
                "filtered_codes": sorted(set(r.filtered_codes)),
                "filtered_occurrences": len(r.filtered_codes),
                "dropped_cases": r.dropped_cases,
            }
            for r in results
            if r.filtered_codes and r.failure is None
        }
        if filtered:
            warnings.append(
                StageWarning(
                    code="REQUIREMENT_CODES_FILTERED",
                    message=f"{len(filtered)} unidad(es) enlazaron RF que no son objetivo; se filtraron.",
                    details={"units": filtered},
                )
            )
        retried = {r.unit.unit_id: r.errors for r in results if r.retries}
        if retried:
            warnings.append(
                StageWarning(
                    code="BATCH_RETRIED",
                    message=f"{len(retried)} unidad(es) necesitaron reintentos.",
                    details={"units": retried},
                )
            )
        if output.uncovered_requirement_codes:
            warnings.append(
                StageWarning(
                    code="UNCOVERED_REQUIREMENTS",
                    message=f"{len(output.uncovered_requirement_codes)} RF objetivo quedaron sin casos de prueba.",
                    details={"requirement_codes": list(output.uncovered_requirement_codes)},
                )
            )
        return tuple(warnings)


# ----------------------------------------------------------------- helpers
def build_user_message(generation_context: GenerationContext, unit: ContextUnit, max_cases: int) -> str:
    """Mensaje de usuario por unidad: el contenido variable que no va en el `.md` del prompt."""

    def requirements(items: Sequence[ContextRequirement]) -> str:
        return json.dumps([item.model_dump(mode="json") for item in items], ensure_ascii=False, indent=2)

    stories = [
        story.model_dump(mode="json", include={"code", "original_text", "role", "objective", "benefit", "content_sections"})
        for story in unit.user_stories
    ]
    parts = [
        f"Genera como máximo {max_cases} casos de prueba para esta unidad.",
        "## RF objetivo\n" + requirements(unit.requirements),
    ]
    if unit.context_requirements:
        parts.append("## RF de contexto (no enlazar)\n" + requirements(unit.context_requirements))
    parts.append("## Historias de usuario de origen\n" + json.dumps(stories, ensure_ascii=False, indent=2))
    parts.append(
        "## JSON Schema de salida\n" + json.dumps(generation_context.output_spec.json_schema, ensure_ascii=False)
    )
    parts.append("Devuelve solo el objeto JSON.")
    return "\n\n".join(parts)


def _unit_output(unit_id: str, response: P6LlmResponse, first_number: int) -> P6UnitOutput:
    """Asigna `id` y `CP-xxx` (desde `first_number`) a los casos del LLM. Vínculos `pending` (R7, D-14)."""
    cases: list[TestCase] = []
    for offset, draft in enumerate(response.test_cases):
        values: dict[str, Any] = draft.model_dump(exclude={"requirement_codes"})
        cases.append(
            TestCase(
                id=uuid4(),
                code=f"CP-{first_number + offset:03d}",
                requirement_links=tuple(RequirementTestCaseLink(requirement_code=c) for c in draft.requirement_codes),
                **values,
            )
        )
    return P6UnitOutput(unit_id=unit_id, test_cases=tuple(cases))


def _uncovered(units: Sequence[ContextUnit], outputs: Sequence[P6UnitOutput]) -> tuple[str, ...]:
    """RF objetivo (de todas las unidades, también las fallidas) sin ningún caso persistido."""
    linked = {code for output in outputs for case in output.test_cases for code in case.requirement_codes()}
    return tuple(item.code for unit in units for item in unit.requirements if item.code not in linked)


class GenerationStubStage(StubStage):
    """P6 simulada (Fase 1). Se usa con `PIPELINE_STAGES=stub` y en tests del orquestador."""

    key: ClassVar[StageKey] = StageKey.P6

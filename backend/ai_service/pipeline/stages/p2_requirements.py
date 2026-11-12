"""P2 — Clasificación de HU y extracción de RF (LLM en lotes).

1. Lee `context.p1_output` (solo HU no `invalid`).
2. Parte las HU en lotes de `P2Config.max_stories_per_call` y, por lote, llama al `LlmClient`
   con el prompt de `prompts/p2.py` (instrucciones como `system`, lote como JSON en `prompt`).
3. Valida cada respuesta con `P2LlmResponse` (clasificación exacta del lote); reintenta el lote
   hasta `P2Config.max_retries` veces si la salida es inválida o el proveedor falla transitoriamente.
4. Consolida los lotes en un `P2Output` (códigos `RF-xxx` consecutivos) y lo persiste con
   `persist_p2_requirements`.
5. 0 RF → aviso `NO_REQUIREMENTS_EXTRACTED` y `skip_remaining=True` (D-29).
"""

import asyncio
import json
import logging
import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import ClassVar
from uuid import uuid4

from pydantic import ValidationError

from ai_service.clients.llm import LlmClient, LlmRequest, LlmResponse
from ai_service.core.errors import LlmContextLengthError, LlmError, PersistenceError
from ai_service.pipeline.context import PipelineContext
from ai_service.pipeline.contracts.common import StoryClassificationCategory, StoryValidationStatus
from ai_service.pipeline.contracts.p1 import UserStory
from ai_service.pipeline.contracts.p2 import (
    FunctionalRequirement,
    P2Config,
    P2Input,
    P2LlmResponse,
    P2Output,
    RequirementDraft,
    StoryClassification,
)
from ai_service.pipeline.prompts.p2 import ResolvedP2Prompt
from ai_service.pipeline.stages.base import StageBase, StageError, StageResult, StubStage
from ai_service.repositories.pipeline_results import PipelineResultsRepository
from ai_service.schemas.generations import LlmRun, StageKey, StageWarning

logger = logging.getLogger(__name__)

PromptResolver = Callable[[str], ResolvedP2Prompt]

RAW_LOG_LIMIT = 2000  # caracteres de la salida cruda del LLM que se registran ante un lote inválido
_CODE_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)


@dataclass(slots=True)
class _BatchResult:
    response: P2LlmResponse
    run: LlmRun
    retries: int
    errors: list[str] = field(default_factory=list)


class RequirementsStage(StageBase):
    """P2 real. Recibe `LlmClient`, el resolvedor de prompts y el repositorio por constructor (R-DI-2)."""

    key: ClassVar[StageKey] = StageKey.P2

    def __init__(
        self,
        *,
        llm_client: LlmClient,
        prompt_resolver: PromptResolver,
        results: PipelineResultsRepository,
        config: P2Config,
        retry_delay_seconds: float = 1.0,
    ) -> None:
        self._llm = llm_client
        self._resolve_prompt = prompt_resolver
        self._results = results
        self._config = config
        self._retry_delay_seconds = retry_delay_seconds

    async def run(self, context: PipelineContext) -> StageResult:
        if context.p1_output is None:
            raise RuntimeError("P2 requiere p1_output: P1 no se ejecutó")
        stories = tuple(s for s in context.p1_output.user_stories if s.validation_status != StoryValidationStatus.INVALID)
        if not stories:  # P1Output lo impide; defensa en profundidad (D-29)
            return StageResult(
                warnings=(StageWarning(code="NO_PROCESSABLE_STORIES", message="No hay HU procesables para P2."),),
                skip_remaining=True,
            )
        p2_input = P2Input(generation_id=context.generation_id, user_stories=stories, config=self._config)
        prompt = self._resolve_prompt(self._config.prompt_version)

        size = self._config.max_stories_per_call
        batches = [p2_input.user_stories[i : i + size] for i in range(0, len(p2_input.user_stories), size)]
        results: list[_BatchResult] = []
        for number, batch in enumerate(batches, start=1):
            results.append(await self._run_batch(context, prompt, batch, number))

        output = self._consolidate(results)
        try:
            await self._results.persist_p2_requirements(context.generation_id, output.to_rpc_payload())
        except PersistenceError as exc:
            raise StageError(exc.code, exc.message, retryable=True, details=exc.details or None) from exc

        context.p2_output = output
        categories = Counter(item.category.value for item in output.classifications)
        logger.info(
            "P2 completada generation_id=%s lotes=%s rf=%s clasificaciones=%s",
            context.generation_id, len(batches), len(output.requirements), dict(categories),
        )
        return StageResult(
            warnings=self._warnings(output, results),
            llm_runs=tuple(result.run for result in results),
            runtime_info={
                "prompt_version": prompt.prompt_version,
                "provider": self._config.llm.provider,
                "model": self._config.llm.model,
                "max_stories_per_call": size,
                "max_retries": self._config.max_retries,
                "batches": len(batches),
                "retries_used": sum(result.retries for result in results),
                "stories_processed": len(stories),
                "requirements_count": len(output.requirements),
                "classification_counts": {category.value: categories.get(category.value, 0) for category in StoryClassificationCategory},
            },
            skip_remaining=not output.requirements,
        )

    # ----------------------------------------------------------------- lotes
    async def _run_batch(
        self, context: PipelineContext, prompt: ResolvedP2Prompt, batch: Sequence[UserStory], number: int
    ) -> _BatchResult:
        codes = {story.code for story in batch}
        request = self._build_request(prompt, batch)
        attempts = 0
        input_tokens: int | None = None
        output_tokens: int | None = None
        latency_ms: int | None = None
        errors: list[str] = []
        max_attempts = self._config.max_retries + 1

        while attempts < max_attempts:
            attempts += 1
            try:
                response = await self._llm.complete(request)
            except LlmContextLengthError as exc:
                raise StageError(exc.code, exc.message, details={"batch": number}) from exc
            except LlmError as exc:
                errors.append(exc.code)
                logger.warning(
                    "P2 fallo del LLM generation_id=%s batch=%s attempt=%s code=%s",
                    context.generation_id, number, attempts, exc.code,
                )
                if attempts >= max_attempts:
                    code = "LLM_INVALID_OUTPUT" if exc.code == "LLM_INVALID_OUTPUT" else "LLM_UNAVAILABLE"
                    raise StageError(
                        code, f"El modelo de lenguaje falló en el lote {number} tras {attempts} intento(s).",
                        retryable=True, details={"batch": number, "errors": errors},
                    ) from exc
                await asyncio.sleep(self._retry_delay_seconds * attempts)
                continue

            input_tokens = _add(input_tokens, response.input_tokens)
            output_tokens = _add(output_tokens, response.output_tokens)
            latency_ms = _add(latency_ms, response.latency_ms)
            parsed = self._parse(context, response, codes, number, attempts)
            if parsed is not None:
                run = LlmRun(
                    provider=self._config.llm.provider,
                    model=self._config.llm.model,
                    prompt_version=prompt.prompt_version,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    attempts=attempts,
                    latency_ms=latency_ms,
                )
                return _BatchResult(response=parsed, run=run, retries=attempts - 1, errors=errors)
            errors.append("LLM_INVALID_OUTPUT")

        raise StageError(
            "LLM_INVALID_OUTPUT",
            f"La respuesta del modelo de lenguaje no es válida en el lote {number} tras {attempts} intento(s).",
            retryable=True,
            details={"batch": number, "attempts": attempts},
        )

    def _parse(
        self, context: PipelineContext, response: LlmResponse, codes: set[str], number: int, attempt: int
    ) -> P2LlmResponse | None:
        raw = _strip_code_fence(response.text)
        try:
            return P2LlmResponse.model_validate_json(raw, context={"user_story_codes": codes})
        except ValidationError as exc:
            # Observabilidad pedida explícitamente: sin la salida cruda un LLM_INVALID_OUTPUT es opaco.
            logger.debug(
                "P2 lote inválido generation_id=%s batch=%s attempt=%s raw=%s err=%s",
                context.generation_id, number, attempt, response.text[:RAW_LOG_LIMIT], exc,
            )
            logger.warning(
                "P2 lote inválido generation_id=%s batch=%s attempt=%s errores=%s",
                context.generation_id, number, attempt, exc.error_count(),
            )
            return None

    def _build_request(self, prompt: ResolvedP2Prompt, batch: Sequence[UserStory]) -> LlmRequest:
        parameters = dict(self._config.llm.parameters)
        stories = [
            {
                "code": story.code,
                "original_text": story.original_text,
                "role": story.role,
                "objective": story.objective,
                "benefit": story.benefit,
                "content_sections": [{"kind": s.kind, "text": s.text} for s in story.content_sections],
            }
            for story in batch
        ]
        user_prompt = (
            "Historias de usuario a analizar (JSON). Clasifica TODAS y devuelve solo el objeto JSON:\n\n"
            + json.dumps({"user_stories": stories}, ensure_ascii=False, indent=2)
        )
        return LlmRequest(
            prompt=user_prompt,
            model=self._config.llm.model,
            system=prompt.text,
            max_tokens=parameters.pop("max_tokens", None),
            temperature=parameters.pop("temperature", None),
            extra=parameters,
        )

    # ----------------------------------------------------------- consolidación
    @staticmethod
    def _consolidate(results: Sequence[_BatchResult]) -> P2Output:
        classifications: list[StoryClassification] = []
        drafts: list[RequirementDraft] = []
        for result in results:
            classifications.extend(result.response.classifications)
            drafts.extend(result.response.requirements)
        requirements = tuple(
            FunctionalRequirement(id=uuid4(), code=f"RF-{number:03d}", **draft.model_dump())
            for number, draft in enumerate(drafts, start=1)
        )
        covered = {code for requirement in requirements for code in requirement.user_story_codes}
        return P2Output(
            classifications=tuple(classifications),
            requirements=requirements,
            stories_without_requirements=tuple(c.user_story_code for c in classifications if c.user_story_code not in covered),
        )

    @staticmethod
    def _warnings(output: P2Output, results: Sequence[_BatchResult]) -> tuple[StageWarning, ...]:
        warnings: list[StageWarning] = []
        if not output.requirements:
            warnings.append(
                StageWarning(code="NO_REQUIREMENTS_EXTRACTED", message="Ninguna HU produjo requisitos funcionales.")
            )
        retried = {str(i): r.errors for i, r in enumerate(results, start=1) if r.retries}
        if retried:
            warnings.append(
                StageWarning(
                    code="BATCH_RETRIED",
                    message=f"{len(retried)} lote(s) necesitaron reintentos.",
                    details={"batches": retried},
                )
            )
        candidates = {c.user_story_code for c in output.classifications if c.category == StoryClassificationCategory.CANDIDATA_FUNCIONAL}
        without = sorted(candidates & set(output.stories_without_requirements))
        if without:
            warnings.append(
                StageWarning(
                    code="CANDIDATE_WITHOUT_REQUIREMENTS",
                    message=f"{len(without)} HU candidata(s) funcional(es) no produjeron RF.",
                    details={"user_story_codes": without},
                )
            )
        return tuple(warnings)


def _strip_code_fence(text: str) -> str:
    """Quita un bloque ```json … ``` envolvente, habitual en respuestas de LLM."""
    match = _CODE_FENCE.match(text)
    return match.group(1) if match else text.strip()


def _add(total: int | None, value: int | None) -> int | None:
    if value is None:
        return total
    return (total or 0) + value


class RequirementsStubStage(StubStage):
    """P2 simulada (Fase 1). Se usa con `PIPELINE_STAGES=stub` y en tests del orquestador."""

    key: ClassVar[StageKey] = StageKey.P2

"""P3 — Generación de embeddings de los RF (Fase 5).

1. Lee `context.p2_output` (RF). P3 se omite sin clustering (R2) o con 0 RF (D-29).
2. Construye un texto por RF con `P3Config.input_template` (`{code}`, `{description}`).
3. Vectoriza en lotes de `P3Config.batch_size` vía `EmbeddingsClient`; reintenta un lote hasta
   `max_retries` veces solo ante fallos transitorios (`EmbeddingsError` genérico). Los errores de
   dimensión o de vector inválido no se reintentan: el mismo modelo los reproduciría.
4. Ensambla `P3Output` (vectores finitos y de dimensión uniforme) y lo deja en
   `context.p3_output`. **No persiste** (D-09): P4 lo consume en memoria.
"""

import asyncio
import logging
from collections.abc import Sequence
from typing import ClassVar

from pydantic import ValidationError

from ai_service.clients.embeddings import EmbeddingsClient, EmbeddingsRequest, EmbeddingsResponse
from ai_service.core.errors import EmbeddingsDimensionError, EmbeddingsError, EmbeddingsInvalidVectorError
from ai_service.pipeline.context import PipelineContext
from ai_service.pipeline.contracts.p2 import FunctionalRequirement
from ai_service.pipeline.contracts.p3 import EmbeddingModelInfo, P3Config, P3Input, P3Output, RequirementEmbedding
from ai_service.pipeline.stages.base import StageBase, StageError, StageResult, StubStage
from ai_service.schemas.generations import StageKey, StageWarning

logger = logging.getLogger(__name__)

ERROR_CODE = "EMBEDDINGS_FAILED"

# No transitorios (decisión 3): reintentar con el mismo modelo daría el mismo resultado.
_NON_RETRYABLE = (EmbeddingsDimensionError, EmbeddingsInvalidVectorError)


class EmbeddingsStage(StageBase):
    """P3 real. Recibe el puerto `EmbeddingsClient` y su configuración por constructor (R-DI-2).

    `provider` (H-2) y `max_retries` van aparte de `P3Config` para no tocar el contrato de la Fase 3.
    """

    key: ClassVar[StageKey] = StageKey.P3
    requires_clustering: ClassVar[bool] = True

    def __init__(
        self,
        *,
        embeddings_client: EmbeddingsClient,
        config: P3Config,
        provider: str,
        max_retries: int = 2,
        retry_delay_seconds: float = 1.0,
    ) -> None:
        self._client = embeddings_client
        self._config = config
        self._provider = provider
        self._max_retries = max_retries
        self._retry_delay_seconds = retry_delay_seconds

    async def run(self, context: PipelineContext) -> StageResult:
        if context.p2_output is None:
            raise RuntimeError("P3 requiere p2_output: P2 no se ejecutó")
        requirements = context.p2_output.requirements
        if not requirements:  # D-29 lo impide vía skip_remaining; defensa en profundidad
            return StageResult(
                warnings=(StageWarning(code="NO_REQUIREMENTS", message="No hay RF que vectorizar."),),
                skip_remaining=True,
            )
        p3_input = P3Input(generation_id=context.generation_id, requirements=requirements, config=self._config)

        size = self._config.batch_size
        batches = [p3_input.requirements[i : i + size] for i in range(0, len(p3_input.requirements), size)]
        embeddings: list[tuple[FunctionalRequirement, Sequence[float]]] = []
        responses: list[EmbeddingsResponse] = []
        retries_used = 0
        for number, batch in enumerate(batches, start=1):
            response, retries = await self._run_batch(context, batch, number)
            retries_used += retries
            responses.append(response)
            embeddings.extend(zip(batch, response.vectors, strict=True))

        first = responses[0]
        try:
            # Pydantic valida vectores finitos y dimensión uniforme entre lotes.
            vectors = tuple(
                RequirementEmbedding(requirement_code=rf.code, vector=tuple(vector)) for rf, vector in embeddings
            )
            model_info = EmbeddingModelInfo(
                provider=self._provider,
                model_name=first.model_name,
                model_version=first.model_version,
                dimension=first.dimension,
                normalized=first.normalized,
                input_template=self._config.input_template,
            )
            output = P3Output(model_info=model_info, embeddings=vectors)
        except ValidationError as exc:
            raise StageError(
                ERROR_CODE, "Los embeddings generados no son válidos.", details={"errors": exc.error_count()}
            ) from exc

        context.p3_output = output
        logger.info(
            "P3 completada generation_id=%s lotes=%s rf=%s dimension=%s",
            context.generation_id, len(batches), len(embeddings), model_info.dimension,
        )
        warnings: tuple[StageWarning, ...] = ()
        if retries_used:
            warnings = (
                StageWarning(
                    code="BATCH_RETRIED",
                    message=f"Los embeddings necesitaron {retries_used} reintento(s).",
                    details={"retries": retries_used},
                ),
            )
        return StageResult(
            warnings=warnings,
            runtime_info={
                "embedding_model": model_info.model_dump(mode="json"),
                "batch_size": size,
                "max_retries": self._max_retries,
                "batches": len(batches),
                "retries_used": retries_used,
                "requirements_count": len(embeddings),
            },
        )

    async def _run_batch(
        self, context: PipelineContext, batch: Sequence[FunctionalRequirement], number: int
    ) -> tuple[EmbeddingsResponse, int]:
        request = EmbeddingsRequest(
            texts=tuple(self._config.input_template.format(code=rf.code, description=rf.description) for rf in batch),
            model=self._config.model_name,
            input_template=self._config.input_template,
            normalize=self._config.normalize,
            extra={"batch_size": self._config.batch_size},
        )
        max_attempts = self._max_retries + 1
        errors: list[str] = []
        attempts = 0
        while True:
            attempts += 1
            try:
                response = await self._client.embed(request)
            except _NON_RETRYABLE as exc:
                raise StageError(
                    ERROR_CODE, f"El proveedor de embeddings devolvió vectores no válidos en el lote {number}.",
                    details={"batch": number, "cause": exc.code},
                ) from exc
            except EmbeddingsError as exc:
                errors.append(exc.code)
                logger.warning(
                    "P3 fallo de embeddings generation_id=%s batch=%s attempt=%s code=%s",
                    context.generation_id, number, attempts, exc.code,
                )
                if attempts >= max_attempts:
                    raise StageError(
                        ERROR_CODE, f"Falló la generación de embeddings en el lote {number} tras {attempts} intento(s).",
                        retryable=True, details={"batch": number, "errors": errors},
                    ) from exc
                await asyncio.sleep(self._retry_delay_seconds * attempts)
                continue
            if len(response.vectors) != len(batch):
                raise StageError(
                    ERROR_CODE, f"El proveedor de embeddings devolvió un número de vectores inesperado en el lote {number}.",
                    details={"batch": number, "expected": len(batch), "received": len(response.vectors)},
                )
            return response, attempts - 1


class EmbeddingsStubStage(StubStage):
    """P3 simulada (Fase 1). Se usa con `PIPELINE_STAGES=stub` y en tests del orquestador."""

    key: ClassVar[StageKey] = StageKey.P3
    requires_clustering: ClassVar[bool] = True

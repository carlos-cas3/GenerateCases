"""Adaptador OpenAI de `EmbeddingsClient` (`embeddings.create` sobre `AsyncOpenAI`, D-EMB-4)."""

import math
from typing import Any

import openai
from openai import AsyncOpenAI

from ai_service.clients.embeddings import EmbeddingsRequest, EmbeddingsResponse, validate_vectors
from ai_service.core.errors import EmbeddingsError

# Límite de entradas por llamada de la API de embeddings de OpenAI.
MAX_INPUTS_PER_CALL = 2048


class OpenAIEmbeddingsClient:
    """Implementación de `EmbeddingsClient` sobre la API de OpenAI.

    Recibe el `AsyncOpenAI` ya construido (lo crea `EmbeddingsClientFactory`), así que
    los tests pueden pasarle un cliente con transporte simulado.
    `extra["batch_size"]` trocea la solicitud; el resto de `extra` (p. ej. `dimensions`)
    se pasa a la API. Si se pide `dimensions`, es la dimensión esperada.
    """

    def __init__(self, client: AsyncOpenAI) -> None:
        self._client = client

    async def embed(self, request: EmbeddingsRequest) -> EmbeddingsResponse:
        params: dict[str, Any] = dict(request.extra)
        batch_size = min(int(params.pop("batch_size", MAX_INPUTS_PER_CALL)), MAX_INPUTS_PER_CALL)
        texts = list(request.texts)

        vectors: list[tuple[float, ...]] = []
        model_name = request.model
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            try:
                response = await self._client.embeddings.create(model=request.model, input=batch, **params)
            except openai.APITimeoutError as exc:
                raise EmbeddingsError("OpenAI no respondió dentro del tiempo límite.") from exc
            except openai.OpenAIError as exc:  # incluye RateLimitError
                raise EmbeddingsError(f"Falló la llamada de embeddings a OpenAI: {exc}") from exc
            if len(response.data) != len(batch):
                raise EmbeddingsError(
                    "OpenAI devolvió un número de vectores distinto al de textos.",
                    details={"expected": len(batch), "received": len(response.data)},
                )
            ordered = sorted(response.data, key=lambda item: item.index)
            vectors.extend(tuple(float(component) for component in item.embedding) for item in ordered)
            model_name = response.model

        expected = params.get("dimensions")
        dimension = validate_vectors(vectors, int(expected) if expected is not None else None)
        if request.normalize:
            vectors = [_l2_normalize(vector) for vector in vectors]
        return EmbeddingsResponse(
            vectors=tuple(vectors),
            model_name=model_name,
            model_version=None,
            dimension=dimension,
            normalized=request.normalize,
        )

    async def aclose(self) -> None:
        await self._client.close()


def _l2_normalize(vector: tuple[float, ...]) -> tuple[float, ...]:
    """OpenAI ya devuelve vectores de norma 1; se renormaliza por si el modelo cambia."""
    norm = math.sqrt(sum(component * component for component in vector))
    return vector if norm == 0 else tuple(component / norm for component in vector)

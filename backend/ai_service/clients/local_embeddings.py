"""Adaptador local de `EmbeddingsClient` sobre `sentence-transformers` (D-EMB-2, D-EMB-3)."""

import asyncio
from typing import Any

from ai_service.clients.embeddings import EmbeddingsRequest, EmbeddingsResponse, validate_vectors
from ai_service.core.errors import EmbeddingsError

DEFAULT_BATCH_SIZE = 32


class LocalEmbeddingsClient:
    """Implementación de `EmbeddingsClient` con un modelo `SentenceTransformer` en proceso.

    Recibe el modelo ya cargado (lo crea `EmbeddingsClientFactory`) y su nombre, así que
    los tests pueden pasarle un modelo falso sin cargar torch. La librería es síncrona y
    consume CPU: `embed()` la ejecuta en un hilo (D-EMB-6).
    """

    def __init__(self, model: Any, model_name: str) -> None:
        self._model = model
        self._model_name = model_name

    async def embed(self, request: EmbeddingsRequest) -> EmbeddingsResponse:
        if request.model != self._model_name:
            # El modelo se carga una vez al arrancar: no se puede cambiar por solicitud.
            raise EmbeddingsError(
                f"El modelo solicitado ({request.model!r}) no es el cargado ({self._model_name!r}).",
                details={"requested": request.model, "loaded": self._model_name},
            )
        batch_size = int(request.extra.get("batch_size", DEFAULT_BATCH_SIZE))  # type: ignore[call-overload]
        try:
            expected = self._model.get_sentence_embedding_dimension()
            raw = await asyncio.to_thread(
                self._model.encode,
                list(request.texts),
                batch_size=batch_size,
                normalize_embeddings=request.normalize,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            vectors = tuple(tuple(float(component) for component in vector) for vector in raw.tolist())
        except Exception as exc:  # torch/sentence-transformers no tienen una excepción base común (R-AP-4)
            raise EmbeddingsError("Falló la vectorización con el modelo local.") from exc

        dimension = validate_vectors(vectors, expected)
        return EmbeddingsResponse(
            vectors=vectors,
            model_name=self._model_name,
            model_version=None,
            dimension=dimension,
            normalized=request.normalize,
        )

    async def aclose(self) -> None:
        """No-op: el modelo no mantiene conexiones."""

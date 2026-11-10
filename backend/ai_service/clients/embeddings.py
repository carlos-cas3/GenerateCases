"""Puerto del cliente de embeddings — contrato, DTOs y validación, sin infraestructura (R-AP-2).

Lo usa P3 (ver `issue_resolver_embeddings.md`). P3 depende de `EmbeddingsClient`, nunca de
un adaptador concreto; lo implementan `local_embeddings.py`, `openai_embeddings.py` y el
fake (`embeddings_fake.py`) por duck typing (R-AP-3).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from ai_service.core.errors import EmbeddingsDimensionError, EmbeddingsInvalidVectorError


@dataclass(frozen=True, slots=True)
class EmbeddingsRequest:
    """Solicitud de vectorización. La construye P3 a partir de los RF y su `P3Config`."""

    texts: tuple[str, ...]  # textos a vectorizar (uno por RF), con la plantilla ya aplicada
    model: str  # modelo concreto; viene de `P3Config.model_name`
    # Plantilla con la que P3 construyó `texts` (p. ej. "{description}"). Los adaptadores no la
    # reinterpretan: viaja para reproducibilidad (`EmbeddingModelInfo.input_template`).
    input_template: str | None = None
    normalize: bool = True  # normalizar L2 los vectores resultantes
    # Parámetros adicionales específicos del proveedor (p. ej. `batch_size`, `dimensions`).
    # dict: `frozen` no lo hace inmutable por dentro.
    extra: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EmbeddingsResponse:
    """Respuesta del proveedor. Un vector por texto, en el mismo orden."""

    vectors: tuple[tuple[float, ...], ...]  # un vector por texto de entrada
    model_name: str  # nombre exacto del modelo usado
    model_version: str | None  # versión si el proveedor la expone
    dimension: int  # dimensión de cada vector
    normalized: bool  # si los vectores están normalizados


class EmbeddingsClient(Protocol):
    """Puerto de generación de embeddings. Lo implementan los adaptadores y el fake."""

    async def embed(self, request: EmbeddingsRequest) -> EmbeddingsResponse:
        """Vectoriza los textos. Lanza `EmbeddingsError` (o un subtipo) ante fallos."""
        ...

    async def aclose(self) -> None:
        """Libera recursos. `main.py` lo llama al apagar (R-FA-7)."""
        ...


def validate_vectors(vectors: Sequence[Sequence[float]], expected_dimension: int | None = None) -> int:
    """Comprueba dimensión uniforme y valores finitos; devuelve la dimensión.

    Utilidad compartida por los adaptadores. Sin `expected_dimension`, la del primer vector
    marca la esperada. Lanza `EmbeddingsDimensionError` o `EmbeddingsInvalidVectorError`
    con el contexto diagnóstico en `details` (P-5).
    """
    if not vectors:
        return expected_dimension or 0
    expected = expected_dimension if expected_dimension is not None else len(vectors[0])
    for index, vector in enumerate(vectors):
        if len(vector) != expected:
            raise EmbeddingsDimensionError(
                details={"expected": expected, "received": len(vector), "vector_index": index}
            )
        if not all(math.isfinite(component) for component in vector):
            raise EmbeddingsInvalidVectorError(details={"vector_index": index, "reason": "contains NaN or inf"})
    return expected

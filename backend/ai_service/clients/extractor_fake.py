"""Fake determinista de `DocumentTextExtractor` para tests (R-DI-3)."""

from collections.abc import Iterable

from ai_service.core.errors import DocumentExtractionError
from ai_service.pipeline.contracts.common import FileType


class FakeDocumentExtractor:
    """Devuelve, en orden, los textos con los que se construyó.

    Cada elemento puede ser un texto (extracción correcta) o una
    `DocumentExtractionError` (se lanza al llegar su turno).
    Las llamadas recibidas quedan en `calls` para inspeccionarlas.
    """

    def __init__(self, responses: Iterable[str | DocumentExtractionError] = ()) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[bytes, FileType]] = []

    async def extract(self, data: bytes, file_type: FileType) -> str:
        self.calls.append((data, file_type))
        if not self._responses:
            raise AssertionError("FakeDocumentExtractor: no quedan respuestas programadas.")
        item = self._responses.pop(0)
        if isinstance(item, DocumentExtractionError):
            raise item
        return item

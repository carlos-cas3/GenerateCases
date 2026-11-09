"""Extractor compuesto: implementa `DocumentTextExtractor` delegando por `FileType`.

No es una factory (D-EXT-5): los adaptadores por formato coexisten siempre y el
tipo de archivo de cada llamada decide cuál se usa. `main.py` lo construye con
los tres adaptadores; cada estrategia sigue siendo reemplazable por separado.
"""

from collections.abc import Mapping

from ai_service.clients.extractor import DocumentTextExtractor
from ai_service.core.errors import DocumentExtractionError
from ai_service.pipeline.contracts.common import FileType


class CompositeDocumentExtractor:
    """Reparte cada extracción al adaptador registrado para su tipo de archivo."""

    def __init__(self, extractors: Mapping[FileType, DocumentTextExtractor]) -> None:
        self._extractors = dict(extractors)

    async def extract(self, data: bytes, file_type: FileType) -> str:
        extractor = self._extractors.get(file_type)
        if extractor is None:
            raise DocumentExtractionError(f"No hay extractor para archivos de tipo {file_type!s}.")
        return await extractor.extract(data, file_type)

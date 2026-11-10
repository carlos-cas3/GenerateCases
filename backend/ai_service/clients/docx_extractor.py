"""Adaptador DOCX de `DocumentTextExtractor` sobre `python-docx` (D-EXT-3).

Alcance v1: solo el texto de los párrafos del cuerpo, sin tablas, encabezados,
pies, estilos ni numeración automática (D-EXT-6, D-25).
"""

import asyncio
import io

import docx

from ai_service.core.errors import DocumentExtractionError
from ai_service.pipeline.contracts.common import FileType


class DocxDocumentExtractor:
    """Concatena el texto de los párrafos con `\\n`. Se ejecuta en un hilo (librería síncrona)."""

    async def extract(self, data: bytes, file_type: FileType) -> str:
        return await asyncio.to_thread(_extract_sync, data)


def _extract_sync(data: bytes) -> str:
    try:
        document = docx.Document(io.BytesIO(data))
        paragraphs = [paragraph.text for paragraph in document.paragraphs]
    except Exception as exc:  # zip/XML inválido: python-docx no tiene una excepción base común (R-AP-4)
        raise DocumentExtractionError("No se pudo leer el archivo DOCX.") from exc
    return "\n".join(paragraphs).strip()

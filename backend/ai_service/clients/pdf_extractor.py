"""Adaptador PDF de `DocumentTextExtractor` sobre `pdfplumber` (D-EXT-2).

Alcance v1: solo texto plano, sin tratar encabezados, pies, tablas ni estilos (D-EXT-6, D-25).
"""

import asyncio
import io

import pdfplumber

from ai_service.core.errors import DocumentExtractionError
from ai_service.pipeline.contracts.common import FileType


class PdfDocumentExtractor:
    """Concatena el texto de cada página con `\\n`.

    Un PDF sin texto extraíble (escaneado, solo imágenes) devuelve `""`: P1 lo
    rechaza con `EMPTY_DOCUMENT`. `pdfplumber` es síncrono y analizar un PDF
    grande consume CPU, así que se ejecuta en un hilo para no bloquear el event loop.
    """

    async def extract(self, data: bytes, file_type: FileType) -> str:
        return await asyncio.to_thread(_extract_sync, data)


def _extract_sync(data: bytes) -> str:
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
    except Exception as exc:  # pdfplumber/pdfminer no tienen una excepción base común (R-AP-4)
        raise DocumentExtractionError("No se pudo leer el archivo PDF.") from exc
    return "\n".join(pages).strip()

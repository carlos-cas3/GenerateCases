"""Adaptador TXT de `DocumentTextExtractor`. Solo stdlib (D-EXT-4)."""

from ai_service.core.errors import DocumentExtractionError
from ai_service.pipeline.contracts.common import FileType

# `utf-8-sig` acepta UTF-8 con o sin BOM. `latin-1` asigna un carácter a cada byte,
# así que como último recurso nunca falla: el texto puede salir con mojibake, pero no se pierde.
_ENCODINGS: tuple[str, ...] = ("utf-8-sig", "latin-1")


class TxtDocumentExtractor:
    """Decodifica texto plano: UTF-8 primero, `latin-1` como alternativa."""

    async def extract(self, data: bytes, file_type: FileType) -> str:
        for encoding in _ENCODINGS:
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise DocumentExtractionError("No se pudo decodificar el archivo de texto.")

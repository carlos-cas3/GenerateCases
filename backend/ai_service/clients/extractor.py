"""Puerto de extracción de texto — contrato sin infraestructura (R-AP-2).

Lo usa P1 (ver `issue_resolver_extractor.md`). P1 depende de `DocumentTextExtractor`,
nunca de un adaptador concreto. Lo implementan los adaptadores por formato
(`txt_extractor.py`, `pdf_extractor.py`, `docx_extractor.py`), el compuesto que los
reparte según el tipo de archivo (`composite_extractor.py`) y el fake (`extractor_fake.py`).
"""

from typing import Protocol

from ai_service.pipeline.contracts.common import FileType


class DocumentTextExtractor(Protocol):
    """Puerto de extracción de texto. P1 lo recibe por constructor (R-DI-2)."""

    async def extract(self, data: bytes, file_type: FileType) -> str:
        """Extrae el texto plano del archivo.

        Devuelve `""` si el archivo no contiene texto extraíble (P1 lo rechaza con
        `EMPTY_DOCUMENT`). Lanza `DocumentExtractionError` ante fallos irrecuperables.
        """
        ...

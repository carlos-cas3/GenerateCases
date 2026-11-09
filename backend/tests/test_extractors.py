"""Extractor de texto: fake, adaptadores TXT/PDF/DOCX, compuesto y cableado en `create_app`."""

import io
from typing import Any

import docx
import pytest

from ai_service.clients.composite_extractor import CompositeDocumentExtractor
from ai_service.clients.docx_extractor import DocxDocumentExtractor
from ai_service.clients.extractor_fake import FakeDocumentExtractor
from ai_service.clients.pdf_extractor import PdfDocumentExtractor
from ai_service.clients.txt_extractor import TxtDocumentExtractor
from ai_service.core.errors import DocumentExtractionError
from ai_service.main import create_app
from ai_service.pipeline.contracts.common import FileType
from ai_service.repositories.in_memory import InMemoryDocumentsRepository, InMemoryGenerationsRepository
from tests.conftest import make_settings
from tests.factories import FakeDocumentStorage


def _pdf(*pages: str) -> bytes:
    """PDF mínimo válido con una línea de texto por página (Helvetica, sin compresión)."""
    page_ids = [3 + 2 * i for i in range(len(pages))]
    font_id = 3 + 2 * len(pages)
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % pid for pid in page_ids)
        + b"] /Count %d >>" % len(pages),
        font_id: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for page_id, text in zip(page_ids, pages, strict=True):
        stream = b"BT /F1 12 Tf 72 720 Td (" + text.encode("latin-1") + b") Tj ET"
        objects[page_id] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents %d 0 R "
            b"/Resources << /Font << /F1 %d 0 R >> >> >>" % (page_id + 1, font_id)
        )
        objects[page_id + 1] = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"

    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += b"%d 0 obj\n" % number + objects[number] + b"\nendobj\n"
    xref = len(out)
    size = max(objects) + 1
    out += b"xref\n0 %d\n0000000000 65535 f \n" % size
    for number in range(1, size):
        out += b"%010d 00000 n \n" % offsets[number]
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (size, xref)
    return bytes(out)


def _docx(*paragraphs: str) -> bytes:
    document = docx.Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


# --- fake ---------------------------------------------------------------------------------


async def test_fake_returns_programmed_responses_in_order() -> None:
    error = DocumentExtractionError("ilegible")
    fake = FakeDocumentExtractor(["uno", error])

    assert await fake.extract(b"a", FileType.TXT) == "uno"
    with pytest.raises(DocumentExtractionError) as exc_info:
        await fake.extract(b"b", FileType.PDF)
    assert exc_info.value is error
    assert fake.calls == [(b"a", FileType.TXT), (b"b", FileType.PDF)]
    with pytest.raises(AssertionError):
        await fake.extract(b"c", FileType.DOCX)


# --- TXT ----------------------------------------------------------------------------------


async def test_txt_decodes_utf8_and_strips_bom() -> None:
    text = "Como usuario quiero iniciar sesión"
    extractor = TxtDocumentExtractor()

    assert await extractor.extract(text.encode("utf-8"), FileType.TXT) == text
    assert await extractor.extract(b"\xef\xbb\xbf" + text.encode("utf-8"), FileType.TXT) == text


async def test_txt_falls_back_to_latin1() -> None:
    text = "Gestión de módulos"
    assert await TxtDocumentExtractor().extract(text.encode("latin-1"), FileType.TXT) == text


# --- PDF ----------------------------------------------------------------------------------


async def test_pdf_joins_pages_with_newline() -> None:
    result = await PdfDocumentExtractor().extract(_pdf("HU-001 Iniciar sesion", "HU-002 Cerrar sesion"), FileType.PDF)
    assert result == "HU-001 Iniciar sesion\nHU-002 Cerrar sesion"


async def test_pdf_without_text_returns_empty_string() -> None:
    assert await PdfDocumentExtractor().extract(_pdf(""), FileType.PDF) == ""


async def test_pdf_library_errors_become_extraction_error() -> None:
    with pytest.raises(DocumentExtractionError):
        await PdfDocumentExtractor().extract(b"esto no es un pdf", FileType.PDF)


# --- DOCX ---------------------------------------------------------------------------------


async def test_docx_joins_paragraphs_with_newline() -> None:
    data = _docx("HU-001 Iniciar sesión", "Criterios: el usuario existe")
    result = await DocxDocumentExtractor().extract(data, FileType.DOCX)
    assert result == "HU-001 Iniciar sesión\nCriterios: el usuario existe"


async def test_docx_library_errors_become_extraction_error() -> None:
    with pytest.raises(DocumentExtractionError):
        await DocxDocumentExtractor().extract(b"esto no es un docx", FileType.DOCX)


# --- compuesto ----------------------------------------------------------------------------


async def test_composite_delegates_by_file_type() -> None:
    txt, pdf = FakeDocumentExtractor(["texto"]), FakeDocumentExtractor(["pdf"])
    composite = CompositeDocumentExtractor({FileType.TXT: txt, FileType.PDF: pdf})

    assert await composite.extract(b"x", FileType.PDF) == "pdf"
    assert await composite.extract(b"y", FileType.TXT) == "texto"
    assert pdf.calls == [(b"x", FileType.PDF)] and txt.calls == [(b"y", FileType.TXT)]


async def test_composite_without_adapter_for_type_raises_extraction_error() -> None:
    composite = CompositeDocumentExtractor({FileType.TXT: FakeDocumentExtractor()})
    with pytest.raises(DocumentExtractionError):
        await composite.extract(b"x", FileType.DOCX)


# --- create_app ---------------------------------------------------------------------------


def test_injected_extractor_is_exposed(client: Any) -> None:
    assert isinstance(client.app.state.extractor, FakeDocumentExtractor)


def test_default_extractor_handles_the_three_formats(store: Any) -> None:
    from fastapi.testclient import TestClient

    from ai_service.clients.llm_fake import FakeLlmClient

    app = create_app(
        make_settings(),
        generations_repository=InMemoryGenerationsRepository(store),
        documents_repository=InMemoryDocumentsRepository(store),
        documents_storage=FakeDocumentStorage(),
        llm_client=FakeLlmClient(),
    )
    with TestClient(app):
        extractor = app.state.extractor
        assert isinstance(extractor, CompositeDocumentExtractor)
        assert set(extractor._extractors) == set(FileType)

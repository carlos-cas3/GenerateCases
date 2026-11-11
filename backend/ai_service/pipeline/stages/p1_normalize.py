"""P1 — Procesamiento, segmentación y estructuración de HU (camino B: heurística, sin LLM).

Implementa la plantilla `docs/prompts_fases/Fase 4/plantilla_hu.md` (versionada por
`P1Config.rules_version`):

1. Storage → bytes → `DocumentTextExtractor` → texto.
2. `P1Config.story_delimiter_pattern` (`^##\\s+.+$`) parte el texto en bloques.
3. Cada bloque con declaración canónica ("Como …, quiero …, para …") → `UserStory`;
   sin ella → `UnresolvedFragment` ("historia no identificada"). El preámbulo previo al
   primer delimitador también es un fragmento no resuelto.
4. `persist_p1_user_stories` guarda las HU (los fragmentos e incidencias no se persisten, D-22).
"""

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import ClassVar
from uuid import uuid4

from pydantic import ValidationError

from ai_service.clients.extractor import DocumentTextExtractor
from ai_service.clients.storage import DocumentStorage
from ai_service.core.errors import DocumentExtractionError, PersistenceError, StoredDocumentUnavailable
from ai_service.pipeline.context import PipelineContext
from ai_service.pipeline.contracts.common import FileType, IssueSeverity, SourceSpan, StoryValidationStatus
from ai_service.pipeline.contracts.p1 import (
    P1Config,
    P1Output,
    SourceDocument,
    StorySection,
    UnresolvedFragment,
    UserStory,
    ValidationIssue,
)
from ai_service.pipeline.stages.base import StageBase, StageError, StageResult, StubStage
from ai_service.repositories.documents import DocumentsRepository
from ai_service.repositories.pipeline_results import PipelineResultsRepository
from ai_service.schemas.generations import StageKey, StageWarning

logger = logging.getLogger(__name__)

# Declaración canónica de `plantilla_hu.md` §2. Única diferencia: `\b` antes de "para" para no
# partir palabras que lo contienen ("comparar", "separar").
CANONICAL_STATEMENT = re.compile(
    r"^Como\s+(.+?),\s+quiero\s+(.+?)(?:,?\s*\bpara\s+(.+?))?\s*\.?\s*$",
    re.IGNORECASE | re.DOTALL,
)
SECTION_HEADER = re.compile(r"^###\s+(.+?)\s*#*\s*$", re.MULTILINE)
UNRESOLVED_REASON = "no coincide con la plantilla de HU"
PREAMBLE_REASON = "texto previo a la primera HU"

# Palabras vacías que se omiten al normalizar el título de una sección ("Reglas de negocio" →
# `reglas_negocio`), para coincidir con los `kind` sugeridos en `plantilla_hu.md` §4.
_SECTION_STOPWORDS = frozenset({"de", "del", "la", "las", "el", "los", "y", "e"})


@dataclass(frozen=True, slots=True)
class _Block:
    text: str  # del delimitador al siguiente (o al fin), sin espacios finales
    position: int  # orden de aparición entre todos los bloques (preámbulo incluido)


class NormalizeStage(StageBase):
    """P1 real. Depende de puertos (R-AP-2) inyectados por constructor (R-DI-2); sin `LlmClient`."""

    key: ClassVar[StageKey] = StageKey.P1

    def __init__(
        self,
        *,
        documents: DocumentsRepository,
        storage: DocumentStorage,
        extractor: DocumentTextExtractor,
        results: PipelineResultsRepository,
        config: P1Config,
    ) -> None:
        self._documents = documents
        self._storage = storage
        self._extractor = extractor
        self._results = results
        self._config = config
        self._delimiter = re.compile(config.story_delimiter_pattern, re.MULTILINE)

    async def run(self, context: PipelineContext) -> StageResult:
        document = await self._load_document(context)
        text = await self._extract_text(document)
        output, blocks_found = self.segment(text)

        try:
            await self._results.persist_p1_user_stories(context.generation_id, output.to_rpc_payload())
        except PersistenceError as exc:
            raise StageError(exc.code, exc.message, retryable=True, details=exc.details or None) from exc

        context.p1_output = output
        logger.info(
            "P1 completada generation_id=%s bloques=%s hu=%s no_identificadas=%s",
            context.generation_id, blocks_found, len(output.user_stories), len(output.unresolved_fragments),
        )
        return StageResult(
            warnings=self._warnings(output),
            runtime_info={
                "rules_version": self._config.rules_version,
                "language": self._config.language,
                "max_story_chars": self._config.max_story_chars,
                "blocks_found": blocks_found,
                "stories_identified": len(output.user_stories),
                "stories_unresolved": len(output.unresolved_fragments),
                "valid_count": output.valid_count,
                "warning_count": output.warning_count,
                "invalid_count": output.invalid_count,
            },
        )

    # ------------------------------------------------------------------ lectura
    async def _load_document(self, context: PipelineContext) -> SourceDocument:
        record = await self._documents.get_by_id(context.document_id)
        if record is None:
            raise StageError("DOCUMENT_UNREADABLE", "El documento de la generación ya no existe.")
        try:
            file_type = FileType(record.file_type)
        except ValueError as exc:
            raise StageError("DOCUMENT_UNREADABLE", "El tipo de archivo del documento no está soportado.") from exc
        try:
            data = await self._storage.download(record.storage_path)
        except StoredDocumentUnavailable as exc:
            raise StageError(exc.code, exc.message, retryable=True) from exc
        return SourceDocument(document_id=record.id, filename=record.filename, file_type=file_type, data=data)

    async def _extract_text(self, document: SourceDocument) -> str:
        try:
            text = await self._extractor.extract(document.data, document.file_type)
        except DocumentExtractionError as exc:
            raise StageError(exc.code, exc.message) from exc
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if not text.strip():
            raise StageError("EMPTY_DOCUMENT", "El documento no contiene texto extraíble.")
        return text

    # ------------------------------------------------------------- heurística
    def segment(self, text: str) -> tuple[P1Output, int]:
        """Segmenta y estructura el texto. Devuelve el `P1Output` y el número de bloques HU.

        Lanza `StageError(NO_STORIES_FOUND)` si ningún bloque encaja con la plantilla.
        """
        blocks, preamble = self._split(text)
        stories: list[UserStory] = []
        fragments: list[UnresolvedFragment] = []
        if preamble is not None:
            fragments.append(UnresolvedFragment(text=preamble.text, position=preamble.position, reason=PREAMBLE_REASON))
        for block in blocks:
            story = self._structure(block, number=len(stories) + 1)
            if story is None:
                fragments.append(UnresolvedFragment(text=block.text, position=block.position, reason=UNRESOLVED_REASON))
            else:
                stories.append(story)

        if not stories:
            raise StageError(
                "NO_STORIES_FOUND",
                "No se identificó ninguna historia de usuario con el formato de la plantilla.",
                details={"blocks_found": len(blocks), "unresolved_fragments": len(fragments)},
            )
        counts = {status: sum(s.validation_status == status for s in stories) for status in StoryValidationStatus}
        try:
            output = P1Output(
                user_stories=tuple(stories),
                unresolved_fragments=tuple(fragments),
                valid_count=counts[StoryValidationStatus.VALID],
                warning_count=counts[StoryValidationStatus.VALID_WITH_WARNINGS],
                invalid_count=counts[StoryValidationStatus.INVALID],
            )
        except ValidationError as exc:  # no debería ocurrir: la heurística respeta el contrato
            raise StageError("STORY_SEGMENTATION_FAILED", "La segmentación produjo un resultado inconsistente.") from exc
        return output, len(blocks)

    def _split(self, text: str) -> tuple[list[_Block], _Block | None]:
        starts = [match.start() for match in self._delimiter.finditer(text)]
        preamble_text = text[: starts[0]] if starts else text
        preamble = _Block(preamble_text.strip(), position=1) if preamble_text.strip() else None
        offset = 1 if preamble else 0
        bounds = zip(starts, [*starts[1:], len(text)], strict=False)  # sin delimitadores → sin bloques
        blocks = [_Block(text[a:b].rstrip(), position=i + offset) for i, (a, b) in enumerate(bounds, start=1)]
        return blocks, preamble

    def _structure(self, block: _Block, *, number: int) -> UserStory | None:
        code = f"HU-{number:03d}"
        statement = _statement(block.text)
        match = CANONICAL_STATEMENT.match(statement) if statement else None
        if match is None:
            return None
        role, objective, benefit = (_clean(group) for group in match.groups())
        if not role or not objective:
            return None

        issues: list[ValidationIssue] = []
        if not benefit:
            issues.append(
                ValidationIssue(
                    rule_code="MISSING_BENEFIT",
                    severity=IssueSeverity.WARNING,
                    message="Falta la justificación 'para …' en la declaración de la HU.",
                    field="benefit",
                )
            )
        if len(block.text) > self._config.max_story_chars:
            # No se trunca ni se descarta contenido (pipeline_design.md, P1): solo se avisa.
            issues.append(
                ValidationIssue(
                    rule_code="STORY_TOO_LONG",
                    severity=IssueSeverity.WARNING,
                    message=f"La HU supera {self._config.max_story_chars} caracteres.",
                    field="original_text",
                )
            )
        return UserStory(
            id=uuid4(),
            code=code,
            original_text=block.text,
            role=role,
            objective=objective,
            benefit=benefit,
            normalized_text=" ".join(statement.split()),
            validation_status=StoryValidationStatus.VALID_WITH_WARNINGS if issues else StoryValidationStatus.VALID,
            issues=tuple(issues),
            position=number,
            content_sections=_sections(block.text, code),
        )

    @staticmethod
    def _warnings(output: P1Output) -> tuple[StageWarning, ...]:
        warnings: list[StageWarning] = []
        if output.unresolved_fragments:
            warnings.append(
                StageWarning(
                    code="UNRESOLVED_FRAGMENTS",
                    message=f"{len(output.unresolved_fragments)} bloque(s) no se identificaron como HU.",
                    details={"positions": [fragment.position for fragment in output.unresolved_fragments]},
                )
            )
        flagged = [story for story in output.user_stories if story.issues]
        if flagged:
            warnings.append(
                StageWarning(
                    code="STORIES_WITH_WARNINGS",
                    message=f"{len(flagged)} HU tienen advertencias de estructura.",
                    details={story.code: [issue.rule_code for issue in story.issues] for story in flagged},
                )
            )
        return tuple(warnings)


def _statement(block_text: str) -> str:
    """Primer párrafo no vacío tras el encabezado `##` (hasta línea en blanco o `###`).

    Se admiten varias líneas: la extracción de PDF/DOCX puede partir la declaración.
    """
    lines = block_text.split("\n")[1:]
    paragraph: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if paragraph:
                break
            continue
        if stripped.startswith("#"):
            break
        paragraph.append(stripped)
    return " ".join(paragraph)


def _sections(block_text: str, code: str) -> tuple[StorySection, ...]:
    headers = list(SECTION_HEADER.finditer(block_text))
    sections: list[StorySection] = []
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(block_text)
        raw = block_text[header.end() : end]
        body = raw.strip()
        if not body:
            continue
        start = header.end() + raw.index(body)
        sections.append(
            StorySection(
                kind=_section_kind(header.group(1)),
                text=body,
                source_span=SourceSpan(user_story_code=code, start=start, end=start + len(body)),
            )
        )
    return tuple(sections)


def _section_kind(title: str) -> str:
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii").lower()
    words = [word for word in re.split(r"[^a-z0-9]+", ascii_title) if word and word not in _SECTION_STOPWORDS]
    return "_".join(words) or "seccion"


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split()).strip(" ,.;")
    return cleaned or None


class NormalizeStubStage(StubStage):
    """P1 simulada (Fase 1). Se usa con `PIPELINE_STAGES=stub` y en tests del orquestador."""

    key: ClassVar[StageKey] = StageKey.P1

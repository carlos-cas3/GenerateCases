"""P1 real (camino B: heurística sin LLM) con extractor y storage fakes."""

from uuid import UUID, uuid4

import pytest

from ai_service.clients.extractor_fake import FakeDocumentExtractor
from ai_service.core.errors import DocumentExtractionError, InvalidReferenceError
from ai_service.pipeline.context import PipelineConfiguration, PipelineContext
from ai_service.pipeline.contracts.common import FileType, StoryValidationStatus
from ai_service.pipeline.contracts.p1 import P1Config
from ai_service.pipeline.stages import NormalizeStage, StageError
from ai_service.repositories.in_memory import InMemoryDocumentsRepository, InMemoryPipelineResultsRepository, InMemoryStore
from tests.conftest import DOCUMENT_ID, DOCUMENT_NAME
from tests.factories import FakeDocumentStorage

STORAGE_PATH = f"{DOCUMENT_ID}/{DOCUMENT_NAME}"

DOCUMENT = """Documento de requisitos — Release 1
Versión 2.

## Exportar reporte de ventas
Como administrador, quiero exportar el reporte de ventas mensual, para revisar el rendimiento del equipo.

### Criterios de aceptación
- El reporte se genera en formato PDF y CSV.
- Solo el administrador puede exportarlo.

### Reglas de negocio
- El reporte incluye las ventas del mes en curso por defecto.

### Restricciones
- El archivo no puede superar 10 MB.

## Iniciar sesión
Como usuario registrado, quiero iniciar sesión con mi correo.

## Notas de la reunión
Se habló del presupuesto y de las vacaciones.

## Comparar precios
Como cliente,
quiero comparar precios entre tiendas para elegir la oferta más barata.
"""


class FailingResults(InMemoryPipelineResultsRepository):
    async def persist_p1_user_stories(self, generation_id, payload):
        raise InvalidReferenceError()


def _config(**overrides) -> P1Config:
    values = {"rules_version": "v1", "story_delimiter_pattern": r"^##\s+.+$", "max_story_chars": 5000, **overrides}
    return P1Config(**values)


def _context() -> PipelineContext:
    return PipelineContext(
        generation_id=uuid4(),
        document_id=DOCUMENT_ID,
        configuration=PipelineConfiguration(clustering_enabled=True, method_type="llm_pipeline"),
    )


@pytest.fixture
def storage() -> FakeDocumentStorage:
    return FakeDocumentStorage(objects={STORAGE_PATH: b"bytes del documento"})


@pytest.fixture
def results(store: InMemoryStore) -> InMemoryPipelineResultsRepository:
    return InMemoryPipelineResultsRepository(store)


def _stage(store, storage, results, extractor, **config) -> NormalizeStage:
    return NormalizeStage(
        documents=InMemoryDocumentsRepository(store),
        storage=storage,
        extractor=extractor,
        results=results,
        config=_config(**config),
    )


async def test_happy_path_structures_template_blocks(store, storage, results) -> None:
    extractor = FakeDocumentExtractor([DOCUMENT])
    context = _context()

    result = await _stage(store, storage, results, extractor).run(context)

    assert extractor.calls == [(b"bytes del documento", FileType.TXT)]
    output = context.p1_output
    assert [s.code for s in output.user_stories] == ["HU-001", "HU-002", "HU-003"]
    assert [s.position for s in output.user_stories] == [1, 2, 3]

    export, login, compare = output.user_stories
    assert (export.role, export.objective, export.benefit) == (
        "administrador", "exportar el reporte de ventas mensual", "revisar el rendimiento del equipo",
    )
    assert export.validation_status == StoryValidationStatus.VALID and export.issues == ()
    assert export.original_text.startswith("## Exportar reporte de ventas")
    assert [(s.kind, s.text) for s in export.content_sections] == [
        ("criterios_aceptacion", "- El reporte se genera en formato PDF y CSV.\n- Solo el administrador puede exportarlo."),
        ("reglas_negocio", "- El reporte incluye las ventas del mes en curso por defecto."),
        ("restricciones", "- El archivo no puede superar 10 MB."),
    ]
    for section in export.content_sections:  # los spans apuntan al texto literal de la HU
        span = section.source_span
        assert export.original_text[span.start : span.end] == section.text

    assert (login.role, login.objective, login.benefit) == ("usuario registrado", "iniciar sesión con mi correo", None)
    assert login.validation_status == StoryValidationStatus.VALID_WITH_WARNINGS
    assert [i.rule_code for i in login.issues] == ["MISSING_BENEFIT"]

    # Declaración partida en dos líneas y "comparar" no se confunde con "para".
    assert (compare.role, compare.objective, compare.benefit) == (
        "cliente", "comparar precios entre tiendas", "elegir la oferta más barata",
    )

    assert [(f.position, f.reason) for f in output.unresolved_fragments] == [
        (1, "texto previo a la primera HU"),
        (4, "no coincide con la plantilla de HU"),
    ]
    assert output.unresolved_fragments[1].text.startswith("## Notas de la reunión")
    assert (output.valid_count, output.warning_count, output.invalid_count) == (2, 1, 0)

    assert result.llm_runs == ()  # P1 no llama al LLM
    assert result.skip_remaining is False
    assert result.runtime_info["blocks_found"] == 4
    assert result.runtime_info["stories_identified"] == 3
    assert result.runtime_info["stories_unresolved"] == 2
    assert result.runtime_info["rules_version"] == "v1"
    assert [w.code for w in result.warnings] == ["UNRESOLVED_FRAGMENTS", "STORIES_WITH_WARNINGS"]
    assert result.warnings[1].details == {"HU-002": ["MISSING_BENEFIT"]}


@pytest.mark.parametrize(
    ("rules_version", "expected"),
    [
        (
            "v1",
            (
                ("poder redactar recetas", "pacientes"),
                ("que el sistema sea accesible", "los usuarios con permiso, para que no se filtren datos"),
            ),
        ),
        (
            "v2",
            (
                ("poder redactar recetas para pacientes", None),
                ("que el sistema sea accesible para los usuarios con permiso", "que no se filtren datos"),
            ),
        ),
        (
            "v3",
            (
                ("poder redactar recetas para pacientes", None),
                ("que el sistema sea accesible para los usuarios con permiso", "no se filtren datos"),
            ),
        ),
    ],
)
async def test_rules_version_selects_statement_parser(
    store, storage, results, rules_version: str, expected: tuple
) -> None:
    text = (
        "## Recetas\n"
        "Como médico, quiero poder redactar recetas para pacientes.\n\n"
        "## Acceso\n"
        "Como administrador, quiero que el sistema sea accesible para los usuarios con permiso, "
        "para que no se filtren datos.\n"
    )
    context = _context()

    result = await _stage(
        store, storage, results, FakeDocumentExtractor([text]), rules_version=rules_version
    ).run(context)

    assert result.runtime_info["rules_version"] == rules_version
    assert [(s.objective, s.benefit) for s in context.p1_output.user_stories] == list(expected)


async def test_v2_detects_benefit_without_comma_before_infinitive(store, storage, results) -> None:
    text = "## Análisis\nComo analista, quiero datos clínicos para poder analizarlos.\n"
    context = _context()

    await _stage(store, storage, results, FakeDocumentExtractor([text]), rules_version="v2").run(context)

    story = context.p1_output.user_stories[0]
    assert (story.objective, story.benefit) == ("datos clínicos", "poder analizarlos")


V3_DOCUMENT = """## Publicaciones
Como miembro de la facultad, quiero recopilar mis publicaciones en un único punto de acceso, de modo que pueda elevar el perfil de mi trabajo.

## Suscriptores
Como administrador de DB / IR, quiero ver la lista de suscriptores para un informe específico con el fin de investigar las quejas de informes faltantes.

## Datos centrales
Como administrador del sistema, quiero que todos los datos se almacenen en una base de datos central, para que haya menos discrepancias entre los departamentos.

## Estrellato
Como miembro de la facultad de Cornell, quiero que los elementos que he depositado aparezcan en los primeros lugares de Google, porque ese es mi boleto al estrellato.

## Filtros
Como analista, quiero filtrar datos, de modo que pueda revisarlos para corregir errores.
"""


async def test_v3_fills_marker_fields_and_runtime_counts(store, storage, results) -> None:
    context = _context()

    result = await _stage(store, storage, results, FakeDocumentExtractor([V3_DOCUMENT]), rules_version="v3").run(context)

    stories = context.p1_output.user_stories
    assert [(s.objective, s.benefit, s.benefit_marker, s.benefit_strength, s.other_markers) for s in stories] == [
        (
            "recopilar mis publicaciones en un único punto de acceso",
            "pueda elevar el perfil de mi trabajo", "de modo que", "weak", (),
        ),
        (
            "ver la lista de suscriptores para un informe específico",
            "investigar las quejas de informes faltantes", "con el fin de", "strong", (),
        ),
        (
            "que todos los datos se almacenen en una base de datos central",
            "haya menos discrepancias entre los departamentos", "para que", "strong", (),
        ),
        (  # nivel 5 ("porque") desactivado por defecto dentro de v3
            "que los elementos que he depositado aparezcan en los primeros lugares de Google, "
            "porque ese es mi boleto al estrellato",
            None, None, None, (),
        ),
        ("filtrar datos, de modo que pueda revisarlos", "corregir errores", "para", "weak", ("de modo que",)),
    ]
    assert [i.rule_code for i in stories[3].issues] == ["MISSING_BENEFIT"]

    info = result.runtime_info
    assert info["rules_version"] == "v3"
    assert info["benefit_marker_counts"] == {"con el fin de": 1, "de modo que": 1, "para": 1, "para que": 1}
    assert info["benefit_strength_counts"] == {"none": 1, "strong": 2, "weak": 2}
    assert info["discarded_marker_counts"] == {"de modo que": 1}

    # Los campos nuevos no se persisten: el payload de la RPC conserva las mismas claves.
    payload = context.p1_output.to_rpc_payload()
    assert {tuple(sorted(row)) for row in payload} == {
        ("action", "code", "goal", "id", "original_text", "position", "role", "validation_status"),
    }


@pytest.mark.parametrize("rules_version", ["v1", "v2"])
async def test_legacy_versions_report_no_markers(store, storage, results, rules_version: str) -> None:
    context = _context()

    result = await _stage(store, storage, results, FakeDocumentExtractor([DOCUMENT]), rules_version=rules_version).run(
        context
    )

    assert all(s.benefit_marker is None and s.other_markers == () for s in context.p1_output.user_stories)
    assert result.runtime_info["benefit_marker_counts"] == {}
    assert result.runtime_info["benefit_strength_counts"] == {"none": 3}
    assert result.runtime_info["discarded_marker_counts"] == {}


def test_unknown_rules_version_is_rejected_by_stage(store, storage, results) -> None:
    with pytest.raises(ValueError, match="P1_RULES_VERSION"):
        _stage(store, storage, results, FakeDocumentExtractor([DOCUMENT]), rules_version="v9")


async def test_persists_only_user_stories_with_rpc_payload(store, storage, results) -> None:
    context = _context()
    await _stage(store, storage, results, FakeDocumentExtractor([DOCUMENT])).run(context)

    assert results.calls == [("persist_p1_user_stories", context.generation_id)]
    rows = store.user_stories[context.generation_id]
    assert sorted(rows) == ["HU-001", "HU-002", "HU-003"]
    assert rows["HU-001"] == {
        "id": str(context.p1_output.user_stories[0].id),
        "code": "HU-001",
        "position": 1,
        "original_text": context.p1_output.user_stories[0].original_text,
        "role": "administrador",
        "action": "exportar el reporte de ventas mensual",  # objective → action (D-02)
        "goal": "revisar el rendimiento del equipo",  # benefit → goal (D-02)
        "validation_status": "valid",
    }


async def test_long_story_gets_warning_without_truncation(store, storage, results) -> None:
    text = "## Larga\nComo usuario, quiero ver todo, para decidir.\n\n" + "x" * 200
    context = _context()
    await _stage(store, storage, results, FakeDocumentExtractor([text]), max_story_chars=100).run(context)

    story = context.p1_output.user_stories[0]
    assert story.original_text == text
    assert story.validation_status == StoryValidationStatus.VALID_WITH_WARNINGS
    assert [i.rule_code for i in story.issues] == ["STORY_TOO_LONG"]


async def test_crlf_text_from_extractor_is_normalized(store, storage, results) -> None:
    text = "## A\r\nComo usuario, quiero entrar, para trabajar.\r\n\r\n### Criterios\r\n- Rápido\r\n"
    context = _context()
    await _stage(store, storage, results, FakeDocumentExtractor([text])).run(context)

    story = context.p1_output.user_stories[0]
    assert story.benefit == "trabajar"
    assert [(s.kind, s.text) for s in story.content_sections] == [("criterios", "- Rápido")]


@pytest.mark.parametrize("text", ["", "   \n\t  "])
async def test_empty_document(store, storage, results, text: str) -> None:
    with pytest.raises(StageError) as info:
        await _stage(store, storage, results, FakeDocumentExtractor([text])).run(_context())
    assert info.value.code == "EMPTY_DOCUMENT"
    assert results.calls == []


@pytest.mark.parametrize(
    "text",
    [
        "Texto sin ningún delimitador de historia.",
        "## Solo títulos\nAlgo que no es una HU.\n\n## Otro\nQuiero cosas sin rol.",
    ],
)
async def test_no_stories_found_when_everything_is_unresolved(store, storage, results, text: str) -> None:
    context = _context()
    with pytest.raises(StageError) as info:
        await _stage(store, storage, results, FakeDocumentExtractor([text])).run(context)
    assert info.value.code == "NO_STORIES_FOUND"
    assert context.p1_output is None
    assert results.calls == []


async def test_extractor_failure_is_document_unreadable(store, storage, results) -> None:
    extractor = FakeDocumentExtractor([DocumentExtractionError()])
    with pytest.raises(StageError) as info:
        await _stage(store, storage, results, extractor).run(_context())
    assert info.value.code == "DOCUMENT_UNREADABLE"


async def test_missing_storage_object_is_document_unreadable(store, results) -> None:
    extractor = FakeDocumentExtractor([DOCUMENT])
    with pytest.raises(StageError) as info:
        await _stage(store, FakeDocumentStorage(), results, extractor).run(_context())
    assert info.value.code == "DOCUMENT_UNREADABLE"
    assert extractor.calls == []


async def test_missing_document_record_is_document_unreadable(store, storage, results) -> None:
    context = _context()
    context.document_id = UUID(int=0)
    with pytest.raises(StageError) as info:
        await _stage(store, storage, results, FakeDocumentExtractor([DOCUMENT])).run(context)
    assert info.value.code == "DOCUMENT_UNREADABLE"


async def test_persistence_error_becomes_stage_error(store, storage) -> None:
    context = _context()
    with pytest.raises(StageError) as info:
        await _stage(store, storage, FailingResults(store), FakeDocumentExtractor([DOCUMENT])).run(context)
    assert info.value.code == "INVALID_STORY_REFERENCE"
    assert context.p1_output is None


async def test_persist_p1_is_idempotent(store, storage, results) -> None:
    """Reenviar el mismo payload (reintento post-commit) no duplica filas ni cambia ids."""
    context = _context()
    await _stage(store, storage, results, FakeDocumentExtractor([DOCUMENT])).run(context)
    payload = context.p1_output.to_rpc_payload()
    first_ids = {code: row["id"] for code, row in store.user_stories[context.generation_id].items()}

    await results.persist_p1_user_stories(context.generation_id, payload)

    rows = store.user_stories[context.generation_id]
    assert len(rows) == 3
    assert {code: row["id"] for code, row in rows.items()} == first_ids

"""Parser puro de la declaración canónica (`p1_statement`), en especial P1 v3 (`issue_v3_p1.md` §6.1, §6.3)."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from ai_service.pipeline.contracts.common import StoryValidationStatus
from ai_service.pipeline.contracts.p1 import UserStory
from ai_service.pipeline.stages.p1_statement import (
    SUPPORTED_RULES_VERSIONS,
    MarkerCandidate,
    ParsedStatement,
    find_candidates,
    parse_statement,
)

PREFIX = "Como usuario, quiero exportar los datos"


def _v3(statement: str, **kwargs) -> ParsedStatement:
    parsed = parse_statement(statement, "v3", **kwargs)
    assert parsed is not None
    return parsed


def test_supported_versions() -> None:
    assert SUPPORTED_RULES_VERSIONS == {"v1", "v2", "v3"}


def test_unknown_version_is_rejected() -> None:
    with pytest.raises(ValueError, match="P1_RULES_VERSION"):
        parse_statement("Como usuario, quiero entrar", "v9")


@pytest.mark.parametrize(
    ("tail", "objective", "benefit", "marker", "strength"),
    [
        (", para que haya menos discrepancias", "exportar los datos", "haya menos discrepancias", "para que", "strong"),
        (
            " con el fin de que otro equipo los analice",
            "exportar los datos", "otro equipo los analice", "con el fin de que", "strong",
        ),
        (" con el objetivo de evitar errores", "exportar los datos", "evitar errores", "con el objetivo de", "strong"),
        (
            " con la finalidad de que se registre",
            "exportar los datos", "se registre", "con la finalidad de que", "strong",
        ),
        (
            " a fin de que se reduzcan los tiempos",
            "exportar los datos", "se reduzcan los tiempos", "a fin de que", "strong",
        ),
        (" para no perder datos", "exportar los datos", "no perder datos", "para", "weak"),
        (" para usarlas en Excel", "exportar los datos", "usarlas en Excel", "para", "weak"),
        (" para revisarlo más tarde", "exportar los datos", "revisarlo más tarde", "para", "weak"),
        (" para enviarnos el resumen", "exportar los datos", "enviarnos el resumen", "para", "weak"),
        (
            ", de modo que pueda elevar el perfil de mi trabajo",
            "exportar los datos", "pueda elevar el perfil de mi trabajo", "de modo que", "weak",
        ),
        (
            ", de manera que se garantice la seguridad",
            "exportar los datos", "se garantice la seguridad", "de manera que", "weak",
        ),
        (
            ", de forma que se procese correctamente",
            "exportar los datos", "se procese correctamente", "de forma que", "weak",
        ),
    ],
)
def test_v3_lexicon(tail: str, objective: str, benefit: str, marker: str, strength: str) -> None:
    parsed = _v3(PREFIX + tail)
    assert (parsed.role, parsed.objective, parsed.benefit) == ("usuario", objective, benefit)
    assert (parsed.benefit_marker, parsed.benefit_strength, parsed.other_markers) == (marker, strength, ())


@pytest.mark.parametrize(
    "statement",
    [
        "Como usuario, quiero guardar el archivo para el administrador",
        "Como usuario, quiero guardar el archivo para los usuarios",
        "Como usuario, quiero registrar gastos con el fin de lucro",
        "Como usuario, quiero cerrar la cuenta a fin de cuentas",
        "Como usuario, quiero ver el menú de modo claro",
        "Como usuario, quiero ver el menú de manera ordenada",
        "Como paciente, quiero poder renovar mis recetas de medicamentos",  # US27-H6, sin marcador
    ],
)
def test_v3_without_benefit(statement: str) -> None:
    parsed = _v3(statement)
    expected_objective = statement.split("quiero ", 1)[1]
    assert parsed.objective == expected_objective
    assert (parsed.benefit, parsed.benefit_marker, parsed.benefit_strength, parsed.other_markers) == (
        None, None, None, (),
    )


def test_porque_is_disabled_by_default() -> None:
    statement = (
        "Como miembro de la facultad de Cornell, quiero que los elementos que he depositado aparezcan "
        "en los primeros lugares de Google, porque ese es mi boleto al estrellato"
    )
    disabled = _v3(statement)
    assert (disabled.benefit, disabled.benefit_marker) == (None, None)

    enabled = _v3(statement, enable_porque=True)  # US21-H32
    assert enabled.objective == "que los elementos que he depositado aparezcan en los primeros lugares de Google"
    assert enabled.benefit == "ese es mi boleto al estrellato"
    assert (enabled.benefit_marker, enabled.benefit_strength) == ("porque", "weak")


@pytest.mark.parametrize(
    ("statement", "objective", "benefit", "marker", "strength"),
    [
        (
            "Como miembro de la facultad, quiero recopilar mis publicaciones en un único punto de acceso, "
            "de modo que pueda elevar el perfil de mi trabajo",
            "recopilar mis publicaciones en un único punto de acceso",
            "pueda elevar el perfil de mi trabajo", "de modo que", "weak",
        ),  # US21-H11
        (
            "Como administrador de DB / IR, quiero ver la lista de suscriptores para un informe específico "
            "con el fin de investigar las quejas de informes faltantes",
            "ver la lista de suscriptores para un informe específico",
            "investigar las quejas de informes faltantes", "con el fin de", "strong",
        ),  # US21-H22
        (
            "Como administrador del sistema, quiero que todos los datos se almacenen en una base de datos central, "
            "para que haya menos discrepancias entre los departamentos",
            "que todos los datos se almacenen en una base de datos central",
            "haya menos discrepancias entre los departamentos", "para que", "strong",
        ),  # US24-H6
        (
            "Como médico, quiero que las enfermeras solo tengan un control parcial sobre los registros médicos "
            "del paciente, para que no eliminen accidentalmente datos importantes",
            "que las enfermeras solo tengan un control parcial sobre los registros médicos del paciente",
            "no eliminen accidentalmente datos importantes", "para que", "strong",
        ),  # US27-H17
    ],
)
def test_v3_corpus_examples(statement: str, objective: str, benefit: str, marker: str, strength: str) -> None:
    parsed = _v3(statement)
    assert (parsed.objective, parsed.benefit, parsed.benefit_marker, parsed.benefit_strength) == (
        objective, benefit, marker, strength,
    )


def test_same_level_last_wins() -> None:
    parsed = _v3("Como usuario, quiero filtrar datos para revisar errores para corregirlos")
    assert (parsed.objective, parsed.benefit) == ("filtrar datos para revisar errores", "corregirlos")
    assert (parsed.benefit_marker, parsed.other_markers) == ("para", ("para",))


def test_level_1_beats_later_level_3() -> None:
    parsed = _v3("Como usuario, quiero exportar, para que el equipo lo vea, para revisarlo luego")
    assert (parsed.objective, parsed.benefit) == ("exportar", "el equipo lo vea, para revisarlo luego")
    assert (parsed.benefit_marker, parsed.other_markers) == ("para que", ("para",))


def test_level_3_beats_earlier_level_4() -> None:
    parsed = _v3("Como usuario, quiero exportar, de modo que pueda ver los datos para revisarlos")
    assert (parsed.objective, parsed.benefit) == ("exportar, de modo que pueda ver los datos", "revisarlos")
    assert (parsed.benefit_marker, parsed.other_markers) == ("para", ("de modo que",))


def test_level_3_beats_porque() -> None:
    parsed = _v3("Como usuario, quiero exportar porque lo pide auditoría para cumplir la norma", enable_porque=True)
    assert (parsed.objective, parsed.benefit) == ("exportar porque lo pide auditoría", "cumplir la norma")
    assert (parsed.benefit_marker, parsed.other_markers) == ("para", ("porque",))


def test_overlapping_candidates_are_dropped_from_other_markers() -> None:
    from ai_service.pipeline.stages import p1_statement

    chosen = MarkerCandidate(1, "strong", "para que", 10, 18)
    overlapped = MarkerCandidate(3, "weak", "para", 10, 14)
    other = MarkerCandidate(3, "weak", "para", 30, 34)
    candidates = [chosen, overlapped, other]

    assert p1_statement.select_candidate(candidates) is chosen
    assert p1_statement._overlaps(chosen, overlapped)
    assert not p1_statement._overlaps(chosen, other)


def test_marker_without_following_text_is_not_a_candidate() -> None:
    assert find_candidates("exportar los datos para que") == []
    parsed = _v3("Como usuario, quiero exportar los datos, para que.")
    assert (parsed.objective, parsed.benefit, parsed.benefit_marker) == ("exportar los datos, para que", None, None)


def test_case_accents_and_whitespace() -> None:
    parsed = _v3("COMO Usuario,  QUIERO   exportar los datos,\n  Con  El   Fin\nDe   Que   Él lo revise.")
    assert (parsed.role, parsed.objective, parsed.benefit) == ("Usuario", "exportar los datos", "Él lo revise")
    assert (parsed.benefit_marker, parsed.benefit_strength) == ("con el fin de que", "strong")

    accented = _v3("Como usuario, quiero exportar PARA Auditar más rápido")
    assert (accented.benefit, accented.benefit_marker) == ("Auditar más rápido", "para")


def test_final_period_is_removed() -> None:
    with_benefit = _v3("Como usuario, quiero exportar los datos, para revisarlos.")
    assert (with_benefit.objective, with_benefit.benefit) == ("exportar los datos", "revisarlos")
    without_benefit = _v3("Como usuario, quiero exportar los datos.")
    assert (without_benefit.objective, without_benefit.benefit) == ("exportar los datos", None)


@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
def test_non_matching_statement_returns_none(version: str) -> None:
    assert parse_statement("Quiero cosas sin rol.", version) is None


@pytest.mark.parametrize("version", ["v1", "v2"])
def test_legacy_versions_do_not_report_markers(version: str) -> None:
    parsed = parse_statement("Como usuario, quiero exportar, para que lo vea el equipo.", version)
    assert parsed is not None
    assert parsed.benefit == "que lo vea el equipo"  # v1/v2 conservan el "que" inicial
    assert (parsed.benefit_marker, parsed.benefit_strength, parsed.other_markers) == (None, None, ())


# --------------------------------------------------------------- contrato (§6.3)
def _story(**overrides) -> UserStory:
    values = {
        "id": uuid4(),
        "code": "HU-001",
        "original_text": "## A\nComo usuario, quiero entrar, para trabajar.",
        "role": "usuario",
        "objective": "entrar",
        "benefit": "trabajar",
        "validation_status": StoryValidationStatus.VALID,
        "position": 1,
        **overrides,
    }
    return UserStory(**values)


def test_contract_accepts_consistent_marker_fields() -> None:
    story = _story(benefit_marker="para", benefit_strength="weak", other_markers=["de modo que", "de modo que"])
    assert story.other_markers == ("de modo que", "de modo que")
    assert isinstance(story.other_markers, tuple)


@pytest.mark.parametrize(
    "overrides",
    [
        {"benefit_marker": "para", "benefit_strength": "weak", "benefit": None},
        {"benefit_marker": "para", "benefit_strength": None},
        {"benefit_marker": None, "benefit_strength": "strong"},
        {"benefit_marker": "para", "benefit_strength": "medium"},
    ],
)
def test_contract_rejects_inconsistent_marker_fields(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        _story(**overrides)

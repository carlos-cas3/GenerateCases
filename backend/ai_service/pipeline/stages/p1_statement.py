"""Parser puro de la declaración canónica de una HU ("Como …, quiero …, para …").

Sin base de datos, sin LLM y sin `PipelineContext`: invocable directamente para evaluación
offline (`issue_v3_p1.md`). Versionado por `P1Config.rules_version`:

- v1: parte en el primer "para" (legado; corta complementos como "para pacientes").
- v2: un "para" solo introduce el beneficio si le sigue "que" o un infinitivo, y `\\b` antes
  de "para" evita partir palabras que lo contienen ("comparar", "separar").
- v3: léxico de marcadores de fin en cinco niveles con prioridad (`issue_v3_p1.md` §4.1–§4.2);
  registra el marcador elegido, su fuerza y los marcadores descartados. El nivel 5 ("porque")
  está desactivado salvo que se pida explícitamente con `enable_porque=True`.
"""

import re
from dataclasses import dataclass
from typing import Literal

BenefitStrength = Literal["strong", "weak"]

# v1/v2: regex de un solo pase que captura (role, objective, benefit). Lógica movida sin cambios
# desde `p1_normalize.py`.
_LEGACY_RULES: dict[str, re.Pattern[str]] = {
    "v1": re.compile(
        r"^Como\s+(.+?),\s+quiero\s+(.+?)(?:,?\s*\bpara\s+(.+?))?\s*\.?\s*$",
        re.IGNORECASE | re.DOTALL,
    ),
    "v2": re.compile(
        r"^Como\s+(.+?),\s+quiero\s+(.+?)"
        r"(?:,?\s*\bpara\s+(?=que\b|(?:no\s+)?[a-záéíóúüñ]+(?:ar|er|ir)\b)(.+?))?"
        r"\s*\.?\s*$",
        re.IGNORECASE | re.DOTALL,
    ),
}

# v3: la cabecera separa rol y resto; el beneficio se busca después en el resto.
_V3_HEADER = re.compile(r"^Como\s+(.+?),\s+quiero\s+(.+)$", re.IGNORECASE | re.DOTALL)

# Infinitivo con `no` opcional y enclítico opcional ("no perder", "usarlas", "enviarnos").
_INFINITIVE = r"(?:no\s+)?[a-záéíóúüñ]+(?:ar|er|ir)(?:se|lo|la|le|me|te|nos|los|las)?\b"


@dataclass(frozen=True, slots=True)
class _MarkerRule:
    level: int
    strength: BenefitStrength
    pattern: re.Pattern[str]


# Cada patrón cubre exactamente el marcador que se consume; el beneficio empieza en `match.end()`.
_V3_MARKERS: tuple[_MarkerRule, ...] = (
    _MarkerRule(1, "strong", re.compile(r"\bpara\s+que\b", re.IGNORECASE)),
    # Nivel 2: conector + "de" + ("que" | infinitivo). La guarda evita "con el fin de lucro".
    _MarkerRule(
        2,
        "strong",
        re.compile(
            r"\b(?:con\s+el\s+(?:fin|objetivo)|con\s+la\s+finalidad|a\s+fin)\s+de"
            rf"(?:\s+que\b|(?=\s+{_INFINITIVE}))",
            re.IGNORECASE,
        ),
    ),
    # Nivel 3: solo consume "para"; no captura complementos nominales ("para el administrador").
    _MarkerRule(3, "weak", re.compile(rf"\bpara(?=\s+{_INFINITIVE})", re.IGNORECASE)),
    _MarkerRule(4, "weak", re.compile(r"\bde\s+(?:modo|manera|forma)\s+que\b", re.IGNORECASE)),
    _MarkerRule(5, "weak", re.compile(r"\bporque\b", re.IGNORECASE)),
)
PORQUE_LEVEL = 5

SUPPORTED_RULES_VERSIONS = frozenset({*_LEGACY_RULES, "v3"})


@dataclass(frozen=True, slots=True)
class ParsedStatement:
    role: str | None
    objective: str | None
    benefit: str | None
    benefit_marker: str | None = None
    benefit_strength: BenefitStrength | None = None
    other_markers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MarkerCandidate:
    level: int
    strength: BenefitStrength
    label: str  # marcador normalizado: minúsculas y espacios colapsados
    start: int  # inicio del marcador dentro del resto
    end: int  # fin del marcador (el beneficio empieza aquí)


def parse_statement(statement: str, rules_version: str, *, enable_porque: bool = False) -> ParsedStatement | None:
    """Estructura una declaración canónica. `None` si no encaja con la plantilla o falta rol/objetivo.

    `enable_porque` activa el nivel 5 de v3 (desactivado por defecto, `issue_v3_p1.md` §8);
    v1/v2 lo ignoran.
    """
    if rules_version == "v3":
        parsed = _parse_v3(statement, enable_porque=enable_porque)
    elif rules_version in _LEGACY_RULES:
        parsed = _parse_legacy(statement, _LEGACY_RULES[rules_version])
    else:
        raise ValueError(f"P1_RULES_VERSION no soportada: {rules_version}")
    if parsed is None or not parsed.role or not parsed.objective:
        return None
    return parsed


def _parse_legacy(statement: str, rule: re.Pattern[str]) -> ParsedStatement | None:
    match = rule.match(statement)
    if match is None:
        return None
    role, objective, benefit = (clean(group) for group in match.groups())
    return ParsedStatement(role=role, objective=objective, benefit=benefit)


def _parse_v3(statement: str, *, enable_porque: bool) -> ParsedStatement | None:
    match = _V3_HEADER.match(statement)
    if match is None:
        return None
    role, rest = clean(match.group(1)), match.group(2)
    candidates = find_candidates(rest, enable_porque=enable_porque)
    chosen = select_candidate(candidates)
    if chosen is None:
        return ParsedStatement(role=role, objective=clean(rest), benefit=None)
    others = tuple(c.label for c in candidates if c is not chosen and not _overlaps(c, chosen))
    return ParsedStatement(
        role=role,
        objective=clean(rest[: chosen.start]),
        benefit=clean(rest[chosen.end :]),
        benefit_marker=chosen.label,
        benefit_strength=chosen.strength,
        other_markers=others,
    )


def find_candidates(rest: str, *, enable_porque: bool = False) -> list[MarkerCandidate]:
    """Candidatos válidos en orden de aparición (§4.2 pasos 1–2).

    Se descartan los que no dejan texto útil ni antes (objetivo) ni después (beneficio).
    """
    candidates: list[MarkerCandidate] = []
    for rule in _V3_MARKERS:
        if rule.level == PORQUE_LEVEL and not enable_porque:
            continue
        for found in rule.pattern.finditer(rest):
            if clean(rest[found.end() :]) is None or clean(rest[: found.start()]) is None:
                continue
            label = " ".join(found.group(0).lower().split())
            candidates.append(MarkerCandidate(rule.level, rule.strength, label, found.start(), found.end()))
    candidates.sort(key=lambda c: (c.start, c.level))
    return candidates


def select_candidate(candidates: list[MarkerCandidate]) -> MarkerCandidate | None:
    """Gana el nivel más bajo; a igual nivel, el último en aparecer (§4.2 paso 3)."""
    if not candidates:
        return None
    return min(candidates, key=lambda c: (c.level, -c.start))


def _overlaps(a: MarkerCandidate, b: MarkerCandidate) -> bool:
    return a.start < b.end and b.start < a.end


def clean(value: str | None) -> str | None:
    """Colapsa espacios y quita separadores (`,`, `.`, `;`) en los extremos; `None` si queda vacío."""
    if value is None:
        return None
    cleaned = " ".join(value.split()).strip(" ,.;")
    return cleaned or None

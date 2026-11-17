"""Saneo de la salida cruda del LLM, común a P2 y P6 (D-OLLAMA-4, `docs/llm_ollama_context.md`)."""

import json
import re

RAW_LOG_LIMIT = 2000  # caracteres de la salida cruda del LLM que se registran ante una respuesta inválida
_CODE_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)


def strip_code_fence(text: str) -> str:
    """Quita un bloque ```json … ``` envolvente, habitual en respuestas de LLM."""
    match = _CODE_FENCE.match(text)
    return match.group(1) if match else text.strip()


def drop_blank_list_items(raw: str) -> str:
    """Quita los strings vacíos de las listas del JSON (`[""]` → `[]`) antes de validar (D-OLLAMA-4).

    Algunos modelos locales rellenan las listas sin datos con `""`, que `NonEmptyStr` rechaza. Es
    un saneo local de la etapa: los contratos compartidos no cambian. Los campos escalares no se
    tocan, y si el texto no es JSON se devuelve igual para que la validación informe el error real.
    """
    try:
        data = json.loads(raw)
    except ValueError:
        return raw
    return json.dumps(_clean(data), ensure_ascii=False)


def _clean(value: object) -> object:
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean(item) for item in value if not (isinstance(item, str) and not item.strip())]
    return value


def filter_requirement_codes(raw: str, target_codes: set[str]) -> str:
    """Filtra de `requirement_codes` los RF que no son objetivo de la unidad antes de validar.

    El LLM puede enlazar RF de contexto aunque el prompt lo prohíba. En vez de rechazar el caso
    entero se eliminan los códigos foráneos. Un caso que queda sin códigos se descarta.
    Si el texto no es JSON se devuelve igual para que la validación informe el error real.
    """
    return filter_requirement_codes_with_stats(raw, target_codes)[0]


def filter_requirement_codes_with_stats(raw: str, target_codes: set[str]) -> tuple[str, list[str], int]:
    """Como `filter_requirement_codes`, y además devuelve los códigos filtrados y los casos descartados.

    Solo actúa sobre `{"test_cases": [{..., "requirement_codes": [...]}, ...]}`; cualquier otra
    forma se devuelve sin tocar. Si no se filtra nada el texto se devuelve tal cual.
    """
    try:
        data = json.loads(raw)
    except ValueError:
        return raw, [], 0
    if not isinstance(data, dict) or not isinstance(data.get("test_cases"), list):
        return raw, [], 0
    filtered: list[str] = []
    dropped = 0
    cases: list[object] = []
    for case in data["test_cases"]:
        codes = case.get("requirement_codes") if isinstance(case, dict) else None
        if not isinstance(codes, list):
            cases.append(case)
            continue
        kept = [code for code in codes if not isinstance(code, str) or code in target_codes]
        filtered.extend(code for code in codes if isinstance(code, str) and code not in target_codes)
        if codes and not kept:
            dropped += 1
            continue
        cases.append({**case, "requirement_codes": kept})
    if not filtered:
        return raw, [], 0
    data["test_cases"] = cases
    return json.dumps(data, ensure_ascii=False), filtered, dropped


def add_optional(total: int | None, value: int | None) -> int | None:
    """Suma de contadores opcionales del LLM (tokens, latencia); `None` si nunca hubo valor."""
    if value is None:
        return total
    return (total or 0) + value

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


def add_optional(total: int | None, value: int | None) -> int | None:
    """Suma de contadores opcionales del LLM (tokens, latencia); `None` si nunca hubo valor."""
    if value is None:
        return total
    return (total or 0) + value

"""Resolución del prompt de P2 (clasificación de HU + extracción de RF).

A diferencia de P6 (que tiene dos variantes por `UnitStrategy`), P2 usa una única variante
(`p2_requirements`). `prompt_version` identifica la familia/versión del prompt; la etapa lo
carga y lo combina con el lote de HU que va a enviar al LLM.
"""

from dataclasses import dataclass
from pathlib import Path

_PROMPTS_DIR = Path(__file__).with_name("texts")
_P2_TEXT = "p2_requirements.md"


@dataclass(frozen=True, slots=True)
class ResolvedP2Prompt:
    prompt_version: str
    text: str


def _load() -> str:
    return (_PROMPTS_DIR / _P2_TEXT).read_text(encoding="utf-8")


def resolve_p2_prompt(prompt_version: str) -> ResolvedP2Prompt:
    return ResolvedP2Prompt(prompt_version=prompt_version, text=_load())

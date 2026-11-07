"""Resolución de la variante de prompt de P6 (D-38).

`prompt_version` identifica la familia/versión; la variante se elige por
`GenerationContext.strategy`:
- `by_cluster` -> `contexto`
- `by_user_story` -> `contexto_sin_clustering`
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ai_service.pipeline.contracts.common import UnitStrategy

_PROMPTS_DIR = Path(__file__).with_name("texts")


class P6PromptVariant(StrEnum):
    CONTEXT = "contexto"
    CONTEXT_WITHOUT_CLUSTERING = "contexto_sin_clustering"


@dataclass(frozen=True, slots=True)
class ResolvedP6Prompt:
    variant: P6PromptVariant
    prompt_version: str
    text: str


_VARIANT_BY_STRATEGY = {
    UnitStrategy.BY_CLUSTER: P6PromptVariant.CONTEXT,
    UnitStrategy.BY_USER_STORY: P6PromptVariant.CONTEXT_WITHOUT_CLUSTERING,
}


def _load(variant: P6PromptVariant) -> str:
    return (_PROMPTS_DIR / f"{variant.value}.md").read_text(encoding="utf-8")


def resolve_p6_prompt(prompt_version: str, strategy: UnitStrategy) -> ResolvedP6Prompt:
    try:
        variant = _VARIANT_BY_STRATEGY[strategy]
    except KeyError as exc:
        raise ValueError(f"estrategia de contexto no soportada: {strategy}") from exc
    return ResolvedP6Prompt(
        variant=variant,
        prompt_version=f"{variant.value}@{prompt_version}",
        text=_load(variant),
    )

from ai_service.pipeline.contracts.common import UnitStrategy
from ai_service.pipeline.prompts.p6 import P6PromptVariant, resolve_p6_prompt


def test_by_cluster_uses_context_prompt() -> None:
    prompt = resolve_p6_prompt("p6-v1", UnitStrategy.BY_CLUSTER)
    assert prompt.variant is P6PromptVariant.CONTEXT
    assert prompt.prompt_version == "contexto@p6-v1"
    assert prompt.text.strip()


def test_by_user_story_uses_context_without_clustering_prompt() -> None:
    prompt = resolve_p6_prompt("p6-v1", UnitStrategy.BY_USER_STORY)
    assert prompt.variant is P6PromptVariant.CONTEXT_WITHOUT_CLUSTERING
    assert prompt.prompt_version == "contexto_sin_clustering@p6-v1"
    assert prompt.text.strip()


def test_prompt_variants_are_distinct() -> None:
    a = resolve_p6_prompt("p6-v1", UnitStrategy.BY_CLUSTER)
    b = resolve_p6_prompt("p6-v1", UnitStrategy.BY_USER_STORY)
    assert a.text != b.text

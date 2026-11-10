"""Factory del cliente LLM (sección 6 de `architecture_patterns.md`).

Es el único lugar del sistema que decide qué proveedor se usa. Solo la llama
`main.py` (R-FA-5); las etapas reciben el `LlmClient` ya construido (R-DI-2).
Los imports de adaptadores y SDKs son lazy (R-FA-3): solo se carga la librería
del proveedor activo.
"""

from ai_service.clients.llm import LlmClient
from ai_service.config import Settings
from ai_service.core.errors import ConfigurationError

SUPPORTED_PROVIDERS: tuple[str, ...] = ("openai", "anthropic", "ollama")


class LlmClientFactory:
    """Construye el `LlmClient` correcto según `Settings.llm_provider`."""

    @staticmethod
    def create(settings: Settings) -> LlmClient:
        match settings.llm_provider:
            case "openai":
                from openai import AsyncOpenAI

                from ai_service.clients.openai_llm import OpenAILlmClient

                return OpenAILlmClient(
                    AsyncOpenAI(
                        api_key=_require_api_key(settings),
                        base_url=settings.llm_base_url,
                        timeout=settings.llm_timeout_seconds,
                        max_retries=0,  # los reintentos los decide la etapa, no el SDK
                    )
                )
            case "anthropic":
                from anthropic import AsyncAnthropic

                from ai_service.clients.anthropic_llm import AnthropicLlmClient

                return AnthropicLlmClient(
                    AsyncAnthropic(
                        api_key=_require_api_key(settings),
                        base_url=settings.llm_base_url,
                        timeout=settings.llm_timeout_seconds,
                        max_retries=0,
                    )
                )
            case "ollama":
                import httpx

                from ai_service.clients.ollama_llm import OllamaLlmClient

                if not settings.llm_base_url:
                    raise ConfigurationError("LLM_BASE_URL es obligatoria cuando LLM_PROVIDER=ollama.")
                return OllamaLlmClient(
                    httpx.AsyncClient(base_url=settings.llm_base_url, timeout=settings.llm_timeout_seconds)
                )
            case _:
                raise ConfigurationError(
                    f"Proveedor LLM no soportado: {settings.llm_provider!r}. "
                    f"Valores válidos: {', '.join(SUPPORTED_PROVIDERS)}."
                )


def _require_api_key(settings: Settings) -> str:
    if settings.llm_api_key is None:
        raise ConfigurationError(f"LLM_API_KEY es obligatoria cuando LLM_PROVIDER={settings.llm_provider}.")
    return settings.llm_api_key.get_secret_value()

"""Factory del cliente de embeddings (sección 6 de `architecture_patterns.md`, D-EMB-5).

Único lugar que decide qué proveedor de embeddings se usa. Solo la llama `main.py`
(R-FA-5); P3 recibe el `EmbeddingsClient` ya construido (R-DI-2). Imports lazy (R-FA-3).
"""

from ai_service.clients.embeddings import EmbeddingsClient
from ai_service.config import Settings
from ai_service.core.errors import ConfigurationError

SUPPORTED_PROVIDERS: tuple[str, ...] = ("local", "openai")


class EmbeddingsClientFactory:
    """Construye el `EmbeddingsClient` correcto según `Settings.embeddings_provider`."""

    @staticmethod
    def create(settings: Settings) -> EmbeddingsClient:
        match settings.embeddings_provider:
            case "local":
                from sentence_transformers import SentenceTransformer

                from ai_service.clients.local_embeddings import LocalEmbeddingsClient

                return LocalEmbeddingsClient(SentenceTransformer(settings.embeddings_model), settings.embeddings_model)
            case "openai":
                from openai import AsyncOpenAI

                from ai_service.clients.openai_embeddings import OpenAIEmbeddingsClient

                return OpenAIEmbeddingsClient(
                    AsyncOpenAI(
                        api_key=_require_embeddings_api_key(settings),
                        timeout=settings.embeddings_timeout_seconds,
                        max_retries=0,  # los reintentos los decide la etapa, no el SDK
                    )
                )
            case _:
                raise ConfigurationError(
                    f"Proveedor de embeddings no soportado: {settings.embeddings_provider!r}. "
                    f"Valores válidos: {', '.join(SUPPORTED_PROVIDERS)}."
                )


def _require_embeddings_api_key(settings: Settings) -> str:
    if settings.embeddings_api_key is None:
        raise ConfigurationError("EMBEDDINGS_API_KEY es obligatoria cuando EMBEDDINGS_PROVIDER=openai.")
    return settings.embeddings_api_key.get_secret_value()

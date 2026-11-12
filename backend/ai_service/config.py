"""Configuración de la aplicación a partir de variables de entorno."""

import re
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

StageKeyLiteral = Literal["p1", "p2", "p3", "p4", "p5", "p6", "p7"]
LlmProviderLiteral = Literal["openai", "anthropic", "ollama"]
EmbeddingsProviderLiteral = Literal["local", "openai"]
ClusteringAlgorithmLiteral = Literal["hdbscan"]
PipelineStagesLiteral = Literal["real", "stub"]


class Settings(BaseSettings):
    """Variables de entorno del backend. La clave de servicio nunca sale del servidor."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    supabase_url: str | None = None
    supabase_service_role_key: SecretStr | None = None

    # `real`: P1–P4 reales, P5–P7 stubs (Fase 5). `stub`: las 7 simuladas
    # (arranque sin LLM/Supabase de resultados y tests del orquestador).
    pipeline_stages: PipelineStagesLiteral = "real"
    pipeline_stub_delay_seconds: float = Field(default=2.0, ge=0)
    pipeline_stub_fail_at_stage: StageKeyLiteral | None = None
    default_method_type: str = Field(default="llm_pipeline", min_length=1)

    # Subida de documentos: límite por archivo (20 MiB) y bucket privado de Supabase Storage.
    max_upload_size_bytes: int = Field(default=20 * 1024 * 1024, gt=0)
    documents_bucket: str = Field(default="docs_testgen", min_length=1)

    # Orígenes del frontend autorizados por CORS. En `.env`: lista separada por comas.
    # El valor por defecto solo cubre desarrollo local; producción debe definir los suyos.
    frontend_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    # Cliente LLM de P2/P6 (ver docs/llm_client_design.md). La coherencia proveedor ↔
    # credenciales la comprueba `LlmClientFactory` al construir el cliente en el arranque.
    llm_provider: LlmProviderLiteral = "openai"
    llm_api_key: SecretStr | None = None  # obligatoria para openai y anthropic
    llm_base_url: str | None = None  # obligatoria para ollama; opcional (proxy) para el resto
    llm_timeout_seconds: float = Field(default=60.0, gt=0)
    llm_model: str | None = None  # nombre del modelo concreto para P2/P6 (LlmSettings.model)

    # Configuración de P1 (camino B: heurística, sin LLM). Ver plantilla_hu.md (T-F4-02).
    p1_rules_version: str = Field(default="v1", min_length=1)
    p1_language: str = Field(default="es", min_length=1)
    p1_story_delimiter_pattern: str = Field(default=r"^##\s+.+$", min_length=1)
    p1_max_story_chars: int = Field(default=5000, gt=0)

    # Configuración de P2 (LLM en batches). Ver prompt_p2.md (T-F4-03).
    p2_prompt_version: str = Field(default="v1", min_length=1)
    p2_max_stories_per_call: int = Field(default=5, gt=0)
    p2_max_retries: int = Field(default=2, ge=0)

    # Embeddings de P3 y clustering de P4 (ver issue_resolver_embeddings.md). La coherencia
    # proveedor ↔ credenciales la comprueba `EmbeddingsClientFactory` en el arranque.
    embeddings_provider: EmbeddingsProviderLiteral = "local"
    embeddings_model: str = Field(default="all-mpnet-base-v2", min_length=1)
    embeddings_api_key: SecretStr | None = None  # obligatoria para openai
    embeddings_timeout_seconds: float = Field(default=60.0, gt=0)  # solo proveedores remotos
    clustering_algorithm: ClusteringAlgorithmLiteral = "hdbscan"

    # Configuración de P3 (embeddings en lotes). Ver Fase 5 (fase5.md, decisiones 3–5).
    p3_normalize: bool = True
    p3_input_template: str = Field(default="{code}. {description}", min_length=1)
    p3_batch_size: int = Field(default=32, gt=0)
    p3_max_retries: int = Field(default=2, ge=0)  # solo fallos transitorios del proveedor

    # Configuración de P4 (clustering). Pisos mínimos de HDBSCAN, no tamaños forzados (decisión 1).
    p4_metric: str = Field(default="cosine", min_length=1)
    p4_min_cluster_size: int = Field(default=2, ge=2)  # HDBSCAN no admite clusters de 1
    p4_min_samples: int = Field(default=1, ge=1)

    @field_validator("pipeline_stub_fail_at_stage", "llm_base_url", "llm_model", mode="before")
    @classmethod
    def _empty_as_none(cls, value: object) -> object:
        """Permite dejar la variable vacía en `.env` (fallo simulado desactivado, sin URL base)."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("p3_input_template")
    @classmethod
    def _valid_template(cls, value: str) -> str:
        """La plantilla solo admite `{code}` y `{description}` y debe usar `{description}`."""
        try:
            rendered = value.format(code="RF-000", description="\x00")
        except (KeyError, IndexError, ValueError) as exc:
            raise ValueError(
                f"P3_INPUT_TEMPLATE inválida (solo admite {{code}} y {{description}}): {exc}"
            ) from exc
        if "\x00" not in rendered:
            raise ValueError("P3_INPUT_TEMPLATE debe incluir {description}.")
        return value

    @field_validator("p1_story_delimiter_pattern")
    @classmethod
    def _valid_regex(cls, value: str) -> str:
        """Valida que el delimitador de HU sea una expresión regular compilable."""
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"P1_STORY_DELIMITER_PATTERN es una regex inválida: {exc}") from exc
        return value

    @field_validator("llm_api_key", "embeddings_api_key", mode="before")
    @classmethod
    def _empty_secret_as_none(cls, value: object) -> object:
        """`LLM_API_KEY=` o `EMBEDDINGS_API_KEY=` vacías en `.env` equivalen a no tener clave."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("frontend_origins", mode="before")
    @classmethod
    def _parse_origins(cls, value: object) -> object:
        """Convierte `a,b,c` en lista, descarta vacíos y rechaza el comodín `*`."""
        if isinstance(value, str):
            value = [origin.strip() for origin in value.split(",")]
        if isinstance(value, list):
            origins = [str(origin).strip().rstrip("/") for origin in value if str(origin).strip()]
            if "*" in origins:
                raise ValueError("FRONTEND_ORIGINS no admite '*'; indica orígenes explícitos.")
            return origins
        return value


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración cargada una sola vez por proceso."""
    return Settings()

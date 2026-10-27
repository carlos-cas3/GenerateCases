"""Configuración de la aplicación a partir de variables de entorno."""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

StageKeyLiteral = Literal["p1", "p2", "p3", "p4", "p5", "p6", "p7"]


class Settings(BaseSettings):
    """Variables de entorno del backend. La clave de servicio nunca sale del servidor."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    supabase_url: str | None = None
    supabase_service_role_key: SecretStr | None = None

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

    @field_validator("pipeline_stub_fail_at_stage", mode="before")
    @classmethod
    def _empty_as_none(cls, value: object) -> object:
        """Permite dejar la variable vacía en `.env` para desactivar el fallo simulado."""
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

"""Configuración de la aplicación a partir de variables de entorno."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

StageKeyLiteral = Literal["p1", "p2", "p3", "p4", "p5", "p6", "p7"]


class Settings(BaseSettings):
    """Variables de entorno del backend. La clave de servicio nunca sale del servidor."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    supabase_url: str | None = None
    supabase_service_role_key: SecretStr | None = None

    pipeline_stub_delay_seconds: float = Field(default=2.0, ge=0)
    pipeline_stub_fail_at_stage: StageKeyLiteral | None = None
    default_method_type: str = Field(default="llm_pipeline", min_length=1)

    @field_validator("pipeline_stub_fail_at_stage", mode="before")
    @classmethod
    def _empty_as_none(cls, value: object) -> object:
        """Permite dejar la variable vacía en `.env` para desactivar el fallo simulado."""
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración cargada una sola vez por proceso."""
    return Settings()

"""Cliente de Supabase con la clave de servicio. Solo lo usan los repositorios."""

from supabase import Client, create_client

from ai_service.config import Settings
from ai_service.core.errors import ConfigurationError


def create_supabase_client(settings: Settings) -> Client:
    """Crea el cliente o falla de forma explícita si faltan credenciales."""
    if not settings.supabase_url or settings.supabase_service_role_key is None:
        raise ConfigurationError("SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY son obligatorias.")
    return create_client(settings.supabase_url, settings.supabase_service_role_key.get_secret_value())

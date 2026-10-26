"""Punto de entrada de la aplicación FastAPI."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ai_service.api.errors import register_exception_handlers
from ai_service.api.routes import generations, health
from ai_service.config import Settings, get_settings
from ai_service.core.logging import configure_logging
from ai_service.pipeline.stages import build_stub_stages
from ai_service.repositories.documents import DocumentsRepository
from ai_service.repositories.generations import GenerationsRepository
from ai_service.services.generations import GenerationsService
from ai_service.services.pipeline_runs import PipelineRunService, recover_interrupted_generations

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


def create_app(
    settings: Settings | None = None,
    *,
    generations_repository: GenerationsRepository | None = None,
    documents_repository: DocumentsRepository | None = None,
) -> FastAPI:
    """Construye la aplicación. Los repositorios se inyectan en tests; si no, se usa Supabase."""
    configure_logging()
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        generations_repo = generations_repository
        documents_repo = documents_repository
        if generations_repo is None or documents_repo is None:
            from ai_service.clients.supabase import create_supabase_client
            from ai_service.repositories.documents import SupabaseDocumentsRepository
            from ai_service.repositories.generations import SupabaseGenerationsRepository

            client = create_supabase_client(app_settings)
            generations_repo = generations_repo or SupabaseGenerationsRepository(client)
            documents_repo = documents_repo or SupabaseDocumentsRepository(client)

        # Supone un único proceso: nada activo puede seguir vivo tras el arranque.
        await recover_interrupted_generations(generations_repo)

        stages = build_stub_stages(
            app_settings.pipeline_stub_delay_seconds, app_settings.pipeline_stub_fail_at_stage
        )
        app.state.generations_service = GenerationsService(
            generations=generations_repo,
            documents=documents_repo,
            pipeline_runs=PipelineRunService(generations_repo, stages),
            default_method_type=app_settings.default_method_type,
        )
        logger.info("Servicio iniciado")
        yield

    app = FastAPI(title="TestGen API", version="2.0.0", lifespan=lifespan)
    register_exception_handlers(app)
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(generations.router, prefix=API_PREFIX)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("ai_service.main:app", host="127.0.0.1", port=8000)

"""Punto de entrada de la aplicación FastAPI."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ai_service.api.errors import register_exception_handlers
from ai_service.api.routes import documents, generations, health
from ai_service.clients.storage import DocumentStorage
from ai_service.config import Settings, get_settings
from ai_service.core.logging import configure_logging
from ai_service.pipeline.stages import build_stub_stages
from ai_service.repositories.documents import DocumentsRepository
from ai_service.repositories.generations import GenerationsRepository
from ai_service.services.documents import DocumentsService
from ai_service.services.generations import GenerationsService
from ai_service.services.pipeline_runs import PipelineRunService, recover_interrupted_generations

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


def create_app(
    settings: Settings | None = None,
    *,
    generations_repository: GenerationsRepository | None = None,
    documents_repository: DocumentsRepository | None = None,
    documents_storage: DocumentStorage | None = None,
) -> FastAPI:
    """Construye la aplicación. Repositorios y Storage se inyectan en tests; si no, se usa Supabase."""
    configure_logging()
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        generations_repo = generations_repository
        documents_repo = documents_repository
        storage = documents_storage
        if generations_repo is None or documents_repo is None or storage is None:
            from ai_service.clients.storage import SupabaseDocumentStorage
            from ai_service.clients.supabase import create_supabase_client
            from ai_service.repositories.documents import SupabaseDocumentsRepository
            from ai_service.repositories.generations import SupabaseGenerationsRepository

            client = create_supabase_client(app_settings)
            generations_repo = generations_repo or SupabaseGenerationsRepository(client)
            documents_repo = documents_repo or SupabaseDocumentsRepository(client)
            storage = storage or SupabaseDocumentStorage(client, app_settings.documents_bucket)

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
        app.state.documents_service = DocumentsService(
            documents=documents_repo,
            generations=generations_repo,
            storage=storage,
            max_upload_size_bytes=app_settings.max_upload_size_bytes,
        )
        logger.info("Servicio iniciado")
        yield

    app = FastAPI(title="TestGen API", version="2.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.frontend_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )
    register_exception_handlers(app)
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(documents.router, prefix=API_PREFIX)
    app.include_router(generations.router, prefix=API_PREFIX)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("ai_service.main:app", host="127.0.0.1", port=8000)

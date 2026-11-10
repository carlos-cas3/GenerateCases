"""Punto de entrada de la aplicación FastAPI."""

import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ai_service.api.errors import register_exception_handlers
from ai_service.api.routes import documents, generations, health
from ai_service.clients.clustering import ClusteringClient  # puerto
from ai_service.clients.embeddings import EmbeddingsClient  # puerto
from ai_service.clients.extractor import DocumentTextExtractor  # puerto
from ai_service.clients.llm import LlmClient  # puerto
from ai_service.clients.storage import DocumentStorage  # puerto
from ai_service.config import Settings, get_settings
from ai_service.core.logging import configure_logging
from ai_service.pipeline.stages import build_stub_stages
from ai_service.repositories.documents import DocumentsRepository  # puerto
from ai_service.repositories.generations import GenerationsRepository  # puerto
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
    llm_client: LlmClient | None = None,
    embeddings_client: EmbeddingsClient | None = None,
    clustering_client: ClusteringClient | None = None,
    extractor: DocumentTextExtractor | None = None,
) -> FastAPI:
    """Construye la aplicación.

    Repositorios, Storage, clientes LLM/embeddings/clustering y extractor se inyectan en
    tests (R-DI-4); si no, se usan Supabase, las factories (`LLM_PROVIDER`,
    `EMBEDDINGS_PROVIDER`, `CLUSTERING_ALGORITHM`) y los extractores TXT/PDF/DOCX reales.
    """
    configure_logging()
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        generations_repo = generations_repository
        documents_repo = documents_repository
        storage = documents_storage
        if generations_repo is None or documents_repo is None or storage is None:
            from ai_service.clients.supabase import create_supabase_client
            from ai_service.clients.supabase_storage import SupabaseDocumentStorage  # adaptador
            from ai_service.repositories.supabase_documents import SupabaseDocumentsRepository  # adaptador
            from ai_service.repositories.supabase_generations import SupabaseGenerationsRepository  # adaptador

            client = create_supabase_client(app_settings)
            generations_repo = generations_repo or SupabaseGenerationsRepository(client)
            documents_repo = documents_repo or SupabaseDocumentsRepository(client)
            storage = storage or SupabaseDocumentStorage(client, app_settings.documents_bucket)

        # Quien construye, cierra (R-FA-7): solo se registran los clientes de las factories,
        # y en orden inverso, aunque el arranque falle a mitad.
        async with AsyncExitStack() as closers:
            llm = llm_client
            if llm is None:
                from ai_service.clients.llm_factory import LlmClientFactory  # factory (R-FA-5)

                llm = LlmClientFactory.create(app_settings)
                closers.push_async_callback(llm.aclose)

            embeddings = embeddings_client
            if embeddings is None:
                from ai_service.clients.embeddings_factory import EmbeddingsClientFactory  # factory (R-FA-5)

                embeddings = EmbeddingsClientFactory.create(app_settings)
                closers.push_async_callback(embeddings.aclose)

            clustering = clustering_client
            if clustering is None:
                from ai_service.clients.clustering_factory import ClusteringClientFactory  # factory (R-FA-5)

                clustering = ClusteringClientFactory.create(app_settings)
                closers.push_async_callback(clustering.aclose)

            document_extractor = extractor
            if document_extractor is None:
                # Sin factory (D-EXT-5): los tres adaptadores coexisten y el tipo de archivo elige.
                from ai_service.clients.composite_extractor import CompositeDocumentExtractor
                from ai_service.clients.docx_extractor import DocxDocumentExtractor  # adaptador
                from ai_service.clients.pdf_extractor import PdfDocumentExtractor  # adaptador
                from ai_service.clients.txt_extractor import TxtDocumentExtractor  # adaptador
                from ai_service.pipeline.contracts.common import FileType

                document_extractor = CompositeDocumentExtractor(
                    {
                        FileType.TXT: TxtDocumentExtractor(),
                        FileType.PDF: PdfDocumentExtractor(),
                        FileType.DOCX: DocxDocumentExtractor(),
                    }
                )

            # Las etapas P1–P6 aún son stubs: estos clientes se exponen para inyectarlos en ellas
            # al construir `build_real_stages` (Fase 4: P1, P2, P6; Fase 5: P3, P4).
            # Nadie más debe leerlos de aquí.
            app.state.llm_client = llm
            app.state.embeddings_client = embeddings
            app.state.clustering_client = clustering
            app.state.extractor = document_extractor

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

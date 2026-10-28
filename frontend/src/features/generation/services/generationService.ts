/**
 * Acceso a datos de la generación de casos de prueba.
 * `startGeneration` (subida + creación), `getGeneration` y `listRecentExecutions` usan el backend real;
 * `getExecutionPipeline` sigue con mocks porque lo consume el detalle de historial.
 */
import { request } from "@/shared/api";
import { delay } from "@/shared/utils/delay";
import { buildMockStages } from "../mocks/generationMocks";
import type { ExecutionStage, Generation, RecentExecution } from "../types";
import type {
    CreateGenerationRequestDto,
    GenerationDto,
    GenerationListDto,
} from "./generationDto";
import { documentService } from "./documentService";
import { mapGeneration, mapRecentExecutions } from "./generationMappers";

export interface StartGenerationInput {
    /** Se sube con `POST /documents` antes de crear la generación. */
    file: File;
    semanticGrouping: boolean;
}

export const generationService = {
    /**
     * Sube el archivo (`POST /documents`) y crea la generación sobre él (`POST /generations`).
     * Si la creación falla tras la subida, el documento queda registrado y es reutilizable
     * (no hay rollback). `method_type` no se envía: aplica el valor por defecto del servidor.
     */
    async startGeneration(input: StartGenerationInput): Promise<Generation> {
        const documentId = await documentService.uploadDocument(input.file);
        const body: CreateGenerationRequestDto = {
            document_id: documentId,
            configuration: {
                semantic_clustering_enabled: input.semanticGrouping,
            },
        };
        const dto = await request<GenerationDto>("/generations", {
            method: "POST",
            body,
        });
        return mapGeneration(dto);
    },

    /** `GET /generations/{id}`: alimenta el polling del progreso. */
    async getGeneration(id: string, signal?: AbortSignal): Promise<Generation> {
        const dto = await request<GenerationDto>(
            `/generations/${encodeURIComponent(id)}`,
            { signal },
        );
        return mapGeneration(dto);
    },

    /** `GET /generations?limit=&offset=0` (orden `created_at` desc en el backend). */
    async listRecentExecutions(
        limit: number,
        signal?: AbortSignal,
    ): Promise<RecentExecution[]> {
        const params = new URLSearchParams({
            limit: String(limit),
            offset: "0",
        });
        const list = await request<GenerationListDto>(
            `/generations?${params}`,
            { signal },
        );
        return mapRecentExecutions(list);
    },

    /** Pipeline de UNA ejecución concreta para el detalle de historial (todavía con mocks). */
    async getExecutionPipeline(
        _executionId: string,
        semanticGrouping: boolean,
    ): Promise<ExecutionStage[]> {
        await delay(300);
        return buildMockStages(semanticGrouping, "running");
    },
};

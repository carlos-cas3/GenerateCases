/**
 * Acceso a datos de la generación de casos de prueba.
 * `startGeneration`, `getGeneration` y `listRecentExecutions` usan el backend real;
 * `getExecutionPipeline` sigue con mocks porque lo consume el detalle de historial (Fase 2).
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
import { mapGeneration, mapRecentExecutions } from "./generationMappers";

/** Fase 1.5: documento del seed. Sin él no se puede iniciar una generación. */
export const DEV_DOCUMENT_ID =
    import.meta.env.VITE_DEV_DOCUMENT_ID?.trim() || undefined;

export interface StartGenerationInput {
    /** Se valida en el cliente pero todavía NO se envía (no existe `POST /documents`). */
    file: File;
    semanticGrouping: boolean;
}

export const generationService = {
    /**
     * `POST /generations` con el documento del seed (`VITE_DEV_DOCUMENT_ID`).
     * `method_type` no se envía: aplica el valor por defecto del servidor.
     */
    async startGeneration(input: StartGenerationInput): Promise<Generation> {
        // TODO Fase 2: POST /documents con `input.file` y usar el id devuelto.
        if (!DEV_DOCUMENT_ID) {
            throw new Error("VITE_DEV_DOCUMENT_ID no está configurado.");
        }
        const body: CreateGenerationRequestDto = {
            document_id: DEV_DOCUMENT_ID,
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

/**
 * Acceso a datos de la generación de casos de prueba.
 * Hoy responde con mocks; cuando exista el backend solo cambia este archivo.
 */
import { delay } from "@/shared/utils/delay";
import {
    buildMockStages,
    MOCK_RECENT_EXECUTIONS,
} from "../mocks/generationMocks";
import type { ExecutionStage, RecentExecution } from "../types";

export interface StartGenerationInput {
    file: File;
    semanticGrouping: boolean;
}

export const generationService = {
    /** Etapas de la ejecución en curso (con o sin la etapa de agrupación semántica). */
    async getExecutionStages(
        semanticGrouping: boolean,
    ): Promise<ExecutionStage[]> {
        await delay(200);
        return buildMockStages(semanticGrouping, "running");
    },

    async listRecentExecutions(limit: number): Promise<RecentExecution[]> {
        await delay(200);
        return MOCK_RECENT_EXECUTIONS.slice(0, limit);
    },

    /** TODO: enviar el documento al backend e iniciar la generación real. */
    async startGeneration(
        _input: StartGenerationInput,
    ): Promise<{ executionId: string }> {
        await delay(800);
        // El servicio todavía utiliza una respuesta simulada.
        void _input;
        return { executionId: `exec-${Date.now()}` };
    },
};

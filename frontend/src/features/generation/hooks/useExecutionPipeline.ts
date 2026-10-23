import { useAsyncData } from "@/shared/hooks/useAsyncData";
import { generationService } from "../services/generationService";
import type { ExecutionStage } from "../types";

const NO_STAGES: ExecutionStage[] = [];

/** Etapas del pipeline de la ejecución con ese identificador. */
export function useExecutionPipeline(
    executionId: string,
    semanticGrouping: boolean,
) {
    const { data, isLoading, error, reload } = useAsyncData(
        () =>
            generationService.getExecutionPipeline(
                executionId,
                semanticGrouping,
            ),
        [executionId, semanticGrouping],
        {
            errorMessage: "No se pudo cargar el pipeline de la ejecución.",
            initialData: NO_STAGES,
        },
    );

    return { stages: data, isLoading, error, reload };
}

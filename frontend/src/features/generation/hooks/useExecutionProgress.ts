import { useAsyncData } from "@/shared/hooks/useAsyncData";
import { generationService } from "../services/generationService";
import type { ExecutionStage } from "../types";

const NO_STAGES: ExecutionStage[] = [];

/** Etapas de la ejecución. Al cambiar la agrupación semántica conserva las anteriores mientras recarga. */
export function useExecutionProgress(semanticGrouping: boolean) {
    const { data, isLoading, error } = useAsyncData(
        () => generationService.getExecutionStages(semanticGrouping),
        [semanticGrouping],
        {
            errorMessage: "No se pudo cargar el progreso de la ejecución.",
            initialData: NO_STAGES,
            keepPreviousData: true,
        },
    );

    return { stages: data, isLoading, error };
}

import { useAsyncData } from "@/shared/hooks/useAsyncData";
import { generationService } from "../services/generationService";
import type { RecentExecution } from "../types";

const NO_EXECUTIONS: RecentExecution[] = [];

export function useRecentExecutions(limit: number) {
    const { data, isLoading, error, reload } = useAsyncData(
        () => generationService.listRecentExecutions(limit),
        [limit],
        {
            errorMessage: "No se pudieron cargar las ejecuciones recientes.",
            initialData: NO_EXECUTIONS,
            keepPreviousData: true,
        },
    );

    return { executions: data, isLoading, error, reload };
}

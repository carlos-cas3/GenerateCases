import { useAsyncData } from "@/shared/hooks/useAsyncData";
import { generationService } from "../services/generationService";
import type { RecentExecution } from "../types";

const NO_EXECUTIONS: RecentExecution[] = [];

/** Últimas generaciones (sin polling: quien la usa llama a `reload` cuando cambia algo). */
export function useRecentExecutions(limit: number) {
    const { data, isLoading, error, reload } = useAsyncData(
        (signal) => generationService.listRecentExecutions(limit, signal),
        [limit],
        {
            errorMessage: "No se pudieron cargar las ejecuciones recientes.",
            initialData: NO_EXECUTIONS,
            keepPreviousData: true,
        },
    );

    return { executions: data, isLoading, error, reload };
}

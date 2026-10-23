import { useAsyncData } from "@/shared/hooks/useAsyncData";
import { historyService } from "../services/historyService";
import type { ExecutionDetail } from "../types";

/**
 * Detalle de una ejecución a partir de su identificador (el de la ruta).
 * `execution === null` y sin `isLoading` ni `error` significa «no existe».
 */
export function useExecutionDetail(executionId: string) {
    const { data, isLoading, error, reload } =
        useAsyncData<ExecutionDetail | null>(
            () => historyService.getExecutionById(executionId),
            [executionId],
            {
                errorMessage: "No se pudo cargar el detalle de la ejecución.",
                initialData: null,
            },
        );

    return { execution: data, isLoading, error, reload };
}

import { useCallback } from "react";
import { useAsyncData } from "@/shared/hooks/useAsyncData";
import { historyService } from "../services/historyService";
import type { ExecutionRecord } from "../types";

const NO_RECORDS: ExecutionRecord[] = [];

/**
 * Fuente única de las ejecuciones para la UI (historial, comparación…).
 * Recuerda la última lista: al volver a una pantalla se ve al instante y se revalida en segundo plano.
 */
export function useExecutions() {
    const { data, isLoading, error, reload, mutate } = useAsyncData(
        () => historyService.listExecutions(),
        [],
        {
            errorMessage:
                "No se pudo cargar el historial. Inténtalo nuevamente.",
            initialData: NO_RECORDS,
            keepPreviousData: true,
            cacheKey: "executions",
        },
    );

    /** Elimina en el servicio y, solo si tuvo éxito, actualiza la lista local. */
    const remove = useCallback(
        async (targets: ExecutionRecord[]) => {
            const ids = targets.map((t) => t.id);
            await historyService.deleteExecutions(ids);
            mutate((previous) => previous.filter((r) => !ids.includes(r.id)));
        },
        [mutate],
    );

    return { records: data, isLoading, error, reload, remove };
}

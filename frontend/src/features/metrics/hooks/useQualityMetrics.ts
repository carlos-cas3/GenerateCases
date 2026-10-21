import { useAsyncData } from "@/shared/hooks/useAsyncData";
import { metricsService } from "../services/metricsService";
import type { MetricComparison } from "../types";

const NO_METRICS: MetricComparison[] = [];

/** Métricas de un par A/B. Con ids `null` no consulta nada ni muestra nada. */
export function useQualityMetrics(aId: string | null, bId: string | null) {
    const { data, isLoading, error } = useAsyncData(
        () =>
            aId && bId
                ? metricsService.getQualityMetrics(aId, bId)
                : Promise.resolve(NO_METRICS),
        [aId, bId],
        {
            errorMessage: "No se pudieron cargar las métricas de calidad.",
            initialData: NO_METRICS,
            enabled: aId !== null && bId !== null,
        },
    );

    return { metrics: data, isLoading, error };
}

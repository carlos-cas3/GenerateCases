/**
 * Acceso a datos de las métricas de calidad.
 * Recibe SOLO ids: así «metrics» no necesita conocer el modelo de ejecuciones de otra feature.
 * Hoy responde con mocks; cuando exista el backend solo cambia este archivo.
 */
import { delay } from "@/shared/utils/delay";
import { buildMockMetrics } from "../mocks/metricsMocks";
import type { MetricComparison } from "../types";

const LATENCY_MS = 300;

export const metricsService = {
    /** Métricas de calidad de la ejecución A (con clustering) frente a la B (sin clustering). */
    async getQualityMetrics(
        aId: string,
        bId: string,
    ): Promise<MetricComparison[]> {
        await delay(LATENCY_MS);
        return buildMockMetrics(aId, bId);
    },
};

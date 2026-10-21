import type { ExecutionRecord } from "@/features/history";
import type { MetricComparison } from "@/features/metrics";

/**
 * Si alguna de las dos ejecuciones no terminó, no hay resultados reales todavía:
 * se conservan las métricas (nombre y descripción) pero sin valores («—»).
 */
export function hideValuesIfIncomplete(
    metrics: MetricComparison[],
    pair: { a: ExecutionRecord; b: ExecutionRecord },
): MetricComparison[] {
    const complete =
        pair.a.status === "completed" && pair.b.status === "completed";
    return complete
        ? metrics
        : metrics.map((metric) => ({ ...metric, a: null, b: null }));
}

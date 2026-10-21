/**
 * DEMO: las métricas de calidad todavía no están definidas.
 * Devuelve métricas y valores ficticios (deterministas por par de ids) solo para ver las cards;
 * se reemplaza cuando existan las métricas reales.
 */
import type { MetricComparison } from "../types";

function seededRandom(seed: string) {
    let h = 0;
    for (const char of seed) h = (h * 31 + char.charCodeAt(0)) >>> 0;
    return () => {
        h = (h * 1664525 + 1013904223) >>> 0;
        return h / 2 ** 32;
    };
}

const round1 = (n: number) => Math.round(n * 10) / 10;
const clampPercent = (n: number) => Math.min(100, Math.max(0, n));

/** A = ejecución con clustering, B = ejecución sin clustering. */
export function buildMockMetrics(aId: string, bId: string): MetricComparison[] {
    const rnd = seededRandom(`${aId}|${bId}`);

    const baseCoverage = 72 + rnd() * 20;
    const baseRedundancy = 12 + rnd() * 14;
    const baseQuality = 65 + rnd() * 20;

    return [
        {
            id: "coverage",
            name: "Cobertura de requisitos",
            description: "Requisitos con al menos un caso de prueba.",
            icon: "coverage",
            betterWhen: "higher",
            detail: "Ejemplo de detalle: proporción de requisitos funcionales cubiertos por los casos generados.",
            a: round1(clampPercent(baseCoverage + rnd() * 10 - 2)),
            b: round1(baseCoverage),
        },
        {
            id: "redundancy",
            name: "Redundancia de casos",
            description: "Casos de prueba muy parecidos entre sí.",
            icon: "redundancy",
            betterWhen: "lower",
            detail: "Ejemplo de detalle: porcentaje de casos que repiten el mismo escenario. Menos es mejor.",
            a: round1(clampPercent(baseRedundancy - (rnd() * 9 - 1))),
            b: round1(baseRedundancy),
        },
        {
            id: "quality",
            name: "Calidad promedio",
            description: "Puntaje medio de calidad de los casos.",
            icon: "quality",
            betterWhen: "higher",
            detail: "Ejemplo de detalle: promedio del puntaje asignado a cada caso en la etapa de evaluación.",
            a: round1(clampPercent(baseQuality + rnd() * 10 - 2)),
            b: round1(baseQuality),
        },
    ];
}

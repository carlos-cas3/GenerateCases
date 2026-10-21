import type { BetterWhen } from '@/shared/utils/metricFormat';

export type MetricIconKey = 'coverage' | 'redundancy' | 'quality' | 'generic';

/** Definición de una métrica (qué es). Todas se expresan en % (0–100). */
export interface MetricInfo {
  id: string;
  name: string;
  /** Descripción breve, visible bajo el nombre. */
  description: string;
  icon?: MetricIconKey;
  /** Sentido en el que mejora; si se omite, la diferencia se muestra neutra. */
  betterWhen?: BetterWhen;
  /** Texto del modal «Ver detalle». */
  detail?: string;
}

/** Métrica medida en dos ejecuciones. A = con clustering, B = sin clustering. `null` = sin dato aún. */
export interface MetricComparison extends MetricInfo {
  a: number | null;
  b: number | null;
}

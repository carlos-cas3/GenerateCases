import type { BetterWhen, ValueUnit } from '@/shared/utils/metricFormat';

/** Ejecuciones elegidas, guardadas por id. A = con clustering, B = sin clustering. */
export interface ComparisonSelection {
  aId: string | null;
  bId: string | null;
}


/** Una fila de cualquiera de las dos tablas de resultados. */
export interface ComparisonRow {
  id: string;
  label: string;
  /** `null` = valor aún no disponible (p. ej. la ejecución no terminó). */
  a: number | null;
  b: number | null;
  unit?: ValueUnit;
  /**
   * Sentido en el que la métrica «mejora». Si se omite, la diferencia se muestra neutra
   * (p. ej. cantidad de HU: más o menos no es mejor ni peor por sí solo).
   */
  betterWhen?: BetterWhen;
}

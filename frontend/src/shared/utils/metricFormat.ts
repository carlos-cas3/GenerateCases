export type ValueUnit = 'count' | 'percent' | 'score';
/** Sentido en el que una métrica «mejora». Si se omite, la diferencia se considera neutra. */
export type BetterWhen = 'higher' | 'lower';

const integer = new Intl.NumberFormat('es-PE', { maximumFractionDigits: 0 });
const oneDecimal = new Intl.NumberFormat('es-PE', { minimumFractionDigits: 1, maximumFractionDigits: 1 });

function formatNumber(value: number, unit: ValueUnit) {
  return unit === 'count' ? integer.format(value) : oneDecimal.format(value);
}

export function formatValue(value: number | null, unit: ValueUnit = 'count'): string {
  if (value === null) return '—';
  return unit === 'percent' ? `${formatNumber(value, unit)} %` : formatNumber(value, unit);
}

export interface Difference {
  /** A − B */
  delta: number;
  /** Variación relativa respecto a B, en %. `null` si B es 0. */
  percent: number | null;
}

/** Diferencia = A − B. `null` si falta alguno de los dos valores. */
export function computeDifference(a: number | null, b: number | null): Difference | null {
  if (a === null || b === null) return null;
  const delta = a - b;
  return { delta, percent: b === 0 ? null : (delta / Math.abs(b)) * 100 };
}

const signOf = (n: number) => (n > 0 ? '+' : n < 0 ? '−' : '');

/** "+35", "−2,4 pp" (puntos porcentuales para métricas en %) o "0". */
export function formatDelta(delta: number, unit: ValueUnit = 'count'): string {
  const rounded = Math.abs(Number(delta.toFixed(unit === 'count' ? 0 : 1)));
  if (rounded === 0) return '0';
  const text = `${signOf(delta)}${formatNumber(rounded, unit)}`;
  return unit === 'percent' ? `${text} pp` : text;
}

export function formatPercentChange(percent: number): string {
  const rounded = Math.abs(Number(percent.toFixed(1)));
  return rounded === 0 ? '0 %' : `${signOf(percent)}${oneDecimal.format(rounded)} %`;
}

export type DifferenceTone = 'better' | 'worse' | 'neutral';

export function getDifferenceTone(delta: number, betterWhen?: BetterWhen): DifferenceTone {
  if (delta === 0 || !betterWhen) return 'neutral';
  const improved = betterWhen === 'higher' ? delta > 0 : delta < 0;
  return improved ? 'better' : 'worse';
}

import type { ExecutionStatus } from '@/shared/types';
import type { HistoryFilters, SortDirection, SortKey, SortState } from './types';

/** Etiquetas del historial (el estado «pending» representa la cola). */
export const HISTORY_STATUS_LABEL: Record<ExecutionStatus, string> = {
  completed: 'Completado',
  in_progress: 'En proceso',
  pending: 'Pendiente',
  failed: 'Error',
};

export const STATUS_FILTER_ORDER: ExecutionStatus[] = ['completed', 'in_progress', 'pending', 'failed'];

export const PAGE_SIZE_OPTIONS = [5, 10] as const;
export type PageSize = (typeof PAGE_SIZE_OPTIONS)[number];

/** Cantidad exacta de ejecuciones que se comparan. Con más seleccionadas, solo se puede eliminar. */
export const COMPARE_SELECTION_SIZE = 2;

export const DEFAULT_FILTERS: HistoryFilters = { query: '', status: 'all', clustering: 'all' };
export const DEFAULT_SORT: SortState = { key: 'uploadedAt', direction: 'desc' };

/** Primer sentido al ordenar una columna: nombre A→Z; fecha y conteos de mayor a menor. */
export const DEFAULT_DIRECTION: Record<SortKey, SortDirection> = {
  documentName: 'asc',
  uploadedAt: 'desc',
  huCount: 'desc',
  rfCount: 'desc',
  cpCount: 'desc',
};

/** Espera tras una descarga antes de permitir otra (evita solicitudes repetidas por clics seguidos). */
export const DOWNLOAD_COOLDOWN_MS = 3000;
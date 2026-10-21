import type { ExecutionStatus } from '@/shared/types';

export interface ExecutionRecord {
  id: string;
  /** Nombre completo con extensión, p. ej. "historias.pdf". */
  documentName: string;
  /** ISO string. */
  uploadedAt: string;
  status: ExecutionStatus;
  /** Historias de usuario, requisitos funcionales y casos de prueba. `null` = aún no disponible. */
  huCount: number | null;
  rfCount: number | null;
  cpCount: number | null;
  clustering: boolean;
}

export type StatusFilter = ExecutionStatus | 'all';
export type ClusteringFilter = 'all' | 'yes' | 'no';

export interface HistoryFilters {
  query: string;
  status: StatusFilter;
  clustering: ClusteringFilter;
}

export type SortKey = 'documentName' | 'uploadedAt' | 'huCount' | 'rfCount' | 'cpCount';
export type SortDirection = 'asc' | 'desc';

export interface SortState {
  key: SortKey;
  direction: SortDirection;
}

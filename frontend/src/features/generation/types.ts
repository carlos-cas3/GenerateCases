import type { ReactNode } from 'react';
import type { ExecutionStatus, StageStatus } from '@/shared/types';

export type { ExecutionStatus, StageStatus };

export interface ExecutionStage {
  /** Identificador estable de la etapa (en la API: `key`, p. ej. `p1`). */
  id: string;
  title: string;
  /** Texto corto visible bajo el título. */
  summary?: string;
  status: StageStatus;
  /** Si existe, la etapa se puede expandir para mostrarlo. */
  details?: ReactNode;
  /** Ej.: "12 s". */
  durationLabel?: string;
  /** Mensaje de error de la etapa, si la API lo informa. */
  errorMessage?: string;
  /** ISO 8601 (UTC). */
  startedAt?: string;
  completedAt?: string;
}

export interface RecentExecution {
  id: string;
  documentName: string;
  /** ISO string o Date. */
  createdAt: string | Date;
  status: ExecutionStatus;
}

/** Generación tal como la usa la UI (adaptada desde el DTO del backend). */
export interface Generation extends RecentExecution {
  documentId: string;
  semanticGrouping: boolean;
  stages: ExecutionStage[];
  /** Motivo del fallo de la generación (p. ej. ejecución interrumpida por reinicio). */
  errorMessage?: string;
  startedAt?: string;
  completedAt?: string;
}

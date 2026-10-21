import type { ReactNode } from 'react';
import type { ExecutionStatus } from '@/shared/types';

export type { ExecutionStatus };

export interface ExecutionStage {
  id: string;
  title: string;
  /** Texto corto visible bajo el título. */
  summary?: string;
  status: ExecutionStatus;
  /** Si existe, la etapa se puede expandir para mostrarlo. */
  details?: ReactNode;
  /** Ej.: "12 s". */
  durationLabel?: string;
}

export interface RecentExecution {
  id: string;
  documentName: string;
  /** ISO string o Date. */
  createdAt: string | Date;
  status: ExecutionStatus;
}

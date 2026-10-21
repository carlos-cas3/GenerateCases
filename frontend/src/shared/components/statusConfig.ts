import type { ExecutionStatus } from '../types';

/** Clave de color del tema usada por cada estado. */
export type StatusTone = 'success' | 'primary' | 'error' | 'neutral';

interface StatusConfig {
  label: string;
  tone: StatusTone;
}

export const STATUS_CONFIG: Record<ExecutionStatus, StatusConfig> = {
  pending: { label: 'Pendiente', tone: 'neutral' },
  in_progress: { label: 'En proceso', tone: 'primary' },
  completed: { label: 'Completada', tone: 'success' },
  failed: { label: 'Fallida', tone: 'error' },
};

/** Color de texto/icono del tema para un tono. */
export const toneColor = (tone: StatusTone) => (tone === 'neutral' ? 'text.secondary' : `${tone}.main`);

import type { ExecutionStatus, StageStatus } from '../types';

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

/** Estados de etapa: los de ejecución más `skipped` (no se ejecutó; no es éxito ni error). */
export const STAGE_STATUS_CONFIG: Record<StageStatus, StatusConfig> = {
  ...STATUS_CONFIG,
  skipped: { label: 'Omitida', tone: 'neutral' },
};

/** Color de texto/icono del tema para un tono. */
export const toneColor = (tone: StatusTone) => (tone === 'neutral' ? 'text.secondary' : `${tone}.main`);

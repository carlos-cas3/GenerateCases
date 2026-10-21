import type { ReactElement } from 'react';
import CheckCircleRoundedIcon from '@mui/icons-material/CheckCircleRounded';
import ErrorRoundedIcon from '@mui/icons-material/ErrorRounded';
import RadioButtonUncheckedRoundedIcon from '@mui/icons-material/RadioButtonUncheckedRounded';
import CircularProgress from '@mui/material/CircularProgress';
import type { ExecutionStatus } from './types';

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

/** Icono coherente con cada estado. No depende solo del color: la forma también cambia. */
export function StatusIcon({ status, size = 22 }: { status: ExecutionStatus; size?: number }): ReactElement {
  const sx = { fontSize: size, color: toneColor(STATUS_CONFIG[status].tone) };
  switch (status) {
    case 'completed':
      return <CheckCircleRoundedIcon sx={sx} aria-hidden />;
    case 'failed':
      return <ErrorRoundedIcon sx={sx} aria-hidden />;
    case 'in_progress':
      return <CircularProgress size={size - 4} thickness={5} aria-hidden sx={{ m: '2px' }} />;
    default:
      return <RadioButtonUncheckedRoundedIcon sx={sx} aria-hidden />;
  }
}

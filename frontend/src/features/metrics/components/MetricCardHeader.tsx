import type { ReactNode } from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import type { MetricIconKey } from '../types';
import { MetricIconBadge } from './MetricIconBadge';

export interface MetricCardHeaderProps {
  name: string;
  description: string;
  icon?: MetricIconKey;
  /** Tercera parte del header: el resultado (valor en % o diferencia). */
  result: ReactNode;
  /** Texto pequeño bajo el resultado. */
  resultCaption: string;
}

/** Header en 3 partes: [icono] [nombre + descripción] [resultado]. */
export function MetricCardHeader({ name, description, icon, result, resultCaption }: MetricCardHeaderProps) {
  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: 'auto minmax(0, 1fr) auto',
        alignItems: 'center',
        gap: { xs: 1.5, sm: 2 },
        p: { xs: 1.5, sm: 2 },
        border: '1px solid',
        borderColor: 'divider',
        borderRadius: '12px',
        bgcolor: 'background.default',
      }}
    >
      <MetricIconBadge icon={icon} />

      <Box sx={{ minWidth: 0 }}>
        <Typography variant="subtitle1" component="h3" sx={{ lineHeight: 1.3 }}>
          {name}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {description}
        </Typography>
      </Box>

      <Box sx={{ textAlign: 'right' }}>
        <Box sx={{ fontSize: '1.5rem', fontWeight: 700, lineHeight: 1.2, fontVariantNumeric: 'tabular-nums' }}>
          {result}
        </Box>
        <Typography variant="caption" color="text.secondary">
          {resultCaption}
        </Typography>
      </Box>
    </Box>
  );
}

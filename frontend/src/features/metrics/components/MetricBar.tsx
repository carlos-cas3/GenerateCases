import Box from '@mui/material/Box';
import LinearProgress from '@mui/material/LinearProgress';
import Typography from '@mui/material/Typography';
import { formatValue } from '@/shared/utils/metricFormat';

export interface MetricBarProps {
  /** Valor en % (0–100). `null` = sin dato: se dibuja la barra vacía. */
  value: number | null;
  /** Nombre accesible de la barra. */
  label: string;
  tone?: 'primary' | 'neutral';
  /** Muestra las marcas 0 % · 50 % · 100 % bajo la barra. */
  showScale?: boolean;
}

const clamp = (n: number) => Math.min(100, Math.max(0, n));

/** Gráfico de barra simple de 0 a 100 %. */
export function MetricBar({ value, label, tone = 'primary', showScale = true }: MetricBarProps) {
  return (
    <Box>
      <LinearProgress
        variant="determinate"
        value={value === null ? 0 : clamp(value)}
        aria-label={label}
        aria-valuetext={value === null ? 'Sin datos' : formatValue(value, 'percent')}
        sx={{
          height: 12,
          borderRadius: 6,
          bgcolor: 'divider',
          '& .MuiLinearProgress-bar': {
            borderRadius: 6,
            bgcolor: tone === 'primary' ? 'primary.main' : 'text.secondary',
          },
        }}
      />
      {showScale && (
        <Box aria-hidden sx={{ display: 'flex', justifyContent: 'space-between', mt: 0.5 }}>
          {['0 %', '50 %', '100 %'].map((tick) => (
            <Typography key={tick} variant="caption" color="text.secondary">
              {tick}
            </Typography>
          ))}
        </Box>
      )}
    </Box>
  );
}

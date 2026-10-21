import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Typography from '@mui/material/Typography';
import { formatValue } from '@/shared/utils/metricFormat';
import { MetricBar } from './MetricBar';

export interface MetricSeriesRowProps {
  /** Ej.: «Ejecución A». */
  title: string;
  /** Ej.: «Con clustering». */
  badge: string;
  tone: 'primary' | 'neutral';
  value: number | null;
  metricName: string;
}

/** Un resultado dentro de su propio contenedor: título + insignia + valor y su barra. Lo usan la card y el modal. */
export function MetricSeriesRow({ title, badge, tone, value, metricName }: MetricSeriesRowProps) {
  return (
    <Box sx={{ p: 1.5, border: '1px solid', borderColor: 'divider', borderRadius: '12px' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1, mb: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 1, minWidth: 0 }}>
          <Typography variant="subtitle2">{title}</Typography>
          <Chip size="small" label={badge} color={tone === 'primary' ? 'primary' : 'default'} variant="outlined" />
        </Box>
        <Typography variant="subtitle2" sx={{ fontVariantNumeric: 'tabular-nums', flexShrink: 0 }}>
          {formatValue(value, 'percent')}
        </Typography>
      </Box>
      <MetricBar value={value} tone={tone} label={`${metricName}: ${title}, ${badge.toLowerCase()}`} />
    </Box>
  );
}

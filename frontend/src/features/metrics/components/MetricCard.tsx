import { useState } from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import type { SxProps, Theme } from '@mui/material/styles';
import { BaseCard } from '../../../components/cards';
import { formatValue } from '../../../shared/utils/metricFormat';
import type { MetricInfo } from '../types';
import { MetricBar } from './MetricBar';
import { MetricCardHeader } from './MetricCardHeader';
import { MetricDetailDialog } from './MetricDetailDialog';
import { ViewDetailFooter } from './ViewDetailFooter';

export interface MetricCardProps {
  metric: MetricInfo;
  /** Resultado en % (0–100). `null` = aún sin dato. */
  value: number | null;
  sx?: SxProps<Theme>;
}

/** Versión simple: el resultado de UNA métrica de UNA ejecución. */
export function MetricCard({ metric, value, sx }: MetricCardProps) {
  const [open, setOpen] = useState(false);

  return (
    <BaseCard ariaLabel={metric.name} sx={sx}>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5, flex: 1 }}>
        <MetricCardHeader
          name={metric.name}
          description={metric.description}
          icon={metric.icon}
          result={formatValue(value, 'percent')}
          resultCaption="Resultado"
        />

        <MetricBar value={value} label={metric.name} />

        <ViewDetailFooter metricName={metric.name} onClick={() => setOpen(true)} />
      </Box>

      <MetricDetailDialog open={open} onClose={() => setOpen(false)} metric={metric}>
        <Box sx={{ p: 1.5, border: '1px solid', borderColor: 'divider', borderRadius: '12px' }}>
          <Typography variant="h4" component="p" sx={{ fontWeight: 700, mb: 1.5, fontVariantNumeric: 'tabular-nums' }}>
            {formatValue(value, 'percent')}
          </Typography>
          <MetricBar value={value} label={metric.name} />
        </Box>
      </MetricDetailDialog>
    </BaseCard>
  );
}

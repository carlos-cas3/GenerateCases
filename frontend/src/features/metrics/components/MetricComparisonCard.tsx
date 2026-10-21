import { useState } from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import type { SxProps, Theme } from '@mui/material/styles';
import { BaseCard } from '@/shared/components/BaseCard';
import { DifferenceValue } from '@/shared/components/DifferenceValue';
import { computeDifference, formatPercentChange } from '@/shared/utils/metricFormat';
import type { MetricComparison } from '../types';
import { MetricCardHeader } from './MetricCardHeader';
import { MetricDetailDialog } from './MetricDetailDialog';
import { MetricSeriesRow } from './MetricSeriesRow';
import { ViewDetailFooter } from './ViewDetailFooter';

export interface MetricComparisonCardProps {
  metric: MetricComparison;
  sx?: SxProps<Theme>;
}

/**
 * Versión de comparación: igual que la simple pero el header muestra la DIFERENCIA (A − B)
 * y el body tiene un contenedor por ejecución, indicando cuál lleva clustering.
 */
export function MetricComparisonCard({ metric, sx }: MetricComparisonCardProps) {
  const [open, setOpen] = useState(false);
  const relative = computeDifference(metric.a, metric.b)?.percent ?? null;

  const rows = (
    <>
      <MetricSeriesRow title="Ejecución A" badge="Con clustering" tone="primary" value={metric.a} metricName={metric.name} />
      <MetricSeriesRow title="Ejecución B" badge="Sin clustering" tone="neutral" value={metric.b} metricName={metric.name} />
    </>
  );

  return (
    <BaseCard ariaLabel={`${metric.name}: comparación`} sx={sx}>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5, flex: 1 }}>
        <MetricCardHeader
          name={metric.name}
          description={metric.description}
          icon={metric.icon}
          result={
            <DifferenceValue a={metric.a} b={metric.b} unit="percent" betterWhen={metric.betterWhen} size="large" />
          }
          resultCaption="Diferencia (A − B)"
        />

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>{rows}</Box>

        <ViewDetailFooter metricName={metric.name} onClick={() => setOpen(true)} />
      </Box>

      <MetricDetailDialog open={open} onClose={() => setOpen(false)} metric={metric}>
        {rows}
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 1,
            p: 1.5,
            borderRadius: '12px',
            bgcolor: 'background.default',
          }}
        >
          <Box>
            <Typography variant="subtitle2">Diferencia (A − B)</Typography>
            {relative !== null && (
              <Typography variant="caption" color="text.secondary">
                Variación relativa respecto a B: {formatPercentChange(relative)}
              </Typography>
            )}
          </Box>
          <DifferenceValue a={metric.a} b={metric.b} unit="percent" betterWhen={metric.betterWhen} size="large" />
        </Box>
      </MetricDetailDialog>
    </BaseCard>
  );
}

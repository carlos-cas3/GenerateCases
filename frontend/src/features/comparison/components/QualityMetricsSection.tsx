import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import { BaseCard } from '../../../components/cards';
import { MetricComparisonCard } from '../../metrics/components/MetricComparisonCard';
import type { MetricComparison } from '../../metrics/types';

export interface QualityMetricsSectionProps {
  /** Las métricas llegan por props: aún no están definidas, así que la lista es configurable. */
  metrics: MetricComparison[];
}

/** Sección «Métricas de calidad»: una card de comparación por métrica, en una grilla adaptable. */
export function QualityMetricsSection({ metrics }: QualityMetricsSectionProps) {
  return (
    <Box component="section" aria-labelledby="quality-metrics-heading">
      <Box sx={{ mb: 2 }}>
        <Typography id="quality-metrics-heading" variant="h6" component="h2">
          Métricas de calidad
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Calidad de los casos de prueba generados con y sin clustering. Verde = mejora de A respecto a B.
        </Typography>
      </Box>

      {metrics.length === 0 ? (
        <BaseCard>
          <Typography variant="body2" color="text.secondary" sx={{ py: 3, textAlign: 'center' }}>
            Las métricas de calidad aún no están definidas.
          </Typography>
        </BaseCard>
      ) : (
        <Box
          sx={{
            display: 'grid',
            gap: { xs: 2, md: 3 },
            gridTemplateColumns: {
              xs: 'minmax(0, 1fr)',
              md: 'repeat(2, minmax(0, 1fr))',
              xl: 'repeat(3, minmax(0, 1fr))',
            },
          }}
        >
          {metrics.map((metric) => (
            <MetricComparisonCard key={metric.id} metric={metric} />
          ))}
        </Box>
      )}
    </Box>
  );
}

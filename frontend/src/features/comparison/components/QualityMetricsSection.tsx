import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Skeleton from '@mui/material/Skeleton';
import Typography from '@mui/material/Typography';
import { BaseCard } from '@/shared/components/BaseCard';
import { MetricComparisonCard } from '@/features/metrics';
import type { MetricComparison } from '@/features/metrics';

export interface QualityMetricsSectionProps {
  /** Las métricas llegan por props: aún no están definidas, así que la lista es configurable. */
  metrics: MetricComparison[];
  isLoading?: boolean;
  errorMessage?: string;
}

const GRID_SX = {
  display: 'grid',
  gap: { xs: 2, md: 3 },
  gridTemplateColumns: {
    xs: 'minmax(0, 1fr)',
    md: 'repeat(2, minmax(0, 1fr))',
    xl: 'repeat(3, minmax(0, 1fr))',
  },
} as const;

/** Sección «Métricas de calidad»: una card de comparación por métrica, en una grilla adaptable. */
export function QualityMetricsSection({ metrics, isLoading = false, errorMessage }: QualityMetricsSectionProps) {
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

      {errorMessage ? (
        <Alert severity="error" variant="outlined">
          {errorMessage}
        </Alert>
      ) : isLoading ? (
        <Box aria-busy="true" sx={GRID_SX}>
          {Array.from({ length: 3 }).map((_, i) => (
            <BaseCard key={i} ariaLabel="Cargando métrica">
              <Skeleton variant="rounded" height={72} />
              <Skeleton variant="rounded" height={64} />
              <Skeleton variant="rounded" height={64} />
            </BaseCard>
          ))}
        </Box>
      ) : metrics.length === 0 ? (
        <BaseCard>
          <Typography variant="body2" color="text.secondary" sx={{ py: 3, textAlign: 'center' }}>
            Las métricas de calidad aún no están definidas.
          </Typography>
        </BaseCard>
      ) : (
        <Box sx={GRID_SX}>
          {metrics.map((metric) => (
            <MetricComparisonCard key={metric.id} metric={metric} />
          ))}
        </Box>
      )}
    </Box>
  );
}

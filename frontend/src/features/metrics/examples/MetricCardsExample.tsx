import Box from '@mui/material/Box';
import { MetricCard } from '../components/MetricCard';
import { MetricComparisonCard } from '../components/MetricComparisonCard';
import type { MetricComparison } from '../types';

const SAMPLE: MetricComparison = {
  id: 'coverage',
  name: 'Cobertura de requisitos',
  description: 'Porcentaje de requisitos con al menos un caso de prueba.',
  icon: 'coverage',
  betterWhen: 'higher',
  a: 86.5,
  b: 78.2,
};

/** Ejemplo de uso: versión simple (una ejecución) y versión de comparación (A vs B). */
export function MetricCardsExample() {
  return (
    <Box sx={{ display: 'grid', gap: 3, gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' } }}>
      <MetricCard metric={SAMPLE} value={SAMPLE.a} />
      <MetricComparisonCard metric={SAMPLE} />
    </Box>
  );
}

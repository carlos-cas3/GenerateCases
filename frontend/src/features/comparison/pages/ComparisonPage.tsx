import { useMemo } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Container from '@mui/material/Container';
import Typography from '@mui/material/Typography';
import CompareArrowsRoundedIcon from '@mui/icons-material/CompareArrowsRounded';
import { BaseCard } from '../../../components/cards';
import { HISTORY_STATUS_LABEL } from '../../history/constants';
import type { ExecutionRecord } from '../../history/types';
import { getCompareStatus } from '../../history/utils/comparison';
import { EMPTY_COMPARISON_SELECTION } from '../constants';
import { ExecutionSelectorCard } from '../components/ExecutionSelectorCard';
import { GeneratedArtifactsCard } from '../components/GeneratedArtifactsCard';
import { QualityMetricsSection } from '../components/QualityMetricsSection';
import type { MetricComparison } from '../../metrics/types';
import type { ComparisonSelection } from '../types';
import { buildArtifactRows } from '../utils/artifacts';
import { getOptionsA, getOptionsB } from '../utils/options';

export interface ComparisonPageProps {
  records: ExecutionRecord[];
  /**
   * La selección vive en el padre (App) para que persista al navegar a otras vistas:
   * esta página se desmonta al salir, pero el estado no.
   */
  selection: ComparisonSelection;
  onSelectionChange: (selection: ComparisonSelection) => void;
  /** Calcula las métricas de calidad del par elegido (aún sin definir: hoy es una función de demo). */
  getMetrics: (a: ExecutionRecord, b: ExecutionRecord) => MetricComparison[];
}

/** Selector de A/B arriba; los resultados aparecen debajo solo cuando el par es válido. */
export function ComparisonPage({ records, selection, onSelectionChange, getMetrics }: ComparisonPageProps) {
  // Se guardan ids y se derivan los registros: si una ejecución se elimina, la selección no queda colgada.
  const a = useMemo(() => records.find((r) => r.id === selection.aId) ?? null, [records, selection.aId]);
  const b = useMemo(() => records.find((r) => r.id === selection.bId) ?? null, [records, selection.bId]);

  const optionsA = useMemo(() => getOptionsA(records, b), [records, b]);
  const optionsB = useMemo(() => getOptionsB(records, a), [records, a]);

  const compareStatus = useMemo(() => (a && b ? getCompareStatus([a, b]) : null), [a, b]);
  // A debe ser con clustering y B sin él (los combobox ya lo garantizan; se valida igualmente).
  const pair = useMemo(
    () => (a && b && compareStatus?.canCompare && a.clustering && !b.clustering ? { a, b } : null),
    [a, b, compareStatus],
  );

  const metrics = useMemo(() => (pair ? getMetrics(pair.a, pair.b) : []), [pair, getMetrics]);
  const artifacts = useMemo(() => (pair ? buildArtifactRows(pair.a, pair.b) : []), [pair]);

  const incomplete = pair
    ? [
        pair.a.status !== 'completed' && `A: ${HISTORY_STATUS_LABEL[pair.a.status]}`,
        pair.b.status !== 'completed' && `B: ${HISTORY_STATUS_LABEL[pair.b.status]}`,
      ].filter(Boolean)
    : [];

  return (
    <Container maxWidth="xl" sx={{ py: { xs: 3, md: 5 } }}>
      <Box component="header" sx={{ mb: 3 }}>
        <Typography variant="h5" component="h1" sx={{ fontWeight: 700 }}>
          Comparación de ejecuciones
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Compara el efecto del clustering: una ejecución con clustering frente a otra sin él, del mismo documento.
        </Typography>
      </Box>

      <Box sx={{ display: 'grid', gap: { xs: 2, md: 3 }, gridTemplateColumns: 'minmax(0, 1fr)' }}>
        <ExecutionSelectorCard
          optionsA={optionsA}
          optionsB={optionsB}
          valueA={a}
          valueB={b}
          onChangeA={(next) => onSelectionChange({ ...selection, aId: next?.id ?? null })}
          onChangeB={(next) => onSelectionChange({ ...selection, bId: next?.id ?? null })}
          onClear={() => onSelectionChange(EMPTY_COMPARISON_SELECTION)}
          compareStatus={compareStatus}
        />

        {pair ? (
          <>
            {incomplete.length > 0 && (
              <Alert severity="warning" variant="outlined">
                Alguna ejecución no está completada ({incomplete.join(' · ')}). Los valores que aún no existen se
                muestran como «—».
              </Alert>
            )}
            <QualityMetricsSection metrics={metrics} />
            <GeneratedArtifactsCard rows={artifacts} />
          </>
        ) : (
          <BaseCard>
            <Box
              sx={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 1,
                py: 5,
                textAlign: 'center',
                color: 'text.secondary',
              }}
            >
              <CompareArrowsRoundedIcon sx={{ fontSize: 40 }} aria-hidden />
              <Typography variant="subtitle2" color="text.primary">
                Aún no hay una comparación
              </Typography>
              <Typography variant="body2" sx={{ maxWidth: 420 }}>
                Selecciona la ejecución A y la ejecución B para ver aquí las métricas de calidad y los artefactos
                generados.
              </Typography>
            </Box>
          </BaseCard>
        )}
      </Box>
    </Container>
  );
}

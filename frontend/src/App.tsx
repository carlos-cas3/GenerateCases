import { useState } from 'react';
import CssBaseline from '@mui/material/CssBaseline';
import { ThemeProvider } from '@mui/material/styles';
import { theme } from './theme/theme';
import { AppLayout } from './components/layout';
import { NAV_ITEMS } from './app/navigation';
import { EMPTY_COMPARISON_SELECTION } from './features/comparison/constants';
import { buildMockMetrics } from './features/comparison/mocks/comparisonMocks';
import { ComparisonPage } from './features/comparison/pages/ComparisonPage';
import type { ComparisonSelection } from './features/comparison/types';
import { GenerationPage } from './features/generation/pages/GenerationPage';
import { MOCK_HISTORY } from './features/history/mocks/historyMocks';
import { HistoryPage } from './features/history/pages/HistoryPage';
import type { ExecutionRecord } from './features/history/types';

export default function App() {
  // Estado simple para la demo. Con react-router, reemplázalo por rutas.
  const [active, setActive] = useState('generation');
  // Datos en memoria solo para la demo; después vendrán del backend.
  const [records, setRecords] = useState<ExecutionRecord[]>(MOCK_HISTORY);
  // Vive aquí (no en la página) para que la selección persista al cambiar de vista.
  const [comparison, setComparison] = useState<ComparisonSelection>(EMPTY_COMPARISON_SELECTION);

  const handleDelete = (targets: ExecutionRecord[]) => {
    // TODO: llamar al backend y recién entonces actualizar la lista.
    setRecords((prev) => prev.filter((r) => !targets.some((t) => t.id === r.id)));
  };

  // Desde el historial: A = la ejecución con clustering, B = la que no lo tiene.
  const handleCompareFromHistory = (pair: ExecutionRecord[]) => {
    setComparison({
      aId: pair.find((r) => r.clustering)?.id ?? null,
      bId: pair.find((r) => !r.clustering)?.id ?? null,
    });
    setActive('compare');
  };

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <AppLayout brand="TestGen" navItems={NAV_ITEMS} activeKey={active} onNavigate={setActive}>
        {active === 'generation' && <GenerationPage />}
        {active === 'history' && (
          <HistoryPage
            records={records}
            onCompare={handleCompareFromHistory}
            onView={() => {
              /* TODO: abrir el detalle de la ejecución */
            }}
            onEdit={() => {
              /* TODO: abrir la edición de la ejecución */
            }}
            onDelete={handleDelete}
          />
        )}
        {active === 'compare' && (
          <ComparisonPage
            records={records}
            selection={comparison}
            onSelectionChange={setComparison}
            getMetrics={buildMockMetrics}
          />
        )}
      </AppLayout>
    </ThemeProvider>
  );
}

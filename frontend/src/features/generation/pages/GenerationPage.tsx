import { useMemo, useState } from 'react';
import Box from '@mui/material/Box';
import Container from '@mui/material/Container';
import Typography from '@mui/material/Typography';
import { DocumentUploadCard } from '../components/DocumentUploadCard';
import { ExecutionProgressCard } from '../components/ExecutionProgressCard';
import { RecentExecutionsCard } from '../components/RecentExecutionsCard';
import { buildMockStages, MOCK_RECENT_EXECUTIONS } from '../mocks/generationMocks';

/**
 * ÚNICO lugar donde se decide la distribución.
 * Cada card recibe solo su `gridArea`; ancho, alto y orden salen de aquí.
 * Para cambiar el diseño basta con cambiar `ACTIVE_LAYOUT`.
 */
const LAYOUTS = {
  /** Las tres en una sola columna. */
  singleColumn: {
    columns: { xs: '1fr' },
    areas: { xs: '"upload" "progress" "recent"' },
  },
  /** Carga a todo el ancho; progreso e historial lado a lado debajo. */
  uploadOnTop: {
    columns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' },
    areas: { xs: '"upload" "progress" "recent"', md: '"upload upload" "progress recent"' },
  },
  /** Carga a la izquierda (alta); progreso y historial apilados a la derecha. */
  twoColumns: {
    columns: { xs: '1fr', md: 'minmax(0, 5fr) minmax(0, 7fr)' },
    areas: { xs: '"upload" "progress" "recent"', md: '"upload progress" "upload recent"' },
  },
  /** Proporciones distintas: carga estrecha, progreso ancho, historial debajo del progreso. */
  uneven: {
    columns: { xs: '1fr', lg: 'minmax(0, 1fr) minmax(0, 2fr)' },
    areas: { xs: '"upload" "progress" "recent"', lg: '"upload progress" "recent recent"' },
  },
} as const;

const ACTIVE_LAYOUT: keyof typeof LAYOUTS = 'twoColumns';

export function GenerationPage() {
  const [file, setFile] = useState<File | null>(null);
  const [semanticGrouping, setSemanticGrouping] = useState(true);

  const stages = useMemo(() => buildMockStages(semanticGrouping, 'running'), [semanticGrouping]);

  const handleSubmit = () => {
    // TODO: iniciar la ejecución en el backend con { file, semanticGrouping }.
  };

  const handleViewDetails = (_executionId: string) => {
    // TODO: navegar al detalle de la ejecución.
  };

  const layout = LAYOUTS[ACTIVE_LAYOUT];

  return (
    <Container maxWidth="xl" sx={{ py: { xs: 3, md: 5 } }}>
      <Box component="header" sx={{ mb: 3 }}>
        <Typography variant="h5" component="h1" sx={{ fontWeight: 700 }}>
          Generación de casos de prueba
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Carga un documento, sigue el progreso y consulta tus últimas ejecuciones.
        </Typography>
      </Box>

      <Box
        sx={{
          display: 'grid',
          gap: { xs: 2, md: 3 },
          gridTemplateColumns: layout.columns,
          gridTemplateAreas: layout.areas,
        }}
      >
        <DocumentUploadCard
          sx={{ gridArea: 'upload' }}
          file={file}
          onFileChange={setFile}
          semanticGrouping={semanticGrouping}
          onSemanticGroupingChange={setSemanticGrouping}
          onSubmit={handleSubmit}
        />
        <ExecutionProgressCard sx={{ gridArea: 'progress' }} stages={stages} defaultExpandedIds={[stages[0].id]} />
        <RecentExecutionsCard
          sx={{ gridArea: 'recent' }}
          executions={MOCK_RECENT_EXECUTIONS}
          maxItems={3}
          onViewDetails={handleViewDetails}
        />
      </Box>
    </Container>
  );
}

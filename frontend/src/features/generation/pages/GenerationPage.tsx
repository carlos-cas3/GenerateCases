import { useCallback, useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Container from '@mui/material/Container';
import Typography from '@mui/material/Typography';
import { DocumentUploadCard } from '../components/DocumentUploadCard';
import { ExecutionProgressCard } from '../components/ExecutionProgressCard';
import { RecentExecutionsCard } from '../components/RecentExecutionsCard';
import { useActiveGenerationId } from '../hooks/useActiveGenerationId';
import { useExecutionProgress } from '../hooks/useExecutionProgress';
import { useRecentExecutions } from '../hooks/useRecentExecutions';
import { useStartGeneration } from '../hooks/useStartGeneration';
import { isActiveStatus } from '../services/generationMappers';
import { DEV_DOCUMENT_ID } from '../services/generationService';
import type { Generation } from '../types';

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
  /** Carga y recientes apilados en la columna izquierda (50%); pipeline solo a la derecha (50%). */
  uploadRecentLeft: {
    columns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' },
    areas: { xs: '"upload" "recent" "progress"', md: '"upload progress" "recent progress"' },
  },
} as const;

const ACTIVE_LAYOUT: keyof typeof LAYOUTS = 'uploadRecentLeft';

const RECENT_EXECUTIONS_LIMIT = 3;
/** La primera etapa arranca expandida (las fallidas se expanden siempre). */
const DEFAULT_EXPANDED_IDS = ['p1'];

const DEV_DOCUMENT_NOTICE = DEV_DOCUMENT_ID
  ? 'Fase de pruebas: se usa un documento de ejemplo; el archivo seleccionado no se envía.'
  : 'Falta configurar VITE_DEV_DOCUMENT_ID en el .env del frontend: no se puede iniciar una generación.';

export function GenerationPage() {
  const [file, setFile] = useState<File | null>(null);
  const [semanticGrouping, setSemanticGrouping] = useState(true);

  const recent = useRecentExecutions(RECENT_EXECUTIONS_LIMIT);
  const active = useActiveGenerationId(recent.executions);
  const progress = useExecutionProgress(active.generationId, active.clear);

  const reloadRecent = recent.reload;
  const setActive = active.setActive;
  const handleStarted = useCallback(
    (started: Generation) => {
      setActive(started.id);
      reloadRecent();
    },
    [setActive, reloadRecent],
  );
  const generation = useStartGeneration(handleStarted);

  // Cuando la generación seguida termina (completed/failed) y las recientes aún muestran otro
  // estado para ella, se recargan una vez.
  const isTrackingActive = isActiveStatus(progress.status);
  const trackedInRecent = recent.executions.find((e) => e.id === progress.generation?.id);
  const recentIsStale =
    !!progress.status && !isTrackingActive && !!trackedInRecent && trackedInRecent.status !== progress.status;
  useEffect(() => {
    if (recentIsStale) reloadRecent();
  }, [recentIsStale, reloadRecent]);

  const handleSubmit = async () => {
    if (!file) return;
    // TODO Fase 2: POST /documents. Hoy el archivo no se envía (se usa VITE_DEV_DOCUMENT_ID).
    await generation.start({ file, semanticGrouping });
  };

  /** Retoma el seguimiento de esa generación en esta misma vista (`/?g=<id>`). */
  const handleViewDetails = (executionId: string) => setActive(executionId);

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

      {active.notice && (
        <Alert severity="warning" variant="outlined" onClose={active.dismissNotice} sx={{ mb: 3 }}>
          {active.notice}
        </Alert>
      )}

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
          isSubmitting={generation.isCreating}
          // Una sola generación seguida a la vez (regla de interfaz, no garantía del backend).
          submitDisabled={!DEV_DOCUMENT_ID || isTrackingActive || (!!active.generationId && progress.isLoading)}
          errorMessage={generation.error}
          notice={DEV_DOCUMENT_NOTICE}
        />
        <ExecutionProgressCard
          // Cada generación empieza con su propio estado de expansión.
          key={active.generationId ?? 'none'}
          sx={{ gridArea: 'progress' }}
          status={progress.status}
          stages={progress.stages}
          caption={progress.generation?.documentName}
          failureMessage={progress.generation?.errorMessage}
          isLoading={progress.isLoading}
          isReconnecting={progress.isReconnecting}
          errorMessage={progress.error}
          onRetry={progress.reload}
          defaultExpandedIds={DEFAULT_EXPANDED_IDS}
          emptyMessage="No hay ninguna ejecución en seguimiento. Inicia una generación para ver aquí su progreso."
        />
        <RecentExecutionsCard
          sx={{ gridArea: 'recent' }}
          executions={recent.executions}
          maxItems={RECENT_EXECUTIONS_LIMIT}
          isLoading={recent.isLoading}
          errorMessage={recent.error}
          onRetry={recent.reload}
          onViewDetails={handleViewDetails}
        />
      </Box>
    </Container>
  );
}

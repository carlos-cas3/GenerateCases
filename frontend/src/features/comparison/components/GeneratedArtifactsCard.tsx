import type { SxProps, Theme } from '@mui/material/styles';
import { BaseCard } from '../../../components/cards';
import type { ComparisonRow } from '../types';
import { ComparisonTable } from './ComparisonTable';

export interface GeneratedArtifactsCardProps {
  rows: ComparisonRow[];
  isLoading?: boolean;
  sx?: SxProps<Theme>;
}

export function GeneratedArtifactsCard({ rows, isLoading, sx }: GeneratedArtifactsCardProps) {
  return (
    <BaseCard
      title="Artefactos generados"
      description="Cantidad de historias de usuario, requisitos funcionales y casos de prueba que produjo cada ejecución."
      sx={sx}
    >
      <ComparisonTable
        ariaLabel="Comparación de artefactos generados"
        firstColumnLabel="Artefacto"
        rows={rows}
        isLoading={isLoading}
        emptyMessage="Esta comparación no tiene artefactos."
      />
    </BaseCard>
  );
}

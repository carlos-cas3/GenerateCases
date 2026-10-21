import type { ExecutionRecord } from '../../history/types';
import type { ComparisonRow } from '../types';

/** Filas reales de «Artefactos generados» (HU, RF y CP salen del propio registro de cada ejecución). */
export function buildArtifactRows(a: ExecutionRecord, b: ExecutionRecord): ComparisonRow[] {
  return [
    { id: 'hu', label: 'Historias de usuario (HU)', a: a.huCount, b: b.huCount, unit: 'count' },
    { id: 'rf', label: 'Requisitos funcionales (RF)', a: a.rfCount, b: b.rfCount, unit: 'count' },
    { id: 'cp', label: 'Casos de prueba (CP)', a: a.cpCount, b: b.cpCount, unit: 'count' },
  ];
}

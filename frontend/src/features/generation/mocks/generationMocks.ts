/**
 * Datos ficticios SOLO para la demostración visual.
 * Hoy solo los usa el detalle de historial (`getExecutionPipeline`); se retiran en la Fase 2.
 */
import { getStageDefinitions } from '../utils/stageDefinitions';
import type { ExecutionStage, ExecutionStatus } from '../types';

/** Construye etapas de ejemplo: las primeras completadas, una en proceso y el resto pendientes. */
export function buildMockStages(
  semanticGrouping: boolean,
  scenario: 'running' | 'failed' | 'completed' = 'running',
): ExecutionStage[] {
  const defs = getStageDefinitions(semanticGrouping);
  const currentIndex = scenario === 'completed' ? defs.length : 2;

  return defs.map((def, i): ExecutionStage => {
    let status: ExecutionStatus = 'pending';
    if (i < currentIndex) status = 'completed';
    else if (i === currentIndex) status = scenario === 'failed' ? 'failed' : 'in_progress';

    return {
      id: def.id,
      title: def.title,
      summary: def.summary,
      status,
      durationLabel: status === 'completed' ? `${6 + i * 3} s` : undefined,
      details:
        status === 'completed'
          ? `Etapa finalizada correctamente (${12 + i * 4} elementos procesados).`
          : status === 'failed'
            ? 'No se pudo completar la etapa. Revisa el formato del documento e inténtalo de nuevo.'
            : undefined,
    };
  });
}

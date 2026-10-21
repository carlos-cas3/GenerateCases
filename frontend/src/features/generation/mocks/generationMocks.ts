/**
 * Datos ficticios SOLO para la demostración visual.
 * Se reemplazan por datos reales cuando exista el backend.
 */
import { getStageDefinitions } from '../utils/stageDefinitions';
import type { ExecutionStage, ExecutionStatus, RecentExecution } from '../types';

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

export const MOCK_RECENT_EXECUTIONS: RecentExecution[] = [
  { id: 'exec-103', documentName: 'historias_usuario_pagos_v2.pdf', createdAt: '2026-10-16T16:42:00', status: 'in_progress' },
  { id: 'exec-102', documentName: 'requisitos_modulo_reservas.docx', createdAt: '2026-10-15T11:05:00', status: 'completed' },
  { id: 'exec-101', documentName: 'backlog_sprint_4.txt', createdAt: '2026-10-13T09:18:00', status: 'failed' },
  { id: 'exec-100', documentName: 'historias_login.pdf', createdAt: '2026-10-10T18:30:00', status: 'completed' },
];

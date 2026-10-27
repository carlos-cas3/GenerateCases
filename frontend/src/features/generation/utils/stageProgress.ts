import type { ExecutionStage, StageStatus } from '../types';

/** Una etapa terminó sin error si se completó o se omitió (el backend trata ambas como finales). */
export const isFinalStage = (status: StageStatus) => status === 'completed' || status === 'skipped';

/**
 * Avance visual: etapas finalizadas (completadas u omitidas) sobre el total.
 * No es una métrica de calidad ni sustituye al estado global de la generación.
 */
export function stageProgress(stages: ExecutionStage[]) {
  const completed = stages.filter((s) => s.status === 'completed').length;
  const skipped = stages.filter((s) => s.status === 'skipped').length;
  const total = stages.length;
  const percent = total ? Math.round(((completed + skipped) / total) * 100) : 0;
  return { completed, skipped, total, percent };
}

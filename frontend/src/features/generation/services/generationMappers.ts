/** Adaptadores puros DTO del backend → tipos de la UI. Sin efectos ni dependencias de React. */
import type { ExecutionStatus, StageStatus } from '@/shared/types';
import { getStageUi } from '../utils/stageUi';
import type { ExecutionStage, Generation, RecentExecution } from '../types';
import type {
  ApiGenerationStatus,
  ApiStageStatus,
  GenerationDto,
  GenerationListDto,
  GenerationStageDto,
} from './generationDto';

const GENERATION_STATUS: Record<ApiGenerationStatus, ExecutionStatus> = {
  queued: 'pending',
  running: 'in_progress',
  completed: 'completed',
  failed: 'failed',
};

const STAGE_STATUS: Record<ApiStageStatus, StageStatus> = {
  pending: 'pending',
  running: 'in_progress',
  completed: 'completed',
  failed: 'failed',
  skipped: 'skipped',
};

export const mapGenerationStatus = (status: ApiGenerationStatus): ExecutionStatus => GENERATION_STATUS[status];
export const mapStageStatus = (status: ApiStageStatus): StageStatus => STAGE_STATUS[status];

/** «850 ms», «12 s», «2 min 5 s». Solo si existen ambas marcas de tiempo. */
export function formatDuration(startedAt: string | null, completedAt: string | null): string | undefined {
  if (!startedAt || !completedAt) return undefined;
  const ms = Date.parse(completedAt) - Date.parse(startedAt);
  if (!Number.isFinite(ms) || ms < 0) return undefined;
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds} s`;
  const rest = seconds % 60;
  return `${Math.floor(seconds / 60)} min${rest ? ` ${rest} s` : ''}`;
}

export function mapStage(dto: GenerationStageDto): ExecutionStage {
  const errorMessage = dto.error_message ?? undefined;
  return {
    id: dto.key,
    // Nombre del catálogo del backend; la UI no define nombres alternativos.
    title: dto.name,
    summary: getStageUi(dto.key)?.summary,
    status: mapStageStatus(dto.status),
    // Solo se muestra el motivo que entregue la API; nunca se infiere (p. ej. de una etapa omitida).
    details: errorMessage,
    errorMessage,
    durationLabel: formatDuration(dto.started_at, dto.completed_at),
    startedAt: dto.started_at ?? undefined,
    completedAt: dto.completed_at ?? undefined,
  };
}

/** Etapas en el orden que indica el backend (`order`), sin asumir cuántas son. */
export const mapStages = (stages: GenerationStageDto[]): ExecutionStage[] =>
  [...stages].sort((a, b) => a.order - b.order).map(mapStage);

export function mapGeneration(dto: GenerationDto): Generation {
  return {
    id: dto.id,
    documentId: dto.document_id,
    documentName: dto.document_name,
    createdAt: dto.created_at,
    status: mapGenerationStatus(dto.status),
    semanticGrouping: dto.configuration.semantic_clustering_enabled,
    stages: mapStages(dto.stages),
    errorMessage: dto.error_message ?? undefined,
    startedAt: dto.started_at ?? undefined,
    completedAt: dto.completed_at ?? undefined,
  };
}

export const mapRecentExecution = (dto: GenerationDto): RecentExecution => ({
  id: dto.id,
  documentName: dto.document_name,
  createdAt: dto.created_at,
  status: mapGenerationStatus(dto.status),
});

export const mapRecentExecutions = (list: GenerationListDto): RecentExecution[] =>
  list.items.map(mapRecentExecution);

/** Una generación sigue activa (y se sigue consultando) mientras esté en cola o en ejecución. */
export const isActiveStatus = (status: ExecutionStatus | undefined): boolean =>
  status === 'pending' || status === 'in_progress';

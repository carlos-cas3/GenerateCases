/**
 * Tipos crudos del contrato del backend (espejo de `Generation`, `GenerationStage` y
 * `GenerationList` en `backend/docs/openapi.yaml`, verificados contra `__fixtures__/`).
 * No salen de `services/`: la UI usa los tipos de `../types` a través de `generationMappers`.
 */

export type ApiGenerationStatus = 'queued' | 'running' | 'completed' | 'failed';
export type ApiStageStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped';

export interface GenerationStageDto {
  key: string;
  name: string;
  status: ApiStageStatus;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  order: number;
}

export interface GenerationConfigurationDto {
  semantic_clustering_enabled: boolean;
  method_type: string | null;
}

/** En la Fase 1 siempre llega `null`; se tipa sin detalle porque la UI no lo usa. */
export type MetricSummaryDto = Record<string, unknown>;

export interface GenerationDto {
  id: string;
  document_id: string;
  document_name: string;
  status: ApiGenerationStatus;
  configuration: GenerationConfigurationDto;
  stages: GenerationStageDto[];
  summary: MetricSummaryDto | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface PaginationDto {
  limit: number;
  offset: number;
  total: number;
}

export interface GenerationListDto {
  items: GenerationDto[];
  pagination: PaginationDto;
}

export interface CreateGenerationRequestDto {
  document_id: string;
  configuration?: {
    semantic_clustering_enabled?: boolean;
  };
}

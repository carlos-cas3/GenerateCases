/**
 * Definición de las etapas del pipeline (solo títulos y orden).
 * El estado de cada etapa lo aporta quien orquesta la ejecución.
 * La etapa de agrupación semántica solo existe si la opción está activada.
 */
export interface StageDefinition {
  id: string;
  title: string;
  summary: string;
  onlyWithSemanticGrouping?: boolean;
}

const ALL_STAGES: StageDefinition[] = [
  {
    id: 'document-processing',
    title: 'Procesamiento y validación del documento',
    summary: 'Lectura, limpieza y verificación del formato.',
  },
  {
    id: 'requirements-extraction',
    title: 'Extracción de requisitos funcionales',
    summary: 'Identificación de historias de usuario y criterios.',
  },
  {
    id: 'semantic-grouping',
    title: 'Representación y agrupación semántica',
    summary: 'Embeddings y agrupación de requisitos afines.',
    onlyWithSemanticGrouping: true,
  },
  {
    id: 'test-generation',
    title: 'Construcción del contexto y generación de casos de prueba',
    summary: 'Prompt con contexto y generación con el LLM.',
  },
  {
    id: 'evaluation',
    title: 'Evaluación de resultados',
    summary: 'Revisión de calidad y cobertura de los casos.',
  },
];

export function getStageDefinitions(semanticGrouping: boolean): StageDefinition[] {
  return ALL_STAGES.filter((s) => semanticGrouping || !s.onlyWithSemanticGrouping);
}

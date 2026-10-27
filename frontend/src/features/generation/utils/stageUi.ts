/**
 * Presentación de las etapas del pipeline (solo descripciones en español por `key`).
 * La API es la fuente de verdad de `key`, `name`, `order` y `status`: aquí no se definen nombres
 * técnicos ni etapas. Una clave desconocida se muestra igual, solo sin descripción.
 */
interface StageUi {
  summary: string;
}

const STAGE_UI: Record<string, StageUi> = {
  p1: { summary: 'Estructura las historias de usuario del documento.' },
  p2: { summary: 'Identifica los requisitos funcionales de cada historia.' },
  p3: { summary: 'Representa los requisitos como vectores semánticos.' },
  p4: { summary: 'Agrupa requisitos afines antes de generar los casos.' },
  p5: { summary: 'Prepara el contexto de entrada para la generación.' },
  p6: { summary: 'Genera los casos de prueba con el modelo de lenguaje.' },
  p7: { summary: 'Calcula métricas de calidad sobre los resultados.' },
};

export const getStageUi = (key: string): StageUi | undefined => STAGE_UI[key];

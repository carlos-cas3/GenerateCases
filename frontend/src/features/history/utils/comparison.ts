import { COMPARE_SELECTION_SIZE } from '../constants';
import type { ExecutionRecord } from '../types';
import { splitFileName } from './fileName';

/** Nombre del documento sin la extensión: "historias.pdf" y "historias.docx" son el mismo documento. */
export const getDocumentBaseName = (documentName: string) => splitFileName(documentName).base.trim();

export function isSameDocument(a: ExecutionRecord, b: ExecutionRecord): boolean {
  return getDocumentBaseName(a.documentName) === getDocumentBaseName(b.documentName);
}

export interface CompareStatus {
  canCompare: boolean;
  /** Explica por qué se puede o no comparar. */
  message: string;
}

/**
 * Regla de negocio: se comparan exactamente 2 ejecuciones del MISMO documento
 * (mismo nombre; el formato no importa), una con clustering y otra sin él. Con más de 2 seleccionadas solo se puede eliminar.
 */
export function getCompareStatus(selected: ExecutionRecord[]): CompareStatus {
  if (selected.length > COMPARE_SELECTION_SIZE) {
    return {
      canCompare: false,
      message: `Hay ${selected.length} ejecuciones seleccionadas: solo se pueden eliminar. Para comparar, deja únicamente 2.`,
    };
  }

  const [a, b] = selected;

  if (!a) {
    return {
      canCompare: false,
      message: 'Selecciona dos ejecuciones del mismo documento (el formato no importa): una con clustering y otra sin él.',
    };
  }
  if (!b) {
    return { canCompare: false, message: 'Selecciona una segunda ejecución del mismo documento.' };
  }
  if (!isSameDocument(a, b)) {
    return {
      canCompare: false,
      message: 'Las dos ejecuciones deben ser del mismo documento (el formato no importa).',
    };
  }
  if (a.clustering === b.clustering) {
    return { canCompare: false, message: 'Una ejecución debe tener clustering y la otra no.' };
  }
  return { canCompare: true, message: 'Listas para comparar.' };
}

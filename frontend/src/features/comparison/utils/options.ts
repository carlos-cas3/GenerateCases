import { getDocumentBaseName, isSameDocument } from '@/features/history';
import type { ExecutionRecord } from '@/features/history';

/** Orden estable para el listado: por nombre y, dentro de un documento, la más reciente primero. */
function byDocumentThenDate(a: ExecutionRecord, b: ExecutionRecord) {
  return (
    getDocumentBaseName(a.documentName).localeCompare(getDocumentBaseName(b.documentName), 'es', {
      numeric: true,
      sensitivity: 'base',
    }) ||
    new Date(b.uploadedAt).getTime() - new Date(a.uploadedAt).getTime() ||
    a.id.localeCompare(b.id)
  );
}

/**
 * Opciones de cada combobox. Cada lista se restringe al documento que ya eligió el otro,
 * así es imposible armar un par inválido, y solo se ofrecen ejecuciones ya completadas
 * (de lo contrario no hay resultados que comparar):
 * - A: ejecuciones CON clustering
 * - B: ejecuciones SIN clustering
 */
function getOptions(
  records: ExecutionRecord[],
  clustering: boolean,
  selectedOther: ExecutionRecord | null,
) {
  return records
    .filter(
      (r) =>
        r.status === 'completed' &&
        r.clustering === clustering &&
        (!selectedOther || isSameDocument(r, selectedOther)),
    )
    .sort(byDocumentThenDate);
}

export function getOptionsA(records: ExecutionRecord[], selectedB: ExecutionRecord | null) {
  return getOptions(records, true, selectedB);
}

export function getOptionsB(records: ExecutionRecord[], selectedA: ExecutionRecord | null) {
  return getOptions(records, false, selectedA);
}

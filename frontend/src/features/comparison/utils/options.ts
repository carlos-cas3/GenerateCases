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
 * así es imposible armar un par inválido:
 * - A: ejecuciones CON clustering
 * - B: ejecuciones SIN clustering
 */
export function getOptionsA(records: ExecutionRecord[], selectedB: ExecutionRecord | null) {
  return records
    .filter((r) => r.clustering && (!selectedB || isSameDocument(r, selectedB)))
    .sort(byDocumentThenDate);
}

export function getOptionsB(records: ExecutionRecord[], selectedA: ExecutionRecord | null) {
  return records
    .filter((r) => !r.clustering && (!selectedA || isSameDocument(r, selectedA)))
    .sort(byDocumentThenDate);
}

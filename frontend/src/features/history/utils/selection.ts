import type { ExecutionRecord } from '../types';

/** Agrega o quita un id de la selección. No hay tope: la selección múltiple sirve para eliminar. */
export function toggleId(ids: string[], id: string): string[] {
  return ids.includes(id) ? ids.filter((item) => item !== id) : [...ids, id];
}

/**
 * «Ver» y «Editar» actúan sobre una ejecución a la vez: con 2 o más seleccionadas se bloquean.
 * «Eliminar» nunca se bloquea porque sí admite varias.
 */
export function isMultiSelection(selected: ExecutionRecord[]): boolean {
  return selected.length >= 2;
}

/**
 * Qué se elimina al pulsar el icono de una fila:
 * - si la fila forma parte de la selección → toda la selección;
 * - si no → solo esa fila.
 */
export function getDeleteTargets(row: ExecutionRecord, selected: ExecutionRecord[]): ExecutionRecord[] {
  return selected.some((item) => item.id === row.id) ? selected : [row];
}

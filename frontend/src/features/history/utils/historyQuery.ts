import type { ExecutionRecord, HistoryFilters, SortState } from '../types';

/** Minúsculas y sin tildes, para que "Reservas" coincida con "reservás". */
const normalize = (value: string) =>
  value.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase().trim();

export function hasActiveFilters(filters: HistoryFilters) {
  return filters.query.trim() !== '' || filters.status !== 'all' || filters.clustering !== 'all';
}

export function filterRecords(records: ExecutionRecord[], filters: HistoryFilters): ExecutionRecord[] {
  const query = normalize(filters.query);
  return records.filter((record) => {
    if (query && !normalize(record.documentName).includes(query)) return false;
    if (filters.status !== 'all' && record.status !== filters.status) return false;
    if (filters.clustering !== 'all' && record.clustering !== (filters.clustering === 'yes')) return false;
    return true;
  });
}

/** Compara números dejando los valores `null` siempre al final, sin importar el sentido. */
function compareNullable(a: number | null, b: number | null, factor: number) {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return factor * (a - b);
}

export function sortRecords(records: ExecutionRecord[], sort: SortState): ExecutionRecord[] {
  const factor = sort.direction === 'asc' ? 1 : -1;

  return [...records].sort((a, b) => {
    let result = 0;
    switch (sort.key) {
      case 'documentName':
        result = factor * a.documentName.localeCompare(b.documentName, 'es', { numeric: true, sensitivity: 'base' });
        break;
      case 'uploadedAt':
        result = factor * (new Date(a.uploadedAt).getTime() - new Date(b.uploadedAt).getTime());
        break;
      default:
        result = compareNullable(a[sort.key], b[sort.key], factor);
    }
    // Desempate estable: más reciente primero y luego por id.
    return result || new Date(b.uploadedAt).getTime() - new Date(a.uploadedAt).getTime() || a.id.localeCompare(b.id);
  });
}

export function paginate<T>(items: T[], page: number, pageSize: number): T[] {
  return items.slice(page * pageSize, page * pageSize + pageSize);
}

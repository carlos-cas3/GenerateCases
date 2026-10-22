import type { ExecutionRecord, HistoryFilters, SortState } from "../types";

/** Relevancia de una coincidencia de nombre: menor = más relevante. */
export const MATCH_RANK = { prefix: 0, partial: 1 } as const;
export type MatchRank = (typeof MATCH_RANK)[keyof typeof MATCH_RANK];

/**
 * Relevancia del nombre COMPLETO (con extensión) frente a una búsqueda ya normalizada.
 * - prefijo: el nombre empieza con el texto → más relevante
 * - parcial: el texto aparece en cualquier otro punto (incluida la extensión) → después
 * - `null`: no coincide
 */

export function getMatchRank(
    documentName: string,
    normalizedQuery: string,
): MatchRank | null {
    const name = normalize(documentName);
    if (name.startsWith(normalizedQuery)) return MATCH_RANK.prefix;
    return name.includes(normalizedQuery) ? MATCH_RANK.partial : null;
}

/** Minúsculas y sin tildes, para que "Reservas" coincida con "reservás". */
const normalize = (value: string) =>
    value
        .normalize("NFD")
        .replace(/\p{Diacritic}/gu, "")
        .toLowerCase()
        .trim();

export function hasActiveFilters(filters: HistoryFilters) {
    return (
        filters.query.trim() !== "" ||
        filters.status !== "all" ||
        filters.clustering !== "all"
    );
}

export function filterRecords(
    records: ExecutionRecord[],
    filters: HistoryFilters,
): ExecutionRecord[] {
    const query = normalize(filters.query);
    return records.filter((record) => {
        if (query && getMatchRank(record.documentName, query) === null)
            return false;
        if (filters.status !== "all" && record.status !== filters.status)
            return false;
        if (
            filters.clustering !== "all" &&
            record.clustering !== (filters.clustering === "yes")
        )
            return false;
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

/**
 * Con búsqueda activa, la relevancia es el criterio principal; el orden elegido en la tabla
 * ordena dentro de cada nivel. Sin búsqueda, solo aplica el orden elegido.
 */

export function sortRecords(
    records: ExecutionRecord[],
    sort: SortState,
    query = "",
): ExecutionRecord[] {
    const factor = sort.direction === "asc" ? 1 : -1;
    const normalizedQuery = normalize(query);

    // Se calcula una vez por registro (no en cada comparación del sort)
    const ranks = normalizedQuery
        ? new Map(
            records.map((r) => [
                r.id,
                getMatchRank(r.documentName, normalizedQuery) ??
                    MATCH_RANK.partial,
            ]),
        )
        : null;
    return [...records].sort((a, b) => {
        const byRelevance = ranks
            ? (ranks.get(a.id) ?? MATCH_RANK.partial) -
            (ranks.get(b.id) ?? MATCH_RANK.partial)
            : 0;
        if (byRelevance) return byRelevance;

        let result: number;

        switch (sort.key) {
            case "documentName": {
                result =
                    factor *
                    a.documentName.localeCompare(b.documentName, "es", {
                        numeric: true,
                        sensitivity: "base",
                    });
                break;
            }

            case "uploadedAt": {
                result =
                    factor *
                    (new Date(a.uploadedAt).getTime() -
                        new Date(b.uploadedAt).getTime());
                break;
            }

            default: {
                result = compareNullable(a[sort.key], b[sort.key], factor);
                break;
            }
        }

        // Desempate estable: más reciente primero y luego por id.
        return (
            result ||
            new Date(b.uploadedAt).getTime() -
                new Date(a.uploadedAt).getTime() ||
            a.id.localeCompare(b.id)
        );
    });
}

export function paginate<T>(items: T[], page: number, pageSize: number): T[] {
    return items.slice(page * pageSize, page * pageSize + pageSize);
}

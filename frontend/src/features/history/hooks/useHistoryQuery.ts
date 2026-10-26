import { useCallback, useMemo, useState } from "react";
import {
    DEFAULT_DIRECTION,
    DEFAULT_FILTERS,
    DEFAULT_SORT,
    PAGE_SIZE_OPTIONS,
} from "../constants";
import type { PageSize } from "../constants";
import type { ExecutionRecord, HistoryFilters, SortKey } from "../types";
import {
    filterRecords,
    hasActiveFilters,
    paginate,
    sortRecords,
} from "../utils/historyQuery";

/**
 * Estado y derivación de la tabla: filtros → orden → paginación.
 * Hoy trabaja sobre un arreglo en memoria; si luego pagina el backend,
 * solo cambia este hook y las cards siguen igual.
 */
export function useHistoryQuery(records: ExecutionRecord[]) {
    const [filters, setFilters] = useState<HistoryFilters>(DEFAULT_FILTERS);
    const [sort, setSort] = useState(DEFAULT_SORT);
    const [page, setPage] = useState(0);
    const [pageSize, setPageSize] = useState<PageSize>(PAGE_SIZE_OPTIONS[0]);

    const filtered = useMemo(
        () => filterRecords(records, filters),
        [records, filters],
    );
    const sorted = useMemo(
        () => sortRecords(filtered, sort, filters.query),
        [filtered, sort, filters.query],
    );

    const lastPage = Math.max(0, Math.ceil(sorted.length / pageSize) - 1);
    const currentPage = Math.min(page, lastPage);
    const rows = useMemo(
        () => paginate(sorted, currentPage, pageSize),
        [sorted, currentPage, pageSize],
    );

    const changeFilters = useCallback((next: HistoryFilters) => {
        setFilters(next);
        setPage(0);
    }, []);

    const clearFilters = useCallback(
        () => changeFilters(DEFAULT_FILTERS),
        [changeFilters],
    );

    const changeSort = useCallback((key: SortKey) => {
        setSort((prev) =>
            prev.key === key
                ? { key, direction: prev.direction === "asc" ? "desc" : "asc" }
                : { key, direction: DEFAULT_DIRECTION[key] },
        );
        setPage(0);
    }, []);

    const changePageSize = useCallback((size: PageSize) => {
        setPageSize(size);
        setPage(0);
    }, []);

    return {
        filters,
        changeFilters,
        clearFilters,
        hasActiveFilters: hasActiveFilters(filters),
        sort,
        changeSort,
        page: currentPage,
        setPage,
        pageSize,
        changePageSize,
        rows,
        totalCount: sorted.length,
    };
}

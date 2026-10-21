import { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Container from "@mui/material/Container";
import Typography from "@mui/material/Typography";
import { CompareButton } from "../components/CompareButton";
import { ConfirmDeleteDialog } from "../components/ConfirmDeleteDialog";
import { ExecutionFiltersCard } from "../components/ExecutionFiltersCard";
import { ExecutionHistoryTableCard } from "../components/ExecutionHistoryTableCard";
import { useExecutions } from "../hooks/useExecutions";
import { useHistoryQuery } from "../hooks/useHistoryQuery";
import type { ExecutionRecord } from "../types";
import { getCompareStatus } from "../utils/comparison";
import { toggleId } from "../utils/selection";

export interface HistoryPageProps {
    /**
     * Se invoca con las 2 ejecuciones a comparar (solo si cumplen la regla).
     * La página no sabe adónde se navega: eso lo decide quien compone las features (app/routes).
     */
    onCompare: (pair: ExecutionRecord[]) => void;
    onView?: (record: ExecutionRecord) => void;
    onEdit?: (record: ExecutionRecord) => void;
}

/** Orquesta header (con «Comparar»), filtros, tabla y modal de eliminación. */
export function HistoryPage({ onCompare, onView, onEdit }: HistoryPageProps) {
    const { records, isLoading, error, reload, remove } = useExecutions();
    const query = useHistoryQuery(records);

    // Se guardan ids y se derivan los registros: si se elimina o actualiza uno, la selección no queda obsoleta.
    // La selección se conserva al cambiar de página o de filtros.
    const [selectedIds, setSelectedIds] = useState<string[]>([]);
    const selected = useMemo(
        () => records.filter((r) => selectedIds.includes(r.id)),
        [records, selectedIds],
    );
    const compareStatus = useMemo(() => getCompareStatus(selected), [selected]);

    const [deleteTargets, setDeleteTargets] = useState<ExecutionRecord[]>([]);
    const [deleteOpen, setDeleteOpen] = useState(false);
    const [isDeleting, setIsDeleting] = useState(false);
    const [deleteError, setDeleteError] = useState<string>();

    const requestDelete = (targets: ExecutionRecord[]) => {
        setDeleteTargets(targets);
        setDeleteError(undefined);
        setDeleteOpen(true);
    };

    const confirmDelete = async () => {
        setIsDeleting(true);
        setDeleteError(undefined);
        try {
            await remove(deleteTargets);
            setSelectedIds((ids) =>
                ids.filter((id) => !deleteTargets.some((t) => t.id === id)),
            );
            setDeleteOpen(false);
        } catch {
            setDeleteError(
                "No se pudo completar la eliminación. Inténtalo nuevamente.",
            );
        } finally {
            setIsDeleting(false);
        }
    };

    return (
        <Container maxWidth="xl" sx={{ py: { xs: 3, md: 5 } }}>
            <Box
                component="header"
                sx={{
                    mb: 3,
                    display: "flex",
                    alignItems: "flex-start",
                    justifyContent: "space-between",
                    gap: 2,
                    flexWrap: "wrap",
                }}
            >
                <Box>
                    <Typography
                        variant="h5"
                        component="h1"
                        sx={{ fontWeight: 700 }}
                    >
                        Historial de ejecuciones
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                        Busca, filtra, compara y administra las generaciones
                        realizadas.
                    </Typography>
                </Box>
                {/* Siempre pegado a la derecha del header; desactivado hasta que la selección sea válida. */}
                <Box sx={{ ml: "auto", flexShrink: 0 }}>
                    <CompareButton
                        status={compareStatus}
                        onClick={() => onCompare(selected)}
                    />
                </Box>
            </Box>

            <Box
                sx={{
                    display: "grid",
                    gap: { xs: 2, md: 3 },
                    gridTemplateColumns: "minmax(0, 1fr)",
                }}
            >
                <ExecutionFiltersCard
                    filters={query.filters}
                    onFiltersChange={query.changeFilters}
                    onClear={query.clearFilters}
                    hasActiveFilters={query.hasActiveFilters}
                />
                <ExecutionHistoryTableCard
                    rows={query.rows}
                    totalCount={query.totalCount}
                    hasActiveFilters={query.hasActiveFilters}
                    onClearFilters={query.clearFilters}
                    sort={query.sort}
                    onSortChange={query.changeSort}
                    page={query.page}
                    pageSize={query.pageSize}
                    onPageChange={query.setPage}
                    onPageSizeChange={query.changePageSize}
                    selected={selected}
                    onToggleSelect={(record) =>
                        setSelectedIds((ids) => toggleId(ids, record.id))
                    }
                    onClearSelection={() => setSelectedIds([])}
                    compareStatus={compareStatus}
                    // TODO: abrir el detalle / la edición de la ejecución.
                    onView={(record) => onView?.(record)}
                    onEdit={(record) => onEdit?.(record)}
                    onDeleteRequest={requestDelete}
                    isLoading={isLoading}
                    errorMessage={error}
                    onRetry={reload}
                />
            </Box>

            <ConfirmDeleteDialog
                open={deleteOpen}
                items={deleteTargets}
                isDeleting={isDeleting}
                errorMessage={deleteError}
                onCancel={() => setDeleteOpen(false)}
                onConfirm={confirmDelete}
            />
        </Container>
    );
}

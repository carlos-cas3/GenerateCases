import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import { StatusChip } from "@/shared/components/StatusChip";
import { formatDateTime } from "@/shared/utils/formatDateTime";
import { HISTORY_STATUS_LABEL } from "../constants";
import type { ExecutionDetail } from "../types";

export interface ExecutionDetailHeaderProps {
    execution: ExecutionDetail;
    /** Ruta actual con el identificador, p. ej. «/history/e-113». */
    routePath: string;
}

/** Nombre del documento, estado, identificador y ruta. Es común a todos los estados. */
export function ExecutionDetailHeader({
    execution,
    routePath,
}: ExecutionDetailHeaderProps) {
    return (
        <Box component="header" sx={{ mb: 3 }}>
            <Box
                sx={{
                    display: "flex",
                    alignItems: "center",
                    flexWrap: "wrap",
                    gap: 1.5,
                }}
            >
                <Typography
                    variant="h5"
                    component="h1"
                    sx={{ fontWeight: 700, wordBreak: "break-all" }}
                >
                    {execution.documentName}
                </Typography>
                <StatusChip
                    status={execution.status}
                    label={HISTORY_STATUS_LABEL[execution.status]}
                />
                <Chip
                    size="small"
                    variant="outlined"
                    label={
                        execution.clustering
                            ? "Con clustering"
                            : "Sin clustering"
                    }
                    color={execution.clustering ? "primary" : "default"}
                />
            </Box>

            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                Subida el {formatDateTime(execution.uploadedAt)} · ID{" "}
                {execution.id}
            </Typography>
            <Typography
                variant="body2"
                color="text.secondary"
                sx={{ fontFamily: "monospace" }}
            >
                Ruta: {routePath}
            </Typography>
        </Box>
    );
}

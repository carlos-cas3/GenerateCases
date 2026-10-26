import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import type { SxProps, Theme } from "@mui/material/styles";
import { BaseCard } from "@/shared/components/BaseCard";
import type { ExecutionFailure } from "../types";

export interface ExecutionFailureCardProps {
    failure?: ExecutionFailure;
    sx?: SxProps<Theme>;
}

/** Problema que detuvo la ejecución: etapa donde ocurrió y mensaje. */
export function ExecutionFailureCard({
    failure,
    sx,
}: ExecutionFailureCardProps) {
    return (
        <BaseCard
            title="Error en la ejecución"
            description="La ejecución se detuvo antes de terminar."
            sx={sx}
        >
            <Alert severity="error" variant="outlined" role="alert">
                {failure?.message ?? "No se registró el detalle del problema."}
            </Alert>
            {failure && (
                <Box sx={{ mt: 2 }}>
                    <Typography variant="caption" color="text.secondary">
                        Etapa donde falló
                    </Typography>
                    <Typography variant="subtitle2">{failure.stage}</Typography>
                </Box>
            )}
        </BaseCard>
    );
}

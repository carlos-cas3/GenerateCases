import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Container from "@mui/material/Container";
import Skeleton from "@mui/material/Skeleton";
import Typography from "@mui/material/Typography";
import ArrowBackRoundedIcon from "@mui/icons-material/ArrowBackRounded";
import { ExecutionPipeline } from "@/features/generation";
import { ExecutionDetailHeader } from "../components/ExecutionDetailHeader";
import { ExecutionFailureCard } from "../components/ExecutionFailureCard";
import { useExecutionDetail } from "../hooks/useExecutionDetail";
import type { ExecutionDetail } from "../types";

export interface ExecutionDetailPageProps {
    /** Identificador de la ejecución (viene de la ruta). */
    executionId: string;
    /** Ruta actual, para mostrarla junto al identificador. */
    routePath: string;
    onBack: () => void;
}

/** Contenido según el estado. Un `switch` exhaustivo: si se agrega un estado, TypeScript avisa. */
function DetailBody({ execution }: { execution: ExecutionDetail }) {
    switch (execution.status) {
        case "completed":
            return null; // Por ahora en blanco: solo cabecera con el nombre y la ruta.
        case "in_progress":
            return (
                <ExecutionPipeline
                    executionId={execution.id}
                    semanticGrouping={execution.clustering}
                />
            );
        case "failed":
            return <ExecutionFailureCard failure={execution.failure} />;
        case "pending":
            return (
                <Alert severity="info" variant="outlined">
                    Esta ejecución está en cola y comenzará cuando termine la
                    que está en proceso.
                </Alert>
            );
    }
}

export function ExecutionDetailPage({
    executionId,
    routePath,
    onBack,
}: ExecutionDetailPageProps) {
    const { execution, isLoading, error, reload } =
        useExecutionDetail(executionId);

    return (
        <Container maxWidth="xl" sx={{ py: { xs: 3, md: 5 } }}>
            <Button
                startIcon={<ArrowBackRoundedIcon />}
                onClick={onBack}
                sx={{ mb: 2 }}
            >
                Volver al historial
            </Button>

            {isLoading ? (
                <Box aria-busy="true">
                    <Skeleton variant="text" width="40%" height={40} />
                    <Skeleton variant="text" width="60%" />
                </Box>
            ) : error ? (
                <Alert
                    severity="error"
                    variant="outlined"
                    action={
                        <Button color="inherit" size="small" onClick={reload}>
                            Reintentar
                        </Button>
                    }
                >
                    {error}
                </Alert>
            ) : !execution ? (
                <Box>
                    <Typography
                        variant="h5"
                        component="h1"
                        sx={{ fontWeight: 700 }}
                    >
                        Ejecución no encontrada
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                        No existe una ejecución con el identificador «
                        {executionId}».
                    </Typography>
                    <Typography
                        variant="body2"
                        color="text.secondary"
                        sx={{ fontFamily: "monospace" }}
                    >
                        Ruta: {routePath}
                    </Typography>
                </Box>
            ) : (
                <>
                    <ExecutionDetailHeader
                        execution={execution}
                        routePath={routePath}
                    />
                    <DetailBody execution={execution} />
                </>
            )}
        </Container>
    );
}

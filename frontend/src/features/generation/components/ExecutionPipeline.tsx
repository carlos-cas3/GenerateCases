import type { SxProps, Theme } from "@mui/material/styles";
import { useExecutionPipeline } from "../hooks/useExecutionPipeline";
import { ExecutionProgressCard } from "./ExecutionProgressCard";

export interface ExecutionPipelineProps {
    executionId: string;
    /** Si la ejecución usó agrupación semántica (define qué etapas tiene el pipeline). */
    semanticGrouping: boolean;
    sx?: SxProps<Theme>;
}

/** Pipeline de una ejecución concreta: pide sus datos y los muestra con la card de progreso. */
export function ExecutionPipeline({
    executionId,
    semanticGrouping,
    sx,
}: ExecutionPipelineProps) {
    const { stages, isLoading, error, reload } = useExecutionPipeline(
        executionId,
        semanticGrouping,
    );

    return (
        <ExecutionProgressCard
            stages={stages}
            isLoading={isLoading}
            errorMessage={error}
            onRetry={reload}
            sx={sx}
        />
    );
}

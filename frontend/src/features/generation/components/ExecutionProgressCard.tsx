import { useId, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import ButtonBase from "@mui/material/ButtonBase";
import Collapse from "@mui/material/Collapse";
import LinearProgress from "@mui/material/LinearProgress";
import Skeleton from "@mui/material/Skeleton";
import Typography from "@mui/material/Typography";
import type { SxProps, Theme } from "@mui/material/styles";
import ExpandMoreRoundedIcon from "@mui/icons-material/ExpandMoreRounded";
import InsightsOutlinedIcon from "@mui/icons-material/InsightsOutlined";
import { BaseCard } from "@/shared/components/BaseCard";
import type { ExecutionStage, ExecutionStatus } from "../types";
import { isFinalStage, stageProgress } from "../utils/stageProgress";
import { StatusChip } from "@/shared/components/StatusChip";
import { StatusIcon } from "@/shared/components/StatusIcon";
import { STAGE_STATUS_CONFIG, toneColor } from "@/shared/components/statusConfig";

export interface ExecutionProgressCardProps {
    /** Estado general (el de la API). Si se omite, se deriva de las etapas. */
    status?: ExecutionStatus;
    stages: ExecutionStage[];
    isLoading?: boolean;
    /** Error al CONSULTAR el progreso (comunicación), no un fallo de la ejecución. */
    errorMessage?: string;
    onRetry?: () => void;
    /** El seguimiento perdió la conexión y está reintentando; se muestran los últimos datos conocidos. */
    isReconnecting?: boolean;
    /** Texto bajo la cabecera (p. ej. el nombre del documento). */
    caption?: string;
    /** Motivo del fallo de la ejecución informado por el backend. */
    failureMessage?: string;
    /** Ids de etapas expandidas al inicio (las fallidas se expanden siempre). */
    defaultExpandedIds?: string[];
    emptyMessage?: string;
    sx?: SxProps<Theme>;
}

/** Respaldo para quien no pasa `status` (p. ej. `ExecutionPipeline` del historial). */
function deriveStatus(stages: ExecutionStage[]): ExecutionStatus {
    if (stages.some((s) => s.status === "failed")) return "failed";
    if (stages.length > 0 && stages.every((s) => isFinalStage(s.status)))
        return "completed";
    if (
        stages.some(
            (s) => s.status === "in_progress" || s.status === "completed",
        )
    )
        return "in_progress";
    return "pending";
}

const OVERALL_LABEL: Record<ExecutionStatus, string> = {
    pending: "En espera",
    in_progress: "En ejecución",
    completed: "Completada",
    failed: "Fallida",
};

function StageRow({
    stage,
    index,
    isLast,
    expanded,
    onToggle,
}: {
    stage: ExecutionStage;
    index: number;
    isLast: boolean;
    expanded: boolean;
    onToggle: () => void;
}) {
    const panelId = useId();
    const expandable = stage.details !== undefined && stage.details !== null;
    const { label, tone } = STAGE_STATUS_CONFIG[stage.status];

    const content = (
        <>
            <Box
                sx={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    alignSelf: "stretch",
                }}
            >
                <StatusIcon status={stage.status} />
                {!isLast && (
                    <Box
                        sx={{
                            width: 2,
                            flex: 1,
                            minHeight: 12,
                            mt: 0.5,
                            bgcolor: "divider",
                            borderRadius: 1,
                        }}
                    />
                )}
            </Box>
            <Box
                sx={{
                    minWidth: 0,
                    flex: 1,
                    textAlign: "left",
                    pb: isLast ? 0 : 1.5,
                }}
            >
                <Typography variant="subtitle2" sx={{ lineHeight: 1.4 }}>
                    {index + 1}. {stage.title}
                </Typography>
                <Typography
                    variant="caption"
                    sx={{ color: toneColor(tone), fontWeight: 600 }}
                >
                    {label}
                    {stage.durationLabel ? ` · ${stage.durationLabel}` : ""}
                </Typography>
                {stage.summary && (
                    <Typography variant="body2" color="text.secondary">
                        {stage.summary}
                    </Typography>
                )}
            </Box>
            {expandable && (
                <ExpandMoreRoundedIcon
                    aria-hidden
                    sx={{
                        color: "text.secondary",
                        transition: "transform .2s",
                        transform: expanded ? "rotate(180deg)" : "none",
                    }}
                />
            )}
        </>
    );

    const rowSx = {
        display: "flex",
        gap: 1.5,
        width: "100%",
        alignItems: "flex-start",
        borderRadius: 1.5,
    } as const;

    return (
        <li
            style={{ listStyle: "none" }}
            aria-current={stage.status === "in_progress" ? "step" : undefined}
        >
            {expandable ? (
                <ButtonBase
                    onClick={onToggle}
                    aria-expanded={expanded}
                    aria-controls={panelId}
                    sx={{
                        ...rowSx,
                        "&:focus-visible": {
                            outline: "2px solid",
                            outlineColor: "primary.main",
                            outlineOffset: 2,
                        },
                    }}
                >
                    {content}
                </ButtonBase>
            ) : (
                <Box sx={rowSx}>{content}</Box>
            )}
            {expandable && (
                <Collapse in={expanded} unmountOnExit>
                    <Box
                        id={panelId}
                        sx={{
                            ml: "34px",
                            mb: 1.5,
                            mt: -0.5,
                            p: 1.5,
                            borderRadius: "10px",
                            bgcolor: "background.default",
                            border: "1px solid",
                            borderColor:
                                stage.status === "failed"
                                    ? "error.main"
                                    : "divider",
                            color: "text.secondary",
                            fontSize: "0.875rem",
                        }}
                    >
                        {stage.details}
                    </Box>
                </Collapse>
            )}
        </li>
    );
}

export function ExecutionProgressCard({
    status,
    stages,
    isLoading = false,
    errorMessage,
    onRetry,
    isReconnecting = false,
    caption,
    failureMessage,
    defaultExpandedIds = [],
    emptyMessage = "Aún no hay una ejecución en curso. Sube un documento para comenzar.",
    sx,
}: ExecutionProgressCardProps) {
    // Etapas cuyo estado de expansión el usuario invirtió respecto al inicial.
    const [toggledIds, setToggledIds] = useState<Set<string>>(() => new Set());

    const toggle = (id: string) =>
        setToggledIds((prev) => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    const isExpanded = (stage: ExecutionStage) =>
        (defaultExpandedIds.includes(stage.id) || stage.status === "failed") !==
        toggledIds.has(stage.id);

    const overall = status ?? deriveStatus(stages);
    const progress = stageProgress(stages);
    const hasStages = stages.length > 0;

    return (
        <BaseCard
            title="Progreso de la ejecución"
            description="Sigue cada etapa del procesamiento y consulta sus detalles."
            headerAction={
                hasStages && !isLoading ? (
                    <StatusChip
                        status={overall}
                        label={OVERALL_LABEL[overall]}
                    />
                ) : undefined
            }
            sx={sx}
        >
            {isLoading ? (
                <Box
                    aria-busy="true"
                    sx={{ display: "flex", flexDirection: "column", gap: 2 }}
                >
                    {Array.from({ length: 4 }).map((_, i) => (
                        <Box key={i} sx={{ display: "flex", gap: 1.5 }}>
                            <Skeleton
                                variant="circular"
                                width={22}
                                height={22}
                            />
                            <Box sx={{ flex: 1 }}>
                                <Skeleton width="70%" />
                                <Skeleton width="45%" />
                            </Box>
                        </Box>
                    ))}
                </Box>
            ) : errorMessage && !hasStages ? (
                <Alert
                    severity="error"
                    variant="outlined"
                    action={
                        onRetry && (
                            <Button
                                color="inherit"
                                size="small"
                                onClick={onRetry}
                            >
                                Reintentar
                            </Button>
                        )
                    }
                >
                    {errorMessage}
                </Alert>
            ) : !hasStages ? (
                <Box
                    sx={{
                        flex: 1,
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        justifyContent: "center",
                        gap: 1,
                        py: 4,
                        textAlign: "center",
                        color: "text.secondary",
                    }}
                >
                    <InsightsOutlinedIcon sx={{ fontSize: 36 }} aria-hidden />
                    <Typography variant="body2" sx={{ maxWidth: 320 }}>
                        {emptyMessage}
                    </Typography>
                </Box>
            ) : (
                <Box
                    sx={{ display: "flex", flexDirection: "column", gap: 2.5 }}
                >
                    {caption && (
                        <Typography
                            variant="subtitle2"
                            noWrap
                            title={caption}
                            sx={{ mb: -1 }}
                        >
                            {caption}
                        </Typography>
                    )}
                    {isReconnecting && (
                        <Alert severity="warning" variant="outlined">
                            Reconectando con el servidor… Se muestra el último
                            estado conocido.
                        </Alert>
                    )}
                    {errorMessage && (
                        <Alert
                            severity="warning"
                            variant="outlined"
                            action={
                                onRetry && (
                                    <Button
                                        color="inherit"
                                        size="small"
                                        onClick={onRetry}
                                    >
                                        Reintentar
                                    </Button>
                                )
                            }
                        >
                            {errorMessage} Se muestra el último estado conocido.
                        </Alert>
                    )}
                    {overall === "failed" && failureMessage && (
                        <Alert severity="error" variant="outlined">
                            {failureMessage}
                        </Alert>
                    )}
                    <Box>
                        <Box
                            sx={{
                                display: "flex",
                                justifyContent: "space-between",
                                mb: 0.75,
                            }}
                        >
                            <Typography
                                variant="caption"
                                color="text.secondary"
                            >
                                {progress.completed} completadas
                                {progress.skipped > 0 &&
                                    ` · ${progress.skipped} omitidas`}{" "}
                                de {progress.total} etapas
                            </Typography>
                            <Typography
                                variant="caption"
                                color="text.secondary"
                            >
                                {progress.percent}%
                            </Typography>
                        </Box>
                        <LinearProgress
                            variant="determinate"
                            value={progress.percent}
                            color={
                                overall === "failed"
                                    ? "error"
                                    : overall === "completed"
                                      ? "success"
                                      : "primary"
                            }
                            aria-label="Progreso general"
                            sx={{
                                height: 8,
                                borderRadius: 4,
                                bgcolor: "divider",
                            }}
                        />
                    </Box>
                    <Box
                        component="ol"
                        sx={{
                            m: 0,
                            p: 0,
                            display: "flex",
                            flexDirection: "column",
                        }}
                    >
                        {stages.map((stage, i) => (
                            <StageRow
                                key={stage.id}
                                stage={stage}
                                index={i}
                                isLast={i === stages.length - 1}
                                expanded={isExpanded(stage)}
                                onToggle={() => toggle(stage.id)}
                            />
                        ))}
                    </Box>
                </Box>
            )}
        </BaseCard>
    );
}

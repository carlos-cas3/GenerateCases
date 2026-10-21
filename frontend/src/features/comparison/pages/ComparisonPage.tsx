import { useMemo } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Container from "@mui/material/Container";
import Typography from "@mui/material/Typography";
import CompareArrowsRoundedIcon from "@mui/icons-material/CompareArrowsRounded";
import { BaseCard } from "@/shared/components/BaseCard";
import {
    getCompareStatus,
    HISTORY_STATUS_LABEL,
    useExecutions,
} from "@/features/history";
import { useQualityMetrics } from "@/features/metrics";
import { ExecutionSelectorCard } from "../components/ExecutionSelectorCard";
import { GeneratedArtifactsCard } from "../components/GeneratedArtifactsCard";
import { QualityMetricsSection } from "../components/QualityMetricsSection";
import { useComparisonSelection } from "../hooks/useComparisonSelection";
import { buildArtifactRows } from "../utils/artifacts";
import { hideValuesIfIncomplete } from "../utils/availability";
import { getOptionsA, getOptionsB } from "../utils/options";

/** Selector de A/B arriba; los resultados aparecen debajo solo cuando el par es válido. */
export function ComparisonPage() {
    const {
        records,
        isLoading: loadingRecords,
        error: recordsError,
        reload,
    } = useExecutions();
    const { selection, setSelection, clear } = useComparisonSelection();

    // Se guardan ids y se derivan los registros: si una ejecución se elimina, la selección no queda colgada.
    const a = useMemo(
        () => records.find((r) => r.id === selection.aId) ?? null,
        [records, selection.aId],
    );
    const b = useMemo(
        () => records.find((r) => r.id === selection.bId) ?? null,
        [records, selection.bId],
    );

    const optionsA = useMemo(() => getOptionsA(records, b), [records, b]);
    const optionsB = useMemo(() => getOptionsB(records, a), [records, a]);

    const compareStatus = useMemo(
        () => (a && b ? getCompareStatus([a, b]) : null),
        [a, b],
    );
    // A debe ser con clustering y B sin él (los combobox ya lo garantizan; se valida igualmente).
    const pair = useMemo(
        () =>
            a && b && compareStatus?.canCompare && a.clustering && !b.clustering
                ? { a, b }
                : null,
        [a, b, compareStatus],
    );

    const quality = useQualityMetrics(pair?.a.id ?? null, pair?.b.id ?? null);
    const metrics = useMemo(
        () => (pair ? hideValuesIfIncomplete(quality.metrics, pair) : []),
        [pair, quality.metrics],
    );
    const artifacts = useMemo(
        () => (pair ? buildArtifactRows(pair.a, pair.b) : []),
        [pair],
    );

    const incomplete = pair
        ? [
              pair.a.status !== "completed" &&
                  `A: ${HISTORY_STATUS_LABEL[pair.a.status]}`,
              pair.b.status !== "completed" &&
                  `B: ${HISTORY_STATUS_LABEL[pair.b.status]}`,
          ].filter(Boolean)
        : [];

    return (
        <Container maxWidth="xl" sx={{ py: { xs: 3, md: 5 } }}>
            <Box component="header" sx={{ mb: 3 }}>
                <Typography
                    variant="h5"
                    component="h1"
                    sx={{ fontWeight: 700 }}
                >
                    Comparación de ejecuciones
                </Typography>
                <Typography variant="body2" color="text.secondary">
                    Compara el efecto del clustering: una ejecución con
                    clustering frente a otra sin él, del mismo documento.
                </Typography>
            </Box>

            <Box
                sx={{
                    display: "grid",
                    gap: { xs: 2, md: 3 },
                    gridTemplateColumns: "minmax(0, 1fr)",
                }}
            >
                {recordsError && (
                    <Alert
                        severity="error"
                        variant="outlined"
                        action={
                            <Button
                                color="inherit"
                                size="small"
                                onClick={reload}
                            >
                                Reintentar
                            </Button>
                        }
                    >
                        {recordsError}
                    </Alert>
                )}

                <ExecutionSelectorCard
                    optionsA={optionsA}
                    optionsB={optionsB}
                    valueA={a}
                    valueB={b}
                    isLoading={loadingRecords}
                    onChangeA={(next) =>
                        setSelection({ ...selection, aId: next?.id ?? null })
                    }
                    onChangeB={(next) =>
                        setSelection({ ...selection, bId: next?.id ?? null })
                    }
                    onClear={clear}
                    compareStatus={compareStatus}
                />

                {pair ? (
                    <>
                        {incomplete.length > 0 && (
                            <Alert severity="warning" variant="outlined">
                                Alguna ejecución no está completada (
                                {incomplete.join(" · ")}). Los valores que aún
                                no existen se muestran como «—».
                            </Alert>
                        )}
                        <QualityMetricsSection
                            metrics={metrics}
                            isLoading={quality.isLoading}
                            errorMessage={quality.error}
                        />
                        <GeneratedArtifactsCard rows={artifacts} />
                    </>
                ) : (
                    <BaseCard>
                        <Box
                            sx={{
                                display: "flex",
                                flexDirection: "column",
                                alignItems: "center",
                                gap: 1,
                                py: 5,
                                textAlign: "center",
                                color: "text.secondary",
                            }}
                        >
                            <CompareArrowsRoundedIcon
                                sx={{ fontSize: 40 }}
                                aria-hidden
                            />
                            <Typography
                                variant="subtitle2"
                                color="text.primary"
                            >
                                Aún no hay una comparación
                            </Typography>
                            <Typography variant="body2" sx={{ maxWidth: 420 }}>
                                Selecciona la ejecución A y la ejecución B para
                                ver aquí las métricas de calidad y los
                                artefactos generados.
                            </Typography>
                        </Box>
                    </BaseCard>
                )}
            </Box>
        </Container>
    );
}

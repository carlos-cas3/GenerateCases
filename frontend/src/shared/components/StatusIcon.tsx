import type { ReactElement } from "react";
import CheckCircleRoundedIcon from "@mui/icons-material/CheckCircleRounded";
import ErrorRoundedIcon from "@mui/icons-material/ErrorRounded";
import NotInterestedRoundedIcon from "@mui/icons-material/NotInterestedRounded";
import RadioButtonUncheckedRoundedIcon from "@mui/icons-material/RadioButtonUncheckedRounded";
import CircularProgress from "@mui/material/CircularProgress";
import type { StageStatus } from "../types";
import { STAGE_STATUS_CONFIG, toneColor } from "./statusConfig";

/** Icono coherente con cada estado. No depende solo del color: la forma también cambia. */
export function StatusIcon({
    status,
    size = 22,
}: {
    status: StageStatus;
    size?: number;
}): ReactElement {
    const sx = { fontSize: size, color: toneColor(STAGE_STATUS_CONFIG[status].tone) };
    switch (status) {
        case "completed":
            return <CheckCircleRoundedIcon sx={sx} aria-hidden />;
        case "failed":
            return <ErrorRoundedIcon sx={sx} aria-hidden />;
        case "skipped":
            return <NotInterestedRoundedIcon sx={sx} aria-hidden />;
        case "in_progress":
            return (
                <CircularProgress
                    size={size - 4}
                    thickness={5}
                    aria-hidden
                    sx={{ m: "2px" }}
                />
            );
        default:
            return <RadioButtonUncheckedRoundedIcon sx={sx} aria-hidden />;
    }
}

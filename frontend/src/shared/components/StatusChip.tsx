import Chip from "@mui/material/Chip";
import { alpha } from "@mui/material/styles";
import type { SxProps, Theme } from "@mui/material/styles";
import type { StageStatus } from "../types";
import { StatusIcon } from "./StatusIcon";
import { STAGE_STATUS_CONFIG } from "./statusConfig";

interface StatusChipProps {
    /** Acepta estados de ejecución y de etapa (`skipped`). */
    status: StageStatus;
    /** Sobrescribe el texto por defecto (p. ej. "Ejecución en curso"). */
    label?: string;
    sx?: SxProps<Theme>;
}

export function StatusChip({ status, label, sx }: StatusChipProps) {
    const { tone, label: defaultLabel } = STAGE_STATUS_CONFIG[status];

    return (
        <Chip
            size="small"
            label={label ?? defaultLabel}
            icon={<StatusIcon status={status} size={18} />}
            sx={[
                (theme) => {
                    const main =
                        tone === "neutral"
                            ? theme.palette.text.secondary
                            : theme.palette[tone].main;
                    return {
                        color: main,
                        bgcolor: alpha(main, 0.1),
                        border: `1px solid ${alpha(main, 0.25)}`,
                        "& .MuiChip-icon": { ml: 0.75, mr: -0.25 },
                    };
                },
                ...(Array.isArray(sx) ? sx : [sx]),
            ]}
        />
    );
}

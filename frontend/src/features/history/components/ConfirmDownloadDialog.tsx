import { useId } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import { alpha } from "@mui/material/styles";
import FileDownloadOutlinedIcon from "@mui/icons-material/FileDownloadOutlined";
import {
    DIALOG_BACKDROP_SX,
    DIALOG_PAPER_SX,
} from "@/shared/components/dialogStyles";
import type { ExecutionRecord } from "../types";

const MAX_LISTED = 5;

export interface ConfirmDownloadDialogProps {
    open: boolean;
    /** Ejecuciones a descargar (2 o más; con una sola la descarga es automática). */
    items: ExecutionRecord[];
    isDownloading?: boolean;
    onCancel: () => void;
    onConfirm: () => void;
}

export function ConfirmDownloadDialog({
    open,
    items,
    isDownloading = false,
    onCancel,
    onConfirm,
}: ConfirmDownloadDialogProps) {
    const titleId = useId();
    const descriptionId = useId();
    const hidden = items.length - MAX_LISTED;

    return (
        <Dialog
            open={open}
            onClose={isDownloading ? undefined : onCancel}
            aria-labelledby={titleId}
            aria-describedby={descriptionId}
            maxWidth="xs"
            fullWidth
            slotProps={{
                backdrop: { sx: DIALOG_BACKDROP_SX },
                paper: { sx: DIALOG_PAPER_SX },
            }}
        >
            <DialogTitle
                id={titleId}
                sx={{ display: "flex", alignItems: "center", gap: 1.5, pb: 1 }}
            >
                <Box
                    aria-hidden
                    sx={(theme) => ({
                        display: "grid",
                        placeItems: "center",
                        width: 40,
                        height: 40,
                        borderRadius: "50%",
                        flexShrink: 0,
                        color: "primary.main",
                        bgcolor: alpha(theme.palette.primary.main, 0.1),
                    })}
                >
                    <FileDownloadOutlinedIcon />
                </Box>
                Descargar documentos
            </DialogTitle>

            <DialogContent>
                <DialogContentText
                    id={descriptionId}
                    component="div"
                    sx={{ color: "text.secondary" }}
                >
                    Se van a descargar{" "}
                    <Box component="strong" sx={{ color: "text.primary" }}>
                        {items.length} documentos
                    </Box>
                    .
                    <Box component="ul" sx={{ mt: 1, mb: 0, pl: 2.5 }}>
                        {items.slice(0, MAX_LISTED).map((item) => (
                            <li
                                key={item.id}
                                style={{ wordBreak: "break-all" }}
                            >
                                {item.documentName} (
                                {item.clustering ? "con" : "sin"} clustering)
                            </li>
                        ))}
                        {hidden > 0 && <li>y {hidden} más…</li>}
                    </Box>
                </DialogContentText>
            </DialogContent>

            <DialogActions sx={{ px: 3, pb: 2.5, gap: 1 }}>
                <Button
                    onClick={onCancel}
                    disabled={isDownloading}
                    color="inherit"
                    autoFocus
                >
                    Cancelar
                </Button>
                <Button
                    onClick={onConfirm}
                    disabled={isDownloading}
                    variant="contained"
                    startIcon={
                        isDownloading ? (
                            <CircularProgress size={16} color="inherit" />
                        ) : undefined
                    }
                >
                    {isDownloading
                        ? "Descargando…"
                        : `Descargar (${items.length})`}
                </Button>
            </DialogActions>
        </Dialog>
    );
}

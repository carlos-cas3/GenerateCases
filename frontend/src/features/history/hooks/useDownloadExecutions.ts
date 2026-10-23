import { useCallback, useEffect, useRef, useState } from "react";
import { saveBlob } from "@/shared/utils/saveBlob";
import { DOWNLOAD_COOLDOWN_MS } from "../constants";
import { historyService } from "../services/historyService";
import type { ExecutionRecord } from "../types";

export type DownloadResult =
    | { ok: true; fileName: string }
    | { ok: false; reason: "busy" | "error" };

/**
 * Descarga 1 o varias ejecuciones con el mecanismo del backend y aplica una espera
 * (`DOWNLOAD_COOLDOWN_MS`) antes de permitir otra descarga.
 */
export function useDownloadExecutions() {
    const [isDownloading, setIsDownloading] = useState(false);
    const [isCoolingDown, setIsCoolingDown] = useState(false);
    // Guarda contra doble clic: el estado de React se actualiza después, la ref es inmediata.
    const busy = useRef(false);
    const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

    useEffect(() => () => clearTimeout(timer.current), []);

    const download = useCallback(
        async (targets: ExecutionRecord[]): Promise<DownloadResult> => {
            if (busy.current || targets.length === 0)
                return { ok: false, reason: "busy" };
            busy.current = true;
            setIsDownloading(true);

            try {
                const file = await historyService.downloadExecutions(
                    targets.map((t) => t.id),
                );
                saveBlob(file.blob, file.fileName);

                setIsCoolingDown(true);
                timer.current = setTimeout(() => {
                    busy.current = false;
                    setIsCoolingDown(false);
                }, DOWNLOAD_COOLDOWN_MS);

                return { ok: true, fileName: file.fileName };
            } catch {
                busy.current = false; // si falló, se puede reintentar de inmediato
                return { ok: false, reason: "error" };
            } finally {
                setIsDownloading(false);
            }
        },
        [],
    );

    return { download, isDownloading, isBusy: isDownloading || isCoolingDown };
}

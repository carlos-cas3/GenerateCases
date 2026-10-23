/**
 * Acceso a datos de las ejecuciones.
 * Hoy se respalda en un almacén en memoria (mock); cuando exista el backend solo cambia
 * este archivo: los hooks y las páginas no se enteran.
 */
import { delay } from "@/shared/utils/delay";
import { buildMockDownload } from "../mocks/downloadMocks";
import {
    DEFAULT_FAILURE,
    MOCK_FAILURES,
    MOCK_HISTORY,
} from "../mocks/historyMocks";
import type {
    DownloadedFile,
    ExecutionDetail,
    ExecutionRecord,
} from "../types";

const LATENCY_MS = 250;
const DOWNLOAD_LATENCY_MS = 600;

let store: ExecutionRecord[] = [...MOCK_HISTORY];

export const historyService = {
    async listExecutions(): Promise<ExecutionRecord[]> {
        await delay(LATENCY_MS);
        return [...store];
    },

    /** Detalle de una ejecución por su identificador. `null` si no existe. (Backend: GET /executions/:id) */
    async getExecutionById(id: string): Promise<ExecutionDetail | null> {
        await delay(LATENCY_MS);
        const record = store.find((r) => r.id === id);
        if (!record) return null;
        return {
            ...record,
            failure:
                record.status === "failed"
                    ? (MOCK_FAILURES[id] ?? DEFAULT_FAILURE)
                    : undefined,
        };
    },

    async deleteExecutions(ids: string[]): Promise<void> {
        await delay(LATENCY_MS);
        store = store.filter((record) => !ids.includes(record.id));
    },

    /**
     * Descarga de 1 o varias ejecuciones: el backend responde con el archivo.
     * (Backend: GET /executions/:id/download · POST /executions/download con { ids } → .zip)
     */
    async downloadExecutions(ids: string[]): Promise<DownloadedFile> {
        await delay(DOWNLOAD_LATENCY_MS);
        const records = store.filter((r) => ids.includes(r.id));
        if (records.length === 0)
            throw new Error("No se encontraron ejecuciones para descargar.");
        return buildMockDownload(records);
    },
};

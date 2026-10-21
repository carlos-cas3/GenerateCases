/**
 * Acceso a datos de las ejecuciones.
 * Hoy se respalda en un almacén en memoria (mock); cuando exista el backend solo cambia
 * este archivo: los hooks y las páginas no se enteran.
 */
import { delay } from "@/shared/utils/delay";
import { MOCK_HISTORY } from "../mocks/historyMocks";
import type { ExecutionRecord } from "../types";

const LATENCY_MS = 250;

let store: ExecutionRecord[] = [...MOCK_HISTORY];

export const historyService = {
    async listExecutions(): Promise<ExecutionRecord[]> {
        await delay(LATENCY_MS);
        return [...store];
    },

    async deleteExecutions(ids: string[]): Promise<void> {
        await delay(LATENCY_MS);
        store = store.filter((record) => !ids.includes(record.id));
    },
};

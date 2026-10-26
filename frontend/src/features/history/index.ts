/**
 * API pública de la feature «history» (dueña del dominio «ejecuciones»).
 * Las demás features y la capa app importan SOLO desde aquí, nunca rutas internas.
 */
export { HistoryPage } from "./pages/HistoryPage";
export type { HistoryPageProps } from "./pages/HistoryPage";
export { ExecutionDetailPage } from "./components/ExecutionDetailPage";
export type { ExecutionDetailPageProps } from "./components/ExecutionDetailPage";

export { useExecutions } from "./hooks/useExecutions";
export { HISTORY_STATUS_LABEL } from "./constants";
export type { ExecutionRecord } from "./types";

// Regla de negocio: qué ejecuciones se pueden comparar entre sí.
export {
    getCompareStatus,
    getDocumentBaseName,
    isSameDocument,
} from "./utils/comparison";
export type { CompareStatus } from "./utils/comparison";
export { splitFileName } from "./utils/fileName";

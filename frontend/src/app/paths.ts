import { generatePath } from "react-router-dom";

/** Rutas de la aplicación (única fuente de verdad). */
export const ROUTES = {
    generation: "/",
    history: "/history",
    historyDetail: "/history/:executionId",
    comparison: "/comparison",
} as const;

/** Ruta de detalle de una ejecución: «/history/e-113». */
export const historyDetailPath = (executionId: string) =>
    generatePath(ROUTES.historyDetail, { executionId });

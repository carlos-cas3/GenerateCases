/** Estado compartido por ejecuciones (generaciones) y registros del historial. */
export type ExecutionStatus =
    | "pending"
    | "in_progress"
    | "completed"
    | "failed";

/** Estado de una etapa del pipeline. `skipped` solo existe para etapas, nunca para una generación. */
export type StageStatus = ExecutionStatus | "skipped";

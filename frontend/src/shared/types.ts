/** Estado compartido por etapas, ejecuciones y registros del historial. */
export type ExecutionStatus =
    | "pending"
    | "in_progress"
    | "completed"
    | "failed";

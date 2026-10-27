/** Códigos propios del cliente (no los emite el backend). */
export type ClientErrorCode = "NETWORK_ERROR" | "UNEXPECTED_RESPONSE";

/**
 * Error de una llamada a la API con el formato `{"error": {code, message, details}}`.
 * `status` 0 = no hubo respuesta HTTP (fallo de red).
 */
export class ApiError extends Error {
    readonly status: number;
    readonly code: string;
    readonly details: unknown;

    constructor(status: number, code: string, message: string, details?: unknown) {
        super(message);
        this.name = "ApiError";
        this.status = status;
        this.code = code;
        this.details = details;
    }

    /** Errores que pueden resolverse solos: sin conexión o fallo del servidor. */
    get isTransient(): boolean {
        return this.status === 0 || this.status >= 500;
    }
}

export const isApiError = (error: unknown): error is ApiError =>
    error instanceof ApiError;

/** Abortar una petición no es un error que deba mostrarse. */
export const isAbortError = (error: unknown): boolean =>
    error instanceof DOMException && error.name === "AbortError";

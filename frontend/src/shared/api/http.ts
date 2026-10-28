/**
 * Cliente HTTP único de la aplicación: ningún `fetch` debe vivir fuera de `shared/api/`.
 * Base: `VITE_API_URL` o vacío (rutas relativas atendidas por el proxy de Vite en desarrollo).
 */
import { ApiError, isAbortError } from "./ApiError";

const API_BASE_URL = (import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "");
export const API_PREFIX = "/api/v1";

export interface RequestOptions {
    method?: "GET" | "POST" | "DELETE";
    body?: unknown;
    signal?: AbortSignal;
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null;
}

/** Traduce una respuesta no exitosa a `ApiError`, tolerando cuerpos fuera de formato. */
function toApiError(status: number, payload: unknown): ApiError {
    if (isRecord(payload) && isRecord(payload.error)) {
        const { code, message, details } = payload.error;
        if (typeof code === "string" && typeof message === "string") {
            return new ApiError(status, code, message, details);
        }
    }
    const detail =
        isRecord(payload) && typeof payload.detail === "string"
            ? payload.detail
            : undefined;
    return new ApiError(
        status,
        "UNEXPECTED_RESPONSE",
        detail ?? `Respuesta inesperada del servidor (HTTP ${status}).`,
    );
}

async function readJson(response: Response): Promise<unknown> {
    const text = await response.text();
    if (!text) return undefined;
    try {
        return JSON.parse(text);
    } catch {
        return text;
    }
}

/** Ejecuta el `fetch` y traduce la respuesta. Común a `request` y `uploadFormData`. */
async function send<T>(path: string, init: RequestInit): Promise<T> {
    let response: Response;
    try {
        response = await fetch(`${API_BASE_URL}${API_PREFIX}${path}`, init);
    } catch (error) {
        if (isAbortError(error)) throw error;
        throw new ApiError(0, "NETWORK_ERROR", "No se pudo conectar con el servidor.");
    }

    if (response.status === 204) return undefined as T;

    const payload = await readJson(response);
    if (!response.ok) throw toApiError(response.status, payload);
    if (!isRecord(payload) && !Array.isArray(payload)) {
        throw new ApiError(
            response.status,
            "UNEXPECTED_RESPONSE",
            "La respuesta del servidor no tiene el formato esperado.",
        );
    }
    return payload as T;
}

/** Petición JSON a la API. Lanza `ApiError`; un `AbortError` se relanza sin envolver. */
export async function request<T>(
    path: string,
    { method = "GET", body, signal }: RequestOptions = {},
): Promise<T> {
    return send<T>(path, {
        method,
        signal,
        headers: {
            Accept: "application/json",
            ...(body !== undefined && { "Content-Type": "application/json" }),
        },
        body: body !== undefined ? JSON.stringify(body) : undefined,
    });
}

/**
 * `POST` multipart a la API. Sin `Content-Type`: el navegador lo fija con su `boundary`.
 * Mismos errores que `request`; aquí no hay reintentos, el llamador muestra el error.
 */
export async function uploadFormData<T>(
    path: string,
    formData: FormData,
    { signal }: { signal?: AbortSignal } = {},
): Promise<T> {
    return send<T>(path, {
        method: "POST",
        signal,
        headers: { Accept: "application/json" },
        body: formData,
    });
}

import { useEffect } from "react";
import { isApiError } from "@/shared/api";
import { useAsyncData } from "@/shared/hooks/useAsyncData";
import { isActiveStatus } from "../services/generationMappers";
import { generationService } from "../services/generationService";
import type { Generation } from "../types";

/** Cada cuánto se consulta una generación en cola o en ejecución. */
export const POLL_INTERVAL_MS = 2000;

const pollWhileActive = (generation: Generation | null | undefined) =>
    isActiveStatus(generation?.status) ? POLL_INTERVAL_MS : undefined;

/**
 * Sigue una generación por id con polling mientras esté `queued`/`running` y se detiene en
 * `completed`/`failed`. El estado mostrado es SIEMPRE el del backend: un error de comunicación
 * no convierte la generación en fallida (se conserva el último estado y se reintenta).
 *
 * `onGone` se invoca si la generación no existe (404) o el id no es válido (400).
 */
export function useExecutionProgress(
    generationId: string | null,
    onGone?: (message: string) => void,
) {
    const { data, isLoading, isReconnecting, error, errorCause, reload } =
        useAsyncData<Generation | null>(
            (signal) =>
                generationId
                    ? generationService.getGeneration(generationId, signal)
                    : Promise.resolve(null),
            [generationId],
            {
                errorMessage: "No se pudo consultar el progreso de la ejecución.",
                initialData: null,
                enabled: !!generationId,
                refreshInterval: pollWhileActive,
            },
        );

    const goneMessage = !isApiError(errorCause)
        ? undefined
        : errorCause.code === "GENERATION_NOT_FOUND"
          ? "La ejecución ya no existe."
          : errorCause.code === "VALIDATION_ERROR"
            ? "El enlace de la ejecución no es válido."
            : undefined;

    useEffect(() => {
        if (goneMessage) onGone?.(goneMessage);
    }, [goneMessage, onGone]);

    return {
        generation: data,
        stages: data?.stages ?? [],
        status: data?.status,
        isLoading,
        isReconnecting,
        error: goneMessage ? undefined : error,
        reload,
    };
}

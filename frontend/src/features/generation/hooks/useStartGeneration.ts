import { useCallback, useRef, useState } from "react";
import { isApiError } from "@/shared/api";
import { generationService } from "../services/generationService";
import type { StartGenerationInput } from "../services/generationService";
import type { Generation } from "../types";

/** Mensaje para el usuario según el error devuelto al crear la generación. */
function startErrorMessage(error: unknown): string {
    if (isApiError(error)) {
        if (error.code === "DOCUMENT_NOT_FOUND") {
            return "El documento de prueba no existe en la base de datos. Aplica supabase/seed.sql.";
        }
        if (error.code === "VALIDATION_ERROR") return "La solicitud no es válida.";
        if (error.code === "NETWORK_ERROR") return "No se pudo conectar con el servidor.";
        if (error.status >= 500) return "Error del servidor. Inténtalo de nuevo.";
    }
    return "No se pudo iniciar la generación. Inténtalo nuevamente.";
}

/**
 * Inicia una generación y expone su estado de envío y error para el formulario.
 * Ignora un segundo envío mientras el primero está en curso (doble clic).
 */
export function useStartGeneration(onStarted?: (generation: Generation) => void) {
    const [isCreating, setIsCreating] = useState(false);
    const [error, setError] = useState<string>();
    const inFlight = useRef(false);

    const start = useCallback(
        async (input: StartGenerationInput) => {
            if (inFlight.current) return null;
            inFlight.current = true;
            setIsCreating(true);
            setError(undefined);
            try {
                const generation = await generationService.startGeneration(input);
                onStarted?.(generation);
                return generation;
            } catch (e) {
                setError(startErrorMessage(e));
                return null;
            } finally {
                inFlight.current = false;
                setIsCreating(false);
            }
        },
        [onStarted],
    );

    return { start, isCreating, error };
}

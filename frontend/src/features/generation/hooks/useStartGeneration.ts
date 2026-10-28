import { useCallback, useRef, useState } from "react";
import { isApiError } from "@/shared/api";
import { generationService } from "../services/generationService";
import type { StartGenerationInput } from "../services/generationService";
import type { Generation } from "../types";

/** Mensaje para el usuario según el error devuelto al subir el documento o crear la generación. */
function startErrorMessage(error: unknown): string {
    if (isApiError(error)) {
        if (error.code === "PAYLOAD_TOO_LARGE") return "El archivo supera el límite de 20 MB.";
        if (error.code === "UNSUPPORTED_MEDIA_TYPE") {
            return "Tipo de archivo no soportado. Usa un archivo TXT, PDF o DOCX.";
        }
        if (error.code === "DOCUMENT_NOT_FOUND") {
            return "El documento subido ya no existe. Vuelve a seleccionarlo e inténtalo de nuevo.";
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

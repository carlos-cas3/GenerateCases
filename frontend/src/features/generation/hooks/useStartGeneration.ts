import { useCallback, useState } from "react";
import { generationService } from "../services/generationService";
import type { StartGenerationInput } from "../services/generationService";

/** Inicia una generación y expone su estado de envío y error para el formulario. */
export function useStartGeneration() {
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [error, setError] = useState<string>();

    const start = useCallback(async (input: StartGenerationInput) => {
        setIsSubmitting(true);
        setError(undefined);
        try {
            return await generationService.startGeneration(input);
        } catch {
            setError("No se pudo iniciar la generación. Inténtalo nuevamente.");
            return null;
        } finally {
            setIsSubmitting(false);
        }
    }, []);

    return { start, isSubmitting, error };
}

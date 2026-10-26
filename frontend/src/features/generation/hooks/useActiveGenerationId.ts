import { useCallback, useEffect } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { isActiveStatus } from "../services/generationMappers";
import type { RecentExecution } from "../types";

/** Parámetro de la URL con la generación seguida: `/?g=<uuid>`. Es un identificador técnico, no se muestra. */
const PARAM = "g";
const UUID_PATTERN =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export const isUuid = (value: string) => UUID_PATTERN.test(value);

interface NavigationState {
    /** Aviso para el usuario tras limpiar el parámetro (enlace inválido, generación inexistente…). */
    notice?: string;
    /** Tras limpiar por un error no se elige otra generación automáticamente. */
    noFallback?: boolean;
}

/**
 * Resuelve qué generación sigue la página.
 * 1. `?g=<uuid>` es la selección explícita y tiene prioridad (sobrevive a recargar la página).
 * 2. Sin `?g=`, se retoma la generación activa más reciente de `recentItems` (ya cargados) y se
 *    fija en la URL. Si hubiera varias activas, esta vista solo retoma una.
 */
export function useActiveGenerationId(recentItems: RecentExecution[]) {
    const [params, setParams] = useSearchParams();
    const location = useLocation();
    const state = (location.state ?? {}) as NavigationState;

    const raw = params.get(PARAM);
    const explicitId = raw !== null && isUuid(raw) ? raw : null;
    const recoveredId =
        raw === null && !state.noFallback
            ? (recentItems.find((item) => isActiveStatus(item.status))?.id ??
              null)
            : null;

    const clear = useCallback(
        (notice?: string) =>
            setParams(
                (prev) => {
                    const next = new URLSearchParams(prev);
                    next.delete(PARAM);
                    return next;
                },
                {
                    replace: true,
                    state: { notice, noFallback: true } satisfies NavigationState,
                },
            ),
        [setParams],
    );

    const setActive = useCallback(
        (id: string) => setParams({ [PARAM]: id }),
        [setParams],
    );

    const dismissNotice = useCallback(
        () => setParams((prev) => prev, { replace: true, state: null }),
        [setParams],
    );

    // `?g=` con formato inválido: se limpia y se informa.
    useEffect(() => {
        if (raw !== null && explicitId === null) {
            clear("El enlace de la ejecución no es válido.");
        }
    }, [raw, explicitId, clear]);

    // La activa recuperada se fija en la URL para que siga seleccionada aunque termine.
    useEffect(() => {
        if (recoveredId) setParams({ [PARAM]: recoveredId }, { replace: true });
    }, [recoveredId, setParams]);

    return {
        generationId: explicitId ?? recoveredId,
        notice: state.notice,
        setActive,
        clear,
        dismissNotice,
    };
}

import { useCallback, useEffect, useRef, useState } from "react";

/** Última respuesta por `cacheKey`: permite mostrar datos conocidos al volver a una pantalla mientras se revalida. */
const cache = new Map<string, unknown>();
const STALE_KEY = "__stale__";

interface Result<T> {
    key: string;
    data?: T;
    error?: string;
}

export interface UseAsyncDataOptions<T> {
    /** Mensaje mostrado si la carga falla. */
    errorMessage: string;
    /** Valor mientras no hay datos (mantenerlo estable evita re-renders). */
    initialData: T;
    /** Si es `true`, al cambiar `deps` se siguen mostrando los datos anteriores mientras llegan los nuevos. */
    keepPreviousData?: boolean;
    /** Si es `false`, no consulta nada. */
    enabled?: boolean;
    /** Si se indica, la última respuesta se recuerda entre montajes (stale-while-revalidate). */
    cacheKey?: string;
}

/**
 * Carga asíncrona con estados de carga/error, cancelación de respuestas obsoletas y recarga.
 * `deps` deben ser valores primitivos. Es la pieza común de los hooks de datos de cada feature.
 *
 * - `isLoading`: se está pidiendo algo y todavía no hay NADA que mostrar (usar esqueletos).
 * - `isFetching`: hay una petición en curso (aunque ya se muestren datos anteriores).
 */
export function useAsyncData<T>(
    load: () => Promise<T>,
    deps: readonly (string | number | boolean | null | undefined)[],
    {
        errorMessage,
        initialData,
        keepPreviousData = false,
        enabled = true,
        cacheKey,
    }: UseAsyncDataOptions<T>,
) {
    const [version, setVersion] = useState(0);
    const [result, setResult] = useState<Result<T> | null>(() =>
        cacheKey && cache.has(cacheKey)
            ? { key: STALE_KEY, data: cache.get(cacheKey) as T }
            : null,
    );
    const key = `${version}|${deps.map(String).join("|")}`;

    const loadRef = useRef(load);
    useEffect(() => {
        loadRef.current = load;
    });

    useEffect(() => {
        if (!enabled) return;
        let cancelled = false;

        loadRef
            .current()
            .then((data) => {
                if (cacheKey) cache.set(cacheKey, data);
                if (!cancelled) setResult({ key, data });
            })
            .catch(() => {
                if (!cancelled) setResult({ key, error: errorMessage });
            });

        return () => {
            cancelled = true;
        };
    }, [key, enabled, errorMessage, cacheKey]);

    const isCurrent = enabled && result?.key === key;
    const shown =
        isCurrent ||
        (enabled && (keepPreviousData || result?.key === STALE_KEY))
            ? result?.data
            : undefined;

    const reload = useCallback(() => setVersion((v) => v + 1), []);

    /** Aplica un cambio local a los datos (p. ej. tras eliminar) sin volver a pedirlos. */
    const mutate = useCallback(
        (update: (previous: T) => T) => {
            setResult((prev) => {
                if (!prev || prev.data === undefined) return prev;
                const data = update(prev.data);
                if (cacheKey) cache.set(cacheKey, data);
                return { ...prev, data };
            });
        },
        [cacheKey],
    );

    return {
        data: shown ?? initialData,
        isLoading: enabled && !isCurrent && shown === undefined,
        isFetching: enabled && !isCurrent,
        error: isCurrent ? result?.error : undefined,
        reload,
        mutate,
    };
}

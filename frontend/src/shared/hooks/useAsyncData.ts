import { useCallback, useEffect, useRef, useState } from "react";
import { isAbortError, isApiError } from "@/shared/api";

/** Última respuesta por `cacheKey`: permite mostrar datos conocidos al volver a una pantalla mientras se revalida. */
const cache = new Map<string, unknown>();
const STALE_KEY = "__stale__";

/** Reintentos ante errores transitorios durante el polling: 2 s, 4 s y 8 s. */
const MAX_POLL_RETRIES = 3;
const RETRY_BASE_DELAY_MS = 2000;

interface Result<T> {
    key: string;
    data?: T;
    error?: string;
    /** Error original (p. ej. `ApiError`) para que el llamador distinga casos. */
    cause?: unknown;
    /** El polling falló de forma transitoria y se está reintentando. */
    reconnecting?: boolean;
}

/** Intervalo de repetición en ms; `undefined` detiene el polling. */
export type RefreshInterval<T> =
    | number
    | ((data: T | undefined) => number | undefined);

export interface UseAsyncDataOptions<T> {
    /** Mensaje mostrado si la carga falla. */
    errorMessage: string;
    /** Valor mientras no hay datos (mantenerlo estable evita re-renders). */
    initialData: T;
    /** Si es `true`, al cambiar `deps` se siguen mostrando los datos anteriores mientras llegan los nuevos. */
    keepPreviousData?: boolean;
    /** Si es `false`, no consulta nada. */
    enabled?: boolean;
    /** Si se indica, la última respuesta se recuerda en memoria entre montajes (no sobrevive a recargar la página). */
    cacheKey?: string;
    /**
     * Activa el polling. El siguiente ciclo se programa al terminar el anterior (nunca hay dos
     * peticiones en vuelo). La forma función decide según los datos recibidos (`undefined` = detener).
     */
    refreshInterval?: RefreshInterval<T>;
}

const isTransient = (error: unknown) => isApiError(error) && error.isTransient;

function resolveInterval<T>(
    interval: RefreshInterval<T> | undefined,
    data: T | undefined,
): number | undefined {
    return typeof interval === "function" ? interval(data) : interval;
}

/**
 * Carga asíncrona con estados de carga/error, cancelación real (`AbortSignal`), recarga y polling opcional.
 * `deps` deben ser valores primitivos. Es la pieza común de los hooks de datos de cada feature.
 *
 * - `isLoading`: se está pidiendo algo y todavía no hay NADA que mostrar (usar esqueletos).
 * - `isFetching`: hay una petición en curso (aunque ya se muestren datos anteriores).
 * - `isReconnecting`: el polling falló de forma transitoria y reintenta conservando los datos.
 */
export function useAsyncData<T>(
    load: (signal: AbortSignal) => Promise<T>,
    deps: readonly (string | number | boolean | null | undefined)[],
    {
        errorMessage,
        initialData,
        keepPreviousData = false,
        enabled = true,
        cacheKey,
        refreshInterval,
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
    const intervalRef = useRef(refreshInterval);
    const errorMessageRef = useRef(errorMessage);
    useEffect(() => {
        loadRef.current = load;
        intervalRef.current = refreshInterval;
        errorMessageRef.current = errorMessage;
    });

    useEffect(() => {
        if (!enabled) return;
        const controller = new AbortController();
        let timer: ReturnType<typeof setTimeout> | undefined;
        let retries = 0;

        const run = () => {
            loadRef
                .current(controller.signal)
                .then((data) => {
                    if (controller.signal.aborted) return;
                    retries = 0;
                    if (cacheKey) cache.set(cacheKey, data);
                    setResult({ key, data });
                    const next = resolveInterval(intervalRef.current, data);
                    if (next !== undefined) timer = setTimeout(run, next);
                })
                .catch((error: unknown) => {
                    if (controller.signal.aborted || isAbortError(error)) return;
                    const polling = intervalRef.current !== undefined;
                    if (polling && isTransient(error) && retries < MAX_POLL_RETRIES) {
                        const wait = RETRY_BASE_DELAY_MS * 2 ** retries;
                        retries += 1;
                        setResult((prev) => ({
                            key,
                            data: prev?.key === key ? prev.data : undefined,
                            reconnecting: true,
                        }));
                        timer = setTimeout(run, wait);
                        return;
                    }
                    // Agotados los reintentos (o error no transitorio): se detiene; `reload()` reintenta.
                    setResult((prev) => ({
                        key,
                        data: polling && prev?.key === key ? prev.data : undefined,
                        error: errorMessageRef.current,
                        cause: error,
                    }));
                });
        };
        run();

        return () => {
            controller.abort();
            clearTimeout(timer);
        };
    }, [key, enabled, cacheKey]);

    const reload = useCallback(() => setVersion((v) => v + 1), []);

    // Al volver a la pestaña, el polling activo (o detenido por error) se pone al día de inmediato.
    const resultRef = useRef(result);
    useEffect(() => {
        resultRef.current = result;
    });
    const polls = refreshInterval !== undefined;
    useEffect(() => {
        if (!enabled || !polls) return;
        const onVisible = () => {
            if (document.visibilityState !== "visible") return;
            const last = resultRef.current;
            const active =
                last?.error !== undefined ||
                last?.reconnecting === true ||
                resolveInterval(intervalRef.current, last?.data) !== undefined;
            if (active) reload();
        };
        document.addEventListener("visibilitychange", onVisible);
        return () => document.removeEventListener("visibilitychange", onVisible);
    }, [enabled, polls, reload]);

    const isCurrent = enabled && result?.key === key;
    const shown =
        isCurrent ||
        (enabled && (keepPreviousData || result?.key === STALE_KEY))
            ? result?.data
            : undefined;
    const settled = isCurrent && !result?.reconnecting;

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
        isLoading: enabled && !settled && shown === undefined,
        isFetching: enabled && !isCurrent,
        isReconnecting: isCurrent && result?.reconnecting === true,
        error: isCurrent ? result?.error : undefined,
        errorCause: isCurrent ? result?.cause : undefined,
        reload,
        mutate,
    };
}

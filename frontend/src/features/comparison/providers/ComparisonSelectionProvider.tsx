import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { ExecutionRecord } from "@/features/history";
import { EMPTY_COMPARISON_SELECTION } from "../constants";
import type { ComparisonSelection } from "../types";
import { ComparisonSelectionContext } from "./ComparisonSelectionContext";
import type { ComparisonSelectionValue } from "./ComparisonSelectionContext";

/**
 * Guarda la selección A/B por encima de las rutas: la página de comparación se desmonta al
 * navegar a otra vista, pero lo elegido se conserva.
 */
export function ComparisonSelectionProvider({
    children,
}: {
    children: ReactNode;
}) {
    const [selection, setSelection] = useState<ComparisonSelection>(
        EMPTY_COMPARISON_SELECTION,
    );

    const value = useMemo<ComparisonSelectionValue>(
        () => ({
            selection,
            setSelection,
            selectPair: (pair: ExecutionRecord[]) =>
                setSelection({
                    aId: pair.find((r) => r.clustering)?.id ?? null,
                    bId: pair.find((r) => !r.clustering)?.id ?? null,
                }),
            clear: () => setSelection(EMPTY_COMPARISON_SELECTION),
        }),
        [selection],
    );

    return (
        <ComparisonSelectionContext.Provider value={value}>
            {children}
        </ComparisonSelectionContext.Provider>
    );
}

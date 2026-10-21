import { useContext } from "react";
import { ComparisonSelectionContext } from "../providers/ComparisonSelectionContext";

export function useComparisonSelection() {
    const context = useContext(ComparisonSelectionContext);
    if (!context) {
        throw new Error(
            "useComparisonSelection debe usarse dentro de <ComparisonSelectionProvider>.",
        );
    }
    return context;
}

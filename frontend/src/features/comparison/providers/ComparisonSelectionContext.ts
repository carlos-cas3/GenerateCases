import { createContext } from "react";
import type { ExecutionRecord } from "@/features/history";
import type { ComparisonSelection } from "../types";

export interface ComparisonSelectionValue {
    selection: ComparisonSelection;
    setSelection: (selection: ComparisonSelection) => void;
    /** A = la ejecución con clustering, B = la que no lo tiene. */
    selectPair: (pair: ExecutionRecord[]) => void;
    clear: () => void;
}

export const ComparisonSelectionContext =
    createContext<ComparisonSelectionValue | null>(null);

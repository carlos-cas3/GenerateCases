import type { ReactNode } from "react";
import CssBaseline from "@mui/material/CssBaseline";
import { ThemeProvider } from "@mui/material/styles";
import { ComparisonSelectionProvider } from "@/features/comparison";
import { theme } from "./theme";

/** Providers globales. El estado que debe sobrevivir al cambio de ruta se monta aquí. */
export function AppProviders({ children }: { children: ReactNode }) {
    return (
        <ThemeProvider theme={theme}>
            <CssBaseline />
            <ComparisonSelectionProvider>
                {children}
            </ComparisonSelectionProvider>
        </ThemeProvider>
    );
}

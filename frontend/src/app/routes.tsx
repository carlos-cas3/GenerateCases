import { createBrowserRouter, Navigate } from "react-router-dom";
import type { RouteObject } from "react-router-dom";
import { ComparisonPage } from "@/features/comparison";
import { GenerationPage } from "@/features/generation";
import { AppShell } from "./AppShell";
import { HistoryRoute } from "./HistoryRoute";
import { ROUTES } from "./paths";

export const routes: RouteObject[] = [
    {
        path: ROUTES.generation,
        element: <AppShell />,
        children: [
            { index: true, element: <GenerationPage /> },
            { path: ROUTES.history, element: <HistoryRoute /> },
            { path: ROUTES.comparison, element: <ComparisonPage /> },
            { path: "*", element: <Navigate to={ROUTES.generation} replace /> },
        ],
    },
];

export const router = createBrowserRouter(routes);

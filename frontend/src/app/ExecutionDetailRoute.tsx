import { useLocation, useNavigate, useParams } from "react-router-dom";
import { ExecutionDetailPage } from "@/features/history";
import { ROUTES } from "./paths";

/** Extrae el identificador de la URL y se lo pasa a la página (la feature no conoce el router). */
export function ExecutionDetailRoute() {
    const { executionId = "" } = useParams();
    const { pathname } = useLocation();
    const navigate = useNavigate();

    return (
        <ExecutionDetailPage
            executionId={executionId}
            routePath={pathname}
            onBack={() => navigate(ROUTES.history)}
        />
    );
}

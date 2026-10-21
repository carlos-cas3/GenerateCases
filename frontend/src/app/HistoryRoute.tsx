import { useNavigate } from "react-router-dom";
import { useComparisonSelection } from "@/features/comparison";
import { HistoryPage } from "@/features/history";
import { ROUTES } from "./paths";

/**
 * Aquí se conectan dos features entre sí.
 * «history» no conoce a «comparison»: avisa «quiero comparar este par» y la app decide
 * guardar la selección y navegar.
 */
export function HistoryRoute() {
    const navigate = useNavigate();
    const { selectPair } = useComparisonSelection();

    return (
        <HistoryPage
            onCompare={(pair) => {
                selectPair(pair);
                navigate(ROUTES.comparison);
            }}
        />
    );
}

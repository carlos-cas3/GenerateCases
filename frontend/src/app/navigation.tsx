import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import CompareArrowsRoundedIcon from "@mui/icons-material/CompareArrowsRounded";
import HistoryRoundedIcon from "@mui/icons-material/HistoryRounded";
import type { NavItem } from "@/components/layout";
import { ROUTES } from "./paths";

/** Opciones del topbar. Agrega o quita elementos aquí. */
export const NAV_ITEMS: NavItem[] = [
    {
        key: "generation",
        label: "Generación",
        href: ROUTES.generation,
        icon: <AutoAwesomeOutlinedIcon fontSize="small" />,
    },
    {
        key: "history",
        label: "Historial",
        href: ROUTES.history,
        icon: <HistoryRoundedIcon fontSize="small" />,
    },
    {
        key: "comparison",
        label: "Comparación",
        href: ROUTES.comparison,
        icon: <CompareArrowsRoundedIcon fontSize="small" />,
    },
];

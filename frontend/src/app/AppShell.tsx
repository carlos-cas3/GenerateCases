import { matchPath, Outlet, useLocation, useNavigate } from "react-router-dom";
import { AppLayout } from "@/components/layout";
import { NAV_ITEMS } from "./navigation";
import { ROUTES } from "./paths";

/** Ruta «layout»: topbar con la navegación + la vista activa (Outlet). */
export function AppShell() {
    const navigate = useNavigate();
    const { pathname } = useLocation();

    const active = NAV_ITEMS.find(
        (item) =>
            item.href &&
            matchPath(
                { path: item.href, end: item.href === ROUTES.generation },
                pathname,
            ),
    );

    const handleNavigate = (key: string) => {
        const target = NAV_ITEMS.find((item) => item.key === key)?.href;
        if (target) navigate(target);
    };

    return (
        <AppLayout
            brand="TestGen"
            navItems={NAV_ITEMS}
            activeKey={active?.key ?? ""}
            onNavigate={handleNavigate}
        >
            <Outlet />
        </AppLayout>
    );
}

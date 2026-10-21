import { useState } from 'react';
import type { ReactNode } from 'react';
import AppBar from '@mui/material/AppBar';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Drawer from '@mui/material/Drawer';
import IconButton from '@mui/material/IconButton';
import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Toolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';
import MenuRoundedIcon from '@mui/icons-material/MenuRounded';
import CloseRoundedIcon from '@mui/icons-material/CloseRounded';

export interface NavItem {
  key: string;
  label: string;
  icon?: ReactNode;
  /** Opcional: si usas un router, pásalo para que sea un enlace real. */
  href?: string;
}

export interface AppLayoutProps {
  navItems: NavItem[];
  activeKey: string;
  onNavigate: (key: string) => void;
  /** Logo o nombre de la app, a la izquierda del topbar. */
  brand?: ReactNode;
  /** Contenido a la derecha del topbar (usuario, ajustes…). */
  actions?: ReactNode;
  children: ReactNode;
}

const TOPBAR_HEIGHT = 56;

/**
 * Layout con topbar fijo y navegación dentro de la barra.
 * Sin sidebar: el contenido usa todo el ancho disponible y la página decide su propio contenedor.
 */
export function AppLayout({ navItems, activeKey, onNavigate, brand, actions, children }: AppLayoutProps) {
  const [drawerOpen, setDrawerOpen] = useState(false);

  const go = (key: string) => {
    onNavigate(key);
    setDrawerOpen(false);
  };

  return (
    <Box sx={{ minHeight: '100dvh', display: 'flex', flexDirection: 'column', bgcolor: 'background.default' }}>
      <AppBar
        position="sticky"
        color="inherit"
        elevation={0}
        sx={{ bgcolor: 'background.paper', borderBottom: '1px solid', borderColor: 'divider' }}
      >
        <Toolbar disableGutters sx={{ minHeight: TOPBAR_HEIGHT, px: { xs: 1.5, md: 3 }, gap: { xs: 1, md: 3 } }}>
          <IconButton
            edge="start"
            aria-label="Abrir menú de navegación"
            onClick={() => setDrawerOpen(true)}
            sx={{ display: { xs: 'inline-flex', md: 'none' } }}
          >
            <MenuRoundedIcon />
          </IconButton>

          <Typography variant="subtitle1" component="div" noWrap sx={{ fontWeight: 700, color: 'primary.main' }}>
            {brand}
          </Typography>

          <Box
            component="nav"
            aria-label="Navegación principal"
            sx={{ display: { xs: 'none', md: 'flex' }, alignItems: 'stretch', gap: 0.5, height: TOPBAR_HEIGHT }}
          >
            {navItems.map((item) => {
              const active = item.key === activeKey;
              return (
                <Button
                  key={item.key}
                  href={item.href}
                  onClick={(e) => {
                    if (!item.href) e.preventDefault();
                    go(item.key);
                  }}
                  aria-current={active ? 'page' : undefined}
                  startIcon={item.icon}
                  sx={{
                    position: 'relative',
                    px: 1.75,
                    borderRadius: 0,
                    color: active ? 'primary.main' : 'text.secondary',
                    '&:hover': { bgcolor: 'action.hover', color: 'text.primary' },
                    '&::after': {
                      content: '""',
                      position: 'absolute',
                      left: 12,
                      right: 12,
                      bottom: 0,
                      height: 3,
                      borderRadius: '3px 3px 0 0',
                      bgcolor: active ? 'primary.main' : 'transparent',
                    },
                  }}
                >
                  {item.label}
                </Button>
              );
            })}
          </Box>

          <Box sx={{ flex: 1 }} />
          {actions}
        </Toolbar>
      </AppBar>

      <Drawer
        anchor="left"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        sx={{ display: { md: 'none' } }}
        slotProps={{ paper: { sx: { width: 280 } } }}
      >
        <Toolbar sx={{ justifyContent: 'space-between', minHeight: TOPBAR_HEIGHT }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700, color: 'primary.main' }}>
            {brand}
          </Typography>
          <IconButton aria-label="Cerrar menú" onClick={() => setDrawerOpen(false)}>
            <CloseRoundedIcon />
          </IconButton>
        </Toolbar>
        <List component="nav" aria-label="Navegación principal" sx={{ px: 1 }}>
          {navItems.map((item) => (
            <ListItemButton
              key={item.key}
              selected={item.key === activeKey}
              onClick={() => go(item.key)}
              aria-current={item.key === activeKey ? 'page' : undefined}
              sx={{ borderRadius: 2 }}
            >
              {item.icon && <ListItemIcon sx={{ minWidth: 40 }}>{item.icon}</ListItemIcon>}
              <ListItemText primary={item.label} />
            </ListItemButton>
          ))}
        </List>
      </Drawer>

      {/* El contenido ocupa todo el espacio restante; cada página define su ancho máximo. */}
      <Box component="main" sx={{ flex: 1, minWidth: 0 }}>
        {children}
      </Box>
    </Box>
  );
}

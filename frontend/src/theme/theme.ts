import { createTheme } from '@mui/material/styles';

/**
 * Tokens de diseño de la aplicación.
 * Todas las cards leen sus colores del tema: cambiar un valor aquí
 * actualiza todas las tarjetas sin tocar su implementación.
 */
export const theme = createTheme({
  cssVariables: true,
  palette: {
    mode: 'light',
    primary: { main: '#3459B8' },
    success: { main: '#16794C' },
    error: { main: '#B42318' },
    warning: { main: '#CA8A04', dark: '#A16207' },
    background: { default: '#F8FAFC', paper: '#FFFFFF' },
    text: { primary: '#172033', secondary: '#64748B' },
    divider: '#E2E8F0',
  },
  shape: { borderRadius: 12 },
  typography: {
    fontFamily:
      'Inter, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    h6: { fontSize: '1.0625rem', fontWeight: 600, lineHeight: 1.35 },
    subtitle2: { fontWeight: 600 },
    body2: { lineHeight: 1.55 },
    button: { textTransform: 'none', fontWeight: 600 },
  },
  components: {
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: { root: { borderRadius: 10 } },
    },
    MuiChip: { styleOverrides: { root: { fontWeight: 600 } } },
  },
});

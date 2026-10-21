import AutoAwesomeOutlinedIcon from '@mui/icons-material/AutoAwesomeOutlined';
import HistoryRoundedIcon from '@mui/icons-material/HistoryRounded';
import CompareArrowsRoundedIcon from '@mui/icons-material/CompareArrowsRounded';
import type { NavItem } from '../components/layout';

/** Opciones del topbar. Agrega o quita elementos aquí. */
export const NAV_ITEMS: NavItem[] = [
  { key: 'generation', label: 'Generación', icon: <AutoAwesomeOutlinedIcon fontSize="small" /> },
  { key: 'history', label: 'Historial', icon: <HistoryRoundedIcon fontSize="small" /> },
  { key: 'compare', label: 'Comparación', icon: <CompareArrowsRoundedIcon fontSize="small" /> },
];

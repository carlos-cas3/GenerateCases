import Button from '@mui/material/Button';
import Tooltip from '@mui/material/Tooltip';
import CompareArrowsRoundedIcon from '@mui/icons-material/CompareArrowsRounded';
import type { CompareStatus } from '../utils/comparison';

export interface CompareButtonProps {
  status: CompareStatus;
  onClick: () => void;
}

/** Botón del topbar. Desactivado por defecto; se activa solo si la selección cumple la regla. */
export function CompareButton({ status, onClick }: CompareButtonProps) {
  return (
    <Tooltip title={status.message}>
      {/* El <span> permite mostrar el tooltip aunque el botón esté deshabilitado. */}
      <span>
        <Button
          variant="contained"
          size="small"
          startIcon={<CompareArrowsRoundedIcon />}
          disabled={!status.canCompare}
          onClick={onClick}
        >
          Comparar
        </Button>
      </span>
    </Tooltip>
  );
}

import { useId } from 'react';
import type { ReactNode } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import Typography from '@mui/material/Typography';
import { DIALOG_BACKDROP_SX, DIALOG_PAPER_SX } from '../../../components/dialogs/dialogStyles';
import type { MetricInfo } from '../types';
import { MetricIconBadge } from './MetricIconBadge';

export interface MetricDetailDialogProps {
  open: boolean;
  onClose: () => void;
  metric: MetricInfo;
  /** Valores de la métrica (una barra, o dos barras + diferencia). */
  children: ReactNode;
}

/** Modal centrado y simple: el fondo translúcido concentra la atención en el detalle. */
export function MetricDetailDialog({ open, onClose, metric, children }: MetricDetailDialogProps) {
  const titleId = useId();
  const descriptionId = useId();

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      slotProps={{ backdrop: { sx: DIALOG_BACKDROP_SX }, paper: { sx: DIALOG_PAPER_SX } }}
    >
      <DialogTitle id={titleId} sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
        <MetricIconBadge icon={metric.icon} size={40} />
        {metric.name}
      </DialogTitle>

      <DialogContent>
        <DialogContentText id={descriptionId}>{metric.description}</DialogContentText>

        <Box sx={{ mt: 2.5, display: 'flex', flexDirection: 'column', gap: 1.5 }}>{children}</Box>

        <Box sx={{ mt: 3 }}>
          <Typography variant="subtitle2">Detalle</Typography>
          <Typography variant="body2" color="text.secondary">
            {metric.detail ?? 'El detalle ampliado de esta métrica aún no está definido.'}
          </Typography>
        </Box>
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 2.5 }}>
        <Button onClick={onClose} autoFocus>
          Cerrar
        </Button>
      </DialogActions>
    </Dialog>
  );
}

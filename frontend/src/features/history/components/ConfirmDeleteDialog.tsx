import { useId } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import CircularProgress from '@mui/material/CircularProgress';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import WarningAmberRoundedIcon from '@mui/icons-material/WarningAmberRounded';
import { DIALOG_BACKDROP_SX, DIALOG_PAPER_SX } from '../../../components/dialogs/dialogStyles';
import type { ExecutionRecord } from '../types';

export interface ConfirmDeleteDialogProps {
  open: boolean;
  /** Ejecuciones que se eliminarán. 1 → se muestra el nombre; 2 o más → la cantidad. */
  items: ExecutionRecord[];
  isDeleting?: boolean;
  errorMessage?: string;
  onCancel: () => void;
  onConfirm: () => void;
}

export function ConfirmDeleteDialog({
  open,
  items,
  isDeleting = false,
  errorMessage,
  onCancel,
  onConfirm,
}: ConfirmDeleteDialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const isSingle = items.length === 1;

  return (
    <Dialog
      open={open}
      onClose={isDeleting ? undefined : onCancel}
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      maxWidth="xs"
      fullWidth
      slotProps={{
        backdrop: { sx: DIALOG_BACKDROP_SX },
        paper: { sx: DIALOG_PAPER_SX },
      }}
    >
      <DialogTitle id={titleId} sx={{ display: 'flex', alignItems: 'center', gap: 1.5, pb: 1 }}>
        <Box
          aria-hidden
          sx={{
            display: 'grid',
            placeItems: 'center',
            width: 40,
            height: 40,
            borderRadius: '50%',
            bgcolor: 'color-mix(in srgb, var(--mui-palette-error-main) 12%, white)',
            color: 'error.main',
            flexShrink: 0,
          }}
        >
          <WarningAmberRoundedIcon />
        </Box>
        {isSingle ? 'Eliminar ejecución' : 'Eliminar ejecuciones'}
      </DialogTitle>

      <DialogContent>
        <DialogContentText id={descriptionId} component="div" sx={{ color: 'text.secondary' }}>
          {isSingle ? (
            <>
              ¿Deseas eliminar la ejecución del documento{' '}
              <Box component="strong" sx={{ color: 'text.primary', wordBreak: 'break-all' }}>
                «{items[0]?.documentName}»
              </Box>
              ?
            </>
          ) : (
            <>
              ¿Deseas eliminar{' '}
              <Box component="strong" sx={{ color: 'text.primary' }}>
                {items.length} ejecuciones
              </Box>{' '}
              seleccionadas?
            </>
          )}{' '}
          Esta acción no se puede deshacer.
        </DialogContentText>
        {errorMessage && (
          <Alert severity="error" variant="outlined" sx={{ mt: 2 }}>
            {errorMessage}
          </Alert>
        )}
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 2.5, gap: 1 }}>
        <Button onClick={onCancel} disabled={isDeleting} color="inherit" autoFocus>
          Cancelar
        </Button>
        <Button
          onClick={onConfirm}
          disabled={isDeleting}
          color="error"
          variant="contained"
          startIcon={isDeleting ? <CircularProgress size={16} color="inherit" /> : undefined}
        >
          {isDeleting ? 'Eliminando…' : isSingle ? 'Eliminar' : `Eliminar (${items.length})`}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

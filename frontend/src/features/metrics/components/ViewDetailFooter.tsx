import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import OpenInFullRoundedIcon from '@mui/icons-material/OpenInFullRounded';

export interface ViewDetailFooterProps {
  metricName: string;
  onClick: () => void;
}

/** Contenedor inferior de la card con el botón que abre el modal de detalle. */
export function ViewDetailFooter({ metricName, onClick }: ViewDetailFooterProps) {
  return (
    <Box sx={{ mt: 'auto', pt: 2, borderTop: '1px solid', borderColor: 'divider' }}>
      <Button
        fullWidth
        variant="outlined"
        endIcon={<OpenInFullRoundedIcon fontSize="small" />}
        onClick={onClick}
        aria-haspopup="dialog"
        aria-label={`Ver detalle de ${metricName}`}
      >
        Ver detalle
      </Button>
    </Box>
  );
}

import type { ReactNode } from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import type { SxProps, Theme } from '@mui/material/styles';

export interface CardHeaderProps {
  /** Id aplicado al título; lo usa BaseCard para `aria-labelledby`. */
  titleId?: string;
  title?: ReactNode;
  description?: ReactNode;
  /** Contenido alineado a la derecha (chip de estado, botón, etc.). */
  action?: ReactNode;
  sx?: SxProps<Theme>;
}

/**
 * Cabecera genérica de una card: título + descripción + acción opcional.
 * Si no hay título, descripción ni acción, no renderiza nada.
 */
export function CardHeader({ titleId, title, description, action, sx }: CardHeaderProps) {
  if (!title && !description && !action) return null;

  return (
    <Box
      sx={[
        {
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 2,
          flexWrap: 'wrap',
        },
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    >
      <Box sx={{ minWidth: 0, flex: '1 1 14rem' }}>
        {title && (
          <Typography id={titleId} variant="h6" component="h2" color="text.primary">
            {title}
          </Typography>
        )}
        {description && (
          <Typography variant="body2" color="text.secondary" sx={{ mt: title ? 0.5 : 0 }}>
            {description}
          </Typography>
        )}
      </Box>
      {action && <Box sx={{ flexShrink: 0, maxWidth: '100%' }}>{action}</Box>}
    </Box>
  );
}

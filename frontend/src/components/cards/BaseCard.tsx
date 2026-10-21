import { useId } from 'react';
import type { ElementType, ReactNode } from 'react';
import Paper from '@mui/material/Paper';
import Box from '@mui/material/Box';
import type { SxProps, Theme } from '@mui/material/styles';
import { CardHeader } from './CardHeader';

export interface BaseCardProps {
  title?: ReactNode;
  description?: ReactNode;
  /** Contenido a la derecha de la cabecera. */
  headerAction?: ReactNode;
  /** Reemplaza por completo la cabecera por defecto. */
  header?: ReactNode;
  children?: ReactNode;
  /** Estilos del contenedor raíz. Aquí se pueden sobrescribir ancho, alto, gridArea, etc. */
  sx?: SxProps<Theme>;
  /** Estilos del área de contenido. */
  contentSx?: SxProps<Theme>;
  className?: string;
  /** Nombre accesible cuando no hay `title` (p. ej. con una cabecera personalizada). */
  ariaLabel?: string;
  /** Elemento HTML raíz. Por defecto `section`. */
  component?: ElementType;
}

/**
 * Tarjeta visual reutilizable. No conoce nada del dominio.
 *
 * Layout: NO fija ancho, alto ni posición. Ocupa el 100 % del espacio que le
 * asigne su contenedor (celda de grid, item de flex, etc.).
 */
export function BaseCard({
  title,
  description,
  headerAction,
  header,
  children,
  sx,
  contentSx,
  className,
  ariaLabel,
  component = 'section',
}: BaseCardProps) {
  const titleId = useId();
  const hasDefaultHeader = !header && (title || description || headerAction);

  return (
    <Paper
      component={component}
      variant="outlined"
      className={className}
      aria-labelledby={title ? titleId : undefined}
      aria-label={title ? undefined : ariaLabel}
      sx={[
        {
          display: 'flex',
          flexDirection: 'column',
          gap: 2.5,
          height: '100%',
          minWidth: 0,
          p: { xs: 2, sm: 3 },
          borderRadius: '14px',
          borderColor: 'divider',
          bgcolor: 'background.paper',
          boxShadow: '0 1px 2px rgba(15, 23, 42, 0.04)',
        },
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    >
      {header}
      {hasDefaultHeader && (
        <CardHeader titleId={titleId} title={title} description={description} action={headerAction} />
      )}
      {children !== undefined && (
        <Box
          sx={[
            { display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, minWidth: 0 },
            ...(Array.isArray(contentSx) ? contentSx : [contentSx]),
          ]}
        >
          {children}
        </Box>
      )}
    </Paper>
  );
}

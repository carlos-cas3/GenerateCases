import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Typography from '@mui/material/Typography';
import { BaseCard } from '../../../components/cards';

/**
 * Ejemplo de BaseCard con contenido propio: no depende del dominio
 * y su tamaño lo decide quien lo coloque (aquí, `maxWidth` desde fuera).
 */
export function BaseCardExample() {
  return (
    <BaseCard
      title="Resumen de métricas"
      description="Ejemplo de tarjeta con contenido personalizado."
      headerAction={<Chip size="small" label="Demo" color="primary" variant="outlined" />}
      sx={{ maxWidth: 420 }}
    >
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <Typography variant="h4" component="p">
          128 casos
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Generados en las últimas 3 ejecuciones.
        </Typography>
        <Button variant="outlined" sx={{ alignSelf: 'flex-start' }}>
          Ver reporte
        </Button>
      </Box>
    </BaseCard>
  );
}

import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Skeleton from '@mui/material/Skeleton';
import Typography from '@mui/material/Typography';
import type { SxProps, Theme } from '@mui/material/styles';
import HistoryRoundedIcon from '@mui/icons-material/HistoryRounded';
import InsertDriveFileOutlinedIcon from '@mui/icons-material/InsertDriveFileOutlined';
import { BaseCard } from '../../../components/cards';
import type { RecentExecution } from '../types';
import { formatDateTime } from '../../../shared/utils/formatDateTime';
import { StatusChip } from '../../../shared/execution/StatusChip';

export interface RecentExecutionsCardProps {
  executions: RecentExecution[];
  /** Cantidad máxima de registros visibles (2 o 3 según el diseño). */
  maxItems?: number;
  onViewDetails: (executionId: string) => void;
  isLoading?: boolean;
  errorMessage?: string;
  onRetry?: () => void;
  emptyMessage?: string;
  sx?: SxProps<Theme>;
}

export function RecentExecutionsCard({
  executions,
  maxItems = 3,
  onViewDetails,
  isLoading = false,
  errorMessage,
  onRetry,
  emptyMessage = 'Todavía no hay ejecuciones. Cuando generes casos de prueba aparecerán aquí.',
  sx,
}: RecentExecutionsCardProps) {
  const visible = executions.slice(0, maxItems);

  return (
    <BaseCard
      title="Ejecuciones recientes"
      description="Consulta rápidamente tus últimas generaciones."
      sx={sx}
    >
      {isLoading ? (
        <Box aria-busy="true" sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
          {Array.from({ length: Math.min(maxItems, 3) }).map((_, i) => (
            <Skeleton key={i} variant="rounded" height={64} />
          ))}
        </Box>
      ) : errorMessage ? (
        <Alert
          severity="error"
          variant="outlined"
          action={
            onRetry && (
              <Button color="inherit" size="small" onClick={onRetry}>
                Reintentar
              </Button>
            )
          }
        >
          {errorMessage}
        </Alert>
      ) : visible.length === 0 ? (
        <Box
          sx={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 1,
            py: 3,
            textAlign: 'center',
            color: 'text.secondary',
          }}
        >
          <HistoryRoundedIcon sx={{ fontSize: 36 }} aria-hidden />
          <Typography variant="body2" sx={{ maxWidth: 320 }}>
            {emptyMessage}
          </Typography>
        </Box>
      ) : (
        <Box component="ul" sx={{ m: 0, p: 0, display: 'flex', flexDirection: 'column', gap: 1.5 }}>
          {visible.map((execution) => (
            <Box
              component="li"
              key={execution.id}
              sx={{
                listStyle: 'none',
                display: 'flex',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: 1.5,
                p: 1.5,
                border: '1px solid',
                borderColor: 'divider',
                borderRadius: '12px',
              }}
            >
              <InsertDriveFileOutlinedIcon sx={{ color: 'text.secondary' }} aria-hidden />
              <Box sx={{ minWidth: 0, flex: '1 1 10rem' }}>
                <Typography variant="subtitle2" noWrap title={execution.documentName}>
                  {execution.documentName}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {formatDateTime(execution.createdAt)}
                </Typography>
              </Box>
              <StatusChip status={execution.status} />
              <Button
                size="small"
                variant="outlined"
                onClick={() => onViewDetails(execution.id)}
                aria-label={`Ver detalles de ${execution.documentName}`}
              >
                Ver detalles
              </Button>
            </Box>
          ))}
        </Box>
      )}
    </BaseCard>
  );
}

import type { ReactNode } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import IconButton from '@mui/material/IconButton';
import Skeleton from '@mui/material/Skeleton';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TablePagination from '@mui/material/TablePagination';
import TableRow from '@mui/material/TableRow';
import TableSortLabel from '@mui/material/TableSortLabel';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import type { SxProps, Theme } from '@mui/material/styles';
import DeleteOutlineRoundedIcon from '@mui/icons-material/DeleteOutlineRounded';
import EditOutlinedIcon from '@mui/icons-material/EditOutlined';
import SearchOffOutlinedIcon from '@mui/icons-material/SearchOffOutlined';
import VisibilityOutlinedIcon from '@mui/icons-material/VisibilityOutlined';
import { BaseCard } from '../../../components/cards';
import { StatusChip } from '../../../shared/components/StatusChip';
import { formatDateTime } from '../../../shared/utils/formatDateTime';
import { HISTORY_STATUS_LABEL, PAGE_SIZE_OPTIONS } from '../constants';
import type { PageSize } from '../constants';
import type { ExecutionRecord, SortKey, SortState } from '../types';
import type { CompareStatus } from '../utils/comparison';
import { getDeleteTargets, isMultiSelection } from '../utils/selection';
import { TruncatedFileName } from './TruncatedFileName';

export interface ExecutionHistoryTableCardProps {
  /** Filas de la página actual (ya filtradas y ordenadas). */
  rows: ExecutionRecord[];
  /** Total de filas tras aplicar los filtros. */
  totalCount: number;
  hasActiveFilters: boolean;
  onClearFilters: () => void;

  sort: SortState;
  onSortChange: (key: SortKey) => void;

  page: number;
  pageSize: PageSize;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: PageSize) => void;

  selected: ExecutionRecord[];
  onToggleSelect: (record: ExecutionRecord) => void;
  onClearSelection: () => void;
  compareStatus: CompareStatus;

  onView: (record: ExecutionRecord) => void;
  onEdit: (record: ExecutionRecord) => void;
  /** Pide confirmar la eliminación de las ejecuciones indicadas (la fila o toda la selección). */
  onDeleteRequest: (targets: ExecutionRecord[]) => void;

  isLoading?: boolean;
  errorMessage?: string;
  onRetry?: () => void;
  sx?: SxProps<Theme>;
}

interface SortableColumn {
  key: SortKey;
  label: string;
  /** Texto accesible para las abreviaturas. */
  description?: string;
  numeric?: boolean;
}

const COLUMN_COUNT = 9; // checkbox + 7 columnas + acciones

const SORTABLE: Record<'document' | 'date' | 'hu' | 'rf' | 'cp', SortableColumn> = {
  document: { key: 'documentName', label: 'Documento' },
  date: { key: 'uploadedAt', label: 'Fecha de subida' },
  hu: { key: 'huCount', label: 'HU', description: 'Historias de usuario', numeric: true },
  rf: { key: 'rfCount', label: 'RF', description: 'Requisitos funcionales', numeric: true },
  cp: { key: 'cpCount', label: 'CP', description: 'Casos de prueba', numeric: true },
};

function SortableHeader({
  column,
  sort,
  onSortChange,
}: {
  column: SortableColumn;
  sort: SortState;
  onSortChange: (key: SortKey) => void;
}) {
  const active = sort.key === column.key;
  const label = (
    <TableSortLabel
      active={active}
      direction={active ? sort.direction : 'asc'}
      onClick={() => onSortChange(column.key)}
    >
      {column.label}
    </TableSortLabel>
  );

  return (
    <TableCell
      align={column.numeric ? 'right' : 'left'}
      sortDirection={active ? sort.direction : false}
      sx={{ whiteSpace: 'nowrap', fontWeight: 600 }}
    >
      {column.description ? <Tooltip title={column.description}>{label}</Tooltip> : label}
    </TableCell>
  );
}

const count = (value: number | null) => (value === null ? '—' : value);

interface ActionButtonProps {
  label: string;
  ariaLabel: string;
  icon: ReactNode;
  onClick: () => void;
  disabled?: boolean;
  disabledReason?: string;
  /** Verde = ver, amarillo = editar, rojo = eliminar. Al deshabilitarse, MUI lo pinta gris. */
  color?: 'success' | 'warning' | 'error';
}

function ActionButton({ label, ariaLabel, icon, onClick, disabled = false, disabledReason, color }: ActionButtonProps) {
  return (
    // describeChild: el texto del tooltip es una descripción, no reemplaza el aria-label del botón.
    <Tooltip title={disabled && disabledReason ? disabledReason : label} describeChild>
      {/* El <span> permite mostrar el tooltip aunque el botón esté deshabilitado. */}
      <span>
        <IconButton size="small" color={color} aria-label={ariaLabel} disabled={disabled} onClick={onClick}>
          {icon}
        </IconButton>
      </span>
    </Tooltip>
  );
}

function ClusteringChip({ enabled }: { enabled: boolean }) {
  return (
    <Chip
      size="small"
      label={enabled ? 'Sí' : 'No'}
      color={enabled ? 'primary' : 'default'}
      variant={enabled ? 'filled' : 'outlined'}
      sx={{ minWidth: 44 }}
    />
  );
}

export function ExecutionHistoryTableCard({
  rows,
  totalCount,
  hasActiveFilters,
  onClearFilters,
  sort,
  onSortChange,
  page,
  pageSize,
  onPageChange,
  onPageSizeChange,
  selected,
  onToggleSelect,
  onClearSelection,
  compareStatus,
  onView,
  onEdit,
  onDeleteRequest,
  isLoading = false,
  errorMessage,
  onRetry,
  sx,
}: ExecutionHistoryTableCardProps) {
  // Ver y Editar son de a una ejecución: se bloquean (y quedan grises) con 2 o más seleccionadas.
  const multiSelection = isMultiSelection(selected);
  const singleOnlyReason = 'Disponible solo con una ejecución a la vez';

  return (
    <BaseCard
      title="Historial de ejecuciones"
      description="Selecciona 2 ejecuciones del mismo documento para compararlas, o varias para eliminarlas."
      headerAction={
        selected.length > 0 ? (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <Typography variant="body2" color="text.secondary" aria-live="polite">
              {selected.length} {selected.length === 1 ? 'seleccionada' : 'seleccionadas'}
            </Typography>
            <Button size="small" onClick={onClearSelection}>
              Limpiar selección
            </Button>
          </Box>
        ) : undefined
      }
      sx={sx}
      contentSx={{ gap: 1 }}
    >
      {selected.length > 0 && (
        <Typography
          variant="body2"
          role="status"
          sx={{ color: compareStatus.canCompare ? 'success.main' : 'text.secondary', fontWeight: 500 }}
        >
          {compareStatus.message}
        </Typography>
      )}

      {errorMessage ? (
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
      ) : (
        <>
          <TableContainer sx={{ overflowX: 'auto' }}>
            <Table size="medium" aria-label="Historial de ejecuciones" sx={{ minWidth: 960 }}>
              <TableHead>
                <TableRow>
                  <TableCell padding="checkbox">
                    <Box component="span" sx={visuallyHidden}>
                      Seleccionar para comparar
                    </Box>
                  </TableCell>
                  <SortableHeader column={SORTABLE.document} sort={sort} onSortChange={onSortChange} />
                  <SortableHeader column={SORTABLE.date} sort={sort} onSortChange={onSortChange} />
                  <TableCell sx={{ fontWeight: 600 }}>Estado</TableCell>
                  <SortableHeader column={SORTABLE.hu} sort={sort} onSortChange={onSortChange} />
                  <SortableHeader column={SORTABLE.rf} sort={sort} onSortChange={onSortChange} />
                  <SortableHeader column={SORTABLE.cp} sort={sort} onSortChange={onSortChange} />
                  <TableCell sx={{ fontWeight: 600 }}>Clustering</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 600 }}>
                    Acciones
                  </TableCell>
                </TableRow>
              </TableHead>

              <TableBody>
                {isLoading &&
                  Array.from({ length: pageSize }).map((_, i) => (
                    <TableRow key={i} aria-busy="true">
                      {Array.from({ length: COLUMN_COUNT }).map((__, j) => (
                        <TableCell key={j}>
                          <Skeleton width={j === 0 ? 24 : '80%'} />
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}

                {!isLoading && rows.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={COLUMN_COUNT} sx={{ border: 0 }}>
                      <Box
                        sx={{
                          display: 'flex',
                          flexDirection: 'column',
                          alignItems: 'center',
                          gap: 1,
                          py: 5,
                          textAlign: 'center',
                          color: 'text.secondary',
                        }}
                      >
                        <SearchOffOutlinedIcon sx={{ fontSize: 36 }} aria-hidden />
                        <Typography variant="body2">
                          {hasActiveFilters
                            ? 'No se encontraron ejecuciones con los filtros aplicados.'
                            : 'Aún no hay ejecuciones registradas.'}
                        </Typography>
                        {hasActiveFilters && (
                          <Button size="small" onClick={onClearFilters}>
                            Limpiar filtros
                          </Button>
                        )}
                      </Box>
                    </TableCell>
                  </TableRow>
                )}

                {!isLoading &&
                  rows.map((record) => {
                    const isSelected = selected.some((item) => item.id === record.id);
                    const deleteTargets = getDeleteTargets(record, selected);

                    return (
                      <TableRow key={record.id} hover selected={isSelected}>
                        <TableCell padding="checkbox">
                          <Checkbox
                            checked={isSelected}
                            onChange={() => onToggleSelect(record)}
                            slotProps={{
                              input: {
                                'aria-label': `Seleccionar ${record.documentName}, ${
                                  record.clustering ? 'con' : 'sin'
                                } clustering`,
                              },
                            }}
                          />
                        </TableCell>
                        <TableCell sx={{ minWidth: 240, maxWidth: 320 }}>
                          <TruncatedFileName name={record.documentName} />
                        </TableCell>
                        <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDateTime(record.uploadedAt)}</TableCell>
                        <TableCell>
                          <StatusChip status={record.status} label={HISTORY_STATUS_LABEL[record.status]} />
                        </TableCell>
                        <TableCell align="right" sx={numericCell}>
                          {count(record.huCount)}
                        </TableCell>
                        <TableCell align="right" sx={numericCell}>
                          {count(record.rfCount)}
                        </TableCell>
                        <TableCell align="right" sx={numericCell}>
                          {count(record.cpCount)}
                        </TableCell>
                        <TableCell>
                          <ClusteringChip enabled={record.clustering} />
                        </TableCell>
                        <TableCell align="right">
                          <Box
                            role="group"
                            aria-label={`Acciones de ${record.documentName}`}
                            sx={{ display: 'inline-flex', gap: 0.5 }}
                          >
                            <ActionButton
                              label="Ver detalles"
                              ariaLabel={`Ver detalles de ${record.documentName}`}
                              icon={<VisibilityOutlinedIcon fontSize="small" />}
                              color="success"
                              disabled={multiSelection}
                              disabledReason={singleOnlyReason}
                              onClick={() => onView(record)}
                            />
                            <ActionButton
                              label="Editar"
                              ariaLabel={`Editar ${record.documentName}`}
                              icon={<EditOutlinedIcon fontSize="small" />}
                              color="warning"
                              disabled={multiSelection}
                              disabledReason={singleOnlyReason}
                              onClick={() => onEdit(record)}
                            />
                            <ActionButton
                              label={deleteTargets.length > 1 ? `Eliminar ${deleteTargets.length} seleccionadas` : 'Eliminar'}
                              ariaLabel={
                                deleteTargets.length > 1
                                  ? `Eliminar las ${deleteTargets.length} ejecuciones seleccionadas`
                                  : `Eliminar ${record.documentName}`
                              }
                              icon={<DeleteOutlineRoundedIcon fontSize="small" />}
                              color="error"
                              onClick={() => onDeleteRequest(deleteTargets)}
                            />
                          </Box>
                        </TableCell>
                      </TableRow>
                    );
                  })}
              </TableBody>
            </Table>
          </TableContainer>

          {totalCount > 0 && (
            <TablePagination
              component="div"
              count={totalCount}
              page={page}
              rowsPerPage={pageSize}
              rowsPerPageOptions={[...PAGE_SIZE_OPTIONS]}
              onPageChange={(_, next) => onPageChange(next)}
              onRowsPerPageChange={(e) => onPageSizeChange(Number(e.target.value) as PageSize)}
              labelRowsPerPage="Filas por página"
              labelDisplayedRows={({ from, to, count: total }) => `${from}–${to} de ${total}`}
              getItemAriaLabel={(type) =>
                ({ first: 'Primera página', previous: 'Página anterior', next: 'Página siguiente', last: 'Última página' })[
                  type
                ]
              }
              showFirstButton
              showLastButton
              sx={{ borderTop: '1px solid', borderColor: 'divider' }}
            />
          )}
        </>
      )}
    </BaseCard>
  );
}

const numericCell = { fontVariantNumeric: 'tabular-nums' } as const;

const visuallyHidden = {
  position: 'absolute',
  width: 1,
  height: 1,
  overflow: 'hidden',
  clip: 'rect(0 0 0 0)',
  whiteSpace: 'nowrap',
} as const;

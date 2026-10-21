import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import InputAdornment from '@mui/material/InputAdornment';
import MenuItem from '@mui/material/MenuItem';
import TextField from '@mui/material/TextField';
import type { SxProps, Theme } from '@mui/material/styles';
import CloseRoundedIcon from '@mui/icons-material/CloseRounded';
import FilterAltOffOutlinedIcon from '@mui/icons-material/FilterAltOffOutlined';
import SearchRoundedIcon from '@mui/icons-material/SearchRounded';
import { BaseCard } from '../../../components/cards';
import { HISTORY_STATUS_LABEL, STATUS_FILTER_ORDER } from '../constants';
import type { ClusteringFilter, HistoryFilters, StatusFilter } from '../types';

export interface ExecutionFiltersCardProps {
  filters: HistoryFilters;
  onFiltersChange: (filters: HistoryFilters) => void;
  onClear: () => void;
  hasActiveFilters: boolean;
  sx?: SxProps<Theme>;
}

/** Barra de búsqueda por documento + filtros de estado y clustering, en una sola card. */
export function ExecutionFiltersCard({
  filters,
  onFiltersChange,
  onClear,
  hasActiveFilters,
  sx,
}: ExecutionFiltersCardProps) {
  return (
    <BaseCard sx={[{ height: 'auto' }, ...(Array.isArray(sx) ? sx : [sx])]}>
      <Box
        role="search"
        aria-label="Filtros del historial de ejecuciones"
        sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 2 }}
      >
        <TextField
          size="small"
          label="Buscar por nombre del documento"
          placeholder="Ej.: historias_usuario"
          value={filters.query}
          onChange={(e) => onFiltersChange({ ...filters, query: e.target.value })}
          sx={{ flex: '2 1 260px', minWidth: 0 }}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchRoundedIcon fontSize="small" aria-hidden />
                </InputAdornment>
              ),
              endAdornment: filters.query ? (
                <InputAdornment position="end">
                  <IconButton
                    size="small"
                    edge="end"
                    aria-label="Limpiar búsqueda"
                    onClick={() => onFiltersChange({ ...filters, query: '' })}
                  >
                    <CloseRoundedIcon fontSize="small" />
                  </IconButton>
                </InputAdornment>
              ) : undefined,
            },
          }}
        />

        <TextField
          select
          size="small"
          label="Estado"
          value={filters.status}
          onChange={(e) => onFiltersChange({ ...filters, status: e.target.value as StatusFilter })}
          sx={{ flex: '1 1 170px', minWidth: 0 }}
        >
          <MenuItem value="all">Todos</MenuItem>
          {STATUS_FILTER_ORDER.map((status) => (
            <MenuItem key={status} value={status}>
              {HISTORY_STATUS_LABEL[status]}
            </MenuItem>
          ))}
        </TextField>

        <TextField
          select
          size="small"
          label="Clustering"
          value={filters.clustering}
          onChange={(e) => onFiltersChange({ ...filters, clustering: e.target.value as ClusteringFilter })}
          sx={{ flex: '1 1 150px', minWidth: 0 }}
        >
          <MenuItem value="all">Todos</MenuItem>
          <MenuItem value="yes">Sí</MenuItem>
          <MenuItem value="no">No</MenuItem>
        </TextField>

        <Button
          variant="text"
          startIcon={<FilterAltOffOutlinedIcon />}
          onClick={onClear}
          disabled={!hasActiveFilters}
          sx={{ flexShrink: 0 }}
        >
          Limpiar filtros
        </Button>
      </Box>
    </BaseCard>
  );
}

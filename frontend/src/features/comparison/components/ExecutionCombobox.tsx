import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { StatusChip } from '../../../shared/components/StatusChip';
import { formatDateTime } from '../../../shared/utils/formatDateTime';
import { HISTORY_STATUS_LABEL } from '../../history/constants';
import type { ExecutionRecord } from '../../history/types';

export interface ExecutionComboboxProps {
  id: string;
  /** Ej.: «Ejecución A». */
  label: string;
  /** Ej.: «Con clustering». */
  badge: string;
  badgeColor: 'primary' | 'default';
  options: ExecutionRecord[];
  value: ExecutionRecord | null;
  onChange: (value: ExecutionRecord | null) => void;
  noOptionsText: string;
}

/** Combobox buscable de ejecuciones, con etiqueta visible y datos de la ejecución elegida debajo. */
export function ExecutionCombobox({
  id,
  label,
  badge,
  badgeColor,
  options,
  value,
  onChange,
  noOptionsText,
}: ExecutionComboboxProps) {
  return (
    <Box sx={{ minWidth: 0 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.75 }}>
        <Typography component="label" htmlFor={id} variant="subtitle2">
          {label}
        </Typography>
        <Chip size="small" label={badge} color={badgeColor} variant="outlined" />
      </Box>

      <Autocomplete
        id={id}
        options={options}
        value={value}
        onChange={(_, next) => onChange(next)}
        getOptionLabel={(option) => option.documentName}
        getOptionKey={(option) => option.id}
        isOptionEqualToValue={(option, selected) => option.id === selected.id}
        noOptionsText={noOptionsText}
        openText="Abrir lista"
        closeText="Cerrar lista"
        clearText="Quitar selección"
        autoHighlight
        renderInput={(params) => <TextField {...params} placeholder="Seleccionar una ejecución" />}
        renderOption={(props, option) => {
          const { key, ...liProps } = props as typeof props & { key: string };
          return (
            <li key={key} {...liProps}>
              <Box sx={{ minWidth: 0 }}>
                <Typography variant="body2" sx={{ fontWeight: 600, wordBreak: 'break-all' }}>
                  {option.documentName}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {formatDateTime(option.uploadedAt)} · {HISTORY_STATUS_LABEL[option.status]}
                </Typography>
              </Box>
            </li>
          );
        }}
      />

      {value && (
        <Box sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 1, mt: 1 }}>
          <StatusChip status={value.status} label={HISTORY_STATUS_LABEL[value.status]} />
          <Typography variant="caption" color="text.secondary">
            Subida el {formatDateTime(value.uploadedAt)}
          </Typography>
        </Box>
      )}
    </Box>
  );
}

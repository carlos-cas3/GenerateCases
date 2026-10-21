import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';
import type { SxProps, Theme } from '@mui/material/styles';
import ClearAllRoundedIcon from '@mui/icons-material/ClearAllRounded';
import { BaseCard } from '../../../components/cards';
import type { ExecutionRecord } from '../../history/types';
import { getDocumentBaseName } from '../../history/utils/comparison';
import type { CompareStatus } from '../../history/utils/comparison';
import { splitFileName } from '../../history/utils/fileName';
import { ExecutionCombobox } from './ExecutionCombobox';

export interface ExecutionSelectorCardProps {
  optionsA: ExecutionRecord[];
  optionsB: ExecutionRecord[];
  valueA: ExecutionRecord | null;
  valueB: ExecutionRecord | null;
  onChangeA: (value: ExecutionRecord | null) => void;
  onChangeB: (value: ExecutionRecord | null) => void;
  onClear: () => void;
  /** Resultado de la regla de comparación; solo se evalúa cuando hay A y B. */
  compareStatus: CompareStatus | null;
  sx?: SxProps<Theme>;
}

/** Mensaje de guía bajo los combobox: explica qué se está filtrando y si ya se puede comparar. */
function getHint(
  a: ExecutionRecord | null,
  b: ExecutionRecord | null,
  status: CompareStatus | null,
): { text: string; tone: 'info' | 'success' | 'error' } {
  if (a && b) {
    if (!status?.canCompare) return { text: status?.message ?? '', tone: 'error' };
    const extA = splitFileName(a.documentName).extension;
    const extB = splitFileName(b.documentName).extension;
    const formats = extA.toLowerCase() === extB.toLowerCase() ? '' : ` Formatos distintos: ${extA} (A) y ${extB} (B).`;
    return {
      text: `Comparando «${getDocumentBaseName(a.documentName)}» con clustering (A) y sin clustering (B).${formats}`,
      tone: 'success',
    };
  }
  if (a) {
    return {
      text: `Mostrando solo las ejecuciones sin clustering de «${getDocumentBaseName(a.documentName)}».`,
      tone: 'info',
    };
  }
  if (b) {
    return {
      text: `Mostrando solo las ejecuciones con clustering de «${getDocumentBaseName(b.documentName)}».`,
      tone: 'info',
    };
  }
  return {
    text: 'Elige una ejecución con clustering (A) y una sin clustering (B) del mismo documento. El formato del archivo no importa.',
    tone: 'info',
  };
}

const HINT_COLOR = { info: 'text.secondary', success: 'success.main', error: 'error.main' } as const;

export function ExecutionSelectorCard({
  optionsA,
  optionsB,
  valueA,
  valueB,
  onChangeA,
  onChangeB,
  onClear,
  compareStatus,
  sx,
}: ExecutionSelectorCardProps) {
  const hint = getHint(valueA, valueB, compareStatus);

  return (
    <BaseCard
      title="Ejecuciones a comparar"
      description="La lista de cada ejecución se ajusta automáticamente al documento que elijas en la otra."
      headerAction={
        <Button
          size="small"
          startIcon={<ClearAllRoundedIcon />}
          onClick={onClear}
          disabled={!valueA && !valueB}
        >
          Limpiar selección
        </Button>
      }
      sx={sx}
    >
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <Box
          sx={{
            display: 'grid',
            gap: { xs: 2.5, md: 3 },
            gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: 'repeat(2, minmax(0, 1fr))' },
            alignItems: 'start',
          }}
        >
          <ExecutionCombobox
            id="compare-execution-a"
            label="Ejecución A"
            badge="Con clustering"
            badgeColor="primary"
            options={optionsA}
            value={valueA}
            onChange={onChangeA}
            noOptionsText={
              valueB
                ? `No hay ejecuciones con clustering de «${getDocumentBaseName(valueB.documentName)}».`
                : 'No hay ejecuciones con clustering.'
            }
          />
          <ExecutionCombobox
            id="compare-execution-b"
            label="Ejecución B"
            badge="Sin clustering"
            badgeColor="default"
            options={optionsB}
            value={valueB}
            onChange={onChangeB}
            noOptionsText={
              valueA
                ? `No hay ejecuciones sin clustering de «${getDocumentBaseName(valueA.documentName)}».`
                : 'No hay ejecuciones sin clustering.'
            }
          />
        </Box>

        <Typography variant="body2" role="status" sx={{ color: HINT_COLOR[hint.tone], fontWeight: 500 }}>
          {hint.text}
        </Typography>
      </Box>
    </BaseCard>
  );
}

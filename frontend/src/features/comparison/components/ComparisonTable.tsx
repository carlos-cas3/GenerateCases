//CURRENTLY NOT USED, BUT IT'S A GOOD COMPONENT TO HAVE FOR FUTURE COMPARISON TABLES

import Box from '@mui/material/Box';
import Skeleton from '@mui/material/Skeleton';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { DifferenceValue } from '@/shared/components/DifferenceValue';
import { formatValue } from '@/shared/utils/metricFormat';
import type { ComparisonRow } from '../types';

export interface ComparisonTableProps {
  /** Nombre accesible de la tabla. */
  ariaLabel: string;
  /** Encabezado de la primera columna: «Métrica» o «Artefacto». */
  firstColumnLabel: string;
  rows: ComparisonRow[];
  isLoading?: boolean;
  emptyMessage?: string;
}

const numeric = { fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' } as const;

function ColumnHeader({ title, caption, tooltip }: { title: string; caption?: string; tooltip?: string }) {
  const content = (
    <Box component="span" sx={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'flex-end' }}>
      <span>{title}</span>
      {caption && (
        <Typography variant="caption" color="text.secondary" component="span" sx={{ fontWeight: 400 }}>
          {caption}
        </Typography>
      )}
    </Box>
  );
  return tooltip ? <Tooltip title={tooltip}>{content}</Tooltip> : content;
}

/** Tabla genérica «A vs B + diferencia». La usan las cards de métricas y de artefactos. */
export function ComparisonTable({
  ariaLabel,
  firstColumnLabel,
  rows,
  isLoading = false,
  emptyMessage = 'No hay datos para mostrar.',
}: ComparisonTableProps) {
  return (
    <TableContainer sx={{ overflowX: 'auto' }}>
      <Table aria-label={ariaLabel} sx={{ minWidth: 560 }}>
        <TableHead>
          <TableRow>
            <TableCell sx={{ fontWeight: 600 }}>{firstColumnLabel}</TableCell>
            <TableCell align="right" sx={{ fontWeight: 600 }}>
              <ColumnHeader title="Ejecución A" caption="Con clustering" />
            </TableCell>
            <TableCell align="right" sx={{ fontWeight: 600 }}>
              <ColumnHeader title="Ejecución B" caption="Sin clustering" />
            </TableCell>
            <TableCell align="right" sx={{ fontWeight: 600 }}>
              <ColumnHeader title="Diferencia" caption="A − B" tooltip="Ejecución A menos Ejecución B" />
            </TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {isLoading &&
            Array.from({ length: 3 }).map((_, i) => (
              <TableRow key={i} aria-busy="true">
                {Array.from({ length: 4 }).map((__, j) => (
                  <TableCell key={j}>
                    <Skeleton width={j === 0 ? '70%' : '50%'} sx={{ ml: j === 0 ? 0 : 'auto' }} />
                  </TableCell>
                ))}
              </TableRow>
            ))}

          {!isLoading && rows.length === 0 && (
            <TableRow>
              <TableCell colSpan={4} sx={{ border: 0, py: 4, textAlign: 'center', color: 'text.secondary' }}>
                {emptyMessage}
              </TableCell>
            </TableRow>
          )}

          {!isLoading &&
            rows.map((row) => {
              const unit = row.unit ?? 'count';
              return (
                <TableRow key={row.id} hover>
                  <TableCell component="th" scope="row" sx={{ fontWeight: 500 }}>
                    {row.label}
                  </TableCell>
                  <TableCell align="right" sx={numeric}>
                    {formatValue(row.a, unit)}
                  </TableCell>
                  <TableCell align="right" sx={numeric}>
                    {formatValue(row.b, unit)}
                  </TableCell>
                  <TableCell align="right" sx={numeric}>
                    <DifferenceValue
                      a={row.a}
                      b={row.b}
                      unit={unit}
                      betterWhen={row.betterWhen}
                      showRelative
                    />
                  </TableCell>
                </TableRow>
              );
            })}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

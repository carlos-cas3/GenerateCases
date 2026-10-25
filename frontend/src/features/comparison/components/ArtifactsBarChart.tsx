import Box from '@mui/material/Box';
import Skeleton from '@mui/material/Skeleton';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import type { ComparisonRow } from '../types';

export interface ArtifactsBarChartProps {
  ariaLabel: string;
  rows: ComparisonRow[];
  isLoading?: boolean;
  emptyMessage?: string;
}

const PLOT_HEIGHT = 160;
const BAR_WIDTH = 24;
const BAR_GAP = 2;

const SERIES = [
  { key: 'a' as const, label: 'Ejecución A', badge: 'Con clustering', color: 'primary.main' as const },
  { key: 'b' as const, label: 'Ejecución B', badge: 'Sin clustering', color: '#EB6834' },
];

const integer = new Intl.NumberFormat('es-PE', { maximumFractionDigits: 0 });

/** Siguiente número "limpio" (1, 2, 5, 10, 20, 50…) igual o mayor que `n`, para los ticks del eje. */
function niceCeil(n: number): number {
  if (n <= 0) return 1;
  const exp = Math.floor(Math.log10(n));
  const base = 10 ** exp;
  const mult = n / base;
  const niceMult = mult <= 1 ? 1 : mult <= 2 ? 2 : mult <= 5 ? 5 : 10;
  return niceMult * base;
}

function Bar({ value, color, seriesLabel, categoryLabel, max }: {
  value: number | null;
  color: string;
  seriesLabel: string;
  categoryLabel: string;
  max: number;
}) {
  const height = value === null ? 0 : Math.round((value / max) * PLOT_HEIGHT);
  const valueText = value === null ? 'Sin datos' : integer.format(value);

  return (
    <Tooltip title={`${categoryLabel} · ${seriesLabel}: ${valueText}`}>
      <Box
        sx={{
          position: 'relative',
          width: BAR_WIDTH,
          height: PLOT_HEIGHT,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'flex-end',
        }}
        tabIndex={0}
        role="img"
        aria-label={`${categoryLabel}, ${seriesLabel}: ${valueText}`}
      >
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{
            position: 'absolute',
            left: '50%',
            bottom: height + 4,
            transform: 'translateX(-50%)',
            whiteSpace: 'nowrap',
            fontWeight: 600,
          }}
        >
          {value === null ? '—' : integer.format(value)}
        </Typography>
        <Box
          sx={{
            width: '100%',
            height,
            bgcolor: color,
            borderRadius: '4px 4px 0 0',
            transition: 'filter 0.15s',
            '&:hover, &:focus-visible': { filter: 'brightness(0.92)' },
          }}
        />
      </Box>
    </Tooltip>
  );
}

/** Gráfico de barras agrupadas: una pareja A/B por categoría (HU, RF, CP…). */
export function ArtifactsBarChart({ ariaLabel, rows, isLoading = false, emptyMessage = 'No hay datos para mostrar.' }: ArtifactsBarChartProps) {
  if (isLoading) {
    return (
      <Box aria-busy="true" sx={{ display: 'flex', justifyContent: 'space-around', alignItems: 'flex-end', gap: 2, height: PLOT_HEIGHT, px: 2 }}>
        {Array.from({ length: 3 }).map((_, i) => (
          <Box key={i} sx={{ display: 'flex', alignItems: 'flex-end', gap: `${BAR_GAP}px` }}>
            <Skeleton variant="rounded" width={BAR_WIDTH} height={PLOT_HEIGHT * 0.6} />
            <Skeleton variant="rounded" width={BAR_WIDTH} height={PLOT_HEIGHT * 0.4} />
          </Box>
        ))}
      </Box>
    );
  }

  if (rows.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ py: 4, textAlign: 'center' }}>
        {emptyMessage}
      </Typography>
    );
  }

  const max = niceCeil(Math.max(1, ...rows.flatMap((r) => [r.a ?? 0, r.b ?? 0])));
  const ticks = [max, max / 2, 0];

  return (
    <Box role="img" aria-label={ariaLabel} sx={{ overflowX: 'auto' }}>
      <Box sx={{ display: 'flex', gap: 3, mb: 2, flexWrap: 'wrap' }}>
        {SERIES.map((s) => (
          <Box key={s.key} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Box sx={{ width: 12, height: 12, borderRadius: '3px', bgcolor: s.color }} />
            <Typography variant="caption" color="text.secondary">
              {s.label} · {s.badge}
            </Typography>
          </Box>
        ))}
      </Box>

      <Box sx={{ display: 'flex', minWidth: 420 }}>
        <Box sx={{ position: 'relative', width: 32, height: PLOT_HEIGHT, flexShrink: 0 }}>
          {ticks.map((tick) => (
            <Typography
              key={tick}
              variant="caption"
              color="text.secondary"
              sx={{
                position: 'absolute',
                right: 8,
                bottom: (tick / max) * PLOT_HEIGHT - 7,
                whiteSpace: 'nowrap',
              }}
            >
              {integer.format(tick)}
            </Typography>
          ))}
        </Box>

        <Box sx={{ position: 'relative', flex: 1 }}>
          {ticks.map((tick) => (
            <Box
              key={tick}
              sx={{
                position: 'absolute',
                left: 0,
                right: 0,
                bottom: (tick / max) * PLOT_HEIGHT,
                height: '1px',
                bgcolor: 'divider',
              }}
            />
          ))}

          <Box sx={{ position: 'relative', display: 'flex', justifyContent: 'space-around' }}>
            {rows.map((row) => (
              <Box key={row.id} sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1 }}>
                <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: `${BAR_GAP}px` }}>
                  {SERIES.map((s) => (
                    <Bar
                      key={s.key}
                      value={row[s.key]}
                      color={s.color}
                      seriesLabel={`${s.label} (${s.badge.toLowerCase()})`}
                      categoryLabel={row.label}
                      max={max}
                    />
                  ))}
                </Box>
                <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 500, textAlign: 'center' }}>
                  {row.label}
                </Typography>
              </Box>
            ))}
          </Box>
        </Box>
      </Box>
    </Box>
  );
}
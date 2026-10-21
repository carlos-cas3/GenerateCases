import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import TrendingDownRoundedIcon from '@mui/icons-material/TrendingDownRounded';
import TrendingFlatRoundedIcon from '@mui/icons-material/TrendingFlatRounded';
import TrendingUpRoundedIcon from '@mui/icons-material/TrendingUpRounded';
import {
  computeDifference,
  formatDelta,
  formatPercentChange,
  getDifferenceTone,
} from '../utils/metricFormat';
import type { BetterWhen, DifferenceTone, ValueUnit } from '../utils/metricFormat';

export interface DifferenceValueProps {
  a: number | null;
  b: number | null;
  unit?: ValueUnit;
  betterWhen?: BetterWhen;
  /** Muestra además la variación relativa respecto a B (no aplica a % porque ya va en puntos). */
  showRelative?: boolean;
  size?: 'medium' | 'large';
}

const TONE_COLOR: Record<DifferenceTone, string> = {
  better: 'success.main',
  worse: 'error.main',
  neutral: 'text.primary',
};

/** El color no es la única señal: lectores de pantalla reciben «mejora» o «empeora». */
const TONE_SR_TEXT: Record<DifferenceTone, string> = { better: ' (mejora)', worse: ' (empeora)', neutral: '' };

const visuallyHidden = {
  position: 'absolute',
  width: 1,
  height: 1,
  overflow: 'hidden',
  clip: 'rect(0 0 0 0)',
  whiteSpace: 'nowrap',
} as const;

/** Diferencia A − B con icono de tendencia, signo y color según mejore o empeore. */
export function DifferenceValue({
  a,
  b,
  unit = 'count',
  betterWhen,
  showRelative = false,
  size = 'medium',
}: DifferenceValueProps) {
  const diff = computeDifference(a, b);
  if (!diff) return <>—</>;

  const tone = getDifferenceTone(diff.delta, betterWhen);
  const Icon = diff.delta > 0 ? TrendingUpRoundedIcon : diff.delta < 0 ? TrendingDownRoundedIcon : TrendingFlatRoundedIcon;
  const large = size === 'large';

  return (
    <Box
      component="span"
      sx={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 0.75,
        color: TONE_COLOR[tone],
        fontWeight: 600,
        fontSize: large ? '1.5rem' : undefined,
        lineHeight: large ? 1.2 : undefined,
        fontVariantNumeric: 'tabular-nums',
      }}
    >
      <Icon fontSize={large ? 'medium' : 'small'} aria-hidden />
      <span>
        {formatDelta(diff.delta, unit)}
        <Box component="span" sx={visuallyHidden}>
          {TONE_SR_TEXT[tone]}
        </Box>
      </span>
      {showRelative && unit !== 'percent' && diff.percent !== null && (
        <Typography variant="caption" component="span" color="text.secondary" sx={{ fontWeight: 400 }}>
          ({formatPercentChange(diff.percent)})
        </Typography>
      )}
    </Box>
  );
}

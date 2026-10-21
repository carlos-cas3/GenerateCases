import type { ElementType } from 'react';
import Box from '@mui/material/Box';
import { alpha } from '@mui/material/styles';
import ContentCopyOutlinedIcon from '@mui/icons-material/ContentCopyOutlined';
import FactCheckOutlinedIcon from '@mui/icons-material/FactCheckOutlined';
import InsightsOutlinedIcon from '@mui/icons-material/InsightsOutlined';
import WorkspacePremiumOutlinedIcon from '@mui/icons-material/WorkspacePremiumOutlined';
import type { MetricIconKey } from '../types';

const ICONS: Record<MetricIconKey, ElementType> = {
  coverage: FactCheckOutlinedIcon,
  redundancy: ContentCopyOutlinedIcon,
  quality: WorkspacePremiumOutlinedIcon,
  generic: InsightsOutlinedIcon,
};

/** Icono de la métrica dentro de un recuadro tintado con el color principal. */
export function MetricIconBadge({ icon = 'generic', size = 44 }: { icon?: MetricIconKey; size?: number }) {
  const Icon = ICONS[icon];
  return (
    <Box
      aria-hidden
      sx={(theme) => ({
        display: 'grid',
        placeItems: 'center',
        width: size,
        height: size,
        flexShrink: 0,
        borderRadius: '12px',
        color: 'primary.main',
        bgcolor: alpha(theme.palette.primary.main, 0.1),
      })}
    >
      <Icon fontSize={size >= 44 ? 'medium' : 'small'} />
    </Box>
  );
}

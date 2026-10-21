import { useState } from 'react';
import type { KeyboardEvent } from 'react';
import Box from '@mui/material/Box';
import Tooltip from '@mui/material/Tooltip';
import { splitFileName, truncateText } from '../utils/fileName';

export interface TruncatedFileNameProps {
  /** Nombre completo con extensión. */
  name: string;
  /** Máximo de caracteres visibles del nombre (sin contar la extensión). */
  maxBaseChars?: number;
}

/**
 * Muestra "nombre_largo_del_doc….pdf": recorta el nombre y conserva siempre la extensión.
 * Con doble clic (o Enter con el teclado) alterna entre el nombre recortado y el completo.
 */
export function TruncatedFileName({ name, maxBaseChars = 24 }: TruncatedFileNameProps) {
  const [expanded, setExpanded] = useState(false);
  const { base, extension } = splitFileName(name);
  const isTruncatable = base.length > maxBaseChars;

  if (!isTruncatable) {
    return (
      <Box component="span" sx={{ fontWeight: 500 }}>
        {base}
        <Box component="span" sx={{ color: 'text.secondary' }}>
          {extension}
        </Box>
      </Box>
    );
  }

  const toggle = () => setExpanded((value) => !value);
  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      toggle();
    }
  };

  return (
    <Tooltip title={expanded ? 'Doble clic para contraer' : 'Doble clic para ver el nombre completo'} enterDelay={600}>
      <Box
        component="span"
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        aria-label={name}
        onDoubleClick={toggle}
        onKeyDown={handleKeyDown}
        sx={{
          display: 'flex',
          alignItems: 'baseline',
          minWidth: 0,
          fontWeight: 500,
          cursor: 'pointer',
          userSelect: expanded ? 'text' : 'none',
          borderRadius: 0.5,
          '&:focus-visible': { outline: '2px solid', outlineColor: 'primary.main', outlineOffset: 2 },
        }}
      >
        {expanded ? (
          <Box component="span" sx={{ wordBreak: 'break-all' }}>
            {base}
            <Box component="span" sx={{ color: 'text.secondary' }}>
              {extension}
            </Box>
          </Box>
        ) : (
          <>
            <Box component="span" sx={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {truncateText(base, maxBaseChars)}
            </Box>
            <Box component="span" sx={{ flexShrink: 0, color: 'text.secondary' }}>
              {extension}
            </Box>
          </>
        )}
      </Box>
    </Tooltip>
  );
}

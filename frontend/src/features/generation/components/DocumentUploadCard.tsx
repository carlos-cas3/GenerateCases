import { useId, useRef, useState } from 'react';
import type { ChangeEvent, DragEvent, KeyboardEvent } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import CircularProgress from '@mui/material/CircularProgress';
import IconButton from '@mui/material/IconButton';
import Switch from '@mui/material/Switch';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import type { SxProps, Theme } from '@mui/material/styles';
import CloudUploadOutlinedIcon from '@mui/icons-material/CloudUploadOutlined';
import DeleteOutlineRoundedIcon from '@mui/icons-material/DeleteOutlineRounded';
import DescriptionOutlinedIcon from '@mui/icons-material/DescriptionOutlined';
import SwapHorizRoundedIcon from '@mui/icons-material/SwapHorizRounded';
import { BaseCard } from '../../../components/cards';

const ACCEPTED_EXTENSIONS = ['pdf', 'docx', 'txt'] as const;
const DEFAULT_MAX_SIZE_MB = 20;

export interface DocumentUploadCardProps {
  /** Archivo seleccionado (estado controlado por el padre). */
  file: File | null;
  onFileChange: (file: File | null) => void;
  semanticGrouping: boolean;
  onSemanticGroupingChange: (enabled: boolean) => void;
  /** Se invoca al pulsar «Generar casos de prueba». La lógica real vive en el padre. */
  onSubmit: () => void;
  /** Una ejecución se está iniciando: bloquea el formulario y muestra un spinner. */
  isSubmitting?: boolean;
  /** Deshabilita todo el formulario (p. ej. hay otra ejecución activa). */
  disabled?: boolean;
  /** Error externo (p. ej. del backend) mostrado bajo la zona de carga. */
  errorMessage?: string;
  maxSizeMB?: number;
  sx?: SxProps<Theme>;
}

function getExtension(name: string) {
  return name.split('.').pop()?.toLowerCase() ?? '';
}

function validateFile(file: File, maxSizeMB: number): string | null {
  if (!(ACCEPTED_EXTENSIONS as readonly string[]).includes(getExtension(file.name))) {
    return 'Formato no permitido. Usa un archivo PDF, DOCX o TXT.';
  }
  if (file.size === 0) return 'El archivo está vacío.';
  if (file.size > maxSizeMB * 1024 * 1024) return `El archivo supera el límite de ${maxSizeMB} MB.`;
  return null;
}

function formatSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function DocumentUploadCard({
  file,
  onFileChange,
  semanticGrouping,
  onSemanticGroupingChange,
  onSubmit,
  isSubmitting = false,
  disabled = false,
  errorMessage,
  maxSizeMB = DEFAULT_MAX_SIZE_MB,
  sx,
}: DocumentUploadCardProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const hintId = useId();
  const switchHelpId = useId();
  const [isDragging, setIsDragging] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  const locked = disabled || isSubmitting;
  const canSubmit = !!file && !validationError && !locked;
  const shownError = validationError ?? errorMessage;

  const openPicker = () => !locked && inputRef.current?.click();

  const handleFile = (candidate: File | undefined) => {
    if (!candidate) return;
    const error = validateFile(candidate, maxSizeMB);
    setValidationError(error);
    if (!error) onFileChange(candidate);
  };

  const handleInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    handleFile(e.target.files?.[0]);
    e.target.value = ''; // permite volver a elegir el mismo archivo
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (!locked) handleFile(e.dataTransfer.files?.[0]);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      openPicker();
    }
  };

  const handleRemove = () => {
    setValidationError(null);
    onFileChange(null);
  };

  return (
    <BaseCard
      title="Nueva generación"
      description="Sube un documento con historias de usuario y genera casos de prueba funcionales con un modelo de lenguaje."
      sx={sx}
    >
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5, flex: 1 }}>
        <input
          ref={inputRef}
          type="file"
          hidden
          accept=".pdf,.docx,.txt"
          onChange={handleInputChange}
          disabled={locked}
          aria-label="Seleccionar documento"
        />

        {file ? (
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 1.5,
              p: 1.5,
              border: '1px solid',
              borderColor: 'divider',
              borderRadius: '12px',
              bgcolor: 'background.default',
            }}
          >
            <DescriptionOutlinedIcon color="primary" aria-hidden />
            <Box sx={{ minWidth: 0, flex: 1 }}>
              <Typography variant="subtitle2" noWrap title={file.name}>
                {file.name}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {getExtension(file.name).toUpperCase()} · {formatSize(file.size)}
              </Typography>
            </Box>
            <Tooltip title="Reemplazar archivo">
              <span>
                <IconButton aria-label="Reemplazar archivo" onClick={openPicker} disabled={locked} size="small">
                  <SwapHorizRoundedIcon />
                </IconButton>
              </span>
            </Tooltip>
            <Tooltip title="Eliminar archivo">
              <span>
                <IconButton aria-label="Eliminar archivo" onClick={handleRemove} disabled={locked} size="small">
                  <DeleteOutlineRoundedIcon />
                </IconButton>
              </span>
            </Tooltip>
          </Box>
        ) : (
          <Box
            role="button"
            tabIndex={locked ? -1 : 0}
            aria-disabled={locked}
            aria-describedby={hintId}
            aria-label="Seleccionar o arrastrar un documento"
            onClick={openPicker}
            onKeyDown={handleKeyDown}
            onDragOver={(e) => {
              e.preventDefault();
              if (!locked) setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            sx={(theme) => ({
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 0.75,
              px: 2,
              py: 4,
              textAlign: 'center',
              cursor: locked ? 'not-allowed' : 'pointer',
              opacity: locked ? 0.6 : 1,
              border: '1.5px dashed',
              borderColor: isDragging ? 'primary.main' : 'divider',
              borderRadius: '12px',
              bgcolor: isDragging ? `color-mix(in srgb, ${theme.palette.primary.main} 6%, white)` : 'background.default',
              transition: 'border-color .15s, background-color .15s',
              '&:hover': locked ? undefined : { borderColor: 'primary.main' },
              '&:focus-visible': { outline: `2px solid ${theme.palette.primary.main}`, outlineOffset: 2 },
            })}
          >
            <CloudUploadOutlinedIcon sx={{ fontSize: 36, color: 'primary.main' }} aria-hidden />
            <Typography variant="subtitle2">
              Arrastra tu documento aquí o{' '}
              <Box component="span" sx={{ color: 'primary.main', textDecoration: 'underline' }}>
                selecciónalo
              </Box>
            </Typography>
            <Typography id={hintId} variant="caption" color="text.secondary">
              PDF, DOCX o TXT · máximo {maxSizeMB} MB
            </Typography>
          </Box>
        )}

        {shownError && (
          <Alert severity="error" variant="outlined" role="alert">
            {shownError}
          </Alert>
        )}

        <Box
          sx={{
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: 2,
            p: 1.5,
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: '12px',
          }}
        >
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="subtitle2" id={`${switchHelpId}-label`}>
              Agrupación semántica
            </Typography>
            <Typography id={switchHelpId} variant="body2" color="text.secondary">
              Agrupa requisitos similares antes de generar los casos, para dar más contexto al modelo y reducir
              redundancias.
            </Typography>
          </Box>
          <Switch
            checked={semanticGrouping}
            onChange={(e) => onSemanticGroupingChange(e.target.checked)}
            disabled={locked}
            sx={{ flexShrink: 0 }}
            slotProps={{
              input: { 'aria-labelledby': `${switchHelpId}-label`, 'aria-describedby': switchHelpId },
            }}
          />
        </Box>

        <Box sx={{ mt: 'auto' }}>
          <Button
            fullWidth
            variant="contained"
            size="large"
            disabled={!canSubmit}
            onClick={onSubmit}
            startIcon={isSubmitting ? <CircularProgress size={18} color="inherit" /> : undefined}
          >
            {isSubmitting ? 'Iniciando ejecución…' : 'Generar casos de prueba'}
          </Button>
        </Box>
      </Box>
    </BaseCard>
  );
}

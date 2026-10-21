const formatter = new Intl.DateTimeFormat('es-PE', {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

/** Fecha y hora legibles en español (ej.: "16 oct 2026, 04:42 p. m."). */
export const formatDateTime = (value: string | Date) => formatter.format(new Date(value));

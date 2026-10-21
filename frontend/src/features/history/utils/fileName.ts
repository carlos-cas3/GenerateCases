/** Separa "informe.final.pdf" en { base: "informe.final", extension: ".pdf" }. */
export function splitFileName(name: string): { base: string; extension: string } {
  const dot = name.lastIndexOf('.');
  if (dot <= 0 || dot === name.length - 1) return { base: name, extension: '' };
  return { base: name.slice(0, dot), extension: name.slice(dot) };
}

export function truncateText(text: string, maxChars: number): string {
  return text.length > maxChars ? `${text.slice(0, maxChars).trimEnd()}…` : text;
}

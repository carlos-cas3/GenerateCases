/** Dispara la descarga de un archivo en el navegador a partir de un Blob (la respuesta del backend). */
export function saveBlob(blob: Blob, fileName: string) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = fileName;
    link.style.display = "none";
    document.body.appendChild(link);
    link.click();
    link.remove();
    // Se libera después del clic para que el navegador alcance a iniciar la descarga.
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

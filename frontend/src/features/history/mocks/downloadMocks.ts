/**
 * DEMO: simula el archivo que devolverá el backend al descargar.
 * El backend real responderá con el documento (y un .zip cuando sean varios).
 */
import type { DownloadedFile, ExecutionRecord } from "../types";
import { HISTORY_STATUS_LABEL } from "../constants";
import { splitFileName } from "../utils/fileName";

const describe = (r: ExecutionRecord) =>
    [
        `Documento: ${r.documentName}`,
        `Ejecución: ${r.id}`,
        `Estado: ${HISTORY_STATUS_LABEL[r.status]}`,
        `Clustering: ${r.clustering ? "Sí" : "No"}`,
        `HU: ${r.huCount ?? "—"} · RF: ${r.rfCount ?? "—"} · CP: ${r.cpCount ?? "—"}`,
    ].join("\n");

export function buildMockDownload(records: ExecutionRecord[]): DownloadedFile {
    const body = `# Archivo simulado (el backend real devolverá el documento)\n\n${records.map(describe).join("\n\n---\n\n")}\n`;
    const fileName =
        records.length === 1
            ? `${splitFileName(records[0].documentName).base}_resultado.txt`
            : `ejecuciones_${records.length}_documentos.txt`;

    return {
        blob: new Blob([body], { type: "text/plain;charset=utf-8" }),
        fileName,
    };
}

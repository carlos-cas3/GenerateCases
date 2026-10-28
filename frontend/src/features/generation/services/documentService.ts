/**
 * Acceso a documentos. Por ahora solo se consume `POST /documents`;
 * listar y borrar documentos no tienen UI todavía (Fase 3).
 */
import { uploadFormData } from "@/shared/api";

export interface DocumentDto {
    id: string;
    filename: string;
    file_type: "txt" | "pdf" | "docx";
    size_bytes: number;
    checksum: string;
    uploaded_at: string;
}

export const documentService = {
    /** `POST /documents` (multipart): devuelve el id del documento registrado. */
    async uploadDocument(file: File, signal?: AbortSignal): Promise<string> {
        const formData = new FormData();
        // El contrato exige que el campo se llame `file`.
        formData.append("file", file);
        const dto = await uploadFormData<DocumentDto>("/documents", formData, { signal });
        return dto.id;
    },
};

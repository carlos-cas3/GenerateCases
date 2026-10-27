/// <reference types="vite/client" />

interface ImportMetaEnv {
    /** URL base de la API. Vacío = rutas relativas (proxy de Vite en desarrollo). */
    readonly VITE_API_URL?: string;
    /** Fase 1.5: documento del seed usado al iniciar una generación (aún no hay subida). */
    readonly VITE_DEV_DOCUMENT_ID?: string;
}

interface ImportMeta {
    readonly env: ImportMetaEnv;
}

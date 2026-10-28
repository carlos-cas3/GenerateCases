/// <reference types="vite/client" />

interface ImportMetaEnv {
    /** URL base de la API. Vacío = rutas relativas (proxy de Vite en desarrollo). */
    readonly VITE_API_URL?: string;
}

interface ImportMeta {
    readonly env: ImportMetaEnv;
}

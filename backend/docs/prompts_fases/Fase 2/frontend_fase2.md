# Fase 2 — Frontend: subida real de documentos

Consumir `POST /documents` desde `GenerationPage` para que la interfaz suba el archivo
seleccionado y cree la generación sobre ese documento, eliminando `VITE_DEV_DOCUMENT_ID`.
Resumen de alcance y decisiones: `fase2.md`.

Todas las rutas son relativas a `frontend/`.

**Prerrequisito:** `POST /api/v1/documents` implementado en el backend (`backend_fase2.md`,
pasos 1-8). El frontend no necesita nada más del backend.

---

## 0. Decisiones que aplican al frontend

| # | Decisión |
|---|---|
| D1 | `VITE_DEV_DOCUMENT_ID` se elimina por completo (servicio, página, tipos, `.env*`). |
| D2 | Solo se consume `POST /documents`. `GET`/`DELETE` de documentos **no** tienen UI en esta fase. |
| D6 | Si `POST /generations` falla tras la subida, el documento **no** se revierte. |

---

## 1. Cliente multipart

**Archivos:** `src/shared/api/http.ts` (+ export en el barrel).

Nueva función junto a `request<T>`:

```ts
export async function uploadFormData<T>(
    path: string,
    formData: FormData,
    { signal }: { signal?: AbortSignal } = {},
): Promise<T>
```

- Mismo `fetch` que `request`, **sin cabecera `Content-Type`**: el navegador la pone con su
  `boundary`. Solo `Accept: application/json`.
- Reutiliza `readJson`, `toApiError` y `ApiError`, y la tolerancia a cuerpos no JSON (por ejemplo,
  HTML devuelto por el proxy).
- `204 → undefined`; `AbortError` se relanza sin envolver; `NETWORK_ERROR` igual que hoy.
- El error de red **no** es «transitorio» aquí (no hay polling de subida): el llamador lo muestra.

---

## 2. `documentService`

**Archivo nuevo:** `src/features/generation/services/documentService.ts`.

```ts
export interface DocumentDto {
    id: string; filename: string; file_type: "txt" | "pdf" | "docx";
    size_bytes: number; checksum: string; uploaded_at: string;
}

export const documentService = {
    /** `POST /documents` (multipart): devuelve el id del documento registrado. */
    async uploadDocument(file: File, signal?: AbortSignal): Promise<string> {
        const formData = new FormData();
        formData.append("file", file);   // el campo DEBE llamarse "file" (contrato)
        const dto = await uploadFormData<DocumentDto>("/documents", formData, { signal });
        return dto.id;
    },
};
```

Sin mapeador aparte: solo se usa el `id` (D2). El DTO completo crecerá cuando se liste o borre
documentos (Fase 3).

---

## 3. `generationService.startGeneration`

**Archivo:** `src/features/generation/services/generationService.ts`.

- **Eliminar** `DEV_DOCUMENT_ID` (la constante que lee `VITE_DEV_DOCUMENT_ID`) y su uso. También
  desaparece el `throw` de «VITE_DEV_DOCUMENT_ID no está configurado».
- `StartGenerationInput.file` deja de ser «validado pero no enviado»: ahora se sube.
- Nuevo cuerpo:

```ts
async startGeneration(input: StartGenerationInput): Promise<Generation> {
    const documentId = await documentService.uploadDocument(input.file);
    const body: CreateGenerationRequestDto = {
        document_id: documentId,
        configuration: { semantic_clustering_enabled: input.semanticGrouping },
    };
    const dto = await request<GenerationDto>("/generations", { method: "POST", body });
    return mapGeneration(dto);
},
```

- Documentar D6 en el JSDoc: si `POST /generations` falla tras la subida, el documento queda
  registrado y es reutilizable (no hay rollback).
- `getExecutionPipeline` **sigue con mocks** (no se toca).

---

## 4. `useStartGeneration`

**Archivo:** `src/features/generation/hooks/useStartGeneration.ts` — ampliar `startErrorMessage`:

| `code` | Mensaje |
|---|---|
| `PAYLOAD_TOO_LARGE` | «El archivo supera el límite de 20 MB.» |
| `UNSUPPORTED_MEDIA_TYPE` | «Tipo de archivo no soportado. Usa un archivo TXT, PDF o DOCX.» |
| `DOCUMENT_NOT_FOUND` | Se conserva (residual; hoy inalcanzable en este flujo) |
| `VALIDATION_ERROR` | «La solicitud no es válida.» (igual que hoy) |
| `NETWORK_ERROR` / `status >= 500` | Sin cambios |

La doble llamada (subir + crear) queda cubierta por el estado `isCreating` existente. El guard
anti doble clic (`inFlight`) **no** se toca.

---

## 5. `GenerationPage` y `DocumentUploadCard`

**`pages/GenerationPage.tsx`:**
- Eliminar el import de `DEV_DOCUMENT_ID` y la constante `DEV_DOCUMENT_NOTICE`. La tarjeta ya no
  recibe `notice` (la propiedad es opcional en el componente).
- `submitDisabled`: quitar `!DEV_DOCUMENT_ID`, de modo que quede
  `isTrackingActive || (!!active.generationId && progress.isLoading)`.
- `handleSubmit`: retirar el comentario `TODO Fase 2`; el archivo ya se envía.

**`components/DocumentUploadCard.tsx`:**
- Sin cambios estructurales. El botón conserva «Iniciando ejecución…»; un solo estado
  `isSubmitting` cubre subir + crear.
- El aviso de «documento de ejemplo» desaparece junto con `DEV_DOCUMENT_NOTICE`.

### 5.1. Validación del cliente (se conserva)

`DocumentUploadCard` ya valida extensión (`pdf/docx/txt`), tamaño (≤ 20 MB) y archivo vacío
**antes** de enviar. Se mantiene como primera línea de defensa (mejor experiencia de usuario); la
validación del backend es la autoritativa. Ambas deben coincidir en formatos y límite.

---

## 6. Eliminación de `VITE_DEV_DOCUMENT_ID` (incluye `vite-env.d.ts`)

| Archivo | Acción |
|---|---|
| `frontend/.env` | Borrar la línea `VITE_DEV_DOCUMENT_ID=…` (está en `.gitignore`: editarlo a mano) |
| `frontend/.env.example` | Borrar el bloque comentado de la variable (aprox. líneas 6-8) |
| `src/vite-env.d.ts` | Quitar la línea `readonly VITE_DEV_DOCUMENT_ID?: string` (ver §6.1) |
| `src/features/generation/services/generationService.ts` | Quitar `DEV_DOCUMENT_ID` (§3) |
| `src/features/generation/pages/GenerationPage.tsx` | Quitar aviso y guard (§5) |
| `frontend/README.md` | Buscar menciones a `VITE_*` (`grep`) y quitar la de `VITE_DEV_DOCUMENT_ID` si existe |

### 6.1. Qué es `vite-env.d.ts` y qué hay que modificar

**Qué es.** `src/vite-env.d.ts` es un archivo de *declaraciones de tipos* de TypeScript. No
contiene lógica ni se ejecuta. Su función es decirle a TypeScript qué variables existen en
`import.meta.env`. Por ejemplo, algo como:

```ts
/// <reference types="vite/client" />

interface ImportMetaEnv {
    readonly VITE_API_BASE_URL?: string;
    readonly VITE_DEV_DOCUMENT_ID?: string;   // ← esta es la que se elimina
}

interface ImportMeta {
    readonly env: ImportMetaEnv;
}
```

Gracias a esa interfaz, el editor autocompleta `import.meta.env.VITE_…` y `tsc` avisa si se usa
una variable que no está declarada.

**Qué hay que modificar.** Una sola cosa: **borrar la línea** de `VITE_DEV_DOCUMENT_ID` dentro de
`ImportMetaEnv`. Nada más.

- No hay que añadir ninguna variable nueva: `POST /documents` usa la misma `VITE_API_BASE_URL` (o
  el proxy de Vite) que el resto de llamadas.
- No hay que tocar `/// <reference types="vite/client" />` ni el resto del archivo.
- Si el archivo declara otras variables `VITE_*`, se dejan como están.

**Por qué hay que hacerlo.** Es coherencia, no funcionalidad: si la variable ya no se usa pero
sigue declarada, el proyecto compila igual, pero el tipo queda mintiendo (sugiere una variable que
no existe) y el `grep` de cierre (`VITE_DEV_DOCUMENT_ID` → 0 resultados) fallaría.

**Orden recomendado:** quitar primero los usos (`generationService.ts`, `GenerationPage.tsx`) y
después la declaración. Si se hace al revés, `tsc` marcará error en los archivos que todavía leen
la variable, lo que sirve de guía para encontrar los usos que falten.

---

## 7. Archivos a tocar

| Archivo | Cambio |
|---|---|
| `src/shared/api/http.ts` (+ barrel) | `uploadFormData` |
| `src/features/generation/services/documentService.ts` | **Nuevo** |
| `src/features/generation/services/generationService.ts` | Subir → crear; fuera `DEV_DOCUMENT_ID` |
| `src/features/generation/hooks/useStartGeneration.ts` | Mensajes 413/415 |
| `src/features/generation/pages/GenerationPage.tsx` | Fuera aviso y guard del ID |
| `src/features/generation/components/DocumentUploadCard.tsx` | Sin cambios estructurales |
| `.env`, `.env.example`, `src/vite-env.d.ts` | Fuera `VITE_DEV_DOCUMENT_ID` |

**No se tocan:** `features/history/**`, `features/metrics/**`, `features/comparison/**`,
`hooks/useExecutionProgress.ts`, `__fixtures__/`.

---

## 8. Checklist de verificación

### 8.1. Automático

```bash
# desde frontend/
npx tsc --noEmit -p tsconfig.app.json     # 0 errores
npx eslint .                              # 0 problemas
npm run build                             # OK
grep -rn "VITE_DEV_DOCUMENT_ID" src/ .env.example   # 0 resultados
```

### 8.2. Manual

Con backend en marcha (`.env` con Supabase y bucket creado) y frontend levantado:

1. **Flujo completo sin `VITE_DEV_DOCUMENT_ID`:** seleccionar un archivo nuevo → «Generar casos de
   prueba» → subida (`201`) → creación de la generación → URL `/?g=<uuid>` → polling hasta
   `completed`. La generación aparece en recientes con el nombre del archivo subido.
2. **Validación del cliente:** `.png` o archivo > 20 MB → error en la tarjeta sin llegar a la red.
3. **Errores del servidor:** con el backend caído, mensaje «No se pudo iniciar la generación»
   (red). Opcional: forzar 413/415 con un `MAX_UPLOAD_SIZE_BYTES` temporal.
4. **Doble clic en «Generar»:** una sola subida (el guard `inFlight` sigue intacto).
5. **Subida correcta, creación fallida (D6):** apagar el backend entre las dos llamadas → el
   documento queda registrado (`GET /documents`) y la UI permite reintentar.
6. **Regresión:** `/history`, métricas y comparación siguen con mocks; health y formato de error
   estándar sin cambios.

**Hecho cuando:** el checklist automático pasa limpio y el flujo manual 1 funciona de extremo a
extremo sin ninguna variable `VITE_DEV_DOCUMENT_ID` en el proyecto.

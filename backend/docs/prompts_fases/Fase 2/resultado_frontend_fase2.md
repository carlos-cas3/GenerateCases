# Fase 2 — Resultado del frontend

## Resultado

La interfaz ya sube el archivo real: «Generar» → `POST /documents` → `POST /generations` con el
`id` devuelto → polling (sin cambios). `VITE_DEV_DOCUMENT_ID` está eliminada del frontend.

Verificación automática (desde `frontend/`):

| Comprobación | Resultado |
|---|---|
| `npx tsc --noEmit -p tsconfig.app.json` | 0 errores |
| `npx eslint .` | 0 problemas |
| `npm run build` | OK (solo el aviso habitual de chunk > 500 kB, previo a esta fase) |
| `grep -rn "VITE_DEV_DOCUMENT_ID" frontend/` | 0 resultados |

## Qué se ha añadido o cambiado

| Archivo | Cambio |
|---|---|
| `src/shared/api/http.ts` | Nueva `uploadFormData<T>` (sin `Content-Type`, solo `Accept`). |
| `src/shared/api/index.ts` | Exporta `uploadFormData`. |
| `src/features/generation/services/documentService.ts` | **Nuevo.** `DocumentDto` y `uploadDocument(file, signal?)` → `id` (campo `file`). |
| `src/features/generation/services/generationService.ts` | `startGeneration` sube y luego crea; fuera `DEV_DOCUMENT_ID`; JSDoc documenta D6 (sin rollback). `getExecutionPipeline` sigue con mocks. |
| `src/features/generation/hooks/useStartGeneration.ts` | Mensajes para `PAYLOAD_TOO_LARGE` y `UNSUPPORTED_MEDIA_TYPE`. Guard `inFlight` intacto. |
| `src/features/generation/pages/GenerationPage.tsx` | Fuera el import, `DEV_DOCUMENT_NOTICE`, el `TODO Fase 2`, la prop `notice` y `!DEV_DOCUMENT_ID` de `submitDisabled`. |
| `src/vite-env.d.ts` | Fuera la declaración de `VITE_DEV_DOCUMENT_ID`. |
| `.env.example` y `.env` (local, en `.gitignore`) | Fuera el bloque de `VITE_DEV_DOCUMENT_ID`. |

`DocumentUploadCard.tsx` no se ha tocado: su validación (pdf/docx/txt, ≤ 20 MiB, no vacío) ya
coincide con la del backend.

## Desviaciones respecto al plan

1. **`http.ts` refactorizado internamente.** En lugar de duplicar `fetch` + manejo de errores, se
   extrajo un helper privado `send<T>(path, init)` que usan `request` y `uploadFormData`. La firma y
   el comportamiento de `request` no cambian (mismo `NETWORK_ERROR`, `204 → undefined`,
   `AbortError` sin envolver, tolerancia a cuerpos no JSON).
2. **Mensaje de `DOCUMENT_NOT_FOUND` reescrito.** El plan dice «se conserva», y la rama se conserva,
   pero el texto anterior remitía a aplicar `supabase/seed.sql`, que ya no tiene sentido sin el
   documento del seed. Ahora: «El documento subido ya no existe. Vuelve a seleccionarlo e inténtalo
   de nuevo.»
3. **Nombre de variable en el plan.** `frontend_fase2.md` §6.1 usa `VITE_API_BASE_URL` como ejemplo;
   la variable real es `VITE_API_URL`. No ha hecho falta cambiar nada (solo es un ejemplo del doc).
4. `frontend/README.md` no mencionaba `VITE_DEV_DOCUMENT_ID`: no hubo que modificarlo.

## Pendiente

- **Checklist manual (§8.2) sin ejecutar.** Necesita el backend con Supabase y el bucket
  `DOCUMENTS_BUCKET` creado; no se lanzó desde aquí para no escribir en la base de datos/Storage
  reales. Puntos a comprobar: flujo completo (1), validación del cliente (2), backend caído (3),
  doble clic (4), D6 (5) y regresión (6).
- `uploadDocument` acepta `signal`, pero `startGeneration` no lo pasa (no hay cancelación en la UI).
  Es lo que pide el plan; queda listo para cuando se quiera cancelar una subida.

## Observaciones

- El botón sigue mostrando «Iniciando ejecución…» durante subida + creación. Con archivos grandes
  o conexiones lentas puede parecer bloqueado; si se quiere, en Fase 3 se podría distinguir
  «Subiendo documento…» de «Creando generación…» (requeriría un estado extra en el hook).
- Al reintentar tras un fallo de `POST /generations` (D6) se vuelve a subir el archivo, creando un
  segundo documento con el mismo `checksum`. Es coherente con el plan, pero el selector de
  documentos de Fase 3 (o reutilizar el `id` subido en el reintento) evitaría duplicados.
- El límite de 20 MB está escrito en dos sitios del frontend (`DocumentUploadCard` y el mensaje
  413 del hook) y en el backend (`MAX_UPLOAD_SIZE_BYTES`). Si cambia, hay que actualizar los tres.

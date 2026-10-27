# Fase 2 — Subida de documentos y subida real en la interfaz

Implementar las cuatro rutas de `documents` definidas en `docs/openapi.yaml` y conectar la subida
real de archivos en `GenerationPage`, eliminando la dependencia del documento fijo del seed
(`VITE_DEV_DOCUMENT_ID`).

Este archivo es el **resumen de alcance**. El detalle de implementación está separado por
responsabilidad:

| Archivo | Contenido | Se ejecuta |
|---|---|---|
| `fase2.md` (este) | Alcance, decisiones, orden y criterios de cierre | — |
| `backend_fase2.md` | Endpoints, storage, repositorios, servicio, pruebas y documentación | **Primero** |
| `frontend_fase2.md` | Cliente multipart, servicios, hook, página y limpieza de variables de entorno | **Después** (consume los endpoints del backend) |

Las rutas del backend son relativas a `backend/` y las del frontend a `frontend/`.

Fuentes: `indicaciones.md` (§1.2 y §2.1), `Fase 1/database.md` (decisión 8), `docs/openapi.yaml`
(contrato) y `entrega_fase1_5.md`.

---

## 1. Objetivo

Que la interfaz funcione con archivos reales: el usuario selecciona un TXT, PDF o DOCX, pulsa
«Generar» y el sistema sube el archivo, lo registra y crea la generación sobre ese documento, sin
depender de un documento precargado en la base de datos.

Flujo de la UI al cerrar la fase:

```
seleccionar archivo → «Generar» → POST /documents (201, id)
                               → POST /generations (document_id)
                               → polling de la generación (sin cambios)
```

---

## 2. Endpoints

Contrato: `docs/openapi.yaml`.

| Método | Ruta | `operationId` | Respuestas | Backend | Frontend |
|---|---|---|---|---|---|
| `POST` | `/api/v1/documents` | `createDocument` | 201 / 400 / 413 / 415 / 500 | Implementar | **Consumir** |
| `GET` | `/api/v1/documents` | `listDocuments` | 200 / 400 / 500 | Implementar | No se consume |
| `GET` | `/api/v1/documents/{document_id}` | `getDocument` | 200 / 404 / 500 | Implementar | No se consume |
| `DELETE` | `/api/v1/documents/{document_id}` | `deleteDocument` | 204 / 404 / 409 / 500 | Implementar | No se consume |

Códigos de error del contrato: `VALIDATION_ERROR` (400), `DOCUMENT_NOT_FOUND` (404),
`DOCUMENT_IN_USE` (409), `PAYLOAD_TOO_LARGE` (413), `UNSUPPORTED_MEDIA_TYPE` (415),
`INTERNAL_ERROR` (500).

---

## 3. Decisiones adoptadas

| # | Decisión | Motivo |
|---|---|---|
| D1 | `VITE_DEV_DOCUMENT_ID` se **elimina por completo** (servicio, página, tipos, `.env*`). El flujo siempre sube el archivo. | Dos caminos de código cuestan más de mantener que de usar. |
| D2 | El frontend **solo consume `POST /documents`**. `GET`/`DELETE` se implementan y prueban en backend, sin UI. | Alcance mínimo para desbloquear la subida. |
| D3 | **`DELETE /documents/{id}` solo procede si el documento no tiene ninguna generación asociada** (activa o finalizada). Si tiene alguna → `409 DOCUMENT_IN_USE` y no se borra nada. | Coherente con la FK `on delete restrict` y con la lectura de `document_name` por JOIN; cero migraciones. |
| D4 | El contrato es `openapi.yaml` tal cual; solo se ajusta la **prosa** del `deleteDocument` (hoy dice «solo activas»). | La regla real es más estricta que la descripción actual. |
| D5 | **Abstracción de Storage** (`DocumentStorage`: implementación Supabase + fake en memoria). | Los tests no deben tocar Supabase. |
| D6 | Si `POST /documents` tiene éxito y `POST /generations` falla, **no se revierte** el documento. | Carga y generación son operaciones independientes; el documento es reutilizable. |
| D7 | La validación de tipo se hace por **extensión** (`txt`/`pdf`/`docx`), no por `Content-Type`. | El navegador puede enviar cabeceras genéricas. |
| D8 | `checksum` = **SHA-256** hexadecimal del contenido. | El contrato no fija algoritmo; huella determinista. |

### Regla de borrado (D3) en una línea

> Lo que ya se usó en una generación no se borra. Para borrar un documento primero hay que
> eliminar sus generaciones (`DELETE /generations/{id}`, ya implementado).

**Por qué no basta con quitar la FK:** `document_name` no está guardado en `generations`; se
resuelve con un JOIN (`documents(filename)`) en cada lectura. Si el documento desapareciera,
`GenerationRecord.document_name: str` fallaría y toda lectura de esas generaciones daría `500`.

**Consecuencia asumida:** un documento usado al menos una vez no puede eliminarse mientras exista
alguna de sus generaciones. Un soft delete (`documents.deleted_at`) que permitiría borrarlo
conservando la fila queda para una fase futura.

---

## 4. Dentro del alcance

**Backend**
- Cuatro rutas de `documents` con validación de tipo (extensión), tamaño (20 MiB), archivo vacío y
  checksum SHA-256.
- Almacenamiento en bucket privado de Supabase Storage (`DOCUMENTS_BUCKET`).
- Regla de borrado D3 con `409` que incluye `details.generation_ids` (tope 50).
- Pruebas (de 50 a ~61) y actualización de documentación.

**Frontend**
- Función `uploadFormData` en el cliente HTTP.
- `documentService.uploadDocument` y `generationService.startGeneration` en dos pasos
  (subir → crear).
- Mensajes de error 413/415 en `useStartGeneration`.
- Limpieza total de `VITE_DEV_DOCUMENT_ID`.

## 5. Fuera del alcance (→ Fase 3)

| Bloque | Qué incluye |
|---|---|
| Selector de documentos | Consumir `GET /documents` en la UI para reutilizar documentos ya subidos |
| Borrado con UI | Consumir `DELETE /documents/{id}` con confirmación |
| Soft delete | `deleted_at`, filtros y purga de Storage |
| Retención automática | Limpieza de generaciones/documentos antiguos |
| Historial conectado | `historyService` sobre las rutas existentes de `generations` |
| Resultados | Rutas `user-stories`, `clusters`, `metrics`, etc. |
| SSE | `GET /generations/{id}/events` (hoy `501`) |
| Autenticación | No existe en ninguna parte del proyecto |

---

## 6. Qué se toca y qué no

| Zona | Se toca | No se toca |
|---|---|---|
| Backend | `api/routes/documents.py` (nuevo), `api/dependencies.py`, `main.py`, `services/documents.py` (nuevo), `schemas/documents.py` (nuevo), `schemas/records.py`, `repositories/documents.py`, `repositories/generations.py`, `repositories/in_memory.py`, `clients/storage.py` (nuevo), `core/errors.py`, `api/errors.py`, `config.py`, `.env.example`, `supabase/schema.sql`, `tests/`, `README.md`, `docs/openapi.yaml` (solo prosa del 409) | `ai_service/pipeline/**`, `api/routes/generations.py`, `services/generations.py`, `supabase/seed.sql` |
| Frontend | `src/shared/api/`, `features/generation/services/`, `hooks/useStartGeneration.ts`, `pages/GenerationPage.tsx`, `components/DocumentUploadCard.tsx`, `.env`, `.env.example`, `src/vite-env.d.ts` | `features/history/**`, `features/metrics/**`, `features/comparison/**`, `hooks/useExecutionProgress.ts`, `__fixtures__/` |
| Documentación | `README.md` (§4, §9, §10 y enlace roto de `database.md`), `docs/openapi.yaml`, `Fase 1/database.md` (decisión 8) | `indicaciones.md`, `fase1_5_pipeline.md` (históricos) |

---

## 7. Orden de ejecución

| Paso | Zona | Contenido | Archivo de detalle |
|---|---|---|---|
| 0 | Ambas | Verificar bucket, firma de storage y estado de la rama | `backend_fase2.md` §10 |
| 1 | Backend | Errores + configuración | `backend_fase2.md` §1-2 |
| 2 | Backend | Esquemas + `DocumentRecord.storage_path` | `backend_fase2.md` §3 |
| 3 | Backend | Storage (protocolo, Supabase, fake) | `backend_fase2.md` §4 |
| 4 | Backend | Repositorios + `ids_by_document` | `backend_fase2.md` §5 |
| 5 | Backend | Servicio de documentos | `backend_fase2.md` §6 |
| 6 | Backend | Rutas, dependencia, `main.py` y bucket | `backend_fase2.md` §7-8 |
| 7 | Backend | Pruebas → `pytest` en verde | `backend_fase2.md` §9 |
| 8 | Backend | Documentación | `backend_fase2.md` §11 |
| 9 | Frontend | `uploadFormData` | `frontend_fase2.md` §1 |
| 10 | Frontend | `documentService` + `generationService` | `frontend_fase2.md` §2-3 |
| 11 | Frontend | Hook, página, tarjeta y limpieza de env | `frontend_fase2.md` §4-6 |
| 12 | Ambas | Checklist de verificación manual de extremo a extremo | `frontend_fase2.md` §8 |

Los pasos 1-8 no dependen del frontend. El frontend solo necesita que `POST /documents` esté
disponible y que el formato de error estándar siga igual.

---

## 8. Criterios de cierre de la fase

- [ ] `pytest` en backend: 50 base + nuevos (~61) en verde.
- [ ] `tsc`, `eslint` y `npm run build` en frontend sin errores.
- [ ] `grep -rn "VITE_DEV_DOCUMENT_ID" frontend/` → 0 resultados.
- [ ] Subida real desde la UI → generación creada → polling hasta `completed`, mostrando el nombre
      del archivo subido.
- [ ] `DELETE /documents/{id}` → `204` solo sin generaciones; `409` en cualquier otro caso.
- [ ] `openapi.yaml`, `README.md` y `database.md` actualizados.

---

## 9. Regla ante conflictos

Si hay un conflicto entre estos documentos, `openapi.yaml` y lo que se encuentre en el código,
prevalece el contrato real (`docs/openapi.yaml` + código) y el conflicto debe reportarse antes de
continuar, igual que en la Fase 1.5.

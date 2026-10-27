# Fase 2 — Subida de documentos (`POST /documents`) y subida real en la interfaz

Implementación de las cuatro rutas de `documents` definidas en `docs/openapi.yaml` y conexión de la
subida real de archivos en `GenerationPage`, eliminando la dependencia del documento fijo del seed
(`VITE_DEV_DOCUMENT_ID`).

Las rutas del backend son relativas a `backend/` y las del frontend a `frontend/`.

**Prerrequisito:** esta fase parte del código de la **Fase 1.5** (commit `bc0e3b3` «Ejecución de la
fase 1.5», ramas `backend`/`generador-backend`): manejador de errores HTTP y CORS en el backend;
cliente HTTP (`shared/api`), `useAsyncData` con reintentos y `VITE_DEV_DOCUMENT_ID` activo en el
frontend. La rama actual de documentación (`docs-backend`) **no contiene ese código**: si se
implementa desde aquí, integrar primero la Fase 1.5.

Fuentes: `indicaciones.md` (§1.2 y §2.1), `Fase 1/database.md` (decisión 8), `docs/openapi.yaml`
(contrato) y `entrega_fase1_5.md`.

---

## 1. Mapa de carpetas: qué se toca y qué no

| Zona | Se toca | No se toca |
|---|---|---|
| Backend | `ai_service/api/routes/documents.py` **(nuevo)**, `api/dependencies.py`, `main.py`, `services/documents.py` **(nuevo)**, `schemas/documents.py` **(nuevo)**, `schemas/records.py`, `repositories/documents.py`, `repositories/generations.py`, `repositories/in_memory.py`, `clients/storage.py` **(nuevo)**, `core/errors.py`, `api/errors.py`, `config.py`, `.env.example`, `supabase/schema.sql`, `tests/`, `README.md`, `docs/openapi.yaml` (solo texto del 409) | `ai_service/pipeline/**`, `api/routes/generations.py`, `services/generations.py`, `supabase/seed.sql` |
| Frontend | `src/shared/api/` (multipart), `src/features/generation/services/` (`documentService` nuevo, `generationService`), `hooks/useStartGeneration.ts`, `pages/GenerationPage.tsx`, `components/DocumentUploadCard.tsx`, `.env`, `.env.example`, `src/vite-env.d.ts` | `features/history/**`, `features/metrics/**`, `features/comparison/**`, `hooks/useExecutionProgress.ts`, `__fixtures__/` |
| Documentación | `README.md` (§4, §9, §10 y enlace roto de `database.md`), `docs/openapi.yaml` (descripción del `deleteDocument`), `Fase 1/database.md` (decisión 8) | `indicaciones.md`, `fase1_5_pipeline.md` (históricos) |

---

## 2. Decisiones adoptadas

| # | Decisión | Motivo |
|---|---|---|
| D1 | **`VITE_DEV_DOCUMENT_ID` se elimina por completo** (servicio, página, tipos, `.env*`). El flujo siempre sube el archivo. | El objetivo de la fase es que la UI funcione con archivos reales; dos caminos de código cuestan más de mantener que de usar. |
| D2 | El frontend **solo consume `POST /documents`**. `GET`/`DELETE` se implementan y prueban en backend, sin UI. | Alcance mínimo para desbloquear la subida; el listado y el borrado se consumirán en la fase de gestión de documentos (§9). |
| D3 | Regla de `DELETE /documents/{id}` = **409 si el documento tiene alguna generación** (§4). | Coherente con la restricción FK real y con la lectura del nombre por JOIN; cero migraciones. |
| D4 | El contrato es `openapi.yaml` tal cual; solo se ajusta la **descripción** del 409 (hoy redactada como «solo activas»). | El contrato ya está cerrado (4 `operationId`, mensajes y códigos); la regla real es más estricta que la prosa actual. |
| D5 | **Abstracción de Storage** (`DocumentStorage` con impl Supabase y fake en memoria), siguiendo el patrón de repositorios. | Los tests no deben tocar Supabase; `create_app` ya inyecta dependencias. |
| D6 | Si `POST /documents` tiene éxito y `POST /generations` falla, **no se revierte** el documento. | README §4.4: carga y generación son operaciones independientes; un documento es reutilizable. |
| D7 | La **validación de tipo se hace por extensión** (`txt`/`pdf`/`docx`), no por cabecera `Content-Type`. | El navegador puede enviar cabeceras genéricas; el esquema de `file_type` es la extensión y el mensaje del contrato habla de «Use TXT, PDF o DOCX». |
| D8 | `checksum` = **SHA-256** en hexadecimal del contenido. | Huella determinista del contenido; el contrato no fija algoritmo. |

---

## 3. Alcance

### 3.1. Endpoints (contrato: `docs/openapi.yaml`)

| Método | Ruta | `operationId` | Línea | Backend | Frontend |
|---|---|---|---|---|---|
| `POST` | `/api/v1/documents` | `createDocument` (201 multipart) | 93 | **Por implementar** | **Se consume** (subida) |
| `GET` | `/api/v1/documents` | `listDocuments` (200) | 135 | **Por implementar** | No se consume |
| `GET` | `/api/v1/documents/{document_id}` | `getDocument` (200/404) | 158 | **Por implementar** | No se consume |
| `DELETE` | `/api/v1/documents/{document_id}` | `deleteDocument` (204/404/409) | 173 | **Por implementar** | No se consume |

Respuestas de error previstas por el contrato: `400 VALIDATION_ERROR`, `404 DOCUMENT_NOT_FOUND`,
`409 DOCUMENT_IN_USE`, `413 PAYLOAD_TOO_LARGE`, `415 UNSUPPORTED_MEDIA_TYPE`, `500 INTERNAL_ERROR`.

Flujo de la UI tras esta fase: seleccionar archivo → «Generar» → `POST /documents` → `201` con
`id` → `POST /generations` con ese `document_id` → polling (sin cambios).

### 3.2. Fuera del alcance

- Selector de documentos existentes y borrado desde la UI (§9).
- `GET /generations/{id}/events` (SSE, hoy `501`).
- Rutas de resultados (`user-stories`, `clusters`, `metrics`, …) y `summary` con conteos.
- Historial conectado (`history` sigue con mocks), métricas y comparación.
- Retención automática de generaciones antiguas (§4.4).
- Soft delete de documentos (solución B2 de §4).
- Autenticación/autorización por usuario (no existe en ninguna parte).

---

## 4. `DELETE /documents/{id}`: posibles soluciones y por qué

### 4.1. Contexto verificado (dos bloqueadores, no uno)

1. **FK explícita** — `supabase/schema.sql:27`:
   `generations.document_id uuid not null references public.documents (id) on delete restrict`.
   La base de datos prohíbe borrar un documento con **cualquier** generación que lo referencie,
   activa o finalizada.
2. **JOIN en vivo (bloqueador oculto)** — `repositories/generations.py:22`:
   `_SELECT = "*, documents(filename), generation_stages(*)"`. `document_name` **no está
   denormalizado** en `generations` (no existe la columna); se resuelve en cada lectura contra la
   fila de `documents`. Si el documento se borrara, `document_name` sería `null` y
   `GenerationRecord.document_name: str` (`schemas/records.py`) **fallaría → 500 en toda lectura**
   de esas generaciones (`GET /generations`, listados, polling de la Fase 1.5). Quitar solo la FK
   no bastaría.

Qué protege realmente la **decisión 8** de `database.md` («cómo se eliminan documentos y
ejecuciones sin comprometer la integridad de los resultados históricos»): los resultados
(`user_stories`, `test_cases`, `generation_metrics`, …) dependen de `generations` con
`on delete cascade`, **no del documento**; su integridad no está en peligro. Lo que se pierde al
borrar un documento es la **procedencia** (qué archivo produjo estos resultados) y el nombre
legible de la entrada.

### 4.2. Soluciones posibles

| | Solución | Cambia la BD | Contrato / frontend | Alcance | Procedencia |
|---|---|---|---|---|---|
| **A** | **409 si tiene alguna generación**; `204` solo con cero generaciones | **No** | Ajustar la *descripción* del 409 en openapi (la respuesta en sí no cambia) | Mínimo: servicio + tests + docs | ✅ intacta |
| **B2** | **Soft delete**: columna `documents.deleted_at`; `DELETE` marca borrado y purga Storage; listados y `GET` ocultan; `POST /generations` rechaza borrados | **Sí** (migración: columna + índice) | Sin cambios en esquemas (el borrado se oculta) | Medio: migración + filtros en repo/servicio + pruebas | ✅ la fila se conserva para el JOIN |
| **B1** | **Denormalizar** `document_name` en `generations` + FK `on delete set null` (`document_id` nullable) | **Sí** (migración + backfill + repo deja de usar JOIN) | `Generation.document_id` pasa a nullable → openapi **y** tipos/mapeadores del frontend | Alto | ❌ solo queda el nombre; desaparece el vínculo con el archivo |
| **C** | `on delete cascade` | **Sí** | — | — | ❌ **descartada**: borraría resultados históricos; es exactamente lo que la decisión 8 quiere evitar |

**Por qué cada una (resumen):**

- **A** — Es la única que cumple el objetivo sin tocar la base de datos: la FK y el JOIN siguen
  garantizando que ninguna generación pierda su nombre o su procedencia. Regla simple y explicable
  («lo que ya se usó no se borra»), alcance mínimo para una fase cuyo objetivo es la subida.
  *Contra:* un documento usado una vez no puede eliminarse nunca (acumula fila + objeto en
  Storage) y la decisión 8 queda cerrada solo **parcialmente**.
- **B2** — Cierra del todo la decisión 8: se puede «borrar» un documento usado porque la fila se
  conserva (el JOIN y la procedencia siguen vivos) y el archivo se purga de Storage. *Contra:*
  exige migración en Supabase, filtros obligatorios en listado/`GET`/`POST /generations` (si no,
  un documento «borrado» seguiría siendo utilizable) y más pruebas; el alcance crece sin ayudar al
  objetivo real de esta fase (subir archivos).
- **B1** — Permite borrado real y definitivo. *Contra:* es el cambio más grande (migración con
  backfill, contrato y frontend), y **pierde el vínculo con el archivo original**: solo queda el
  nombre, contradiciendo el espíritu de la decisión 8 (conservar la integridad de los resultados
  históricos).
- **C** — Imposible de defender: destruiría resultados históricos al borrar el archivo de entrada.

### 4.3. Decisión adoptada: **A**

- `DELETE /documents/{id}`:
  1. `404 DOCUMENT_NOT_FOUND` si no existe.
  2. Si el documento tiene **alguna** generación → `409 DOCUMENT_IN_USE` con
     `details.generation_ids` (ids reales, tope 50) **sin borrar nada**. Mensajes:
     - con generaciones activas (`queued`/`running`): «El documento tiene generaciones activas y
       no puede eliminarse.» (el ejemplo del contrato, `openapi.yaml:194`).
     - solo finales: «El documento tiene generaciones asociadas y no puede eliminarse.».
  3. En otro caso: borrar la fila y, **después**, purgar el objeto de Storage (best-effort: si la
     purga falla, se loguea el `storage_path` como huérfano y se devuelve `204`).
- La comprobación previa es barata: existe el índice `generations_document_id_idx`
  (`schema.sql:208`). Como red de seguridad, si la fila se elimina entre el chequeo y el borrado,
  la violación de FK (Supabase `23503`) se traduce también en `409` (§11.4).
- **Registro de la decisión 8:** `Fase 1/database.md` (§7.8) y `README.md` apuntan a esta regla y
  dejan constancia de que el **soft delete (B2) queda como fase futura de gestión de documentos**.
  Aprovechar para corregir el enlace roto `docs/database.md` del README (la ruta real es
  `docs/prompts_fases/Fase 1/database.md`).
- **Ajuste de openapi:** solo prosa — en `deleteDocument` (líneas 176-178) sustituir
  «generaciones activas (`queued` o `running`)» por «generaciones que dependan del documento
  (activas o finalizadas)» y señalar la decisión 8 como cerrada con esa regla. El esquema de
  respuesta no cambia.

### 4.4. Aclaraciones relacionadas

- **El borrado de generaciones ya existe**: `DELETE /api/v1/generations/{generation_id}`
  (`openapi.yaml:348`; implementado en `api/routes/generations.py:62` vía la RPC
  `delete_generation_if_final`, `supabase/schema.sql:266`) borra la generación y sus resultados en
  cascada, con `409 GENERATION_IN_PROGRESS` si sigue activa. En el frontend ya existe UI de
  borrado en `/history` (`ConfirmDeleteDialog`, `ExecutionHistoryTableCard`,
  `historyService.deleteExecutions`), hoy con mocks hasta que el historial se conecte.
  `DELETE /documents` **no** borra generaciones: borra el archivo de entrada.
- **Retención automática** («borrar generaciones con más de X días»): **no está contemplada** en
  `openapi.yaml`, `database.md` ni en el código. Sería una función nueva de backend (tarea
  programada + política de retención) y una decisión de producto aparte → §9.
- Incidental: `database.md` §7.10 («ejecuciones interrumpidas, pendiente») está desactualizada —
  `recover_interrupted_generations` ya existe desde la Fase 1 (`services/pipeline_runs.py:149`).

---

# PARTE BACKEND

## 5.1. Errores de dominio (413/415/409 y 400 de subida)

**Archivo:** `ai_service/core/errors.py` (+ `ai_service/api/errors.py`).

Nuevas excepciones y su estado HTTP en `_STATUS_BY_ERROR`:

| Excepción | `code` | HTTP | Mensaje por defecto (contrato) |
|---|---|---|---|
| `PayloadTooLarge` | `PAYLOAD_TOO_LARGE` | 413 | «El archivo supera el tamaño máximo de 20 MiB.» (la longitud se lee de `MAX_UPLOAD_SIZE_BYTES`; si cambia la variable, el mensaje se formatea con el valor real en MiB) |
| `UnsupportedMediaType` | `UNSUPPORTED_MEDIA_TYPE` | 415 | «Tipo de archivo no soportado. Use TXT, PDF o DOCX.» |
| `DocumentInUse` | `DOCUMENT_IN_USE` | 409 | Activa: «El documento tiene generaciones activas y no puede eliminarse.»; solo finales: «El documento tiene generaciones asociadas y no puede eliminarse.» |
| `InvalidDocumentUpload` | `VALIDATION_ERROR` | 400 | «El archivo está vacío.» (con `details=[{"path": "file", ...}]`, imitando el formato del manejador de validación) |

Registrar los cuatro en `_STATUS_BY_ERROR` (`api/errors.py:22`): sin entrada, el manejador de
`AppError` responde `500`. Los códigos ya están declarados en `openapi.yaml`
(`components.schemas.ErrorDetail`, línea ~861).

## 5.2. Configuración

**Archivo:** `ai_service/config.py` (+ `.env.example`).

| Variable | Atributo | Default | Origen |
|---|---|---|---|
| `MAX_UPLOAD_SIZE_BYTES` | `max_upload_size_bytes: int` (`Field(gt=0)`) | `20971520` (20 MiB) | Nombre fijado por `openapi.yaml:110` |
| `DOCUMENTS_BUCKET` | `documents_bucket: str` | `documents` | Bucket privado de Storage |

`.env.example`: añadir ambas con comentario (formato y que el bucket debe existir en Supabase,
ver §5.8). `FRONTEND_ORIGINS` no cambia (CORS ya admite `GET/POST/DELETE` y `Content-Type`).

## 5.3. Esquemas públicos

**Archivo nuevo:** `ai_service/schemas/documents.py` (espejo exacto de
`openapi.yaml:894-912`).

```python
class Document(BaseModel):
    id: UUID
    filename: str
    file_type: Literal["txt", "pdf", "docx"]
    size_bytes: int
    checksum: str
    uploaded_at: datetime

class DocumentList(BaseModel):
    items: list[Document]
    pagination: Pagination   # de schemas/generations.py (reutilizar)
```

`storage_path` **nunca** aparece aquí («no se expone», openapi:895). En paraleto,
`schemas/records.py::DocumentRecord` gana `storage_path: str` (interno; el comentario
«sin storage_path, que la Fase 1 no necesita» pasa a ser falso) y `repositories/documents.py`
incluye la columna en `_COLUMNS`.

## 5.4. Almacenamiento

**Archivo nuevo:** `ai_service/clients/storage.py`.

```python
class DocumentStorage(Protocol):
    async def upload(self, *, document_id: UUID, filename: str, content_type: str, data: bytes) -> str: ...
    async def remove(self, storage_path: str) -> None: ...
```

- `SupabaseDocumentStorage(client, bucket)`: `client.storage.from_(bucket).upload(...)` /
  `.remove([...])` ejecutados con `asyncio.to_thread` (mismo patrón que los repositorios).
  `storage_path = f"{document_id}/{filename_saneado}"` (saneado: separadores de ruta `/\` y
  nombres vacíos; conserva extensión). `content_type` por extensión
  (`txt → text/plain`, `pdf → application/pdf`,
  `docx → application/vnd.openxmlformats-officedocument.wordprocessingml.document`).
- `remove` es **best-effort** en los flujos de servicio (se loguea y se continúa); la firma no
  lanza hacia arriba salvo error inesperado.
- **Fake para tests:** `FakeDocumentStorage` en `tests/factories.py` — guarda los objetos en un
  `dict[bytes|tuple]`, registra `uploads`/`removes` para poder asertarlos y simula «no existe» al
  retirar una clave inexistente.

## 5.5. Repositorios

### `repositories/documents.py` (ampliar protocolo + Supabase)

```python
class DocumentsRepository(Protocol):
    async def get_by_id(self, document_id: UUID) -> DocumentRecord | None: ...   # ya existe
    async def create(self, *, document_id: UUID, filename: str, file_type: str,
                     size_bytes: int, storage_path: str, checksum: str,
                     uploaded_at: datetime) -> None: ...
    async def list_documents(self, *, limit: int, offset: int) -> tuple[list[DocumentRecord], int]: ...
    async def delete(self, document_id: UUID) -> None: ...   # lanza DocumentNotFound
```

- `create`: `insert` con `id` explícito (lo genera el servicio, porque el `storage_path` lo
  necesita antes). Ante violación de FK u otra `APIError` → se propaga (el servicio ya limpió
  Storage).
- `list_documents`: orden `uploaded_at` desc + `id` desc (desempate, como `list_generations`),
  `count=CountMethod.exact`, `range(offset, offset+limit-1)` y manejo del `416` de PostgREST con
  página vacía (replicar el patrón de `SupabaseGenerationsRepository.list_generations`,
  `repositories/generations.py:147-180`).
- `delete`: `delete().eq("id", …)`; si `APIError.code == 23503` → lanzar `DocumentInUse` (red de
  seguridad, §4.3).

### `repositories/in_memory.py` (fake de tests)

- `InMemoryDocumentsRepository`: `create` (inserta `DocumentRecord`), `list_documents` (ordena
  por `uploaded_at` desc con desempate por inserción y pagina), `delete` (404 si falta).
- `InMemoryGenerationsRepository`: **no** se cambia.

### `repositories/generations.py` (consulta de soporte para el 409)

Nuevo método en el protocolo y en ambas implementaciones:

```python
async def ids_by_document(self, document_id: UUID, *, statuses: Collection[GenerationStatus] | None,
                          limit: int) -> tuple[list[UUID], int]:
    """Ids de generaciones del documento (filtradas por estado si se indica) y total."""
```

- Supabase: `select("id", count=exact).eq("document_id", …)` + `.in_("status", […])` cuando
  `statuses` no es `None`.
- In-memory: filtro equivalente sobre el `store`.
- El servicio lo llama dos veces: con `ACTIVE_GENERATION_STATUSES` (si `total > 0` → 409
  «activas») y con `None` (si `total > 0` → 409 «asociadas»); `limit=50` para los ids.

## 5.6. Servicio de documentos

**Archivo nuevo:** `ai_service/services/documents.py`.

```python
class DocumentsService:
    def __init__(self, documents: DocumentsRepository, generations: GenerationsRepository,
                 storage: DocumentStorage, max_upload_size_bytes: int) -> None: ...

    async def upload(self, file: UploadFile) -> Document: ...
    async def list(self, *, limit: int, offset: int) -> DocumentList: ...
    async def get(self, document_id: UUID) -> Document: ...
    async def delete(self, document_id: UUID) -> None: ...
```

**`upload` (orden y validaciones):**

1. Extensión del nombre original (`filename`): `txt|pdf|docx` → de lo contrario
   `UnsupportedMediaType` (D7). Nota: comprobar **antes** de leer todo el contenido.
2. Lectura **por tramos** (1 MiB) acumulando hasta `max_upload_size_bytes + 1`; si se supera →
   `PayloadTooLarge` (no confiar en `Content-Length`, §11.3).
3. Vacío (`size_bytes == 0`) → `InvalidDocumentUpload` (400).
4. `checksum = sha256(data).hexdigest()`; `document_id = uuid4()`; `file_type` = extensión;
   `storage_path` calculado por el storage.
5. `storage.upload(...)`; a continuación `documents.create(...)`; si el insert falla →
   `storage.remove(...)` best-effort y relanzar.
6. Devuelve `to_document(record)`.

**`delete` (§4.3):** `get` (404) → `ids_by_document` activas (409) → `ids_by_document` total
(409) → `documents.delete` (traduce `23503` → 409) → `storage.remove` best-effort (log con
`storage_path` si falla).

**`list`/`get`:** mapeo simple; `Pagination(limit=…, offset=…, total=…)`.

`to_document(record)` vive en este servicio (patrón de `to_generation` en
`services/generations.py:34`).

## 5.7. Rutas y registro

**Archivo nuevo:** `ai_service/api/routes/documents.py`
(`APIRouter(prefix="/documents", tags=["Documents"])`, con `responses` que referencien
`ErrorResponse` como en `routes/generations.py`):

| Ruta | Firma | Notas |
|---|---|---|
| `POST ""` | `async def create_document(file: UploadFile, service: Service) -> Document` con `201` y `operation_id="createDocument"` | El campo multipart **se llama `file`** (openapi:105). Sin `File(...)` explícito basta con el tipo `UploadFile`; si falta el campo, FastAPI devuelve `422` → el manejador de validación lo traduce a `400 VALIDATION_ERROR` con `details path: file` (ya verificado en Fase 1.5) |
| `GET ""` | `limit` (1-100, defecto 20), `offset` (≥0) → `DocumentList`, `operation_id="listDocuments"` | Idéntico a `listGenerations` |
| `GET "/{document_id}"` | `Document`, `404`, `operation_id="getDocument"` | |
| `DELETE "/{document_id}"` | `204`, `404`, `409`, `operation_id="deleteDocument"` | Devuelve `Response(status_code=204)` |

**`api/dependencies.py`:** `get_documents_service(request) -> DocumentsService` (mismo patrón que
`get_generations_service`).

**`main.py`:**

- `create_app` gana el parámetro `documents_storage: DocumentStorage | None = None` (para tests).
- En el `lifespan`: `storage = documents_storage or SupabaseDocumentStorage(client,
  app_settings.documents_bucket)`; construir
  `app.state.documents_service = DocumentsService(documents=documents_repo,
  generations=generations_repo, storage=storage,
  max_upload_size_bytes=app_settings.max_upload_size_bytes)`.
- `app.include_router(documents.router, prefix=API_PREFIX)`.
- **CORS:** sin cambios — `allow_methods=["GET","POST","DELETE"]` y `allow_headers=["Content-Type"]`
  ya cubren el preflight multipart (solo relevante en flujos cross-origin; en desarrollo manda el
  proxy de Vite, ver `entrega_fase1_5.md`).

## 5.8. Bucket de Storage en Supabase

**Archivo:** `supabase/schema.sql` (al final, junto a las tablas):

```sql
-- Bucket privado para POST /documents (service_role bypasa RLS; sin políticas para anon/auth).
insert into storage.buckets (id, name, public)
values ('documents', 'documents', false)
on conflict (id) do nothing;
```

- El nombre real se puede ajustar con `DOCUMENTS_BUCKET` (§5.2); verificar primero si el
  proyecto ya tiene un bucket (§11.1).
- El objeto del `seed.sql` **no existe** en Storage (comentario de la propia cabecera): borrar el
  documento del seed con `DELETE` funciona (la purga best-effort tolera el objeto inexistente).
- `README.md` §9: añadir el requisito del bucket al «Ejecución local».

## 5.9. Pruebas del backend

**Archivo nuevo:** `tests/test_documents_api.py` (patrón de `test_generations_api.py`, helper
`assert_error`):

1. `POST /documents` con `.txt` → `201`, cuerpo igual al esquema `Document`, sin `storage_path`,
   fila presente en el listado, objeto registrado en el fake de Storage.
2. Extensión no permitida (`.png`) → `415 UNSUPPORTED_MEDIA_TYPE`.
3. Tamaño superado (settings con `max_upload_size_bytes` pequeño, p. ej. 64) →
   `413 PAYLOAD_TOO_LARGE`.
4. Archivo vacío → `400 VALIDATION_ERROR` con `details[0].path == "file"`.
5. Sin campo `file` (multipart sin él) → `400 VALIDATION_ERROR`.
6. `GET /documents` → paginación (`limit`/`offset`/`total`), orden `uploaded_at` desc.
7. `GET /documents/{id}` → `200` / `404 DOCUMENT_NOT_FOUND`.
8. `DELETE` sin generaciones → `204`, luego `GET` → `404`, `storage.remove` invocado.
9. `DELETE` con generación activa → `409 DOCUMENT_IN_USE` + `details.generation_ids` (usa
   `add_generation` de `tests/factories.py`); sin borrar la fila ni el storage.
10. `DELETE` con solo generaciones finales → `409` con el mensaje de «asociadas».
11. `DELETE` inexistente → `404`.

**`tests/conftest.py` y `tests/factories.py`:** fixture `storage` (`FakeDocumentStorage`) y
paso a `client_factory(...)` → `create_app(..., documents_storage=storage)`; el `store` existente
sigue sembrando el documento del seed.

**`tests/test_contract.py`:** validar `Document` y `DocumentList` contra `docs/openapi.yaml` en
un upload y en el listado; añadir el `409` de `deleteDocument` al helper de errores (los
esquemas ya están en el spec: `components.schemas.Document` línea 894).

Objetivo: **50 base + ~11 nuevos = 61 passed**.

## 5.10. Documentación afectada

| Archivo | Cambio |
|---|---|
| `README.md` §4.1 | Las cuatro filas de documentos pasan a estar implementadas (§10 es la fuente de estado). |
| `README.md` §4.3 | Sustituir «mientras existan generaciones activas» por la regla de §4.3 (activas **o** finales) y enlazar la decisión 8. |
| `README.md` §9 | Requisito del bucket (`DOCUMENTS_BUCKET`) para la subida. |
| `README.md` §10 | `Carga de documentos` → **Implementado** (valida tipo/tamaño, guarda en Storage, registra metadatos); `Listado y consulta de documentos` → **Implementado**; `Eliminación de documentos y generaciones` → **Parcial** (documentos: regla Fase 2; generaciones: ya implementadas). |
| `README.md` «Documentación relacionada» | Enlace roto `docs/database.md` → `docs/prompts_fases/Fase 1/database.md`. |
| `docs/openapi.yaml` | Solo la prosa del `deleteDocument`/409 (§4.3). Los 20 `operationId` ya están completos. |
| `Fase 1/database.md` | §7.8 decisión 8: registrar la regla A de la Fase 2 y que B2 queda como fase futura; nota en §3.2. Opcional: §7.10 (incidental, §4.4). |

---

# PARTE FRONTEND

## 6.1. Cliente multipart

**Archivos:** `src/shared/api/http.ts` (+ export en el barrel correspondiente).

Nueva función junto a `request<T>`:

```ts
export async function uploadFormData<T>(
    path: string,
    formData: FormData,
    { signal }: { signal?: AbortSignal } = {},
): Promise<T>
```

- Mismo `fetch` que `request` **sin cabecera `Content-Type`** (la pone el navegador con su
  `boundary`); solo `Accept: application/json`.
- Reutiliza `readJson`/`toApiError`/`ApiError` y la tolerancia a cuerpos no JSON (p. ej. HTML del
  proxy). `204 → undefined`, `AbortError` se relanza sin envolver, `NETWORK_ERROR` igual que hoy.
- El error de red **no** es «transitorio» aquí (no hay polling de subida): el llamador lo muestra.

## 6.2. `documentService`

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
        formData.append("file", file);
        const dto = await uploadFormData<DocumentDto>("/documents", formData, { signal });
        return dto.id;
    },
};
```

Sin mapeador aparte: solo se consume el `id` (D2). Si en una fase futura se lista/borra
documentos, aquí crecerá el DTO completo.

## 6.3. `generationService.startGeneration`

**Archivo:** `src/features/generation/services/generationService.ts`.

- **Eliminar** `DEV_DOCUMENT_ID` (líneas 17-19) y su uso; el `throw` de「VITE_DEV_DOCUMENT_ID no
  está configurado」desaparece.
- `StartGenerationInput.file` deja de ser «validado pero no enviado»: se sube.
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
  registrado (reutilizable; no hay rollback).
- `getExecutionPipeline` **sigue con mocks** (intacto).

## 6.4. `useStartGeneration`

**Archivo:** `src/features/generation/hooks/useStartGeneration.ts` — ampliar
`startErrorMessage`:

| `code` | Mensaje |
|---|---|
| `PAYLOAD_TOO_LARGE` | «El archivo supera el límite de 20 MB.» |
| `UNSUPPORTED_MEDIA_TYPE` | «Tipo de archivo no soportado. Usa un archivo TXT, PDF o DOCX.» |
| `DOCUMENT_NOT_FOUND` | se conserva (residual, hoy inalcanzable en este flujo) |
| `VALIDATION_ERROR` | «La solicitud no es válida.» (igual que hoy) |
| `NETWORK_ERROR` / `status >= 500` | sin cambios |

La doble llamada (subir + crear) cubre el estado `isCreating` entero; el guard anti doble clic
(`inFlight`) **no** se toca.

## 6.5. `GenerationPage` y `DocumentUploadCard`

**`pages/GenerationPage.tsx`:**

- Eliminar el import de `DEV_DOCUMENT_ID` y la constante `DEV_DOCUMENT_NOTICE` (líneas 51-53):
  la tarjeta ya no recibe `notice` (la propiedad es opcional en el componente).
- `submitDisabled`: quitar `!DEV_DOCUMENT_ID` →
  `isTrackingActive || (!!active.generationId && progress.isLoading)`.
- `handleSubmit`: retirar el comentario `TODO Fase 2` (línea 86): el archivo ya se envía.

**`components/DocumentUploadCard.tsx`:**

- Sin cambios estructurales; el botón conserva «Iniciando ejecución…» (un solo estado
  `isSubmitting` cubre subir + crear; añadir etiquetas por paso exigiría estado extra sin valor).
- El aviso de «documento de ejemplo» desaparece con `DEV_DOCUMENT_NOTICE`.

## 6.6. Eliminación de `VITE_DEV_DOCUMENT_ID`

| Archivo | Acción |
|---|---|
| `frontend/.env` | **Borrar la línea** `VITE_DEV_DOCUMENT_ID=…` (está en `.gitignore`; editarlo a mano o al ejecutar) |
| `frontend/.env.example` | Borrar el bloque comentado de la variable (líneas 6-8) |
| `src/vite-env.d.ts` | Quitar la propiedad `readonly VITE_DEV_DOCUMENT_ID?: string` |
| `src/features/generation/services/generationService.ts` | Quitar `DEV_DOCUMENT_ID` (§6.3) |
| `src/features/generation/pages/GenerationPage.tsx` | Quitar aviso y guard (§6.5) |

Verificación: `grep -rn "VITE_DEV_DOCUMENT_ID" frontend/` → 0 resultados.

## 6.7. Validación del cliente (se conserva)

`DocumentUploadCard` ya valida extensión (`pdf/docx/txt`), tamaño (≤ 20 MB) y archivo vacío
(líneas 47-54) **antes** de enviar. Se mantiene como primera línea de defensa (mejor UX); la
del backend (§5.6) es la autoritativa — ambas deben coincidir en límites y formatos.

---

## 7. Archivos a tocar, por zona

### 7.1. Backend

| Archivo | Cambio |
|---|---|
| `ai_service/core/errors.py` | +4 excepciones (§5.1) |
| `ai_service/api/errors.py` | Registrar en `_STATUS_BY_ERROR` |
| `ai_service/config.py` | `max_upload_size_bytes`, `documents_bucket` (§5.2) |
| `ai_service/schemas/documents.py` | **Nuevo**: `Document`, `DocumentList` |
| `ai_service/schemas/records.py` | `DocumentRecord.storage_path` |
| `ai_service/clients/storage.py` | **Nuevo**: protocolo + `SupabaseDocumentStorage` |
| `ai_service/repositories/documents.py` | `create`, `list_documents`, `delete` + columnas |
| `ai_service/repositories/generations.py` | `ids_by_document` |
| `ai_service/repositories/in_memory.py` | Fakes de los métodos nuevos |
| `ai_service/services/documents.py` | **Nuevo**: servicio (§5.6) |
| `ai_service/api/routes/documents.py` | **Nuevo**: 4 endpoints |
| `ai_service/api/dependencies.py` | `get_documents_service` |
| `ai_service/main.py` | Inyección de storage + router |
| `.env.example` | `MAX_UPLOAD_SIZE_BYTES`, `DOCUMENTS_BUCKET` |
| `supabase/schema.sql` | Inserción del bucket (§5.8) |
| `tests/factories.py`, `tests/conftest.py` | `FakeDocumentStorage`, fixture |
| `tests/test_documents_api.py` | **Nuevo** (§5.9) |
| `tests/test_contract.py` | Contratos `Document`/`DocumentList`/409 |
| `README.md`, `docs/openapi.yaml`, `Fase 1/database.md` | §5.10 |

### 7.2. Frontend

| Archivo | Cambio |
|---|---|
| `src/shared/api/http.ts` (+ barrel) | `uploadFormData` |
| `src/features/generation/services/documentService.ts` | **Nuevo** |
| `src/features/generation/services/generationService.ts` | Subir → crear; fuera `DEV_DOCUMENT_ID` |
| `src/features/generation/hooks/useStartGeneration.ts` | Mensajes 413/415 |
| `src/features/generation/pages/GenerationPage.tsx` | Fuera aviso/guard del ID |
| `src/features/generation/components/DocumentUploadCard.tsx` | Sin cambios estructurales |
| `.env`, `.env.example`, `src/vite-env.d.ts` | Fuera `VITE_DEV_DOCUMENT_ID` |

---

## 8. Checklist de verificación

### 8.1. Automático

```bash
# backend (desde backend/; el venv es .venv)
.venv\Scripts\python -m pytest                  # base 50 + nuevos (§5.9) → 61

# frontend (desde frontend/)
npx tsc --noEmit -p tsconfig.app.json           # 0 errores
npx eslint .                                    # 0 problemas
npm run build                                   # OK
grep -rn "VITE_DEV_DOCUMENT_ID" src/ .env.example  # 0 resultados
```

### 8.2. Manual

Con backend (`.env` con Supabase, bucket §5.8 aplicado) y frontend en marcha:

1. `POST /documents` con un `.txt` real (curl `-F "file=@notas.txt"`) → `201` con `Document`,
   sin `storage_path`; el objeto aparece en el bucket y la fila en `documents`.
2. `POST` con `.png` → `415 UNSUPPORTED_MEDIA_TYPE`.
3. `POST` con archivo > 20 MiB → `413 PAYLOAD_TOO_LARGE`.
4. `POST` multipart sin campo `file` → `400 VALIDATION_ERROR` (`details path: file`).
5. `GET /documents` → lista paginada ordenada por `uploaded_at` desc; `GET /documents/{id}`
   → `200` y con id inventado → `404`.
6. `DELETE` de un documento sin generaciones → `204`; repetir → `404`; el objeto desaparece del
   bucket.
7. `DELETE` del documento de una generación activa → `409 DOCUMENT_IN_USE` con
   `generation_ids`; de uno con solo generaciones finales → `409` con el mensaje de «asociadas».
8. **Flujo UI completo sin `VITE_DEV_DOCUMENT_ID`:** seleccionar un archivo nuevo →
   «Generar casos de prueba» → subida (`201`) → creación de la generación → URL `/?g=<uuid>` →
   polling hasta `completed`; la generación aparece en recientes con el nombre del archivo subido.
9. Validación del cliente: `.png` o archivo > 20 MB → error en la tarjeta sin llegar a la red.
10. Errores del servidor en la UI: con el backend caído, «No se pudo iniciar la generación»
    (red); comprobación opcional de 413/415 forzados con `MAX_UPLOAD_SIZE_BYTES` temporal.
11. Doble clic en «Generar» → una sola subida (guard `inFlight` intacto).
12. Regresión: `/history`, métricas y comparación siguen con mocks; health y formato de error
    estándar (404 de ruta inexistente) sin cambios.
13. Tras la subida fallida de `POST /generations` (p. ej. apagando el backend entre las dos
    llamadas): el documento queda registrado en `GET /documents` (D6, sin rollback) y la UI
    permite reintentar.

---

## 9. Fuera de alcance → Fase 3

| Bloque | Qué incluye |
|---|---|
| Selector de documentos | Consumir `GET /documents` en la UI para reutilizar documentos ya subidos (opción B de `indicaciones.md` §2.1) |
| Borrado con UI | Consumir `DELETE /documents/{id}` con confirmación (hoy solo backend + tests) |
| Soft delete (B2) | Cierre total de la decisión 8 (§4.2): `deleted_at`, filtros y purga |
| Retención automática | Limpieza de generaciones/documentos antiguos (§4.4): nueva función + política |
| Historial conectado | `historyService.listExecutions`/`deleteExecutions` sobre las rutas ya existentes de `generations` |
| Resultados | Las 10 rutas de `README` §4.2 (requieren pipeline que persista resultados) |
| SSE | `GET /generations/{id}/events` (hoy `501`) |

---

## 10. Orden de implementación sugerido

| Paso | Zona | Contenido | Dependencias |
|---|---|---|---|
| 0 | Ambas | §11: verificar bucket, firma de storage y estado de la rama | Ninguna |
| 1 | Backend | Errores (§5.1) + config (§5.2) + `.env.example` | — |
| 2 | Backend | Esquemas (§5.3) + `DocumentRecord.storage_path` | 1 |
| 3 | Backend | Storage: protocolo, Supabase y fake (§5.4) | 1 |
| 4 | Backend | Repositorios: documentos + `ids_by_document` + fakes (§5.5) | 2 |
| 5 | Backend | Servicio (§5.6) | 3, 4 |
| 6 | Backend | Rutas, dependencia y `main.py` (§5.7) + bucket (§5.8) | 5 |
| 7 | Backend | Pruebas nuevas + contrato (§5.9) → `pytest` | 6 |
| 8 | Backend | Documentación (§5.10) | 7 |
| 9 | Frontend | `uploadFormData` (§6.1) | Paso 1 (formato de error) |
| 10 | Frontend | `documentService` + `generationService` (§6.2-6.3) | 9 |
| 11 | Frontend | Hook, página, tarjeta y limpieza de env (§6.4-6.6) | 10 |
| 12 | Ambas | Checklist §8 completo | Todo |

Los pasos 1-8 no dependen del frontend. No confundir el proxy de desarrollo con CORS: el proxy
cubre el flujo local same-origin (subida incluida); CORS solo importa para llamadas cross-origin
directas (ya configurado en la Fase 1.5).

---

## 11. Puntos que el agente debe verificar antes de codificar

1. **Bucket real del proyecto:** ¿existe ya un bucket en Supabase y con qué nombre?
   (`client.storage.list_buckets()` o dashboard). Si existe otro, usarlo vía `DOCUMENTS_BUCKET`
   en vez de crear `documents`.
2. **Firma de storage en `supabase>=2.10`** (`requirements.txt`): parámetros de `upload`
   (opciones de content-type/upsert) y comportamiento de `remove` con claves inexistentes (el
   seed no tiene objeto real).
3. **Límite de tamaño:** validar durante la lectura por tramos (`max+1` bytes), no confiando en
   `Content-Length` (puede venir ausente o manipulado en multipart).
4. **FK en `delete`:** confirmar que `APIError` de Supabase para `23503` trae el código
   «23503» para mapearlo a `409` como red de seguridad (el pre-check ya cubre el caso normal).
5. **Paginación de `list`:** replicar el manejo del `416` de PostgREST (offset más allá del
   total) usado en `SupabaseGenerationsRepository.list_generations`.
6. **Estado de la rama:** el código de la Fase 1.5 vive en `bc0e3b3` (ramas `backend`/
   `generador-backend`); `docs-backend` solo tiene documentación. Confirmar sobre qué rama se
   implementa (§ «Prerrequisito»).
7. **`frontend/README.md`:** comprobar si menciona variables `VITE_*` (grep) y actualizar si
   documenta `VITE_DEV_DOCUMENT_ID`.
8. **Paridad contrato/rutas:** no existe ningún test global que exiga que todas las
   `operationId` de openapi estén implementadas (solo valida respuestas de rutas llamadas); las
   rutas nuevas añaden sus propios tests de contrato (§5.9).

Si hay un conflicto entre este documento, `openapi.yaml` y lo que el agente encuentre en el
código, prevalece el contrato real (`docs/openapi.yaml` + código) y el conflicto debe reportarse
antes de continuar, igual que en la Fase 1.5.

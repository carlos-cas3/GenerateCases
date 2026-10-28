# Fase 2 — Backend: endpoints de `documents`

Preparar primero los cuatro endpoints de `documents` (y los datos/infraestructura que necesitan)
para que el frontend pueda consumirlos después. Resumen de alcance y decisiones: `fase2.md`.

Todas las rutas son relativas a `backend/`.

**Resultado esperado:** `POST/GET/GET{id}/DELETE /api/v1/documents` implementados según
`docs/openapi.yaml`, con Storage real en Supabase, pruebas en verde y documentación actualizada.

---

## 0. Decisiones que aplican al backend

| # | Decisión |
|---|---|
| D3 | `DELETE` solo procede si el documento **no tiene ninguna generación** (activa o finalizada). |
| D4 | `openapi.yaml` no cambia en esquemas; solo la prosa del `deleteDocument`. |
| D5 | Storage abstraído (`DocumentStorage`) con implementación Supabase y fake para tests. |
| D7 | Tipo validado por **extensión** (`txt`/`pdf`/`docx`), no por `Content-Type`. |
| D8 | `checksum` = SHA-256 hexadecimal. |

---

## 1. Errores de dominio

**Archivos:** `ai_service/core/errors.py` y `ai_service/api/errors.py`.

| Excepción | `code` | HTTP | Mensaje por defecto |
|---|---|---|---|
| `PayloadTooLarge` | `PAYLOAD_TOO_LARGE` | 413 | «El archivo supera el tamaño máximo de 20 MiB.» (se formatea con el valor real de `MAX_UPLOAD_SIZE_BYTES` en MiB) |
| `UnsupportedMediaType` | `UNSUPPORTED_MEDIA_TYPE` | 415 | «Tipo de archivo no soportado. Use TXT, PDF o DOCX.» |
| `DocumentInUse` | `DOCUMENT_IN_USE` | 409 | Ver mensajes en §6 |
| `InvalidDocumentUpload` | `VALIDATION_ERROR` | 400 | «El archivo está vacío.» con `details=[{"path": "file", ...}]` |

Registrar las cuatro en `_STATUS_BY_ERROR` (`api/errors.py`): sin entrada, el manejador de
`AppError` responde `500`. Los códigos ya están declarados en `openapi.yaml`
(`components.schemas.ErrorDetail`).

---

## 2. Configuración

**Archivos:** `ai_service/config.py` y `.env.example`.

| Variable | Atributo | Default | Nota |
|---|---|---|---|
| `MAX_UPLOAD_SIZE_BYTES` | `max_upload_size_bytes: int` (`Field(gt=0)`) | `20971520` (20 MiB) | Nombre fijado por `openapi.yaml` |
| `DOCUMENTS_BUCKET` | `documents_bucket: str` | `docs_testgen` | Bucket privado ya creado en Supabase Storage |

En `.env.example` añadir ambas con comentario (formato y que el bucket debe existir en
Supabase). Para el entorno actual, configurar `DOCUMENTS_BUCKET=docs_testgen` en el `.env` local
y en el entorno desplegado correspondiente. `FRONTEND_ORIGINS` no cambia. No incluir claves
secretas en `.env.example` ni en el frontend.

---

## 3. Esquemas públicos

**Archivo nuevo:** `ai_service/schemas/documents.py` (espejo de `components.schemas.Document` y
`DocumentList` en `openapi.yaml`).

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
    pagination: Pagination   # reutilizar el de schemas/generations.py
```

`storage_path` **nunca** aparece en el esquema público.

**Interno:** `schemas/records.py::DocumentRecord` gana `storage_path: str` (el comentario que dice
«sin storage_path, que la Fase 1 no necesita» deja de ser cierto) y `repositories/documents.py`
incluye la columna en `_COLUMNS`.

---

## 4. Almacenamiento

**Archivo nuevo:** `ai_service/clients/storage.py`.

```python
class DocumentStorage(Protocol):
    async def upload(self, *, document_id: UUID, filename: str,
                     content_type: str, data: bytes) -> str: ...
    async def remove(self, storage_path: str) -> None: ...
```

**`SupabaseDocumentStorage(client, bucket)`**
- Usa `client.storage.from_(bucket).upload(...)` y `.remove([...])` con `asyncio.to_thread` (mismo
  patrón que los repositorios).
- `storage_path = f"{document_id}/{filename_saneado}"`. Saneado: eliminar separadores de ruta
  `/` y `\`, evitar nombres vacíos, conservar extensión.
- `content_type` por extensión:

| Extensión | Content-Type |
|---|---|
| `txt` | `text/plain` |
| `pdf` | `application/pdf` |
| `docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |

- `remove` es **best-effort** en los flujos de servicio: se loguea y se continúa.

**Fake para tests:** `FakeDocumentStorage` en `tests/factories.py`. Guarda los objetos en un
diccionario, registra `uploads` y `removes` para poder asertarlos y tolera retirar claves
inexistentes.

---

## 5. Repositorios

### 5.1. `repositories/documents.py`

```python
class DocumentsRepository(Protocol):
    async def get_by_id(self, document_id: UUID) -> DocumentRecord | None: ...   # ya existe
    async def create(self, *, document_id: UUID, filename: str, file_type: str,
                     size_bytes: int, storage_path: str, checksum: str,
                     uploaded_at: datetime) -> None: ...
    async def list_documents(self, *, limit: int, offset: int
                             ) -> tuple[list[DocumentRecord], int]: ...
    async def delete(self, document_id: UUID) -> None: ...   # lanza DocumentNotFound
```

- `create`: `insert` con `id` explícito (lo genera el servicio porque el `storage_path` lo
  necesita antes). Si falla, se propaga (el servicio ya limpia Storage).
- `list_documents`: orden `uploaded_at` desc + `id` desc como desempate, `count=exact`,
  `range(offset, offset+limit-1)` y manejo del `416` de PostgREST devolviendo página vacía.
  Replicar `SupabaseGenerationsRepository.list_generations` (`repositories/generations.py`).
- `delete`: `delete().eq("id", …)`. Si `APIError.code == "23503"` → lanzar `DocumentInUse`
  (red de seguridad de la FK).

### 5.2. `repositories/in_memory.py` (fakes de tests)

- `InMemoryDocumentsRepository`: `create`, `list_documents` (orden `uploaded_at` desc con
  desempate por inserción, y paginación) y `delete` (404 si falta).
- `InMemoryGenerationsRepository`: añadir solo `ids_by_document`.

### 5.3. `repositories/generations.py` — consulta de soporte para el 409

Nuevo método en el protocolo y en ambas implementaciones:

```python
async def ids_by_document(self, document_id: UUID, *,
                          statuses: Collection[GenerationStatus] | None,
                          limit: int) -> tuple[list[UUID], int]:
    """Ids de generaciones del documento (filtradas por estado si se indica) y total."""
```

- Supabase: `select("id", count=exact).eq("document_id", …)` y `.in_("status", […])` cuando
  `statuses` no es `None`.
- In-memory: filtro equivalente sobre el `store`.
- Existe el índice `generations_document_id_idx`, así que la consulta es barata.

---

## 6. Servicio de documentos

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

`to_document(record)` vive en este servicio (patrón de `to_generation` en
`services/generations.py`).

### 6.1. `upload` (orden y validaciones)

1. Extensión del nombre original: `txt|pdf|docx`; si no → `UnsupportedMediaType`. Se comprueba
   **antes** de leer el contenido.
2. Lectura **por tramos** (1 MiB) acumulando hasta `max_upload_size_bytes + 1`; si se supera →
   `PayloadTooLarge`. No confiar en `Content-Length`.
3. Archivo vacío (`size_bytes == 0`) → `InvalidDocumentUpload` (400).
4. `checksum = sha256(data).hexdigest()`, `document_id = uuid4()`, `file_type` = extensión.
5. `storage.upload(...)` y luego `documents.create(...)`. Si el insert falla →
   `storage.remove(...)` best-effort y se relanza el error.
6. Devuelve `to_document(record)`.

### 6.2. `delete` — regla D3

Orden de evaluación:

1. `get` → `404 DOCUMENT_NOT_FOUND` si no existe.
2. `ids_by_document(statuses=ACTIVE_GENERATION_STATUSES)`: si `total > 0` →
   `409 DOCUMENT_IN_USE`, mensaje **«El documento tiene generaciones activas y no puede
   eliminarse.»** (es el ejemplo del contrato).
3. `ids_by_document(statuses=None)`: si `total > 0` → `409 DOCUMENT_IN_USE`, mensaje **«El
   documento tiene generaciones asociadas y no puede eliminarse.»**
4. Solo si no hay ninguna generación: `documents.delete` y, **después**, `storage.remove`
   best-effort (si falla, se loguea el `storage_path` como huérfano y se devuelve igual `204`).

En los pasos 2 y 3 el error lleva `details.generation_ids` con ids reales (`limit=50`) y **no se
borra nada**.

Red de seguridad: si la fila se elimina o aparece una generación entre el chequeo y el borrado, la
violación de FK de Supabase (`23503`) también se traduce a `409`.

### 6.3. `list` y `get`

Mapeo simple. `list` devuelve `Pagination(limit=…, offset=…, total=…)`.

---

## 7. Rutas y registro

**Archivo nuevo:** `ai_service/api/routes/documents.py`
(`APIRouter(prefix="/documents", tags=["Documents"])`, con `responses` que referencien
`ErrorResponse` como en `routes/generations.py`).

| Ruta | Firma | Notas |
|---|---|---|
| `POST ""` | `async def create_document(file: UploadFile, service: Service) -> Document`, `201`, `operation_id="createDocument"` | El campo multipart se llama **`file`**. Si falta, FastAPI responde `422` y el manejador de validación lo traduce a `400 VALIDATION_ERROR` con `details path: file` |
| `GET ""` | `limit` (1-100, defecto 20), `offset` (≥0) → `DocumentList`, `operation_id="listDocuments"` | Idéntico a `listGenerations` |
| `GET "/{document_id}"` | `Document`, `404`, `operation_id="getDocument"` | |
| `DELETE "/{document_id}"` | `204`, `404`, `409`, `operation_id="deleteDocument"` | Devuelve `Response(status_code=204)` |

**`api/dependencies.py`:** `get_documents_service(request) -> DocumentsService` (mismo patrón que
`get_generations_service`).

**`main.py`:**
- `create_app` gana el parámetro `documents_storage: DocumentStorage | None = None` (para tests).
- En el `lifespan`: `storage = documents_storage or SupabaseDocumentStorage(client,
  app_settings.documents_bucket)` y
  `app.state.documents_service = DocumentsService(documents=documents_repo,
  generations=generations_repo, storage=storage,
  max_upload_size_bytes=app_settings.max_upload_size_bytes)`.
- `app.include_router(documents.router, prefix=API_PREFIX)`.
- **CORS:** sin cambios (`GET/POST/DELETE` y `Content-Type` ya están permitidos). En desarrollo
  manda el proxy de Vite.

---

## 8. Bucket de Storage en Supabase

**Archivo:** `supabase/schema.sql` (al final):

```sql
-- Bucket privado para POST /documents (service_role bypasa RLS; sin políticas para anon/auth).
insert into storage.buckets (id, name, public)
values ('docs_testgen', 'docs_testgen', false)
on conflict (id) do nothing;
```

- El bucket existente del proyecto se llama `docs_testgen`; confirmar en el Dashboard que el
  identificador sea exactamente ese, sin espacios al inicio o al final. No crear un segundo bucket
  llamado `documents` por mantener el valor predeterminado anterior.
- El bucket debe ser **privado** (`public = false`). La API usa credenciales de backend con permisos
  de Storage; la `service_role` nunca debe exponerse al frontend ni incluirse en variables `VITE_*`.
- El límite de tamaño configurado en Supabase Storage debe permitir al menos 20 MiB, para no
  contradecir `MAX_UPLOAD_SIZE_BYTES=20971520`. El backend sigue validando el límite por tramos;
  el límite de Storage es una segunda barrera.
- Si se configura una lista de MIME types permitidos en el bucket, incluir `text/plain`,
  `application/pdf` y
  `application/vnd.openxmlformats-officedocument.wordprocessingml.document`. La validación principal
  del contrato sigue siendo por extensión (`txt`, `pdf`, `docx`), como indica D7.
- El objeto del `seed.sql` **no existe** en Storage: borrar ese documento con `DELETE` funciona
  porque la purga best-effort tolera el objeto inexistente (siempre que no tenga generaciones).

---

## 9. Pruebas

**Archivo nuevo:** `tests/test_documents_api.py` (patrón de `test_generations_api.py`, helper
`assert_error`).

| # | Caso | Resultado esperado |
|---|---|---|
| 1 | `POST` con `.txt` | `201`, cuerpo = esquema `Document`, sin `storage_path`, presente en el listado y registrado en el fake de Storage |
| 2 | Extensión no permitida (`.png`) | `415 UNSUPPORTED_MEDIA_TYPE` |
| 3 | Tamaño superado (`max_upload_size_bytes` pequeño, p. ej. 64) | `413 PAYLOAD_TOO_LARGE` |
| 4 | Archivo vacío | `400 VALIDATION_ERROR` con `details[0].path == "file"` |
| 5 | Multipart sin campo `file` | `400 VALIDATION_ERROR` |
| 6 | `GET /documents` | Paginación (`limit`/`offset`/`total`), orden `uploaded_at` desc |
| 7 | `GET /documents/{id}` | `200` / `404 DOCUMENT_NOT_FOUND` |
| 8 | `DELETE` sin generaciones | `204`; después `GET` → `404`; `storage.remove` invocado |
| 9 | `DELETE` con generación **activa** | `409 DOCUMENT_IN_USE` + `details.generation_ids`; ni la fila ni el storage se tocan |
| 10 | `DELETE` con solo generaciones **finales** | `409` con mensaje de «asociadas»; nada se borra |
| 11 | `DELETE` inexistente | `404` |
| 12 | `DELETE` tras borrar la generación asociada | `204` (confirma que la regla se libera al eliminar las generaciones) |

**`tests/conftest.py` y `tests/factories.py`:** fixture `storage` (`FakeDocumentStorage`) y paso a
`client_factory(...)` → `create_app(..., documents_storage=storage)`. El `store` existente sigue
sembrando el documento del seed. Usar `add_generation` de `tests/factories.py` para los casos 9, 10
y 12.

**`tests/test_contract.py`:** validar `Document` y `DocumentList` contra `docs/openapi.yaml` en un
upload y en el listado; añadir el `409` de `deleteDocument` al helper de errores.

**Objetivo:** 50 base + ~12 nuevos ≈ 62 passed.

---

## 10. Verificar antes de codificar

1. **Bucket real:** ya se creó `docs_testgen`. Confirmar en Dashboard o con
   `client.storage.list_buckets()` que el ID exacto es `docs_testgen`, que es privado y que permite
   archivos de al menos 20 MiB. Configurar `DOCUMENTS_BUCKET=docs_testgen`; no crear ni usar otro
   bucket `documents` accidentalmente.
2. **Firma de storage en `supabase>=2.10`** (`requirements.txt`): parámetros de `upload`
   (content-type / upsert) y comportamiento de `remove` con claves inexistentes.
3. **Límite de tamaño:** validar durante la lectura por tramos (`max+1` bytes), no con
   `Content-Length`.
4. **FK en `delete`:** confirmar que el `APIError` de Supabase trae el código `23503` para mapearlo
   a `409`.
5. **Paginación:** replicar el manejo del `416` de PostgREST (offset más allá del total).
6. **Rama de trabajo:** el código de la Fase 1.5 vive en `bc0e3b3` (ramas `backend` /
   `generador-backend`); `docs-backend` solo tiene documentación. Confirmar sobre cuál se
   implementa.
7. **Paridad contrato/rutas:** no hay test global que exija que todas las `operationId` estén
   implementadas; las rutas nuevas añaden sus propios tests de contrato.
8. **Checksum:** el ejemplo del contrato muestra 32 caracteres hexadecimales; SHA-256 produce 64.
   El contrato no fija algoritmo ni longitud (`type: string`), por lo que es válido, pero conviene
   confirmarlo.

---

## 11. Documentación afectada

| Archivo | Cambio |
|---|---|
| `docs/openapi.yaml` | Solo la prosa de `deleteDocument` (ver abajo). Los esquemas y respuestas no cambian. |
| `README.md` §4.1 | Las cuatro filas de documentos pasan a implementadas. |
| `README.md` §4.3 | Sustituir «mientras existan generaciones activas» por la regla D3: no se elimina un documento con **ninguna** generación (activa o finalizada); enlazar la decisión 8. |
| `README.md` §9 | Requisito del bucket (`DOCUMENTS_BUCKET`) en «Ejecución local». |
| `README.md` §10 | `Carga de documentos` → Implementado; `Listado y consulta de documentos` → Implementado; `Eliminación de documentos y generaciones` → Parcial (documentos: regla Fase 2; generaciones: ya implementadas). |
| `README.md` «Documentación relacionada» | Corregir enlace roto `docs/database.md` → `docs/prompts_fases/Fase 1/database.md`. |
| `Fase 1/database.md` | §7.8 (decisión 8): registrar la regla D3 y que el soft delete queda como fase futura. Opcional: §7.10 está desactualizada (`recover_interrupted_generations` ya existe en `services/pipeline_runs.py`). |

**Cambio exacto en `openapi.yaml` (`deleteDocument`, descripción):** sustituir

> No se permite mientras existan generaciones activas (`queued` o `running`) que dependan del
> documento. Las políticas de borrado respecto a generaciones ya finalizadas siguen pendientes de
> definición (ver `database.md`, decisión 8).

por algo equivalente a

> Elimina el registro y su archivo en Storage. No se permite si existe alguna generación que
> dependa del documento (activa o finalizada); en ese caso responde `409 DOCUMENT_IN_USE`. Para
> eliminar el documento, primero hay que eliminar sus generaciones. Regla que cierra la decisión 8
> de `database.md`.

Opcional: actualizar la descripción de la respuesta 409 y/o añadir un segundo ejemplo con el
mensaje de «asociadas».

---

## 12. Aclaraciones relacionadas

- **El borrado de generaciones ya existe:** `DELETE /api/v1/generations/{generation_id}`
  (`api/routes/generations.py`, vía la RPC `delete_generation_if_final`) borra la generación y sus
  resultados en cascada; responde `409 GENERATION_IN_PROGRESS` si sigue activa. `DELETE /documents`
  **no** borra generaciones: borra el archivo de entrada.
- **Retención automática** (borrar generaciones con más de X días): no está contemplada en el
  contrato ni en el código; sería una función nueva (tarea programada + política). Fase 3.

---

## 13. Checklist del backend

```bash
# desde backend/ (el venv es .venv)
.venv\Scripts\python -m pytest        # 50 base + nuevos (~62) en verde
```

Manual (con `.env` de Supabase y el bucket privado `docs_testgen` creado y configurado):

1. `curl -F "file=@notas.txt" .../api/v1/documents` → `201` con `Document`, sin `storage_path`; el
   objeto aparece en el bucket y la fila en `documents`.
2. `.png` → `415`. Archivo > 20 MiB → `413`. Multipart sin `file` → `400` (`details path: file`).
3. `GET /documents` → lista paginada por `uploaded_at` desc. `GET /documents/{id}` → `200`; id
   inventado → `404`.
4. `DELETE` de un documento sin generaciones → `204`; repetir → `404`; el objeto desaparece del
   bucket.
5. `DELETE` de un documento con generación activa → `409` con `generation_ids`; con solo
   generaciones finales → `409` con el mensaje de «asociadas».
6. Borrar la generación (`DELETE /generations/{id}`) y reintentar `DELETE /documents/{id}` → `204`.
7. Regresión: `/health` y el formato de error estándar (404 de ruta inexistente) sin cambios.

**Hecho cuando:** los pasos 0-8 del orden de `fase2.md` estén completos y el frontend pueda llamar
a `POST /documents` sin ajustes adicionales.

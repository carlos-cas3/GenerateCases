# Indicaciones — consumo de rutas desde el frontend

Documento único de referencia para conectar el frontend con el backend. **Solo contiene hechos
verificados contra el código** (referencia `archivo:línea`) o contra `docs/openapi.yaml`.
Todo lo que no existe se marca explícitamente como **FALTA DE IMPLEMENTACIÓN** y queda pendiente
de revisión manual: aquí no se diseñan rutas ni código nuevos.

> Estado: Fase 1 del backend verificada en local (conexión a Supabase correcta, flujo completo
> `POST /generations` → polling → `completed`).
> Única vista del frontend en funcionamiento: `GenerationPage`. El resto de features siguen en mocks.

---

## 1. Fuentes de verdad

### 1.1. Implementado hoy en el backend

| Método | Ruta | `operationId` | Ubicación |
|---|---|---|---|
| GET | `/api/v1/health` | `getHealth` | `ai_service/api/routes/health.py:10` |
| POST | `/api/v1/generations` | `createGeneration` (202) | `ai_service/api/routes/generations.py:25` |
| GET | `/api/v1/generations` | `listGenerations` | `ai_service/api/routes/generations.py:39` |
| GET | `/api/v1/generations/{generation_id}` | `getGeneration` | `ai_service/api/routes/generations.py:51` |
| DELETE | `/api/v1/generations/{generation_id}` | `deleteGeneration` (204/409/404) | `ai_service/api/routes/generations.py:62` |
| GET | `/api/v1/generations/{generation_id}/events` | `getGenerationEvents` | `ai_service/api/routes/generations.py:79` — **responde 501** |

Prefijo aplicado en `ai_service/main.py:21,64-65`. Registro central de rutas: solo `health` y
`generations`; no hay ninguna ruta de documentos ni de resultados.

### 1.2. Definido en `docs/openapi.yaml` pero NO implementado

Contrato objetivo con 20 `operationId`; 6 ya tienen ruta en el código (§1.1) y **estos 14 no
existen**:

| Bloque | `operationId` | Línea en `openapi.yaml` |
|---|---|---|
| Documentos | `createDocument` (multipart, 201) | 93 |
| Documentos | `listDocuments` (200) | 135 |
| Documentos | `getDocument` (200/404) | 158 |
| Documentos | `deleteDocument` (204/404/409) | 173 |
| Resultados | `listUserStories` | 400 |
| Resultados | `listRequirements` | 424 |
| Resultados | `listClusters` | 448 |
| Resultados | `listTestCases` | 471 |
| Resultados | `getTestCase` | 501 |
| Resultados | `getTraceability` | 537 |
| Resultados | `updateRequirementTestCaseRelation` (PATCH) | 577 |
| Resultados | `listMetrics` | 623 |
| Resultados | `getMetric` | 653 |
| Resultados | `listFindings` | 687 |

**FALTA DE IMPLEMENTACIÓN:** las cuatro rutas de documentos exigirían crear
`ai_service/api/routes/documents.py` (no existe) apoyándose en
`ai_service/repositories/documents.py` (`SupabaseDocumentsRepository`). El servicio correspondiente
(`ai_service/services/documents.py`) tampoco existe. Decisión pendiente de revisión manual.

### 1.3. Lo que el frontend asuma pero que no existe en ninguna parte

| Uso en el frontend | Referencia | Estado |
|---|---|---|
| Descarga de ejecuciones / `.zip` | `frontend/src/features/history/services/historyService.ts:53` | **No existe ni está especificado** en `openapi.yaml`. No inventar ruta: requiere definir contrato antes. |
| Rutas tipo `/executions/:id`, `/executions/:id/pipeline` | comentarios en `generationService.ts:41` y `historyService.ts:30,51` | **No existen**. El backend expone `/generations`. Decisión adoptada: el frontend se adapta a `/generations`. |

---

## 2. Mapa de consumo de `GenerationPage`

Orden sugerido por prioridad. «Dónde se toca» indica el archivo concreto que hoy contiene el mock.

| # | Acción en la UI | Fuente actual (mock) | Endpoint requerido | ¿Existe en backend? | Dónde se implementa |
|---|---|---|---|---|---|
| 1 | Subir archivo (`.txt`/`.pdf`/`.docx`) | `generationService.startGeneration` — `frontend/src/features/generation/services/generationService.ts:31` | `POST /api/v1/documents` (multipart, `openapi.yaml:90`) | **NO — falta implementar** | Backend: `ai_service/api/routes/documents.py` (inexistente). Frontend: `generationService.ts` |
| 2 | Iniciar la generación | idem (`generationService.ts:31`) | `POST /api/v1/generations` con `document_id` + `configuration` | **SÍ** — `generations.py:25` | Frontend: `generationService.ts` + nuevo cliente HTTP (ver §4) |
| 3 | Progreso de las 7 etapas | `useExecutionProgress` — `frontend/src/features/generation/hooks/useExecutionProgress.ts:10` | `GET /api/v1/generations/{id}` (polling) | **SÍ** — `generations.py:51` | Frontend: `useExecutionProgress.ts` (hoy hace una única carga; `useAsyncData` ya soporta `enabled`) |
| 4 | Ejecuciones recientes | `useRecentExecutions` — `frontend/src/features/generation/hooks/useRecentExecutions.ts:9` | `GET /api/v1/generations?limit=&offset=` | **SÍ** — `generations.py:39` | Frontend: `generationService.listRecentExecutions` (mapeo de tipos, ver §3) |
| 5 | Pipeline de una ejecución concreta | `useExecutionPipeline` — `frontend/src/features/generation/hooks/useExecutionPipeline.ts:14` | `GET /api/v1/generations/{id}` | **SÍ** — `generations.py:51` | Frontend: `generationService.getExecutionPipeline`. **Hoy este hook no se usa en ninguna pantalla** (ver §6) |
| 6 | «Ver detalle» (botón deshabilitado) | `GenerationPage.tsx:61-62` (`TODO: navegar al detalle`) | Estado → `GET /generations/{id}` (existe). Contenido HU/RF/CP → `/user-stories`, `/requirements`, `/test-cases` | Estado: **SÍ**; contenido: **NO — falta implementar** | Frontend: `GenerationPage.tsx` + navegación a `/history/:executionId` (`app/paths.ts:12`). Resultados: backend, §1.2 |
| 7 | Tiempo real (SSE) | sin uso | `GET /api/v1/generations/{id}/events` | Existe pero **501** (`generations.py:79`) | Fase posterior (§5); mientras, polling sobre el punto 3 |
| 8 | Descargar resultados | `historyService.downloadExecutions` — `historyService.ts:53` | — | **No definida** | Pendiente de definición; no implementar sin contrato |
| 9 | Borrar generación (fuera de esta vista) | `historyService.deleteExecutions` — `historyService.ts:44` | `DELETE /api/v1/generations/{id}` | **SÍ** — `generations.py:62` | Frontend: `historyService.ts` (409 `GENERATION_IN_PROGRESS` si sigue activa) |

### 2.1. Obstáculo mínimo para el flujo real

`POST /api/v1/generations` exige un `document_id` válido; si no existe devuelve
`404 DOCUMENT_NOT_FOUND` (`ai_service/services/generations.py:85-86`). Hoy el único documento es
el del `supabase/seed.sql` (`6f9d1c2e-0a4b-4c8d-9e1f-2b3c4d5e6f70`).

- **Opción A (requiere implementar el punto 1):** subir archivo con `POST /documents`.
- **Opción B (sin backend nuevo):** listar documentos ya existentes con `GET /documents` —
  **tampoco está implementada** (§1.2).
- **Opción C (solo para pruebas):** usar el documento del seed.
  **FALTA DE IMPLEMENTACIÓN:** alguna de las opciones A/B debe decidirse y construirse para que
  la `GenerationPage` funcione con archivos reales.

---

## 3. Mapeo obligatorio de contratos

### 3.1. Estados de generación

| Backend (`schemas/generations.py:10-15`) | Frontend (`shared/types.ts:2-6`) |
|---|---|
| `queued` | `pending` |
| `running` | `in_progress` |
| `completed` | `completed` |
| `failed` | `failed` |

Estados activos (siguen moviéndose, toca seguir haciendo polling): `queued`, `running`
(`schemas/generations.py:36-38`).

### 3.2. Estados de etapa

Backend (`schemas/generations.py:17-22`): `pending`, `running`, `completed`, `failed`, `skipped`.
El frontend solo conoce `pending | in_progress | completed | failed` → **`skipped` no tiene
equivalente**: decisión pendiente de revisión manual (mapearlo a `completed`, a `pending` o ampliar
`ExecutionStatus`).

### 3.3. Respuesta de `Generation` (GET/POST)

Campos reales (`schemas/generations.py:98-112`):

```
id, document_id, document_name, status,
configuration { semantic_clustering_enabled, method_type },
stages[7] { key, name, status, error_message, started_at, completed_at, order },
summary,            // SIEMPRE null en Fase 1 (services/generations.py:35)
error_message, created_at, started_at, completed_at
```

Las 7 etapas y sus nombres salen de `ai_service/pipeline/catalog.py:15-23` (`p1` Normalización …
`p7` Evaluación) y `order` va de 1 a 7. **No** hay HU, RF, CP, métricas ni artefactos: todo eso
está en las rutas no implementadas de §1.2. Los tipos UI `RecentExecution` y `ExecutionStage`
(`features/generation/types.ts`) se rellenan a partir de este payload.

### 3.4. Paginación de `GET /generations`

Query: `limit` (1-100, defecto 20), `offset` (≥0), `document_id`, `status`.
Respuesta: `{ items: [Generation], pagination: { limit, offset, total } }`
(`schemas/generations.py:120-124`). Orden: `created_at` descendente.

### 3.5. Errores

Formato siempre `{"error": {"code", "message", "details"}}` (`ai_service/api/errors.py:31-33`).

| Código | HTTP | Cuándo | Origen |
|---|---|---|---|
| `VALIDATION_ERROR` | 400 | cuerpo/query inválido | `api/errors.py:48-49` |
| `DOCUMENT_NOT_FOUND` | 404 | `document_id` inexistente | `core/errors.py:18` |
| `GENERATION_NOT_FOUND` | 404 | id inexistente | `core/errors.py:23` |
| `GENERATION_IN_PROGRESS` | 409 | `DELETE` sobre generación activa | `core/errors.py:28` |
| `NOT_IMPLEMENTED` | 501 | `/events` (SSE) | `core/errors.py:33` |
| `INTERNAL_ERROR` | 500 | error no previsto | `api/errors.py:57` |

El contrato completo de respuestas de error está en `docs/openapi.yaml` (`components.responses`).

---

## 4. Infraestructura que falta en el frontend (FALTA DE IMPLEMENTACIÓN)

Ninguna de estas piezas existe hoy; son requisito previo al punto 2 del §2:

1. **Cliente HTTP base.** No hay ni una llamada `fetch` en todo `frontend/src` (verificado por
   búsqueda). Cada `*Service.ts` usa `delay()` + mocks. Ubicación propuesta a revisar:
   `frontend/src/shared/api/` (el patrón de slices con alias `@/` ya está en
   `frontend/vite.config.ts:10`).
2. **Variable de entorno.** No existe `.env` ni `VITE_API_URL` en `frontend/`, y
   `vite.config.ts` no define proxy ni `define`.
3. **CORS o proxy — decisión manual.** El backend **no** tiene `CORSMiddleware`
   (`ai_service/main.py` solo registra rutas y manejadores de error). Desde Vite en `:5173`
   contra `:8000` el navegador bloqueará la petición. Dos caminos, ambos por construir:
   - añadir CORS al backend (`ai_service/main.py`), o
   - proxy en `frontend/vite.config.ts` y llamar a rutas relativas.
4. **Mapeo de estados y tipos** (§3) en la capa de adaptación de los `*Service.ts`.

---

## 5. Fases siguientes (enunciadas, sin diseñar)

- **Fase B — SSE:** implementar `GET /generations/{id}/events` (hoy 501). Requiere decidir el
  transporte de eventos en el backend (hoy los eventos existen en
  `ai_service/pipeline/events.py` y se consumen persistiendo en
  `ai_service/services/pipeline_runs.py:50`), manejar reconexión y replays, y mantener
  **fallback automático a polling**. Condiciones previas: el frontend ya consumiendo `/generations`
  con polling (puntos 2-4 del §2), para poder validar cualquier cambio de contrato.
- **Fase C — Resultados:** rutas de §1.2 (HU, RF, clusters, casos, trazabilidad, métricas).
- **Fase D — Descargas:** definir contrato antes de tocar `historyService.downloadExecutions`.

---

## 6. Avisos para revisión manual

1. **`.pyc` huérfanos, no confundir con módulos existentes.** Hay restos compilados sin fuente en
   `ai_service/api/routes/__pycache__/` (`documents`, `internal_pipeline_runs`),
   `tests/unit/` y `tests/characterization/`. Corresponden al prototipo de la rama
   `29-doc-OpenAPI-estructura-backend` (commit `728d821 "commit que deberia eliminar"`), que sí
   contenía `routes/documents.py`, `services/documents.py` y clientes LLM/embeddings. En la rama
   actual (`generador-backend`) esos archivos **no existen**.
2. **`useExecutionPipeline` sin uso.** El hook está definido pero ninguna pantalla lo llama; la
   `GenerationPage` solo usa `useExecutionProgress`.
3. **`summary` es siempre `null`** en Fase 1 (`ai_service/services/generations.py:35`): cualquier
   UI que espere conteos HU/RF/CP o métricas no tendrá de dónde leerlos hasta la Fase C.
4. **Documentación desincronizada.** `README.md` §10 mantiene la tabla de estado como
   «Por verificar» y describe rutas de documentos/resultados que aún no existen; `FASE1.md:3017`
   deja el despliegue del esquema en Supabase marcado como pendiente pese a ya estar aplicado.
5. **Contrato de nombres.** Se adopta `/generations` (backend + `openapi.yaml` como fuente de
   verdad). Renombrar los tipos internos `Execution*` → `Generation*` en el frontend es opcional y
   puede hacerse en el mismo paso que la conexión real; hoy solo son comentarios desactualizados
   (`generationService.ts:41`, `historyService.ts:30,51`).
6. **Un solo worker.** La recuperación de arranque asume un proceso único
   (`ai_service/services/pipeline_runs.py:149`, `main.py:47`): no levantar `uvicorn --workers N`.

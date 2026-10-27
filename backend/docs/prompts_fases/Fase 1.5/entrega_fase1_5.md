# Entrega — Fase 1.5 (conectar `GenerationPage` al backend)

Implementación de `fase1_5_pipeline.md` teniendo en cuenta `observaciones_fase1_5_pipeline.md`.
Las rutas del backend son relativas a `backend/` y las del frontend a `frontend/`.

## 1. Verificación automática

| Comando | Resultado |
|---|---|
| `.venv\Scripts\python -m pytest` (desde `backend/`) | **50 passed** (41 de base + 9 nuevas) |
| `npx tsc --noEmit -p tsconfig.app.json` | 0 errores |
| `npx eslint .` | 0 problemas |
| `npm run build` | OK (el aviso de chunk > 500 kB ya existía) |
| `python check_docs.py docs` | **No ejecutado**: el script no está en el repositorio |

> El entorno virtual es `backend/.venv` (no `venv` como dice el plan).

## 2. Puntos a verificar (§11 del plan): resultado

| # | Punto | Resultado |
|---|---|---|
| 1 | `p7` en `skipped` en una generación completada | **Sí.** Lo confirman `__fixtures__/generation-completed-*.json`. Con fallo en `p4`, `p5`–`p7` quedan en `pending` (no `skipped`). Las etapas omitidas llegan con `error_message: null`: la API **no expone motivo**, así que la UI solo muestra «Omitida» (B7/B8). |
| 2 | Consumidores de `stageDefinitions`, `buildMockStages`, `MOCK_RECENT_EXECUTIONS` | `stageDefinitions` y `buildMockStages` los usa `getExecutionPipeline` (detalle de historial) → **se conservan**. `MOCK_RECENT_EXECUTIONS` no tenía otros consumidores → **eliminado**. |
| 3 | `ExecutionStage.status: StageStatus` rompe `features/history` | No. `history` no se tocó y compila. |
| 4 | Campos sin origen en `Generation` | Ninguno de `RecentExecution`. En `ExecutionStage`, `summary` sale del catálogo de presentación (`utils/stageUi.ts`) y `details` del `error_message` de la etapa. No se muestran conteos HU/RF/CP (`summary` es `null`). |
| 5 | `StatusChip`/`StatusIcon` usados con estado de generación | Sí (historial y comparación). Se tipan con `StageStatus` (superconjunto de `ExecutionStatus`), sin cambios en los llamadores. |
| 6 | Raíz del backend y `check_docs.py` | La raíz es `backend/`; `check_docs.py` no existe. |
| 7 | Comandos reales | Los de la tabla §1. Vitest no está en el proyecto (ver §4). |

Además se verificó (§5.5) que `PIPELINE_STUB_DELAY_SECONDS` y `PIPELINE_STUB_FAIL_AT_STAGE` están en `.env.example`.

## 3. Cambios por zona

### Backend

| Archivo | Cambio |
|---|---|
| `ai_service/api/errors.py` | Manejador de `starlette.exceptions.HTTPException`: 404 `NOT_FOUND`, 405 `METHOD_NOT_ALLOWED` (con `Allow`), otros `HTTP_ERROR`. Conserva status y cabeceras. Los errores de dominio (`AppError`) siguen con su manejador propio. |
| `ai_service/config.py` | `frontend_origins` desde `FRONTEND_ORIGINS` (lista separada por comas; rechaza `*`). Default solo de desarrollo: `http://localhost:5173`, `http://127.0.0.1:5173`. |
| `ai_service/main.py` | `CORSMiddleware`: orígenes configurados, métodos `GET/POST/DELETE`, cabecera `Content-Type`, `allow_credentials=False`. |
| `.env.example` | `FRONTEND_ORIGINS` documentado. |
| `tests/test_http_errors_and_cors.py` | 404/405 estándar, errores de dominio intactos, preflight permitido/no permitido, configuración por entorno y rechazo de `*`. |
| `README.md`, `docs/openapi.yaml` | Códigos `NOT_FOUND` y `METHOD_NOT_ALLOWED`; `HTTP_ERROR` en prosa. |

No se tocaron servicios, repositorios, pipeline, esquemas ni `supabase/`.

### Frontend

| Archivo | Cambio |
|---|---|
| `.env.example`, `.env` (ignorado), `.gitignore` | `VITE_API_URL`, `VITE_DEV_DOCUMENT_ID`; `.env` ignorado. |
| `vite.config.ts` | Proxy de desarrollo `/api` → `http://127.0.0.1:8000`. **Desviación del plan**: con `localhost` Node resuelve `::1` y uvicorn (IPv4) rechaza la conexión (502, verificado). |
| `src/vite-env.d.ts` | Tipos de las variables `VITE_*`. |
| `src/shared/api/` | `request<T>()`, `ApiError` (`NETWORK_ERROR`, `UNEXPECTED_RESPONSE`), tolera `{detail}` y respuestas no JSON; `AbortError` se relanza sin envolver. |
| `src/shared/hooks/useAsyncData.ts` | `load(signal)` con aborto real, filtro de `AbortError`, `refreshInterval` (número o función), temporizador encadenado, 3 reintentos (2/4/8 s) solo ante errores transitorios del polling conservando datos (`isReconnecting`), recarga al volver a la pestaña, `errorCause`. Los llamadores de historial/métricas no cambian. |
| `src/shared/types.ts`, `src/shared/components/*` | `StageStatus = ExecutionStatus \| 'skipped'`; `STAGE_STATUS_CONFIG` con «Omitida»; icono propio para `skipped`. |
| `features/generation/services/` | `generationDto.ts` (contrato crudo), `generationMappers.ts` (puros), `generationService.ts` real (`startGeneration`, `getGeneration`, `listRecentExecutions`). `getExecutionPipeline` sigue con mocks. |
| `features/generation/hooks/` | `useActiveGenerationId` (nuevo), `useExecutionProgress(id)`, `useRecentExecutions`, `useStartGeneration` con mensajes por código. |
| `features/generation/components/` | `ExecutionProgressCard`: B1/B2 (`skipped` cuenta como final; «N completadas · M omitidas de T etapas»), aviso de reconexión, error global, nombre del documento, etapa fallida expandida. `DocumentUploadCard`: aviso visible y `submitDisabled`. |
| `features/generation/utils/` | `stageUi.ts` (solo descripciones por `key`; el nombre sale de la API), `stageProgress.ts`. |
| `features/generation/pages/GenerationPage.tsx` | Rehidratación por `?g=`, «Ver detalles» retoma el seguimiento, «Iniciar» bloqueado mientras la generación seguida está activa. |
| `features/generation/__fixtures__/` | JSON reales del §6.1. |

`features/history`, `features/metrics` y `features/comparison` no se modificaron.

## 4. Decisiones aplicadas de las observaciones

| Observación | Decisión |
|---|---|
| 1. P7 | No es criterio de aceptación. La UI no lo trata de forma especial: muestra el estado que llega. |
| 2. Recuperación | `?g=<uuid>` es un identificador técnico en la URL; al usuario se le muestra el **nombre del documento**. Sin `?g=`, se retoma la activa más reciente de la lista ya cargada (una sola) y se fija en la URL. |
| 3. Una sola generación activa | Regla de interfaz (botón deshabilitado + guarda anti doble clic). No es una garantía del backend. |
| 4. Reinicio del backend | Ya implementado en la Fase 1 (`recover_interrupted_generations`). El mensaje real es «Ejecución interrumpida por reinicio del servicio.» (no el texto de ejemplo de la observación); la UI lo muestra como error global. |
| 5. Polling | 2 s mientras `queued`/`running`; 3 reintentos acotados solo para red/5xx; un error de consulta nunca pasa la generación a `failed`. |
| 6. Manejadores | Se añadió solo el de `HTTPException` (404/405 devolvían `{"detail": ...}`); los códigos de dominio se mantienen (probado). |
| 7. Vitest | **No se incorporó** (no forma parte del proyecto). Las pruebas del §6.10 quedan como tarea de una fase específica de pruebas del frontend; mientras tanto se cubren con el checklist manual. |

### Otras desviaciones menores

- `useExecutionProgress` usa `keepPreviousData: false`: al cambiar de generación no se muestran las etapas de la anterior. Durante el polling de una misma generación los datos se conservan igualmente.
- Las recientes se recargan cuando la generación seguida está en estado final y la lista aún muestra otro estado para ella (cubre también el caso de que la primera consulta ya llegue en estado final).
- `stageUi.ts` no define iconos por etapa: la fila ya usa el icono del estado.

## 5. Checklist manual (§8.2)

Se ejecutó con el backend real (repositorios en memoria, sin Supabase), `vite dev` y Chrome headless.

| # | Caso | Estado |
|---|---|---|
| 1 | `GET /api/v1/health` por el proxy | ✅ |
| 2 | Ruta inexistente → formato estándar | ✅ |
| 3 | Estado vacío sin «sube un documento» | ✅ |
| 4 | Camino feliz | ✅ estados de la API, polling hasta el final |
| 5 | Clustering desactivado → `p3`, `p4`, `p7` «Omitida», 100 % | ✅ |
| 6 | Fallo en `p4` → error global + error de etapa; `p5`–`p7` «Pendiente» | ✅ |
| 7 | Recarga con `?g=` / recuperación sin `?g=` | ✅ |
| 8 | `?g=abc` y `?g=<uuid inexistente>` → se limpia con aviso | ✅ |
| 9 | Backend caído durante el polling → «Reconectando…» | ⏳ pendiente (manual en navegador) |
| 10 | Reinicio del backend a mitad → `failed` con motivo | ⏳ requiere Supabase (cubierto en backend por `tests/test_recovery.py`) |
| 11 | Doble clic en «Iniciar» | ⏳ pendiente (manual) |
| 12 | Cambio de pestaña sin error falso ni peticiones solapadas | ⏳ pendiente (manual) |
| 13 | Aviso de documento de prueba visible | ✅; sin `VITE_DEV_DOCUMENT_ID` ⏳ pendiente |
| 14 | `/history`, métricas y comparación con mocks | ✅ compilan; ⏳ revisión visual pendiente |

## 6. Cómo probar en local

```bash
# backend/
.venv\Scripts\python -m uvicorn ai_service.main:app --port 8000   # requiere .env con Supabase y seed aplicado
# PIPELINE_STUB_DELAY_SECONDS=0 en .env para generaciones instantáneas; =2 para ver el polling

# frontend/
cp .env.example .env
npm run dev   # http://localhost:5173 (las llamadas a /api pasan por el proxy)
```

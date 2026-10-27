# Orquestación interna del pipeline

## 1. Propósito

Este documento describe cómo se coordina la generación de casos de prueba funcionales dentro del backend de TestGen: qué hace cada etapa P1–P7, qué datos consume y produce, en qué tablas persiste y cómo se registran los estados y los errores.

El backend es una **única aplicación Python con FastAPI**. La API pública, los casos de uso, la persistencia en Supabase y la ejecución del pipeline viven en el mismo proceso; no existe ningún otro servicio backend con el que comunicarse. El progreso se publica únicamente a través del estado persistido en Supabase, que el cliente consulta con `GET /api/v1/generations/{generation_id}`.

## 2. Componentes y responsabilidades

| Componente | Ubicación | Responsabilidad |
|---|---|---|
| Controlador HTTP | `ai_service/api/routes/generations.py` | Valida la solicitud HTTP, llama al servicio y devuelve la respuesta. |
| Servicio de generaciones | `ai_service/services/generations.py` | Comprueba el documento, crea la generación y sus etapas, programa el trabajo y coordina el acceso a los repositorios. |
| Servicio de ejecución del pipeline | `ai_service/services/pipeline_runs.py` | Adapta una generación persistida a una ejecución del pipeline, recibe los eventos internos y los traduce en escrituras de estado. Puede consolidarse con el servicio de generaciones si el diseño real lo justifica. |
| Orquestador | `ai_service/pipeline/orchestrator.py` | Ejecuta P1–P7 en orden, decide qué etapas se omiten y emite eventos internos de progreso. |
| Contexto del pipeline | `ai_service/pipeline/context.py` | Contenedor tipado con los datos compartidos entre etapas durante una ejecución. |
| Etapas | `ai_service/pipeline/stages/` (`base.py`, `p1_normalize.py` … `p7_evaluation.py`) | Procesamiento específico de cada fase. Todas implementan la interfaz de `base.py`. |
| Repositorios | `ai_service/repositories/` | Leen y escriben en Supabase documentos, generaciones, etapas y resultados. |
| Clientes | `ai_service/clients/` | Encapsulan Supabase (PostgreSQL y Storage), LLM, embeddings y otras dependencias externas. |

Las rutas no contienen reglas de negocio ni consultan Supabase. El orquestador y las etapas no dependen de objetos HTTP ni de FastAPI, y no acceden a Supabase directamente: persisten mediante los repositorios que les proporciona el servicio de ejecución.

## 3. Catálogo de etapas

El nombre visible de cada etapa se define en un catálogo dentro del código y se expone en la API; en base de datos solo se guarda `stage_key`.

| Clave | Nombre | Entrada | Salida | Persistencia (`database.md`) | Se omite (`skipped`) cuando |
|---|---|---|---|---|---|
| `p1` | Normalización de historias de usuario | Texto del documento | Historias estructuradas (código, texto original, rol, acción, objetivo) | `user_stories` | Nunca |
| `p2` | Extracción de requisitos funcionales | Historias de P1 | Requisitos funcionales y su relación con las historias | `functional_requirements`, `user_story_requirements` | Nunca |
| `p3` | Generación de embeddings | Requisitos de P2 | Vectores en el contexto del pipeline | Ninguna por ahora (decisión pendiente 4) | `semantic_clustering_enabled = false` |
| `p4` | Clustering semántico | Embeddings de P3 | Grupos y pertenencia de requisitos | `clusters`, `cluster_requirements` | `semantic_clustering_enabled = false` |
| `p5` | Construcción de contexto estructurado | Historias, requisitos y, si existen, grupos | Contexto de entrada para la generación | Ninguna (se reconstruye desde las tablas) | Nunca |
| `p6` | Generación de casos de prueba funcionales | Contexto de P5 | Casos, pasos y relaciones RF–CP propuestas | `test_cases`, `test_steps`, `requirement_test_cases` (relaciones en `pending`) | Nunca |
| `p7` | Evaluación de resultados | Requisitos, casos y relaciones | Métricas y hallazgos | `generation_metrics`, `metric_findings` | Mientras P7 no esté implementada |

Reglas que se derivan del catálogo:

- **Sin clustering, el pipeline continúa.** Con P3 y P4 omitidas, P5 y P6 trabajan con todos los requisitos sin agrupar. Ninguna etapa posterior puede exigir grupos.
- **Agrupar no es cubrir.** P4 solo registra la pertenencia de un requisito a un grupo. La cobertura se establece únicamente mediante relaciones RF–CP.
- **Las relaciones RF–CP que crea P6 nacen en `pending`.** Que el LLM proponga una relación no demuestra cobertura; solo las relaciones `validated` cuentan como cobertura confirmada. El mecanismo de validación está pendiente (decisión 2 de `database.md`); `PATCH /api/v1/generations/{generation_id}/requirements/{requirement_id}/test-cases/{test_case_id}` es la ruta propuesta para registrarla.
- **Aislamiento por ejecución.** Todo registro creado por una etapa lleva el `generation_id` de la ejecución; las claves foráneas compuestas impiden relacionar registros de ejecuciones distintas.
- **Persistencia por etapa.** Cada etapa persiste su salida en una sola operación (transacción o función RPC) antes de marcarse `completed`. Si la etapa falla, no deben quedar resultados parciales suyos en las tablas.
- **Orden de escritura.** El orden P1→P7 respeta las dependencias entre tablas: historias y requisitos existen antes de sus relaciones, y casos y requisitos existen antes de `requirement_test_cases`.

## 4. Flujo de creación y ejecución

1. El cliente envía `POST /api/v1/generations` con `document_id` y la configuración.
2. FastAPI valida el cuerpo de la solicitud (`400 VALIDATION_ERROR` si es inválido).
3. `GenerationsService` verifica que el documento exista (`404 DOCUMENT_NOT_FOUND` si no).
4. El servicio crea en Supabase la generación en estado `queued` y sus siete registros de `generation_stages` en estado `pending`. La configuración se guarda en `clustering_enabled`, `method_type` y `config_snapshot`.
5. El servicio programa la ejecución asíncrona del pipeline y responde `202 Accepted` con la generación.
6. `pipeline_runs` marca la generación como `running` y registra `started_at`.
7. El orquestador recorre P1–P7. Antes de cada etapa se persiste su inicio; al terminar, se persisten sus resultados y su estado final.
8. Al terminar P7 (o su omisión), la generación pasa a `completed`. Si una etapa falla, se registra el error y la generación pasa a `failed`.
9. El cliente consulta `GET /api/v1/generations/{generation_id}` para obtener estado, etapas, error y `summary`, y después las rutas de resultados, trazabilidad y métricas.

La creación de la generación y de sus etapas debe ser atómica (transacción o función RPC): no debe existir una generación sin sus siete etapas.

## 5. Estados y transiciones

**Generación:** `queued`, `running`, `completed`, `failed`.
**Etapa:** `pending`, `running`, `completed`, `failed`, `skipped`.

| Evento | Efecto en la etapa | Efecto en la generación |
|---|---|---|
| `pipeline_started` (implícito al iniciar) | — | `queued` → `running`; se registra `started_at`. |
| `stage_started` | `pending` → `running`; se registra `started_at`. | — |
| `stage_completed` | `running` → `completed`; se registra `completed_at`. | — |
| `stage_skipped` | `pending` → `skipped`; se registra `completed_at`. | — |
| `stage_failed` | `running` → `failed`; se guarda `error_message` y `completed_at`. | Se guarda su `error_message` (mensaje seguro para el cliente). |
| `pipeline_completed` | — | `running` → `completed`; se registra `completed_at`. |
| `pipeline_failed` | — | `queued` o `running` → `failed`; se registra `completed_at`. |

Reglas:

- Una generación pasa a `completed` solo cuando las siete etapas están en `completed` o `skipped`.
- Si una etapa falla, las etapas posteriores **permanecen en `pending`**: no se marcan `skipped`, porque `skipped` se reserva para etapas omitidas por una condición del flujo (clustering deshabilitado, P7 no implementada). La generación termina en `failed`.
- `completed_at` de la generación se registra al alcanzar cualquier estado final, sea `completed` o `failed`.
- `completed` y `failed` son estados finales: no se reanudan ni se reabren. Reintentar significa crear una nueva generación.
- Un estado solo se considera registrado cuando su escritura en Supabase tuvo éxito. Si la escritura falla, el servicio lo trata como error explícito y no continúa asumiendo que la etapa quedó registrada.

## 6. Eventos internos

Los eventos son un mecanismo interno de coordinación (modelos Pydantic o estructuras tipadas), no mensajes HTTP. El orquestador los emite mediante una interfaz de progreso que le entrega `pipeline_runs`; ese servicio aplica la tabla de la sección 5 a través de los repositorios.

- Eventos de etapa: `stage_started`, `stage_completed`, `stage_skipped`, `stage_failed`.
- Eventos de ejecución: `pipeline_completed`, `pipeline_failed`.

El orquestador no conoce Supabase ni FastAPI; solo emite eventos y recibe de `pipeline_runs` los repositorios y clientes que necesita.

## 7. Manejo de errores

| Situación | Resultado |
|---|---|
| El documento no existe | `404 DOCUMENT_NOT_FOUND`; no se crea ninguna generación. |
| Falla la comprobación previa de las dependencias de IA (LLM o embeddings) al programar la ejecución | La generación queda registrada como `failed` con su `error_message` y se responde `503 AI_SERVICE_UNAVAILABLE` con `details.generation_id`. |
| Falla una etapa | La etapa queda `failed` con su `error_message`; las posteriores quedan `pending`; la generación termina `failed`. |
| Error inesperado | Se registra mediante logging con `generation_id` y `stage_key`; al cliente solo se le entrega un mensaje seguro (`INTERNAL_ERROR` si ocurre durante una petición HTTP). |
| Falla al persistir un estado | Se trata como error explícito (ver sección 5) y se registra en el log. |

Los mensajes guardados en `error_message` y devueltos por la API no deben incluir trazas internas, credenciales ni datos sensibles. El detalle técnico va únicamente al log.

## 8. Ejecución asíncrona, concurrencia y durabilidad

- **Prototipo.** Una tarea dentro del proceso de FastAPI (por ejemplo, `BackgroundTasks` o `asyncio`) permite conservar `202 Accepted` y que el frontend consulte con polling. No es durable: si el proceso se reinicia, la tarea en curso se pierde.
- **No bloquear el servidor.** Las llamadas a LLM, embeddings y clustering son costosas. Deben ejecutarse con clientes asíncronos o en un hilo/proceso de trabajo, de modo que no bloqueen el bucle de eventos que atiende las peticiones.
- **Ejecuciones interrumpidas.** Al arrancar la aplicación, las generaciones que sigan en `queued` o `running` y no pertenezcan a una ejecución viva deben marcarse como `failed` (con la etapa en curso también `failed`) y un mensaje indicando que la ejecución fue interrumpida. Así el cliente no queda esperando indefinidamente.
- **Concurrencia.** Si se limita a una generación activa, la regla debe aplicarse de forma persistente y segura (por ejemplo, con una restricción en base de datos o una función RPC), no con una variable en memoria. Este límite y su código de error HTTP están pendientes de definición.
- **Durabilidad.** Si se requieren reintentos y recuperación garantizada, se incorporará más adelante una cola de trabajos con un worker dedicado, también en Python.
- **SSE.** `GET /api/v1/generations/{generation_id}/events` permanece reservado y responde `501 NOT_IMPLEMENTED` hasta que exista una implementación real.

## 9. Límites entre capas

- **API/rutas:** HTTP, validación de entrada y códigos de respuesta.
- **Servicios:** casos de uso, reglas de negocio, transiciones de estado y persistencia a través de repositorios.
- **Repositorios:** lectura y escritura de datos.
- **Orquestador:** secuencia de P1–P7, omisión de etapas y emisión de eventos.
- **Etapas:** procesamiento específico de cada fase.
- **Clientes:** integración técnica con Supabase, LLM y embeddings.

El pipeline no se acopla a FastAPI ni al frontend.

## 10. Decisiones pendientes específicas del pipeline

Complementan las de `database.md`, sección 7:

1. **P7 sin implementar:** se registra como `skipped` y no persiste métricas. Al implementarla, debe pasar a ejecutarse siempre.
2. **Redundancia semántica con P3 omitida:** esa métrica necesita embeddings. Debe decidirse si P7 calcula los suyos o si registra la métrica sin valor.
3. **Persistencia de embeddings:** hoy P3 los deja solo en el contexto de la ejecución.
4. **Límite de concurrencia:** número de generaciones activas permitidas y su contrato de error.
5. **Mecanismo de validación RF–CP:** qué valida una relación y quién (ver decisión 2 de `database.md`).

## 11. Código heredado

Si el repositorio conserva código de una integración anterior con otro backend (por ejemplo, `clients/express.py` o `api/routes/internal_pipeline_runs.py`), debe eliminarse una vez que sus responsabilidades estén cubiertas por los servicios Python descritos aquí. Los tipos de eventos pueden conservarse como tipos internos.

## 12. Documentación relacionada

- `docs/openapi.yaml`: contrato HTTP público.
- `docs/database.md`: modelo de datos y decisiones pendientes.
- `supabase/schema.sql`: tablas, relaciones e índices desplegables.
- `README.md`: arquitectura general, estructura del proyecto y ejecución local.

Este documento describe la coordinación interna del pipeline; no sustituye el contrato OpenAPI público.

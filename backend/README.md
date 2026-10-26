# TestGen Backend

Backend de TestGen para la gestión de documentos, la generación automática de casos de prueba funcionales y la ejecución del pipeline inteligente P1–P7.

El backend se desarrolla en **Python con FastAPI** y utiliza **Supabase**, que proporciona PostgreSQL como base de datos y Supabase Storage para el almacenamiento de archivos. Forma parte de un monorepo que contiene el frontend y el backend en directorios independientes.

> **Arquitectura objetivo:** implementar un backend unificado con FastAPI, organizado mediante una arquitectura por capas inspirada en el patrón Controller–Service–Repository. El frontend, desarrollado con React y TypeScript, consume la API REST del backend sin acceder directamente a las operaciones privilegiadas de persistencia.

> **Estado de la documentación:** este README describe la arquitectura y el contrato objetivo. Una ruta, etapa o tabla documentada no debe considerarse implementada hasta verificarla en el código y en el esquema de Supabase.

## 1. Objetivos y responsabilidades

El backend se encarga de:

- Exponer la API REST bajo el prefijo `/api/v1`.
- Validar los datos de entrada y salida mediante esquemas Pydantic.
- Gestionar la carga, validación, consulta y almacenamiento de documentos.
- Crear y consultar las generaciones de casos de prueba funcionales.
- Coordinar el pipeline P1–P7 y registrar el estado de cada etapa.
- Persistir en Supabase los documentos, las generaciones, las etapas, los resultados y los errores.
- Integrar modelos de lenguaje (LLM), modelos de embeddings y técnicas de clustering semántico mediante componentes especializados.
- Permitir el uso de un proveedor LLM externo o de un modelo local, por ejemplo, mediante Ollama, según la configuración efectiva del proyecto.
- Generar embeddings mediante un componente encapsulado para facilitar su uso en el pipeline.
- Publicar la documentación OpenAPI a partir de las rutas y los esquemas implementados.

### 1.1. Persistencia y almacenamiento

Supabase se utiliza como servicio externo de persistencia y almacenamiento:

- **Supabase PostgreSQL:** almacena los metadatos de documentos, generaciones, etapas y resultados del pipeline.
- **Supabase Storage:** almacena los archivos originales que se procesan durante la generación.

Las solicitudes del frontend pasan por FastAPI. El backend valida los datos, aplica las reglas de negocio y coordina las operaciones con Supabase. Las credenciales privilegiadas deben permanecer exclusivamente en el servidor.

## 2. Arquitectura

Se utiliza una **arquitectura por capas**, inspirada en el patrón **Controller–Service–Repository**. Las funciones de ruta de FastAPI actúan como controladores HTTP; los servicios coordinan los casos de uso y las reglas de negocio; los repositorios encapsulan el acceso a los datos.

```text
Cliente React
     |
     v
API / Presentación
(FastAPI routes: HTTP y validación de entrada)
     |
     v
Servicios
(casos de uso, reglas de negocio y coordinación)
     |
     +---------------------+
     |                     |
     v                     v
Repositorios           Pipeline
(persistencia)         (P1–P7 y orquestación)
     |                     |
     v                     v
Supabase              Clientes de IA
(PostgreSQL/Storage)   (LLM, embeddings, etc.)
```

### 2.1. Capa de presentación: API / Controllers

**Ubicación:** `ai_service/api/routes/`

Responsabilidades:

- Definir los endpoints HTTP y sus métodos.
- Recibir parámetros de ruta, query, formularios y cuerpos JSON.
- Validar y serializar datos mediante esquemas Pydantic.
- Invocar los servicios correspondientes.
- Traducir resultados a códigos HTTP y modelos de respuesta.
- Aplicar dependencias transversales, como paginación y autenticación cuando corresponda.

Las rutas no deben contener reglas de negocio ni consultas directas a Supabase. Si el número de endpoints crece, `routes/` puede renombrarse a `controllers/`, manteniendo la misma separación de responsabilidades.

### 2.2. Capa de servicios

**Ubicación:** `ai_service/services/`

Responsabilidades:

- Implementar casos de uso, como registrar un documento o iniciar una generación.
- Aplicar reglas de negocio y coordinar validaciones entre entidades.
- Coordinar repositorios, clientes externos y pipeline.
- Gestionar los estados de generación y las transiciones de las etapas.
- Traducir errores de infraestructura a errores de aplicación.

Los servicios no deben depender de objetos HTTP específicos (`Request`, `Response`) ni construir respuestas HTTP. Deben trabajar con modelos y excepciones de aplicación.

### 2.3. Capa de repositorios

**Ubicación:** `ai_service/repositories/`

Responsabilidades:

- Encapsular las operaciones de lectura y escritura sobre Supabase.
- Consultar, insertar y actualizar documentos, generaciones, etapas y resultados.
- Aplicar filtros, ordenamiento y paginación.
- Evitar que las consultas a la base de datos se dispersen por controladores o servicios.

Los servicios deciden **cuándo** se realiza una operación; el repositorio define **cómo** se persisten o recuperan los datos.

### 2.4. Clientes e infraestructura

**Ubicación:** `ai_service/clients/`

Responsabilidades:

- Encapsular integraciones con Supabase Storage, modelos LLM, embeddings y otros sistemas externos.
- Centralizar la configuración técnica de esas integraciones.
- Evitar que las bibliotecas específicas de cada proveedor se propaguen por las demás capas.

Los clientes no deben contener la lógica completa de los casos de uso. Por ejemplo, un cliente de Supabase puede cargar un archivo, mientras que el servicio de documentos valida la operación y coordina la carga con el registro de metadatos.

### 2.5. Pipeline de generación

**Ubicación:** `ai_service/pipeline/`

El pipeline implementa la secuencia P1–P7. El orquestador coordina las etapas:

1. **P1 — Normalización:** normaliza el contenido de las historias de usuario.
2. **P2 — Extracción de requisitos:** obtiene requisitos funcionales con apoyo de un LLM.
3. **P3 — Embeddings:** representa semánticamente los artefactos de texto.
4. **P4 — Clustering semántico:** agrupa requisitos semánticamente relacionados cuando está habilitado.
5. **P5 — Contexto estructurado:** prepara el contexto que consumirá la generación.
6. **P6 — Generación:** genera casos de prueba funcionales.
7. **P7 — Evaluación:** calcula o consolida métricas de evaluación, cuando esta etapa esté implementada.

El pipeline no debe exponer endpoints ni dispersar consultas directas a la base de datos. Se integra con servicios y clientes mediante interfaces explícitas. Una etapa `stub` o pendiente no debe describirse como funcional hasta completar su implementación.

Cuando `semantic_clustering_enabled` sea `false`, P3 y P4 se registran como `skipped` y el pipeline continúa con P5 y P6 sin grupos semánticos. Mientras P7 no esté implementada, también se registra como `skipped` y no persiste métricas. El detalle de entradas, salidas y tablas que escribe cada etapa se describe en `docs/pipeline-orchestration.md`.

### 2.6. Esquemas, configuración y errores

- `schemas/`: modelos Pydantic de entrada, salida y datos internos.
- `core/config.py`: configuración y variables de entorno.
- `core/errors.py` y `api/errors.py`: errores de aplicación y conversión centralizada a respuestas HTTP.
- `core/logging.py`: configuración de logging.
- `api/deps.py`: dependencias HTTP reutilizables, por ejemplo, paginación.

Los esquemas de transporte no deberían convertirse en contenedores de lógica de negocio. Cuando un modelo HTTP y un modelo interno tengan responsabilidades distintas, deben mantenerse separados.

## 3. Estructura del proyecto

La siguiente estructura representa una organización objetivo. Debe ajustarse al árbol real del repositorio; los módulos listados no implican que todos existan todavía.

```text
backend/
├── ai_service/
│   ├── main.py
│   ├── api/
│   │   ├── deps.py
│   │   ├── errors.py
│   │   └── routes/
│   │       ├── health.py
│   │       ├── documents.py
│   │       ├── generations.py
│   │       ├── user_stories.py
│   │       ├── requirements.py
│   │       ├── clusters.py
│   │       ├── test_cases.py
│   │       ├── traceability.py
│   │       └── metrics.py
│   ├── schemas/
│   ├── services/
│   ├── repositories/
│   ├── clients/
│   ├── pipeline/
│   │   ├── context.py
│   │   ├── orchestrator.py
│   │   └── stages/
│   │       ├── base.py
│   │       ├── p1_normalize.py
│   │       ├── p2_requirements.py
│   │       ├── p3_embeddings.py
│   │       ├── p4_clustering.py
│   │       ├── p5_context.py
│   │       ├── p6_generation.py
│   │       └── p7_evaluation.py
│   └── core/
│       ├── config.py
│       ├── errors.py
│       ├── logging.py
│       └── security.py
├── docs/
│   ├── openapi.yaml
│   ├── pipeline-orchestration.md
│   └── database.md
└── supabase/
    └── schema.sql
```

La estructura separa la API, los casos de uso, la persistencia y el procesamiento de IA para facilitar el mantenimiento y la evolución del sistema.

## 4. API REST

La API pública utiliza el prefijo `/api/v1`. FastAPI expone la documentación interactiva en `/docs` y el esquema OpenAPI en `/openapi.json`, según la configuración de la aplicación.

### 4.1. Endpoints de documentos y generaciones

Estos endpoints constituyen el contrato inicial. Su estado real debe comprobarse en el código.

| Método | Endpoint | Responsabilidad |
|---|---|---|
| `GET` | `/api/v1/health` | Comprobar el estado del servicio. |
| `POST` | `/api/v1/documents` | Subir un documento mediante `multipart/form-data`, utilizando el campo `file`. |
| `GET` | `/api/v1/documents` | Listar documentos con paginación. |
| `GET` | `/api/v1/documents/{document_id}` | Consultar metadatos y estado de un documento. |
| `DELETE` | `/api/v1/documents/{document_id}` | Eliminar un documento y gestionar su archivo asociado. |
| `POST` | `/api/v1/generations` | Crear una generación para un documento existente. |
| `GET` | `/api/v1/generations` | Listar generaciones con paginación. |
| `GET` | `/api/v1/generations/{generation_id}` | Consultar estado, etapas, errores y resumen de una generación. |
| `DELETE` | `/api/v1/generations/{generation_id}` | Eliminar una generación y sus datos dependientes, si está habilitado. |
| `GET` | `/api/v1/generations/{generation_id}/events` | Endpoint reservado para eventos SSE; puede responder `501 Not Implemented` hasta implementarse. |

### 4.2. Endpoints de resultados

Se proponen las siguientes rutas para que el frontend consulte los resultados persistidos. Son parte del contrato objetivo y no deben considerarse implementadas sin verificar el código.

| Método | Endpoint | Responsabilidad |
|---|---|---|
| `GET` | `/api/v1/generations/{generation_id}/user-stories` | Listar historias de usuario procesadas. |
| `GET` | `/api/v1/generations/{generation_id}/requirements` | Listar requisitos funcionales extraídos. |
| `GET` | `/api/v1/generations/{generation_id}/clusters` | Consultar grupos semánticos y sus requisitos. |
| `GET` | `/api/v1/generations/{generation_id}/test-cases` | Listar casos de prueba generados. |
| `GET` | `/api/v1/generations/{generation_id}/test-cases/{test_case_id}` | Consultar un caso de prueba con sus pasos. |
| `GET` | `/api/v1/generations/{generation_id}/traceability` | Consultar relaciones HU–RF–CP. |
| `GET` | `/api/v1/generations/{generation_id}/metrics` | Consultar métricas almacenadas para la ejecución. |
| `GET` | `/api/v1/generations/{generation_id}/metrics/{metric_name}` | Consultar el detalle de una métrica. |
| `GET` | `/api/v1/generations/{generation_id}/findings` | Consultar hallazgos de evaluación. |
| `PATCH` | `/api/v1/generations/{generation_id}/requirements/{requirement_id}/test-cases/{test_case_id}` | Validar o rechazar una relación RF–CP (propuesto). |

No se necesita crear un endpoint por cada tabla. Una ruta puede consultar varias tablas relacionadas y devolver un objeto de respuesta preparado para la interfaz. Por ejemplo, `clusters` puede combinar los grupos con los requisitos asociados; `traceability` puede integrar historias, requisitos y casos de prueba.

### 4.3. Consideraciones de la API

- **Eliminación de documentos:** no se debe eliminar un documento mientras existan generaciones activas que dependan de él (`409 DOCUMENT_IN_USE`). También se debe gestionar la eliminación del archivo en Storage.
- **Eliminación de generaciones:** deben eliminarse o gestionarse adecuadamente los registros dependientes, según las políticas de retención definidas.
- **Independencia de los recursos:** eliminar una generación no debe eliminar automáticamente el documento original, ya que puede utilizarse en otras generaciones.
- **Ejecuciones activas:** no se debe eliminar una generación mientras se encuentra en cola o en procesamiento (`409 GENERATION_IN_PROGRESS`). La cancelación puede incorporarse como una operación independiente.
- **Resultados parciales:** las rutas de resultados devuelven lo que esté persistido. Si la generación no ha terminado o el clustering está deshabilitado, las listas pueden venir vacías; no es un error.
- **Paginación:** los endpoints de listado deben admitir parámetros como `limit` y `offset`.
- **Validación:** solicitudes y respuestas deben ajustarse a los esquemas Pydantic y al contrato OpenAPI.
- **Autorización:** cuando se incorpore autenticación, debe verificarse que el usuario tenga permiso para acceder al documento o a la generación solicitada.

### 4.4. Flujo de uso

La carga del documento y la generación son operaciones independientes. Esto permite reutilizar un documento para crear varias generaciones con configuraciones distintas.

1. El cliente sube el archivo mediante `POST /api/v1/documents`.
2. FastAPI valida el archivo, lo almacena en Supabase Storage y registra sus metadatos en PostgreSQL.
3. El cliente solicita una generación mediante `POST /api/v1/generations`, enviando el `document_id` y la configuración.
4. FastAPI valida la solicitud, registra la generación y sus etapas iniciales, y programa la ejecución del pipeline.
5. La API responde con `202 Accepted`, incluyendo el identificador de la generación y los datos necesarios para consultar su estado.
6. El pipeline recupera el documento y ejecuta las etapas definidas.
7. El cliente consulta `GET /api/v1/generations/{generation_id}` para obtener el estado, el progreso de las etapas, el error y el `summary` (conteos calculados a partir de los datos persistidos).
8. Cuando los resultados se han persistido, el cliente consulta las rutas de resultados, trazabilidad y métricas.

La ejecución asíncrona dentro del proceso de FastAPI puede ser suficiente para un prototipo, pero no garantiza la recuperación de tareas tras reinicios. Para reintentos y procesamiento durable deberá evaluarse una cola de trabajos y un worker dedicado.

## 5. Estados de ejecución

### 5.1. Estados de una generación

Estados previstos:

- `queued`: la generación está registrada y espera su ejecución.
- `running`: el pipeline se está ejecutando.
- `completed`: el pipeline terminó correctamente.
- `failed`: el pipeline terminó con un error.

Si la implementación actual no utiliza `queued`, la documentación debe ajustarse a los estados realmente admitidos por el esquema y el servicio.

### 5.2. Estados de una etapa

- `pending`: etapa pendiente de ejecución.
- `running`: etapa en ejecución.
- `completed`: etapa completada satisfactoriamente.
- `failed`: etapa que terminó con un error.
- `skipped`: etapa omitida por una condición del flujo (P3 y P4 con clustering deshabilitado; P7 mientras no esté implementada). No se usa para etapas que no llegaron a ejecutarse por un fallo anterior.

### 5.3. Reglas de transición

- La generación puede comenzar en `queued` y pasar a `running` cuando el procesamiento empieza.
- Pasa a `completed` cuando las siete etapas terminan en `completed` o `skipped`.
- Pasa a `failed` cuando ocurre un error que impide completar el pipeline.
- Cada etapa pasa de `pending` a `running` y termina en `completed`, `failed` o `skipped`, según corresponda.
- Si una etapa falla, esa etapa queda en `failed` con su `error_message`, las etapas posteriores permanecen en `pending` y la generación termina en `failed`.
- `completed_at` se registra al alcanzar cualquier estado final (`completed` o `failed`). Los estados finales no se reabren: reintentar implica crear una nueva generación.

Las transiciones se gestionan desde los servicios y se persisten en Supabase. Los controladores deben exponer el estado persistido, sin simular el progreso únicamente en memoria.

La concurrencia debe definirse explícitamente. Si el sistema admite una sola generación activa, el backend debe aplicar esa regla de forma segura y persistente; no basta con comprobar una variable local en memoria.

## 6. Contrato de errores

Las respuestas de error deben mantener un formato JSON común:

```json
{
  "error": {
    "code": "DOCUMENT_NOT_FOUND",
    "message": "No se encontró el documento solicitado.",
    "details": {}
  }
}
```

El campo `details` puede incluir información adicional que sea segura para el cliente.

| HTTP | Código | Uso |
|---|---|---|
| `400` | `VALIDATION_ERROR` | Parámetros o cuerpo de solicitud inválidos, si este es el contrato adoptado. |
| `404` | `DOCUMENT_NOT_FOUND` | El documento solicitado no existe. |
| `404` | `GENERATION_NOT_FOUND` | La generación solicitada no existe. |
| `404` | `TEST_CASE_NOT_FOUND` | El caso de prueba no existe en la generación indicada. |
| `404` | `METRIC_NOT_FOUND` | La métrica no se ha calculado para la generación. |
| `404` | `RELATION_NOT_FOUND` | No existe la relación RF–CP indicada. |
| `409` | `DOCUMENT_IN_USE` | El documento tiene generaciones activas. |
| `409` | `GENERATION_IN_PROGRESS` | La generación está en cola o en procesamiento. |
| `413` | `PAYLOAD_TOO_LARGE` | El archivo supera el tamaño máximo permitido. |
| `415` | `UNSUPPORTED_MEDIA_TYPE` | El formato o tipo de archivo no está permitido. |
| `501` | `NOT_IMPLEMENTED` | Funcionalidad aún no implementada, como eventos SSE. |
| `503` | `AI_SERVICE_UNAVAILABLE` | Una dependencia necesaria para IA no está disponible temporalmente. |
| `500` | `INTERNAL_ERROR` | Error inesperado no representado por un error controlado. |

### Reglas de manejo

- La conversión de excepciones al formato común debe centralizarse en los manejadores de excepciones de FastAPI.
- Si el contrato requiere `400` para errores de validación, se debe configurar FastAPI para convertir sus respuestas predeterminadas `422` de forma consistente.
- Los recursos inexistentes deben distinguirse mediante códigos de aplicación específicos.
- Las respuestas no deben exponer trazas internas, credenciales ni información sensible.
- Los errores del pipeline deben reflejarse en el estado `failed` de la generación y en el registro del error. Esto es distinto de `GENERATION_NOT_FOUND`.

## 7. Persistencia y archivos

El esquema de base de datos se gestiona mediante migraciones o scripts SQL bajo `supabase/`. El archivo `supabase/schema.sql` debe reflejar el esquema realmente desplegado; la documentación de diseño puede mantenerse en `docs/database.md`.

### 7.1. Tablas existentes o previstas

El esquema de persistencia inicial documentado contempla:

- `documents`: `filename`, `file_type`, `size_bytes`, `storage_path`, `checksum` y `uploaded_at`.
- `generations`: documento asociado, `status`, `clustering_enabled`, `method_type`, `config_snapshot`, `error_message` y marcas de tiempo.
- `generation_stages`: `stage_key` (`p1`–`p7`), `stage_order`, `status`, `error_message` y marcas de tiempo de cada etapa. El nombre visible de la etapa proviene de un catálogo en el código y no se almacena.

Para conservar los resultados funcionales y la trazabilidad del sistema, se propone ampliar el esquema con estas tablas:

- `user_stories`: historias de usuario procesadas.
- `functional_requirements`: requisitos funcionales extraídos.
- `user_story_requirements`: relaciones HU–RF.
- `clusters`: grupos semánticos.
- `cluster_requirements`: relaciones entre grupos y requisitos.
- `test_cases`: casos de prueba generados.
- `test_steps`: pasos de los casos de prueba.
- `requirement_test_cases`: relaciones RF–CP y estado de validación.
- `generation_metrics`: métricas calculadas por ejecución.
- `metric_findings`: hallazgos asociados a una métrica.

Estas tablas adicionales son **parte del diseño propuesto** hasta que se creen y verifiquen en Supabase. Sus campos, restricciones y relaciones deben documentarse en `docs/database.md` y definirse en las migraciones SQL.

### 7.2. Criterios de persistencia

- Cada resultado debe quedar asociado a su `generation_id`.
- Las relaciones entre HU, RF, grupos y CP deben impedir asociaciones entre ejecuciones diferentes cuando corresponda.
- La pertenencia de un RF a un grupo semántico no implica que un CP cubra ese RF.
- Una relación RF–CP propuesta por el LLM debe distinguirse de una relación validada. Solo las relaciones que superen el mecanismo de validación definido podrán contarse como cobertura confirmada.
- `generation_metrics` debe permitir almacenar el nombre de la métrica, el valor, la versión de fórmula y detalles del cálculo.
- Los parámetros relevantes aplicados durante una generación pueden conservarse en una instantánea de configuración (`config_snapshot`) para facilitar la reproducibilidad.
- No es necesario implementar todas las métricas desde el inicio; sí conviene diseñar la persistencia para incorporar sus resultados posteriormente.

### 7.3. Supabase Storage y seguridad

El bucket `user-story-documents` debe ser privado. La base de datos almacena la clave de almacenamiento, no una URL firmada permanente. Cuando necesite descargar un archivo, el backend genera una URL firmada temporal o utiliza un mecanismo de acceso equivalente.

Las credenciales privilegiadas de Supabase se utilizan exclusivamente en el servidor. Las políticas RLS y los permisos del bucket deben configurarse para impedir accesos no autorizados. La creación de una generación y sus etapas debe tratarse como una operación coherente; si se necesita atomicidad estricta, debe implementarse mediante una transacción o una función RPC adecuada.

## 8. Configuración

La configuración se obtiene de variables de entorno. Los nombres definitivos deben corresponder a los definidos en `ai_service/core/config.py` y en el entorno de despliegue.

Ejemplo de variables:

```env
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_STORAGE_BUCKET=user-story-documents
MAX_UPLOAD_SIZE_BYTES=20971520
```

Añade las variables necesarias para el proveedor LLM y el modelo de embeddings realmente utilizados por el proyecto. No guardes claves reales en el repositorio ni las incluyas en logs.

- En producción, la aplicación debe validar al inicio las variables críticas.
- En desarrollo, se puede permitir el arranque sin credenciales externas si el modo de desarrollo lo contempla; los endpoints dependientes de Supabase deben fallar de forma explícita y controlada.
- `MAX_UPLOAD_SIZE_BYTES=20971520` equivale a 20 MiB.
- Los secretos deben almacenarse en variables de entorno o en el gestor de secretos de la plataforma de despliegue.

## 9. Ejecución local

Desde el directorio `backend/`, crea y activa el entorno virtual, instala las dependencias declaradas por el proyecto y ejecuta FastAPI.

```bash
# Desde backend/
python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1

# Instalar dependencias
pip install -r requirements.txt

# Iniciar la aplicación, si el módulo expone esta entrada
python -m ai_service.main
```

El comando de instalación debe ajustarse al archivo de dependencias real del repositorio. Si la aplicación expone `app` en `ai_service/main.py`, también puede iniciarse con:

```bash
uvicorn ai_service.main:app --reload
```

URLs locales habituales:

- API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

## 10. Estado de implementación

Esta sección distingue entre la estructura descrita como objetivo y las capacidades que deben verificarse en el código. Actualízala cuando se complete o cambie una funcionalidad. No marques una característica como implementada solo porque su ruta o tabla aparezca en este documento.

| Componente | Estado documentado | Criterio para marcarlo como implementado |
|---|---|---|
| Aplicación FastAPI y endpoint de salud | Por verificar | La aplicación arranca y el endpoint responde con el contrato definido. |
| Carga de documentos | Por verificar | Valida formato y tamaño, guarda el archivo en Storage y registra sus metadatos. |
| Listado y consulta de documentos | Por verificar | Los endpoints consultan datos persistidos y aplican paginación. |
| Creación y consulta de generaciones | Por verificar | Registra una generación y permite consultar su estado persistido. |
| Persistencia de etapas P1–P7 | Por verificar | Cada etapa registra estados, tiempos y errores en la base de datos. |
| Orquestador P1–P7 | Por verificar | Coordina las etapas y aplica las reglas de transición documentadas. |
| Extracción de requisitos funcionales | Por verificar | La etapa produce requisitos estructurados y los persiste. |
| Embeddings y clustering semántico | Por verificar | La implementación calcula embeddings y agrupa requisitos cuando la opción está habilitada. |
| Generación y persistencia de casos de prueba | Por verificar | Guarda casos, pasos y sus relaciones con los requisitos. |
| Consultas de resultados para el frontend | Pendiente de verificar/implementar | Las rutas devuelven los resultados persistidos mediante respuestas documentadas. |
| Trazabilidad HU–RF–CP | Pendiente de verificar/implementar | Se conservan las relaciones y existe una ruta para consultarlas. |
| Validación de relaciones RF–CP | Pendiente de diseño | Existe un mecanismo de validación y la ruta `PATCH` propuesta actualiza `relation_status`. |
| Eliminación de documentos y generaciones | Por verificar | Se respetan los `409` y se eliminan los datos dependientes y los archivos en Storage. |
| Recuperación de ejecuciones interrumpidas | Pendiente de diseño | Al iniciar la aplicación, las generaciones `queued` o `running` sin ejecución viva se marcan `failed`. |
| Métricas y hallazgos de evaluación | Pendiente de definir/implementar | Se definen las fórmulas y se guardan resultados y hallazgos. |
| Eventos SSE | Reservado | Se implementa el streaming o se mantiene la respuesta `501`. |
| Comparación entre métodos o ejecuciones | Pendiente de diseño | Se define el contrato de comparación y se implementa su persistencia y consulta. |
| Pruebas automatizadas | Por verificar | Existen pruebas para servicios, repositorios y endpoints relevantes. |

**Cómo actualizar esta tabla:** reemplaza “Por verificar” por `Implementado`, `Parcial` o `Pendiente` después de comprobar el código, las pruebas y, cuando corresponda, el esquema de Supabase. Si una función está parcialmente implementada, especifica qué falta.

## 11. Principios de diseño

1. **Separación de responsabilidades:** las rutas gestionan HTTP; los servicios implementan casos de uso; los repositorios gestionan persistencia; los clientes encapsulan integraciones externas.
2. **Contratos explícitos:** solicitudes y respuestas se definen con esquemas Pydantic y se documentan mediante OpenAPI.
3. **Persistencia como fuente de verdad:** los estados y resultados que necesita el frontend se consultan desde los datos persistidos; no se simula el progreso únicamente en memoria.
4. **Integridad referencial:** las relaciones entre documentos, ejecuciones, historias, requisitos y casos de prueba deben respetar las claves foráneas y las restricciones definidas.
5. **Trazabilidad verificable:** la asociación HU–RF–CP se almacena explícitamente. Una relación generada por el LLM no se considera evidencia de cobertura hasta que se valide mediante las reglas del sistema.
6. **Separación entre agrupamiento y cobertura:** que un requisito pertenezca a un cluster no significa que esté cubierto por un caso de prueba.
7. **Evolución de métricas:** las métricas se almacenan con nombre, valor, versión de fórmula y detalles para facilitar la evolución de los cálculos sin acoplar la base de datos a una fórmula única.
8. **Reproducibilidad:** se conservan los parámetros relevantes de cada generación cuando sean necesarios para comparar ejecuciones o interpretar sus resultados.
9. **Seguridad por defecto:** los secretos permanecen en el backend, los archivos se almacenan en un bucket privado y los recursos deben estar sujetos a controles de acceso.
10. **Errores controlados:** las excepciones se convierten en respuestas consistentes y no exponen detalles internos sensibles.
11. **Cambios de esquema versionados:** las modificaciones de la base de datos deben realizarse mediante migraciones o scripts revisables, evitando que la documentación y el esquema desplegado diverjan.
12. **Documentación alineada con la realidad:** toda ruta, tabla o etapa se etiqueta según su estado real; los elementos propuestos no se presentan como implementados.
13. **Pruebas por capas:** se prueban las reglas de negocio, el acceso a datos y los endpoints, usando dobles de prueba cuando no corresponda acceder a servicios externos.
14. **Complejidad proporcional:** no se añaden capas, tablas o endpoints sin una necesidad funcional identificada; se prioriza una estructura mantenible y extensible.

## Documentación relacionada

- `docs/database.md`: descripción del modelo de datos, las entidades, sus relaciones y las decisiones pendientes.
- `docs/openapi.yaml`: contrato OpenAPI exportado o mantenido para la API, si se utiliza una especificación versionada.
- `docs/pipeline-orchestration.md`: comportamiento del orquestador y las etapas P1–P7.
- `supabase/schema.sql`: definición SQL del esquema desplegable. Debe mantenerse sincronizada con la base de datos real.

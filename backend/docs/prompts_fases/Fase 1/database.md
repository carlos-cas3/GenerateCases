# Diseño de la base de datos

## 1. Objetivo

La base de datos almacena la información generada durante la ejecución del sistema inteligente para la generación automática de casos de prueba funcionales a partir de historias de usuario.

El diseño permite conservar los resultados de cada ejecución, establecer la trazabilidad entre historias de usuario (HU), requisitos funcionales (RF) y casos de prueba (CP), registrar los grupos obtenidos mediante clustering semántico y almacenar las métricas de evaluación y sus hallazgos.

La base de datos se plantea para PostgreSQL, compatible con Supabase.

## 2. Criterios de diseño

- **Persistencia por ejecución:** cada generación conserva sus propios resultados.
- **Trazabilidad:** se mantienen las relaciones entre HU, RF y CP.
- **Separación de responsabilidades:** la pertenencia de un RF a un grupo semántico es independiente de la relación entre un RF y un CP.
- **Integridad referencial:** las claves foráneas evitan relacionar registros de ejecuciones diferentes.
- **Evaluación extensible:** las métricas almacenan su valor, versión de fórmula y detalles.
- **Configuración reproducible:** cada ejecución puede conservar una copia de los parámetros utilizados.
- **Validación explícita:** las relaciones RF–CP pueden estar pendientes, validadas o rechazadas.

## 3. Modelo de datos

### 3.1. Documentos (`documents`)

Almacena los documentos de entrada que contienen las historias de usuario.

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | UUID, PK | Identificador del documento. |
| `filename` | TEXT | Nombre del archivo original. |
| `file_type` | TEXT | Formato del documento: `txt`, `pdf` o `docx`. |
| `size_bytes` | BIGINT | Tamaño del archivo en bytes. |
| `storage_path` | TEXT | Clave del objeto en el bucket privado de Storage. No se expone en la API. |
| `checksum` | TEXT | Huella digital para identificar el contenido del archivo. |
| `uploaded_at` | TIMESTAMPTZ | Fecha de carga. |

### 3.2. Ejecuciones (`generations`)

Registra cada ejecución del proceso de generación de casos de prueba.

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | UUID, PK | Identificador de la ejecución. |
| `document_id` | UUID, FK | Documento de entrada asociado. |
| `status` | TEXT | Estado: `queued`, `running`, `completed` o `failed`. |
| `clustering_enabled` | BOOLEAN | Indica si se habilitó el clustering semántico. |
| `method_type` | TEXT | Método de generación utilizado. |
| `config_snapshot` | JSONB | Copia de los parámetros aplicados en la ejecución. |
| `started_at` | TIMESTAMPTZ | Fecha de inicio. |
| `completed_at` | TIMESTAMPTZ | Fecha de finalización. |
| `error_message` | TEXT | Información del error, si ocurrió. |
| `created_at` | TIMESTAMPTZ | Fecha de creación del registro. |

La tabla permite distinguir ejecuciones con clustering habilitado y deshabilitado, así como conservar los parámetros aplicados para facilitar futuras comparaciones.

Notas:

- `clustering_enabled` corresponde al parámetro `semantic_clustering_enabled` de la API.
- `completed_at` se registra al alcanzar cualquier estado final (`completed` o `failed`).
- `error_message` contiene un mensaje seguro para el cliente; el detalle técnico se registra únicamente en el log.
- La API impide eliminar un documento mientras existan generaciones activas (`queued` o `running`). La política para las generaciones ya finalizadas sigue pendiente (decisión 8).

### 3.3. Etapas de ejecución (`generation_stages`)

Registra el estado de cada etapa P1–P7 de una ejecución. Se crean siete registros junto con la generación.

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | UUID, PK | Identificador del registro. |
| `generation_id` | UUID, FK | Ejecución a la que pertenece. |
| `stage_key` | TEXT | Etapa: `p1`, `p2`, `p3`, `p4`, `p5`, `p6` o `p7`. |
| `stage_order` | INTEGER | Posición de la etapa en el pipeline (1 a 7). |
| `status` | TEXT | Estado: `pending`, `running`, `completed`, `failed` o `skipped`. |
| `error_message` | TEXT | Información del error si la etapa falló. |
| `started_at` | TIMESTAMPTZ | Fecha de inicio. |
| `completed_at` | TIMESTAMPTZ | Fecha en que la etapa terminó o fue omitida. |

La combinación (`generation_id`, `stage_key`) y la combinación (`generation_id`, `stage_order`) deben ser únicas.

El nombre visible de la etapa no se almacena: se obtiene de un catálogo definido en el código. Si una etapa falla, las posteriores permanecen en `pending`; `skipped` se reserva para etapas omitidas por una condición del flujo (P3 y P4 con clustering deshabilitado; P7 mientras no esté implementada). El detalle de cada etapa se describe en `pipeline-orchestration.md`.

### 3.4. Historias de usuario (`user_stories`)

Almacena las historias de usuario procesadas.

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | UUID, PK | Identificador de la historia. |
| `generation_id` | UUID, FK | Ejecución a la que pertenece. |
| `code` | TEXT | Código de la historia dentro de la ejecución. |
| `original_text` | TEXT | Texto original de la historia. |
| `role` | TEXT | Rol del usuario. |
| `action` | TEXT | Acción solicitada. |
| `goal` | TEXT | Objetivo o beneficio esperado. |
| `validation_status` | TEXT | Estado de validación de la historia. |

Se recomienda que el código de una historia sea único dentro de una misma ejecución cuando esté definido.

### 3.5. Requisitos funcionales (`functional_requirements`)

Almacena los requisitos funcionales extraídos de las historias de usuario.

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | UUID, PK | Identificador del requisito. |
| `generation_id` | UUID, FK | Ejecución a la que pertenece. |
| `code` | TEXT | Código del requisito dentro de la ejecución. |
| `description` | TEXT | Descripción del requisito funcional. |
| `source_text` | TEXT | Fragmento de origen o texto que respalda su extracción. |

El código del requisito debe ser único dentro de la ejecución para facilitar la identificación y la trazabilidad.

### 3.6. Relación entre historias y requisitos (`user_story_requirements`)

Representa la relación entre las historias de usuario y los requisitos funcionales extraídos.

| Campo | Tipo | Descripción |
|---|---|---|
| `generation_id` | UUID, FK | Ejecución a la que pertenece la relación. |
| `user_story_id` | UUID, FK | Historia de usuario relacionada. |
| `requirement_id` | UUID, FK | Requisito funcional relacionado. |

La clave primaria está compuesta por `generation_id`, `user_story_id` y `requirement_id`.

Esta tabla permite representar relaciones de muchos a muchos: una historia puede originar varios requisitos y un requisito puede estar vinculado a más de una historia, si el proceso de extracción lo determina.

### 3.7. Grupos semánticos (`clusters`)

Almacena los grupos resultantes del clustering de requisitos funcionales.

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | UUID, PK | Identificador del grupo. |
| `generation_id` | UUID, FK | Ejecución en la que se creó. |
| `name` | TEXT | Nombre del grupo. |
| `description` | TEXT | Descripción del grupo. |
| `cluster_label` | INTEGER | Etiqueta numérica asignada por el algoritmo. |

La tabla registra los grupos identificados durante una ejecución. La existencia de grupos dependerá de si se habilitó el clustering.

### 3.8. Relación entre grupos y requisitos (`cluster_requirements`)

Registra la pertenencia de cada requisito funcional a un grupo semántico.

| Campo | Tipo | Descripción |
|---|---|---|
| `generation_id` | UUID, FK | Ejecución correspondiente. |
| `cluster_id` | UUID, FK | Grupo semántico. |
| `requirement_id` | UUID, FK | Requisito funcional agrupado. |
| `similarity_to_centroid` | DOUBLE PRECISION, nullable | Similitud respecto al centroide, si se calcula y se define con ese significado. |

La clave primaria está compuesta por `generation_id`, `cluster_id` y `requirement_id`.

El campo de similitud debe interpretarse de acuerdo con la implementación real del algoritmo. Si el valor registrado corresponde a otra comparación semántica, se deberá ajustar su nombre o documentar su significado para evitar ambigüedades.

### 3.9. Casos de prueba (`test_cases`)

Almacena los casos de prueba funcionales generados.

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | UUID, PK | Identificador del caso de prueba. |
| `generation_id` | UUID, FK | Ejecución que produjo el caso. |
| `code` | TEXT | Código del caso de prueba. |
| `title` | TEXT | Título del caso de prueba. |
| `objective` | TEXT | Objetivo del caso. |
| `preconditions` | JSONB | Lista de precondiciones. |
| `test_data` | JSONB | Datos necesarios para la ejecución del caso. |
| `expected_result` | TEXT | Resultado esperado general. |
| `created_at` | TIMESTAMPTZ | Fecha de creación. |

Se recomienda mantener el código único dentro de cada ejecución.

### 3.10. Pasos de prueba (`test_steps`)

Almacena los pasos que conforman cada caso de prueba.

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | UUID, PK | Identificador del paso. |
| `generation_id` | UUID, FK | Ejecución correspondiente. |
| `test_case_id` | UUID, FK | Caso de prueba al que pertenece. |
| `step_number` | INTEGER | Número secuencial del paso. |
| `action` | TEXT | Acción que debe realizarse. |
| `expected_result` | TEXT | Resultado esperado del paso. |

El número del paso debe ser mayor que cero y único dentro de cada caso de prueba.

El resultado esperado puede registrarse a nivel de paso y, cuando corresponda, a nivel general del caso. Se debe definir en la implementación si ambos campos son necesarios para evitar duplicación innecesaria.

### 3.11. Relación entre requisitos y casos de prueba (`requirement_test_cases`)

Registra la asociación entre un requisito funcional y un caso de prueba.

| Campo | Tipo | Descripción |
|---|---|---|
| `generation_id` | UUID, FK | Ejecución correspondiente. |
| `requirement_id` | UUID, FK | Requisito funcional asociado. |
| `test_case_id` | UUID, FK | Caso de prueba relacionado. |
| `relation_status` | TEXT | Estado: `pending`, `validated` o `rejected`. |
| `validation_method` | TEXT | Método utilizado para validar la relación. |
| `validation_notes` | TEXT | Observaciones sobre la validación. |

La clave primaria está compuesta por `generation_id`, `requirement_id` y `test_case_id`.

**Importante:** una asociación propuesta por el LLM no demuestra por sí misma que el caso cubra el requisito. La relación debe poder validarse antes de considerarla evidencia de cobertura funcional.

### 3.12. Métricas por ejecución (`generation_metrics`)

Almacena los resultados de las métricas calculadas para una ejecución.

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | UUID, PK | Identificador del registro de métrica. |
| `generation_id` | UUID, FK | Ejecución evaluada. |
| `metric_name` | TEXT | Nombre de la métrica. |
| `metric_value` | DOUBLE PRECISION, nullable | Valor calculado. |
| `numerator` | DOUBLE PRECISION, nullable | Numerador, cuando la fórmula lo requiera. |
| `denominator` | DOUBLE PRECISION, nullable | Denominador, cuando la fórmula lo requiera. |
| `formula_version` | TEXT | Versión de la fórmula aplicada. |
| `details` | JSONB | Datos complementarios del cálculo. |
| `calculated_at` | TIMESTAMPTZ | Fecha del cálculo. |

La estructura permite incorporar o modificar métricas sin crear una tabla diferente para cada indicador.

Como métricas candidatas iniciales se consideran:

- Cobertura de requisitos funcionales.
- Redundancia semántica de los casos de prueba.
- Completitud estructural de los casos de prueba.

La definición exacta de las fórmulas y sus umbrales se establecerá posteriormente.

### 3.13. Hallazgos de evaluación (`metric_findings`)

Almacena observaciones o problemas identificados durante la evaluación de las métricas.

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | UUID, PK | Identificador del hallazgo. |
| `generation_metric_id` | UUID, FK | Métrica que originó el hallazgo. |
| `finding_code` | TEXT | Código del tipo de hallazgo. |
| `severity` | TEXT | Severidad: `info`, `warning` o `error`. |
| `message` | TEXT | Descripción del hallazgo. |
| `evidence` | JSONB | Evidencia asociada al hallazgo. |
| `created_at` | TIMESTAMPTZ | Fecha de creación. |

Esta tabla permite registrar, por ejemplo, requisitos sin casos de prueba validados, posibles duplicidades o casos de prueba que no contienen determinados elementos estructurales.

Los ejemplos son ilustrativos; las reglas concretas de detección quedan pendientes de definición.

## 4. Relaciones entre las entidades

Las relaciones principales del modelo son:

- Un documento puede tener múltiples ejecuciones.
- Una ejecución tiene siete etapas (`generation_stages`).
- Una ejecución contiene historias de usuario, requisitos funcionales, grupos semánticos y casos de prueba.
- Las historias de usuario se relacionan con los requisitos funcionales mediante `user_story_requirements`.
- Los requisitos funcionales se relacionan con los grupos mediante `cluster_requirements`.
- Los requisitos funcionales se relacionan con los casos de prueba mediante `requirement_test_cases`.
- Cada caso de prueba puede contener múltiples pasos.
- Una ejecución puede tener múltiples registros de métricas.
- Una métrica puede tener múltiples hallazgos de evaluación.

## 5. Integridad referencial

Para evitar asociaciones inconsistentes, las tablas que relacionan entidades de una misma ejecución utilizan claves foráneas compuestas que incluyen `generation_id`.

Esto permite verificar que la historia, el requisito, el grupo o el caso de prueba relacionado pertenezcan a la ejecución correspondiente.

También se recomienda establecer las siguientes restricciones:

- Los estados de ejecución y de etapa deben limitarse a los valores admitidos.
- Cada ejecución debe tener como máximo un registro por etapa (`generation_id`, `stage_key`).
- Los códigos de historias, requisitos y casos de prueba deben ser únicos dentro de la ejecución, cuando se utilicen.
- Los números de paso deben ser positivos.
- Los estados de validación de relaciones deben estar restringidos a los valores definidos.
- Las claves foráneas deben contar con políticas de eliminación explícitas para evitar borrar accidentalmente resultados que deban conservarse.

## 6. Índices

Se proponen índices iniciales para acelerar las consultas más frecuentes:

| Tabla | Campo indexado | Propósito |
|---|---|---|
| `generations` | `document_id` | Consultar ejecuciones de un documento. |
| `generations` | `status` | Detectar ejecuciones activas o interrumpidas. |
| `generation_stages` | `generation_id` | Recuperar las etapas de una ejecución. |
| `user_stories` | `generation_id` | Recuperar historias de una ejecución. |
| `functional_requirements` | `generation_id` | Recuperar requisitos de una ejecución. |
| `test_cases` | `generation_id` | Recuperar casos de prueba de una ejecución. |
| `generation_metrics` | `generation_id` | Consultar métricas de una ejecución. |
| `metric_findings` | `generation_metric_id` | Consultar hallazgos de una métrica. |

Los índices adicionales se definirán según las consultas reales de la API y las necesidades de rendimiento.

## 7. Decisiones pendientes

Las siguientes decisiones no se consideran cerradas en el diseño inicial:

1. **Definición de métricas:** establecer las fórmulas de cobertura, redundancia y completitud estructural.
2. **Validación de cobertura:** determinar cómo comprobar que un caso de prueba cubre realmente un requisito funcional.
3. **Similitud semántica:** precisar qué representa el valor de similitud almacenado y cómo se calcula.
4. **Persistencia de embeddings:** decidir si se utilizará `pgvector`, otra estructura o un servicio externo.
5. **Versionado de métricas:** definir si los resultados anteriores se conservan cuando se recalcula una métrica con la misma versión de fórmula.
6. **Configuración de ejecución:** determinar qué parámetros se almacenarán en `config_snapshot`.
7. **Modelo de precondiciones y datos de prueba:** decidir si el formato JSONB es suficiente o si se necesitan entidades normalizadas.
8. **Políticas de eliminación:** *Cerrada en la Fase 2.* Una generación final se elimina con sus resultados en cascada (`delete_generation_if_final`); una activa responde `409 GENERATION_IN_PROGRESS`. Un documento solo se elimina si **no tiene ninguna generación** (activa o finalizada); si no, `409 DOCUMENT_IN_USE` con los ids. Es coherente con la FK `on delete restrict` y con que `document_name` se obtiene por JOIN. Queda para una fase futura un soft delete (`documents.deleted_at`) que permita retirar documentos conservando el historial, y la retención automática.
9. **Concurrencia de ejecuciones:** definir cuántas generaciones pueden estar activas a la vez y cómo se garantiza de forma persistente.
10. **Ejecuciones interrumpidas:** *Resuelta en la Fase 1.5.* Al arrancar, `recover_interrupted_generations` (`services/pipeline_runs.py`) marca `failed` las generaciones `queued`/`running` y su etapa `running` (supone un único proceso).
11. **P7 sin implementar:** mientras no exista, la etapa se registra como `skipped` y no se persisten métricas.
12. **Embeddings para métricas:** definir cómo obtiene P7 los embeddings cuando P3 fue omitida (ver también la decisión 4).

## 8. Orden recomendado de implementación

1. Crear las tablas principales y sus restricciones.
2. Implementar la persistencia de documentos, ejecuciones y etapas (`generation_stages`).
3. Persistir las historias de usuario y los requisitos funcionales extraídos.
4. Guardar las relaciones HU–RF.
5. Persistir los grupos semánticos y las relaciones RF–grupo cuando el clustering esté habilitado.
6. Guardar los casos de prueba, sus pasos y las relaciones RF–CP.
7. Implementar la validación de las relaciones RF–CP.
8. Incorporar las métricas y sus hallazgos cuando se hayan definido sus fórmulas.

Este orden permite construir primero una base de datos consistente y funcional, dejando la definición detallada de las métricas para una etapa posterior.

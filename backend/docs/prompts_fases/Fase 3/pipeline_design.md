# Diseño técnico del pipeline

> **Estado:** borrador en revisión documental. Contiene únicamente la **Sección 1: modelos y contratos de entrada/salida**.\
> **Alcance:** etapas P1–P7. P7 (evaluación) se ejecuta cuando hay casos de prueba y no es bloqueante (D-33); sus métricas v1 están en D-37 y su contrato en código está pendiente.\
> **Revisión:** incorpora las decisiones D-26 a D-35 de `decisiones_pipeline.md` y el cierre documental (D-18, D-26, D-36, D-37, D-38, D-39 y las tareas T-01 a T-05) de `cierre_documental.md`.

---

## 0. Convenciones de este documento

Cada decisión lleva una etiqueta para distinguir lo que ya está impuesto de lo que se propone:

| Etiqueta | Significado |
|---|---|
| **[Fijado]** | Viene del `schema.sql` o del `openapi.yaml`. Cambiarlo exige migración o cambio de contrato. |
| **[Propuesta]** | Decisión recomendada en este documento, pendiente de confirmación. |
| **[Pendiente D-xx]** | Decisión abierta. Se lista en la sección 1.9 con opciones y recomendación. |

Convenciones de nomenclatura:

- Identificadores de código en inglés (`UserStory`, `FunctionalRequirement`, `TestCase`). Los términos de negocio HU, RF y CP se usan en la prosa.
- Códigos legibles por generación: `HU-001`, `RF-001`, `CP-001`.
- Todos los modelos son **inmutables**. Los contratos P1–P6 se implementan como modelos Pydantic v2 con `frozen=True` y `extra="forbid"` (`ai_service/pipeline/contracts/`). Cada etapa devuelve objetos nuevos y no modifica los recibidos.

---

## 1. Modelos y contratos de entrada/salida

### 1.1 Restricciones heredadas de la API y de la base de datos

Antes de definir los modelos conviene fijar lo que ya está decidido fuera de este documento.

| # | Restricción | Fuente | Impacto en el diseño |
|---|---|---|---|
| R1 | Existen siempre siete etapas (`p1`…`p7`) por generación, creadas en `pending`. | `create_generation`, `generation_stages` | El orquestador resuelve el estado de las siete. P7 se ejecuta siempre que P6 se haya ejecutado (es `skipped` en los casos D-29 y D-36) y **no es bloqueante**: si falla, queda `failed` y la generación termina `completed` (D-33). |
| R2 | Con `semantic_clustering_enabled=false`, P3 y P4 quedan `skipped`. | `openapi.yaml` | **P5 no puede exigir clustering**: su entrada de clusters es opcional. |
| R3 | Si una etapa P1–P6 falla, las siguientes quedan `pending` y la generación termina `failed`. Si P2 no extrae RF, P2 queda `completed` con aviso y P3–P7 `skipped` (D-29). Si con clustering ningún RF queda en un cluster, P5 queda `completed` con aviso y 0 unidades, y P6–P7 `skipped` (D-36). | `openapi.yaml` | Política *fail-fast* a nivel de etapa. Los fallos parciales dentro de una etapa se deciden en cada contrato. |
| R4 | Cada artefacto pertenece a una `generation_id` (FK compuestas `(generation_id, id)`). | `schema.sql` | Todos los contratos transportan `generation_id`. No hay reutilización entre generaciones. |
| R5 | `id` es `uuid`; `code` es texto único por generación en HU, RF y CP. | `schema.sql` | Se necesita doble identidad (ver 1.2). |
| R6 | Relaciones M:N: HU–RF (`user_story_requirements`), RF–CP (`requirement_test_cases`) y RF–cluster (`cluster_requirements`; la PK permite que un RF esté en varios clusters). | `schema.sql` | Los modelos usan listas de referencias, nunca campos escalares. Si un RF está en varios clusters, P5 lo toma como objetivo solo en uno (D-31). |
| R7 | `requirement_test_cases.relation_status` por defecto es `pending`. Solo `validated` cuenta como cobertura. | `schema.sql`, `openapi.yaml` | P6 produce vínculos `pending`. Pertenecer a un cluster o proponerlo el LLM no implica cobertura. |
| R8 | La configuración de la API solo acepta `semantic_clustering_enabled` y `method_type` (`additionalProperties: false`). El resto se guarda en `config_snapshot`. | `openapi.yaml` | Modelo, versión de prompt, parámetros de clustering, etc. salen de la configuración del servidor y se **snapshotean**; no los envía el cliente. El snapshot es **fijo desde la creación** (lo solicitado); lo ejecutado va a `generation_stages.runtime_info` (D-34). |
| R9 | `POST /generations` comprueba las dependencias de IA **antes** de crear la generación y responde `503` si fallan (no se registra nada). Embeddings solo se comprueban con `semantic_clustering_enabled=true`. | `openapi.yaml` | Los puertos de LLM y embeddings necesitan una operación de verificación de disponibilidad. |
| R10 | **No existen tablas** para embeddings, evaluación de calidad, hallazgos de HU ni contexto de generación. Sí se persisten la clasificación de P2 (`user_stories.classification*`, D-27), los RF sin cluster (`unassigned_requirements`, D-32) y los metadatos de etapa (`generation_stages.error_code`, `warnings`, `llm_runs`, `runtime_info`; D-28, D-35). | `schema.sql` | Lo que no tiene tabla vive en memoria o requiere una decisión de persistencia (D-06, D-09, D-12). |
| R11 | El documento de entrada es `txt`, `pdf` o `docx`, no una lista de HU. | `documents`, `openapi.yaml` | Falta definir quién extrae el texto y segmenta las historias (D-01). |

### 1.2 Reglas transversales de modelado

**Doble identidad (R5).** Cada entidad tiene `id: UUID` y `code: str`.

- Dentro del pipeline, **las referencias entre artefactos usan `code`** (`RF-003` referencia a `HU-001`).
- Los prompts muestran **solo códigos** al LLM. Así se ahorran tokens y se evita que el modelo invente UUID.
- El adaptador de persistencia traduce `code` a `uuid` al escribir.
- Los códigos los asigna el pipeline (nunca el LLM), de forma secuencial y determinista, para evitar colisiones entre lotes.

**Borradores frente a entidades.** Lo que devuelve un LLM se modela como `Draft` (por ejemplo `RequirementDraft`, `TestCaseDraft`). La etapa valida el borrador, asigna `id` y `code`, comprueba referencias y solo entonces crea la entidad de dominio. Esto mantiene los contratos libres del formato de un proveedor concreto.

**Ubicación por capa:**

| Capa | Contiene |
|---|---|
| **Domain** | Entidades y objetos de valor con sus invariantes: `UserStory`, `FunctionalRequirement`, `SemanticCluster`, `TestCase`, enumeraciones. |
| **Application** | Contratos de etapa (`P1Input`…`P6Output`), configuraciones de etapa, `Draft`, `GenerationContext`, `StageError`, metadatos de ejecución y puertos. |
| **Infrastructure** | Esquemas específicos de proveedor (JSON schema del LLM, filas de Supabase) y sus mapeadores hacia el dominio. |

---

### 1.3 Modelos de dominio

#### 1.3.1 Enumeraciones

| Enum | Valores | Estado |
|---|---|---|
| `StageKey` | `p1` … `p7` | **[Fijado]** |
| `StageStatus` | `pending`, `running`, `completed`, `failed`, `skipped` | **[Fijado]** |
| `StoryValidationStatus` | `valid`, `valid_with_warnings`, `invalid` | **[Fijado]** (`check` en `user_stories.validation_status`, D-04) |
| `StoryClassificationCategory` | `candidata_funcional`, `requiere_aclaracion`, `no_aplicable` | **[Fijado]** (`check` en `user_stories.classification`, D-27) |
| `IssueSeverity` | `info`, `warning`, `error` | **[Propuesta]** (alineado con `metric_findings.severity`) |
| `QualityCriterion` | `atomicity`, `ambiguity`, `testability`, `specificity`, `duplicity`, `traceability`, `grounding` | Los seis primeros, del pre-diseño; `grounding` es **[Propuesta]** (ver 1.6.2) |
| `FindingKind` | `potential_duplicate`, `decomposition_candidate`, `ungrounded`, `uncovered_fragment` | **[Propuesta]** |
| `RelationStatus` | `pending`, `validated`, `rejected` | **[Fijado]** |

#### 1.3.2 `SourceDocument`

Texto plano ya extraído del archivo subido. Es la entrada del pipeline.

| Campo | Tipo | Oblig. | Notas |
|---|---|---|---|
| `document_id` | UUID | sí | `documents.id` |
| `filename` | str | sí | |
| `file_type` | `txt` \| `pdf` \| `docx` | sí | **[Fijado]** |
| `text` | str | sí | Texto extraído. Quién lo extrae: **[Pendiente D-01]** |

#### 1.3.3 `UserStory` (HU estructurada)

Se persiste en `user_stories`. P1 conserva todas las historias identificadas, incluidas aquellas cuya estructura no permita extraer los componentes tradicionales de una HU. La condición de historia funcional se determina semánticamente en P2, no por la presencia de una plantilla.

| Campo               | Tipo                     | Oblig. | Columna             | Notas                                                                                                                                                                |
|---------------------|--------------------------|--------|---------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `id`                | UUID                     | sí     | `id`                |                                                                                                                                                                      |
| `code`              | str                      | sí     | `code`              | Nullable en BD **a propósito** (no se migra a NOT NULL); el pipeline siempre lo asigna. `HU-001`…                                                                     |
| `original_text`     | str                      | sí     | `original_text`     | Texto íntegro tal como aparece en el documento. Inmutable y fuente principal para P2.                                                                                |
| `role`              | str \| None              | no     | `role`              | Actor/rol si se identifica explícitamente. No es obligatorio ni se infiere cuando no está indicado.                                                                  |
| `objective`         | str \| None              | no     | `action`            | Acción, necesidad o funcionalidad identificada. Mapeo **[Fijado]** (D-02 resuelta). Puede quedar `None` si no se puede delimitar con fiabilidad.                     |
| `benefit`           | str \| None              | no     | `goal`              | Beneficio/valor si aparece explícitamente. Es opcional.                                                                                                              |
| `normalized_text`   | str \| None              | no     | —                   | Representación normalizada auxiliar; no reemplaza `original_text`. No existe columna.                                                                                |
| `validation_status` | `StoryValidationStatus`  | sí     | `validation_status` | Estado de procesamiento estructural, no clasificación funcional.                                                                                                     |
| `issues`            | tuple[`ValidationIssue`] | sí     | —                   | Incidencias de segmentación/normalización. No existe columna en el esquema actual.                                                                                   |
| `position`          | int                      | sí     | `position`          | Orden de aparición en el documento (base 1). Único por generación; los listados de la API ordenan por esta columna.                                                 |
| `content_sections`  | tuple[`StorySection`]    | no     | —                   | Secciones reconocidas (p. ej., criterios de aceptación, reglas, restricciones, condiciones, resultados esperados). Propuesta en memoria; no implica nuevas columnas. |

`StorySection`: `kind: str`, `text: str`, `source_span: SourceSpan | None`. El texto de cada sección se conserva literalmente. Las categorías son etiquetas de organización, no una lista cerrada de contenidos admitidos.

`UnresolvedFragment`: `text: str`, `position: int`, `reason: str`. Se conserva en la salida de P1 y no se convierte en HU artificialmente.

`ValidationIssue`: `rule_code: str`, `severity: IssueSeverity`, `message: str`, `field: str | None`.

**Invariantes**

- `original_text` nunca se descarta ni se reemplaza por una reconstrucción.
- La ausencia de rol, beneficio o de los marcadores «Como», «quiero» o «para» no invalida por sí sola una HU.
- `valid` significa que el fragmento fue segmentado y conservado correctamente; no significa que sea funcional ni que esté completo.
- `valid_with_warnings` indica que se conservó, pero existen incidencias estructurales no bloqueantes (por ejemplo, delimitación incierta).
- `invalid` se reserva para fragmentos que no pueden procesarse de forma fiable como unidad (por ejemplo, contenido vacío o corrupción de extracción), no para historias que no siguen una plantilla.
- Una HU `invalid` **se guarda** en `user_stories` con su `original_text` tal cual (nunca una cadena vacía sustituta), **no pasa a P2** y se cuenta aparte en el resumen (`invalid_user_stories_count`).
- La ambigüedad funcional y la aplicabilidad se evalúan en P2.

#### 1.3.4 `FunctionalRequirement` (RF)

Se persiste en `functional_requirements` y `user_story_requirements`. El contrato distingue los datos mínimos necesarios para registrar y trazar un RF de los atributos descriptivos que solo se incluyen cuando la HU los respalda.

| Campo | Tipo | Oblig. | Columna | Notas |
|---|---|---|---|---|
| `id` | UUID | sí | `id` | Asignado por el pipeline. |
| `code` | str | sí | `code` | `RF-001`… Único por generación. |
| `description` | str | sí | `description` | Enunciado del comportamiento funcional identificado. |
| `source_text` | str \| None | condicional | `source_text` | Fragmento literal que respalda el RF. Debe aportarse cuando pueda delimitarse; no se inventa. La nulabilidad ya existe en BD. |
| `source_span` | `SourceSpan` \| None | no | — | `user_story_code`, `start`, `end`: posición del fragmento dentro de la HU, si puede determinarse. Solo en memoria. |
| `user_story_codes` | tuple[str] | sí | `user_story_requirements` | Al menos una HU de origen. |
| `actor` | str \| None | no | — | Actor explícito, si existe. |
| `objective` | str \| None | no | — | Objetivo o acción funcional, si se identifica. |
| `preconditions` | tuple[str] | no | — | Solo condiciones explícitas en la HU. |
| `business_rules` | tuple[str] | no | — | Reglas de negocio explícitas. |
| `expected_outcomes` | tuple[str] | no | — | Resultados o respuestas esperadas expresamente indicados. |
| `acceptance_criteria` | tuple[str] | no | — | Criterios de aceptación asociados, cuando existan. |
| `conditions` | tuple[str] | no | — | Condiciones, restricciones o excepciones explícitas. |
| `unspecified_information` | tuple[str] | no | — | Aspectos relevantes para especificar o probar que la HU no define. No se completan mediante suposición. |
| `evidence` | tuple[`RequirementEvidence`] | no | — | Fragmentos textuales y referencia a HU que respaldan los atributos extraídos. |
| `depends_on` | tuple[str] | no | — | Dependencias entre RF. Fuera del alcance de la extracción v1 salvo decisión posterior (D-17). |

`RequirementEvidence`: `user_story_code: str`, `text: str`, `attribute: str | None`, `source_span: SourceSpan | None`.

**Integridad del registro frente a completitud descriptiva**

- Son obligatorios para registrar un RF: `id`, `code`, `description` y al menos una relación `user_story_codes` válida.
- Los demás atributos son opcionales y solo se rellenan cuando existe evidencia suficiente en el texto de origen.
- `source_text` puede ser `None` cuando la evidencia no pueda delimitarse como fragmento literal; en ese caso, el RF debe conservar referencias a HU y registrar la limitación. La política de aceptación de estos casos se define en P2.
- Los atributos opcionales no deben convertirse en campos obligatorios por el mero hecho de aparecer en el modelo.
- La estructura de aplicación propuesta no implica añadir columnas a Supabase. En v1, la persistencia se limita a las columnas y relaciones existentes; cualquier ampliación persistente requiere revisar `schema.sql` y justificar una migración.

**Invariantes**

- Cada código de `user_story_codes` existe entre las HU procesadas de la generación.
- Cada atributo informado debe estar respaldado por una evidencia de la HU; la ausencia de información se expresa como no especificada, no mediante valores inventados.
- Una HU puede producir cero, uno o varios RF. Un RF puede relacionarse con una o varias HU cuando el mismo comportamiento esté respaldado por ellas.
- No se fusionan RF únicamente por similitud semántica en P2. La similitud se analiza posteriormente en P3/P4 y no sustituye la identidad funcional.

#### 1.3.5 Evaluación de calidad y hallazgos de RF

Se mantienen **separados** del RF (pre-diseño, 5.2: artefacto ≠ evaluación). No hay tabla para ellos. **[Pendiente D-06]**

`RequirementQualityAssessment`

| Campo | Tipo | Notas |
|---|---|---|
| `requirement_code` | str | |
| `criteria` | tuple[`CriterionAssessment`] | Uno por criterio evaluado. |
| `needs_review` | bool | `True` si algún criterio quedó marcado. No es una probabilidad. |

`CriterionAssessment`

| Campo | Tipo | Notas |
|---|---|---|
| `criterion` | `QualityCriterion` | |
| `value` | float \| None | Escala y método **[Pendiente D-07]**. `None` si el criterio no se evaluó. Es un score heurístico, **no** una probabilidad calibrada. |
| `flagged` | bool | Indica un posible problema. |
| `rationale` | str \| None | Justificación breve. |
| `method` | `llm` \| `rule` | Cómo se obtuvo. |

`RequirementFinding`

| Campo | Tipo | Notas |
|---|---|---|
| `kind` | `FindingKind` | |
| `requirement_codes` | tuple[str] | Mínimo 1 (descomposición) o 2 (duplicado). |
| `detected_by` | `llm` \| `rule` \| `lexical` \| `embedding` | **[Pendiente D-08]** |
| `score` | float \| None | Similitud, si aplica. |
| `note` | str \| None | |

#### 1.3.6 Embeddings

No existe tabla de embeddings en el esquema. **[Pendiente D-09]**

`EmbeddingModelInfo`

| Campo | Tipo | Notas |
|---|---|---|
| `provider` | str | Local o remoto. |
| `model_name` | str | |
| `model_version` | str \| None | Cuando esté disponible. |
| `dimension` | int | |
| `normalized` | bool | Si los vectores están normalizados (L2). |
| `input_template` | str | Cómo se construye el texto a embeber (por ejemplo `"{description}"`), para reproducibilidad. |

`RequirementEmbedding`: `requirement_code: str`, `vector: tuple[float, ...]`.

**Invariante:** todos los vectores de un `EmbeddingSet` tienen longitud `dimension` y no contienen `NaN`.

#### 1.3.7 Grupo semántico

Se persiste en `clusters` y `cluster_requirements`.

`SemanticCluster`

| Campo | Tipo | Columna | Notas |
|---|---|---|---|
| `id` | UUID | `id` | |
| `label` | int | `cluster_label` | Etiqueta numérica del algoritmo. |
| `name` | str | `name` (NOT NULL) | Quién lo genera: **[Pendiente D-10]**. |
| `description` | str \| None | `description` | |
| `assignments` | tuple[`ClusterAssignment`] | `cluster_requirements` | |

`ClusterAssignment`: `requirement_code: str`, `similarity_to_centroid: float | None` (su significado depende del algoritmo; ver decisión pendiente 3 de `database.md`).

**Invariantes**

- Pertenecer a un cluster **no implica** duplicidad ni cobertura.
- Un RF puede aparecer en 0, 1 o varios clusters (el esquema lo permite; el algoritmo concreto puede restringirlo).
- Los RF sin cluster (*outliers*) se guardan en `unassigned_requirements` y la API los devuelve en `ClusterList.unassigned_requirement_ids`. **Por ahora no generan casos de prueba** (D-32, reemplaza a D-11).
- Un RF no puede estar a la vez en `cluster_requirements` y en `unassigned_requirements` (lo garantiza P4; la BD no lo restringe).

#### 1.3.8 Caso de prueba

Se persiste en `test_cases`, `test_steps` y `requirement_test_cases`.

`TestCase`

| Campo | Tipo | Oblig. | Columna | Notas |
|---|---|---|---|---|
| `id` | UUID | sí | `id` | |
| `code` | str | sí | `code` | `CP-001`… asignado por el pipeline. |
| `title` | str | sí | `title` | |
| `objective` | str \| None | no | `objective` | |
| `preconditions` | tuple[str] | sí | `preconditions` (JSONB) | Puede ser vacía. Única ubicación de las precondiciones del caso (D-26). |
| `test_data` | `TestData` \| None | no | `test_data` (JSONB) | Solo `inputs` y `notes` (D-26). |
| `steps` | tuple[`TestStep`] | sí | `test_steps` | **Mínimo 1.** |
| `expected_result` | str | sí\* | `expected_result` | Resultado global y única ubicación del resultado esperado del caso (D-26). Nullable en BD; se exige en el contrato **[Propuesta]**. |
| `requirement_links` | tuple[`RequirementTestCaseLink`] | sí | `requirement_test_cases` | **Mínimo 1.** |

`TestData` (D-26): `inputs: dict[str, Any]`, `notes: str | None`. Ambas opcionales; cualquier otra clave (incluidas `preconditions` y `expected_results`) es `LLM_INVALID_OUTPUT`. Las precondiciones y el resultado esperado son campos de primer nivel del caso, no de `test_data`.

`TestStep`: `step_number: int` (≥ 1, consecutivo desde 1), `action: str`, `expected_result: str | None`.

`RequirementTestCaseLink`: `requirement_code: str`, `status: RelationStatus` (**siempre `pending`** al salir de P6), `validation_method: str | None` (`None` al salir de P6), `validation_notes: str | None` (`None` al salir de P6: el soporte CP–RF está diferido, D-18).

**Invariantes**

- El LLM no inventa requisitos: todo `requirement_code` enlazado debe existir en la **unidad de contexto** que originó el caso.
- Un RF puede tener varios CP y un CP puede enlazar varios RF.

---

### 1.4 Modelos de aplicación

#### 1.4.1 `GenerationContext` y `ContextUnit`

El `GenerationContext` es el contenedor de una generación y está formado por **unidades funcionales independientes**. Con clustering habilitado, cada unidad corresponde a un clúster (o a una subunidad de ese clúster si debe dividirse para respetar el límite de tokens); sin clustering, las unidades se construyen agrupando RF en lotes que respetan el límite de tokens; las HU de origen acompañan como contexto (D-39). P6 procesa cada unidad mediante una solicitud independiente al LLM. Los resultados se reúnen bajo la misma `generation_id`; no se acumula un único contexto global de todos los grupos.

`GenerationContext`

| Campo | Tipo | Notas |
|---|---|---|
| `generation_id` | UUID | |
| `output_spec` | `TestCaseOutputSpec` | Estructura esperada del caso de prueba (común a todas las unidades). |
| `instructions_version` | str | Versión de las instrucciones de P5 (construcción de contexto). No es la variante de prompt de P6 (D-38). |
| `strategy` | str | `by_cluster` o `by_user_story`. `by_user_story` significa «sin clustering: lotes de RF con HU de origen» (D-39). Una unidad puede subdividirse por límite de tokens. **[Resuelta D-12, modificada por D-39]** |
| `units` | tuple[`ContextUnit`] | Puede ser vacía solo con `by_cluster` y D-36 (clustering sin ningún RF asignado). Con `by_user_story`, mínimo 1. |

`ContextUnit`

| Campo | Tipo | Notas |
|---|---|---|
| `unit_id` | str | Identificador estable dentro de la generación, por ejemplo `U-001`. |
| `label` | str | Nombre del clúster, lote de RF o subunidad. |
| `cluster_label` | int \| None | `None` si la unidad no proviene de un clúster. En subunidades se conserva el clúster de origen. |
| `requirements` | tuple[`ContextRequirement`] | RF **objetivo** de la unidad (`code`, `description`). Mínimo 1. |
| `context_requirements` | tuple[`ContextRequirement`] | RF de **contexto**: pertenecen al cluster de la unidad pero son objetivo en otro (D-31). No pueden enlazarse desde los casos generados. Puede ser vacía. En `by_user_story` siempre es vacía (D-39). |
| `user_stories` | tuple[`ContextUserStory`] | Referencias y contenido relevante de las HU de origen, incluidos fragmentos enriquecidos que aporten contexto a la generación. Cada HU aparece una sola vez por unidad. |
| `requirement_to_stories` | mapping[str, tuple[str]] | Relaciones RF→HU por código, sin repetir texto. |
| `prerequisites` | tuple[`ContextRequirement`] | **Solo contexto:** RF prerrequisito que no pertenecen a la unidad. No pueden enlazarse desde los casos generados. Opcional. **[Pendiente D-17]** |
| `token_estimate` | int | Estimación del tamaño de la unidad. |
| `exceeds_limit` | bool | `True` si no se pudo reducir por debajo del límite (ver P5). |

`ContextUserStory`: `code`, `original_text`, componentes identificados (`role`, `objective`, `benefit`) y secciones relevantes (`content_sections`). P5 selecciona el contenido pertinente sin eliminar la relación con la HU original.

**Invariantes**

- Todo RF **objetivo** aparece como objetivo en **exactamente una** unidad. Con clustering, son objetivo los RF asignados a algún cluster; los de `unassigned_requirement_codes` no entran en ninguna unidad (D-32). Sin clustering, todos los RF son objetivo y se reparten en lotes; cada RF aparece como objetivo en una sola unidad (D-39).
- Los textos de HU y RF no se duplican dentro de una unidad: se referencian por código.
- Una unidad contiene solo los RF/HU relevantes para ella.

#### 1.4.2 `TestCaseOutputSpec`

Especificación de la estructura que el LLM debe devolver y que P6 valida. En código tiene dos campos: `version` (versión de la especificación) y `json_schema` (esquema JSON que se entrega al LLM). El esquema se genera desde `P6LlmResponse` con `default_output_spec()`, de modo que la especificación y la validación no pueden divergir. Las reglas del esquema son:

| Campo del caso | Obligatorio | Regla |
|---|---|---|
| `title` | sí | No vacío. |
| `objective` | no | |
| `preconditions` | no | Lista de cadenas; vacía por defecto. |
| `test_data` | no | Objeto `TestData` con solo `inputs` y `notes` (D-26); claves desconocidas no se admiten. |
| `steps` | sí | ≥ 1 paso, cada uno con `action` no vacío. |
| `expected_result` | sí | No vacío. |
| `requirement_codes` | sí | ≥ 1; todos presentes en la unidad. |

Campos como prioridad, tipo (positivo/negativo/límite) o etiquetas **no existen en el esquema actual**. Añadirlos requiere migración. **[Pendiente D-13]**

#### 1.4.3 Borradores producidos por el LLM

| Borrador | Producido en | Campos |
|---|---|---|
| `RequirementDraft` | P2 | `description`, `user_story_codes`, atributos descriptivos opcionales, `evidence` y `unspecified_information`. `source_text` puede ser `None` cuando no pueda delimitarse un fragmento literal. |
| `TestCaseDraft` | P6 | Los campos de `TestCaseOutputSpec` (`requirement_codes` en lugar de vínculos). |

Sobres de la respuesta cruda del LLM (se validan con `model_validate_json()` antes de convertirse en contratos de salida):

| Sobre | Etapa | Campos | Validación con contexto |
|---|---|---|---|
| `P2LlmResponse` | P2 | `classifications` (mínimo 1), `requirements: tuple[RequirementDraft]` (puede ser vacía, D-29) | Los `user_story_codes` deben pertenecer a las HU enviadas en la llamada. |
| `P6LlmResponse` | P6 | `test_cases: tuple[TestCaseDraft]` (mínimo 1) | Los `requirement_codes` deben ser RF objetivo de la unidad. Una respuesta sin casos es `LLM_INVALID_OUTPUT` y se reintenta. |

`P6UnitOutput` (resultado aceptado de una unidad de P6): `unit_id`, `test_cases: tuple[TestCase]`. Expone `to_rpc_payload()` para `persist_p6_unit`; `P6Output.test_cases` se deriva de las unidades.

#### 1.4.4 Metadatos de ejecución y errores

`StageMetadata` (común a todas las etapas; no es un artefacto funcional):

| Campo | Tipo | Notas |
|---|---|---|
| `stage_key` | `StageKey` | |
| `started_at`, `completed_at` | datetime | Se reflejan en `generation_stages`. |
| `warnings` | tuple[`StageWarning`] | `generation_stages.warnings` (D-35). `StageWarning`: `code`, `message`, `details`. |
| `llm_runs` | tuple[`LlmRunInfo`] | Solo etapas con LLM (P2, P6). `generation_stages.llm_runs` (D-35). |
| `config_used` | dict | `generation_stages.runtime_info` (D-34). **No** modifica `config_snapshot`. |

En código, la etapa devuelve un `StageResult` (`warnings`, `llm_runs`, `runtime_info`, `skip_remaining`) y el orquestador lo persiste al completar la etapa. `skip_remaining=True` marca `skipped` todas las etapas posteriores (D-29).

`LlmRunInfo`: `provider`, `model`, `prompt_version`, `input_tokens`, `output_tokens`, `attempts`, `latency_ms`, `unit_id | None`. `prompt_version` es la variante concreta ejecutada (p. ej. `contexto@p6-v1`, D-38).

`StageError` (se refleja en `generation_stages.error_code` y `generation_stages.error_message`, D-28). Cualquier otra excepción se registra con `error_code=INTERNAL_ERROR` y un mensaje genérico. `StageError` **no** lleva la etapa: la aporta el orquestador, que sabe qué etapa está ejecutando y escribe el error en la fila de `generation_stages` correspondiente.

| Campo | Tipo | Notas |
|---|---|---|
| `code` | str | Ver tabla de errores por etapa. |
| `message` | str | Apto para persistir y mostrar. Sin datos sensibles ni texto completo del documento. |
| `retryable` | bool | |
| `details` | dict \| None | |

---

### 1.5 Contratos por etapa

Todos los `PxInput` incluyen `generation_id`. En las tablas, **Oblig.** indica si el campo debe estar presente.

#### P1. Procesamiento, segmentación y estructuración de historias de usuario

| | |
|---|---|
| **Estado** | Siempre se ejecuta. |
| **Tecnología** | Procesamiento determinista y expresiones regulares. Sin LLM. |
| **Responsabilidad** | Identificar unidades de historia, conservar el contenido original y estructurar señales explícitas sin decidir si la historia es funcional. |

**`P1Input`**

| Campo | Tipo | Oblig. |
|---|---|---|
| `generation_id` | UUID | sí |
| `document` | `SourceDocument` | sí |
| `config` | `P1Config` (`rules_version`, `language` = `es`, `story_delimiter_pattern`, `max_story_chars`) | sí |

**`P1Output`**

| Campo | Tipo | Notas |
|---|---|---|
| `user_stories` | tuple[`UserStory`] | Todas las historias segmentadas, con su texto original y estado de procesamiento. |
| `unresolved_fragments` | tuple[`UnresolvedFragment`] | Fragmentos conservados que no pudieron asociarse con confianza a una HU. |
| `valid_count`, `warning_count`, `invalid_count` | int | Resumen de procesamiento estructural. |
| `metadata` | `StageMetadata` | |

**Responsabilidades de P1**

1. Extraer/recibir el texto del documento y segmentarlo en unidades candidatas a HU mediante delimitadores, saltos de línea, identificadores, numeración, encabezados y patrones reconocibles.
2. Reconocer formatos simples y enriquecidos. No asumir que todas las historias siguen «Como [rol], quiero [funcionalidad], para [beneficio]» ni que contienen rol, acción y beneficio.
3. Aplicar regex para reconocer patrones formales y ayudar a segmentar o identificar campos cuando estén explícitos. Las regex no determinan si una historia describe una funcionalidad válida.
4. Conservar íntegramente `original_text`. La normalización se limita a generar representaciones auxiliares; nunca reescribe la fuente.
5. Reconocer y conservar, cuando sea posible, secciones como criterios de aceptación, reglas de negocio, precondiciones, condiciones, restricciones, excepciones y resultados esperados. No descartarlas por no ser parte de la plantilla tradicional.
6. Mantener el orden de aparición y asignar códigos HU deterministas por generación.
7. Señalar fragmentos que no puedan segmentarse con confianza, sin eliminarlos silenciosamente.

**Segmentación**

La estrategia combina señales configurables y no depende de una sola frase inicial. Se consideran, según estén presentes:

- Delimitadores explícitos configurados (`---`, `===`, `***`, etc.).
- Identificadores y encabezados (`HU-01`, `US-01`, «Historia de usuario 1»).
- Numeración o viñetas que indiquen el inicio de una unidad.
- Líneas en blanco y cambios de bloque.
- Marcadores tradicionales («Como…», «quiero…», «para…») como señales útiles, pero no obligatorias.
- Encabezados de secciones subordinadas (por ejemplo, criterios de aceptación) que deben asociarse a la historia correspondiente y no tratarse automáticamente como una HU independiente.

Las reglas deben evitar tanto unir historias distintas como separar una historia de sus criterios, reglas o restricciones. Si la segmentación resulta incierta, P1 conserva el fragmento y genera una incidencia de advertencia para revisión posterior. `max_story_chars` puede actuar como límite operativo configurable, pero superar ese límite no autoriza a descartar contenido: debe producirse un error controlado o una estrategia de división documentada.

**Estructuración**

- `role`, `objective` y `benefit` se extraen únicamente cuando los marcadores y límites puedan reconocerse de forma fiable.
- Para historias simples, `original_text` puede ser la única información estructurada disponible inicialmente.
- Para historias enriquecidas, P1 conserva y etiqueta secciones reconocibles sin exigir que todas estén presentes.
- Las secciones desconocidas o no clasificables permanecen en el texto original y no se eliminan.
- P1 no interpreta semánticamente si una petición es funcional, ambigua, fuera de alcance o requiere aclaración. Esa decisión corresponde a P2.

**Validación y estados**

| Situación | Resultado |
|---|---|
| Unidad segmentada y conservada correctamente | `valid` |
| Unidad conservada con delimitación o estructura parcialmente incierta | `valid_with_warnings` |
| Contenido vacío, ilegible o imposible de tratar como unidad por un fallo de procesamiento | `invalid` o error de etapa, según el caso |
| Ausencia de «Como», rol, «quiero» o beneficio | No invalida por sí sola |
| Criterios de aceptación, reglas o restricciones asociados | Se conservan y vinculan a la HU; no se ignoran |
| Texto que no puede asociarse con seguridad a una HU | Se conserva como fragmento no resuelto/incidencia; no se descarta silenciosamente |

Los estados de P1 expresan la calidad del procesamiento estructural, no la clasificación funcional. Una HU `valid` puede ser clasificada en P2 como `requiere_aclaracion` o `no_aplicable`.

**Regla de salida:** P1 entrega a P2 todas las unidades de historia que haya podido conservar, incluidas las que tengan advertencias. Los fragmentos que no sean procesables se reportan explícitamente. P1 solo falla cuando no puede obtener texto utilizable o no puede identificar ninguna unidad procesable, según los errores definidos.

**Errores:** `DOCUMENT_UNREADABLE`, `EMPTY_DOCUMENT`, `NO_STORIES_FOUND`, `STORY_SEGMENTATION_FAILED`.

**Ejemplos conceptuales**

- Simple: «El usuario puede recuperar su contraseña». No requiere rol ni beneficio explícitos.
- Tradicional: «Como usuario, quiero recuperar mi contraseña para volver a acceder». Los componentes pueden extraerse por patrón.
- Enriquecida: historia con descripción, criterios de aceptación, reglas y restricciones. P1 conserva y asocia cada sección a la historia.
- Ambigua: se conserva como HU y P2 determina si requiere aclaración.

**Alcance de idioma y formatos:** v1 procesa español. PDF y DOCX se convierten a texto antes de aplicar la segmentación; las particularidades de extracción (encabezados, pies, estilos y listas) se atienden en el adaptador documental. La lógica de P1 no debe asumir que cada salto de línea equivale a una historia.

---

#### P2. Clasificación de HU y extracción de requisitos funcionales (LLM)

| | |
|---|---|
| **Estado** | Siempre se ejecuta sobre las HU procesables entregadas por P1. |
| **Puerto** | `RequirementAnalyzer` (abstracción del componente de análisis basado en LLM). |
| **Responsabilidad** | Determinar la aplicabilidad funcional de cada HU y, cuando corresponda, extraer cero, uno o varios RF respaldados por su contenido. |

**Clasificación de HU**

Cada HU se clasifica individualmente en una de estas categorías exactas:

| Categoría | Significado | Tratamiento |
|---|---|---|
| `candidata_funcional` | Describe o implica un comportamiento/servicio que el sistema debe proporcionar y del que pueden derivarse requisitos funcionales. | Se analiza para extraer RF. Puede producir cero, uno o varios RF si el contenido no permite identificar un comportamiento suficientemente especificado. |
| `requiere_aclaracion` | Puede corresponder a una necesidad funcional, pero la información es ambigua, insuficiente, contradictoria o no permite determinar con confianza el comportamiento esperado. | Se conserva sin completar vacíos mediante suposiciones; se registran los aspectos que requieren aclaración. |
| `no_aplicable` | No expresa un requisito funcional del sistema dentro del alcance del proceso (por ejemplo, texto contextual, informativo o ajeno a una funcionalidad). | No genera RF; se conserva la clasificación y su justificación. |

La clasificación se basa en el significado del contenido completo, incluidos criterios de aceptación, reglas, condiciones y restricciones asociados. No depende de que la HU tenga rol, verbo en primera persona o plantilla específica. La categoría no se deduce de la validación estructural de P1.

**`P2Input`**

| Campo | Tipo | Oblig. |
|---|---|---|
| `generation_id` | UUID | sí |
| `user_stories` | tuple[`UserStory`] | sí. Todas las HU procesables de P1 (`valid` y `valid_with_warnings`); las `invalid` no entran. |
| `config` | `P2Config` (`prompt_version`, `llm`: proveedor/modelo/parámetros, `max_stories_per_call` y configuración de validación/reintentos que se confirme) | sí |

**`P2Output`**

| Campo | Tipo | Notas |
|---|---|---|
| `classifications` | tuple[`StoryClassification`] | Una clasificación por HU procesada, con categoría, justificación y elementos que requieren aclaración cuando corresponda. |
| `requirements` | tuple[`FunctionalRequirement`] | RF extraídos. Las relaciones RF–HU se expresan mediante `user_story_codes`. |
| `quality` | tuple[`RequirementQualityAssessment`] | Evaluaciones de calidad, si se ejecutan; no sustituyen la clasificación. |
| `findings` | tuple[`RequirementFinding`] | Hallazgos informativos, como información faltante o fragmentos sin cobertura. |
| `stories_without_requirements` | tuple[str] | HU sin RF; debe interpretarse junto con su clasificación, no como error automático. |
| `metadata` | `StageMetadata` | Incluye `LlmRunInfo`. |

`StoryClassification`: `user_story_code: str`, `category: StoryClassificationCategory`, `rationale: str`, `clarification_items: tuple[str]`, `evidence: tuple[RequirementEvidence]`. Se persiste en `user_stories.classification`, `classification_rationale` y `clarification_items` (D-27); `evidence` solo vive en memoria.

`StoryClassificationCategory`: `candidata_funcional`, `requiere_aclaracion`, `no_aplicable`.

**Extracción de RF**

1. Analizar la historia completa y las secciones asociadas que P1 haya identificado; el texto original siempre está disponible como referencia.
2. Una HU puede producir cero, uno o varios RF. La cantidad depende de los comportamientos funcionales distintos respaldados por el contenido, no de una división mecánica por verbos o conjunciones.
3. Cada RF describe un comportamiento funcional específico. Cuando una HU contiene varios comportamientos independientes, pueden representarse como RF separados, manteniendo la misma HU de origen.
4. Una HU `candidata_funcional` puede generar RF incompletos si existe un comportamiento identificable, pero no deben completarse los datos ausentes mediante inferencias no respaldadas.
5. Una HU `requiere_aclaracion` no debe convertirse artificialmente en un RF completo. Si se puede identificar una parte funcional inequívoca, puede extraerse con sus limitaciones explícitas; de lo contrario, no genera RF y se registran las aclaraciones necesarias.
6. Una HU `no_aplicable` no genera RF.
7. No fusionar requisitos solo porque sus descripciones sean similares. La identidad y trazabilidad de cada RF deben mantenerse.

**Evidencia, información faltante y trazabilidad**

- Cada RF debe referenciar una o más HU existentes en la entrada de P2.
- Los atributos extraídos (actor, objetivo, precondiciones, reglas, criterios de aceptación, condiciones, restricciones y resultados esperados) solo se informan si están explícitos o inequívocamente respaldados por el texto.
- Diferenciar entre información explícita, información no especificada y aspectos que requieren aclaración. No inventar precondiciones, reglas de negocio, validaciones, datos de entrada ni resultados esperados.
- `source_text` y `evidence` deben conservar fragmentos literales cuando puedan delimitarse. Si no existe un fragmento único, mantener la referencia a la HU y registrar esa limitación en lugar de fabricar una cita.
- Una HU sin RF no es automáticamente un fallo: puede ser `no_aplicable`, `requiere_aclaracion` o una candidata funcional cuya especificación no permita derivar un RF completo. La salida debe permitir distinguir estos casos.

**Invariantes de salida**

1. Cada HU de entrada tiene exactamente una clasificación.
2. Cada `user_story_code` referenciado por un RF existe en la entrada de P2.
3. Los códigos de RF son únicos y asignados por el pipeline, nunca por el LLM.
4. `description` no está vacía y expresa un comportamiento respaldado por la evidencia disponible.
5. Los atributos opcionales no respaldados permanecen ausentes/no especificados.
6. Una HU puede producir 0, 1 o varios RF; no se impone correspondencia 1:1.
7. No se fusionan RF por similitud semántica en esta etapa.

**Errores:** `LLM_UNAVAILABLE`, `LLM_INVALID_OUTPUT` (tras agotar reintentos), `INVALID_STORY_REFERENCE`.

**Cero RF (D-29):** `NO_REQUIREMENTS_EXTRACTED` **no es un error**, sino un aviso. P2 queda `completed` con ese aviso, P3–P7 quedan `skipped` y la generación termina `completed`. La explicación al usuario es la clasificación de cada HU (D-27).

**Persistencia:** al terminar, P2 llama a `persist_p2_requirements` (una transacción): clasificación en `user_stories`, RF en `functional_requirements` y vínculos en `user_story_requirements`.

**Diseño extensible del clasificador**

En v1, la clasificación se realiza mediante LLM. El contrato `StoryClassification` debe mantenerse independiente del mecanismo utilizado para producirla, de modo que en el futuro puedan evaluarse alternativas como embeddings, SVM o regresión logística sin cambiar los consumidores de P2. No se implementan esos clasificadores en esta versión.

**Referencia normativa:** ISO/IEC/IEEE 29148:2018 se toma como referencia para la especificación y calidad de requisitos, así como para su trazabilidad. No se interpreta como una lista de campos obligatorios que deban existir en cada RF de este modelo. La completitud de un RF se evalúa según la información disponible y el propósito de especificación, sin inventar datos ausentes.

---

#### P3. Generación de embeddings

| | |
|---|---|
| **Estado** | `skipped` si `semantic_clustering_enabled=false`. |
| **Puerto** | `EmbeddingGenerator`. |

**`P3Input`**

| Campo | Tipo | Oblig. |
|---|---|---|
| `generation_id` | UUID | sí |
| `requirements` | tuple[`FunctionalRequirement`] | sí |
| `config` | `P3Config` (modelo, normalización, `input_template`, tamaño de lote) | sí |

**`P3Output`**

| Campo | Tipo | Notas |
|---|---|---|
| `model_info` | `EmbeddingModelInfo` | |
| `embeddings` | tuple[`RequirementEmbedding`] | **Un vector por RF.** |
| `metadata` | `StageMetadata` | |

**Invariantes:** `len(embeddings) == len(requirements)`; dimensión uniforme; sin `NaN`.

**Errores:** `EMBEDDING_PROVIDER_UNAVAILABLE`, `EMBEDDING_DIMENSION_MISMATCH`, `EMBEDDING_INVALID_VECTOR`.

#### P4. Clustering semántico

| | |
|---|---|
| **Estado** | `skipped` si `semantic_clustering_enabled=false`. |
| **Puerto** | `ClusteringAlgorithm`. |

**`P4Input`**

| Campo | Tipo | Oblig. |
|---|---|---|
| `generation_id` | UUID | sí |
| `requirements` | tuple[`FunctionalRequirement`] | sí |
| `embeddings` | `P3Output` (modelo + vectores) | sí |
| `config` | `P4Config` (algoritmo, métrica, parámetros) | sí |

**`P4Output`**

| Campo | Tipo | Notas |
|---|---|---|
| `clusters` | tuple[`SemanticCluster`] | |
| `unassigned_requirement_codes` | tuple[str] | RF sin grupo. |
| `algorithm_info` | `ClusteringAlgorithmInfo` (`name`, `metric`, `params`, `embedding_model`) | Para reproducibilidad. |
| `metadata` | `StageMetadata` | |

**Invariantes**

1. Todo RF de la entrada aparece en alguna asignación **o** en `unassigned_requirement_codes`. P4 nunca descarta RF.
2. `label` único por cluster.
3. Los embeddings corresponden exactamente a los RF recibidos.

**Errores:** `EMBEDDING_REQUIREMENT_MISMATCH`, `CLUSTERING_FAILED`.

**Pocos RF (D-32):** `INSUFFICIENT_REQUIREMENTS` **deja de ser un error**: si hay menos RF de los que el algoritmo necesita, todos quedan en `unassigned_requirement_codes` y P4 termina `completed` con ese aviso. Lo que ocurre después en P5–P7 lo fija D-36 (ver P5).

**Persistencia:** al terminar, P4 llama a `persist_p4_clusters` (una transacción): `clusters`, `cluster_requirements` y `unassigned_requirements`.

#### P5. Construcción del contexto estructurado

| | |
|---|---|
| **Estado** | Siempre se ejecuta. Sin LLM. |
| **Tecnología** | Lógica determinista de composición y estimación de tokens. |

**`P5Input`**

| Campo | Tipo | Oblig. | Notas |
|---|---|---|---|
| `generation_id` | UUID | sí | |
| `user_stories` | tuple[`UserStory`] | sí | Solo las que originaron RF. |
| `requirements` | tuple[`FunctionalRequirement`] | sí | |
| `clustering` | `P4Output` \| None | **no** | `None` si P3/P4 fueron omitidas (R2). |
| `output_spec` | `TestCaseOutputSpec` | sí | |
| `config` | `P5Config` (`max_tokens_per_unit`, `strategy`, `instructions_version`, `include_prerequisites`) | sí | |

**`P5Output`**

| Campo | Tipo | Notas |
|---|---|---|
| `context` | `GenerationContext` | |
| `metadata` | `StageMetadata` | |

**Comportamiento**

- Con `clustering`: P5 crea una unidad por clúster. Los RF sin grupo **no** forman unidad y no generan CP por ahora (D-32); siguen guardados y visibles.
- **RF en varios clusters (D-31):** el RF es objetivo solo en el cluster con mayor `similarity_to_centroid`; en los demás entra como contexto adicional. Desempate (misma similitud o sin valor): el cluster con menor `label`.
- Si una unidad excede `max_tokens_per_unit`, P5 la divide en subunidades del mismo clúster, procurando no separar RF que compartan HU cuando sea viable. Cada RF tiene una única unidad objetivo de generación; los RF/HU relacionados que no sean objetivo pueden incluirse como contexto sin convertirse en objetivos duplicados. Se conserva la pertenencia al clúster de origen.
- Sin `clustering` (D-39): P5 agrupa los RF en lotes que respetan `max_tokens_per_unit`; cada unidad incluye los RF objetivo del lote y las HU de origen como contexto. No hay `cluster_label` ni `context_requirements` de clúster. Las HU pueden repetirse como contexto si sus RF caen en lotes distintos.
- Si una unidad mínima no cabe en el límite, se conserva con `exceeds_limit=True` y se registra advertencia. P6 la trata como error de unidad (sin enviar una solicitud que exceda deliberadamente el límite).

**Invariantes:** completitud de RF en unidades; sin texto duplicado; referencias por código resolubles.

**Errores:** `EMPTY_CONTEXT` (sin clustering, o con clustering y RF asignados, cuando hay RF objetivo y aun así no se puede construir ninguna unidad; no aplica con cero RF, D-29, ni con cero RF asignados, D-36), `UNRESOLVED_REFERENCE`, `TOKEN_LIMIT_UNSATISFIABLE`.

**Ningún RF asignado a un cluster (D-36, resuelta con la opción a):** con clustering, si P4 deja todos los RF en `unassigned_requirement_codes`, no hay RF objetivo. Aplica **solo con clustering**. Sin clustering no se emite `INSUFFICIENT_CONTEXT`: P5 produce al menos una unidad o falla con `EMPTY_CONTEXT`. **No es un fallo:**

| Etapa | Estado |
|---|---|
| P1–P4 | `completed` (P4 con aviso `INSUFFICIENT_REQUIREMENTS` si corresponde) |
| P5 | `completed` con aviso `INSUFFICIENT_CONTEXT` y `GenerationContext.units` vacía |
| P6 – P7 | `skipped` |
| Generación | `completed` |

Los RF siguen guardados en `unassigned_requirements` y visibles en la API (D-32). El contrato de P5 admite cero unidades solo con `by_cluster`; con `by_user_story` exige al menos una (ver `cierre_documental.md`).

#### P6. Generación de casos de prueba funcionales (LLM)

| | |
|---|---|
| **Estado** | Se ejecuta si P5 produjo al menos una unidad; `skipped` con cero RF (D-29) o cero unidades **solo por D-36**. |
| **Puerto** | `TestCaseGenerator`. |

**Selección de prompt (D-38).** `P6Config.prompt_version` identifica la familia/versión. P6 resuelve la variante con `context.strategy`:

- `by_cluster` → `contexto`
- `by_user_story` → `contexto_sin_clustering`

Ambas comparten `TestCaseOutputSpec`. La variante ejecutada se registra en `LlmRunInfo.prompt_version` (p. ej. `contexto@p6-v1`) y en `runtime_info`. El resolvedor está en `ai_service/pipeline/prompts/p6.py`.

**`P6Input`**

| Campo | Tipo | Oblig. |
|---|---|---|
| `generation_id` | UUID | sí |
| `context` | `GenerationContext` | sí |
| `config` | `P6Config` (`prompt_version` (familia; la variante se resuelve por `context.strategy`), `llm`, `max_retries`, `on_unit_failure`) | sí |

**`P6Output`**

| Campo | Tipo | Notas |
|---|---|---|
| `test_cases` | tuple[`TestCase`] | Códigos `CP-001`… globales y consecutivos. |
| `uncovered_requirement_codes` | tuple[str] | RF para los que no se generó ningún caso. Es una advertencia, no cobertura. |
| `failed_units` | tuple[`UnitFailure`] | `unit_id`, `error_code`, `message`. Describe el fallo de unidad; no implica que se descarten los resultados persistidos de unidades anteriores. |
| `metadata` | `StageMetadata` | Incluye `LlmRunInfo` por unidad. |

**Invariantes**

1. Todo vínculo `requirement_code` pertenece a la unidad de origen del caso.
2. Todos los vínculos salen en `pending` y sin `validation_method`.
3. Pasos consecutivos desde 1; código de CP único.
4. Una respuesta que no cumple `TestCaseOutputSpec` se reintenta; agotados los reintentos, la unidad se marca como fallida.
5. Un RF de `prerequisites` (solo contexto) no puede aparecer en `requirement_links`.
6. El soporte del vínculo CP–RF está **diferido** (D-18): P6 no calcula ningún score y deja `validation_notes` en `None`.
7. Los códigos `CP-xxx` se asignan solo a los casos de la respuesta **aceptada** de una unidad: los reintentos no consumen códigos.
8. Los `requirement_codes` repetidos en un mismo caso se eliminan antes de persistir (la PK de `requirement_test_cases` los rechazaría). `persist_p6_unit` también los elimina.
9. `test_data` debe cumplir `TestData` (solo `inputs` y `notes`, D-26); si no, la respuesta es `LLM_INVALID_OUTPUT` y se reintenta.

**Errores:** `LLM_UNAVAILABLE`, `LLM_INVALID_OUTPUT`, `UNIT_GENERATION_FAILED`, `NO_TEST_CASES_GENERATED` (solo cuando hay unidades y no se genera ningún CP; con cero RF o cero unidades **solo por D-36** P6 está `skipped`, D-29 y D-36).

**Ejecución y persistencia incremental (D-15 resuelta):** P6 procesa las unidades secuencialmente en v1. Cada unidad completada persiste sus casos de prueba y vínculos de forma atómica mediante `persist_p6_unit`: se guardan todos los artefactos de esa unidad o ninguno. Si una unidad falla, se reintenta hasta `max_retries`; si el fallo persiste, P6 termina y la generación global queda `failed`. Las unidades completadas antes del fallo y sus resultados persistidos se conservan. Se registra `unit_id`, código de error y mensaje apto para consulta; los detalles internos sensibles quedan en logs. No se implementa reanudación automática en v1. `P6Output.failed_units` describe la unidad fallida si el contrato devuelve un resultado de etapa; el estado terminal de la etapa sigue siendo fallido.

#### P7. Evaluación de resultados

| | |
|---|---|
| **Estado** | Se ejecuta cuando P6 se ejecutó; `skipped` si P2 no extrajo RF (D-29) o si P5 no produjo unidades **solo por D-36**. |
| **Bloqueante** | **No** (D-33): si falla, queda `failed` con su `error_code` y la generación termina `completed`. |
| **Responsabilidad** | Calcular métricas y guardarlas en `generation_metrics` (y sus hallazgos en `metric_findings`). Es la única etapa que escribe ahí. |

**Métricas v1 (D-37, `formula_version = "v1"`).** Cada métrica es una fila de `generation_metrics` con `metric_name`, `metric_value`, `numerator`, `denominator` y `formula_version`. Todas se calculan sobre la generación actual.

| `metric_name` | Numerador | Denominador | Notas |
|---|---|---|---|
| `requirement_coverage` | RF con al menos un vínculo `validated` | Total de RF | Solo `validated` cuenta como cobertura (R7). Recién salida de P6 vale 0, porque todos los vínculos son `pending`. |
| `proposed_requirement_coverage` | RF con al menos un vínculo `pending` o `validated` | Total de RF | Cobertura propuesta por el LLM. **No** es cobertura (R7); se muestra aparte. Los vínculos `rejected` no cuentan. |
| `story_coverage` | HU no `invalid` con al menos un RF | HU no `invalid` | |
| `cases_per_requirement` | Vínculos CP–RF no `rejected` | Total de RF | Promedio de CP por RF. |
| `unassigned_ratio` | RF en `unassigned_requirements` | Total de RF | **Solo con clustering habilitado.** Sin clustering no se inserta la fila (no aplica; ni 0 ni `null`). |

- Si el denominador es 0, `metric_value` es `null` y `numerator`/`denominator` se guardan igual. Con D-29 y D-36 P7 está `skipped`, así que en la práctica el total de RF nunca es 0.
- Un cambio en cualquiera de estas fórmulas exige nueva `formula_version`.
- La versión evolucionada (reglas de rechazo, contención, etc.) queda fuera del alcance. El contrato `P7Input`/`P7Output` en código se escribe en el cambio de contratos posterior.

---

### 1.6 Validadores deterministas y calibración

**Principio de diseño** (tomado de CLAST y ASTER, adaptado a texto): el LLM **propone**, una regla determinista **verifica**, y el artefacto original no se modifica. Un LLM puede inventar contenido; una comprobación por código no depende del LLM y es repetible. Se aplican dos ideas:

1. **Anclaje** (CLAST): cada artefacto generado debe poder apuntar a un fragmento del artefacto del que procede.
2. **Contexto por dependencias** (ASTER): al generar, el LLM recibe también los prerrequisitos que lo orientan, en vez de solo el texto aislado.

#### 1.6.1 Dónde se aplica cada validador

| Etapa | Validador | Qué verifica | Resultado | Estado |
|---|---|---|---|---|
| P1 | Conservación y segmentación | `original_text` permanece intacto; las secciones reconocidas apuntan a fragmentos del original. No se exige plantilla ni extracción de todos los componentes. | Incidencias de segmentación/anclaje; no invalidar por ausencia de rol o beneficio | **[Propuesta]** |
| P2 | Anclaje del RF | `source_text` aparece en la HU referenciada. | Criterio `grounding`; hallazgo `ungrounded` | **[Propuesta]** |
| P2 | Cobertura de la HU | Cada fragmento del objetivo está cubierto por algún RF. | Hallazgo `uncovered_fragment` | **[Propuesta]** |
| P2 | Pistas de atomización | Coordinaciones (y, e, comas, "así como") entre verbos u objetos distintos. | Hallazgo `decomposition_candidate` (pista, **no** división automática) | **[Pendiente D-20]** |
| P5 | Dependencias entre RF | Cadena de RF prerrequisito inyectada en la unidad. | `ContextUnit.prerequisites` | **[Pendiente D-17]** |
| P6 | Anclaje del caso | `requirement_codes` ⊂ RF de la unidad; los prerrequisitos no se enlazan. | Rechazo del vínculo | **[Propuesta]** |
| P6 | Soporte del vínculo CP–RF | Similitud léxica entre el caso y el RF enlazado. | — | **Diferido (D-18).** No forma parte de v1. |

P3 y P4 ya tienen sus invariantes en 1.5 y no necesitan un validador adicional.

#### 1.6.2 Evidencia y respaldo del RF en la HU (P2)

**Principio.** Cada RF y cada atributo que se extraiga deben estar respaldados por el contenido de una o más HU de origen. Cuando se pueda delimitar un fragmento literal, se registra en `source_text` y/o `evidence`; cuando no sea posible, se conserva la referencia a la HU y se explicita la limitación. No se debe fabricar un fragmento para satisfacer el contrato.

**Validación determinista.** Para los fragmentos literales disponibles, un validador comprueba que el texto aparece en la HU referenciada, tolerando únicamente diferencias de formato previamente definidas (espacios, normalización Unicode y mayúsculas). Una coincidencia aproximada puede servir como señal para revisión, pero no debe convertir automáticamente una paráfrasis en evidencia literal.

**Atributos no especificados.** La ausencia de precondiciones, reglas, condiciones, restricciones, criterios de aceptación o resultados esperados no es un error de extracción por sí misma. El modelo debe mantenerlos ausentes y, cuando sean relevantes para la precisión del requisito o su posterior prueba, registrarlos en `unspecified_information` o `clarification_items`.

**Cobertura.** La revisión de cobertura debe considerar el contenido funcional completo de la HU y las secciones asociadas, no únicamente un campo `objective` extraído mediante una plantilla. Los fragmentos relevantes que no queden representados por ningún RF se reportan como hallazgos para análisis; no se fuerza la creación de requisitos que el texto no respalde.

**Límite.** La coincidencia textual demuestra respaldo textual, no garantiza que la interpretación semántica sea correcta. La clasificación y la revisión semántica de P2 siguen siendo necesarias.

#### 1.6.3 Pistas de atomización (P2)

La atomización no debe aplicarse por cada verbo o conjunción (pre-diseño, P2). Una regla (por ejemplo, buscar coordinaciones con un analizador de dependencias como spaCy) solo puede **sugerir** candidatos: se pasan al LLM como pista en el prompt y se registran como `decomposition_candidate`. La decisión de dividir sigue siendo del LLM.

Recomendación: empezar solo con el anclaje y la cobertura, y dejar las reglas de atomicidad para cuando exista un conjunto etiquetado (D-20).

#### 1.6.4 Dependencias entre RF (P5 y P6)

Para probar "editar perfil" suele hacer falta antes "iniciar sesión". El clustering agrupa por similitud, no por precedencia, así que no captura esa relación. Además, un RF interno o no observable (por ejemplo "el sistema valida el token") se prueba a través de otro RF visible para el usuario.

- `FunctionalRequirement.depends_on` es opcional y vive en memoria (no hay tabla).
- P5 añade a cada `ContextUnit` los prerrequisitos que no pertenecen a la unidad, en `prerequisites`, como **solo contexto**.
- P6 los usa para redactar precondiciones y pasos, pero **no puede enlazar** casos a ellos.
- No se permiten ciclos; si se detecta uno, se ignora la dependencia y se emite advertencia.
- Cómo se obtiene `depends_on` (LLM en P2, reglas o en P5) queda en D-17. Para v1 puede omitirse.

#### 1.6.5 Validación empírica de criterios

Los umbrales o criterios automáticos de respaldo y cobertura no se fijan por analogía con otros trabajos. Si se incorporan como controles operativos, deberán calibrarse con un conjunto representativo y anotado, separando datos de calibración y validación. La clasificación funcional y la decisión de que una HU requiere aclaración no deben reducirse a un umbral de coincidencia textual.

La calibración de métricas y umbrales concretos queda pendiente de contar con ejemplos etiquetados y de demostrar que el control mejora la detección de información no respaldada sin penalizar requisitos válidos expresados mediante paráfrasis.

#### 1.6.6 Límites

- La comprobación de evidencia verifica que los atributos y fragmentos citados del RF tienen respaldo en el texto; no garantiza por sí sola que la interpretación semántica sea correcta. Reduce las alucinaciones, no las elimina.
- Cualquier score heurístico que se incorpore debe documentarse como señal de apoyo y no como probabilidad calibrada de error.

---

### 1.7 Matriz de flujo de artefactos

| Artefacto | Lo produce | Lo consume | Persistencia |
|---|---|---|---|
| `SourceDocument` | Puerto de extracción (previo a P1) | P1 | `documents` + Storage (el texto no se guarda) |
| `UserStory` | P1 | P2, P5 | `user_stories` |
| `StoryClassification` | P2 | API (explica HU sin RF) | `user_stories.classification*` · D-27 |
| `FunctionalRequirement` | P2 | P3, P4, P5, P6 | `functional_requirements` + `user_story_requirements` |
| `RequirementQualityAssessment`, `RequirementFinding` | P2 | (informativo) | **Sin tabla** · D-06 |
| `EmbeddingSet` | P3 | P4 | **Sin tabla**; en memoria · D-09 |
| `SemanticCluster`, asignaciones | P4 | P5 | `clusters` + `cluster_requirements` |
| RF sin cluster | P4 | API | `unassigned_requirements` · D-32 |
| `GenerationContext` | P5 | P6 | **Sin tabla**; derivado y reproducible · D-12 |
| `TestCase`, `TestStep`, vínculos | P6 | API de resultados, validación RF–CP | `test_cases` + `test_steps` + `requirement_test_cases` |
| Métricas y hallazgos de evaluación | P7 | API de métricas | `generation_metrics` + `metric_findings` · D-33 |
| `StageMetadata` / estado | Todas | Orquestador, API | `generation_stages` (estado, tiempos, `error_code`, `error_message`, `warnings`, `llm_runs`, `runtime_info`) · D-28, D-35. `config_snapshot` queda fijo desde la creación (D-34). |

**Momento de persistencia (D-30).** Cada etapa guarda su resultado al terminar y de forma atómica, para que la API muestre resultados parciales si una etapa posterior falla:

| Etapa | Cómo se guarda |
|---|---|
| P1 | Un único `insert` masivo en `user_stories` (una sola sentencia: atómica sin RPC). |
| P2 | RPC `persist_p2_requirements`. |
| P3 | Nada (embeddings en memoria, D-09). |
| P4 | RPC `persist_p4_clusters`. |
| P5 | Nada (contexto derivado, D-12). |
| P6 | RPC `persist_p6_unit`, una llamada por unidad (D-15). |
| P7 | Inserción en `generation_metrics` / `metric_findings`. |

Las RPC reciben las referencias por `code` y las traducen a `id` dentro de la generación; un código inexistente aborta toda la llamada. Su comportamiento ante una segunda llamada con el mismo payload (idempotencia) está abierto en T-01, y el manejo de HU duplicadas en `persist_p2_requirements` en T-02 (ver `cierre_documental.md`).

---

### 1.8 Trazabilidad en los contratos

```text
HU (code) ──► RF.user_story_codes ──► ContextUnit.requirement_to_stories
                 │                            │
                 ├─► RequirementEmbedding     ▼
                 └─► ClusterAssignment ──► ContextUnit ──► TestCase.requirement_links
```

Todo el recorrido se resuelve por `code` dentro de una misma `generation_id`. No se supone 1:1 en ninguna relación.

---

### 1.9 Decisiones pendientes de esta sección

| ID | Decisión | Opciones | Recomendación |
|---|---|---|---|
| **D-01** | ¿Quién extrae el texto del archivo (TXT/PDF/DOCX) y quién segmenta en HU individuales? | (a) Puerto de extracción previo + segmentación dentro de P1. (b) Etapa previa fuera de P1–P7. | (a): extraer texto con un puerto previo (no es una etapa, porque las etapas están fijadas en BD) y segmentar en P1, que ya es determinista. |
| **D-02** | Nombres `action`/`goal` en BD frente a `objective`/`benefit` | Mantener nombres de BD en el dominio, o mapear. | **Resuelta.** Dominio con `objective`/`benefit`; el mapeador asocia *Means* ("quiero") → `action` y *Ends* ("para") → `goal`, igual que el dataset original (*Role / Means / Ends*). |
| **D-03** | Política de fragmentos/HU no procesables | Detener todo / conservar con advertencia / excluir | Conservar toda unidad que pueda segmentarse; usar `invalid` solo ante fallo real de procesamiento. P2 clasifica funcionalmente las HU procesables. |
| **D-04** | Valores de `validation_status` | Texto libre actual | **Resuelta.** `valid`, `valid_with_warnings`, `invalid`, con `check` en BD y `enum` en el openapi. |
| **D-05** | ¿Persistir `normalized_text`, secciones e incidencias de P1? | Memoria/logs, columna nueva, tabla nueva | Mantener `original_text` y las columnas existentes en BD; las estructuras auxiliares viven en memoria en v1. Evaluar persistencia solo si un requisito de consulta/UI la justifica. |
| **D-06** | Dónde guardar evaluación de calidad y hallazgos de RF | Solo memoria; `generation_metrics`+`metric_findings` (exige métrica padre); tabla nueva; columna JSONB en RF | Memoria en v1 y decidir tras definir las métricas de tesis. |
| **D-07** | Escala y método de los scores de calidad | LLM, reglas, mixto | Mantener `value: float \| None` y `method`. Para los criterios por regla, usar escala 0–1 y calibrar el umbral con 1.6.5. |
| **D-08** | Duplicados: ¿en P2 o con embeddings? | P2 solo LLM/léxico; o informe de pares similares en P4 | No fusionar RF en P2. Los pares similares pueden analizarse posteriormente mediante embeddings, sin alterar su identidad ni trazabilidad. |
| **D-09** | Persistencia de embeddings | Memoria; columna `vector`/pgvector; almacén externo | Memoria entre P3 y P4; solo metadatos del modelo en `config_snapshot`. Sin reanudación en v1. |
| **D-10** | Nombre/descripción de cada cluster (`name` es NOT NULL) | Determinista (`Grupo {label}`) o generado por LLM | Determinista en v1, para no añadir otra llamada al LLM. |
| **D-11** | RF no asignados (*outliers*) | Unidad propia en P5; descartarlos; forzar asignación | **Reemplazada por D-32.** |
| **D-12** | Estrategia de unidades de generación y contexto de P5 | Contexto global único; unidades por clúster/HU; persistir el contexto | **Resuelta, modificada por D-39.** Con clustering: unidad por clúster, dividida en subunidades si excede el límite. Sin clustering: unidades por lotes de RF con HU de origen como contexto (D-39). Cada unidad tiene una solicitud independiente a P6. Contexto derivado no persistido; resultados de P6 sí se persisten incrementalmente. |
| **D-13** | Campos extra del caso de prueba (prioridad, tipo, etiquetas) | Migración, o dentro de `test_data` | v1 alineado al esquema actual; ampliar después con migración. |
| **D-14** | Validación de vínculos RF–CP | P6 deja `pending` y un paso determinista rechaza códigos inexistentes | **Resuelta para v1.** La estructura de `test_data` se trata aparte en D-26. P6 valida la estructura del borrador y que los códigos RF existan y pertenezcan a los RF objetivo de la unidad. Los vínculos persistidos salen `pending`, sin `validation_method`; la validación semántica/real queda para revisión manual o una futura P7. Solo `validated` cuenta como cobertura (R7). |
| **D-15** | Fallo de una unidad de P6 y conservación de resultados previos | Fallar etapa y descartar resultados; continuar con otras unidades; persistencia incremental | **Resuelta.** Procesar secuencialmente en v1; reintentar la unidad según `max_retries`; si persiste, detener P6 y marcar la generación `failed`. Conservar las unidades ya completadas. Persistencia atómica por unidad (todo o nada), registrar causa del fallo y no reanudar automáticamente en v1. |
| **D-16** | Valores admitidos de `method_type` | Texto libre actual | Definir catálogo (`llm_pipeline` ya aparece en los ejemplos). |
| **D-17** | Dependencias entre RF (`depends_on`): ¿se incluyen y quién las obtiene? | Omitir en v1; LLM en P2; reglas; LLM en P5 | Omitir en v1 y evaluarlas cuando se mida la calidad de P6. |
| **D-18** | Conjunto etiquetado y umbrales (`grounding`, cobertura, soporte CP–RF) | Definir tamaño, quién etiqueta y dónde se guarda | **Soporte CP–RF: diferido.** Se retira `link_support_threshold` de `P6Config` y P6 no anota `validation_notes` en v1. Si se retoma: umbral configurable, nota informativa no bloqueante y `formula_version` registrada, con una propuesta de cálculo revisada antes de implementarla. Para `grounding` y cobertura se mantiene: no fijar umbrales hasta disponer de datos etiquetados. |
| **D-19** | Tratamiento de RF con evidencia insuficiente | Regenerar automáticamente; conservar marcado; excluir; pedir aclaración | No asumir regeneración automática ni exclusión. Conservar la limitación y la evidencia disponible; los criterios de revisión/reintento se definirán tras validar el comportamiento del LLM. |
| **D-20** | Reglas de atomicidad (pistas de descomposición) | Empezar ahora; posponer | Posponer hasta tener un conjunto etiquetado de "atómico / no atómico". |
| **D-21** | Tratamiento de criterios de aceptación y secciones enriquecidas | Ignorarlos; conservarlos y usarlos en P2; usarlos solo para evaluación | Conservarlos y asociarlos a la HU en P1; P2 los utiliza como evidencia para clasificar y extraer RF. No se añaden columnas persistentes en v1 sin justificar una migración. |
| **D-22** | ¿Persistir las incidencias y fragmentos no resueltos de P1? | Solo en memoria/logs; columna JSONB; tabla nueva | Solo en memoria/logs en v1. Si posteriormente deben consultarse desde el frontend o auditarse entre sesiones, evaluar una ampliación de persistencia. |
| **D-23** | Reglas para historias en inglés | Definirlas ahora; posponer | Posponer. En v1 los datasets en inglés se traducen y se estructuran en español antes de subirlos. Al añadirlas, los patrones irán en configuración por idioma. |
| **D-24** | ¿Se procesan las HU al subir el documento (`POST /documents`) o en el pipeline? | Todo en la subida; todo en P1; separado | **Separado.** La subida acepta el **archivo** (tipo, tamaño, legible, no vacío) y no crea HU. El pipeline asume un archivo ya aceptado, pero **no** que tenga historias ni que sean válidas: eso lo valida P1 en cada generación. Opcional más adelante: vista previa que reutilice la lógica de P1 sin persistir (`x-status: proposed`). |
| **D-25** | Reglas específicas de PDF y DOCX (encabezados, pies de página, viñetas, numeración, estilos) | Definirlas ahora; posponer | Posponer. En v1 se extrae su texto y se trata como un TXT. |
| **D-26** | Estructura de `test_data` | Libre; claves fijas | **Resuelta.** JSON con solo `inputs` (objeto clave-valor) y `notes` (texto opcional). `preconditions` y `expected_result` son campos de primer nivel del caso (`test_cases.preconditions`, `test_cases.expected_result`) y no se repiten en `test_data`. El esquema `TestData` del openapi y el contrato se ajustan en el cambio de contratos posterior. |
| **D-27** | Persistencia de la clasificación de P2 | Solo memoria; columnas en `user_stories` | **Resuelta.** `classification` (con `check`), `classification_rationale`, `clarification_items`. Expuestas en `UserStory`. |
| **D-28** | Código de error por etapa | Solo mensaje; columna `error_code` | **Resuelta.** `generation_stages.error_code`; el orquestador propaga `StageError.code` y `message`. |
| **D-29** | Cero RF extraídos | Fallar en P5; completar con aviso | **Resuelta.** P2 `completed` con aviso `NO_REQUIREMENTS_EXTRACTED`; P3–P7 `skipped`; generación `completed`. |
| **D-30** | Momento y atomicidad de la persistencia | Al final; por etapa; por etapa vía RPC | **Resuelta.** Cada etapa guarda al terminar; P2, P4 y P6 mediante RPC transaccionales (ver 1.7). |
| **D-31** | RF en varios clusters | Duplicar objetivo; elegir uno | **Resuelta.** Objetivo en el cluster de mayor `similarity_to_centroid` (desempate: menor `label`); contexto en los demás. |
| **D-32** | RF sin cluster | Descartar; unidad `ungrouped`; guardar sin generar CP | **Resuelta.** Se guardan en `unassigned_requirements` y se muestran; por ahora no generan CP. `INSUFFICIENT_REQUIREMENTS` pasa a aviso. |
| **D-33** | P7 | Siempre `skipped`; siempre se ejecuta | **Resuelta.** Siempre se ejecuta (salvo D-29 y D-36), calcula métricas (D-37) y no es bloqueante. Modifica R1. |
| **D-34** | `config_snapshot` | Fijo al inicio; fusionar durante la ejecución | **Resuelta.** Fijo al inicio (lo solicitado); lo ejecutado va a `generation_stages.runtime_info`. |
| **D-35** | Metadatos de etapa | Solo logs; columnas en `generation_stages` | **Resuelta.** Columnas `warnings`, `llm_runs`, `runtime_info`, expuestas en `GenerationStage`. |
| **D-36** | Con clustering, ningún RF queda asignado a un cluster | (a) P5/P6 `completed` con 0 unidades y aviso; (b) volver a unidades por HU para esa generación; (c) fallar con `EMPTY_CONTEXT` | **Resuelta: (a), solo con clustering.** P5 `completed` con aviso `INSUFFICIENT_CONTEXT` y 0 unidades; P6 y P7 `skipped`; generación `completed`. No es un fallo y no se emite `EMPTY_CONTEXT`. El contrato de P5 admite cero unidades en este caso. |
| **D-37** | Métricas de P7 v1 | Lista sugerida; ampliada | **Resuelta.** `requirement_coverage` (solo `validated`), `proposed_requirement_coverage` (aparte), `story_coverage`, `cases_per_requirement` y `unassigned_ratio` (solo con clustering; sin clustering no se registra). `formula_version = "v1"`. Fórmulas en P7. |
| **D-38** | Variante de prompt de P6 según clustering | Una sola instrucción; dos variantes | **Resuelta.** `contexto` con clustering; `contexto_sin_clustering` sin clustering. Se resuelve por `context.strategy`; mismo `TestCaseOutputSpec`; se registra en `LlmRunInfo`/`runtime_info`. |
| **D-39** | Unidades sin clustering | Por HU; lotes de RF; una por RF | **Resuelta.** Sin clustering, P5 agrupa RF en lotes por tokens; cada unidad lleva RF objetivo + HU de origen; `cluster_label=None`, `context_requirements=()`. Modifica D-12. |

---

### 1.10 Siguientes secciones previstas

1. Reglas de validación y manejo de errores (política de reintentos y mapeo `StageError` → API).
2. Contrato común de ejecución de etapa y contexto de ejecución (`PipelineState`).
3. Casos de uso y orquestador (transiciones de estado, etapas omitidas, P7).
4. Puertos de infraestructura.
5. Tecnologías y adaptadores iniciales.
6. Persistencia y seguimiento.
7. Estrategia de pruebas y criterios de aceptación.

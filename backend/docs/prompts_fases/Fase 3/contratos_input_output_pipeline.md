Quiero que escribas los contratos de entrada y salida de las etapas P1 a P6 del pipeline,
sin implementar la lógica de ninguna etapa.

## Fuentes de verdad (léelas completas antes de escribir código)
1. docs/pipeline_design.md: descripción de cada etapa, reglas R1-R10 y decisiones D-01 a D-35.
2. docs/openapi.yaml: esquemas expuestos por la API (UserStory, TestData, ClusterList, GenerationStage, etc.).
3. supabase/schema.sql: tablas y, sobre todo, las firmas y el payload esperado de las RPC
   persist_p2_requirements, persist_p4_clusters y persist_p6_unit.
4. El código actual en ai_service/pipeline/, en especial pipeline/stages/base.py
   (StageError, StageMetadata, StageResult), pipeline/context.py y pipeline/catalog.py.

Si dos fuentes se contradicen, no elijas una por tu cuenta: lístalas y pregúntame.

## Qué debes crear
En ai_service/pipeline/contracts/ (un módulo por etapa más common.py):
- P1Input / P1Output, P2Input / P2Output, ..., P6Input / P6Output, como modelos Pydantic v2.
- Los tipos auxiliares que necesiten (por ejemplo, el objeto de una HU, de un RF,
  de un cluster, de una unidad de generación, de un caso de prueba y de un paso).
- Un tipo para TestData con las claves del openapi (preconditions, inputs, expected_results, notes).
- En common.py: la clase base común y lo que se repita entre etapas (enums de clasificación,
  estado de validación, etc.), alineados con los check de schema.sql y los enum del openapi.

## Reglas de modelado
- Usa exclusivamente modelos Pydantic v2 (BaseModel) para los contratos de P1 a P6 y sus tipos
  auxiliares. No uses dataclasses, SQLAlchemy ni otras librerías de modelado para estos contratos.
- Define una clase base común en contracts/common.py con ConfigDict(frozen=True, extra="forbid").
  No actives strict. Todos los contratos heredan de ella.
- Usa tuple para las colecciones. Si un campo es un diccionario (por ejemplo TestData.inputs),
  frozen no lo hace inmutable por dentro: déjalo anotado con un comentario y menciónalo en el resumen.
- Los contratos son estructuras de datos validadas: sin acceso a BD, sin llamadas al LLM,
  sin lógica de negocio, sin importar FastAPI ni Supabase.
- Las invariantes del diseño se expresan con field_validator / model_validator
  (códigos no vacíos, enums válidos, sin duplicados en requirement_codes, TestData con la forma correcta).
- No modifiques ni reemplaces StageError, StageMetadata ni StageResult, independientemente de
  cómo estén definidos. No los incrustes dentro de los contratos.
- La decisión de usar Pydantic aplica solo a los contratos P1-P6; no implica refactorizar las
  estructuras internas existentes del pipeline (PipelineContext, StageDefinition, fakes de test).
- Los contratos no se reutilizan como modelos de la API (schemas/); si coinciden en forma,
  se mantienen como clases separadas.
- Los Output de P2, P4 y P6 exponen to_rpc_payload(), limitado a transformar y serializar
  (model_dump(mode="json")) al formato que espera la RPC, sin ejecutar persistencia.
- Cada contrato lleva un docstring corto: qué etapa lo produce, qué etapa lo consume
  y a qué tabla o RPC corresponde.
- Nombres, campos y enums idénticos a los del diseño y el openapi (no inventes campos).
- Para la salida del LLM (P2 y P6) debe poder usarse model_validate_json() sobre el contrato
  correspondiente. Si la salida cruda del LLM difiere de lo que se persiste, propón un modelo
  intermedio y señálame dónde hace falta.

## Reglas del diseño que los contratos deben reflejar
- Las HU con validation_status='invalid' no entran en P2Input.
- Si P2 produce cero RF, el contrato lo permite (tupla vacía) sin error;
  el efecto sobre P3-P7 lo decide el orquestador, no el contrato.
- Un RF pertenece a un único cluster; en los demás aparece solo como contexto (D-31).
  El contrato de P5/P6 distingue los RF objetivo de los RF de contexto.
- Los RF sin cluster van en un campo separado (unassigned) en el Output de P4 (D-32);
  no generan casos de prueba.
- Los requirement_codes de un caso de prueba no admiten duplicados.
- No incluyas P7: sus métricas aún no están definidas.

## Proceso
1. Lee las fuentes y devuélveme un resumen breve con:
   - la lista de contratos que vas a crear y los campos de cada uno;
   - cómo StageResult transporta la salida de una etapa, y si es compatible con los contratos nuevos;
   - dónde harías falta un modelo intermedio para la salida del LLM;
   - las discrepancias o dudas entre las fuentes.
2. Espera mi confirmación antes de escribir código.
3. Después implementa los contratos y sus pruebas.

## Pruebas (pytest)
- Cada contrato se construye con datos válidos, y asignar un campo lanza ValidationError.
- Los campos desconocidos (extra) lanzan ValidationError.
- Los casos de invariante inválida lanzan el error esperado.
- Los to_rpc_payload() generan JSON serializable que coincide con la forma esperada por cada RPC.
- Los contratos de salida del LLM generan model_json_schema() sin error.
- Un test que verifique que los ejemplos del openapi (TestData, UserStory, ClusterList)
  son compatibles con los contratos correspondientes.

## Fuera de alcance
No modifiques schema.sql, openapi.yaml, el orquestador, los repositorios ni pipeline_design.md.
No implementes la lógica de las etapas ni llames al LLM. Si crees que algún cambio fuera de
contracts/ es necesario, propónmelo en vez de hacerlo.

## Entrega
- Lista de archivos creados.
- Resultado de las pruebas.
- Cualquier decisión que tomaste por ambigüedad, marcada claramente para que yo la revise.

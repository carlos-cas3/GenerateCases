Implementé los contratos de P1 a P6 con todas las propuestas que aprobaste. Pasan 305 pruebas (las 73 existentes y 232 nuevas). Además, pasé los payloads reales por las tres RPC en un Postgres temporal y los datos se guardaron bien. No hice commit.

Archivos creados

ai_service/pipeline/contracts/
- __init__.py
- common.py: la base ContractModel (frozen=True, extra="forbid", sin strict), los enums, los formatos de código (HU-001, RF-001, CP-001, U-001) y los tipos compartidos SourceSpan, RequirementEvidence, LlmSettings y TestData.
- p1.py … p6.py: los contratos de cada etapa, con los nombres del diseño. Incluye lo que aprobaste en las decisiones:

┌────────────────┬──────────────────────────────────────────────────────────────────────────────────┐
│    Decisión    │                                   Dónde quedó                                    │
├────────────────┼──────────────────────────────────────────────────────────────────────────────────┤
│ D3             │ P6UnitOutput con to_rpc_payload(); P6Output.test_cases se deriva de las unidades │
├────────────────┼──────────────────────────────────────────────────────────────────────────────────┤
│ D4             │ ContextUnit.context_requirements                                                 │
├────────────────┼──────────────────────────────────────────────────────────────────────────────────┤
│ D5             │ Validación con contexto (user_story_codes / target_codes) en los sobres del LLM  │
├────────────────┼──────────────────────────────────────────────────────────────────────────────────┤
│ Sobres del LLM │ P2LlmResponse y P6LlmResponse                                                    │
└────────────────┴──────────────────────────────────────────────────────────────────────────────────┘

tests/
- contract_factories.py: un escenario coherente de P1 a P6, del que salen 51 contratos válidos.
- test_contracts.py: inmutabilidad, rechazo de campos extra, ida y vuelta por JSON, esquemas JSON de la salida del LLM y compatibilidad con el openapi (ejemplo de TestData y valores de los enums).
- test_contracts_invariants.py: las invariantes de cada etapa.
- test_contracts_rpc.py: compara to_rpc_payload() con las claves que leen las funciones de schema.sql. Las claves se extraen de la propia SQL, así que si cambia una RPC, el test falla.

No toqué StageResult, StageError ni nada fuera de contracts/ y tests/.

Diccionarios que frozen no hace inmutables

Están anotados con un comentario en el código:
- LlmSettings.parameters
- TestData.inputs
- P4Config.params
- ClusteringAlgorithmInfo.params
- TestCaseOutputSpec.json_schema
- ContextUnit.requirement_to_stories

⚠️ Decisiones que tomé por ambigüedad (revísalas)

1. TestCaseOutputSpec tiene dos campos, version y json_schema, y el esquema se genera desde P6LlmResponse con default_output_spec(). El diseño solo describía reglas en una tabla, sin campos.
2. UserStory: valid_with_warnings exige al menos una incidencia, y una HU valid no puede tener incidencias de severidad error.
3. P1Output exige al menos una HU que no sea invalid, que es la condición en la que P1 lanza NO_STORIES_FOUND.
4. P2Output, todo comprobado de forma estricta:
   - stories_without_requirements debe coincidir exactamente con las HU clasificadas que no tienen RF.
   - Una HU no_aplicable no puede generar RF.
   - Hay una sola evaluación de calidad por RF.
5. P5Input:
   - Solo admite las HU que originaron RF.
   - Los RF del clustering deben coincidir con los de entrada.
   - by_cluster exige que haya clustering.
6. ContextUnit rechaza HU que ningún RF de la unidad referencia.
7. Los vectores de embeddings rechazan también los infinitos, no solo NaN.
8. Un SemanticCluster necesita al menos un RF asignado.
9. P6Output.failed_units admite como máximo una unidad, porque P6 se detiene en el primer fallo (D-15).
10. Unidades vacías: P6UnitOutput.test_cases puede venir vacío, pero P6LlmResponse exige al menos un caso. En la práctica, si el LLM no devuelve casos, se trata como LLM_INVALID_OUTPUT y se reintenta.
11. TestData en el payload incluye todas las claves con sus valores por defecto ([], null) en lugar de omitir las vacías.

Propuestas fuera de contracts/ (no las implementé)

- Paso de datos entre etapas: añadir a PipelineContext un campo opcional por etapa (p1: P1Output | None, …).
- persist_p6_unit no inserta validation_notes. La anotación opcional de soporte CP–RF del diseño (D-18) no llegaría a la BD.
- pipeline_design.md debería documentar context_requirements, P6UnitOutput, P2LlmResponse, P6LlmResponse y la nueva forma de TestCaseOutputSpec.
- El StageError del diseño tiene stage_key, pero el del código no.
# Fase 6 — Implementación real de P5 (construcción del contexto estructurado)

> **Estado:** 🔲 pendiente de implementación.
> **Fase anterior:** Fase 5 (P3 embeddings + P4 clustering) — ✅ cerrada en código y pruebas
> (464 tests). Detalle en `docs/prompts_fases/Fase 5/cierre_documental_fase5.md`.
> **Documentos fuente:**
> `docs/pipeline_roadmap.md`,
> `ai_service/pipeline/contracts/p5.py`,
> `ai_service/pipeline/contracts/p1.py` (`UserStory`),
> `ai_service/pipeline/contracts/p2.py` (`FunctionalRequirement`),
> `ai_service/pipeline/contracts/p4.py` (`P4Output`, `SemanticCluster`),
> `ai_service/pipeline/contracts/p6.py` (`default_output_spec`),
> `ai_service/pipeline/context.py`,
> `ai_service/pipeline/stages/__init__.py`,
> `ai_service/config.py`,
> `docs/architecture_patterns.md`.
>
> Este archivo es el **plan de la fase**: decisiones tomadas, trabajo a realizar y criterios
> de cierre. No contiene código. El detalle de lo que se implementó quedará en
> `cierre_documental_fase6.md` al cerrar la fase.

---

## Objetivo de la fase

Que `ContextStage` deje de ser un `StubStage` y ejecute lógica real:

```
P5: P1Output (HU) + P2Output (RF) + P4Output (clusters, puede ser None)
      → agrupa RF por unidad de generación
      → construye GenerationContext
      → escribe context.p5_output
```

Al cerrar la fase, el pipeline con clustering activo produce un `GenerationContext` con unidades
`BY_CLUSTER`; sin clustering, con unidades `BY_USER_STORY`. P6 y P7 siguen siendo stubs.

P5 **no persiste** nada (D-12): su output vive solo en memoria para que P6 lo consuma.

---

## Estado del código relevante al empezar

### Lo que ya existe y no se toca

| Artefacto | Archivo | Observación |
|---|---|---|
| Contrato completo `P5Input / P5Output / GenerationContext / ContextUnit / P5Config` | `pipeline/contracts/p5.py` | Escrito en Fase 3; no se modifica |
| `P4Output` con `clusters`, `unassigned_requirement_codes`, `assigned_requirement_codes()` | `pipeline/contracts/p4.py` | Producido en Fase 5 |
| `FunctionalRequirement` con `user_story_codes` | `pipeline/contracts/p2.py` | La relación RF → HU ya está en el contrato |
| `UserStory` con `role`, `objective`, `benefit`, `content_sections` | `pipeline/contracts/p1.py` | P5 los copia a `ContextUserStory` |
| `default_output_spec(version)` | `pipeline/contracts/p6.py` | Genera el `TestCaseOutputSpec` que P5 incluye en `GenerationContext` |
| `UnitStrategy` enum | `pipeline/contracts/common.py` | `BY_CLUSTER` / `BY_USER_STORY` |
| `PipelineContext` con `p1_output`, `p2_output`, `p4_output`, `p5_output` | `pipeline/context.py` | Regla de lectura documentada; no se modifica |
| `ContextStage` (stub actual) | `pipeline/stages/p5_context.py` | Se reemplaza en T-F6-03 — actualmente hereda de `StubStage` directamente, sin lógica |
| `PENDING_STUB_STAGE_CLASSES` | `pipeline/stages/__init__.py` | Se retira `ContextStage`; se añade `ContextStubStage` |
| Env vars `P5_*` | `config.py` | **No existen aún** — se añaden en T-F6-01 |
| Puerto `PipelineResultsRepository` | `repositories/pipeline_results.py` | P5 no llama a ninguna RPC; no se modifica |
| Factories de P5 en tests | `tests/contract_factories.py` | **Ya existen**: `p5_config()`, `p5_input()`, `context_unit()`, `generation_context()`, `context_unit_without_clustering()`, `generation_context_without_clustering()`, `p5_output()`. Los tests de P5 pueden usarlas directamente como punto de partida. |
| `make_settings` en tests | `tests/conftest.py` | Helper que construye `Settings` con overrides; úsalo para pasar los valores de `P5_*` en los tests de config |

### Lo que se va a crear o modificar

| Artefacto | Archivo | Acción |
|---|---|---|
| Env vars `P5_MAX_TOKENS_PER_UNIT`, `P5_INSTRUCTIONS_VERSION`, `P5_INCLUDE_PREREQUISITES` | `config.py`, `.env.example` | Crear en T-F6-01 |
| `build_p5_config` | `pipeline/stages/__init__.py` | Crear en T-F6-02 |
| `ContextStage` real | `pipeline/stages/p5_context.py` | Reemplazar stub en T-F6-03 |
| `ContextStubStage` | `pipeline/stages/p5_context.py` | Crear al lado de la etapa real — seguir el patrón de `NormalizeStubStage` al final de `p1_normalize.py` y `RequirementsStubStage` al final de `p2_requirements.py` |
| `build_real_stages` | `pipeline/stages/__init__.py` | Añadir P5 real + actualizar stubs en T-F6-02 |
| Pruebas de P5 | `tests/test_p5_context.py` | Crear en T-F6-04 — no existe aún; usar `contract_factories.py` como base |
| Pruebas de wiring | `tests/test_stages_wiring.py` | Extender en T-F6-04 — el archivo ya existe con tests de P1–P4 |
| Roadmap + cierre documental | `docs/pipeline_roadmap.md`, este archivo | Actualizar en T-F6-05 |

### Patrón exacto que sigue cada archivo modificado

Antes de tocar cualquier archivo, leer las implementaciones de referencia:

- **`p5_context.py`**: seguir la estructura de `p4_clustering.py` (etapa real + stub al final).
  P5 es más simple porque no tiene cliente externo.
- **`__init__.py`** (`pipeline/stages`): seguir el patrón de `build_p4_config` para
  `build_p5_config`, y el bloque `p4 = ClusteringStage(...)` dentro de `build_real_stages` para
  instanciar P5.
- **`config.py`**: seguir el patrón de `p4_min_cluster_size` / `p4_min_samples` para las tres
  nuevas env vars.
- **`test_p5_context.py`**: seguir la estructura de `test_p4_clustering.py` (fixture de stage,
  casos positivos y negativos, sin dependencias externas).

---

## Decisiones de la fase

### ✅ Decisiones cerradas (no bloquean la implementación)

#### D-F6-1 — P5 no persiste (D-12 del diseño original)
`GenerationContext` es derivado y vive solo en memoria. No hay RPC de P5. El contrato no tiene
`to_rpc_payload()`. Esta regla viene del diseño original y no cambia.

#### D-F6-2 — Estrategia se deriva de `p4_output`, no de `clustering_enabled`
Siguiendo R-ST-4 (`architecture_patterns.md`): P5 no lee `context.configuration.clustering_enabled`.
Lee `context.p4_output`:
- `p4_output is None` → estrategia `BY_USER_STORY` (clustering estaba desactivado o P3/P4 fueron
  omitidos).
- `p4_output` tiene valor → estrategia `BY_CLUSTER`.

Esto es consistente con el validador de `P5Input` que exige coherencia entre `clustering` y
`config.strategy`.

#### D-F6-3 — RF sin cluster no generan unidad (D-32 / D-36)
Los RF en `P4Output.unassigned_requirement_codes` **no forman una unidad de generación**. P5 los
recoge, emite el aviso `UNASSIGNED_REQUIREMENTS` con sus códigos, y los excluye del
`GenerationContext`. P6 no los verá. La generación termina `completed` (no `failed`). Esta regla
viene de D-32 y D-36 del diseño original.

#### D-F6-4 — `context_requirements` con `BY_CLUSTER`
Con estrategia `BY_CLUSTER`, los RF de **otros clusters** que compartan HU de origen con la unidad
actual se incluyen como `context_requirements` (D-31). P5 puede asumir membresía única (R6 /
H-3 diferido): cada RF pertenece a exactamente un cluster.

Con estrategia `BY_USER_STORY`, `context_requirements` siempre es vacío (el contrato
`GenerationContext` lo valida y lo exige vacío en esta estrategia).

#### D-F6-5 — `prerequisites` vacío en v1
`P5Config.include_prerequisites` existe en el contrato pero en v1 siempre es `False` (D-17). P5
construye todas las unidades con `prerequisites=()`. El campo se conserva en `P5Config` para una
fase futura sin tocar el contrato.

#### D-F6-6 — `token_estimate` y `exceeds_limit`
P5 calcula un **estimado** del tamaño de cada unidad para detectar si supera
`P5Config.max_tokens_per_unit`. El estimado se hace contando caracteres del JSON serializado de
los campos de texto de la unidad (descripción de RF, texto original de HU) dividido por 4 (regla
heurística: ~4 caracteres por token para español/inglés). No se usa una librería de tokenización:
el objetivo es una señal de alerta, no un conteo exacto.

P5 **marca** la unidad con `exceeds_limit=True` y emite un aviso `UNIT_EXCEEDS_TOKEN_LIMIT` con
el `unit_id` afectado. **No parte la unidad ni la descarta**: la decisión de cómo manejar una
unidad grande queda en P6 (que ya recibe el flag) y en una fase futura. Esto evita añadir
lógica de partición en P5 sin un requisito concreto ni pruebas de que sea necesaria con documentos
reales.

> **Decisión abierta en la Fase 3** que se cierra aquí: el roadmap decía "respeta
> `max_tokens_per_unit`" sin definir qué significa eso. Se elige marcar + avisar, no partir.

#### D-F6-7 — Numeración de unidades y orden
Las unidades se numeran `U-001`, `U-002`, … en orden de aparición:
- `BY_CLUSTER`: orden creciente de `cluster.label` (que ya sale ordenado de P4 por diseño).
- `BY_USER_STORY`: orden de aparición de la primera HU del grupo (es decir, el orden de
  `P1Output.user_stories`).

Los códigos `U-xxx` los asigna P5 de forma consecutiva en ese orden, igual que P2 asigna
`RF-xxx` y P6 asigna `CP-xxx`.

#### D-F6-8 — Nombre de la unidad (`label`)
- `BY_CLUSTER`: el `label` de la unidad toma el `name` del cluster (`SemanticCluster.name`), que
  en esta versión es `"Cluster {label}"` (D-A de la Fase 5). En una fase futura P4 o P5 podrían
  asignar un nombre semántico; por ahora se usa el placeholder.
- `BY_USER_STORY`: el `label` toma el código de la primera HU del grupo (p. ej., `"HU-001"`).

#### D-F6-9 — Agrupación `BY_USER_STORY`
Sin clustering, cada HU que haya generado al menos un RF forma su propia unidad de generación.
Los RF de la unidad son todos los que `FunctionalRequirement.user_story_codes` incluye **como
primer código** de esa HU (RF cuyo origen principal es esa HU). Los RF que referencian varias
HU se asignan a la HU con la posición más baja entre sus `user_story_codes`.

> Esto produce una partición limpia sin duplicar RF entre unidades (el contrato de
> `GenerationContext` lo valida: `RF objetivo entre unidades` deben ser únicos).

#### D-F6-10 — `ContextUserStory` y `requirement_to_stories`
Para cada unidad, `user_stories` incluye **todas** las HU referenciadas por algún RF objetivo o
de contexto de esa unidad (desde `FunctionalRequirement.user_story_codes`). El campo
`requirement_to_stories` mapea cada RF a las HU que lo originaron (tal cual vienen en
`FunctionalRequirement.user_story_codes`), tal como exige el validador de `ContextUnit`.

---

## Preguntas abiertas — ✅ todas resueltas

### PA-1 — `P5_INSTRUCTIONS_VERSION` ✅
`"v1"` — consistente con el resto del pipeline (P1, P2).

### PA-2 — `P5_MAX_TOKENS_PER_UNIT` ✅
Default `8000`, ajustable por env var `P5_MAX_TOKENS_PER_UNIT`.

**Riesgos de calibración incorrecta:**

- **Valor demasiado bajo**: muchas unidades quedan marcadas `exceeds_limit=True` sin que haya
  problema real. P6 recibe avisos falsos. En v1 no rompe nada porque el flag es solo informativo,
  pero si en una fase futura P6 decide saltar unidades marcadas se perderían casos de prueba
  válidos.
- **Valor demasiado alto** (el caso peligroso): unidades grandes llegan a P6 sin marcar. El LLM
  recibe un prompt que supera su ventana útil y o bien trunca silenciosamente el contenido, o
  produce una respuesta de baja calidad o incompleta. No hay aviso: los casos de prueba
  generados cubrirán menos RF de los que deberían, o serán incorrectos, sin que el sistema lo
  detecte.

Validar con documentos reales: si unidades con `exceeds_limit=True` funcionan bien en P6, subir
el umbral; si unidades sin marcar producen casos pobres, bajarlo.

### PA-3 — `output_spec` y versión ✅
**Una sola env var `P5_INSTRUCTIONS_VERSION`** para ambas cosas.

`instructions_version` y `output_spec` son los dos elementos que P5 escribe en
`GenerationContext`. Cualquier cambio en uno de los dos produce un `GenerationContext`
diferente, lo que constituye un cambio en P5 como unidad. Para auditoría la pregunta relevante
es "¿con qué versión de P5 se generó este contexto?", no si cambió la agrupación o el esquema
por separado. Una sola versión responde esa pregunta; cuando cambie cualquiera de los dos,
sube `P5_INSTRUCTIONS_VERSION`.

---

## Trabajo a realizar — tareas

### T-F6-01 · Configuración de `P5Config`

Añadir a `ai_service/config.py`:

- `p5_max_tokens_per_unit: int` — env var `P5_MAX_TOKENS_PER_UNIT`, default `8000` (PA-2).
- `p5_instructions_version: str` — env var `P5_INSTRUCTIONS_VERSION`, default `"v1"` (PA-1 y PA-3).
- `p5_include_prerequisites: bool` — env var `P5_INCLUDE_PREREQUISITES`, default `False` (D-F6-5).

`p5_instructions_version` se usa tanto para `GenerationContext.instructions_version` como para
la versión pasada a `default_output_spec(version)`. Una sola env var porque cualquier cambio en
la lógica de agrupación de P5 o en el esquema de salida de P6 produce un `GenerationContext`
diferente, que es lo que identifica esta versión (PA-3).

Actualizar `.env.example` con los tres valores y sus defaults.

No se añade `strategy` a `config.py`: la estrategia se deriva de `p4_output` en la etapa (D-F6-2).

### T-F6-02 · Cableado de dependencias (DI)

En `pipeline/stages/__init__.py`:

1. Añadir `build_p5_config(settings) -> P5Config`. La `strategy` que va en `P5Config` la fija el
   wiring con un valor placeholder; la etapa la sobreescribe según `p4_output`. Alternativa más
   limpia: `P5Config` no lleva `strategy` en la construcción desde `Settings` y la etapa calcula
   la estrategia en tiempo de ejecución. Elegir la que sea más coherente con el contrato.

   > El contrato exige `strategy` en `P5Config`. Por eso `build_p5_config` necesita conocer la
   > estrategia. Opciones: (a) construir dos `P5Config` (uno por estrategia) y elegir en la etapa,
   > o (b) construir un `P5Config` sin `strategy` y añadirlo en la etapa con `model_copy`. La
   > opción (b) es más limpia: un solo objeto de config inmutable que se completa en runtime.
   > **Decisión sugerida:** (b) — `build_p5_config` no recibe `strategy`; la etapa llama a
   > `config.model_copy(update={"strategy": strategy})` antes de construir `P5Input`.

2. Mover `ContextStage` fuera de `PENDING_STUB_STAGE_CLASSES` y añadir `ContextStubStage` en su
   lugar.

3. Extender `build_real_stages` para instanciar `ContextStage` real con su config inyectada. P5
   no recibe ningún cliente externo (no llama a LLM, embeddings ni storage): solo recibe
   `P5Config` por constructor (R-DI-2).

### T-F6-03 · Implementar `ContextStage.run()` (P5)

Pasos de la implementación:

1. **Leer el contexto.** Leer `context.p1_output` y `context.p2_output`. Si `p1_output` o
   `p2_output` es `None`, lanzar `RuntimeError` (igual que P2 ante `p1_output is None`): es un
   invariante del orquestador, no un error controlado.

2. **Determinar la estrategia.** `p4_output = context.p4_output`:
   - `None` → `strategy = UnitStrategy.BY_USER_STORY`
   - con valor → `strategy = UnitStrategy.BY_CLUSTER`

   Construir el `P5Config` efectivo con `config.model_copy(update={"strategy": strategy})`.

3. **Filtrar HU.** Solo las HU no `INVALID` de `p1_output`. (El validador de `P5Input` rechaza
   las `INVALID`.)

4. **Filtrar RF.** Solo los RF de `p2_output.requirements` (puede ser una tupla vacía, pero si
   P5 se ejecuta es porque P2 produjo al menos un RF — D-29 lo garantiza vía `skip_remaining`).

5. **Construir unidades.** Bifurcar según `strategy`:

   - `BY_CLUSTER` — ver §"Lógica de agrupación BY_CLUSTER".
   - `BY_USER_STORY` — ver §"Lógica de agrupación BY_USER_STORY".

6. **Construir `P5Input`** con HU filtradas, RF, `p4_output`, `output_spec` y `P5Config`
   efectivo. Validar con Pydantic (si hay errores de contrato, lanzar `StageError`
   `CONTEXT_BUILD_FAILED`). Siguiendo R-CP-3, `P5Input` se construye desde el contexto, no al
   revés.

7. **Construir `P5Output`** con el `GenerationContext` resultante.

8. **Escribir `context.p5_output`.**

9. **Devolver `StageResult`** con:
   - `warnings`: avisos de RF sin cluster y de unidades que superan el límite de tokens.
   - `runtime_info`: estrategia usada, número de unidades, número de RF cubiertos, número de RF
     sin cluster (si aplica), `instructions_version`.

#### Lógica de agrupación `BY_CLUSTER`

Para cada `SemanticCluster` en `p4_output.clusters` (en orden de `label`):

1. Recoger los `RequirementCode` asignados al cluster (`cluster.assignments`).
2. Para cada código, obtener el `FunctionalRequirement` correspondiente de `p2_output`.
3. Recoger todas las `UserStory` referenciadas por esos RF (`FunctionalRequirement.user_story_codes`).
4. Calcular `context_requirements`: RF de **otros clusters** que compartan al menos una HU de
   origen con algún RF de esta unidad (D-F6-4).
5. Calcular `token_estimate` y `exceeds_limit` (D-F6-6).
6. Construir `ContextUnit` con:
   - `unit_id = f"U-{number:03d}"` (numeración correlativa, D-F6-7).
   - `label = cluster.name` (D-F6-8).
   - `cluster_label = cluster.label`.
   - `requirements`: los RF objetivo como `ContextRequirement`.
   - `context_requirements`: los RF de contexto como `ContextRequirement`.
   - `user_stories`: `ContextUserStory` para cada HU (RF objetivo + contexto).
   - `requirement_to_stories`: mapa de cada RF (objetivo + contexto) a sus `user_story_codes`.
   - `prerequisites = ()` (D-F6-5).

Los RF en `p4_output.unassigned_requirement_codes` no generan unidad (D-F6-3). Si existen,
emitir aviso `UNASSIGNED_REQUIREMENTS` con los códigos.

Si `p4_output.clusters` está vacío (todos los RF sin asignar), `units = ()` es válido para
`BY_CLUSTER` (el contrato lo permite). La generación sigue `completed` con aviso.

#### Lógica de agrupación `BY_USER_STORY`

1. Construir un mapa `HU → [RF]` donde cada RF se asigna a la HU con la posición más baja entre
   sus `user_story_codes` (D-F6-9).
2. Ordenar las HU por posición (que coincide con el orden de `P1Output.user_stories`).
3. Para cada HU que tenga al menos un RF asignado:
   - Recoger sus RF en orden del código (`RF-001`, `RF-002`, …).
   - Construir `ContextUnit` con:
     - `unit_id = f"U-{number:03d}"`.
     - `label = hu.code` (D-F6-8).
     - `cluster_label = None` (el contrato lo exige para `BY_USER_STORY`).
     - `requirements`: los RF como `ContextRequirement`.
     - `context_requirements = ()` (el contrato lo exige para `BY_USER_STORY`).
     - `user_stories`: `ContextUserStory` para la HU (y las demás HU que compartan RF con ella,
       si las hay — `FunctionalRequirement.user_story_codes` puede referenciar varias HU).
     - `requirement_to_stories`: mapa de cada RF a sus `user_story_codes`.
     - `prerequisites = ()`.
4. Nunca hay RF sin asignar en `BY_USER_STORY`: todos los RF de `p2_output` vienen de al menos
   una HU (el validador de `P2Output` lo garantiza).

#### Construcción de `ContextUserStory`

Para cada `UserStory` que forma parte de la unidad, copiar los campos relevantes:
```
ContextUserStory(
    code            = story.code,
    original_text   = story.original_text,
    role            = story.role,
    objective       = story.objective,
    benefit         = story.benefit,
    content_sections = story.content_sections,  # tupla de StorySection, puede ser vacía
)
```

#### Cálculo de `token_estimate`

Sumar la longitud en caracteres de:
- `description` de cada `ContextRequirement` en `requirements` + `context_requirements`.
- `original_text` de cada `ContextUserStory`.

Dividir entre 4 (entero). Ese es el `token_estimate`. Si supera `P5Config.max_tokens_per_unit`,
marcar `exceeds_limit=True`.

### T-F6-04 · Pruebas

Crear `tests/test_p5_context.py` con los siguientes casos (sin dependencias externas: P5 no
llama a ningún cliente):

**Estrategia `BY_CLUSTER`:**
- Happy path: 2 clusters con RF distintos → 2 unidades, `cluster_label` correcto, `label` =
  nombre del cluster, RF objetivo correctos, `context_requirements` poblados cuando hay HU
  compartidas entre clusters.
- RF sin cluster: unidad no generada, aviso `UNASSIGNED_REQUIREMENTS` con los códigos.
- Todos los RF sin asignar: `units = ()`, aviso presente, `StageResult` sin `skip_remaining`.
- `token_estimate` supera el límite: `exceeds_limit=True`, aviso `UNIT_EXCEEDS_TOKEN_LIMIT`.
- `token_estimate` no supera el límite: `exceeds_limit=False`, sin aviso de tokens.

**Estrategia `BY_USER_STORY`:**
- Happy path: 3 HU con RF → 3 unidades, `cluster_label = None`, `context_requirements = ()`.
- RF con múltiples HU: se asigna a la HU con posición más baja; la otra HU aparece en
  `user_stories` y en `requirement_to_stories`.
- Una HU sin RF: no genera unidad (no debe aparecer en el contexto).

**Guardias comunes:**
- `p1_output is None` → `RuntimeError`.
- `p2_output is None` → `RuntimeError`.
- `p4_output is None` → estrategia `BY_USER_STORY` (aunque `config` initial dijera otra cosa).
- `p4_output` presente → estrategia `BY_CLUSTER`.

**Wiring / extremo a extremo** (`tests/test_stages_wiring.py`):
- Documento completo con clustering → P5 produce `GenerationContext` con `strategy=BY_CLUSTER`.
- `clustering_enabled=false` → P5 produce `GenerationContext` con `strategy=BY_USER_STORY`.
- P5 escribe `context.p5_output` y la generación llega a `completed` (P6–P7 siguen siendo stubs).

### T-F6-05 · Actualizar roadmap y cierre documental

- Marcar Fase 6 como ✅ en `docs/pipeline_roadmap.md`.
- Generar `cierre_documental_fase6.md` con decisiones tomadas, supuestos de implementación,
  cualquier divergencia respecto a este plan y advertencias activas.
- Actualizar `PENDING_STUB_STAGE_CLASSES` en el roadmap para que solo liste P6 y P7.

---

## Patrones de arquitectura en esta fase

P5 no introduce ningún patrón nuevo. Aplica los ya registrados en
`docs/architecture_patterns.md`:

| Patrón | Cómo lo usa P5 |
|---|---|
| **Pipeline** (R-PP-1 / R-PP-3 / R-PP-4) | `ContextStage` hereda de `StageBase`, lee del contexto, escribe `p5_output`, devuelve `StageResult` solo con metadatos |
| **Strategy** (R-ST-4) | La bifurcación `BY_CLUSTER` / `BY_USER_STORY` se decide leyendo `context.p4_output is None`, nunca `clustering_enabled`. Las dos variantes de lógica de agrupación son la expresión más completa de este patrón en el pipeline hasta ahora |
| **Dependency Injection** (R-DI-2) | `ContextStage` recibe `P5Config` por constructor; sin ningún cliente externo, es el caso más simple del pipeline |
| **Contract** (R-CP-3 / R-CP-2) | `P5Input` se construye desde el contexto y se valida con Pydantic antes de proceder; las invariantes (HU de RF presentes, RF objetivo únicos entre unidades, `cluster_label` obligatorio en `BY_CLUSTER`) las garantiza el contrato, no la etapa |

**Si durante la implementación se introduce un patrón que no esté en ese catálogo**, añadirlo
en `docs/architecture_patterns.md` antes de hacer el cierre documental (igual que se hizo en
fases anteriores: Fase 5 comprobó explícitamente que no añadía ninguno nuevo y lo dejó anotado
en `cierre_documental_fase5.md` §3).

### Principios SOLID relevantes

De los cinco principios, solo uno requiere atención activa en esta fase:

**SRP a nivel de método.** `ContextStage.run()` decide la estrategia y delega, pero no
implementa directamente la lógica de agrupación. Las dos variantes deben vivir en métodos
privados separados (`_build_by_cluster()` y `_build_by_user_story()`), con `run()` actuando
solo como coordinador. Si ambas variantes se implementan inline en `run()`, el método termina
haciendo dos cosas distintas y se vuelve difícil de probar y mantener.

Los demás se cumplen pasivamente por el diseño existente: LSP porque `ContextStage` respeta
la firma de `StageBase`; DIP porque depende de `P5Config` y los contratos, no de
implementaciones concretas; OCP e ISP no tienen superficie de aplicación en esta etapa.

---

## Orden de ejecución sugerido

```
T-F6-01 (env vars P5_*)       ← no depende de nada; se puede hacer primero
   │
T-F6-02 (DI wiring)           ← necesita las env vars de T-F6-01
   │
T-F6-03 (ContextStage.run())  ← necesita el wiring de T-F6-02
   │
T-F6-04 (pruebas)             ← necesita la etapa de T-F6-03
   │
T-F6-05 (cierre documental + roadmap)
```

---

## Criterios de cierre

La Fase 6 está completa cuando **todos** estos puntos se cumplen:

- [ ] `ContextStage` no hereda de `StubStage` (lógica real implementada).
- [ ] Con clustering activo, produce `GenerationContext` con `strategy=BY_CLUSTER` y una unidad
      por cluster asignado.
- [ ] Sin clustering, produce `GenerationContext` con `strategy=BY_USER_STORY` y una unidad por
      HU con RF.
- [ ] RF sin cluster no generan unidad; se emite aviso `UNASSIGNED_REQUIREMENTS` (D-F6-3).
- [ ] `exceeds_limit` se calcula y se emite aviso `UNIT_EXCEEDS_TOKEN_LIMIT` cuando aplica.
- [ ] `prerequisites = ()` en todas las unidades (D-F6-5, v1).
- [ ] `context_requirements` poblados en `BY_CLUSTER` cuando hay HU compartidas (D-F6-4); vacíos
      en `BY_USER_STORY`.
- [ ] P5 no persiste nada en BD (D-12 / D-F6-1).
- [ ] `config.py` expone `P5_MAX_TOKENS_PER_UNIT`, `P5_INSTRUCTIONS_VERSION` y
      `P5_INCLUDE_PREREQUISITES`.
- [ ] Pruebas de P5 pasan; wiring E2E actualizado; suite completa sin regresión.
- [ ] `pipeline_roadmap.md` actualizado y `cierre_documental_fase6.md` generado.

---

## Reglas del pipeline que aplican a esta fase (referencia rápida)

| Regla | Cómo aplica en Fase 6 |
|---|---|
| D-12 | P5 no persiste: el `GenerationContext` vive solo en `context.p5_output`. |
| D-17 | `prerequisites` vacío en v1; `P5Config.include_prerequisites = False`. |
| D-29 | P5 solo se ejecuta si P2 produjo RF (si no, `skip_remaining` ya dejó P5 en `skipped`). |
| D-31 | Con `BY_CLUSTER`, RF de otros clusters que comparten HU van a `context_requirements`. |
| D-32 / D-36 | RF sin cluster no generan unidad; aviso `UNASSIGNED_REQUIREMENTS`. |
| D-38 | `instructions_version` de P5 ≠ `prompt_version` de P6; son versiones independientes. |
| D-39 | Sin clustering → `BY_USER_STORY`; con clustering → `BY_CLUSTER`. |
| R-PP-3 | P5 escribe `context.p5_output`; P6 lo leerá desde ahí. |
| R-PP-4 | `StageResult` solo lleva `warnings` y `runtime_info`; el contexto viaja en `PipelineContext`. |
| R-ST-4 | P5 no lee `clustering_enabled`; lee `context.p4_output is None`. |
| R-DI-2 | `ContextStage` recibe `P5Config` por constructor; sin clientes externos. |
| R-CP-3 | `P5Input` se construye desde el contexto, no se guarda en él. |

---

## Advertencias heredadas relevantes para esta fase

1. **Calibración de `P5_MAX_TOKENS_PER_UNIT`**: el estimado de tokens (÷4 sobre caracteres) es
   heurístico. Con documentos reales puede quedar desviado respecto al tokenizador del modelo
   de P6. Ajustar por env var tras validar con documentos reales (ver PA-2).

2. **Nombres de cluster como placeholder**: `SemanticCluster.name` es `"Cluster {label}"` (D-A
   de Fase 5). Cuando se use como `label` de la unidad en `BY_CLUSTER`, el usuario verá ese
   nombre en la interfaz. Se puede mejorar en una fase futura sin tocar el contrato (P4 o P5
   podrían asignar un nombre semántico con el LLM).

3. **R6 / D-31 diferido**: el contrato `P4Output` permite que un RF esté en varios clusters, pero
   HDBSCAN produce membresía única. P5 puede asumir eso. Si en el futuro se introduce un
   algoritmo superpuesto, habrá que implementar D-31 (P5 elige en qué cluster es objetivo el RF).

4. **`dict` en modelos frozen** (heredada): `ContextUnit.requirement_to_stories` es un `dict` que
   `frozen=True` no hace inmutable por dentro. P5 debe pasar un dict recién construido al
   contrato, nunca reutilizar un dict que modifica después.

5. **`P5Input` valida que las HU de los RF estén presentes**: si `user_story_codes` de un RF
   referencia una HU que no llegó a P5 (porque era `INVALID`), el validador de `P5Input` lanza
   error (`"RF con HU de origen ausentes"`). Asegurarse de filtrar correctamente las HU antes de
   construir `P5Input`.

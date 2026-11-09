# Patrones de arquitectura — reglas de implementación

> Este documento define los patrones que rigen la arquitectura del proyecto y las
> reglas concretas que toda nueva pieza de código debe respetar.  
> No es documentación histórica: es una referencia activa para desarrollo.

---

## 1. Pipeline Pattern

### Qué es en este proyecto

El orquestador recorre las 7 etapas (P1–P7) en orden fijo, pasando el mismo
`PipelineContext` a cada una. Cada etapa tiene una única responsabilidad y una
interfaz uniforme.

### Reglas

**R-PP-1 — Interfaz uniforme.**  
Toda etapa debe heredar de `StageBase` e implementar exactamente:
```python
async def run(self, context: PipelineContext) -> StageResult | None
```
Nunca cambiar la firma. El orquestador no sabe qué hace cada etapa, solo que
todas hablan el mismo idioma.

**R-PP-2 — El orquestador no conoce los contratos.**  
`PipelineOrchestrator` no debe importar ningún módulo de `pipeline/contracts/`.
La lógica de qué datos necesita cada etapa es interna a cada etapa, no al orquestador.

**R-PP-3 — Los outputs viajan por el contexto.**  
Cada etapa escribe su output en el campo correspondiente de `PipelineContext`
(`p1_output`, `p2_output`, …) y lee los campos que necesita. El orquestador
no transporta datos entre etapas; solo pasa el contexto.

```python
# Correcto — dentro de P2Stage.run()
p1_out = context.p1_output          # lee la etapa anterior
assert p1_out is not None           # garantía de que P1 completó
result = self._process(p1_out)
context.p2_output = result          # deposita su propio output
```

**R-PP-4 — `StageResult` es solo metadatos.**  
`StageResult` transporta `warnings`, `llm_runs`, `runtime_info` y `skip_remaining`.
Nunca datos del dominio (HU, RF, casos de prueba). Los datos del dominio van
siempre en `PipelineContext`.

**R-PP-5 — Terminación anticipada con `skip_remaining`.**  
Si una etapa determina que no tiene sentido continuar (ej: P2 no extrajo RF),
devuelve `StageResult(skip_remaining=True)`. El orquestador marca el resto como
`skipped`. La etapa no llama al orquestador ni conoce las etapas siguientes.

**R-PP-6 — P3 y P4 declaran su dependencia de clustering.**  
Cualquier etapa que solo debe ejecutarse con clustering activo debe declarar:
```python
requires_clustering: ClassVar[bool] = True
```
El orquestador aplica el skip automáticamente. La etapa no comprueba la configuración
por su cuenta.

### Archivos de referencia
- `pipeline/orchestrator.py` — implementación del orquestador
- `pipeline/stages/base.py` — `StageBase`, `StageResult`, `StageError`
- `pipeline/context.py` — `PipelineContext`
- `pipeline/catalog.py` — definición de orden y `blocking`

---

## 2. Strategy Pattern

### Qué es en este proyecto

Hay dos variantes de comportamiento controladas por configuración que se
resuelven sin condicionales dispersos por el código:

- **Estrategia de clustering** (`clustering_enabled`): determina si P3/P4 se
  ejecutan y qué rama sigue P5 para construir las unidades.
- **Variante de prompt de P6** (`UnitStrategy`): selecciona el prompt correcto
  según si se usó clustering o no.

### Reglas

**R-ST-1 — La estrategia de clustering se declara en el catálogo, no en código.**  
P3 y P4 usan `requires_clustering = True`. El orquestador aplica la regla.
Ninguna otra etapa debe leer `context.configuration.clustering_enabled` para
decidir si P3/P4 corrieron — debe leer `context.p4_output is None`.

**R-ST-2 — La variante de prompt se resuelve con `resolve_p6_prompt()`.**  
P6 llama a `resolve_p6_prompt(prompt_version, strategy)` para obtener el prompt
correcto. Nunca seleccionar el archivo de prompt con un `if` inline en la etapa.

**R-ST-3 — Nuevas variantes se añaden al mapeo, no como condicionales.**  
Si se añaden nuevas estrategias, se extiende `_VARIANT_BY_STRATEGY` en
`pipeline/prompts/p6.py` y los enums en `contracts/common.py`. No se añaden
`if/elif` en las etapas.

**R-ST-4 — `P5Input.clustering` es `None` cuando no hay clustering.**  
P5 no comprueba `clustering_enabled`: lee `context.p4_output`. Si es `None`,
construye las unidades con estrategia `by_user_story`. Si no es `None`, usa
`by_cluster`. Esta es la única fuente de verdad para la bifurcación en P5.

### Archivos de referencia
- `pipeline/prompts/p6.py` — `resolve_p6_prompt()`, `P6PromptVariant`
- `pipeline/contracts/common.py` — `UnitStrategy`
- `pipeline/contracts/p5.py` — `P5Input.clustering: P4Output | None`

---

## 3. Dependency Injection

### Qué es en este proyecto

Las dependencias concretas (Supabase, LLM, embeddings) se construyen en un
único punto (`main.py`/`lifespan`) y se inyectan hacia adentro. Las capas
internas nunca instancian infraestructura por su cuenta.

### Reglas

**R-DI-1 — Un único punto de composición.**  
Toda instanciación de infraestructura concreta ocurre en `main.py`/`lifespan`.
Ningún servicio, repositorio, etapa ni orquestador llama a constructores de
clientes de Supabase, LLM o embeddings directamente.

**R-DI-2 — Los servicios reciben dependencias por constructor.**  
```python
# Correcto
class RequirementsStage(StageBase):
    def __init__(self, llm_client: LlmClient, config: P2Config) -> None:
        self._llm = llm_client
        self._config = config

# Incorrecto
class RequirementsStage(StageBase):
    def __init__(self) -> None:
        self._llm = OpenAIClient(api_key=os.getenv("OPENAI_KEY"))  # ❌
```

**R-DI-3 — Los tests inyectan fakes, no mocks de librería.**  
Los tests usan `InMemoryGenerationsRepository`, `InMemoryDocumentsRepository`,
`FakeDocumentStorage` y `FakeLlmClient` (`clients/llm_fake.py`). No parchean
clientes de Supabase ni SDKs de LLM con `unittest.mock`; los adaptadores LLM se
prueban con `httpx.MockTransport`. El extractor tiene `FakeDocumentExtractor`
(`clients/extractor_fake.py`). Cuando se añada `EmbeddingsClient`, su fake
debe vivir en `tests/` o en un módulo `*_fake.py` al lado del puerto.

**R-DI-4 — `create_app()` acepta inyección externa.**  
La firma de `create_app()` debe mantener los parámetros opcionales de
repositorios, storage y `llm_client` para que los tests puedan inyectar fakes
sin Supabase ni proveedor LLM. Al añadir nuevos puertos (embeddings), se añaden
como parámetros opcionales con el mismo patrón.

**R-DI-5 — Los imports de adaptadores en `main.py` son lazy.**  
Los adaptadores Supabase se importan dentro del bloque `if` del `lifespan`,
no a nivel de módulo. Así la aplicación puede arrancarse en tests sin que
Python cargue `supabase-py`.

### Archivos de referencia
- `main.py` — punto único de composición y lifespan
- `api/dependencies.py` — extracción de servicios del `app.state` para FastAPI
- `repositories/in_memory.py` — fakes de repositorio para tests

---

## 4. Adapter Pattern (Puertos y Adaptadores)

### Qué es en este proyecto

Cada dependencia de infraestructura tiene un **puerto** (un `Protocol` de Python
que define el contrato) y uno o más **adaptadores** (clases que implementan ese
contrato para una tecnología concreta).

### Puertos actuales

| Puerto | Módulo | Adaptadores |
|---|---|---|
| `DocumentsRepository` | `repositories/documents.py` | `SupabaseDocumentsRepository`, `InMemoryDocumentsRepository` |
| `GenerationsRepository` | `repositories/generations.py` | `SupabaseGenerationsRepository`, `InMemoryGenerationsRepository` |
| `DocumentStorage` | `clients/storage.py` | `SupabaseDocumentStorage`, `FakeDocumentStorage` (`upload`, `download`, `remove`; P1 usa `download`) |
| `ProgressReporter` | `pipeline/events.py` | `RepositoryProgressReporter` |
| `LlmClient` | `clients/llm.py` | `OpenAILlmClient`, `AnthropicLlmClient`, `OllamaLlmClient` (construidos por `LlmClientFactory`), `FakeLlmClient` |
| `DocumentTextExtractor` | `clients/extractor.py` | `TxtDocumentExtractor`, `PdfDocumentExtractor`, `DocxDocumentExtractor` (repartidos por `CompositeDocumentExtractor` según `FileType`, sin factory), `FakeDocumentExtractor` |

### Puertos pendientes (Fase 4)

| Puerto | Módulo previsto | Usado por |
|---|---|---|
| `EmbeddingsClient` | `clients/embeddings.py` | P3 |

### Reglas

**R-AP-1 — Puerto y adaptador en módulos separados.**  
El puerto (Protocol) vive en el módulo base (`repositories/documents.py`).  
El adaptador Supabase vive en su propio módulo (`repositories/supabase_documents.py`).  
El adaptador de tests vive en `repositories/in_memory.py`.  
Nunca mezclar puerto y adaptador en el mismo archivo.

**R-AP-2 — El puerto no importa infraestructura.**  
Un módulo de puerto (`repositories/documents.py`, `clients/storage.py`, etc.)
solo puede importar: tipos de la librería estándar, schemas de dominio propios
(`schemas/`), y errores de dominio (`core/errors.py`). Excepción acotada: el
puerto `DocumentTextExtractor` importa el enum `FileType` de
`pipeline/contracts/common.py` (solo pydantic/stdlib, sin infraestructura) para no
duplicar el tipo de archivo.  
Nunca importar `supabase`, `postgrest`, `openai`, `httpx` ni ninguna librería
de infraestructura en un módulo de puerto.

**R-AP-3 — Los adaptadores implementan el puerto por duck typing.**  
Python no requiere declarar `class SupabaseX(RepositoryProtocol)`. El
cumplimiento se verifica en runtime por duck typing. No añadir herencia explícita
del Protocol — solo asegurarse de que la firma de cada método coincide exactamente.

**R-AP-4 — Los adaptadores traducen errores al dominio.**  
Un adaptador nunca deja escapar excepciones de infraestructura hacia las capas
internas. `APIError` de postgrest se convierte en `DocumentNotFound`,
`InvalidStateTransition`, etc. antes de salir del adaptador.

```python
# Correcto
except APIError as exc:
    if exc.code == _FK_VIOLATION:
        raise DocumentNotFound() from exc
    raise

# Incorrecto — deja escapar APIError al servicio
except Exception:
    raise  # ❌ el servicio no debe saber que existe postgrest
```

**R-AP-5 — `main.py` es el único punto que importa adaptadores concretos.**  
Ningún servicio, etapa, repositorio ni módulo de dominio debe importar
`SupabaseDocumentsRepository`, `SupabaseGenerationsRepository`,
`SupabaseDocumentStorage` ni ningún adaptador concreto futuro.
Solo `main.py` los importa, y de forma lazy dentro del `lifespan`.

**R-AP-6 — Nombrado consistente.**  
- Puerto: `XRepository`, `XStorage`, `XClient` → en módulo `x.py`
- Adaptador Supabase: `SupabaseXRepository`, `SupabaseXStorage` → en módulo `supabase_x.py`
- Adaptador de tests: `InMemoryXRepository`, `FakeXStorage`, `FakeXClient` → en módulo `in_memory.py` o `x_fake.py`
- Adaptador de proveedor LLM: `{Proveedor}LlmClient` → en módulo `{proveedor}_llm.py`
- Adaptador de extracción por formato: `{Formato}DocumentExtractor` → en módulo `{formato}_extractor.py`
- Factory: `XClientFactory` → en módulo `x_factory.py`

### Archivos de referencia
- `repositories/documents.py` — ejemplo de puerto limpio
- `repositories/supabase_documents.py` — ejemplo de adaptador Supabase
- `repositories/in_memory.py` — adaptadores de tests
- `pipeline/events.py` — `ProgressReporter` como puerto del orquestador
- `services/pipeline_runs.py` — `RepositoryProgressReporter` como adaptador

---

## 5. Contratos de etapa (Contract Pattern)

### Qué es en este proyecto

Cada etapa tiene un contrato de entrada (`PNInput`) y uno de salida (`PNOutput`)
definido como `ContractModel` (Pydantic, `frozen=True`, `extra="forbid"`).
Los contratos son la frontera formal entre etapas: garantizan que los datos
que entran y salen de cada etapa son válidos por construcción.

### Reglas

**R-CP-1 — Los contratos son puros.**  
Un contrato no importa nada de infraestructura (`supabase`, `openai`, `httpx`),
ni de FastAPI, ni del orquestador, ni del contexto. Solo importa:
- `pydantic`
- `uuid`, `datetime`, tipos de la stdlib
- otros contratos del mismo paquete (`pipeline/contracts/`)
- tipos comunes de `contracts/common.py`

**R-CP-2 — Validaciones cruzadas en el contrato, no en la etapa.**  
Si hay una invariante entre dos campos (ej: "las HU de `evidence` deben estar
en `user_story_codes`"), se implementa en un `@model_validator` del contrato.
La etapa confía en que si el objeto existe, es válido.

**R-CP-3 — `PNInput` se construye desde `PipelineContext`, no al revés.**  
La etapa lee los campos del contexto y construye su `PNInput`. No se almacena
un `PNInput` en el contexto — solo el `PNOutput`.

```python
# Correcto — dentro de P2Stage.run()
p2_input = P2Input(
    generation_id=context.generation_id,
    user_stories=context.p1_output.user_stories,
    config=self._config,
)
result = self._process(p2_input)
context.p2_output = result  # se guarda el Output, no el Input
```

**R-CP-4 — Los modelos intermedios del LLM son contratos separados.**  
`P2LlmResponse` y `P6LlmResponse` son modelos de validación de la respuesta
cruda del LLM. Se validan con `model_validate_json()` antes de procesar.
Nunca confiar en la respuesta del LLM sin pasar por su contrato.

**R-CP-5 — `to_rpc_payload()` vive en el Output.**  
La serialización para las RPCs de Supabase es responsabilidad del contrato
(`P2Output.to_rpc_payload()`, `P4Output.to_rpc_payload()`,
`P6UnitOutput.to_rpc_payload()`). La etapa llama al método y pasa el resultado
a la RPC. No construir el payload manualmente en la etapa.

**R-CP-6 — P7 no tiene contrato aún.**  
Su diseño se define al inicio de Fase 8. No crear `contracts/p7.py` hasta entonces.

### Archivos de referencia
- `pipeline/contracts/common.py` — `ContractModel`, tipos base, enums
- `pipeline/contracts/p1.py` … `p6.py` — contratos por etapa
- `pipeline/contracts/__init__.py` — nota sobre P7

---

## 6. Factory Pattern

### Qué es en este proyecto

Cuando hay múltiples adaptadores intercambiables para un mismo puerto (OpenAI,
Anthropic, Ollama para `LlmClient`), una factory centraliza la lógica de
construcción. `main.py` llama a la factory con `Settings` y recibe un `LlmClient`
listo para inyectar. Las etapas nunca ven la factory.

```
main.py
  └─ LlmClientFactory.create(settings)
        ├─ "openai"    → OpenAILlmClient     (API remota)
        ├─ "anthropic" → AnthropicLlmClient  (API remota)
        └─ "ollama"    → OllamaLlmClient     (servidor local)
              │
              └─ devuelve LlmClient (puerto)
                    ├─ P2Stage.run() lo usa sin saber qué proveedor es
                    └─ P6Stage.run() lo usa sin saber qué proveedor es
```

### Reglas

**R-FA-1 — Una factory por puerto con múltiples adaptadores.**  
Solo se crea una factory cuando un puerto tiene más de un adaptador seleccionable
en producción. `DocumentsRepository` no necesita factory porque en producción
siempre es Supabase; `LlmClient` sí la necesita porque el proveedor es
configurable. `DocumentTextExtractor` tampoco la necesita: sus tres adaptadores
coexisten siempre y el tipo de archivo de cada llamada decide cuál se usa, así
que `main.py` construye directamente un `CompositeDocumentExtractor` que delega
por `FileType`.

**R-FA-2 — La factory vive en su propio módulo.**  
`LlmClientFactory` vive en `clients/llm_factory.py`, no en `clients/llm.py`
(puerto) ni en ningún adaptador. No mezclar la lógica de construcción con el
contrato ni con la implementación.

**R-FA-3 — Los imports dentro de la factory son lazy.**  
Cada rama del `match` importa su adaptador dentro del bloque, no a nivel de
módulo. Así solo se carga la librería del proveedor activo:

```python
match settings.llm_provider:
    case "openai":
        from ai_service.clients.openai_llm import OpenAILlmClient  # lazy
        return OpenAILlmClient(...)
    case "anthropic":
        from ai_service.clients.anthropic_llm import AnthropicLlmClient  # lazy
        return AnthropicLlmClient(...)
```

**R-FA-4 — La factory falla explícitamente ante proveedor desconocido.**  
Si `settings.llm_provider` no coincide con ningún caso, lanza
`ConfigurationError` con mensaje que lista los valores válidos. Nunca devolver
`None` ni un adaptador por defecto silencioso. Lo mismo aplica si falta una
variable obligatoria del proveedor elegido (`LLM_API_KEY` para OpenAI/Anthropic,
`LLM_BASE_URL` para Ollama): la factory valida esa coherencia, igual que
`create_supabase_client()` valida las credenciales de Supabase.

**R-FA-5 — Solo `main.py` llama a la factory.**  
La factory es infraestructura de composición, no lógica de aplicación.
Ningún servicio, etapa ni repositorio importa `LlmClientFactory`.

**R-FA-6 — El fake no pasa por la factory.**  
`FakeLlmClient` se inyecta directamente en los tests por constructor.
No añadir `"fake"` como caso válido en la factory de producción.

### Estructura de módulos para LlmClient

```
clients/
  llm.py              ← Puerto: LlmClient (Protocol), LlmRequest, LlmResponse
  llm_factory.py      ← Factory: LlmClientFactory.create(settings) → LlmClient
  openai_llm.py       ← Adaptador OpenAI
  anthropic_llm.py    ← Adaptador Anthropic
  ollama_llm.py       ← Adaptador Ollama (servidor local)
  llm_fake.py         ← Fake determinista para tests
```

**R-FA-7 — Quien construye, cierra.**
Los adaptadores exponen `aclose()` (parte del puerto). `main.py` cierra en el
apagado del `lifespan` solo el cliente que construyó la factory; un cliente
inyectado desde fuera (tests) lo cierra quien lo inyectó.

### Archivos de referencia
- `clients/llm.py` — puerto (ver `docs/llm_client_design.md`)
- `clients/llm_factory.py` — factory
- `tests/test_llm_clients.py` — pruebas de factory, fake y adaptadores
- `docs/llm_client_design.md` — especificación completa de implementación

---

## 7. Separación de capas — regla general de imports

La siguiente tabla define qué puede importar cada capa. Una flecha `→` significa
"puede importar de". Una `✗` significa que está prohibido.

| Capa | Puede importar de | Nunca importa de |
|---|---|---|
| `pipeline/contracts/` | `pipeline/contracts/`, `schemas/`, stdlib | infraestructura, servicios, FastAPI |
| `pipeline/stages/` | contratos, contexto, `schemas/`, `core/`, puertos (`clients/llm.py`, `clients/extractor.py`, `clients/storage.py`) | Supabase, LLM concreto, FastAPI directamente |
| `pipeline/orchestrator.py` | `pipeline/stages/base`, `pipeline/events`, `pipeline/catalog`, `pipeline/context` | contratos concretos, servicios, infraestructura |
| `repositories/*.py` (puertos) | `schemas/`, `core/errors`, stdlib | supabase, postgrest, openai |
| `repositories/supabase_*.py` (adaptadores) | su puerto, `schemas/`, `core/`, supabase, postgrest | FastAPI, servicios |
| `clients/*.py` (puertos) | stdlib, `core/errors`, enums de `pipeline/contracts/common.py` (`FileType`) | supabase, openai, anthropic, httpx, pdfplumber, docx |
| `clients/*_extractor.py` (adaptadores) | su puerto, `core/errors`, `FileType`, librería del formato | FastAPI, servicios, etapas |
| `clients/*_llm.py` (adaptadores) | su puerto, `core/errors`, librería del proveedor | FastAPI, servicios, contratos |
| `clients/llm_factory.py` | `config.py`, `core/errors`, adaptadores LLM (lazy) | servicios, etapas, contratos |
| `services/` | puertos (`repositories/`, `clients/`), `pipeline/`, `schemas/`, `core/` | adaptadores concretos (`supabase_*`, `*_llm`) |
| `api/` | servicios, `schemas/`, `core/` | repositorios, pipeline directamente |
| `main.py` | todo (es el punto de composición) | — |

---

## Checklist para añadir una nueva pieza de código

Antes de hacer un PR con una nueva etapa, puerto, adaptador o servicio,
verificar:

- [ ] ¿La etapa hereda de `StageBase` y solo recibe `PipelineContext`?
- [ ] ¿El orquestador sigue sin importar ningún contrato concreto?
- [ ] ¿El puerto (Protocol) está en un módulo sin imports de infraestructura?
- [ ] ¿El adaptador Supabase/LLM está en un módulo separado (`supabase_*.py`, `*_llm.py`)?
- [ ] ¿Los errores de infraestructura se traducen a excepciones de dominio antes de salir del adaptador?
- [ ] ¿`main.py` es el único lugar que importa los adaptadores concretos?
- [ ] Si hay múltiples adaptadores para un puerto, ¿existe una factory en `*_factory.py`?
- [ ] ¿Los imports dentro de la factory son lazy (dentro del `match`, no a nivel de módulo)?
- [ ] ¿El fake del nuevo cliente se inyecta por constructor en tests, sin pasar por la factory?
- [ ] ¿El contrato nuevo hereda de `ContractModel` (`frozen=True`, `extra="forbid"`)?
- [ ] ¿Las invariantes del contrato están en `@model_validator`, no en la etapa?
- [ ] ¿Los datos del dominio viajan por `PipelineContext`, no por `StageResult`?
- [ ] ¿Los tests inyectan fakes por constructor, sin parchear clientes de infraestructura?

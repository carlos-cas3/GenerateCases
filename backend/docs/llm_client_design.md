# Diseño del cliente LLM — especificación de implementación

> Fase 4 — prerequisito para implementar P2 y P6.  
> Este documento describe qué construir, por qué y cómo debe encajar con los
> patrones definidos en `architecture_patterns.md`.
>
> **Estado:** implementado al cierre de Fase 3 (pasos 1–10 del orden sugerido,
> salvo `build_real_stages`). Las etapas P2 y P6 siguen siendo stubs: el
> `LlmClient` ya se construye en `main.py` y queda listo para inyectarse en ellas
> en Fase 4. Registro de cambios en
> `docs/prompts_fases/Fase 3/resultados_patrones_LLMDisenoCliente.md`.

---

## Contexto y necesidad

P2 (clasificación de HU y extracción de RF) y P6 (generación de casos de prueba)
realizan llamadas a un LLM. El proyecto debe soportar tres proveedores desde el
inicio:

| Proveedor | Tipo | Librería esperada |
|---|---|---|
| OpenAI | API remota | `openai` |
| Anthropic | API remota | `anthropic` |
| Ollama | Servidor local | `httpx` o `ollama` |

El proveedor activo se configura por variable de entorno. Las etapas P2 y P6
no deben saber qué proveedor está activo — solo llaman al puerto `LlmClient`.

---

## Patrones aplicables

Esta pieza requiere **tres patrones** trabajando juntos:

### Adapter Pattern
Cada proveedor es un adaptador que implementa el puerto `LlmClient`. Las etapas
dependen del puerto, nunca del adaptador concreto. Ver reglas R-AP-1 a R-AP-6
en `architecture_patterns.md`.

### Factory Pattern (nuevo)
Una factory lee `Settings` y construye el adaptador correcto. Es el único lugar
del sistema donde existe un `if provider == "openai"`. Ver sección 6 de
`architecture_patterns.md`.

### Dependency Injection
La factory se llama en `main.py`/`lifespan`. El `LlmClient` resultante se
inyecta por constructor en las etapas P2 y P6. Ver reglas R-DI-1 a R-DI-5
en `architecture_patterns.md`.

---

## Estructura de módulos a crear

```
ai_service/clients/
  llm.py                  ← Puerto LlmClient + tipos LlmRequest / LlmResponse
  llm_factory.py          ← LlmClientFactory (lee Settings, devuelve LlmClient)
  openai_llm.py           ← Adaptador OpenAI
  anthropic_llm.py        ← Adaptador Anthropic
  ollama_llm.py           ← Adaptador Ollama
  llm_fake.py             ← Fake determinista para tests
```

Regla de nombrado (R-AP-6): los adaptadores siguen `{proveedor}_llm.py`, el
puerto es `llm.py`, la factory es `llm_factory.py`.

---

## Puerto `LlmClient` — `clients/llm.py`

El puerto define exactamente lo que las etapas pueden pedirle a un LLM.

```python
# clients/llm.py — solo stdlib, sin imports de infraestructura (R-AP-2)

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class LlmRequest:
    """Solicitud al LLM. El prompt ya viene formateado por la etapa."""
    prompt: str
    model: str           # modelo concreto, viene de LlmSettings del contrato
    system: str | None = None   # D-LLM-1: instrucciones de sistema
    max_tokens: int | None = None
    temperature: float | None = None
    # parámetros adicionales específicos del proveedor (timeout, top_p, etc.)
    extra: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LlmResponse:
    """Respuesta del LLM. Contiene solo lo que el pipeline necesita."""
    text: str                     # texto generado (JSON crudo para P2/P6)
    input_tokens: int | None      # para LlmRun en StageResult
    output_tokens: int | None     # para LlmRun en StageResult
    latency_ms: int | None        # para LlmRun en StageResult


class LlmClient(Protocol):
    """Puerto de comunicación con el LLM. Lo implementan OpenAI, Anthropic, Ollama y el fake."""

    async def complete(self, request: LlmRequest) -> LlmResponse:
        """Envía el prompt y devuelve la respuesta. Lanza LlmError ante fallos."""
        ...

    async def aclose(self) -> None:
        """Libera conexiones. main.py lo llama al apagar (R-FA-7)."""
        ...
```

**Por qué `LlmRequest` y no pasar `LlmSettings` directamente:**  
`LlmSettings` es un contrato del pipeline (Pydantic, frozen). `LlmRequest` es
el DTO de transporte hacia el adaptador. La etapa construye el `LlmRequest`
combinando el prompt que generó con los parámetros de `LlmSettings`. Así el
puerto no depende de los contratos del pipeline.

---

## Errores de dominio — `core/errors.py`

Añadir antes de implementar los adaptadores:

```python
class LlmError(AppError):
    """Fallo en la llamada al LLM. Los adaptadores lo lanzan; las etapas lo capturan."""

class LlmRateLimitError(LlmError):
    """El proveedor rechazó la llamada por límite de tasa. Reintentable."""

class LlmInvalidResponseError(LlmError):
    """La respuesta no es JSON válido o no supera la validación del contrato."""

class LlmContextLengthError(LlmError):
    """El prompt supera el límite de tokens del modelo."""
```

Códigos implementados: `LLM_ERROR`, `LLM_RATE_LIMIT`, `LLM_INVALID_OUTPUT`
(coincide con el código de error de etapa ya citado en `openapi.yaml`) y
`LLM_CONTEXT_LENGTH`.

Regla R-AP-4: los adaptadores traducen errores de librería a estos tipos antes
de que salgan del adaptador. Las etapas solo conocen `LlmError` y sus subtipos.

---

## Adaptadores

### Estructura común de cada adaptador

Cada adaptador sigue el mismo esquema:

```
1. Recibe el cliente de librería ya construido por constructor
   (AsyncOpenAI / AsyncAnthropic / httpx.AsyncClient, creado por la factory)
2. Traduce LlmRequest → llamada de librería
3. Traduce respuesta de librería → LlmResponse
4. Captura excepciones de librería → lanza LlmError del dominio
```

### `clients/openai_llm.py`

- Librería: `openai` (cliente async `AsyncOpenAI`)
- Método: `client.chat.completions.create()`
- `system` → mensaje `role: "system"`; `max_tokens` → `max_completion_tokens`
  (parámetro vigente de Chat Completions); `extra` se pasa tal cual.
- Errores a traducir: `RateLimitError` → `LlmRateLimitError`,
  `BadRequestError` con `code == "context_length_exceeded"` → `LlmContextLengthError`,
  resto → `LlmError`. Respuesta sin texto → `LlmInvalidResponseError`.
- Tokens: disponibles en `response.usage.prompt_tokens` / `completion_tokens`
- Latencia: medir con `time.monotonic()` alrededor de la llamada

### `clients/anthropic_llm.py`

- Librería: `anthropic` (cliente async `AsyncAnthropic`)
- Método: `client.messages.create()`
- Modelo de mensajes: `LlmRequest.system` va al parámetro `system` de la API y
  el prompt como único mensaje `user` (D-LLM-1 resuelta).
- `max_tokens` es obligatorio en la Messages API: si la solicitud no lo fija se
  usa `DEFAULT_MAX_TOKENS = 4096`.
- Errores a traducir: `RateLimitError` → `LlmRateLimitError`;
  `BadRequestError` cuyo mensaje contiene "prompt is too long" o HTTP 413 →
  `LlmContextLengthError`; resto (incluido otro `BadRequestError`) → `LlmError`.
  Traducir todo `BadRequestError` a contexto excedido ocultaría errores de
  parámetros.
- Tokens: disponibles en `response.usage.input_tokens` / `output_tokens`

- Texto: concatenación de los bloques `type == "text"` de `response.content`.

### `clients/ollama_llm.py`

- Librería: `httpx` (cliente async) directo (D-LLM-2 resuelta)
- Endpoint: `POST {base_url}/api/chat` con `"stream": false`; `system` va como
  mensaje `role: "system"`
- El modelo se pasa en el body (`"model": request.model`); `max_tokens` →
  `options.num_predict`; `temperature` y `extra` → `options`
- Errores: conexión rechazada → `LlmError` con mensaje claro sobre Ollama no
  disponible; HTTP 429 → `LlmRateLimitError`; otro HTTP de error → `LlmError`;
  cuerpo no JSON o sin `message.content` → `LlmInvalidResponseError`
- Tokens: Ollama los devuelve en `prompt_eval_count` / `eval_count`
- Latencia: `total_duration` (nanosegundos → ms). Se prefiere a `eval_duration`
  porque esta excluye la evaluación del prompt y la carga del modelo; si falta,
  se usa la medida con `time.monotonic()`.

---

## Factory — `clients/llm_factory.py`

```python
# clients/llm_factory.py

class LlmClientFactory:
    """Construye el LlmClient correcto según Settings.llm_provider.

    Solo main.py llama a esta factory (R-DI-1). Las etapas reciben el
    LlmClient ya construido por constructor (R-DI-2).
    """

    @staticmethod
    def create(settings: Settings) -> LlmClient:
        match settings.llm_provider:
            case "openai":
                from ai_service.clients.openai_llm import OpenAILlmClient
                return OpenAILlmClient(
                    api_key=settings.llm_api_key.get_secret_value(),
                    timeout=settings.llm_timeout_seconds,
                )
            case "anthropic":
                from ai_service.clients.anthropic_llm import AnthropicLlmClient
                return AnthropicLlmClient(
                    api_key=settings.llm_api_key.get_secret_value(),
                    timeout=settings.llm_timeout_seconds,
                )
            case "ollama":
                from ai_service.clients.ollama_llm import OllamaLlmClient
                return OllamaLlmClient(
                    base_url=settings.llm_base_url,
                    timeout=settings.llm_timeout_seconds,
                )
            case _:
                raise ConfigurationError(
                    f"Proveedor LLM no soportado: {settings.llm_provider!r}. "
                    "Valores válidos: openai, anthropic, ollama."
                )
```

Los imports dentro del `match` son lazy — solo se carga la librería del
proveedor activo, no las tres. Esto cumple R-DI-5 (imports lazy de adaptadores)
aplicado a la factory.

> **Implementado:** la factory construye también el cliente de librería
> (`AsyncOpenAI` / `AsyncAnthropic` con `max_retries=0`, `httpx.AsyncClient`) y
> se lo pasa al adaptador, que así se prueba con `httpx.MockTransport`. Los
> reintentos los decidirá la etapa, no el SDK. La factory valida que exista
> `LLM_API_KEY` (OpenAI/Anthropic) o `LLM_BASE_URL` (Ollama) y lanza
> `ConfigurationError` si falta.

---

## Fake para tests — `clients/llm_fake.py`

```python
# clients/llm_fake.py

class FakeLlmClient:
    """LlmClient determinista para tests. Devuelve respuestas programadas."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = iter(responses)

    async def complete(self, request: LlmRequest) -> LlmResponse:
        text = next(self._responses)   # lanza StopIteration si se agotan
        return LlmResponse(
            text=text,
            input_tokens=len(request.prompt) // 4,  # estimación burda
            output_tokens=len(text) // 4,
            latency_ms=0,
        )
```

El fake es determinista: se construye con la lista de respuestas que devolverá
en orden. Los tests no necesitan `unittest.mock.patch` ni monkeypatching (R-DI-3).

> **Implementado con ajustes:** cada elemento puede ser un texto o una
> `LlmError` (que se lanza en su turno, para probar reintentos); las solicitudes
> recibidas quedan en `fake.requests`; al agotarse lanza `AssertionError` con un
> mensaje claro (un `StopIteration` dentro de una corrutina se convierte en un
> `RuntimeError` confuso). `aclose()` es un no-op que marca `fake.closed`.

---

## Variables de entorno a añadir en `config.py`

```python
# Proveedor activo
llm_provider: Literal["openai", "anthropic", "ollama"] = "openai"

# Credenciales (solo para OpenAI y Anthropic)
llm_api_key: SecretStr | None = None

# URL base (obligatoria para Ollama, opcional para proxies de OpenAI/Anthropic)
llm_base_url: str | None = None

# Timeout de red en segundos
llm_timeout_seconds: float = Field(default=60.0, gt=0)
```

Validador necesario: si `llm_provider` es `openai` o `anthropic`, `llm_api_key`
no puede ser `None`. Si `llm_provider` es `ollama`, `llm_base_url` no puede
ser `None`.

> **Implementado en la factory, no en `Settings`:** un `model_validator` en
> `Settings` haría fallar cualquier `Settings()` sin credenciales LLM (tests,
> scripts que no usan el LLM). La comprobación vive en `LlmClientFactory.create()`,
> que se ejecuta en el arranque, igual que `create_supabase_client()`. Un valor
> vacío en `.env` (`LLM_API_KEY=`, `LLM_BASE_URL=`) cuenta como ausente.

---

## Cómo se inyecta en las etapas

En `main.py`/`lifespan`:

```python
# Implementado (create_app acepta llm_client opcional, R-DI-4):
llm = llm_client
if llm is None:
    from ai_service.clients.llm_factory import LlmClientFactory
    llm = LlmClientFactory.create(app_settings)
app.state.llm_client = llm
...
try:
    yield
finally:
    if llm_client is None:      # solo se cierra lo que construyó la factory
        await llm.aclose()

# Pendiente (Fase 4), cuando existan las etapas reales:
stages = build_real_stages(llm_client=llm, ...)
```

En las etapas:

```python
class RequirementsStage(StageBase):
    key: ClassVar[StageKey] = StageKey.P2

    def __init__(self, llm_client: LlmClient, config: P2Config) -> None:
        self._llm = llm_client      # puerto, no adaptador concreto
        self._config = config

    async def run(self, context: PipelineContext) -> StageResult | None:
        ...
```

---

## Orden de implementación sugerido

1. Añadir errores LLM en `core/errors.py`
2. Crear el puerto `clients/llm.py` (sin dependencias externas)
3. Crear el fake `clients/llm_fake.py` (permite escribir tests de etapa ya)
4. Añadir variables LLM en `config.py` con su validador
5. Crear la factory `clients/llm_factory.py`
6. Implementar `clients/openai_llm.py`
7. Implementar `clients/anthropic_llm.py` (resolver decisión de system prompt)
8. Implementar `clients/ollama_llm.py`
9. Actualizar `main.py` para construir y pasar `llm_client`
10. Actualizar `architecture_patterns.md` tabla de puertos actuales

---

## Decisiones

| # | Decisión | Impacto |
|---|---|---|
| D-LLM-1 | ¿`LlmRequest` tiene `system: str \| None`? | Afecta al puerto y a todos los adaptadores |
| D-LLM-2 | ¿Se usa la librería `ollama` o `httpx` directo para Ollama? | Afecta solo a `ollama_llm.py` |
| D-LLM-3 | ¿El modelo se define solo en `LlmSettings` del contrato o también hay un modelo por defecto en `Settings`? | Afecta a `config.py` y a la factory |

Resolución (cierre de Fase 3):

- **D-LLM-1 — resuelta.** `LlmRequest` incluye `system: str | None = None`.
  Anthropic lo pasa en el parámetro `system`; OpenAI y Ollama como mensaje
  `role: "system"`.
- **D-LLM-2 — resuelta.** `httpx` directo: ya es dependencia (transitiva de
  supabase, openai y anthropic) y permite probar con `httpx.MockTransport`.
- **D-LLM-3 — abierta.** No afecta a la factory: el modelo viaja en cada
  `LlmRequest`. Se decide en Fase 4 al construir `P2Config`/`P6Config`.
  Propuesta: `LLM_MODEL` en `Settings` como fuente de `LlmSettings.model`.

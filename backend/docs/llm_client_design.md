# Diseño del cliente LLM — especificación de implementación

> Fase 4 — prerequisito para implementar P2 y P6.  
> Este documento describe qué construir, por qué y cómo debe encajar con los
> patrones definidos en `architecture_patterns.md`.

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
del sistema donde existe un `if provider == "openai"`. Ver sección 7 de
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

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class LlmRequest:
    """Solicitud al LLM. El prompt ya viene formateado por la etapa."""
    prompt: str
    model: str           # modelo concreto, viene de LlmSettings del contrato
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

Regla R-AP-4: los adaptadores traducen errores de librería a estos tipos antes
de que salgan del adaptador. Las etapas solo conocen `LlmError` y sus subtipos.

---

## Adaptadores

### Estructura común de cada adaptador

Cada adaptador sigue el mismo esquema:

```
1. Recibe el cliente de librería por constructor (inyectado por la factory)
2. Traduce LlmRequest → llamada de librería
3. Traduce respuesta de librería → LlmResponse
4. Captura excepciones de librería → lanza LlmError del dominio
```

### `clients/openai_llm.py`

- Librería: `openai` (cliente async `AsyncOpenAI`)
- Método: `client.chat.completions.create()`
- Errores a traducir: `RateLimitError` → `LlmRateLimitError`,
  `BadRequestError` (context length) → `LlmContextLengthError`,
  resto → `LlmError`
- Tokens: disponibles en `response.usage.prompt_tokens` / `completion_tokens`
- Latencia: medir con `time.monotonic()` alrededor de la llamada

### `clients/anthropic_llm.py`

- Librería: `anthropic` (cliente async `AsyncAnthropic`)
- Método: `client.messages.create()`
- Modelo de mensajes: Anthropic requiere separar `system` prompt de `user`
  prompt. El adaptador debe partir el prompt en dos si el `LlmRequest` lo
  necesita — o bien el puerto `LlmRequest` añade un campo opcional `system: str | None`.
- Errores a traducir: `RateLimitError` → `LlmRateLimitError`,
  `BadRequestError` → `LlmContextLengthError`, resto → `LlmError`
- Tokens: disponibles en `response.usage.input_tokens` / `output_tokens`

> **Decisión pendiente:** Anthropic separa system/user en la API. Evaluar si
> `LlmRequest` añade `system: str | None = None` o si el adaptador de Anthropic
> maneja el prompt completo como `user`. Decidir antes de implementar
> `anthropic_llm.py`.

### `clients/ollama_llm.py`

- Librería: `httpx` (cliente async) o librería `ollama`
- Endpoint: `POST {base_url}/api/generate` o `/api/chat`
- El modelo se pasa en el body (`"model": request.model`)
- Errores: conexión rechazada → `LlmError` con mensaje claro sobre Ollama no disponible
- Tokens: Ollama los devuelve en `prompt_eval_count` / `eval_count`
- Latencia: disponible en `eval_duration` (nanosegundos → convertir a ms)

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

---

## Cómo se inyecta en las etapas

En `main.py`/`lifespan`:

```python
from ai_service.clients.llm_factory import LlmClientFactory

llm_client = LlmClientFactory.create(app_settings)

stages = build_real_stages(
    llm_client=llm_client,
    ...
)
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

## Decisiones pendientes antes de implementar

| # | Decisión | Impacto |
|---|---|---|
| D-LLM-1 | ¿`LlmRequest` tiene `system: str \| None`? | Afecta al puerto y a todos los adaptadores |
| D-LLM-2 | ¿Se usa la librería `ollama` o `httpx` directo para Ollama? | Afecta solo a `ollama_llm.py` |
| D-LLM-3 | ¿El modelo se define solo en `LlmSettings` del contrato o también hay un modelo por defecto en `Settings`? | Afecta a `config.py` y a la factory |

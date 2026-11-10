# Resultados — patrones de arquitectura y diseño del cliente LLM

> Cierre de Fase 3. Aplica al proyecto lo propuesto en el commit `e02791b`
> ("actualizacion patrones y llm client propuesta"), que modificó
> `docs/architecture_patterns.md` (nueva sección 6, Factory Pattern, y tabla de
> capas) y creó `docs/llm_client_design.md` (especificación del cliente LLM).

## Resumen

Se implementó el cliente LLM completo según `llm_client_design.md`: puerto,
errores de dominio, fake, configuración, factory y los tres adaptadores
(OpenAI, Anthropic, Ollama), y se conectó en `main.py`. Las etapas P2 y P6
siguen siendo stubs; el `LlmClient` queda construido y listo para inyectarse
en ellas en Fase 4.

**Pruebas:** 341 pasan (312 existentes y 29 nuevas en `tests/test_llm_clients.py`).
Ninguna hace llamadas de red: los adaptadores se prueban con `httpx.MockTransport`.

## Revisión de los documentos del commit

Inconsistencias encontradas y corregidas en los documentos:

| Documento | Problema | Corrección |
|---|---|---|
| `llm_client_design.md` | Remitía a la "sección 7" de `architecture_patterns.md` para la factory; es la 6. | Referencia corregida. |
| `llm_client_design.md` | El ejemplo de `LlmRequest` usaba `field(...)` sin importarlo. | Añadido `from dataclasses import dataclass, field`. |
| `llm_client_design.md` | "Estructura común de cada adaptador" dice que recibe el cliente de librería por constructor, pero el ejemplo de factory le pasa `api_key`/`timeout`. | Se sigue la estructura común: la factory crea el SDK y se lo pasa al adaptador (así es testeable sin red). Documentado. |
| `llm_client_design.md` | Anthropic: traducir todo `BadRequestError` a `LlmContextLengthError`. | Solo cuando el mensaje es "prompt is too long" o HTTP 413; el resto → `LlmError`. |
| `llm_client_design.md` | Ollama: latencia desde `eval_duration`. | Se usa `total_duration` (incluye evaluación del prompt y carga del modelo); `eval_duration` mide solo la generación. |
| `llm_client_design.md` | El fake usaba `next()` y lanzaba `StopIteration` al agotarse. | Dentro de una corrutina eso se convierte en `RuntimeError` confuso; ahora lanza `AssertionError` con mensaje claro. |
| `architecture_patterns.md` | `LlmClient` figuraba como puerto pendiente; archivos de referencia "pendientes de crear". | Movido a "Puertos actuales"; referencias actualizadas (paso 10 del orden sugerido). |
| `architecture_patterns.md` | R-AP-6 no nombraba adaptadores de proveedor ni factories. | Añadidos `{Proveedor}LlmClient` en `{proveedor}_llm.py` y `XClientFactory` en `x_factory.py`. |

## Archivos creados

| Archivo | Contenido |
|---|---|
| `ai_service/clients/llm.py` | Puerto `LlmClient` (`complete`, `aclose`) y DTOs `LlmRequest` / `LlmResponse`. Solo stdlib (R-AP-2). |
| `ai_service/clients/llm_fake.py` | `FakeLlmClient`: respuestas programadas en orden; admite `LlmError` para simular fallos; registra `requests`. |
| `ai_service/clients/llm_factory.py` | `LlmClientFactory.create(settings)` con `match` e imports lazy (R-FA-3); valida credenciales y lanza `ConfigurationError` (R-FA-4). |
| `ai_service/clients/openai_llm.py` | `OpenAILlmClient` sobre `AsyncOpenAI` (Chat Completions). |
| `ai_service/clients/anthropic_llm.py` | `AnthropicLlmClient` sobre `AsyncAnthropic` (Messages API). |
| `ai_service/clients/ollama_llm.py` | `OllamaLlmClient` sobre `httpx.AsyncClient` (`POST /api/chat`). |
| `tests/test_llm_clients.py` | 29 pruebas: factory (cada proveedor, credenciales, proveedor desconocido, imports lazy), arranque sin configuración, fake, traducción de peticiones/respuestas y de errores de los tres adaptadores. |
| `docs/prompts_fases/Fase 3/resultados_patrones_LLMDisenoCliente.md` | Este registro. |

## Archivos modificados

| Archivo | Cambio |
|---|---|
| `ai_service/core/errors.py` | `LlmError` (`LLM_ERROR`), `LlmRateLimitError` (`LLM_RATE_LIMIT`), `LlmInvalidResponseError` (`LLM_INVALID_OUTPUT`, el código que ya cita `openapi.yaml`) y `LlmContextLengthError` (`LLM_CONTEXT_LENGTH`). No se añadieron a `api/errors.py`: no llegan a HTTP, los capturan las etapas. |
| `ai_service/config.py` | `llm_provider` (`Literal["openai","anthropic","ollama"]`, por defecto `openai`), `llm_api_key`, `llm_base_url`, `llm_timeout_seconds`. Valores vacíos en `.env` cuentan como ausentes. |
| `ai_service/main.py` | `create_app(..., llm_client=None)` (R-DI-4). En el `lifespan`, si no se inyecta, se construye con la factory (import lazy, R-FA-5) y se guarda en `app.state.llm_client`; al apagar se cierra con `aclose()` solo si lo construyó la factory. |
| `tests/conftest.py` | Inyecta `FakeLlmClient()` en `create_app` (R-FA-6: el fake no pasa por la factory). |
| `requirements.txt` | Añadidos `openai>=1.40,<3.0` y `anthropic>=0.34,<1.0`; `httpx` pasa de dependencia de tests a dependencia de runtime (lo usa el adaptador de Ollama). |
| `.env.example` | Variables `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_TIMEOUT_SECONDS`. |
| `README.md` | Requisitos del cliente LLM para ejecutar en local. |
| `docs/architecture_patterns.md` | R-DI-3 y R-DI-4 incluyen el LLM; `LlmClient` en puertos actuales; R-AP-6 ampliada; R-FA-4 cubre credenciales; nueva **R-FA-7 — Quien construye, cierra**; referencias actualizadas. |
| `docs/llm_client_design.md` | Estado de implementación, correcciones de la tabla anterior, notas "Implementado" en factory, fake y config, y resolución de decisiones. |

## Decisiones tomadas

| # | Decisión | Resolución |
|---|---|---|
| D-LLM-1 | ¿`LlmRequest` tiene `system`? | **Sí**, `system: str \| None = None`. Anthropic lo manda en `system`; OpenAI y Ollama como mensaje `role: "system"`. Sin él, el adaptador de Anthropic tendría que adivinar dónde partir el prompt. |
| D-LLM-2 | ¿Librería `ollama` o `httpx`? | **`httpx` directo.** Ya está instalado (transitiva de supabase/openai/anthropic) y se prueba con `MockTransport`. |
| D-LLM-3 | ¿Modelo por defecto en `Settings`? | **Sigue abierta.** No afecta a lo implementado: el modelo viaja en cada `LlmRequest`. Propuesta para Fase 4: `LLM_MODEL` en `Settings` como fuente de `LlmSettings.model` al construir `P2Config`/`P6Config`. |

Otras decisiones de implementación:

1. **Validación proveedor ↔ credenciales en la factory, no en `Settings`.** Un
   `model_validator` en `Settings` rompería cualquier `Settings()` sin credenciales
   LLM (tests y scripts que no usan el LLM). La factory se ejecuta en el arranque,
   así que el efecto *fail-fast* es el mismo, igual que `create_supabase_client()`.
2. **`aclose()` forma parte del puerto.** Los SDKs y `httpx` mantienen conexiones
   abiertas; sin un método en el puerto, `main.py` no podría cerrarlas sin conocer
   el adaptador. Regla nueva R-FA-7.
3. **`max_retries=0` en los SDKs.** Los reintentos ante `LlmRateLimitError` o
   `LLM_INVALID_OUTPUT` los decidirá la etapa (P2/P6), no el SDK de forma oculta.
4. **OpenAI usa `max_completion_tokens`**, el parámetro vigente de Chat
   Completions (`max_tokens` está obsoleto y los modelos de razonamiento lo rechazan).
5. **Anthropic: `DEFAULT_MAX_TOKENS = 4096`** cuando la solicitud no fija
   `max_tokens`, porque la Messages API lo exige.
6. **Respuesta sin texto → `LlmInvalidResponseError`** en los tres adaptadores
   (p. ej., un rechazo de OpenAI con `content = None`).

## ⚠️ Cambio de comportamiento a tener en cuenta

El servicio **ahora construye el cliente LLM al arrancar**. Con
`LLM_PROVIDER=openai` (valor por defecto) y sin `LLM_API_KEY`, el arranque falla
con `ConfigurationError`, aunque las etapas P2/P6 todavía sean stubs. Para
desarrollo local sin clave basta con `LLM_PROVIDER=ollama` y
`LLM_BASE_URL=http://localhost:11434` (la construcción no conecta con Ollama).
Los tests no se ven afectados porque inyectan `FakeLlmClient`.

## Verificación de las reglas

- [x] Puerto (`clients/llm.py`) sin imports de infraestructura (R-AP-2).
- [x] Adaptadores en módulos `*_llm.py` separados, sin herencia del Protocol (R-AP-1, R-AP-3, R-AP-6).
- [x] Los adaptadores traducen todas las excepciones de librería a `LlmError` y subtipos (R-AP-4).
- [x] Solo `main.py` importa la factory; ningún servicio, etapa ni repositorio importa adaptadores LLM (R-AP-5, R-FA-5). Comprobado con `grep`.
- [x] Imports lazy en la factory: importarla no carga `openai`, `anthropic` ni ningún `*_llm` (R-FA-3, cubierto por test).
- [x] Proveedor desconocido o credencial ausente → `ConfigurationError` (R-FA-4, cubierto por test).
- [x] El fake se inyecta por constructor y no existe el caso `"fake"` en la factory (R-FA-6).
- [x] `create_app()` acepta `llm_client` opcional (R-DI-4).

## Pendiente para Fase 4

1. Implementar `RequirementsStage` (P2) y `GenerationStage` (P6) reales recibiendo
   `llm_client: LlmClient` por constructor, y crear `build_real_stages(llm_client=...)`
   para sustituir a `build_stub_stages` en `main.py`.
2. Resolver D-LLM-3 (origen de `LlmSettings.model`).
3. Política de reintentos en las etapas ante `LlmRateLimitError` y `LLM_INVALID_OUTPUT`.

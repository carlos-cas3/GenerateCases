# Ajuste del contexto y opciones de Ollama para P2/P6

> **Estado:** propuesta de mejora (pendiente de implementar). Surge al probar el pipeline
> real (P1→P4) con `qwen3.5:latest` (9B) en Ollama: P2 falla con `LLM_INVALID_OUTPUT`.
> **Alcance:** el cliente LLM (`ai_service/clients/ollama_llm.py`, factory y `config.py`) y el
> saneamiento de la salida de P2. No toca P3/P4. Actualiza decisiones de
> [`llm_client_design.md`](llm_client_design.md) (sección Ollama y "Variables de entorno").

---

## 1. Contexto

P2 (`RequirementsStage`) y, en el futuro, P6 llaman al LLM para extraer JSON estructurado. El
cliente de Ollama se construye en `LlmClientFactory` y las etapas le pasan `LlmRequest` con
`max_tokens`, `temperature` y `extra` (parámetros del proveedor).

Al correr un documento real con `LLM_PROVIDER=ollama` y `LLM_MODEL=qwen3.5:latest`, P2 devuelve:

```
error_code: LLM_INVALID_OUTPUT
error_message: La respuesta del modelo de lenguaje no es válida en el lote 1 tras N intento(s).
llm_runs: []   # el LlmRun solo se registra si la respuesta valida
```

Ollama respondió sin error de red: el problema es que el JSON que devuelve **no valida** contra
`P2LlmResponse`. Hay dos causas, ambas verificadas en el código.

---

## 2. Causas (verificadas)

### Causa principal — el pipeline no pasa `num_ctx` ni `think` a Ollama

- `build_p2_config` (`pipeline/stages/__init__.py`) construye `LlmSettings(..., parameters={})`.
- `_build_request` (P2) deja `extra = {}` (nada de `num_ctx`, `think`, `temperature`).
- El adaptador `ollama_llm.py` arma `body = {"model", "messages", "stream": false}` y solo añade
  `options` si hay `extra`/`max_tokens`/`temperature`. Como no llega nada, **Ollama usa sus
  defaults**: `num_ctx = 4096`, thinking activado y temperatura alta.

Con un modelo "con thinking" (qwen3.5), los tokens se gastan razonando antes de escribir el JSON.
El resultado: `done_reason = length` (se cortó por límite, no porque terminara). El JSON queda
truncado a la mitad → `P2LlmResponse.model_validate_json` falla. La HU más corta entra; la que tiene
más criterios/reglas (más RF) se corta.

### Causa secundaria — el modelo escribe `[""]` en vez de `[]`

Aunque el JSON no se trunque, el modelo a veces rellena listas vacías con `[""]` (un string vacío)
en lugar de `[]`:

```json
{ "business_rules": [""], "conditions": [""], "unspecified_information": [""] }
```

El contrato define esas listas como `tuple[NonEmptyStr, ...]`, y `NonEmptyStr` (`common.py`,
`_not_blank`) rechaza el string vacío:

```
requirements.1.business_rules.0           → no puede estar vacío (input_value='')
requirements.2.conditions.0             → no puede estar vacío
requirements.3.unspecified_information.0 → no puede estar vacío
```

Esto **no depende del contexto**: es una maña del modelo que conviene saneaar.

---

## 3. Solución — decisiones

| # | Decisión | Dónde |
|---|---|---|
| D-OLLAMA-1 | Exponer `LLM_NUM_CTX` (default `16384`), `LLM_THINK` (default `false`), `LLM_TEMPERATURE` (default `0.0`) en `config.py` | `ai_service/config.py`, `.env.example` |
| D-OLLAMA-2 | `build_p2_config` los mete en `LlmSettings.parameters = {"num_ctx", "think", "temperature"}` | `pipeline/stages/__init__.py` |
| D-OLLAMA-3 | El adaptador Ollama pone `num_ctx`/`temperature` en `options`, pero `think` va en el **body** (no en `options`): sacarlo de `extra` antes de armar `options` | `ai_service/clients/ollama_llm.py` |
| D-OLLAMA-4 | Saneaar `[""]` → `[]` filtrando strings vacíos de las listas **antes** de validar `P2LlmResponse` (local en P2, sin tocar el contrato compartido) | `pipeline/stages/p2_requirements.py` (`_parse`) |
| D-OLLAMA-5 | (Diferido / opt-in) `format: "json"` de Ollama fuerza salida JSON sintácticamente válida vía `LLM_JSON_FORMAT`. Fuera del primer alcance: con D-OLLAMA-1..4 lo normal es que el JSON ya salga limpio | `ollama_llm.py`, `config.py` |

**Defaults propuestos (D-OLLAMA-1):** thinking apagado por defecto (para JSON estructurado no
aporta y devora el contexto); `num_ctx = 16384` cubre HU grandes; `temperature = 0.0` para
extracción determinista. Todo configurable por env var sin tocar código.

---

## 4. Archivos a modificar

1. `ai_service/config.py` — añadir `llm_num_ctx`, `llm_think`, `llm_temperature`.
2. `.env.example` — documentar las tres variables con sus defaults.
3. `pipeline/stages/__init__.py` — `build_p2_config` pasa los tres a `LlmSettings.parameters`.
   (`_build_request` ya popea `temperature` y deja el resto en `extra`; no cambia).
4. `ai_service/clients/ollama_llm.py` — extraer `think` del `extra`/`options` y mandarlo en el
   `body`. `num_ctx` y `temperature` ya caen en `options` correctamente.
5. `pipeline/stages/p2_requirements.py` — en `_parse`, filtrar strings vacíos de las listas del
   JSON antes de `model_validate_json` (D-OLLAMA-4). Alternativa B (descartada por ahora): un
   `model_validator(mode="before")` en el contrato `_RequirementContent`; afecta a P5/P6 y se
   deja para cuando se implemente P6.

---

## 5. Orden de implementación

```
D-OLLAMA-1 (config)        ← fija num_ctx / think / temperature
   │
D-OLLAMA-2 (wiring P2)     ← build_p2_config los pasa a LlmSettings.parameters
   │
D-OLLAMA-3 (adaptador)     ← ollama_llm.py: think al body, num_ctx/temp a options
   │
D-OLLAMA-4 (saneo [""] )   ← P2._parse filtra "" antes de validar
   │
pruebas                   ← adaptador Ollama, saneo, defaults de config
```

## 6. Pruebas

- **Adaptador Ollama** (`tests/test_llm_clients.py`): `think` viaja en el `body` y **no** en
  `options`; `num_ctx` viaja en `options`; `temperature` en `options`.
- **Saneo de `[""]`** (`tests/test_p2_requirements.py`): una respuesta con `[""]` en
  `business_rules`/`conditions`/`unspecified_information` se acepta y queda como `[]`.
- **Config** (`tests/test_p3_embeddings.py` ya cubre el patrón; añadir defaults de
  `llm_num_ctx`/`llm_think`/`llm_temperature`).
- **Regresión:** suite completa sin fallos.

---

## 7. Alternativa sin tocar código (y sus límites)

Crear un Modelfile con `PARAMETER num_ctx 16384` a partir de `qwen3.5` y apuntar `LLM_MODEL` a ese
modelo. **Resuelve el truncado por contexto**, pero:

- No apaga el thinking (Ollama no expone `think` como `PARAMETER` de Modelfile; va por API).
  Con thinking activo sigue gastando tokens.
- No resuelve el `[""]` (D-OLLAMA-4): sigue fallando la validación aunque el JSON no se trunque.

Por eso conviene el cambio de código; el Modelfile queda como parche rápido solo para el contexto.

---

## 8. Nota de actualización a `llm_client_design.md`

Al implementar, actualizar en `llm_client_design.md`:

- Sección **`clients/ollama_llm.py`**: añadir que `num_ctx` y `temperature` van en `options`, pero
  `think` va en el `body` (no en `options`).
- Sección **Variables de entorno**: añadir `LLM_NUM_CTX`, `LLM_THINK`, `LLM_TEMPERATURE`.
- Tabla de decisiones: cerrar D-LLM-3 (modelo por defecto ya está resuelto con `LLM_MODEL`) y
  añadir D-OLLAMA-1..4 con remisión a este documento.

El saneo de `[""]` (D-OLLAMA-4) es un ajuste de la etapa P2, no del cliente LLM; se documenta en el
propio `p2_requirements.py` y, si se mueve al contrato (opción B), en `p2.py`.

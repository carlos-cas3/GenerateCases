# Issue — Saneo de `requirement_codes` en la respuesta del LLM (P6)

> **Estado:** abierta. Detectada en la primera iteración de calibración con el pipeline real
> (generación `6122e12a-0a5b-4cfc-9da7-6229faa3c2c3`).
> **Área:** `ai_service/pipeline/stages/p6_generation.py`,
> `ai_service/pipeline/stages/llm_output.py`.
> **Prioridad:** alta — provoca `LLM_INVALID_OUTPUT` en todas las unidades afectadas y deja
> la generación en `failed` si supera el `failure_threshold`.

---

## Descripción del problema

Durante la validación de la respuesta del LLM en P6, `P6LlmResponse` rechaza cualquier caso de
prueba cuyo `requirement_codes` incluya un RF que no sea objetivo de la unidad (validación
`target_codes` en `TestCaseDraft._consistent`). Este comportamiento es correcto por contrato, pero
expone una fragilidad ante respuestas del LLM que enlacen RF de contexto en vez de limitarse a
los RF objetivo.

El error observado en el log:

```
Value error, RF que no son objetivo de la unidad: ['RF-003']
  test_cases.0 → requirement_codes: ['RF-001', 'RF-003']
  test_cases.1 → requirement_codes: ['RF-002', 'RF-003']
```

`RF-003` pertenece a otra unidad y llega al mensaje como RF de contexto. El contenido de los
casos (título, pasos, resultado esperado) es correcto; solo los códigos están mal. El validador
descarta el caso entero y, al agotar los reintentos, marca la unidad como fallida con
`LLM_INVALID_OUTPUT`.

---

## Causa raíz

El prompt instruye explícitamente a no enlazar RF de contexto (instrucción 2 de `contexto.md` y
`contexto_sin_clustering.md`). Sin embargo, el LLM puede no respetar esta restricción con
consistencia, ya sea por la longitud del mensaje, la complejidad del schema de salida o la
ambigüedad al distinguir RF objetivo de RF de contexto cuando ambos aparecen en el mismo mensaje.

Este es un problema de robustez del pipeline ante variabilidad en la salida del LLM, no un defecto
del prompt en sí.

---

## Solución propuesta

Añadir un paso de saneo en `llm_output.py` análogo a `drop_blank_list_items` (D-OLLAMA-4):
**filtrar de `requirement_codes` los códigos que no pertenezcan al conjunto `target_codes` de la
unidad**, antes de pasar el JSON a `P6LlmResponse.model_validate_json`.

Comportamiento esperado del saneo:

- Si un caso enlaza `['RF-001', 'RF-003']` y `target_codes = {'RF-001', 'RF-002'}`, el resultado
  es `['RF-001']`.
- Si tras el filtro un caso queda con `requirement_codes` vacío (`[]`), el caso se descarta
  (el validador exige `min_length=1` y un caso sin RF enlazado no tiene valor).
- Si el texto no es JSON válido, se devuelve sin tocar para que el validador informe el error real.
- Campos distintos de `requirement_codes` no se modifican.

La función nueva en `llm_output.py`:

```python
def filter_requirement_codes(raw: str, target_codes: set[str]) -> str:
    """Filtra de `requirement_codes` los RF que no son objetivo de la unidad antes de validar.

    El LLM puede enlazar RF de contexto aunque el prompt lo prohíba. En vez de rechazar el caso
    entero se eliminan los códigos foráneos. Un caso que queda sin códigos se descarta.
    Si el texto no es JSON se devuelve igual para que la validación informe el error real.
    """
```

Se llama en `GenerationStage._parse`, después de `drop_blank_list_items` y antes de
`P6LlmResponse.model_validate_json`:

```python
raw = filter_requirement_codes(drop_blank_list_items(strip_code_fence(response.text)), targets)
```

---

## Impacto en contratos y tests

- **Contratos (`p6.py`):** sin cambios. La validación `target_codes` en `TestCaseDraft` sigue
  siendo la fuente de verdad; el saneo solo evita que lleguen códigos inválidos al validador.
- **`llm_output.py`:** función nueva `filter_requirement_codes`. Se exporta desde el módulo.
- **`p6_generation.py`:** un cambio de una línea en `_parse` para insertar la llamada.
- **Tests nuevos sugeridos:**
  - `filter_requirement_codes` descarta código foráneo y conserva los válidos.
  - `filter_requirement_codes` descarta el caso entero si todos sus códigos son foráneos.
  - `filter_requirement_codes` no toca texto que no sea JSON.
  - E2E en `test_p6_generation.py`: unidad cuya respuesta incluye un RF de contexto en
    `requirement_codes` → el caso se persiste con solo los RF objetivo.

---

## Advertencia

El saneo corrige silenciosamente una violación del contrato del LLM. Para mantener observabilidad
se recomienda emitir un aviso `REQUIREMENT_CODES_FILTERED` (nuevo código de `StageWarning`) cuando
se descarte al menos un código, con el detalle de qué unidades y cuántos códigos se filtraron.
Esto permite distinguir en calibración si el problema es recurrente o puntual, y decidir si ajustar
el prompt o el schema de salida en una fase posterior.

---

## Evidencia

Generación `6122e12a-0a5b-4cfc-9da7-6229faa3c2c3`, unidad `U-001`, intento 1.
Respuesta cruda del LLM (fragmento relevante) y error de validación capturados con nivel DEBUG:

```
DEBUG ai_service.pipeline.stages.p6_generation P6 unidad inválida
generation_id=6122e12a-0a5b-4cfc-9da7-6229faa3c2c3 unit_id=U-001 attempt=1 raw={
  "test_cases": [
    {
      "title": "Generación de reporte de ventas mensual en formato PDF",
      "steps": [
        { "step_number": 1, "action": "...", "expected_result": "..." },
        { "step_number": 2, "action": "...", "expected_result": "..." }
      ],
      "expected_result": "El reporte se genera correctamente en formato PDF ...",
      "requirement_codes": ["RF-001", "RF-003"]
    },
    {
      "title": "Generación de reporte de ventas mensual en formato CSV",
      ...
      "requirement_codes": ["RF-002", "RF-003"]
    }
  ]
} err=2 validation errors for P6LlmResponse
test_cases.0
  Value error, RF que no son objetivo de la unidad: ['RF-003']
  [type=value_error, input_value={...requirement_codes: ['RF-001', 'RF-003']}]
test_cases.1
  Value error, RF que no son objetivo de la unidad: ['RF-003']
  [type=value_error, input_value={...requirement_codes: ['RF-002', 'RF-003']}]
```

El mismo error se repitió en el intento 2, agotando los reintentos (`P6_MAX_RETRIES=1`) y
dejando la unidad como `LLM_INVALID_OUTPUT`. `RF-003` pertenecía a otra unidad y llegaba al
mensaje como RF de contexto.

---

## Referencias

- `docs/prompts_fases/Fase 7/cierre_documental_fase7.md` §3 decisión 4 (saneo de salida del LLM).
- `ai_service/pipeline/stages/llm_output.py` — `drop_blank_list_items` como precedente (D-OLLAMA-4).
- `docs/llm_ollama_context.md` — historial de ajustes por variabilidad en la salida del LLM.

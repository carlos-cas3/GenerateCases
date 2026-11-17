# Issue resolver — Requisitos no funcionales en la salida de P2

> **Fase:** 6 (detectado al verificar con datos reales en `HUtest/`)
> **Estado:** ✅ implementado (pendiente verificación con documento real, ver §8)
> **Afecta a:** `ai_service/pipeline/prompts/texts/p2_requirements.md`,
> `ai_service/pipeline/contracts/p2.py`, `ai_service/pipeline/stages/p2_requirements.py`
> **No afecta a:** `schema.sql`, contratos de P3/P4/P5/P6, `openapi.yaml`

---

## 1. Problema observado

Al correr una generación real con el documento `HUtest/Cantidad_HU_2.txt` (2 HU,
secciones "Criterios de aceptación", "Reglas de negocio" y "Restricciones"), P2
extrajo 12 RF. De esos, 2 son claramente no funcionales:

| RF | Descripción | Tipo real |
|---|---|---|
| RF-005 | El sistema debe generar un archivo de reporte que no supere los 10 MB | Restricción técnica |
| RF-011 | El reporte debe generarse en un máximo de 5 segundos | Requisito de rendimiento |

Ambos llegaron a P3 (se embebieron), a P4 (se intentó agruparlos) y quedaron
como RF sin cluster (`unassigned_requirements`). En consecuencia P5 emitió el
aviso `UNASSIGNED_REQUIREMENTS` con 6 RF, de los cuales 2 no deberían haber
entrado al pipeline en absoluto.

---

## 2. Causa raíz

El diseño tiene clasificación a nivel de **HU completa** (`candidata_funcional` /
`requiere_aclaracion` / `no_aplicable`), pero no a nivel de **RF individual**.

El prompt (`p2_requirements.md`) dice que una HU es `no_aplicable` si es un
requisito no funcional, pero no instruye al LLM sobre qué hacer cuando una HU
`candidata_funcional` contiene secciones mixtas (funcionales + restricciones
técnicas + rendimiento). El LLM extrae todo lo que encuentra en la HU sin
distinguir.

El contrato `RequirementDraft` tampoco tiene ningún campo que marque si un
requisito es funcional o no, por lo que P2 no tiene forma de filtrarlo después
de recibirlo del LLM.

---

## 3. Decisión tomada (D-NFR-1)

**Opción elegida: el LLM marca, P2 filtra.**

Cada `RequirementDraft` en la respuesta del LLM lleva un campo booleano
`is_functional`. El LLM decide si el requisito es funcional; P2 descarta los
`False` **antes de numerar** los `RF-xxx`, de forma determinista.

### Por qué esta opción

| Criterio | Opción A (filtro solo en prompt) | Opción B (campo + filtro en P2) |
|---|---|---|
| Depende del modelo | Sí — falla con LLMs menos capaces | No — P2 siempre filtra |
| Cambio en contrato downstream | No | No (P3/P4/P5 nunca ven los descartados) |
| Cambio en schema.sql | No | No |
| Trazabilidad | Ninguna (el LLM simplemente no los devuelve) | Los descartados quedan en el log |
| Complejidad de implementación | Mínima | Baja |

La opción B es más robusta porque el filtro es determinista independientemente
del modelo. Con Ollama local (`sachasayan/interimlabs-qwen3.5-4b`) la
instrucción de "no extraigas" en el prompt no es suficientemente fiable.

### Qué se descarta y qué no

Se descarta como no funcional cualquier RF que el LLM marque con
`is_functional: false`. Ejemplos típicos:

- Restricciones técnicas (tamaño de archivo, límites de memoria)
- Requisitos de rendimiento (tiempo de respuesta, throughput)
- Requisitos de seguridad genéricos sin comportamiento funcional (ej. "solo admin
  puede acceder" **sin** describir qué hace el sistema cuando accede un no-admin)
- Restricciones de infraestructura o plataforma

**No se descarta** un requisito funcional que mencione una condición de acceso
con comportamiento asociado (ej. "el sistema muestra un error 403 si el usuario
no es admin" — eso sí es funcional).

---

## 4. Artefactos que cambian

### 4.1 Prompt — `ai_service/pipeline/prompts/texts/p2_requirements.md`

Añadir en la sección **2. Extracción de RF**, antes de "RF simple":

```markdown
### Requisitos funcionales vs no funcionales

Solo extrae requisitos **funcionales**: comportamientos o salidas del sistema
que se pueden verificar con un caso de prueba funcional.

**No extraigas** como RF (márcalos con `is_functional: false` si aparecen):
- Restricciones técnicas (tamaño máximo de archivo, límites de memoria, etc.)
- Requisitos de rendimiento (tiempo de respuesta, throughput, latencia)
- Requisitos de disponibilidad o fiabilidad (uptime, SLA)
- Restricciones de infraestructura o plataforma
- Requisitos de seguridad genéricos sin comportamiento funcional asociado
  (ej. "solo admin puede acceder" sin describir qué ocurre si no es admin)

Si el texto describe un límite técnico, añádelo en `unspecified_information`
del RF funcional más cercano en vez de crear un RF separado.
```

Añadir `is_functional` al ejemplo JSON de la sección **5. Formato de salida**:

```json
{
  "description": "El sistema debe exportar el reporte de ventas en formato PDF.",
  "is_functional": true,
  ...
}
```

Y un ejemplo de RF no funcional descartado:

```json
{
  "description": "El archivo generado no debe superar los 10 MB.",
  "is_functional": false,
  "source_text": "El archivo no supera 10 MB.",
  "user_story_codes": ["HU-001"]
}
```

### 4.2 Contrato — `ai_service/pipeline/contracts/p2.py`

En `_RequirementContent`, añadir el campo:

```python
is_functional: bool = True
```

Con `True` como default para mantener compatibilidad con tests existentes que
construyen `RequirementDraft` sin ese campo.

`FunctionalRequirement` hereda de `_RequirementContent`, por lo que también
tendrá el campo. Sirve para trazabilidad en el log; los RF con
`is_functional=False` nunca llegan a `P2Output`.

### 4.3 Consolidación — `ai_service/pipeline/stages/p2_requirements.py`

En `RequirementsStage._consolidate()`, filtrar antes de numerar:

```python
functional_drafts = [d for d in drafts if d.is_functional]
# (el resto del método usa functional_drafts en lugar de drafts)
```

Añadir un aviso `NON_FUNCTIONAL_DISCARDED` si se descartó al menos uno:

```python
StageWarning(
    code="NON_FUNCTIONAL_DISCARDED",
    message=f"{n} requisito(s) no funcional(es) descartados.",
    details={"descriptions": [d.description for d in discarded]},
)
```

Registrar en el log cada RF descartado con nivel `INFO`:

```python
logger.info(
    "P2 RF no funcional descartado generation_id=%s description=%s",
    context.generation_id, draft.description,
)
```

---

## 5. Artefactos que NO cambian

| Artefacto | Motivo |
|---|---|
| `schema.sql` | Los RF no funcionales nunca se persisten; no necesitan columna |
| Contratos de P3, P4, P5, P6 | Solo reciben `FunctionalRequirement` ya filtrados |
| `openapi.yaml` | El campo `is_functional` es interno del pipeline; no se expone en la API |
| `persist_p2_requirements` (RPC) | El payload que llega ya solo tiene RF funcionales |
| Tests existentes de P2 | El campo tiene `default=True`; los tests que no lo usan siguen pasando |

---

## 6. Tests nuevos a añadir

En `tests/test_p2_requirements.py` (o el archivo de tests de P2 correspondiente):

1. **RF no funcional marcado se descarta antes de numerar.**
   - Entrada: 2 RF, uno con `is_functional=False`.
   - Esperado: `P2Output.requirements` tiene 1 RF numerado `RF-001`; el descartado no aparece.

2. **Aviso `NON_FUNCTIONAL_DISCARDED` se emite cuando hay descartes.**
   - Esperado: `StageResult.warnings` contiene el aviso con los `descriptions` correctos.

3. **Sin descartes no se emite el aviso.**
   - Entrada: todos los RF con `is_functional=True` (o sin el campo).
   - Esperado: no hay aviso `NON_FUNCTIONAL_DISCARDED`.

4. **El LLM devuelve solo RF no funcionales → 0 RF → `skip_remaining=True`.**
   - Verificar que el comportamiento de D-29 sigue funcionando tras el filtro.

5. **Wiring E2E con documento real.**
   - Usar el texto de `HUtest/Cantidad_HU_2.txt` en un test de integración.
   - Esperado: RF-005 y RF-011 equivalentes no aparecen en `P2Output.requirements`.

---

## 7. Orden de implementación

```
1. Actualizar p2_requirements.md (prompt)
       ↓
2. Añadir is_functional a _RequirementContent en contracts/p2.py
       ↓
3. Filtrar en RequirementsStage._consolidate()
       ↓
4. Añadir aviso NON_FUNCTIONAL_DISCARDED en _warnings()
       ↓
5. Escribir los tests nuevos
       ↓
6. Correr suite completa (493 tests deben seguir pasando + los nuevos)
```

---

## 8. Criterios de cierre

- [x] `p2_requirements.md` incluye la sección "Requisitos funcionales vs no funcionales"
      y el campo `is_functional` en el ejemplo JSON.
- [x] `RequirementDraft` y `FunctionalRequirement` tienen `is_functional: bool = True`.
- [x] `_consolidate()` descarta los `is_functional=False` antes de numerar los `RF-xxx`.
- [x] Se emite `NON_FUNCTIONAL_DISCARDED` cuando hay al menos un descarte.
- [x] Los RF descartados se loguean con nivel `INFO`.
- [x] Suite completa pasa sin regresión (499 tests: 493 previos + 6 nuevos).
- [ ] Con el documento `HUtest/Cantidad_HU_2.txt`, los equivalentes de RF-005 y RF-011
      no aparecen en `generation_stages` ni en `functional_requirements`.

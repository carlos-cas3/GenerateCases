# Por revisar — Semántica de `filtered_count` en el aviso `REQUIREMENT_CODES_FILTERED`

> **Estado:** por revisar. Aún no se decide qué hacer con `filtered_count`. Este documento
> reúne toda la información relevante —incluida una **evidencia de ejecución real** (§Evidencia
> de ejecución real) que muestra el problema tal como se manifestó en una generación— para
> decidirlo más adelante. No requiere acción inmediata: el pipeline funciona correctamente y la
> suite pasa (533 tests).
> **Quien lo resuelva** debe elegir una de las opciones de §Opciones de resolución, aplicarla, y
> **explicar por qué eligió esa forma y en qué ayuda** hacerlo así (ver §Nota para quien resuelva).
> **Área:** `ai_service/pipeline/stages/p6_generation.py` (construcción del aviso),
> `ai_service/pipeline/stages/llm_output.py` (`filter_requirement_codes_with_stats`, que
> acumula los códigos filtrados).
> **Origen:** revisión del commit `e5eab309` ("issue p6"), que resolvió
> `issue_p6_requirement_codes_sanitization.md`.

---

## Descripción

En el aviso `REQUIREMENT_CODES_FILTERED` (emitido cuando una unidad exitosa enlazó RF que no
son objetivo y fueron filtrados) el detalle por unidad expone dos campos que miden cosas
distintas, pero cuyos nombres sugieren que deberían coincidir:

```python
"filtered_codes": sorted(set(r.filtered_codes)),   # códigos distintos, ordenados
"filtered_count": len(r.filtered_codes),           # ocurrencias totales (con duplicados)
```

`r.filtered_codes` es una lista que acumula **cada ocurrencia** de un código foráneo, una por
caso. Si el mismo RF aparece en varios casos, la lista contiene repetido ese código, y
`filtered_count` cuenta todas las apariciones. En cambio `filtered_codes` se deduplica con
`set(...)`. Por eso puede verse `filtered_codes: ["RF-003"]` junto a `filtered_count: 3` y dar
la impresión de que faltan códigos en la lista, cuando en realidad es el mismo código repetido
en tres casos.

---

## Código involucrado

### Acumulación de ocurrencias — `llm_output.py:69`

```python
filtered.extend(code for code in codes if isinstance(code, str) and code not in target_codes)
```

`filtered` (el valor de retorno) lleva **todas** las apariciones. Por cada caso se añade cada
código foráneo, sin deduplicar. Esa lista es lo que después se guarda en `r.filtered_codes`
(`p6_generation.py:81` y `:219`).

### Construcción del detalle del aviso — `p6_generation.py:345-362`

```python
filtered = {
    r.unit.unit_id: {
        "filtered_codes": sorted(set(r.filtered_codes)),
        "filtered_count": len(r.filtered_codes),
        "dropped_cases": r.dropped_cases,
    }
    for r in results
    if r.filtered_codes and r.failure is None
}
if filtered:
    warnings.append(
        StageWarning(
            code="REQUIREMENT_CODES_FILTERED",
            message=f"{len(filtered)} unidad(es) enlazaron RF que no son objetivo; se filtraron.",
            details={"units": filtered},
        )
    )
```

- `filtered_codes` = `sorted(set(...))` → **distintos**.
- `filtered_count` = `len(r.filtered_codes)` → **ocurrencias** (con duplicados).
- El log de `p6_generation.py:250` ya imprime los distintos ordenados (`sorted(set(filtered))`),
  así que el log y el campo `filtered_codes` son consistentes entre sí; el único que cuenta
  ocurrencias es `filtered_count`.

---

## Ejemplo concreto (del test)

`tests/test_p6_generation.py::test_context_requirements_are_filtered_and_the_case_is_persisted`.

Unidad `U-001` con `target_codes = {RF-001, RF-002}` y `RF-003` como contexto. El LLM devuelve
3 casos, cada uno enlazando `RF-003`:

| Caso | `requirement_codes` del LLM | tras filtrar |
|------|------------------------------|--------------|
| 0 | `["RF-001", "RF-003"]` | queda `["RF-001"]`; se filtra `RF-003` |
| 1 | `["RF-002", "RF-003"]` | queda `["RF-002"]`; se filtra `RF-003` |
| 2 | `["RF-003"]` | todo foráneo → caso descartado; se filtra `RF-003` |

Resultado:

- `r.filtered_codes = ["RF-003", "RF-003", "RF-003"]`
- `filtered_codes = ["RF-003"]` (distintos)
- `filtered_count = 3` (ocurrencias)
- `dropped_cases = 1`

El test fija exactamente ese comportamiento:

```python
assert result.warnings[0].details == {
    "units": {"U-001": {"filtered_codes": ["RF-003"], "filtered_count": 3, "dropped_cases": 1}}
}
```

---

## ¿Es un bug?

**No es un bug funcional.** El saneo filtra correctamente los códigos foráneos, los casos se
persisten solo con RF objetivo y la suite pasa (533 tests). Es un problema de
**claridad/observabilidad**: los dos campos responden a preguntas distintas y el nombre
`filtered_count` no deja claro que cuenta ocurrencias en vez de elementos de `filtered_codes`.

Las dos preguntas que cada campo responde, ambas útiles para calibración:

- `filtered_codes` → *qué* códigos confunde el LLM (para decidir si ajustar el prompt o el
  schema). Aquí: solo `RF-003`.
- `filtered_count` → *cuántas veces* se equivocó (indicador de severidad/frecuencia). Aquí: 3.

---

## Evidencia de ejecución real

No es solo un caso de test: el problema se manifestó en una generación real del pipeline.
**Generación `caa5f52c-0f82-4b3c-8eee-5d44f36348ed`** (documento `Cantidad_HU_2.txt`),
estado `completed`, con el aviso `REQUIREMENT_CODES_FILTERED` disparado en P6. Para reproducir
la inspección de esta (o cualquier otra) generación:

```bash
py scripts/inspect_generation.py <generation_id>
```

(`scripts/inspect_generation.py` lee `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` de `.env` y
muestra estado, etapas, avisos de P6, `llm_runs` y casos persistidos.)

### Datos de la generación

- Resumen: 2 HU, 6 RF, 2 clusters (unidades), 12 casos, 0 unidades fallidas.
- P6: `units_succeeded=2`, `retries_used=0`, `uncovered_requirements=0`, `units_failed=0`.
- Unidades (por cluster): **U-001** = cluster de 2 RF (`RF-001`, `RF-002`); **U-002** = cluster
  de 3 RF (`RF-003`, `RF-004`, `RF-005`). `RF-006` quedó sin asignar en P4/P5 (no llega a P6).

### Aviso disparado (detalle crudo)

```json
{
  "code": "REQUIREMENT_CODES_FILTERED",
  "message": "1 unidad(es) enlazaron RF que no son objetivo; se filtraron.",
  "details": {
    "units": {
      "U-001": {
        "dropped_cases": 0,
        "filtered_codes": ["RF-003"],
        "filtered_count": 2
      }
    }
  }
}
```

`RF-003` es objetivo de **U-002** y llegó a U-001 como RF de contexto. El LLM lo enlazó en **2
casos** de U-001; el saneo lo eliminó y, al quedar `dropped_cases=0`, los casos sobrevivieron con
sus RF objetivo válidos (`RF-001`/`RF-002`). Sin el saneo, con `P6_FAILURE_THRESHOLD=0.0` esos 2
casos habrían invalidado U-001 (`LLM_INVALID_OUTPUT`) y abortado toda la generación.

### Enlaces persistidos (tabla `requirement_test_cases`)

Confirman que ningún caso de U-001 quedó enlazado al `RF-003` filtrado:

```
U-001: CP-001 -> RF-001   CP-002 -> RF-002   CP-003 -> RF-001
U-002: CP-004 -> RF-003   CP-005 -> RF-004   CP-006 -> RF-005
       CP-007 -> RF-003   CP-008 -> RF-004   CP-009 -> RF-005
       CP-010 -> RF-003   CP-011 -> RF-004   CP-012 -> RF-005
```

### El punto a resolver, visto en datos reales

Aquí se ve la inconsistencia de naming de forma concreta:

- `filtered_codes: ["RF-003"]` → **1** código distinto.
- `filtered_count: 2` → **2** ocurrencias (el mismo `RF-003` en 2 casos).

Un lector del aviso vería la lista con un elemento y el conteo en 2, y podría pensar que falta
un código en la lista. La función del pipeline es correcta (los 2 casos se filtraron y se
persistieron solo con RF objetivo); lo único abierto es la **semántica del campo
`filtered_count`**. Esta corrida sirve como caso real de referencia para decidir el cambio y
para validar que la solución elegida sigue reportando bien la frecuencia.

---

## Opciones de resolución (sin decidir)

1. **Renombrar** `filtered_count` → `filtered_occurrences` (o `filtered_total`), dejando claro
   que cuenta ocurrencias. Mínimo impacto; solo cambia el nombre del campo del detalle.
2. **Añadir un tercer campo** con el conteo distinto, p. ej. `filtered_distinct_count =
   len(set(r.filtered_codes))`, manteniendo `filtered_count` como ocurrencias. Más explícito,
   pero agranda el detalle.
3. **Hacer que `filtered_count` cuente distintos** (`len(set(...))`), alineándolo con
   `filtered_codes`. Pierde la información de frecuencia.
4. **Dejarlo como está** y documentar la semántica aquí y/o en `cierre_documental_fase7.md` §3
   decisión 9. Es la opción de menor riesgo si la frecuencia no se usa todavía.

---

## Impacto si se cambia el nombre o el valor

Cualquier cambio en los nombres o valores del detalle del aviso toca:

- `ai_service/pipeline/stages/p6_generation.py:350-351` (construcción del detalle).
- `tests/test_p6_generation.py` (la aserción `result.warnings[0].details == {...}`).
- `docs/prompts_fases/Fase 7/cierre_documental_fase7.md` §3 decisión 9 (describe
  `filtered_codes`, `filtered_count`, `dropped_cases`).
- `docs/calibracion_resultados/plantilla.md` (lista `REQUIREMENT_CODES_FILTERED` entre los
  avisos a revisar en calibración).

El log de `p6_generation.py:250` no se ve afectado por cambiar el campo del detalle.

---

## Nota para quien resuelva esto

Al aplicar la opción elegida:

1. **Dejar constancia de la decisión y su motivo** en este archivo: qué opción se eligió, por
   qué frente a las demás (correctitud, claridad, impacto en calibración, reversibilidad) y qué
   se gana haciéndolo así. Evitar cambios "porque sí": este campo se usa en calibración real y
   conviene que el motivo quede registrado.
2. **Actualizar todo lo que cita los campos** (ver §Impacto si se cambia) y mantener la suite en
   verde.
3. **Revisar la generación `caa5f52c-0f82-4b3c-8eee-5d44f36348ed`** con `scripts/inspect_generation.py`
   tras el cambio (si la generación sigue accesible) para confirmar que el detalle del aviso se
   lee sin ambigüedad; si no, basta con el caso del test.

---

## Referencias

- `scripts/inspect_generation.py` — inspecciona una generación por ID (estado, etapas,
  avisos de P6, casos persistidos). Lee credenciales de `.env`.
- Generación `caa5f52c-0f82-4b3c-8eee-5d44f36348ed` — evidencia real del problema (documentada
  en §Evidencia de ejecución real).
- `docs/prompts_fases/Fase 7/issue_p6_requirement_codes_sanitization.md` — issue original que
  introdujo el saneo y el aviso.
- `docs/prompts_fases/Fase 7/cierre_documental_fase7.md` §3 decisión 9 — documenta el aviso y
  sus campos.
- `ai_service/pipeline/stages/llm_output.py:48` — `filter_requirement_codes_with_stats`
  (acumulación en `:69`).
- `ai_service/pipeline/stages/p6_generation.py:345-362` — construcción del aviso.
- `tests/test_p6_generation.py::test_context_requirements_are_filtered_and_the_case_is_persisted`
  — fija el comportamiento actual.
- Commit `e5eab309` ("issue p6").

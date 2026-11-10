# Decisiones v1 — RPCs de persistencia

> **Guía de sugerencia.** Este documento **no es obligatorio**: son recomendaciones sobre los RPC
> de persistencia (`persist_p2_requirements`, `persist_p4_clusters`, `persist_p6_unit`). Si
> consideras correcta una recomendación, impleméntala y listo; si no, se descarta.

---

## `persist_p2_requirements`

**Hecho:** idempotencia (T-01) — `ON CONFLICT (generation_id, code)` en `functional_requirements`
(`DO UPDATE`) y `ON CONFLICT` en `user_story_requirements` (`DO NOTHING`). Un reintento con el
mismo payload ya no falla por PK/unique duplicada.

**Recomendación (T-02 — HU duplicadas en el payload):** si un `user_story_code` aparece repetido
dentro de `classifications`, hoy el `UPDATE … FROM` actualiza la fila una sola vez y el conteo
lanza el mensaje engañoso *"N de N clasificaciones apuntan a HU inexistentes"*.

- **Cómo solucionarlo:** antes del `UPDATE`, detectar `user_story_code` repetidos en el payload y
  lanzar un mensaje correcto (*"HU-001 aparece 2 veces"*). Acompañar con un test de la RPC.
- El contrato `P2Output` ya impide duplicados, así que esto es defensa en profundidad.

---

## `persist_p4_clusters`

**Hecho:** idempotencia (T-01) — `ON CONFLICT (id)` en `clusters` (`DO UPDATE`, sin tocar la
clave) y `ON CONFLICT` en `cluster_requirements` / `unassigned_requirements` (`DO NOTHING`).

**Recomendación:** sin pendientes. `id` queda como la clave de idempotencia del cluster (es
obligatorio en el payload, así que un reintento envía el mismo `id`).

---

## `persist_p6_unit`

**Hecho:** idempotencia (T-01) — `ON CONFLICT (generation_id, code)` en `test_cases`
(`DO UPDATE`, no toca `id` ni `created_at`), `ON CONFLICT (test_case_id, step_number)` en
`test_steps` (`DO NOTHING`) y `ON CONFLICT` en `requirement_test_cases` (`DO NOTHING`).

**Recomendación (D-18 — soporte del vínculo CP↔RF):** los vínculos se insertan siempre `pending`
sin `validation_notes` (decisión D-18 de la Fase 3). Si en una versión futura se quiere registrar
el soporte del vínculo, la RPC y la tabla `requirement_test_cases` ya tienen las columnas
(`validation_method`, `validation_notes`); bastaría con que el payload las llevara. No es
necesario para v1.

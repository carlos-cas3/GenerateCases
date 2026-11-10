# Decisiones sobre `schema.sql` — Fase 4

> **Fecha:** 2026-11-10
> **Origen:** `tareas_pendientes_final_fase3.md` (sección 4) y `cierre_documental.md` (sección 3).
> **Alcance:** registro de las decisiones T-01, T-02 y T-04 que se diferenciaron al cierre de
> la Fase 3 porque las RPCs se invocan desde las etapas reales recién en la Fase 4.

---

## T-01 — Idempotencia de las RPCs ✅ DECIDIDO E IMPLEMENTADO

**Decisión:** opción (a) — **RPCs idempotentes por clave**, vía `ON CONFLICT`.

**Interpretación de "mismo contenido":** se interpreta como **"misma clave"** (`id` o
`generation_id, code`). Es correcta para el escenario real de T-01 (reintento por timeout de red),
donde el reintento envía **exactamente el mismo payload** → misma clave = mismo contenido por
construcción. No se compara el jsonb completo (más caro y sin beneficio en este caso).

**Reglas aplicadas:**

| Tipo de tabla | Regla | Motivo |
|---|---|---|
| Entidad (con contenido): `functional_requirements`, `clusters`, `test_cases` | `ON CONFLICT (clave) DO UPDATE SET <columnas no-clave>` (last-write-wins) | Un reintento con mismo dato es no-op; si alguna vez llega un dato corregido, gana el nuevo. No se toca `id` ni `created_at`. |
| Puente (solo relaciones): `user_story_requirements`, `cluster_requirements`, `unassigned_requirements`, `test_steps`, `requirement_test_cases` | `ON CONFLICT (clave) DO NOTHING` | Son enlaces aditivos; re-insertar el mismo enlace es no-op. |

**Claves usadas (todas existen como UNIQUE/PK en `schema.sql`):**

| RPC | Tabla | Conflict target |
|---|---|---|
| P2 | `functional_requirements` | `(generation_id, code)` |
| P2 | `user_story_requirements` | `(generation_id, user_story_id, requirement_id)` |
| P4 | `clusters` | `(id)` |
| P4 | `cluster_requirements` | `(generation_id, cluster_id, requirement_id)` |
| P4 | `unassigned_requirements` | `(generation_id, requirement_id)` |
| P6 | `test_cases` | `(generation_id, code)` |
| P6 | `test_steps` | `(test_case_id, step_number)` |
| P6 | `requirement_test_cases` | `(generation_id, requirement_id, test_case_id)` |

**Cobertura:** las **tres** RPCs (P2, P4, P6) se hicieron idempotentes de una vez, aunque P4 se use
en Fase 5 y P6 en Fase 7. La idempotencia es propiedad de la RPC, no del caller; así se evita
reabrir `schema.sql` en fases posteriores para el mismo motivo.

**Cambios aplicados en `supabase/schema.sql` (commit pendiente):** 8 cláusulas `ON CONFLICT`
añadidas a los INSERTs de las tres RPCs. El `UPDATE user_stories` de P2 ya era idempotente (un
UPDATE reaplicado no cambia nada) y no se modificó.

**Edge case descartado:** si un mismo `id` se reutiliza para un `code` distinto en la misma
generación (p. ej., `test_cases` con id repetido pero code distinto), el `ON CONFLICT` objetivo
no atrapa el conflicto de PK y se eleva error. No ocurre en el escenario de reintento de T-01
(mismo payload → mismo id y mismo code), así que no se protege contra él.

**No implementado (opciones descartadas):**
- (b) "no reintentar RPCs desde el cliente": un timeout post-commit dejaría la generación `failed`
  con datos guardados (falso fallo para el usuario). Se prefiere idempotencia real.
- (c) "clave de idempotencia por llamada": robusta pero requiere tabla adicional de
  `idempotency_keys` — infraestructura extra no justificada por la probabilidad del escenario.

**Verificación:**
- Balance del SQL confirmado: 5 funciones, 5 pares `$$`, 5 `begin`/`end;`.
- 180 tests de contratos (`test_contracts.py` + `test_contracts_rpc.py`) pasan — los payloads de
  `to_rpc_payload` siguen cuadrando con las RPCs.
- **Pendiente:** desplegar `schema.sql` contra el proyecto Supabase para que los cambios surtan
  efecto (las funciones son `create or replace`, así que re-ejecutar el script las reemplaza).

---

## T-02 — HU duplicadas en `persist_p2_requirements` ⏸ PENDIENTE

Duplicados de `user_story_code` **dentro de un mismo payload** (no archivos repetidos). Hoy, si un
código aparece dos veces en `classifications`, el `UPDATE ... FROM` actualiza la fila una sola
vez y el conteo `v_updated <> v_expected` lanza el mensaje engarososo *"N de N clasificaciones
apuntan a HU inexistentes"*. El contrato `P2Output` ya impide duplicados, así que es defensa en
profundidad.

**Recomendado:** opción (a) — rechazar duplicados explícitamente con un mensaje correcto
(*"HU-001 aparece 2 veces"*) + test de la RPC.

**Estado:** sin decisión todavía. No bloquea el inicio de la implementación de P2 (el contrato ya
filtra los duplicados), pero conviene aplicarlo antes de que P2 se conecte a la RPC real.

---

## T-04 — Backfill de `position` en `user_stories` ⏸ PENDIENTE

La migración aditiva añade `position` nullable sin rellenar filas antiguas. Si no hay datos en
producción, basta la opción (b): dejar `position` nullable y documentar el orden en `openapi.yaml`.

**Estado:** sin decisión todavía. Bajo riesgo si no hay datos en producción.

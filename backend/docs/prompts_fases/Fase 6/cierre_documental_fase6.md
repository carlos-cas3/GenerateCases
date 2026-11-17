# Cierre documental — Fase 6 (P5 contexto estructurado)

> **Estado:** ✅ implementación cerrada en código y pruebas (493 tests pasan; antes de la fase
> eran 464). Pendiente **fuera de código**: calibrar `P5_MAX_TOKENS_PER_UNIT` con documentos
> reales cuando P6 sea real (ver §6).
> **Alcance:** T-F6-01 … T-F6-05 de [`fase6.md`](fase6.md).

---

## 1. Verificación previa

| Comprobación | Resultado |
|---|---|
| Suite completa antes de tocar código | ✅ 464 pasan |
| Contrato `P5Input / P5Output / GenerationContext / ContextUnit / P5Config` (Fase 3) | ✅ existía; no se modificó |
| Factories de P5 en `tests/contract_factories.py` | ✅ existían; no se modificaron |
| Env vars `P5_*` | ❌ no existían → creadas en T-F6-01 |

---

## 2. Qué se implementó

| Tarea | Archivos | Resumen |
|---|---|---|
| T-F6-01 config | `config.py`, `.env.example` | `P5_MAX_TOKENS_PER_UNIT` (8000, `gt=0`), `P5_INSTRUCTIONS_VERSION` (`v1`, no vacía), `P5_INCLUDE_PREREQUISITES` (false). Sin variable de estrategia (D-F6-2). |
| T-F6-02 DI | `pipeline/stages/__init__.py` | `build_p5_config(settings)`; `build_real_stages` devuelve P1–P5 reales + P6–P7 stubs. `PENDING_STUB_STAGE_CLASSES = (GenerationStage, EvaluationStage)`; `ContextStubStage` entra en `STUB_STAGE_CLASSES`. `ContextStage` se exporta. |
| T-F6-03 P5 | `pipeline/stages/p5_context.py` | `ContextStage(config=P5Config)` real + `ContextStubStage` al final del módulo (patrón de P1–P4). Ver §3. |
| T-F6-04 pruebas | `tests/test_p5_context.py` (20), `tests/test_stages_wiring.py` (+2, 3 extendidos) | Ver §5. |
| T-F6-05 docs | `docs/pipeline_roadmap.md`, `fase6.md`, este archivo | Fase 6 marcada ✅; P5 real en la tabla de etapas; advertencias 8 y 9 añadidas. |

---

## 3. Decisiones y supuestos tomados en la implementación

1. **`strategy` en `P5Config` (T-F6-02).** El plan sugería la opción (b): `P5Config` sin
   `strategy` completado en runtime. El contrato exige `strategy` (no se toca), así que
   `build_p5_config` construye el objeto con un valor **provisional** (`by_user_story`) y la etapa
   lo sustituye en cada ejecución con `config.model_copy(update={"strategy": strategy})`. Es la
   opción (b) adaptada al contrato: un único objeto inmutable, completado en runtime. El objeto
   inyectado no se muta entre ejecuciones (hay prueba).
2. **Filtro de HU más estricto que el plan (paso 3).** El plan decía "solo HU no `INVALID`". El
   validador de `P5Input` además exige que **solo** entren las HU que originaron algún RF
   (`"solo entran las HU que originaron RF"`). P5 filtra por ambas condiciones. Si un RF referencia
   una HU `INVALID`, `P5Input` lo rechaza → `CONTEXT_BUILD_FAILED` (advertencia heredada 5).
3. **`P5Input` se valida antes de agrupar** (no en el paso 6 del plan). Así las unidades se
   construyen sobre una entrada ya validada (R-CP-2/R-CP-3, tabla de patrones del plan). Errores
   de `P5Input` o de `GenerationContext` → `StageError("CONTEXT_BUILD_FAILED")`, no reintentable.
4. **Guardias.** `p1_output` o `p2_output` `None` → `RuntimeError` (invariante del orquestador,
   igual que P2–P4).
5. **Orden dentro de la unidad.** RF objetivo y de contexto ordenados por número de código
   (`RF-001`, `RF-002`, …) en ambas estrategias; HU por `position`. Unidades `by_cluster` en orden
   de `cluster.label` (se reordena por seguridad aunque P4 ya las emite ordenadas).
6. **`context_requirements` (`by_cluster`).** RF asignados a **otros clusters** que comparten al
   menos una HU de origen con algún RF objetivo de la unidad. Los RF sin cluster **no** se usan
   como contexto aunque compartan HU (D-36: P6 no los verá). Se asume membresía única (R6): si un
   RF estuviera en dos clusters sería objetivo en dos unidades y `GenerationContext` lo rechazaría.
7. **`by_user_story`.** Cada RF va a la HU de **menor `position`** entre sus `user_story_codes`,
   independientemente del orden en la tupla (D-F6-9). La otra HU aparece en `user_stories` de la
   unidad y en `requirement_to_stories` (el mapa conserva el orden original de `user_story_codes`).
8. **`token_estimate`.** `(Σ len(description) de RF objetivo + contexto + Σ len(original_text) de
   las HU de la unidad) // 4`. Se usó la fórmula detallada de T-F6-03 (suma de caracteres), no la
   mención a "JSON serializado" de D-F6-6. `exceeds_limit = token_estimate > max_tokens_per_unit`
   (igual al límite no marca).
9. **Avisos.** `UNASSIGNED_REQUIREMENTS` (uno, con `requirement_codes`) si P4 dejó RF sin cluster,
   incluido el caso con 0 unidades. `UNIT_EXCEEDS_TOKEN_LIMIT` **uno por unidad** marcada, con
   `unit_id`, `token_estimate` y `max_tokens_per_unit`.
10. **`runtime_info`.** `strategy`, `instructions_version`, `units`, `requirements_covered`,
    `max_tokens_per_unit`, `units_exceeding_limit` (lista de `unit_id`) y, solo con `by_cluster`,
    `unassigned_requirements`.
11. **`requirement_to_stories`** se construye como dict nuevo por unidad (advertencia heredada 4).
12. **`output_spec`** = `default_output_spec(P5_INSTRUCTIONS_VERSION)` (PA-3: una sola versión).
13. **`include_prerequisites`** se lee de la config pero no cambia nada: `prerequisites=()` siempre (D-F6-5).

**Patrones:** no se introdujo ningún patrón nuevo. P5 aplica Pipeline (R-PP-1/3/4), Strategy
(R-ST-4: la bifurcación se decide con `p4_output is None`), Dependency Injection (R-DI-2: solo
`P5Config` por constructor) y Contract (R-CP-2/R-CP-3). SRP a nivel de método: `run()` coordina y
delega en `_build_by_cluster()` / `_build_by_user_story()`; la construcción común de la unidad vive
en `_unit()`.

---

## 4. Decisiones del plan aplicadas

| Decisión | Dónde |
|---|---|
| D-F6-1 / D-12 — P5 no persiste | `ContextStage` no recibe repositorio; solo escribe `context.p5_output` |
| D-F6-2 / R-ST-4 — estrategia desde `p4_output` | `ContextStage.run()` |
| D-F6-3 / D-32 / D-36 — RF sin cluster sin unidad + aviso | `_build_by_cluster`, `_warnings` |
| D-F6-4 / D-31 — `context_requirements` en `by_cluster`; vacíos en `by_user_story` | `_build_by_cluster`, `_build_by_user_story` |
| D-F6-5 / D-17 — `prerequisites=()` | `_unit` |
| D-F6-6 — marcar + avisar, no partir | `_unit`, `_token_estimate`, `_warnings` |
| D-F6-7 — `U-001…` consecutivos | `_unit` |
| D-F6-8 — `label` = nombre del cluster / código de HU | `_build_by_cluster`, `_build_by_user_story` |
| D-F6-9 — RF a la HU de menor posición | `_build_by_user_story` |
| D-F6-10 — `user_stories` y `requirement_to_stories` | `_unit` |
| PA-1 / PA-2 / PA-3 — `v1`, 8000, una sola versión | `config.py`, `build_p5_config` |

---

## 5. Pruebas

- **P5** (`test_p5_context.py`, 20):
  - `by_cluster`: happy path con 2 clusters y HU compartida (labels, `cluster_label`, objetivo,
    contexto, HU, `requirement_to_stories`, `runtime_info`); sin HU compartidas → sin contexto;
    copia de campos de `UserStory`; RF sin cluster excluidos con aviso; RF sin cluster no es
    contexto aunque comparta HU; todos sin asignar → `units=()`, aviso y sin `skip_remaining`;
    límite superado / no superado (borde exacto); el estimado cuenta los RF de contexto.
  - `by_user_story`: happy path con 3 HU; RF con varias HU → menor posición; HU sin RF no genera
    unidad; HU `invalid` sin RF ignorada; RF de HU `invalid` → `CONTEXT_BUILD_FAILED`.
  - Guardias: `p1_output`/`p2_output` `None` → `RuntimeError`; `p4_output` manda sobre la config y
    sobre `clustering_enabled` en ambos sentidos; clustering incoherente con los RF →
    `CONTEXT_BUILD_FAILED`; la config inyectada no se muta entre ejecuciones.
- **Wiring** (`test_stages_wiring.py`): `build_p5_config` (defaults y overrides); validación de
  las env vars; `build_real_stages` con P1–P5 reales. Extremo a extremo HTTP: con clustering →
  P5 `by_cluster` con 1 unidad y 2 RF cubiertos; `semantic_clustering_enabled=false` → P5
  `by_user_story`; 1 RF sin cluster → P5 `completed` con `UNASSIGNED_REQUIREMENTS` y 0 unidades.
  En todos, la generación termina `completed` (P6–P7 stubs).
- **Regresión:** suite completa 493 ✅.

---

## 6. Advertencias y pendientes

1. **Calibración de `P5_MAX_TOKENS_PER_UNIT`.** El estimado (caracteres / 4) es heurístico y no
   incluye el prompt de P6 ni el `output_spec`. Validar cuando P6 sea real: si unidades marcadas
   funcionan bien, subir el umbral; si unidades sin marcar producen casos pobres, bajarlo (PA-2).
2. **Nombres de cluster placeholder.** Con `by_cluster` el `label` de la unidad es
   `"Cluster {label}"` (D-A de Fase 5).
3. **R6 / D-31 diferido.** P5 asume membresía única. Con un algoritmo de clusters superpuestos
   habría que elegir en qué cluster es objetivo cada RF.
4. **Generación con 0 unidades.** Si P4 deja todos los RF sin cluster, P5 produce
   `GenerationContext(units=())` y la generación sigue `completed`. P6 (Fase 7) debe tratar ese
   caso sin fallar.
5. **Docstring de `P5Config`** dice que `strategy` "se deriva de `semantic_clustering_enabled`".
   En la práctica se deriva de `p4_output` (equivalente salvo que P3/P4 se omitan por otra causa).
   No se corrigió porque el contrato estaba fuera de alcance; conviene ajustarlo en una fase que
   toque contratos.
6. **`dict` en modelos frozen** (heredada): `ContextUnit.requirement_to_stories` y
   `TestCaseOutputSpec.json_schema`.

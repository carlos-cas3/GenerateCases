# Handoff para el agente implementador

  
**Objetivo:** aplicar D-38, D-39 y corregir la inconsistencia de D-36 sin implementar todavía las etapas P5/P6 (siguen siendo stubs y dependen de T-05).

> **Regla de alcance:** este handoff modifica documentación, contratos y añade el resolvedor de prompts. **No** implementa la lógica completa de P5/P6 ni toca `schema.sql`, `TestData`, `link_support_threshold` ni P7; eso queda en la fase posterior.

---

## 0. Decisiones que debe reflejar

### D-38 — Variante de prompt de P6 según clustering
- `P6Config.prompt_version` identifica la familia/versión.
- P6 resuelve la variante con `GenerationContext.strategy`:
  - `by_cluster` → `contexto@<version>`
  - `by_user_story` → `contexto_sin_clustering@<version>`
- Ambas variantes comparten `TestCaseOutputSpec` y el mismo JSON Schema.
- La variante ejecutada se registra en `LlmRunInfo.prompt_version` y en `runtime_info`.
- `config_snapshot` guarda la familia configurada; `runtime_info` guarda lo ejecutado (D-34).

### D-39 — Unidades sin clustering
- Sin clustering, P5 agrupa **RF en lotes** según `max_tokens_per_unit`; no crea una unidad por HU.
- Cada unidad lleva:
  - `requirements`: RF objetivo del lote.
  - `user_stories`: HU de origen de esos RF, como contexto.
  - `requirement_to_stories`: RF→HU.
  - `cluster_label = None`, `context_requirements = ()`.
- Una HU puede repetirse como contexto si sus RF caen en lotes distintos; cada RF es objetivo en exactamente una unidad.
- **Modifica D-12** (que hoy dice “sin clustering: unidades por HU”).
- Se mantiene el valor `by_user_story`; se documenta como “sin clustering: lotes de RF con HU de origen”.

### Corrección de D-36
- `INSUFFICIENT_CONTEXT`, 0 unidades y `skip_remaining` **solo** con clustering activo y **ningún** RF asignado.
- Sin clustering, P5 siempre produce ≥1 unidad o falla con `EMPTY_CONTEXT`.
- `units` vacía solo con `by_cluster`; con `by_user_story` mínimo 1.

### Matriz de comportamiento

| `semantic_clustering_enabled` | `strategy` | Unidad de P5 | Prompt de P6 |
|---|---|---|---|
| `true` con RF asignados | `by_cluster` | clúster / subunidad por tokens | `contexto` |
| `false` | `by_user_story` | lote de RF + HU de origen | `contexto_sin_clustering` |
| `true` sin ningún RF asignado | `by_cluster` | 0 unidades + `INSUFFICIENT_CONTEXT` (D-36) | `skipped` |
| `false` y no se puede construir ninguna unidad | `by_user_story` | `EMPTY_CONTEXT` (fallo) | `pending` |

---

## 1. Documentación

### 1.1 `docs/prompts_fases/Fase 3/pipeline_design.md`

1. **Cabecera (líneas 3–5)**
   - No marcar “cerrado” todavía; usar “revisión documental”.
   - Añadir D-38, D-39 y T-05 a la lista de decisiones incorporadas.

2. **Línea 277** — reemplazar “sin clustering, las unidades se construyen por HU” por:
   > “sin clustering, las unidades se construyen agrupando RF en lotes que respetan el límite de tokens; las HU de origen acompañan como contexto (D-39)”.

3. **Línea 285** — `instructions_version`:
   > “Versión de las instrucciones de P5 (construcción de contexto). No es la variante de prompt de P6 (D-38).”

4. **Línea 286** — `strategy`:
   > “`by_cluster` o `by_user_story`. `by_user_story` significa «sin clustering: lotes de RF con HU de origen» (D-39).”

5. **Línea 287** — `units`:
   > “Puede ser vacía solo con `by_cluster` y D-36. Con `by_user_story`, mínimo 1.”

6. **Línea 294** — `label`:
   > “Nombre del clúster, lote de RF o subunidad.”

7. **Línea 297** — `context_requirements`:
   > Añadir: “En `by_user_story` siempre es vacía (D-39).”

8. **Línea 308** — invariante:
   > “Sin clustering, todos los RF son objetivo y se reparten en lotes; cada RF aparece como objetivo en una sola unidad (D-39).”

9. **P5 (líneas 608–654)**
   - Reemplazar la viñeta de línea 638 por:
     > “Sin `clustering` (D-39): P5 agrupa los RF en lotes que respetan `max_tokens_per_unit`; cada unidad incluye los RF objetivo del lote y las HU de origen como contexto. No hay `cluster_label` ni `context_requirements` de clúster. Las HU pueden repetirse como contexto si sus RF caen en lotes distintos.”
   - En “Errores” (línea 643), aclarar que `EMPTY_CONTEXT` aplica cuando no hay clustering o cuando hay RF asignados y aun así no se puede construir ninguna unidad.
   - En el bloque D-36 (líneas 645–654), añadir: “Aplica **solo con clustering**. Sin clustering no se emite `INSUFFICIENT_CONTEXT`.”

10. **P6 (líneas 656–694)**
    - Línea 660: “`skipped` con cero RF (D-29) o cero unidades **solo por D-36**”.
    - Añadir un apartado **“Selección de prompt (D-38)”**:
      > “`P6Config.prompt_version` identifica la familia/versión. P6 resuelve la variante con `context.strategy`:
      > - `by_cluster` → `contexto`
      > - `by_user_story` → `contexto_sin_clustering`
      > Ambas comparten `TestCaseOutputSpec`. La variante ejecutada se registra en `LlmRunInfo.prompt_version` (p. ej. `contexto@p6-v1`) y en `runtime_info`.”
    - Línea 669: `P6Config` → “`prompt_version` (familia; la variante se resuelve por `context.strategy`)”.
    - Línea 692: “cero unidades **solo por D-36**”.
    - Línea 358 (`LlmRunInfo`): “`prompt_version` es la variante concreta ejecutada”.
    - Línea 700 (P7): “cero unidades **solo por D-36**”.

11. **D-12 (línea 843)**
    > “**Resuelta, modificada por D-39.** Con clustering: unidad por clúster… Sin clustering: unidades por lotes de RF con HU de origen…”

12. **D-36 (línea 867)**
    > Añadir “solo con clustering” al inicio de la resolución.

13. **Añadir después de D-37 (línea 868)**

```markdown
| **D-38** | Variante de prompt de P6 según clustering | Una sola instrucción; dos variantes | **Resuelta.** `contexto` con clustering; `contexto_sin_clustering` sin clustering. Se resuelve por `context.strategy`; mismo `TestCaseOutputSpec`; se registra en `LlmRunInfo`/`runtime_info`. |
| **D-39** | Unidades sin clustering | Por HU; lotes de RF; una por RF | **Resuelta.** Sin clustering, P5 agrupa RF en lotes por tokens; cada unidad lleva RF objetivo + HU de origen; `cluster_label=None`, `context_requirements=()`. Modifica D-12. |
```

---

### 1.2 `docs/prompts_fases/Fase 3/cierre_documental.md`

1. Añadir **D-38** y **D-39** a la tabla de la sección 1.
2. Añadir una sección corta **1.2 Variantes de prompt de P6 (D-38)** con la matriz de comportamiento.
3. En la sección 4, añadir que D-38/D-39 quedan cerradas y que T-05 sigue abierta.
4. Actualizar la sección 5:

| Archivo | Cambio |
|---|---|
| `ai_service/pipeline/contracts/p5.py` | `units` vacía solo con `by_cluster`; `by_user_story` exige ≥1 y sin `context_requirements`. |
| `ai_service/pipeline/contracts/p6.py` | Documentar `prompt_version` como familia; la variante se resuelve por `strategy`. |
| `ai_service/pipeline/prompts/` (nuevo) | Resolvedor `contexto` / `contexto_sin_clustering`. |
| Orquestador / P5 | `INSUFFICIENT_CONTEXT` y `skip_remaining` solo en D-36; sin clustering con 0 unidades → `EMPTY_CONTEXT`. |
| `docs/openapi.yaml` | Documentar D-36, la variante de prompt y el `skipped` sin clustering. |
| `tests/` | Pruebas de `units` por estrategia y del resolvedor de prompts. |

---

### 1.3 `docs/prompts_fases/Fase 3/decisiones_pipeline.md`

1. En la tabla resumen (líneas 16–27), añadir:
   - D-38: “Variante de prompt de P6” / “Decidido” / “`contexto` con clustering; `contexto_sin_clustering` sin clustering”.
   - D-39: “Unidades sin clustering” / “Decidido” / “Lotes de RF con HU de origen”.
2. Añadir una sección corta después de D-37 o al final de la sección 2 explicando ambas.
3. Actualizar la nota de la línea 5 para incluir D-38/D-39.

---

### 1.4 `docs/openapi.yaml`

1. **Línea 45** — aclarar que lo que puede venir vacío es la lista de clusters, no el contexto:
   > “las listas de clusters pueden venir vacías (no es un error)”.

2. **Líneas 57–59 (`StageStatus`)** — añadir:
   > “P6 y P7 también quedan `skipped` cuando, con clustering activo, ningún RF queda asignado a un cluster (D-36). Sin clustering, P5 y P6 se ejecutan: P5 forma lotes de RF.”

3. **Líneas 963–971 (`GenerationConfiguration`)** — añadir:
   > “`semantic_clustering_enabled` determina `strategy` en P5 (`by_cluster`/`by_user_story`) y la variante de prompt de P6 (`contexto`/`contexto_sin_clustering`, D-38).”

4. **Líneas 1006–1011 (`runtime_info`)** — añadir:
   > “En P6 incluye `prompt_variant` y `prompt_version`.”

5. **Líneas 1024–1035 (`LlmRun.prompt_version`)** — añadir descripción:
   > “Variante concreta del prompt ejecutado (p. ej. `contexto@p6-v1` o `contexto_sin_clustering@p6-v1`).”

6. **No tocar** el esquema `TestData` en este handoff (D-26 queda para la fase posterior).

---

## 2. Contratos

### 2.1 `ai_service/pipeline/contracts/p5.py`

**Cambio en `GenerationContext`:** quitar `min_length=1` y validar por estrategia.

```python
class GenerationContext(ContractModel):
    """Contexto de generación. Lo produce P5; lo consume P6. No se persiste (D-12)."""

    generation_id: UUID
    output_spec: TestCaseOutputSpec
    instructions_version: NonEmptyStr
    strategy: UnitStrategy
    units: tuple[ContextUnit, ...]

    @model_validator(mode="after")
    def _single_target(self) -> "GenerationContext":
        ensure_unique((unit.unit_id for unit in self.units), "unit_id")
        ensure_unique((code for unit in self.units for code in unit.target_codes()), "RF objetivo entre unidades")

        if self.strategy == UnitStrategy.BY_CLUSTER:
            if any(unit.cluster_label is None for unit in self.units):
                raise ValueError("con by_cluster toda unidad debe tener cluster_label")
        else:
            if not self.units:
                raise ValueError("con by_user_story debe haber al menos una unidad")
            if any(unit.cluster_label is not None for unit in self.units):
                raise ValueError("con by_user_story ninguna unidad tiene cluster_label")
            if any(unit.context_requirements for unit in self.units):
                raise ValueError("con by_user_story ninguna unidad tiene context_requirements")

        return self
```

Ajustes de documentación:
- `GenerationContext.instructions_version`: “Versión de las instrucciones de P5; no es el prompt de P6”.
- `P5Config.strategy`: “Se deriva de `semantic_clustering_enabled`: `by_cluster` si `true`, `by_user_story` si `false`”.

### 2.2 `ai_service/pipeline/contracts/p6.py`

- **No cambiar la forma de `P6Config`** en este handoff.
- Actualizar el docstring de `P6Config`:
  > “`prompt_version` identifica la familia/versión. P6 resuelve la variante (`contexto`/`contexto_sin_clustering`) con `context.strategy` (D-38).”
- **No eliminar** `link_support_threshold` (D-18 queda para la fase posterior).

---

## 3. Nuevo módulo de prompts

Crear:

```text
ai_service/pipeline/prompts/
├── __init__.py
├── p6.py
└── texts/
    ├── contexto.md
    └── contexto_sin_clustering.md
```

### 3.1 `ai_service/pipeline/prompts/p6.py`

```python
"""Resolución de la variante de prompt de P6 (D-38).

`prompt_version` identifica la familia/versión; la variante se elige por
`GenerationContext.strategy`:
- `by_cluster` -> `contexto`
- `by_user_story` -> `contexto_sin_clustering`
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ai_service.pipeline.contracts.common import UnitStrategy

_PROMPTS_DIR = Path(__file__).with_name("texts")


class P6PromptVariant(StrEnum):
    CONTEXT = "contexto"
    CONTEXT_WITHOUT_CLUSTERING = "contexto_sin_clustering"


@dataclass(frozen=True, slots=True)
class ResolvedP6Prompt:
    variant: P6PromptVariant
    prompt_version: str
    text: str


_VARIANT_BY_STRATEGY = {
    UnitStrategy.BY_CLUSTER: P6PromptVariant.CONTEXT,
    UnitStrategy.BY_USER_STORY: P6PromptVariant.CONTEXT_WITHOUT_CLUSTERING,
}


def _load(variant: P6PromptVariant) -> str:
    return (_PROMPTS_DIR / f"{variant.value}.md").read_text(encoding="utf-8")


def resolve_p6_prompt(prompt_version: str, strategy: UnitStrategy) -> ResolvedP6Prompt:
    try:
        variant = _VARIANT_BY_STRATEGY[strategy]
    except KeyError as exc:
        raise ValueError(f"estrategia de contexto no soportada: {strategy}") from exc
    return ResolvedP6Prompt(
        variant=variant,
        prompt_version=f"{variant.value}@{prompt_version}",
        text=_load(variant),
    )
```

### 3.2 `ai_service/pipeline/prompts/__init__.py`

Exportar `P6PromptVariant`, `ResolvedP6Prompt`, `resolve_p6_prompt`.

### 3.3 Textos de prompts

Contenido mínimo recomendado:

- **`texts/contexto.md`**: instrucciones para generar casos desde una unidad de contexto basada en clúster; recibe RF objetivo, RF de contexto (no enlazables) y HU de origen; debe devolver JSON conforme a `TestCaseOutputSpec`; no inventar RF; enlazar solo RF objetivo; vínculos `pending`.
- **`texts/contexto_sin_clustering.md`**: instrucciones para generar casos desde un lote de RF y sus HU de origen; no hay clusters; mismo JSON Schema; enlazar solo los RF del lote.

Ambos prompts deben declarar que la salida se valida contra el esquema entregado por separado; no incrustar el esquema en el texto.

---

## 4. Etapas y orquestador (fase posterior)

Estos cambios **no se pueden completar** hasta resolver T-05 (paso de datos entre etapas). Dejarlos documentados y, si se implementan, respetar:

1. **P5 sin clustering**
   - Agrupar RF en lotes por `max_tokens_per_unit`.
   - Incluir HU de origen como contexto.
   - `cluster_label=None`, `context_requirements=()`.
   - Si no se puede construir ninguna unidad → `StageError("EMPTY_CONTEXT")`.

2. **P5 D-36**
   - Solo si `clustering is not None` y `clustering.assigned_requirement_codes()` está vacío.
   - Devolver `P5Output` con 0 unidades y `StageResult(warnings=(INSUFFICIENT_CONTEXT,), skip_remaining=True)`.

3. **P6**
   - Resolver el prompt con `resolve_p6_prompt(config.prompt_version, context.strategy)`.
   - Pasarlo al puerto `TestCaseGenerator`.
   - Registrar `prompt_version` en cada `LlmRunInfo` y `prompt_variant` en `runtime_info`.

4. **Orquestador**
   - No marcar `completed` una generación sin contexto cuando no hay clustering; propagar `EMPTY_CONTEXT` como fallo bloqueante.

---

## 5. Pruebas

### 5.1 `tests/contract_factories.py`

Añadir:

```python
def context_unit_without_clustering(**overrides: Any) -> p5.ContextUnit:
    values: dict[str, Any] = {
        "unit_id": "U-001",
        "label": "Lote RF-001",
        "cluster_label": None,
        "requirements": (p5.ContextRequirement(code="RF-001", description="Iniciar sesión."),),
        "context_requirements": (),
        "user_stories": (p5.ContextUserStory(code="HU-001", original_text=HU1_TEXT, objective="iniciar sesión"),),
        "requirement_to_stories": {"RF-001": ("HU-001",)},
        "token_estimate": 350,
    }
    return p5.ContextUnit(**{**values, **overrides})


def generation_context_without_clustering(**overrides: Any) -> p5.GenerationContext:
    values: dict[str, Any] = {
        "generation_id": GENERATION_ID,
        "output_spec": output_spec(),
        "instructions_version": "i-v1",
        "strategy": "by_user_story",
        "units": (context_unit_without_clustering(),),
    }
    return p5.GenerationContext(**{**values, **overrides})
```

Añadir `"GenerationContextWithoutClustering": generation_context_without_clustering()` a `all_contracts()`.

### 5.2 `tests/test_contracts_invariants.py`

Reemplazar `test_generation_context_requires_a_unit` por:

```python
def test_generation_context_allows_empty_units_only_with_clustering() -> None:
    assert f.generation_context(units=()).units == ()
    with pytest.raises(ValidationError, match="al menos una unidad"):
        f.generation_context_without_clustering(units=())


def test_by_user_story_rejects_context_requirements() -> None:
    unit = f.context_unit_without_clustering(
        context_requirements=(p5.ContextRequirement(code="RF-002", description="Bloqueo."),),
        requirement_to_stories={"RF-001": ("HU-001",), "RF-002": ("HU-001",)},
    )
    with pytest.raises(ValidationError, match="context_requirements"):
        f.generation_context_without_clustering(units=(unit,))
```

Mantener `test_by_user_story_units_have_no_cluster` y `test_p5_input_strategy_must_match_clustering`.

### 5.3 Nuevo `tests/test_prompts.py`

```python
from ai_service.pipeline.contracts.common import UnitStrategy
from ai_service.pipeline.prompts.p6 import P6PromptVariant, resolve_p6_prompt


def test_by_cluster_uses_context_prompt() -> None:
    prompt = resolve_p6_prompt("p6-v1", UnitStrategy.BY_CLUSTER)
    assert prompt.variant is P6PromptVariant.CONTEXT
    assert prompt.prompt_version == "contexto@p6-v1"
    assert prompt.text.strip()


def test_by_user_story_uses_context_without_clustering_prompt() -> None:
    prompt = resolve_p6_prompt("p6-v1", UnitStrategy.BY_USER_STORY)
    assert prompt.variant is P6PromptVariant.CONTEXT_WITHOUT_CLUSTERING
    assert prompt.prompt_version == "contexto_sin_clustering@p6-v1"
    assert prompt.text.strip()


def test_prompt_variants_are_distinct() -> None:
    a = resolve_p6_prompt("p6-v1", UnitStrategy.BY_CLUSTER)
    b = resolve_p6_prompt("p6-v1", UnitStrategy.BY_USER_STORY)
    assert a.text != b.text
```

### 5.4 Pruebas que **no** deben tocarse en este handoff

- `tests/test_contracts.py:112-116` sigue probando el `TestData` antiguo; se actualizará cuando se implemente D-26.
- `tests/test_generations_api.py` y `tests/test_pipeline.py` siguen pasando con los stubs; no requieren cambios.

### 5.5 Comandos de verificación

```bash
pytest -q
pytest tests/test_contracts.py tests/test_contracts_invariants.py tests/test_prompts.py -q
git diff --check
```

---

## 6. Criterios de aceptación

- [ ] La documentación ya no dice que sin clustering las unidades son “por HU”; dice “lotes de RF con HU de origen”.
- [ ] `GenerationContext(strategy="by_cluster", units=())` es válido.
- [ ] `GenerationContext(strategy="by_user_story", units=())` lanza `ValidationError`.
- [ ] `GenerationContext(strategy="by_user_story")` con `context_requirements` no vacío lanza `ValidationError`.
- [ ] `resolve_p6_prompt` devuelve `contexto@p6-v1` o `contexto_sin_clustering@p6-v1` según la estrategia.
- [ ] `pytest` pasa completo.
- [ ] No se modificaron `schema.sql`, `TestData`, `link_support_threshold` ni P7 en este handoff.

---

## 7. Pendiente para una fase posterior (no hacer ahora)

- Implementación real de P5 (loteo de RF) y P6 (resolución/wiring del prompt): bloqueada por **T-05** (paso de datos entre etapas).
- D-26: `TestData` solo con `inputs`/`notes`; actualizar `common.py`, `openapi.yaml` y tests.
- D-18: retirar `link_support_threshold` de `P6Config`.
- D-37: crear `contracts/p7.py` y documentar métricas.
- T-01, T-02, T-04, T-05 y revisión de los 11 supuestos.
- No cambiar el estado de `pipeline_design.md` a “cerrado” hasta resolver lo anterior.

---


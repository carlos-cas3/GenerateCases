# Decisiones y recomendaciones sobre el diseño del pipeline

Documento de respuesta a las secciones 2, 3 y 4 de la revisión del diseño (`pipeline_design.md`). Recoge las decisiones tomadas, las recomendaciones propuestas y los cambios que implican en `schema.sql`, `openapi.yaml` y el código.

> **Actualización (cierre documental, 2026-11-04):** las claves de `test_data` (D-26), la lista de métricas de P7 (D-37), D-18 y D-36 quedaron cerradas. Ver `cierre_documental.md`. Donde este documento diga otra cosa, prevalece el cierre.

**Convenciones**
- **Decidido**: confirmado por el responsable del proyecto.
- **Recomendado**: propuesta pendiente de confirmación.
- Todos los cambios de base de datos propuestos son **aditivos** (columnas nullable o con valor por defecto, tablas y funciones nuevas), por lo que no rompen datos ni clientes existentes.

---

## 1. Resumen de decisiones

| ID propuesto | Tema | Estado | Decisión |
|---|---|---|---|
| D-26 | Estructura de `test_data` | Decidido (JSON) / claves recomendadas | JSON con claves fijas |
| D-27 | Clasificación de P2 (G1) | Recomendado | Persistir en `user_stories` |
| D-28 | Código de error por etapa (G2) | Recomendado | `error_code` en `generation_stages` |
| D-29 | Cero RF extraídos (G3) | Decidido | P2 `completed` con aviso; P3–P7 `skipped` |
| D-30 | Persistencia por etapa (G4) | Recomendado | Guardado al terminar cada etapa vía RPC |
| D-31 | RF en varios clusters (G5) | Decidido | Gana mayor similitud; el resto es contexto |
| D-32 | RF sin cluster (G6) | Decidido | Se guardan y se muestran; no generan CP por ahora |
| D-33 | P7 siempre se ejecuta | Decidido | Calcula y persiste métricas; cambia R1 |
| D-34 | `config_snapshot` | Recomendado | Fijo al inicio; lo ocurrido en ejecución va por etapa |
| D-35 | Metadatos de etapa (2.4) | Recomendado | Columnas `warnings`, `llm_runs`, `runtime_info` |

---

## 2. Incoherencias a corregir

### 2.1 Nombres de P1 y P2 — Decidido

Los nombres del diseño son más completos y pasan a ser los oficiales:

- P1: **Procesamiento, segmentación y estructuración de HU**
- P2: **Clasificación de HU y extracción de RF**

**Acciones**
- Actualizar `openapi.yaml` (líneas ~250-251), incluidos los ejemplos.
- Actualizar `pipeline/catalog.py` (líneas ~16-17).
- No hay impacto en el contrato: el nombre no se guarda en BD.

### 2.2 Etapa P7 (evaluación) — Decidido

P7 **siempre se ejecuta**: calcula las métricas, las guarda en `generation_metrics` y otro endpoint las consume. No es opcional ni bloquea otras etapas. La versión "evolucionada" (con contención, reglas de rechazo, etc.) queda fuera del alcance actual.

**Consecuencias**
- Se **modifica la regla R1** del diseño (hoy dice que P7 siempre es `skipped`).
- El ejemplo del openapi (P7 `completed` con `requirement_coverage`) pasa a ser el correcto y se mantiene.
- Cada etapa P1–P6 sigue sin escribir en `generation_metrics`; solo lo hace P7.

**Recomendaciones**
- Un fallo de P7 **no invalida** la generación: queda `completed` con un aviso, porque los casos de prueba ya existen y las métricas son informativas.
- Si no hay RF (ver D-29), P7 queda `skipped`, porque no hay nada que medir.

**Resuelto en D-37** (ver `cierre_documental.md`): `requirement_coverage` cuenta solo vínculos `validated`, se añade `proposed_requirement_coverage` y `unassigned_ratio` solo aplica con clustering. Sugerencia inicial original:
- `requirement_coverage`: proporción de RF con al menos un CP.
- `story_coverage`: proporción de HU con al menos un RF.
- `cases_per_requirement`: promedio de CP por RF.
- `unassigned_ratio`: proporción de RF sin cluster.

### 2.3 Referencia a D-14 — Decidido (corregir) / Recomendado (redacción)

**Problema.** La misma etiqueta señala dos cosas distintas:
1. En 1.3.8, `test_data` dice "[Pendiente D-14]", y el openapi habla de la "decisión pendiente 7": ambos indican que la estructura de `test_data` no está decidida.
2. En 1.9, D-14 figura como **Resuelta**, pero su resolución trata de los vínculos entre entidades, no de `test_data`.

Un lector vería una decisión pendiente que apunta a una decisión cerrada de otro tema.

**Solución.** Crear **D-26** exclusivamente para la estructura de `test_data` y corregir las dos referencias (diseño y openapi).

**D-26 — Estructura de `test_data` (decidido: JSON)**

> **Cerrado:** `test_data` lleva solo `inputs` y `notes`. `preconditions` y `expected_result` quedan como campos de primer nivel del caso. La propuesta original de 4 claves queda abajo como referencia histórica.

Propuesta original de claves fijas (reemplazada):

```json
{
  "preconditions": ["Usuario registrado", "Sesión iniciada"],
  "inputs": { "campo_1": "valor", "campo_2": "valor" },
  "expected_results": ["El sistema muestra confirmación"],
  "notes": "Opcional"
}
```

- `preconditions`: arreglo de textos (puede ser vacío).
- `inputs`: objeto libre clave-valor con los datos de entrada.
- `expected_results`: arreglo de textos.
- `notes`: texto opcional.
- En BD, columna `jsonb`; en el openapi, un esquema `TestData` con estas propiedades.
- Validar la estructura en la salida de P6 (si el LLM devuelve otra forma, se trata como `LLM_INVALID_OUTPUT` y se reintenta).

### 2.4 La tabla 1.7 no recoge todo lo que produce `StageMetadata` — Recomendado

**Problema.** Cada etapa produce un `StageMetadata` con estado, tiempos, error, `warnings` y `llm_runs` (tokens, latencia, intentos). Pero `generation_stages` solo tiene estado, tiempos y `error_message`. Los avisos y el consumo del LLM se calculan y se pierden al terminar la ejecución, lo que impide auditar costos, depurar reintentos o mostrar avisos en el frontend.

**Solución (aditiva).**

```sql
ALTER TABLE generation_stages
  ADD COLUMN IF NOT EXISTS warnings     jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS llm_runs     jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS runtime_info jsonb;
```

Se expone en `GenerationStage` del openapi como campos opcionales.

### 2.5 `config_snapshot` — Recomendado (opción A)

**Contexto.** Hoy `config_snapshot` se escribe una sola vez, en `create_generation`. El diseño pide guardar datos que solo se conocen durante la ejecución (`config_used`, dimensión real del modelo de embeddings, `algorithm_info`).

**Opciones**
- **A (recomendada).** El snapshot queda **fijo desde el inicio** y representa lo que se pidió. Lo que ocurrió realmente se guarda por etapa en `generation_stages.runtime_info`.
- **B.** Crear una operación del repositorio que mezcle datos en el snapshot ya creado.

**Por qué A**: es más simple, no necesita una operación de fusión (con riesgo de condiciones de carrera), separa con claridad "lo solicitado" de "lo ejecutado" y reutiliza la columna del punto 2.4.

**Acción**: documentar en el diseño que el snapshot se fija solo al inicio.

---

## 3. Huecos que bloqueaban los contratos

### G1 — Clasificación de P2 sin persistencia — Recomendado

La clasificación (`candidata_funcional` / `requiere_aclaracion` / `no_aplicable`) es lo único que explica en el frontend por qué una HU no tiene RF. Sin guardarla se pierde al terminar la ejecución y se rompe la trazabilidad.

```sql
ALTER TABLE user_stories
  ADD COLUMN IF NOT EXISTS classification text
    CHECK (classification IN ('candidata_funcional','requiere_aclaracion','no_aplicable')),
  ADD COLUMN IF NOT EXISTS classification_rationale text,
  ADD COLUMN IF NOT EXISTS clarification_items jsonb NOT NULL DEFAULT '[]'::jsonb;
```

- Todas nullable o con default: las filas existentes siguen siendo válidas.
- En el openapi, `UserStory` gana `classification`, `classification_rationale` y `clarification_items` como campos **opcionales**; los clientes actuales no se ven afectados.
- Añadir R10 / D-27 documentando esta persistencia.

### G2 — Código de error de etapa perdido — Recomendado

`StageError.code` (por ejemplo `NO_STORIES_FOUND`, `LLM_INVALID_OUTPUT`) no tiene columna, y el orquestador reemplaza el mensaje por uno genérico (`orchestrator.py:57-62`).

```sql
ALTER TABLE generation_stages
  ADD COLUMN IF NOT EXISTS error_code text;
```

- `GenerationStage.error_code` opcional en el openapi.
- Cambio de código: el orquestador debe **propagar `StageError.message`** en lugar de un mensaje genérico.
- **Verificación previa**: revisar consultas con `select *` o modelos estrictos que podrían fallar ante columnas nuevas.

### G3 — Cero RF extraídos — Decidido

Que el LLM no extraiga RF no es un fallo del pipeline, sino un resultado válido (poca información en la entrada). La etapa cumplió su trabajo.

| Etapa | Estado |
|---|---|
| P1 | `completed` |
| P2 | `completed` con aviso `NO_REQUIREMENTS_EXTRACTED` |
| P3 – P6 | `skipped` |
| P7 | `skipped` (no hay nada que medir) |
| Generación | `completed` con el aviso |

- La explicación de por qué no hay RF se muestra con la clasificación de G1.
- Se eliminan las condiciones `EMPTY_CONTEXT` (P5) y `NO_TEST_CASES_GENERATED` (P6) como consecuencia de este caso; siguen aplicando solo cuando hay RF y aun así no se generan CP.
- Es un cambio de contrato: documentarlo en el diseño y en el openapi (el estado `skipped` y el aviso).

### G4 — Persistencia por etapa y atomicidad — Recomendado

**Qué se resuelve**
- *Cuándo se guarda.* Hoy solo P6 guarda de forma incremental (D-15). Si P3 falla y las demás guardan al final, el usuario no ve nada de P1 y P2, aunque la API promete "resultados parciales". Regla propuesta: **cada etapa guarda su resultado al terminar**.
- *Cómo se garantiza la consistencia.* Guardar un RF implica escribir en `requirements` y en `user_story_requirements`. `supabase-py` (PostgREST) no ofrece transacciones entre tablas: si falla la segunda escritura queda un RF huérfano.

**Solución.** Funciones de Postgres (RPC) que hagan todas las escrituras de una etapa en **una sola transacción**, siguiendo el patrón de `create_generation`:

- `persist_p2_requirements(jsonb)`: RF + `user_story_requirements` + clasificación.
- `persist_p4_clusters(jsonb)`: clusters + `cluster_requirements` + `unassigned_requirements`.
- `persist_p6_unit(jsonb)`: casos de prueba + pasos + vínculos.

**Impacto**: no cambia las tablas existentes, solo añade funciones. Se documenta en el openapi que una generación `failed` puede tener resultados parciales (incluidos CP ya guardados en P6).

### G5 — RF presente en varios clusters — Decidido

El esquema lo permite (R6), pero P5 exige una única unidad objetivo por RF. Regla:

1. El RF **pertenece** al cluster donde tenga mayor `similarity_to_centroid`.
2. En los demás clusters **no participa como objetivo**: entra solo como **contexto adicional**.
3. **Desempate** (misma similitud o sin valor): se elige el cluster con menor `label`.

Se actualiza P5 y la nota de R6.

### G6 — RF sin cluster (outliers) e insuficiencia de RF — Decidido / Recomendado

**Decidido**: los RF no agrupados **no se eliminan**; se guardan y se muestran. **Por ahora no generan casos de prueba.**

**Propuesta de implementación**

```sql
CREATE TABLE IF NOT EXISTS unassigned_requirements (
  generation_id  uuid NOT NULL REFERENCES generations(id) ON DELETE CASCADE,
  requirement_id uuid NOT NULL,
  PRIMARY KEY (generation_id, requirement_id),
  FOREIGN KEY (generation_id, requirement_id)
    REFERENCES functional_requirements (generation_id, id) ON DELETE CASCADE
);
```

> Corregido (T-03): la tabla de RF es `functional_requirements` y la FK es compuesta `(generation_id, id)`, como en `schema.sql`. No existe una tabla `requirements`.

- `ClusterList` del openapi gana `unassigned_requirement_ids`, para que el frontend no tenga que inferirlos por ausencia.
- `INSUFFICIENT_REQUIREMENTS` **deja de fallar la generación**: con pocos RF, todos quedan sin agrupar y se emite un aviso.
- Esto modifica D-11 ("los no asignados no se guardan"): documentarlo como reemplazada por D-32.
- P6 solo procesa unidades con cluster; los sin cluster no producen CP. Si más adelante se quiere lo contrario, bastará con tratarlos como una unidad aparte.

---

## 4. Puntos menores a fijar en los contratos

Son ambigüedades pequeñas que, si no se fijan por escrito, cada persona interpreta distinto al implementar y generan bugs difíciles de rastrear.

| Punto | Recomendación | Por qué importa |
|---|---|---|
| HU `invalid` | Guardarlas con `validation_status='invalid'`; no pasarlas a P2; contarlas aparte en el resumen. Para `original_text` NOT NULL, usar el texto original tal cual, nunca vacío | Trazabilidad: el usuario ve qué se descartó y por qué |
| `user_stories.code` nullable | Dejarlo así a propósito y documentarlo | Pasarlo a NOT NULL arriesga datos antiguos; el pipeline ya lo asigna siempre |
| Orden de los listados | Añadir columna `position` y ordenar por ella; documentar el orden en el openapi | Ordenar `code` como texto falla desde HU-1000 (queda antes que HU-2) |
| `validation_status` (D-04) | Añadir `CHECK` en BD y `enum` en `UserStory`, tras revisar que no existan valores antiguos fuera del conjunto | Evita estados inválidos y da un contrato claro al frontend |
| Comprobación previa (R9) | Verificar embeddings solo si `semantic_clustering_enabled=true`; si responde 503, hacerlo **antes** de crear la generación | Así no quedan etapas en estado ambiguo |
| P6: reintentos | No consumir códigos `CP-xxx` en los reintentos de una unidad | Evita saltos en la numeración |
| P6: RF duplicados | Eliminar duplicados en `requirement_codes` antes de insertar | La PK rechazaría el duplicado y fallaría la inserción |
| Openapi: P6 `failed` | Documentar que puede haber CP ya guardados (D-15) | El cliente no debe asumir que `failed` implica cero resultados |
| D-06: severidad | Añadir `info` al enum `IssueSeverity` | `metric_findings.severity` admite `info` pero el enum solo tiene `error` y `warning` |

---

## 5. Resumen de cambios por artefacto

**`schema.sql` (todo aditivo)**
- `generation_stages`: `error_code`, `warnings`, `llm_runs`, `runtime_info`.
- `user_stories`: `classification` (con check), `classification_rationale`, `clarification_items`, `position`; check en `validation_status`.
- Tabla nueva `unassigned_requirements`.
- RPC: `persist_p2_requirements`, `persist_p4_clusters`, `persist_p6_unit`.

**`openapi.yaml`**
- Nombres de P1 y P2 y sus ejemplos.
- `GenerationStage`: `error_code`, `warnings`, `llm_runs`, `runtime_info` (opcionales).
- `UserStory`: campos de clasificación, `position` y enum de `validation_status`.
- `ClusterList`: `unassigned_requirement_ids`.
- Esquema `TestData`; `IssueSeverity` con `info`.
- Notas sobre resultados parciales y orden de listados.

**Código**
- `pipeline/catalog.py`: nombres de P1 y P2.
- `orchestrator.py`: propagar `StageError.message` y `error_code`; manejar `skipped` por cero RF.
- Repositorio: persistencia por etapa mediante RPC.

**`pipeline_design.md`**
- Modificar R1 (P7) y la nota de R6.
- Añadir R10 y las decisiones D-26 a D-35; marcar D-11 como reemplazada.
- Corregir las referencias a D-14.

---

## 6. Pendientes por decidir

1. ~~Confirmar las claves de `test_data`~~ → cerrado: solo `inputs` y `notes` (D-26).
2. ~~Definir la lista final de métricas de P7~~ → cerrado en D-37.
3. Confirmar las recomendaciones marcadas como "Recomendado" (G1, G2, G4, 2.4, 2.5 y puntos menores).

## 7. Orden de implementación sugerido

1. Actualizar `pipeline_design.md` con estas decisiones.
2. Preparar la migración de `schema.sql` y los cambios del openapi.
3. Escribir los contratos en código (`ai_service/pipeline/contracts/`).

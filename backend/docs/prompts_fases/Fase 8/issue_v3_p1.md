# Issue — P1 v3: léxico de marcadores de fin, prioridad y trazabilidad

> **Estado:** propuesta / pendiente de implementar.
> **Área:** `ai_service/pipeline/stages/p1_normalize.py`,
> `ai_service/pipeline/contracts/p1.py`, `ai_service/pipeline/stages/__init__.py`.
> **Prioridad:** media-alta — afecta a la calidad de `objective`/`benefit` de todas las HU.
> **Depende de:** P1 v2 (`P1_RULES_VERSION=v2`, commit `61a4c63` + cambio en working tree).
> **Decisión de despliegue:** v3 se implementa como versión **seleccionable**; el default sigue
> siendo `v2` hasta que la evaluación anotada confirme la hipótesis.
> **Estado de la evaluación:** bloqueada hasta disponer de 50–100 HU de desarrollo y 50–100 HU
> de test anotadas a mano, de otra fuente distinta a `US24`.

---

## 1. Problema

P1 v2 solo reconoce `"para"` como introductor de beneficio cuando le sigue `"que"` o un
infinitivo. Eso corrigió los cortes de v1 (`"para pacientes"`, `"para los usuarios…"`), pero deja
como `MISSING_BENEFIT` beneficios expresados con otros marcadores:

- `"con el fin de que …"`
- `"con el objetivo de …"`
- `"con la finalidad de …"`
- `"a fin de …"`
- `"de modo que …"`
- `"de manera que …"`
- `"de forma que …"`

Además, cuando v2 sí reconoce `"para que …"`, el `goal` conserva el `"que"` inicial
(`"que los datos no se filtren"`). v3 propone consumir el marcador completo y dejar el beneficio
sin ese arrastre.

El sondeo real de v2 sobre `calibration_doc.txt` (US24, 40 HU) dio 17 HU válidas y 23
`MISSING_BENEFIT`; muchas son ausencias reales de beneficio, pero otras son marcadores que v2 no
reconoce. No se sabe cuántas sin medir con anotaciones.

También falta trazabilidad: hoy no se registra qué marcador se eligió, su fuerza ni qué
candidatos se descartaron cuando había varios.

---

## 2. Hipótesis

Ampliar el léxico con prioridad por niveles y consumir el marcador completo:

1. Reduce los falsos `MISSING_BENEFIT`.
2. No aumenta los objetivos cortados.
3. No cambia `role` y mantiene o mejora `objective`/`benefit` frente a v2.

La hipótesis debe medirse contra v2 sobre el mismo corpus anotado. No se asume cierta.

---

## 3. Alcance

### Incluido

- Léxico de marcadores de fin en cuatro niveles.
- Prioridad, desempate y descarte de solapamientos.
- `benefit_marker`, `benefit_strength` y `other_markers` en `UserStory` (solo memoria).
- Conteos en `generation_stages.runtime_info` de P1.
- Parser puro y seleccionable por `rules_version` para evaluación offline.
- Tests unitarios y de integración de P1.
- Documentación de la versión v3 y de la evaluación pendiente.

### Fuera de alcance

- Ampliar el reconocimiento de rol/medio (`"en calidad de"`, `"necesito"`, `"deseo"`,
  `"puedo"`).
- Segmentación de documentos sin `##` o sin declaración canónica.
- Producir el estado `invalid` para HU mal formadas.
- Persistir incidencias, fragmentos o marcadores por historia.
- Validar atomicidad, uniformidad o unicidad de HU; eso es P2.
- Cambiar prompts de P2/P6 o el contrato de esas etapas.
- Cambiar el default a v3 antes de la evaluación.
- Inventar anotaciones o usar `US24` como test limpio.

---

## 4. Diseño

### 4.1 Léxico y prioridad

`strength` describe la fiabilidad del marcador, no la calidad del beneficio. Un marcador
`weak` sigue produciendo una HU `valid`; solo indica que la relación means-end es menos segura.

| Nivel | Marcador | Fuerza | Consume | Notas |
|---|---|---|---|---|
| 1 | `para que` | `strong` | `para que` | El beneficio empieza después de `que`. |
| 2 | `con el fin de` | `strong` | conector + `que` si existe | También `con el fin de que`. |
| 2 | `con el objetivo de` | `strong` | conector + `que` si existe | También `con el objetivo de que`. |
| 2 | `con la finalidad de` | `strong` | conector + `que` si existe | También `con la finalidad de que`. |
| 2 | `a fin de` | `strong` | conector + `que` si existe | También `a fin de que`. |
| 3 | `para` + infinitivo | `weak` | solo `para` | Admite `no` y enclíticos. |
| 4 | `de modo que` | `weak` | conector completo | El beneficio empieza después de `que`. |
| 4 | `de manera que` | `weak` | conector completo | El beneficio empieza después de `que`. |
| 4 | `de forma que` | `weak` | conector completo | El beneficio empieza después de `que`. |

Reglas de reconocimiento:

- Sin distinguir mayúsculas/minúsculas; aceptar acentos y espacios repetidos.
- Nivel 2 **exige** que después del conector venga `que` o un infinitivo. Sin esa guarda,
  `"con el fin de lucro"` se tomaría como beneficio `"lucro"`.
- Nivel 3 admite `no` opcional y enclíticos plurales/singulares:
  - `para no perder`
  - `para usarlas`
  - `para revisarlo`
  - `para enviarnos`
- Nivel 3 **no** debe capturar complementos nominales:
  - `para el administrador`
  - `para los usuarios`
  - `para pacientes`
- Nivel 4 no debe capturar `"de modo"` ni `"de manera"` sin `"que"`.

Patrones de referencia (el implementador puede ajustarlos si los tests pasan):

```regex
# Nivel 1
\bpara\s+que\b

# Nivel 2: conector + de + (que | infinitivo)
\b(?:con\s+el\s+(?:fin|objetivo)|con\s+la\s+finalidad|a\s+fin)\s+de
(?:\s+que\b|(?=\s+(?:no\s+)?[a-záéíóúüñ]+(?:ar|er|ir)(?:se|lo|la|le|me|te|nos|los|las)?\b))

# Nivel 3: para + (no)? + infinitivo + enclítico opcional
\bpara(?=\s+(?:no\s+)?[a-záéíóúüñ]+(?:ar|er|ir)(?:se|lo|la|le|me|te|nos|los|las)?\b)

# Nivel 4
\bde\s+(?:modo|manera|forma)\s+que\b
```

En nivel 2, si existe `que`, el marcador incluye `que`; si no, el marcador termina en `de` y el
beneficio empieza en el infinitivo. En nivel 1 y 4 el marcador incluye `que`.

### 4.2 Algoritmo

1. Extraer la declaración canónica como hoy: `"Como <rol>, quiero <resto>"`.
2. Buscar todos los candidatos dentro de `<resto>`.
3. Descartar candidatos sin texto útil después del marcador.
4. Ordenar por `(nivel, -posición)`: gana el nivel más bajo; a igual nivel, el último.
5. Descartar candidatos solapados con el elegido.
6. `objective` = texto anterior al marcador elegido; limpiar separadores finales.
7. `benefit` = texto posterior al marcador completo; limpiar separadores iniciales y punto final.
8. Sin candidatos: `benefit=null`, `benefit_marker=null`, `benefit_strength=null` y
   `MISSING_BENEFIT`.

La prioridad manda sobre la posición: `"para que A, para B"` elige nivel 1 (`A`) aunque el nivel 3
(`B`) esté más al final. El “último gana” aplica solo a empates del mismo nivel.

`other_markers` contiene las etiquetas normalizadas de todos los candidatos descartados, en orden
de aparición y sin incluir el elegido. Si hay duplicados, se conservan.

### 4.3 Ejemplos de comportamiento

| Declaración | `objective` | `benefit` | Marcador | Fuerza |
|---|---|---|---|---|
| `Como cliente, quiero comparar precios para elegir la tienda más barata` | `comparar precios` | `elegir la tienda más barata` | `para` | weak |
| `Como cliente, quiero comparar precios para que elija la tienda más barata` | `comparar precios` | `elija la tienda más barata` | `para que` | strong |
| `Como gestor, quiero exportar datos con el fin de que otro equipo los analice` | `exportar datos` | `otro equipo los analice` | `con el fin de que` | strong |
| `Como gestor, quiero exportar datos con el objetivo de evitar errores` | `exportar datos` | `evitar errores` | `con el objetivo de` | strong |
| `Como usuario, quiero configurar el sistema de modo que tolere fallos` | `configurar el sistema` | `tolere fallos` | `de modo que` | weak |
| `Como usuario, quiero configurar el sistema de modo que tolere fallos, para reducir caídas` | `configurar el sistema de modo que tolere fallos` | `reducir caídas` | `para` | weak |
| `Como usuario, quiero revisar el informe para que no se filtren datos, para cumplir la norma` | `revisar el informe` | `no se filtren datos` | `para que` | strong |
| `Como usuario, quiero guardar el archivo para el administrador` | `guardar el archivo para el administrador` | `null` | `null` | `null` |
| `Como usuario, quiero revisar el informe para no perder datos` | `revisar el informe` | `no perder datos` | `para` | weak |
| `Como usuario, quiero descargar reportes para usarlas en Excel` | `descargar reportes` | `usarlas en Excel` | `para` | weak |
| `Como usuario, quiero registrar gastos con el fin de lucro` | `registrar gastos con el fin de lucro` | `null` | `null` | `null` |

Cambio semántico esperado: en `"para que …"`, v3 devuelve `goal="no se filtren datos"`; v2
devuelve `goal="que no se filtren datos"`. Es intencional, pero impide comparar filas v2/v3 sin
separarlas.

### 4.4 Contrato

En `UserStory` (`contracts/p1.py`):

```python
benefit_marker: str | None = None
benefit_strength: Literal["strong", "weak"] | None = None
other_markers: tuple[str, ...] = ()
```

- Usar `tuple[str, ...]`, no `list`, porque el contrato es frozen (advertencia #1 del roadmap).
- `benefit_marker` guarda la etiqueta literal normalizada: `"para que"`, `"con el fin de que"`,
  `"para"`, `"de modo que"`, etc.
- `benefit_strength` solo puede ser `"strong"`, `"weak"` o `None`.
- Validaciones:
  - `benefit_marker is None` ⇔ `benefit_strength is None`.
  - Si hay `benefit_marker`, debe haber `benefit`.
  - `other_markers` contiene candidatos descartados; si otra aparición del mismo marcador se
    descartó, la etiqueta puede repetirse y coincidir con la elegida.
- `to_rpc_payload()` no cambia: los campos nuevos no se persisten.

### 4.5 Trazabilidad

`NormalizeStage.run` añade a `runtime_info`:

```json
{
  "benefit_marker_counts": {
    "para que": 10,
    "con el fin de que": 2,
    "para": 5,
    "de modo que": 4
  },
  "benefit_strength_counts": {
    "strong": 12,
    "weak": 9,
    "none": 19
  },
  "discarded_marker_counts": {
    "de modo que": 3,
    "para": 2
  }
}
```

- Contar solo `user_stories`, no fragmentos.
- Convertir `Counter` a `dict` ordenado para que el JSON sea determinista.
- `rules_version` ya existe en `runtime_info`; no duplicarlo.
- `generations.config_snapshot` **no** guarda `P1_RULES_VERSION` (verificado en
  `services/generations.py:98`); no añadirlo allí. La fuente de verdad de la versión ejecutada es
  `generation_stages.runtime_info` de P1.

### 4.6 Parser puro y versionado

Crear `ai_service/pipeline/stages/p1_statement.py`:

```python
@dataclass(frozen=True)
class ParsedStatement:
    role: str | None
    objective: str | None
    benefit: str | None
    benefit_marker: str | None
    benefit_strength: str | None
    other_markers: tuple[str, ...]


def parse_statement(statement: str, rules_version: str) -> ParsedStatement | None:
    ...
```

- Debe ser puro: sin base de datos, sin LLM, sin `PipelineContext`.
- `v1` y `v2` conservan exactamente el comportamiento actual.
- `v3` usa el algoritmo de §4.2.
- `NormalizeStage._structure` llama a `parse_statement`; deja de aplicar la regex directamente.
- `SUPPORTED_RULES_VERSIONS` incluye `v1`, `v2` y `v3`.
- Mantener la validación de `build_p1_config` y el rechazo de versiones desconocidas.

La función pura permite evaluar v1/v2/v3 offline con las mismas anotaciones, sin arrancar el
servidor ni Supabase.

### 4.7 Orden de implementación

1. Crear `p1_statement.py` con v1/v2 movidos desde `p1_normalize.py` y tests de regresión.
2. Añadir v3 al parser puro y sus tests unitarios.
3. Añadir los campos al contrato y sus validaciones.
4. Integrar el parser en `NormalizeStage`, rellenar los campos y los conteos de `runtime_info`.
5. Añadir `v3` a `SUPPORTED_RULES_VERSIONS`; mantener el default en `v2`.
6. Actualizar documentación y ejecutar la suite rápida.
7. Si hay corpus, ejecutar la evaluación de §7; si no, dejar el issue como evaluación bloqueada.

No cambiar `.env.example` ni el default de `Settings.p1_rules_version`. Para un sondeo manual se
puede poner `P1_RULES_VERSION=v3` en el `.env` local, sin commitearlo.

---

## 5. Archivos que cambian

| Archivo | Cambio |
|---|---|
| `ai_service/pipeline/stages/p1_statement.py` | Nuevo: parser puro v1/v2/v3 y `SUPPORTED_RULES_VERSIONS`. |
| `ai_service/pipeline/stages/p1_normalize.py` | Usa `parse_statement`; rellena campos nuevos; añade conteos a `runtime_info`. |
| `ai_service/pipeline/contracts/p1.py` | Añade `benefit_marker`, `benefit_strength`, `other_markers` y validaciones. |
| `ai_service/pipeline/stages/__init__.py` | Importa/expone la lista de versiones válidas; sin cambio de default. |
| `tests/test_p1_statement.py` | Nuevo: unitarios del parser puro. |
| `tests/test_p1_normalize.py` | Añade v3 al parametrizado de versiones, integración y `runtime_info`. |
| `tests/test_stages_wiring.py` | Verifica que v3 es aceptada y que el default sigue siendo v2. |
| `docs/prompts_fases/Fase 4/plantilla_hu.md` | §2.1 documenta v3. |
| `docs/calibracion_resultados/bitacora/p1.md` | Nueva fila solo cuando haya sondeo real con v3. |
| `docs/pipeline_roadmap.md` | Nota de v3 opt-in y evaluación pendiente. |
| `scripts/evaluate_p1_v3.py` | Opcional: evaluación offline contra JSONL anotado. |

No se toca `supabase/schema.sql`, las RPC ni la tabla `user_stories`.

---

## 6. Pruebas

### 6.1 Parser puro

| Caso | Resultado esperado |
|---|---|
| `para que` | Marcador `"para que"`, strong, beneficio sin `"que"`. |
| `con el fin de que` | Marcador completo, strong, sin arrastre de `"que"`. |
| `con el objetivo de evitar` | Marcador `"con el objetivo de"`, strong, beneficio `"evitar"`. |
| `con la finalidad de que` | Marcador completo, strong. |
| `a fin de que` | Marcador completo, strong. |
| `para no perder` | Marcador `"para"`, weak, beneficio `"no perder"`. |
| `para usarlas` | Marcador `"para"`, weak, beneficio `"usarlas"`. |
| `para revisarlo` | Marcador `"para"`, weak, beneficio `"revisarlo"`. |
| `de modo que` | Marcador completo, weak. |
| `de manera que` | Marcador completo, weak. |
| `de forma que` | Marcador completo, weak. |
| `para el administrador` | Sin beneficio, `MISSING_BENEFIT`. |
| `para los usuarios` | Sin beneficio. |
| `con el fin de lucro` | Sin beneficio. |
| `a fin de cuentas` | Sin beneficio. |
| Sin marcador | `benefit=null`, `benefit_strength=null`. |
| Dos del mismo nivel | Gana el último. |
| Nivel 1 antes que nivel 3 | Gana nivel 1. |
| Nivel 4 antes que nivel 3 | Gana nivel 3. |
| Candidato solapado | Se descarta el solapado. |
| Marcador sin texto posterior | No es candidato. |
| Mayúsculas, acentos, espacios repetidos y saltos de línea | Se reconocen igual. |
| Punto final | Se elimina del `benefit`/`objective`. |

### 6.2 Integración de P1

- `UserStory` de v3 rellena `benefit_marker`, `benefit_strength` y `other_markers`.
- `objective`/`benefit` coinciden con §4.3.
- `runtime_info` contiene los tres conteos y `rules_version="v3"`.
- `to_rpc_payload()` sigue devolviendo exactamente las mismas claves.
- v1 y v2 producen los mismos resultados que antes (regresión).
- `build_p1_config` acepta `v3` y sigue rechazando `v9`.
- El default de `Settings.p1_rules_version` sigue siendo `v2`.
- La suite rápida sigue verde:

```bash
python -m pytest -q
```

Referencia actual: 544 passed, 15 deselected. No se ejecutan integration/e2e/llm.

### 6.3 Contrato

- `benefit_marker` sin `benefit` → error de validación.
- `benefit_marker` sin `benefit_strength` → error.
- `benefit_strength` sin `benefit_marker` → error.
- `other_markers` no incluye el candidato elegido; una etiqueta repetida de otro candidato sí se
  conserva.
- `other_markers` es una tupla inmutable.

---

## 7. Evaluación

### 7.1 Corpus

- **Dev:** 50–100 HU anotadas a mano para ajustar la heurística.
- **Test:** 50–100 HU anotadas de otra fuente/documento, no usadas durante el ajuste.
- `calibration_doc.txt` (US24, 40 HU) **no** sirve como test: v1/v2 ya lo vieron y es pequeño.
  Puede usarse como regresión/dev, nunca como test limpio.
- Si no hay corpus, no se inventan anotaciones: la implementación y los tests pueden completarse,
  pero la evaluación queda **bloqueada** y el default no cambia.

Formato sugerido, una HU por línea:

```json
{"id":"dev-001","text":"Como cliente, quiero comparar precios para elegir la tienda más barata","role":"cliente","objective":"comparar precios","benefit":"elegir la tienda más barata","marker":"para","strength":"weak","notes":""}
```

Para HU sin beneficio:

```json
{"id":"dev-002","text":"Como usuario, quiero iniciar sesión","role":"usuario","objective":"iniciar sesión","benefit":null,"marker":null,"strength":null,"notes":"sin justificación"}
```

### 7.2 Protocolo

1. Anotar primero el conjunto de desarrollo.
2. Implementar y ajustar v3 solo con dev.
3. Congelar la regla y los umbrales antes de abrir test.
4. Ejecutar v2 y v3 sobre test una sola vez.
5. Reportar resultados por versión, sin mezclar filas ni reajustar después de ver test.

La evaluación debe llamar a `parse_statement` directamente. No requiere servidor, Supabase ni
LLM.

### 7.3 Métricas

| Métrica | Definición |
|---|---|
| `role_exact` | `role` coincide tras normalizar. |
| `objective_exact` | `objective` coincide tras normalizar. |
| `benefit_exact` | `benefit` coincide, incluido `null`. |
| `false_missing_benefit` | Anotación con beneficio y parser devuelve `null`. |
| `false_benefit` | Anotación sin beneficio y parser devuelve texto. |
| `objective_cut` | `objective` parseado más corto que el anotado por un marcador mal elegido. |
| `marker_exact` | Marcador y fuerza coinciden con la anotación. |

Normalización de comparación: minúsculas, espacios colapsados, sin punto final.

### 7.4 Criterio de aceptación

En dev, v3 debe:

- Reducir `false_missing_benefit` frente a v2.
- No aumentar `objective_cut`.
- Mantener `role_exact` (la parte de rol no cambia).
- Mejorar o igualar `benefit_exact`.

En test, reportar los mismos valores sin reajustar. Si v3 no cumple, se queda como experimental y
v2 sigue siendo el default.

No se exige un umbral absoluto antes de tener datos; el umbral se fija en dev y se congela antes
de test.

---

## 8. Riesgos

- **`de modo que` expresa manera/consecuencia, no siempre fin.** Aceptarlo como weak puede
  convertir advertencias en beneficios falsos. Medir `false_benefit`.
- **Nivel 2 demasiado laxo.** Sin la guarda `que`/infinitivo, `"con el fin de lucro"` y similares
  serían falsos positivos. La guarda es obligatoria.
- **Prioridad frente a posición.** Un `para que` temprano gana a un `para` final aunque el segundo
  sea más específico. Es la regla acordada; la evaluación dirá si perjudica.
- **Cambio de `goal` al quitar `"que"`.** P2/P6 no deberían depender del `"que"`, pero conviene
  una prueba de humo con una generación P1–P2 y otra P1–P6 antes de promover v3.
- **Sobreajuste a US24.** Por eso US24 no es test y se exige otra fuente.
- **Coste de anotación.** Sin corpus etiquetado no hay validación; no se debe declarar v3
  “mejor” solo porque los tests unitarios pasan.
- **Trazabilidad solo en memoria.** `benefit_marker`/`other_markers` no se persisten; la
  comparación v2/v3 se hace offline con los JSONL, no consultando la BD.

---

## 9. Criterios de cierre

La implementación se considera terminada cuando:

- `v3` es seleccionable con `P1_RULES_VERSION=v3` y `v1`/`v2` siguen funcionando igual.
- Los tests de §6 pasan y la suite rápida sigue verde.
- `runtime_info` registra los conteos de marcadores, fuerza y descartados.
- `to_rpc_payload()` no cambia y no hay migración.
- El default sigue en `v2`.
- La documentación de §5 está actualizada.

La evaluación se considera cerrada solo cuando:

- Existe el corpus dev/test anotado de §7.1.
- Se ejecutó v2 vs v3 con el protocolo de §7.2.
- Se reportaron las métricas de §7.3.
- Se decidió, con datos, si v3 pasa a default o se queda experimental.

Mientras no exista corpus, el issue puede quedar como **implementado con evaluación bloqueada**;
no se debe cerrar como validado.

---

## 10. Referencias

- `ai_service/pipeline/stages/p1_normalize.py` — reglas v1/v2, `_structure`, `runtime_info`.
- `ai_service/pipeline/contracts/p1.py` — `UserStory`, `to_rpc_payload`.
- `ai_service/pipeline/stages/__init__.py` — `build_p1_config`, versiones válidas.
- `ai_service/config.py` — `p1_rules_version` (default `v2`).
- `tests/test_p1_normalize.py` — regresiones v1/v2, payload, persistencia.
- `tests/test_stages_wiring.py` — default y rechazo de versiones.
- `docs/prompts_fases/Fase 4/plantilla_hu.md` §2.1 — contrato de la declaración canónica.
- `docs/calibracion_resultados/bitacora/p1.md` — sondeos v1/v2 sobre US24.
- `docs/calibracion_resultados/guia_calibracion.md` §5 — criterio de P1.
- `docs/prompts_fases/Fase 3/pipeline_design.md` — P1, D-02, D-21, D-22.
- `docs/pipeline_roadmap.md` — advertencia #5 y convención de `runtime_info`.
- `supabase/schema.sql` — `persist_p1_user_stories` y columnas persistidas.

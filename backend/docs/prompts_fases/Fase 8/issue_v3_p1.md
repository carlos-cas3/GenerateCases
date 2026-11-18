# Issue — P1 v3: léxico de marcadores de fin, prioridad y trazabilidad

> **Estado:** pendiente de implementar.
> **Prioridad:** media-alta — afecta la calidad de `objective`/`benefit` en todas las HU.
> **Depende de:** P1 v2 en estado actual (`P1_RULES_VERSION=v2`, commit `61a4c63`).
> **Default tras implementar:** sigue siendo `v2`; v3 se activa con `P1_RULES_VERSION=v3`.
> **Evaluación:** bloqueada hasta tener anotaciones manuales sobre los corpus disponibles.

---

## Qué hay que hacer (resumen ejecutivo)

P1 v2 identifica el beneficio de una HU buscando `"para"` seguido de `"que"` o un infinitivo.
Eso deja sin beneficio muchas HU que sí lo tienen, solo porque usan otro marcador como
`"de modo que"` o `"con el fin de"`.

La tarea es implementar **P1 v3** como una nueva versión seleccionable del parser. v3 amplía el
léxico de marcadores reconocidos, registra cuál se usó y con qué fiabilidad, y lo hace sin tocar
la base de datos ni cambiar el comportamiento de v1/v2.

Los pasos concretos están en §4.7. Los archivos que cambian están en §5. Las pruebas que deben
pasar están en §6. El default **no cambia** hasta que la evaluación de §7 lo confirme.

---

## Lectura previa obligatoria

Antes de tocar código, leer:

- `ai_service/pipeline/stages/p1_normalize.py` — el parser actual; en particular `STATEMENT_RULES`,
  `NormalizeStage._structure` y `NormalizeStage.run`.
- `ai_service/pipeline/contracts/p1.py` — `UserStory`, `P1Output` y `to_rpc_payload`.
- `ai_service/pipeline/stages/__init__.py` — `build_p1_config` y `SUPPORTED_RULES_VERSIONS`.
- `tests/test_p1_normalize.py` — los tests de regresión de v1/v2 que no deben romperse.
- `docs/prompts_fases/Fase 4/plantilla_hu.md` §2.1 — contrato de la declaración canónica.

---

## 1. Contexto del problema

P1 v2 usa una sola regex que captura `(role, objective, benefit)` en un pase. El beneficio solo
se activa cuando detecta `"para que"` o `"para"` + infinitivo. Cualquier otro marcador produce
`benefit=null` y una incidencia `MISSING_BENEFIT`.

El análisis de los tres corpus disponibles muestra marcadores que v2 no reconoce:

- `"de modo que"` — frecuente en US21 (H11, H13, H18, H20, H23 y otros) y US24 (H7, H13,
  H16, H22, H23, H25–H27, H34, H37).
- `"con el fin de"` — aparece en US21 (H22, H77, H94).
- `"porque"` — aparece en US21 (H31, H32, H33, H67) como justificación del autor; semántica
  distinta al beneficio funcional, con riesgo alto de falso positivo.

Además, cuando v2 reconoce `"para que"`, el beneficio conserva el `"que"` inicial
(`"que haya menos discrepancias"`). v3 consume el marcador completo y devuelve solo
`"haya menos discrepancias"`.

Una parte significativa de los `MISSING_BENEFIT` son **ausencias reales** de beneficio, no
marcadores no reconocidos. v3 no los eliminará todos; solo reducirá los falsos.

| Documento | HU totales | Con beneficio explícito (est.) | Sin beneficio real (est.) |
|---|---|---|---|
| US21 | 115 | ~65 | ~50 |
| US24 | 40 | ~18 | ~22 |
| US27 | 34 | ~18 | ~16 |

---

## 2. Qué debe mejorar v3 (hipótesis a validar)

1. Reducir los falsos `MISSING_BENEFIT` en los corpus disponibles.
2. No aumentar los objetivos cortados (`objective_cut`).
3. No cambiar `role`; mantener o mejorar `objective`/`benefit` respecto a v2.

Son hipótesis, no certezas. La evaluación de §7 las confirma o refuta.

---

## 3. Alcance

### Dentro del alcance

- Léxico de marcadores en cinco niveles (ver §4.1).
- Algoritmo de selección con prioridad y desempate (ver §4.2).
- Campos `benefit_marker`, `benefit_strength` y `other_markers` en `UserStory` (solo en memoria,
  no se persisten).
- Conteos de marcadores en `generation_stages.runtime_info` de P1.
- Parser puro en `p1_statement.py`, invocable sin servidor ni Supabase.
- Tests unitarios del parser y tests de integración de P1.

### Fuera del alcance

- Inferir beneficio por posición o por coma sin marcador explícito — los corpus confirman que ese
  patrón no es consistente entre documentos.
- Ampliar el reconocimiento de rol (`"en calidad de"`, `"necesito"`, `"deseo"`, `"puedo"`).
- Segmentación de documentos sin `##` o sin declaración canónica.
- Producir el estado `invalid` para HU mal formadas.
- Persistir marcadores o incidencias por historia en la base de datos.
- Validar atomicidad, uniformidad o unicidad de HU (eso es P2).
- Cambiar prompts de P2/P6 ni su contrato.
- Cambiar el default a v3 antes de la evaluación.
- Inventar anotaciones ni usar los corpus como test limpio antes de anotarlos.

---

## 4. Diseño

### 4.1 Léxico y prioridad

`strength` describe la fiabilidad del marcador como introductor de beneficio, no la calidad del
beneficio en sí. Un marcador `weak` produce una HU `valid`; solo señala que la relación
means-end es menos segura.

| Nivel | Marcador | Fuerza | Qué consume | Notas |
|---|---|---|---|---|
| 1 | `para que` | `strong` | `para que` | Beneficio empieza después de `que`. |
| 2 | `con el fin de` | `strong` | conector + `que` si existe | También `con el fin de que`. Exige guarda (ver abajo). |
| 2 | `con el objetivo de` | `strong` | conector + `que` si existe | También `con el objetivo de que`. |
| 2 | `con la finalidad de` | `strong` | conector + `que` si existe | También `con la finalidad de que`. |
| 2 | `a fin de` | `strong` | conector + `que` si existe | También `a fin de que`. |
| 3 | `para` + infinitivo | `weak` | solo `para` | Admite `no` y enclíticos. No captura nominales. |
| 4 | `de modo que` | `weak` | conector completo | Frecuente en corpus. Expresa consecuencia, no siempre fin — medir `false_benefit`. |
| 4 | `de manera que` | `weak` | conector completo | Beneficio empieza después de `que`. |
| 4 | `de forma que` | `weak` | conector completo | Beneficio empieza después de `que`. |
| 5 | `porque` | `weak` | solo `porque` | Riesgo alto de capturar justificaciones del autor, no beneficios funcionales. Ver §8. Implementar desactivado por default dentro de v3 hasta tener datos de evaluación. |

**Reglas de reconocimiento:**

- Sin distinguir mayúsculas/minúsculas; aceptar acentos y espacios repetidos.
- Nivel 2 **exige** que después del conector venga `que` o un infinitivo. Sin esa guarda,
  `"con el fin de lucro"` produciría beneficio `"lucro"` — falso positivo.
- Nivel 3 admite `no` opcional y enclíticos (`para no perder`, `para usarlas`, `para revisarlo`,
  `para enviarnos`). **No** debe capturar complementos nominales (`para el administrador`,
  `para los usuarios`, `para pacientes`).
- Nivel 4 no debe capturar `"de modo"` ni `"de manera"` sin `"que"`.
- Nivel 5 no tiene guarda de infinitivo porque en los corpus aparece seguido de texto nominal.
  Por eso su riesgo de `false_benefit` es el más alto.

**Patrones de referencia** (ajustar si los tests pasan):

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

# Nivel 5
\bporque\b
```

En nivel 2: si existe `que`, el marcador lo incluye; si no, el marcador termina en `de` y el
beneficio empieza en el infinitivo. En niveles 1 y 4 el marcador incluye `que`.

### 4.2 Algoritmo de selección

Aplicar sobre el texto `<resto>` (todo lo que sigue a `"Como <rol>, quiero "`):

1. Buscar todos los candidatos usando los patrones de §4.1.
2. Descartar candidatos sin texto útil después del marcador.
3. Ordenar por `(nivel, -posición)`: gana el nivel más bajo; a igual nivel, gana el último.
4. Descartar candidatos solapados con el elegido.
5. `objective` = texto antes del marcador elegido; eliminar separadores finales (`,`, `.`, `;`).
6. `benefit` = texto después del marcador completo; eliminar separadores iniciales y punto final.
7. Sin candidatos válidos: `benefit=null`, `benefit_marker=null`, `benefit_strength=null`,
   emitir `MISSING_BENEFIT`.

La prioridad manda sobre la posición: si hay `"para que A, para B"`, gana nivel 1 (`A`) aunque
el nivel 3 (`B`) aparezca después. El "último gana" aplica solo a empates del mismo nivel.

`other_markers` = etiquetas normalizadas de los candidatos descartados, en orden de aparición,
sin incluir el elegido. Los duplicados se conservan.

### 4.3 Comportamiento esperado

Casos reales de los corpus:

| Declaración | `objective` | `benefit` | Marcador | Fuerza | Fuente |
|---|---|---|---|---|---|
| `Como miembro de la facultad, quiero recopilar mis publicaciones en un único punto de acceso, de modo que pueda elevar el perfil de mi trabajo` | `recopilar mis publicaciones en un único punto de acceso` | `pueda elevar el perfil de mi trabajo` | `de modo que` | weak | US21-H11 |
| `Como administrador de DB / IR, quiero ver la lista de suscriptores para un informe específico con el fin de investigar las quejas de informes faltantes` | `ver la lista de suscriptores para un informe específico` | `investigar las quejas de informes faltantes` | `con el fin de` | strong | US21-H22 |
| `Como miembro de la facultad de Cornell, quiero que los elementos que he depositado aparezcan en los primeros lugares de Google, porque ese es mi boleto al estrellato` | `que los elementos que he depositado aparezcan en los primeros lugares de Google` | `ese es mi boleto al estrellato` | `porque` | weak | US21-H32 |
| `Como administrador del sistema, quiero que todos los datos se almacenen en una base de datos central, para que haya menos discrepancias entre los departamentos` | `que todos los datos se almacenen en una base de datos central` | `haya menos discrepancias entre los departamentos` | `para que` | strong | US24-H6 |
| `Como médico, quiero que las enfermeras solo tengan un control parcial sobre los registros médicos del paciente, para que no eliminen accidentalmente datos importantes` | `que las enfermeras solo tengan un control parcial sobre los registros médicos del paciente` | `no eliminen accidentalmente datos importantes` | `para que` | strong | US27-H17 |
| `Como usuario, quiero guardar el archivo para el administrador` | `guardar el archivo para el administrador` | `null` | `null` | `null` | sintético |
| `Como usuario, quiero registrar gastos con el fin de lucro` | `registrar gastos con el fin de lucro` | `null` | `null` | `null` | sintético |

**Cambio respecto a v2:** en `"para que …"`, v3 devuelve `benefit="haya menos discrepancias"`;
v2 devolvía `benefit="que haya menos discrepancias"`. Es intencional. Al comparar resultados en
la evaluación, separar las filas v2 de las v3.

### 4.4 Contrato — cambios en `UserStory`

Añadir a `UserStory` en `contracts/p1.py`:

```python
benefit_marker: str | None = None
benefit_strength: Literal["strong", "weak"] | None = None
other_markers: tuple[str, ...] = ()
```

Restricciones:

- Usar `tuple[str, ...]`, no `list` (el contrato es frozen — advertencia #1 del roadmap).
- `benefit_marker` guarda la etiqueta literal normalizada: `"para que"`, `"con el fin de"`,
  `"para"`, `"de modo que"`, `"porque"`, etc.
- `benefit_strength` acepta solo `"strong"`, `"weak"` o `None`.
- `benefit_marker is None` ⟺ `benefit_strength is None`.
- Si `benefit_marker` tiene valor, `benefit` también debe tenerlo.
- **`to_rpc_payload()` no cambia.** Los tres campos nuevos no se persisten en base de datos.

### 4.5 Trazabilidad en `runtime_info`

Añadir en `NormalizeStage.run`, dentro del dict que se pasa a `StageResult(runtime_info=…)`:

```json
{
  "benefit_marker_counts": {
    "para que": 10,
    "con el fin de": 2,
    "para": 5,
    "de modo que": 4,
    "porque": 1
  },
  "benefit_strength_counts": {
    "strong": 12,
    "weak": 10,
    "none": 18
  },
  "discarded_marker_counts": {
    "de modo que": 3,
    "para": 2
  }
}
```

Reglas:

- Contar solo `user_stories`, no fragmentos no resueltos.
- Convertir cada `Counter` a `dict` ordenado antes de asignarlo (para JSON determinista).
- `rules_version` ya está en `runtime_info`; no duplicarlo.
- **No** añadir `P1_RULES_VERSION` a `generations.config_snapshot` (`services/generations.py:98`).
  La fuente de verdad de la versión ejecutada es `generation_stages.runtime_info` de P1.

### 4.6 Nuevo archivo: `p1_statement.py`

Crear `ai_service/pipeline/stages/p1_statement.py` con:

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

Requisitos del módulo:

- **Puro**: sin base de datos, sin LLM, sin `PipelineContext`.
- `v1` y `v2` conservan el comportamiento actual exacto (mover la lógica desde `p1_normalize.py`,
  no reescribirla).
- `v3` implementa el algoritmo de §4.2.
- `SUPPORTED_RULES_VERSIONS` incluye `"v1"`, `"v2"` y `"v3"`.
- `NormalizeStage._structure` debe llamar a `parse_statement` en lugar de aplicar la regex
  directamente.
- Mantener la validación en `build_p1_config` que rechaza versiones desconocidas.

### 4.7 Pasos de implementación

Seguir este orden para mantener la suite verde en cada paso:

1. Crear `p1_statement.py` moviendo la lógica de v1/v2 desde `p1_normalize.py`. Verificar que
   los tests de regresión de v1/v2 pasan sin cambios.
2. Añadir v3 al parser puro con el algoritmo de §4.2. Escribir los tests unitarios de §6.1.
3. Añadir `benefit_marker`, `benefit_strength` y `other_markers` a `UserStory` con sus
   validaciones (§4.4).
4. Modificar `NormalizeStage._structure` para llamar a `parse_statement` y rellenar los campos
   nuevos. Añadir los conteos de §4.5 a `runtime_info`.
5. Añadir `"v3"` a `SUPPORTED_RULES_VERSIONS`. Verificar que el default sigue siendo `"v2"`.
6. Actualizar la documentación listada en §5. Ejecutar la suite completa.
7. Si hay corpus anotado disponible, ejecutar la evaluación de §7. Si no, marcar el issue como
   **implementado con evaluación bloqueada** y no cerrarlo como validado.

**No modificar** `.env.example` ni el default de `Settings.p1_rules_version`. Para probar v3
localmente: `P1_RULES_VERSION=v3` en el `.env` local, sin commitearlo.

---

## 5. Archivos que cambian

| Archivo | Qué hacer |
|---|---|
| `ai_service/pipeline/stages/p1_statement.py` | **Crear.** Parser puro con v1, v2 y v3. Exportar `SUPPORTED_RULES_VERSIONS`. |
| `ai_service/pipeline/stages/p1_normalize.py` | Reemplazar la regex inline por una llamada a `parse_statement`. Rellenar campos nuevos. Añadir conteos a `runtime_info`. |
| `ai_service/pipeline/contracts/p1.py` | Añadir `benefit_marker`, `benefit_strength`, `other_markers` y sus validaciones a `UserStory`. No tocar `to_rpc_payload`. |
| `ai_service/pipeline/stages/__init__.py` | Importar y exponer `SUPPORTED_RULES_VERSIONS` desde `p1_statement`. Sin cambio de default. |
| `tests/test_p1_statement.py` | **Crear.** Tests unitarios del parser puro (casos de §6.1, incluidos casos reales de US21/US24/US27). |
| `tests/test_p1_normalize.py` | Añadir v3 al parametrizado de versiones, tests de integración y verificación de `runtime_info`. |
| `tests/test_stages_wiring.py` | Verificar que v3 es aceptada y que el default sigue siendo v2. |
| `docs/prompts_fases/Fase 4/plantilla_hu.md` | Documentar v3 en §2.1. |
| `docs/calibracion_resultados/bitacora/p1.md` | Añadir fila solo cuando haya un sondeo real ejecutado con v3. |
| `docs/pipeline_roadmap.md` | Añadir nota de v3 opt-in y evaluación pendiente. |
| `scripts/evaluate_p1_v3.py` | **Crear (opcional).** Script de evaluación offline contra JSONL anotado. |

**No tocar:** `supabase/schema.sql`, las RPC, la tabla `user_stories`, ni ningún archivo de
migración.

---

## 6. Pruebas

La suite debe seguir verde con `python -m pytest -q`. Referencia actual: 544 passed,
15 deselected. No correr integration/e2e/llm.

### 6.1 Tests unitarios del parser puro (`test_p1_statement.py`)

| Entrada | Resultado esperado |
|---|---|
| `"…para que haya menos discrepancias"` | Marcador `"para que"`, strong, benefit sin `"que"`. |
| `"…con el fin de que otro equipo los analice"` | Marcador `"con el fin de que"`, strong. |
| `"…con el objetivo de evitar errores"` | Marcador `"con el objetivo de"`, strong, benefit `"evitar errores"`. |
| `"…con la finalidad de que se registre"` | Marcador `"con la finalidad de que"`, strong. |
| `"…a fin de que se reduzcan los tiempos"` | Marcador `"a fin de que"`, strong. |
| `"…para no perder datos"` | Marcador `"para"`, weak, benefit `"no perder datos"`. |
| `"…para usarlas en Excel"` | Marcador `"para"`, weak, benefit `"usarlas en Excel"`. |
| `"…para revisarlo más tarde"` | Marcador `"para"`, weak. |
| `"…de modo que pueda elevar el perfil de mi trabajo"` | Marcador `"de modo que"`, weak. |
| `"…de manera que se garantice la seguridad"` | Marcador `"de manera que"`, weak. |
| `"…de forma que se procese correctamente"` | Marcador `"de forma que"`, weak. |
| `"…porque ese es mi boleto al estrellato"` (US21-H32, con nivel 5 activo) | Marcador `"porque"`, weak. |
| `"…para el administrador"` | Sin benefit, `MISSING_BENEFIT`. |
| `"…para los usuarios"` | Sin benefit. |
| `"…con el fin de lucro"` | Sin benefit. |
| `"…a fin de cuentas"` | Sin benefit. |
| Sin marcador (ej. US27-H6) | `benefit=null`, `benefit_marker=null`, `benefit_strength=null`. |
| Dos marcadores del mismo nivel | Gana el último. |
| Nivel 1 antes que nivel 3 en la misma declaración | Gana nivel 1. |
| Nivel 4 antes que nivel 3 en la misma declaración | Gana nivel 3. |
| Nivel 5 (`porque`) vs nivel 3 (`para` + infinitivo) | Gana nivel 3. |
| Marcador solapado con el elegido | Se descarta el solapado. |
| Marcador sin texto posterior | No es candidato válido. |
| Mayúsculas, tildes, espacios repetidos y saltos de línea | Se reconocen igual. |
| Punto final en benefit u objective | Se elimina. |

### 6.2 Tests de integración de P1 (`test_p1_normalize.py`)

- Con `rules_version="v3"`, `UserStory` rellena `benefit_marker`, `benefit_strength` y
  `other_markers`.
- Los valores de `objective`/`benefit` coinciden con los ejemplos de §4.3.
- `runtime_info` contiene `benefit_marker_counts`, `benefit_strength_counts`,
  `discarded_marker_counts` y `rules_version="v3"`.
- `to_rpc_payload()` devuelve exactamente las mismas claves que hoy, sin los campos nuevos.
- Con `rules_version="v1"` y `"v2"`, los resultados son idénticos a los tests existentes
  (regresión).
- `build_p1_config` acepta `"v3"` y sigue rechazando `"v9"`.
- El default de `Settings.p1_rules_version` sigue siendo `"v2"`.

### 6.3 Tests de contrato (`test_p1_normalize.py` o `test_p1_statement.py`)

- `benefit_marker` con valor pero `benefit=null` → error de validación de Pydantic.
- `benefit_marker` con valor pero `benefit_strength=null` → error.
- `benefit_strength` con valor pero `benefit_marker=null` → error.
- `other_markers` no incluye el marcador elegido (sí puede incluir etiquetas repetidas de otros
  candidatos descartados).
- `other_markers` es una tupla, no una lista.

---

## 7. Evaluación

La implementación puede completarse sin la evaluación. Lo que **no** puede hacerse sin ella es
cambiar el default a v3 ni declarar v3 "mejor" que v2.

### 7.1 Corpus disponibles

| Rol | Archivo | HU |
|---|---|---|
| Dev (ajuste) | `datasets/pyunml/calibration_doc_US21.txt` | 115 |
| Test (medición final) | `datasets/pyunml/calibration_doc_US24.txt` | 40 |
| Test (medición final) | `datasets/pyunml/calibration_doc_U27.txt` | 34 |

Anotar US21 primero. No abrir US24/US27 hasta tener v3 ajustada con US21. Ninguno de los tres
sirve como test limpio sin anotaciones manuales previas.

### 7.2 Formato de anotación (JSONL, una HU por línea)

HU con beneficio:

```json
{"id":"US21-011","text":"Como miembro de la facultad, quiero recopilar fácilmente mis publicaciones en un único punto de acceso en línea, de modo que pueda elevar el perfil de mi trabajo","role":"miembro de la facultad","objective":"recopilar fácilmente mis publicaciones en un único punto de acceso en línea","benefit":"pueda elevar el perfil de mi trabajo","marker":"de modo que","strength":"weak","notes":""}
```

HU sin beneficio:

```json
{"id":"US27-006","text":"Como paciente, quiero poder renovar mis recetas de medicamentos","role":"paciente","objective":"poder renovar mis recetas de medicamentos","benefit":null,"marker":null,"strength":null,"notes":"sin justificación explícita"}
```

### 7.3 Protocolo

1. Anotar US21 manualmente.
2. Implementar y ajustar v3 usando solo US21.
3. Congelar la regla antes de abrir US24/US27.
4. Ejecutar v2 y v3 sobre US24 + US27 una sola vez, llamando a `parse_statement` directamente.
5. Reportar las métricas de §7.4 por versión. No reajustar después de ver los resultados de test.

### 7.4 Métricas a reportar

| Métrica | Definición |
|---|---|
| `role_exact` | `role` coincide tras normalizar (minúsculas, espacios colapsados). |
| `objective_exact` | `objective` coincide tras normalizar. |
| `benefit_exact` | `benefit` coincide, incluido `null`. |
| `false_missing_benefit` | Anotación tiene benefit pero el parser devuelve `null`. |
| `false_benefit` | Anotación no tiene benefit pero el parser devuelve texto. |
| `objective_cut` | `objective` parseado es más corto que el anotado por un marcador mal elegido. |
| `marker_exact` | Marcador y fuerza coinciden con la anotación. |

Reportar `false_benefit` desglosado por marcador (`"porque"`, `"de modo que"`, resto) para
decidir si nivel 5 se activa o se mantiene desactivado por default.

### 7.5 Criterio de aceptación

En dev (US21), v3 debe:

- Reducir `false_missing_benefit` respecto a v2.
- No aumentar `objective_cut`.
- Mantener `role_exact`.
- Mejorar o igualar `benefit_exact`.

En test (US24 + US27), reportar los mismos valores sin reajustar. Si v3 no cumple, se queda
como versión experimental y v2 sigue siendo el default.

---

## 8. Riesgos a tener en cuenta

- **`"porque"` captura justificaciones del autor, no beneficios funcionales.** US21-H32
  (`"porque ese es mi boleto al estrellato"`) y US21-H31 son los casos típicos. Implementar
  el nivel 5 desactivado por default dentro de v3 y activarlo solo con un flag explícito hasta
  tener datos de evaluación.
- **`"de modo que"` expresa consecuencia, no siempre fin.** El riesgo de `false_benefit` es real,
  especialmente en US24. Medir antes de promover.
- **Nivel 2 sin la guarda produce falsos positivos.** `"con el fin de lucro"` → benefit `"lucro"`.
  La guarda `que`/infinitivo es obligatoria.
- **El cambio de benefit al quitar `"que"` puede afectar P2/P6.** Hacer una prueba de humo con
  una generación P1–P2 y otra P1–P6 antes de promover v3 a default.
- **Una bajada del total de `MISSING_BENEFIT` no confirma que v3 sea mejor.** Si también sube
  `false_benefit`, puede ser peor. Medir ambos.
- **`benefit_marker` y `other_markers` no se persisten.** La comparación v2/v3 se hace offline
  con los JSONL anotados, no consultando la base de datos.

---

## 9. Criterios de cierre

### La implementación está terminada cuando:

- [ ] `P1_RULES_VERSION=v3` selecciona v3 y `v1`/`v2` producen los mismos resultados que antes.
- [ ] Los tests de §6 pasan y `python -m pytest -q` sigue verde (referencia: 544 passed).
- [ ] `runtime_info` incluye los tres conteos nuevos.
- [ ] `to_rpc_payload()` no cambió y no hay migración de base de datos.
- [ ] El default sigue en `v2`.
- [ ] Los archivos de documentación de §5 están actualizados.

### La evaluación está cerrada cuando:

- [ ] US21 está anotado a mano y US24 + US27 están anotados.
- [ ] Se ejecutó v2 vs v3 siguiendo el protocolo de §7.3.
- [ ] Se reportaron las métricas de §7.4, incluido `false_benefit` desglosado por marcador.
- [ ] Se decidió, con datos, si v3 pasa a default y si nivel 5 (`"porque"`) se activa.

Mientras no existan anotaciones, el issue debe quedar como **implementado / evaluación bloqueada**.
No cerrarlo como validado.

---

## 10. Referencias

| Recurso | Para qué |
|---|---|
| `datasets/pyunml/calibration_doc_US21.txt` | Corpus dev; 115 HU con la mayor variedad de marcadores. |
| `datasets/pyunml/calibration_doc_US24.txt` | Corpus test; 40 HU. No abrir hasta ajustar con US21. |
| `datasets/pyunml/calibration_doc_U27.txt` | Corpus test; 34 HU. No abrir hasta ajustar con US21. |
| `ai_service/pipeline/stages/p1_normalize.py` | Parser actual (v1/v2), `_structure`, `runtime_info`. |
| `ai_service/pipeline/contracts/p1.py` | `UserStory`, `P1Output`, `to_rpc_payload`. |
| `ai_service/pipeline/stages/__init__.py` | `build_p1_config`, versiones válidas actuales. |
| `ai_service/config.py` | `p1_rules_version` (default `v2`). |
| `tests/test_p1_normalize.py` | Tests de regresión de v1/v2 que no deben romperse. |
| `tests/test_stages_wiring.py` | Verificación de default y rechazo de versiones. |
| `docs/prompts_fases/Fase 4/plantilla_hu.md` §2.1 | Contrato de la declaración canónica. |
| `docs/calibracion_resultados/bitacora/p1.md` | Sondeos v1/v2 sobre US24. |
| `docs/calibracion_resultados/guia_calibracion.md` §5 | Criterio de P1. |
| `docs/prompts_fases/Fase 3/pipeline_design.md` | P1, D-02, D-21, D-22. |
| `docs/pipeline_roadmap.md` | Advertencia #5 y convención de `runtime_info`. |
| `supabase/schema.sql` | `persist_p1_user_stories` y columnas persistidas (no tocar). |

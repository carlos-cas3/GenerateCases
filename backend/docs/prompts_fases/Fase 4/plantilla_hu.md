# Plantilla de Historia de Usuario (HU)

> **Propuesta para T-F4-02.** Contrato de formato que acuerdan el **servicio externo upstream**
> (normaliza el documento antes de subirlo a Storage) y la **regex/heurística de P1**. Versionada
> por `rules_version` de `P1Config`.
>
> **Estado:** ✅ aprobado por el responsable. P1 no usa LLM (camino B).

---

## 1. Estructura de una HU

Cada HU es un bloque que empieza con un encabezado de nivel 2 (`## `), seguido de la declaración
canónica y secciones opcionales de nivel 3 (`### `).

```
## <Título breve de la HU>
Como <rol>, quiero <objetivo/acción>, para <beneficio/meta>.

### Criterios de aceptación
- <criterio 1>
- <criterio 2>

### Reglas de negocio
- <regla 1>

### Restricciones
- <restricción 1>
```

---

## 2. Delimitadores (lo que parsea P1)

| Elemento | Marcador | Patrón (regex) | Campo del contrato |
|---|---|---|---|
| Inicio de HU | línea que empieza con `## ` | `^##\s+.+$` → va a `P1Config.story_delimiter_pattern` | parte el documento en bloques |
| Declaración canónica | primera línea no vacía tras el `##`, forma "Como X, quiero Y, para Z" | `^Como\s+(.+?),\s+quiero\s+(.+?)(?:,?\s*para\s+(.+?))?\s*\.?\s*$` | `role`, `objective` (→ `action`), `benefit` (→ `goal`) |
| Sección de contenido | encabezado de nivel 3 `### ` | `^###\s+.+$` | `content_sections` (`kind` = título, `text` = cuerpo) |

- `position` lo asigna P1 por orden de aparición (1, 2, 3…).
- Los códigos `HU-xxx` **los asigna el pipeline**, no el documento.
- La regex de la declaración canónica es parte de la heurística de P1 (no de `P1Config`); si se
  quiere configurable, se añade a `P1Config`. Hoy se versiona vía `rules_version`.

---

## 3. Reglas de identificación (heurística de P1)

Para cada bloque delimitado por `## `:

- **Declaración completa** ("Como…, quiero…, para…") → `UserStory` con
  `validation_status = valid`.
- **"Como…, quiero…" sin "para…"** → `UserStory` con
  `validation_status = valid_with_warnings` y un `ValidationIssue`
  (`rule_code="MISSING_BENEFIT"`, `severity="warning"`, "falta la justificación 'para …'").
- **Sin declaración canónica** (no hay "Como…, quiero…") → **historia no identificada** →
  `UnresolvedFragment` (`reason="no coincide con la plantilla de HU"`).
- Si **ningún** bloque produce una `UserStory` → P1 lanza `NO_STORIES_FOUND`.

- `original_text` = todo el texto del bloque (del `## ` al siguiente `## ` o al fin del documento).
- `content_sections` = cada bloque bajo un `### ` (`kind` = título normalizado, `text` = cuerpo).
  El texto fuera de la declaración y de las secciones `### ` se ignora.

---

## 4. Secciones reconocidas (`kind` sugeridos para `content_sections`)

| Marcador `###` | `kind` sugerido | Contenido |
|---|---|---|
| `### Criterios de aceptación` | `criterios_aceptacion` | Lista de CA |
| `### Reglas de negocio` | `reglas_negocio` | Reglas que el sistema debe cumplir |
| `### Restricciones` | `restricciones` | Limitaciones tecnológicas o de dominio |

La lista **no es cerrada**: P1 acepta cualquier sección con marcador `### ` (su `kind` = el título).
Estas son solo las convenciones para que el servicio externo y P1 coincidan.

---

## 5. Ejemplo completo

```
## Exportar reporte de ventas
Como administrador, quiero exportar el reporte de ventas mensual, para revisar el rendimiento del equipo.

### Criterios de aceptación
- El reporte se genera en formato PDF y CSV.
- Solo el administrador puede exportarlo.

### Reglas de negocio
- El reporte incluye las ventas del mes en curso por defecto.

### Restricciones
- El archivo no puede superar 10 MB.
```

P1 produce de este bloque:

- `role` = "administrador", `objective` = "exportar el reporte de ventas mensual",
  `benefit` = "revisar el rendimiento del equipo"
- `validation_status` = `valid`
- `content_sections` =
  - `{kind: "criterios_aceptacion", text: "- El reporte se genera en formato PDF y CSV.\n- Solo el administrador puede exportarlo."}`
  - `{kind: "reglas_negocio", text: "- El reporte incluye las ventas del mes en curso por defecto."}`
  - `{kind: "restricciones", text: "- El archivo no puede superar 10 MB."}`

---

## 6. Límites y formato

- `max_story_chars` (de `P1Config`) acota la longitud de `original_text`. Un bloque que la supere
  → `valid_with_warnings` con issue `STORY_TOO_LONG` (o se trunca; definir en T-F4-05).
- Formato del archivo: TXT, PDF o DOCX (lo resuelve `DocumentTextExtractor`). El servicio externo
  debe producir texto que, al extraerse, **conserve los marcadores `## ` y `### `** y la línea
  "Como…, quiero…, para…". Si la extracción pierde esos marcadores, P1 marcará todo como
  `UnresolvedFragment` y la generación fallará con `NO_STORIES_FOUND`.
- El texto antes del primer `## ` (preambulo) → `UnresolvedFragment` (no es una HU).

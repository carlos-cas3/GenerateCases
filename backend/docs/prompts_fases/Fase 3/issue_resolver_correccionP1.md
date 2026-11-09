# Corrección de diseño — `SourceDocument` y responsabilidades de P1

> Fase 3 — corrección de inconsistencia detectada al diseñar `DocumentTextExtractor`.
> Este documento describe el problema encontrado, la decisión tomada y los cambios
> que deben realizarse antes de implementar P1 real en Fase 4.
>
> **Estado:** aplicada en Fase 3 la parte de contrato y puertos: `SourceDocument.data: bytes`
> (cambio 1), `DocumentStorage.download()` + `StoredDocumentUnavailable` (prerrequisito para
> que P1 lea el archivo) y `architecture_patterns.md` (cambio 4). Los cambios 2 y 3
> (`NormalizeStage` real y `build_real_stages`) quedan para Fase 4, junto con la segmentación.

---

## Problema detectado

Al diseñar el puerto `DocumentTextExtractor` se identificó una inconsistencia
entre la decisión D-01 del pipeline y el contrato actual de P1.

**La decisión D-01 dice:**
> (a): extraer texto con un puerto previo (no es una etapa) y **segmentar en P1**.

**El contrato actual (`contracts/p1.py`) dice:**
`P1Input` recibe un `SourceDocument` con `text: str` ya extraído:

```python
class SourceDocument(ContractModel):
    document_id: UUID
    filename: str
    file_type: FileType
    text: str  # ← texto ya extraído; alguien externo a P1 lo puso aquí
```

**La contradicción:**

Si `SourceDocument` llega con el texto ya extraído, alguien externo a P1 tuvo
que llamar al extractor antes. Ese "alguien" no está definido en el diseño.
Además, los errores `DOCUMENT_UNREADABLE` y `EMPTY_DOCUMENT` están declarados
como errores de P1, pero si la extracción ocurre fuera de P1, esos errores
no tienen dueño natural y el pipeline no puede registrarlos correctamente
como fallo de etapa.

`PipelineContext` solo tiene `document_id` — no transporta bytes del archivo.
No hay ningún punto en el flujo actual que lea el archivo desde Storage y lo
pase a P1 antes de que esta empiece.

---

## Revisión de patrones aplicables

Antes de implementar esta corrección, revisar `architecture_patterns.md` y
verificar si alguna regla existente aplica directamente o si la corrección
introduce un cambio que debe reflejarse en ese documento.

Puntos concretos a revisar:

**R-PP-3 — Los outputs viajan por el contexto.**
P1 escribe su `P1Output` en `context.p1_output`. La corrección no cambia esto.
Pero sí implica que P1 necesita acceder a `context.document_id` para leer el
archivo desde Storage — lo cual ya está disponible en el contexto.

**R-DI-2 — Los servicios reciben dependencias por constructor.**
La corrección hace que P1 reciba `DocumentStorage` y `DocumentTextExtractor`
por constructor. Esto sigue exactamente esta regla. El ejemplo del documento
de patrones muestra `RequirementsStage` recibiendo `LlmClient` por constructor;
P1 sigue el mismo patrón con sus dos dependencias.

**R-AP-4 — Los adaptadores traducen errores al dominio.**
`DocumentTextExtractor` lanza `DocumentExtractionError`. P1 la captura y la
convierte en `StageError` con código `DOCUMENT_UNREADABLE`. Esta traducción
en dos pasos (librería → error de dominio → error de etapa) sigue la cadena
correcta de responsabilidades.

**Actualización requerida en `architecture_patterns.md`:**
La tabla de "Puertos pendientes" lista `DocumentTextExtractor`. Al implementar,
debe moverse a "Puertos actuales" con sus adaptadores. Verificar también si
la corrección de P1 introduce algún patrón nuevo que deba documentarse, o si
modifica alguna regla existente.

---

## Decisión tomada

**P1 es responsable de leer el archivo y extraer su texto.**

P1 recibe por constructor:
- `DocumentStorage` — para leer los bytes del archivo desde Storage
- `DocumentTextExtractor` — para convertir esos bytes en texto plano

P1 construye el `SourceDocument` internamente antes de armar el `P1Input`.
Cualquier fallo en la lectura o extracción se captura dentro de P1 y se
registra como `StageError` con el código correspondiente.

**Por qué esta opción:**

1. **Responsabilidad única y correcta.** P1 se llama "Procesamiento, segmentación
   y estructuración de HU". Leer el archivo y extraer su texto es parte de esa
   responsabilidad. Delegar esa tarea a un componente externo sin nombre ni
   lugar definido en el diseño rompe esa cohesión.

2. **Los errores caen donde corresponde.** `DOCUMENT_UNREADABLE` y `EMPTY_DOCUMENT`
   son errores declarados de P1. Si la extracción ocurre dentro de P1, P1 puede
   lanzarlos como `StageError` y el orquestador los registra correctamente.

3. **`PipelineContext` no se contamina.** No necesita transportar `document_bytes`
   que solo P1 usa. El contexto sigue siendo el mismo.

4. **Sigue R-DI-2.** P1 recibe sus dependencias por constructor, igual que
   `RequirementsStage` recibirá `LlmClient` en Fase 4.

---

## Cambios requeridos

### 1. `pipeline/contracts/p1.py` — `SourceDocument`

Cambiar `text: str` por `data: bytes`:

```python
class SourceDocument(ContractModel):
    """Archivo crudo recibido del Storage. Lo consume P1 internamente."""
    document_id: UUID
    filename: str
    file_type: FileType
    data: bytes  # ← bytes crudos del archivo; P1 extrae el texto con el extractor
```

> `SourceDocument` pasa a ser un objeto de entrada interno de P1, no un contrato
> compartido entre etapas. El texto extraído vive en memoria dentro de P1 y no
> necesita un campo en el contrato ni en `PipelineContext`.

### 2. `pipeline/stages/p1_normalize.py` — P1 real (Fase 4)

Cuando se implemente P1 real, la etapa debe recibir por constructor:

```python
class NormalizeStage(StageBase):
    key: ClassVar[StageKey] = StageKey.P1

    def __init__(
        self,
        storage: DocumentStorage,
        extractor: DocumentTextExtractor,
        config: P1Config,
    ) -> None:
        self._storage = storage
        self._extractor = extractor
        self._config = config

    async def run(self, context: PipelineContext) -> StageResult | None:
        # 1. Leer bytes desde Storage usando context.document_id
        # 2. Extraer texto con self._extractor
        # 3. Construir SourceDocument internamente
        # 4. Segmentar y estructurar HU
        # 5. Escribir P1Output en context.p1_output
        ...
```

Los errores posibles dentro de `run`:

| Situación | Error |
|---|---|
| Storage no encuentra el archivo | `StageError(code="DOCUMENT_UNREADABLE")` |
| Extractor lanza `DocumentExtractionError` | `StageError(code="DOCUMENT_UNREADABLE")` |
| Texto extraído vacío | `StageError(code="EMPTY_DOCUMENT")` |
| No se encontró ninguna HU segmentable | `StageError(code="NO_STORIES_FOUND")` |

### 3. `main.py` — `build_real_stages` (Fase 4)

Cuando se reemplace `build_stub_stages` por `build_real_stages`, P1 se
construye pasándole sus dependencias:

```python
stages = build_real_stages(
    storage=storage,           # ya disponible en app.state
    extractor=extractor,       # ya disponible en app.state (issue_resolver_extractor.md)
    llm_client=llm,            # ya disponible en app.state
    ...
)
```

### 4. `architecture_patterns.md`

Al implementar, actualizar:
- Mover `DocumentTextExtractor` de "Puertos pendientes" a "Puertos actuales"
- Añadir `DocumentStorage` como dependencia de P1 si la tabla de capas
  no lo refleja correctamente

---

## Implementación sin romper lo existente

Para aplicar esta corrección sin romper el sistema en ningún punto intermedio,
se recomienda el siguiente enfoque. **No es obligatorio** — el implementador
puede elegir otro orden siempre que los tests pasen en cada paso.

**Sugerencia:**

1. Implementar primero todo el extractor (`issue_resolver_extractor.md`)
   hasta tener puerto, adaptadores y fake funcionando con tests en verde
2. Modificar `SourceDocument` en `contracts/p1.py` (`text: str` → `data: bytes`)
3. Verificar que ningún otro módulo usa `SourceDocument.text` directamente
   (hoy no debería, porque P1 es stub); si hay referencias, corregirlas
4. Implementar P1 real con las dependencias por constructor
5. Actualizar `build_real_stages` en `main.py` y `create_app()`
6. Actualizar `architecture_patterns.md`

> ⚠️ **Advertencia:** independientemente del orden que se elija, el sistema
> debe compilar y los tests existentes deben pasar en cada paso intermedio.
> No dejar el sistema en un estado roto entre pasos.
>
> Si un cambio afecta varios archivos a la vez para que todo compile,
> **primero documentar qué se va a cambiar y por qué** antes de tocar
> cualquier archivo. Hacerlos en un único commit atómico y registrar
> en el mensaje del commit qué se cambió y la razón.

---

## Verificación

Al terminar, verificar que la corrección es consistente con el resto del sistema:

- [ ] `SourceDocument.text` ya no existe; ningún módulo lo referencia
- [ ] P1 recibe `DocumentStorage` y `DocumentTextExtractor` por constructor (R-DI-2)
- [ ] Los errores `DOCUMENT_UNREADABLE` y `EMPTY_DOCUMENT` se lanzan como
      `StageError` dentro de P1, no fuera de ella
- [ ] `PipelineContext` no transporta bytes ni texto del archivo
- [ ] El orquestador sigue sin conocer los contratos de ninguna etapa (R-PP-2)
- [ ] `architecture_patterns.md` refleja `DocumentTextExtractor` como puerto activo
- [ ] Los tests existentes siguen pasando
- [ ] Existe al menos un test de integración que verifique el flujo completo:
      `FakeDocumentStorage` → `FakeDocumentExtractor` → P1 → `P1Output`

**Pendiente para Fase 4:**

- Implementar P1 real con segmentación y estructuración de HU
- Resolver D-25 si se decide mejorar la extracción de PDF/DOCX

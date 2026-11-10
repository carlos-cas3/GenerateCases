# Diseño del extractor de texto — `DocumentTextExtractor`

> Fase 3 — prerequisito para implementar P1 real (Fase 4).
> Este documento describe qué construir, por qué y cómo debe encajar con los
> patrones definidos en `architecture_patterns.md`.
>
> **Estado:** implementado (puerto, adaptadores TXT/PDF/DOCX, compuesto por `FileType`,
> fake y cableado en `create_app`). Las decisiones aquí registradas
> están tomadas y no requieren nueva aprobación antes de implementar.

---

## Contexto y necesidad

P1 necesita el texto plano del documento para poder segmentar y estructurar
las historias de usuario. El archivo puede ser `.txt`, `.pdf` o `.docx`.
Cada formato requiere una estrategia de extracción distinta, pero P1 no debe
saber qué formato está procesando — solo debe recibir texto.

Esto requiere un puerto `DocumentTextExtractor` con adaptadores por formato,
siguiendo el mismo patrón Adapter + Dependency Injection que ya usa `LlmClient`.

Los puertos pendientes están declarados en `architecture_patterns.md`,
sección "Puertos pendientes (Fase 4)":

```
| DocumentTextExtractor | clients/extractor.py | P1 |
```

---

## Decisiones

| # | Decisión | Resolución |
|---|---|---|
| D-EXT-1 | ¿Async o sync? | `async` por consistencia con el resto de puertos del sistema. Las librerías son síncronas y trabajan sobre `bytes` en memoria (sin I/O de red), pero el puerto es `async` para no romper la cadena de awaits del pipeline. |
| D-EXT-2 | Librería para PDF | `pdfplumber` (licencia MIT). Extrae texto con buena fidelidad en layouts de una columna. Si en el futuro se necesita leer tablas, detectar posiciones o manejar layouts complejos, ya lo soporta sin cambiar de librería. |
| D-EXT-3 | Librería para DOCX | `python-docx` (licencia MIT). Itera párrafos y extrae texto plano. |
| D-EXT-4 | Librería para TXT | Ninguna. Decodificación `utf-8` con fallback a `latin-1`. Solo stdlib. |
| D-EXT-5 | ¿Factory? | No aplica. R-FA-1 establece que solo se crea una factory cuando un puerto tiene más de un adaptador **seleccionable en producción**. Aquí los tres adaptadores siempre coexisten — el tipo de archivo determina cuál usar en cada llamada, no una variable de entorno. `main.py` instancia el extractor directamente. |
| D-EXT-6 | Alcance v1 PDF/DOCX | Texto plano únicamente. No se procesan encabezados, pies de página, tablas, estilos, viñetas con niveles ni numeración automática (decisión D-25 del diseño del pipeline). En v1 el resultado se trata igual que un TXT. |

---

## Estructura de módulos

```
ai_service/clients/
  extractor.py          ← Puerto: DocumentTextExtractor (Protocol) + FileType ya en common.py
  txt_extractor.py      ← Adaptador TXT (stdlib, sin dependencias externas)
  pdf_extractor.py      ← Adaptador PDF (pdfplumber)
  docx_extractor.py     ← Adaptador DOCX (python-docx)
  extractor_fake.py     ← Fake determinista para tests
```

> **Nota sobre el nombrado:** los adaptadores se separan por tener lógica distinta
> entre sí (cada librería es diferente). Si existe una mejor forma de organizar
> esta separación — por ejemplo, un único adaptador compuesto que delegue
> internamente — se puede realizar. Lo importante es que el puerto
> `DocumentTextExtractor` permanezca como contrato único y que cada estrategia
> de extracción sea reemplazable de forma independiente.

---

## Puerto — `clients/extractor.py`

El puerto define el contrato mínimo. Solo stdlib, sin imports de infraestructura
(R-AP-2). `FileType` ya existe en `pipeline/contracts/common.py`; el puerto
lo importa desde ahí.

```python
# clients/extractor.py

from typing import Protocol
from ai_service.pipeline.contracts.common import FileType


class DocumentTextExtractor(Protocol):
    """Puerto de extracción de texto. Lo implementan los adaptadores por formato
    y el fake de tests. P1 lo recibe por constructor (R-DI-2)."""

    async def extract(self, data: bytes, file_type: FileType) -> str:
        """Extrae texto plano del archivo.
        
        Devuelve string vacío si el archivo no contiene texto extraíble.
        Lanza `DocumentExtractionError` ante fallos irrecuperables de la librería.
        """
        ...
```

---

## Errores de dominio

Añadir en `core/errors.py` antes de implementar los adaptadores:

```python
class DocumentExtractionError(AppError):
    """Fallo al extraer texto del archivo. Lo lanzan los adaptadores; P1 lo captura."""
    code = "DOCUMENT_UNREADABLE"
    default_message = "No se pudo extraer el texto del documento."
```

Los adaptadores traducen excepciones de librería a `DocumentExtractionError`
antes de que salgan (R-AP-4). P1 las captura y las convierte en `StageError`
con el código correspondiente.

---

## Adaptadores

### Estructura común

Cada adaptador sigue el mismo esquema:
1. Recibe `data: bytes` y `file_type: FileType`
2. Aplica la lógica de extracción con su librería
3. Devuelve `str` con el texto plano
4. Traduce excepciones de librería a `DocumentExtractionError` (R-AP-4)

### `clients/txt_extractor.py`

- Sin dependencias externas
- Decodifica `data` como `utf-8`; si falla, reintenta con `latin-1`
- Si ambos fallan → `DocumentExtractionError`

### `clients/pdf_extractor.py`

- Librería: `pdfplumber`
- Abre el PDF desde `bytes` con `pdfplumber.open(io.BytesIO(data))`
- Itera páginas y concatena el texto con `\n` entre páginas
- PDF sin texto extraíble (escaneado, solo imágenes) → devuelve `""`;
  P1 lo rechazará con `EMPTY_DOCUMENT`
- Excepción de librería → `DocumentExtractionError`

### `clients/docx_extractor.py`

- Librería: `python-docx`
- Abre el DOCX desde `bytes` con `docx.Document(io.BytesIO(data))`
- Itera `document.paragraphs` y concatena el texto con `\n`
- Excepción de librería → `DocumentExtractionError`

---

## Fake para tests — `clients/extractor_fake.py`

Siguiendo el patrón de `FakeLlmClient` (R-DI-3):

```python
# clients/extractor_fake.py

class FakeDocumentExtractor:
    """Fake determinista de DocumentTextExtractor para tests.
    
    Devuelve, en orden, los textos con los que se construyó.
    Cada elemento puede ser un str (extracción correcta) o un
    DocumentExtractionError (se lanza al llegar su turno).
    Las llamadas recibidas quedan en `calls` para inspeccionarlas.
    """

    def __init__(self, responses: Iterable[str | DocumentExtractionError] = ()) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[bytes, FileType]] = []

    async def extract(self, data: bytes, file_type: FileType) -> str:
        self.calls.append((data, file_type))
        if not self._responses:
            raise AssertionError("FakeDocumentExtractor: no quedan respuestas programadas.")
        item = self._responses.pop(0)
        if isinstance(item, DocumentExtractionError):
            raise item
        return item
```

---

## Inyección en `main.py`

No aplica factory (D-EXT-5). `main.py` instancia el extractor directamente
en el `lifespan` y lo inyecta en P1 por constructor cuando se implemente
`build_real_stages` (Fase 4).

`create_app()` recibe el extractor como parámetro opcional para que los tests
puedan inyectar `FakeDocumentExtractor` sin tocar las librerías reales (R-DI-4):

```python
def create_app(
    ...
    extractor: DocumentTextExtractor | None = None,
) -> FastAPI:
    ...
    # en lifespan:
    _extractor = extractor
    if _extractor is None:
        from ai_service.clients.txt_extractor import TxtDocumentExtractor
        from ai_service.clients.pdf_extractor import PdfDocumentExtractor
        from ai_service.clients.docx_extractor import DocxDocumentExtractor
        _extractor = ...  # composición de los tres adaptadores
    app.state.extractor = _extractor
```

> La forma exacta de componer los tres adaptadores (un objeto coordinador,
> un dict por `FileType`, u otra estrategia) se decide al implementar.
> Lo importante es que el resultado cumpla el puerto `DocumentTextExtractor`.

---

## Implementación sin romper lo existente

Al implementar este diseño se recomienda seguir este orden para no romper
el sistema en ningún punto intermedio. **No es obligatorio** — el implementador
puede elegir otro orden siempre que el sistema compile y los tests pasen en
cada paso.

**Sugerencia:**

1. Añadir `DocumentExtractionError` en `core/errors.py`
2. Crear el puerto `clients/extractor.py` (sin dependencias externas)
3. Crear el fake `clients/extractor_fake.py` (permite escribir tests ya)
4. Implementar `clients/txt_extractor.py` (sin librerías nuevas, el más simple)
5. Implementar `clients/pdf_extractor.py` (añadir `pdfplumber` a `requirements.txt`)
6. Implementar `clients/docx_extractor.py` (añadir `python-docx` a `requirements.txt`)
7. Actualizar `main.py` y `create_app()` con el parámetro opcional `extractor`
8. Actualizar `architecture_patterns.md`: mover `DocumentTextExtractor` de
   "Puertos pendientes" a "Puertos actuales"

---

## Verificación

Al terminar la implementación, verificar:

- [ ] El puerto (`clients/extractor.py`) no importa `pdfplumber`, `docx` ni ninguna librería externa (R-AP-2)
- [ ] Cada adaptador vive en su propio módulo separado del puerto (R-AP-1)
- [ ] Los adaptadores traducen todas las excepciones de librería a `DocumentExtractionError` antes de que salgan (R-AP-4)
- [ ] El fake se inyecta por constructor en los tests; no existe un caso `"fake"` en ninguna factory (R-FA-6)
- [ ] `create_app()` acepta `extractor` como parámetro opcional (R-DI-4)
- [ ] Los tests existentes siguen pasando sin modificación
- [ ] Existe al menos un test por adaptador que verifique extracción correcta y traducción de error

**Pendiente para Fase 4:**

- Implementar P1 real recibiendo `DocumentStorage` y `DocumentTextExtractor` por constructor
  (ver `issue_resolver_correccionP1.md`)
- Resolver D-25: reglas específicas de PDF y DOCX (viñetas, estilos, tablas) cuando
  los requisitos de calidad lo justifiquen

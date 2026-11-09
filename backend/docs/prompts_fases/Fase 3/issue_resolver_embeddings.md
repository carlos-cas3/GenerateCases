# Diseño del cliente de embeddings y clustering — `EmbeddingsClient` y `ClusteringClient`

> **Propuesta de diseño — guía de implementación**
>
> Este documento es una propuesta técnica elaborada ante la ausencia de implementación
> real de los clientes de embeddings y clustering en el proyecto. Su propósito es
> servir de referencia completa para quien vaya a construirlos: consolida las
> decisiones de diseño, los contratos de los puertos, los patrones que debe seguir
> cada pieza y los problemas conocidos que deben resolverse durante la implementación.
>
> Leer este documento de principio a fin antes de escribir código. Las decisiones
> aquí registradas están tomadas; lo que queda pendiente está marcado explícitamente.

---

> Fase 3 — prerequisito para implementar P3 y P4 reales (Fase 5).
> Este documento describe qué construir, por qué y cómo debe encajar con los
> patrones definidos en `architecture_patterns.md`.
> La intención y estructura de este documento es consistente con `llm_client_design.md`:
> ambos definen un puerto, adaptadores intercambiables, una factory y un fake determinista.
>
> **Estado:** pendiente de implementación. Las decisiones aquí registradas
> están tomadas y no requieren nueva aprobación antes de implementar.

---

## Contexto y necesidad

P3 necesita convertir los RF extraídos por P2 en vectores numéricos (embeddings)
para que P4 pueda agruparlos semánticamente. P4 aplica un algoritmo de clustering
sobre esos vectores para producir los grupos que P5 usará como unidades de generación.

El proveedor de embeddings es configurable por variable de entorno — igual que
el LLM. En v1 se usa un modelo local (`sentence-transformers`), pero la
arquitectura debe permitir cambiar a un proveedor remoto (por ejemplo OpenAI)
sin tocar las etapas.

El algoritmo de clustering en v1 es HDBSCAN porque no exige fijar el número
de clusters de antemano — el número varía según los datos. La arquitectura
permite experimentar con otros algoritmos sin tocar P4.

Estos puertos están declarados en `architecture_patterns.md`,
sección "Puertos pendientes (Fase 4)":

```
| EmbeddingsClient    | clients/embeddings.py    | P3 |
```

`ClusteringClient` no estaba declarado aún — se añade en este documento y debe
registrarse en `architecture_patterns.md` al implementar.

---

## Decisiones

| # | Decisión | Resolución |
|---|---|---|
| D-EMB-1 | Nombre del puerto de embeddings | `EmbeddingsClient` en `clients/embeddings.py`, consistente con `LlmClient` en `clients/llm.py`. El diseño del pipeline lo llamaba `EmbeddingGenerator`; ese nombre queda obsoleto. |
| D-EMB-2 | ¿Proveedor configurable? | Sí, mediante variable de entorno `EMBEDDINGS_PROVIDER`. Misma lógica que `LLM_PROVIDER`. En v1 el valor es `"local"` (`sentence-transformers`, modelo `all-mpnet-base-v2`). |
| D-EMB-3 | Modelo local v1 | `all-mpnet-base-v2` vía `sentence-transformers` (Apache 2.0). Produce vectores de 768 dimensiones normalizados. Sin API remota ni credenciales. |
| D-EMB-4 | Adaptador remoto | `OpenAIEmbeddingsClient` como segundo adaptador documentado, para uso futuro o pruebas con API. Requiere `EMBEDDINGS_API_KEY` cuando `EMBEDDINGS_PROVIDER=openai`. |
| D-EMB-5 | ¿Factory? | Sí, aplica R-FA-1: hay más de un adaptador seleccionable en producción. `EmbeddingsClientFactory` en `clients/embeddings_factory.py`, igual que `LlmClientFactory`. |
| D-EMB-6 | Async | `async` por consistencia con el resto de puertos. `sentence-transformers` es síncrono; el adaptador local usa `asyncio.to_thread` igual que los repositorios de Supabase. |
| D-CLU-1 | Puerto de clustering | `ClusteringClient` en `clients/clustering.py`. Permite experimentar con diferentes algoritmos sin modificar P4. |
| D-CLU-2 | Algoritmo v1 | HDBSCAN: no exige fijar el número de clusters, que varía según los datos. Librería `hdbscan` (BSD). |
| D-CLU-3 | ¿Factory de clustering? | Sí, misma lógica. `ClusteringClientFactory` en `clients/clustering_factory.py`. Variable de entorno `CLUSTERING_ALGORITHM` con valor inicial `"hdbscan"`. |
| D-CLU-4 | ¿Bloqueante si clustering falla? | No bloqueante en la factory/construcción. P4 ya es bloqueante como etapa (su fallo detiene el pipeline). La factory solo lanza `ConfigurationError` si el algoritmo no es reconocido. |

---

## Estructura de módulos

```
ai_service/clients/
  embeddings.py             ← Puerto: EmbeddingsClient (Protocol) + DTOs EmbeddingsRequest / EmbeddingsResponse
  embeddings_factory.py     ← EmbeddingsClientFactory.create(settings) → EmbeddingsClient
  local_embeddings.py       ← Adaptador local: sentence-transformers (v1)
  openai_embeddings.py      ← Adaptador remoto: OpenAI text-embedding-* (futuro/pruebas)
  embeddings_fake.py        ← Fake determinista para tests

  clustering.py             ← Puerto: ClusteringClient (Protocol) + DTOs ClusteringRequest / ClusteringResult
  clustering_factory.py     ← ClusteringClientFactory.create(settings) → ClusteringClient
  hdbscan_clustering.py     ← Adaptador HDBSCAN (v1)
  clustering_fake.py        ← Fake determinista para tests
```

---

## Puerto de embeddings — `clients/embeddings.py`

Solo stdlib y tipos propios. Sin imports de infraestructura (R-AP-2).

```python
# clients/embeddings.py

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class EmbeddingsRequest:
    """Solicitud de vectorización. La construye P3 a partir de los RF y su P3Config."""

    texts: tuple[str, ...]        # textos a vectorizar (uno por RF)
    model: str                    # modelo concreto; viene de P3Config
    input_template: str | None = None  # plantilla opcional de preprocesado
    normalize: bool = True        # normalizar L2 los vectores resultantes
    # Parámetros adicionales específicos del proveedor
    extra: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EmbeddingsResponse:
    """Respuesta del proveedor. Un vector por texto, en el mismo orden."""

    vectors: tuple[tuple[float, ...], ...]  # un vector por texto de entrada
    model_name: str                         # nombre exacto del modelo usado
    model_version: str | None               # versión si el proveedor la expone
    dimension: int                          # dimensión de cada vector
    normalized: bool                        # si los vectores están normalizados


class EmbeddingsClient(Protocol):
    """Puerto de generación de embeddings. Lo implementan los adaptadores y el fake."""

    async def embed(self, request: EmbeddingsRequest) -> EmbeddingsResponse:
        """Vectoriza los textos. Lanza `EmbeddingsError` ante fallos."""
        ...

    async def aclose(self) -> None:
        """Libera recursos. `main.py` lo llama al apagar (R-FA-7)."""
        ...
```

---

## Puerto de clustering — `clients/clustering.py`

```python
# clients/clustering.py

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ClusteringRequest:
    """Solicitud de clustering. La construye P4 a partir de P3Output y P4Config."""

    vectors: tuple[tuple[float, ...], ...]  # vectores a agrupar (uno por RF)
    codes: tuple[str, ...]                  # código RF correspondiente a cada vector
    metric: str                             # métrica de distancia (cosine, euclidean...)
    # Parámetros específicos del algoritmo (min_cluster_size, min_samples, etc.)
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ClusteringResult:
    """Resultado del clustering. Un label por vector; -1 indica outlier (sin cluster)."""

    labels: tuple[int, ...]     # label por vector, en el mismo orden que la solicitud
    algorithm: str              # nombre del algoritmo aplicado
    metric: str                 # métrica usada
    params: dict[str, Any]      # parámetros efectivos aplicados


class ClusteringClient(Protocol):
    """Puerto de clustering semántico. Lo implementan los adaptadores y el fake."""

    async def cluster(self, request: ClusteringRequest) -> ClusteringResult:
        """Agrupa los vectores. Lanza `ClusteringError` ante fallos."""
        ...

    async def aclose(self) -> None:
        """Libera recursos. `main.py` lo llama al apagar."""
        ...
```

---

## Errores de dominio

Añadir en `core/errors.py` antes de implementar los adaptadores:

```python
class EmbeddingsError(AppError):
    """Fallo en la generación de embeddings. Los adaptadores lo lanzan; P3 lo captura."""
    code = "EMBEDDING_PROVIDER_UNAVAILABLE"
    default_message = "Falló la generación de embeddings."

class EmbeddingsDimensionError(EmbeddingsError):
    """Los vectores devueltos tienen una dimensión distinta a la esperada."""
    code = "EMBEDDING_DIMENSION_MISMATCH"
    default_message = "Los vectores devueltos tienen una dimensión inesperada."

class EmbeddingsInvalidVectorError(EmbeddingsError):
    """Un vector contiene NaN o valores infinitos."""
    code = "EMBEDDING_INVALID_VECTOR"
    default_message = "El proveedor devolvió un vector con valores no válidos."

class ClusteringError(AppError):
    """Fallo en el clustering. Los adaptadores lo lanzan; P4 lo captura."""
    code = "CLUSTERING_ERROR"
    default_message = "Falló el algoritmo de clustering."
```

Los adaptadores traducen excepciones de librería a estos tipos (R-AP-4).
P3 y P4 los capturan y los convierten en `StageError`.

---

## Adaptadores de embeddings

### Estructura común

Cada adaptador sigue el mismo esquema que los adaptadores LLM:
1. Recibe el cliente de librería ya construido por constructor (factory lo crea)
2. Traduce `EmbeddingsRequest` → llamada de librería
3. Traduce respuesta → `EmbeddingsResponse`
4. Captura excepciones de librería → lanza `EmbeddingsError` o subtipo (R-AP-4)

### `clients/local_embeddings.py` — v1

- Librería: `sentence-transformers`
- Modelo v1: `all-mpnet-base-v2` (768 dimensiones, normalizado)
- Carga el modelo por constructor; la factory lo construye con el nombre de modelo
  que venga de `Settings.embeddings_model`
- Procesa en batches según `EmbeddingsRequest.extra.get("batch_size")`
- Al ser síncrono, usa `asyncio.to_thread` en `embed()` para no bloquear el
  bucle de eventos
- Error de carga del modelo o vectorización → `EmbeddingsError`
- Dimensión distinta a la esperada → `EmbeddingsDimensionError`
- Vector con NaN o infinitos → `EmbeddingsInvalidVectorError`
- `aclose()` es no-op (el modelo no mantiene conexiones)

### `clients/openai_embeddings.py` — futuro/pruebas

- Librería: `openai` (ya en `requirements.txt`)
- Método: `client.embeddings.create(model=..., input=[...])`
- Requiere `EMBEDDINGS_API_KEY` (puede reutilizar `LLM_API_KEY` si el proveedor
  es el mismo, o tener su propia variable — se decide al implementar)
- Errores a traducir: `RateLimitError` → `EmbeddingsError`;
  respuesta con dimensión distinta → `EmbeddingsDimensionError`;
  vector con NaN/inf → `EmbeddingsInvalidVectorError`
- `aclose()` cierra el cliente async

---

## Adaptadores de clustering

### `clients/hdbscan_clustering.py` — v1

- Librería: `hdbscan` (BSD)
- Recibe el cliente ya construido por constructor (parámetros base desde `Settings`)
- Traduce `ClusteringRequest` → llamada a `hdbscan.HDBSCAN(...).fit_predict(vectors)`
- Label `-1` en el resultado = outlier = RF sin cluster asignado
- Error de librería → `ClusteringError`
- `aclose()` es no-op

---

## Factories

### `clients/embeddings_factory.py`

Misma lógica que `LlmClientFactory` (R-FA-2, R-FA-3, R-FA-4, R-FA-5):

```python
class EmbeddingsClientFactory:
    """Construye el EmbeddingsClient correcto según Settings.embeddings_provider.
    Solo main.py llama a esta factory (R-FA-5)."""

    @staticmethod
    def create(settings: Settings) -> EmbeddingsClient:
        match settings.embeddings_provider:
            case "local":
                from sentence_transformers import SentenceTransformer
                from ai_service.clients.local_embeddings import LocalEmbeddingsClient
                return LocalEmbeddingsClient(
                    SentenceTransformer(settings.embeddings_model)
                )
            case "openai":
                from openai import AsyncOpenAI
                from ai_service.clients.openai_embeddings import OpenAIEmbeddingsClient
                return OpenAIEmbeddingsClient(
                    AsyncOpenAI(
                        api_key=_require_embeddings_api_key(settings),
                        timeout=settings.embeddings_timeout_seconds,
                        max_retries=0,
                    )
                )
            case _:
                raise ConfigurationError(
                    f"Proveedor de embeddings no soportado: {settings.embeddings_provider!r}. "
                    "Valores válidos: local, openai."
                )
```

### `clients/clustering_factory.py`

```python
class ClusteringClientFactory:
    """Construye el ClusteringClient correcto según Settings.clustering_algorithm."""

    @staticmethod
    def create(settings: Settings) -> ClusteringClient:
        match settings.clustering_algorithm:
            case "hdbscan":
                from ai_service.clients.hdbscan_clustering import HDBSCANClusteringClient
                return HDBSCANClusteringClient()
            case _:
                raise ConfigurationError(
                    f"Algoritmo de clustering no soportado: {settings.clustering_algorithm!r}. "
                    "Valores válidos: hdbscan."
                )
```

---

## Fakes para tests

### `clients/embeddings_fake.py`

Siguiendo el patrón de `FakeLlmClient`:

```python
class FakeEmbeddingsClient:
    """Fake determinista de EmbeddingsClient para tests.

    Devuelve, en orden, las respuestas con las que se construyó.
    Cada elemento puede ser un EmbeddingsResponse o un EmbeddingsError
    (se lanza al llegar su turno). Las solicitudes recibidas quedan
    en `requests` para inspeccionarlas.
    """

    def __init__(self, responses: Iterable[EmbeddingsResponse | EmbeddingsError] = ()) -> None:
        self._responses = list(responses)
        self.requests: list[EmbeddingsRequest] = []
        self.closed = False

    async def embed(self, request: EmbeddingsRequest) -> EmbeddingsResponse:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("FakeEmbeddingsClient: no quedan respuestas programadas.")
        item = self._responses.pop(0)
        if isinstance(item, EmbeddingsError):
            raise item
        return item

    async def aclose(self) -> None:
        self.closed = True
```

### `clients/clustering_fake.py`

Mismo patrón con `ClusteringResult` y `ClusteringError`.

---

## Variables de entorno — `config.py`

```python
# Proveedor de embeddings
embeddings_provider: Literal["local", "openai"] = "local"

# Modelo (nombre exacto para sentence-transformers o OpenAI)
embeddings_model: str = "all-mpnet-base-v2"

# API key para proveedores remotos (None si es local)
embeddings_api_key: SecretStr | None = None

# Timeout para proveedores remotos
embeddings_timeout_seconds: float = Field(default=60.0, gt=0)

# Algoritmo de clustering
clustering_algorithm: Literal["hdbscan"] = "hdbscan"
```

La validación de credenciales (si `embeddings_provider=openai` y falta
`embeddings_api_key`) vive en la factory, no en `Settings` — igual que
`LlmClientFactory` (ver `llm_client_design.md`).

---

## Inyección en `main.py`

Siguiendo R-DI-4, `create_app()` gana dos parámetros opcionales:

```python
def create_app(
    ...
    embeddings_client: EmbeddingsClient | None = None,
    clustering_client: ClusteringClient | None = None,
) -> FastAPI:
```

En el `lifespan`:
- Si no se inyectan, se construyen con sus factories (imports lazy, R-FA-3)
- Se guardan en `app.state` para inyectarlos en P3 y P4 al construir
  `build_real_stages` en Fase 5
- Al apagar, se cierran con `aclose()` solo si los construyó la factory (R-FA-7)

Los tests inyectan `FakeEmbeddingsClient` y `FakeClusteringClient` directamente,
sin pasar por las factories (R-FA-6).

---

## Revisión y actualización de `architecture_patterns.md`

Antes de implementar, revisar `architecture_patterns.md` completo y verificar:

- Si alguna regla existente aplica directamente a este diseño y no se está
  respetando — corregirlo antes de continuar.
- Si el diseño introduce un patrón nuevo que no está documentado — añadirlo
  como sección o regla nueva antes de implementar el código que lo usa.
  No dejar un patrón nuevo sin documentar: otro agente o desarrollador que
  lea el código no sabrá por qué se hizo así.

Al implementar, realizar los siguientes cambios confirmados en `architecture_patterns.md`:

1. Mover `EmbeddingsClient` de "Puertos pendientes" a "Puertos actuales"
2. Añadir `ClusteringClient` a "Puertos actuales" (no estaba declarado)
3. Añadir `EmbeddingsClientFactory` y `ClusteringClientFactory` a la
   sección del Factory Pattern (sección 6), igual que `LlmClientFactory`
4. Verificar que la tabla de capas (sección 7) refleja que las etapas P3 y P4
   solo importan los puertos, nunca los adaptadores concretos

---

## Implementación sin romper lo existente

Para aplicar este diseño sin romper el sistema en ningún punto intermedio,
se recomienda el siguiente orden. **No es obligatorio** — el implementador
puede elegir otro siempre que los tests pasen en cada paso.

> ⚠️ **Advertencia:** si un cambio afecta varios archivos a la vez,
> **primero documentar qué se va a cambiar y por qué** antes de tocar
> cualquier archivo. No dejar el sistema en un estado roto entre pasos.

**Sugerencia:**

1. Añadir errores en `core/errors.py` (`EmbeddingsError` y subtipos, `ClusteringError`)
2. Crear puerto `clients/embeddings.py` (sin dependencias externas)
3. Crear puerto `clients/clustering.py` (sin dependencias externas)
4. Crear fakes `clients/embeddings_fake.py` y `clients/clustering_fake.py`
5. Añadir variables de entorno en `config.py`
6. Implementar `clients/local_embeddings.py` (añadir `sentence-transformers` a `requirements.txt`)
7. Implementar `clients/hdbscan_clustering.py` (añadir `hdbscan` a `requirements.txt`)
8. Implementar `clients/embeddings_factory.py`
9. Implementar `clients/clustering_factory.py`
10. Actualizar `main.py` con los parámetros opcionales y la construcción en `lifespan`
11. Actualizar `architecture_patterns.md`

---

## Problemas conocidos — a resolver durante la implementación

Esta sección documenta inconsistencias y omisiones detectadas en la propuesta.
Deben corregirse antes de cerrar la implementación.

---

### P-1 🔴 `_require_embeddings_api_key` no está definida

El snippet de `EmbeddingsClientFactory` llama a `_require_embeddings_api_key(settings)`
pero la función nunca se define en este documento. En `llm_factory.py` existe el
equivalente `_require_api_key(settings)`. Al implementar `embeddings_factory.py`,
añadir esta función privada al final del módulo:

```python
def _require_embeddings_api_key(settings: Settings) -> str:
    if settings.embeddings_api_key is None:
        raise ConfigurationError(
            "EMBEDDINGS_API_KEY es obligatoria cuando EMBEDDINGS_PROVIDER=openai."
        )
    return settings.embeddings_api_key.get_secret_value()
```

---

### P-2 ⚠️ `dict` mutable en `frozen=True` — añadir comentario aclaratorio

`EmbeddingsRequest.extra`, `ClusteringRequest.params` y `ClusteringResult.params`
son campos `dict` dentro de dataclasses con `frozen=True`. `frozen` impide reasignar
el atributo pero no impide mutar el dict por dentro — el objeto no es realmente
inmutable. El proyecto ya acepta este trade-off en `LlmRequest.extra`, que incluye
el comentario:

```python
# dict: `frozen` no lo hace inmutable por dentro.
```

Al implementar los puertos, replicar ese comentario en todos los campos `dict`
de `EmbeddingsRequest`, `ClusteringRequest` y `ClusteringResult` para que quede
explícito que es una decisión consciente, no un descuido.

---

### P-3 ⚠️ Asimetría entre `ClusteringRequest.params` y `ClusteringResult.params`

`ClusteringRequest.params` tiene `field(default_factory=dict)` — es opcional.
`ClusteringResult.params` no tiene valor por defecto — es obligatorio.

La asimetría es intencional: el resultado siempre debe devolver los parámetros
efectivos que usó el algoritmo (no puede ser vacío sin más). El adaptador HDBSCAN
debe construir `ClusteringResult` pasando siempre `params` explícitamente con los
valores reales usados. Al implementar, asegurarse de que el adaptador recoge los
parámetros efectivos de la instancia HDBSCAN después del ajuste, no solo los que
venían en la solicitud.

---

### P-4 ⚠️ `FakeEmbeddingsClient` recibe objetos completos, no strings

`FakeLlmClient` recibe `str | LlmError` y envuelve el string en `LlmResponse`
internamente. `FakeEmbeddingsClient` no puede hacer lo mismo porque
`EmbeddingsResponse` requiere campos que no pueden inferirse de un string
(dimensión, modelo, vectores reales).

Por eso `FakeEmbeddingsClient` recibe `EmbeddingsResponse | EmbeddingsError`
directamente — el test construye el objeto completo. Esto es correcto y no es
un error; la diferencia con `FakeLlmClient` es una consecuencia de la riqueza
del tipo de respuesta, no una inconsistencia de diseño. `FakeClusteringClient`
sigue el mismo patrón por la misma razón.

Al escribir los tests, usar helpers de factoría para construir
`EmbeddingsResponse` y `ClusteringResult` de prueba y evitar repetición.

---

### P-5 ⚠️ `EmbeddingsDimensionError` y `EmbeddingsInvalidVectorError` — cómo pasar contexto

Los subtipos de `EmbeddingsError` no especifican cómo incluir contexto útil
(dimensión esperada vs recibida, índice del vector inválido, etc.). `AppError`
expone el parámetro `details: dict | list | None` para eso. Al implementar los
adaptadores, usar `details` para incluir información diagnóstica:

```python
# Dentro del adaptador local, al detectar dimensión incorrecta:
raise EmbeddingsDimensionError(
    details={"expected": expected_dim, "received": actual_dim}
)

# Al detectar un vector con NaN/inf:
raise EmbeddingsInvalidVectorError(
    details={"vector_index": idx, "reason": "contains NaN"}
)
```

No codificar esos valores solo en el `message` — `details` es el lugar estructurado
que `api/errors.py` puede serializar hacia el cliente si fuera necesario.

---

### P-6 ℹ️ Firma completa de `create_app()` con los nuevos parámetros

El documento indica que `create_app()` "gana dos parámetros opcionales" pero
no muestra la firma completa con los existentes. La firma final debe ser:

```python
def create_app(
    settings: Settings | None = None,
    *,
    generations_repository: GenerationsRepository | None = None,
    documents_repository: DocumentsRepository | None = None,
    documents_storage: DocumentStorage | None = None,
    llm_client: LlmClient | None = None,
    embeddings_client: EmbeddingsClient | None = None,
    clustering_client: ClusteringClient | None = None,
) -> FastAPI:
```

Los dos nuevos parámetros van al final, después de `llm_client`, para no romper
ninguna llamada existente que use argumentos posicionales.

---

### P-7 ℹ️ R-DI-3 ya anticipaba este fake — citarlo

`architecture_patterns.md` sección 3 (R-DI-3) menciona explícitamente:

> "Cuando se añada `EmbeddingsClient`, su fake debe vivir en `tests/` o en un
> módulo `*_fake.py` al lado del puerto."

La ubicación propuesta en este documento (`clients/embeddings_fake.py`) cumple
con esa regla. Al actualizar `architecture_patterns.md` (paso 11 del orden de
implementación), actualizar también R-DI-3 para referenciar
`clients/embeddings_fake.py` y `clients/clustering_fake.py` por nombre, igual
que ya referencia `clients/llm_fake.py`.

---

## Verificación

- [ ] `clients/embeddings.py` y `clients/clustering.py` no importan ninguna librería externa (R-AP-2)
- [ ] Cada adaptador vive en su propio módulo separado del puerto (R-AP-1)
- [ ] Los adaptadores traducen todas las excepciones de librería a errores de dominio (R-AP-4)
- [ ] Solo `main.py` importa las factories; ninguna etapa las importa (R-FA-5)
- [ ] Imports lazy en ambas factories (R-FA-3)
- [ ] Proveedor o algoritmo desconocido → `ConfigurationError` (R-FA-4)
- [ ] Los fakes se inyectan por constructor; no existe `"fake"` en ninguna factory (R-FA-6)
- [ ] `create_app()` acepta `embeddings_client` y `clustering_client` opcionales (R-DI-4)
- [ ] `aclose()` se llama al apagar solo para los clientes que construyó la factory (R-FA-7)
- [ ] Los tests existentes siguen pasando
- [ ] Existe al menos un test por adaptador que verifique vectorización correcta,
      agrupamiento correcto y traducción de errores

**Pendiente para Fase 5:**

- Implementar `EmbeddingsStage.run()` (P3) recibiendo `EmbeddingsClient` por constructor
- Implementar `ClusteringStage.run()` (P4) recibiendo `ClusteringClient` por constructor
- Resolver configuración de `min_cluster_size` y `min_samples` de HDBSCAN en `P4Config`
- Decidir si `embeddings_api_key` reutiliza `llm_api_key` cuando el proveedor es OpenAI
  en ambos, o si tiene su propia variable independiente

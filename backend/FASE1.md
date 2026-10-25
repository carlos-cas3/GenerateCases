# Backend TestGen — Fase 1: generaciones con pipeline simulado

Flujo vertical para crear, seguir y eliminar generaciones (`generations` + `generation_stages`).
Las etapas P1–P7 se ejecutan en segundo plano con lógica **simulada** (`asyncio.sleep`): no hay LLM,
embeddings, extracción de requisitos ni casos reales. Fuente de verdad: `README.md`, `database.md`,
`pipeline-orchestration.md` y `docs/openapi.yaml`.

## 1. Supuestos y discrepancias

Cuando hubo contradicciones o huecos se aplicó la opción más conservadora:

### Estructura y configuración

| # | Tema | Decisión |
|---|---|---|
| 1 | Ruta de configuración | La tarea pide `ai_service/config.py`; el README §2.6 dice `core/config.py`. Se siguió la tarea. |
| 2 | Dependencias HTTP | La tarea pide `api/dependencies.py`; el README dice `api/deps.py`. Se siguió la tarea. Los errores se ubicaron según el README: `core/errors.py` (dominio) y `api/errors.py` (HTTP). |
| 3 | Ubicación de los documentos | El README cita `docs/database.md` y `docs/pipeline-orchestration.md`, pero esos archivos están en la raíz de `backend/`. No se movieron. |
| 4 | **Variables nuevas** | `PIPELINE_STUB_DELAY_SECONDS` (por defecto 2), `PIPELINE_STUB_FAIL_AT_STAGE` (opcional, `p1`–`p7`; vacía = sin fallo) y `DEFAULT_METHOD_TYPE` (por defecto `llm_pipeline`) no figuran en el README §8. `SUPABASE_STORAGE_BUCKET` y `MAX_UPLOAD_SIZE_BYTES` no se usan en esta fase y no se definieron. |
| 5 | `method_type` por defecto | `llm_pipeline` se tomó del ejemplo de openapi.yaml. Los valores admitidos siguen pendientes, así que se acepta cualquier string. |
| 6 | Credenciales ausentes | Si faltan `SUPABASE_URL` o `SUPABASE_SERVICE_ROLE_KEY`, el arranque falla con `ConfigurationError`. El README admite un modo de desarrollo sin credenciales, pero no define ninguna variable de modo, así que no se inventó una. |
| 7 | Módulos extra | `core/time.py` (`utc_now`), `schemas/records.py` (filas internas, separadas de los modelos HTTP según el README §2.6) y `schemas/common.py` (Health y Error). |
| 8 | Dependencias de test extra | `pyyaml`, `jsonschema` y `rfc3339-validator`, necesarias para el test de contrato contra openapi.yaml. |

### Contrato HTTP

| # | Tema | Decisión |
|---|---|---|
| 9 | `details` siempre presente | Los ejemplos 404/409 de openapi.yaml no incluyen `details`. La tarea exige el campo siempre, así que se envía `{}`. Es válido según el esquema, donde `details` es opcional. |
| 10 | Validación estricta | Se rechazan con 400 `configuration: null`, `method_type: null` y `semantic_clustering_enabled` no booleano (p. ej. `"si"`), porque el contrato los tipa como objeto, string y boolean sin `null`. |
| 11 | 404/405 de rutas inexistentes | No hay código de error en el contrato para una ruta desconocida, así que se mantiene la respuesta por defecto de FastAPI (`{"detail": ...}`) en lugar de inventar uno. El formato común se aplica a todos los endpoints definidos. |
| 12 | `summary` | Es siempre `null` en la Fase 1, incluso en `completed`: no existen datos persistidos que contar. |
| 13 | `/events` | Responde 501 sin comprobar que la generación exista; el contrato solo define 501. El UUID sí se valida (400). |
| 14 | 503 / concurrencia | No se implementaron `AI_SERVICE_UNAVAILABLE` ni el límite de generaciones activas (decisiones pendientes). |
| 15 | Desempate del orden | El listado se ordena por `created_at desc, id desc` para que la paginación sea estable. |

### Pipeline y estados

| # | Tema | Decisión |
|---|---|---|
| 16 | `stage_failed` frente a `pipeline_failed` | pipeline-orchestration.md §5 guarda el `error_message` de la generación en `stage_failed`; la tarea lo hace en `pipeline_failed`. Se escribe en `pipeline_failed`, junto con `status=failed` y `completed_at`, en **una sola escritura con guarda**. Así nunca hay una generación `running` con `error_message`. |
| 17 | **Mensajes seguros (inventados)** | El contrato no los define. Etapa: `La etapa '<nombre>' falló durante la ejecución.` Generación: `La generación falló en la etapa '<nombre>'.` Error no previsto: `La generación falló por un error interno.` (etapa: `La etapa se interrumpió por un error interno.`). Reinicio: `Ejecución interrumpida por reinicio del servicio.` (texto de la tarea). El detalle técnico va solo al log. |
| 18 | Recuperación al arrancar | La etapa `running` pasa a `failed` con el mismo mensaje de interrupción y `completed_at`; los documentos no definen su `error_message`. Una generación `queued` no tiene etapa `running`, así que sus siete etapas quedan `pending`. |
| 19 | Error no previsto en el pipeline | Además de la generación, se marca `failed` su etapa `running`, por coherencia con la recuperación. Si esa escritura también falla, se registra en el log y la generación queda para la recuperación del siguiente arranque. |
| 20 | Escrituras de estado fallidas | Cualquier excepción del repositorio (incluida `InvalidStateTransition`) detiene el orquestador y se trata como fallo de la generación. No se asume que el estado quedó registrado. |
| 21 | `pipeline_completed` | Antes de marcar `completed` se relee la generación y se exige que existan siete etapas en `completed` o `skipped`. |
| 22 | **Un único proceso** | La recuperación de arranque asume que nada activo sigue vivo. Con `uvicorn --workers N` o varias réplicas, un worker que arranca marcaría `failed` las ejecuciones vivas de otro. Se debe ejecutar con **un solo worker** hasta tener una cola durable. |
| 23 | Ejecución en segundo plano | Se usa `BackgroundTasks` (no `asyncio.create_task`), así que no hace falta conservar referencias a tareas. No es durable: un reinicio pierde la tarea, que luego se recupera como `failed`. |
| 24 | `mark_interrupted` | Son tres llamadas PostgREST (leer ids activos, etapas `running` → `failed`, generaciones → `failed` con guarda), no una RPC: la tarea solo pide dos funciones SQL. Si el proceso cae entre medias, el siguiente arranque termina el trabajo. |
| 25 | `config_snapshot` | Contiene solo `semantic_clustering_enabled` y `method_type` efectivos (decisión 6 de database.md, pendiente). |

### Base de datos

| # | Tema | Decisión |
|---|---|---|
| 26 | Nulabilidad | database.md no la indica. Se puso `NOT NULL` en lo que openapi.yaml marca como obligatorio y en `generations.method_type`, que la API tipa como string no nulo y siempre recibe un valor por defecto. |
| 27 | FK compuestas | Para referenciar `(generation_id, id)` se añadió `UNIQUE (generation_id, id)` en `user_stories`, `functional_requirements`, `clusters` y `test_cases`. |
| 28 | Restricciones extra | `stage_order = número de stage_key` (CHECK), `UNIQUE (test_case_id, step_number)`, `step_number > 0` y unicidad de códigos por ejecución (database.md §5). |
| 29 | Borrado | Todas las tablas dependientes hacen `ON DELETE CASCADE` desde `generations`, directamente o por FK compuesta. `generations.document_id` usa `ON DELETE RESTRICT`. |
| 30 | Seguridad | RLS activado sin políticas en las 13 tablas: solo `service_role`, que la ignora, accede. Las RPC se revocan para `public/anon/authenticated` y se conceden a `service_role`. |
| 31 | Índices | Solo los de §6. `generation_stages(generation_id)` es redundante con el `UNIQUE (generation_id, stage_key)`, pero se crea porque §6 lo pide. No se añadió un índice por `created_at` (la §6 indica definirlos según las consultas reales). |
| 32 | Seed | El `storage_path` del documento de prueba apunta a un objeto inexistente; el pipeline simulado no lee archivos. |
| 33 | Offset fuera de rango | PostgREST responde 416 (`PGRST103`) cuando el offset supera el total. El repositorio lo convierte en una página vacía con el total exacto. |

## 2. Árbol de archivos

```text
backend/
├── .env.example
├── .gitignore
├── FASE1.md                      ← este documento
├── pytest.ini
├── requirements.txt
├── ai_service/
│   ├── __init__.py
│   ├── config.py                 ← pydantic-settings
│   ├── main.py                   ← create_app + lifespan (recuperación de arranque)
│   ├── api/
│   │   ├── dependencies.py
│   │   ├── errors.py             ← manejadores globales → {"error": {...}}
│   │   └── routes/
│   │       ├── generations.py
│   │       └── health.py
│   ├── clients/
│   │   └── supabase.py
│   ├── core/
│   │   ├── errors.py             ← excepciones de dominio
│   │   ├── logging.py
│   │   └── time.py
│   ├── pipeline/
│   │   ├── catalog.py
│   │   ├── context.py
│   │   ├── events.py
│   │   ├── orchestrator.py
│   │   └── stages/
│   │       ├── __init__.py       ← build_stub_stages
│   │       ├── base.py
│   │       ├── p1_normalize.py … p7_evaluation.py
│   ├── repositories/
│   │   ├── documents.py
│   │   ├── generations.py        ← Protocol + Supabase
│   │   └── in_memory.py          ← FAKE para tests
│   ├── schemas/
│   │   ├── common.py
│   │   ├── generations.py        ← esquemas HTTP
│   │   └── records.py            ← filas internas
│   └── services/
│       ├── generations.py
│       └── pipeline_runs.py
├── supabase/
│   ├── schema.sql
│   └── seed.sql
└── tests/
    ├── conftest.py
    ├── factories.py
    ├── test_contract.py
    ├── test_generations_api.py
    ├── test_pipeline.py
    └── test_recovery.py
```

(Los `__init__.py` vacíos de cada paquete se omiten en el árbol y en la sección 3.)

## 3. Código completo

### `backend/requirements.txt`

```text
# Runtime
fastapi>=0.115,<1.0
uvicorn[standard]>=0.30
pydantic>=2.7,<3.0
pydantic-settings>=2.3
supabase>=2.10,<3.0

# Tests
pytest>=8.2
pytest-asyncio>=0.23
httpx>=0.27
pyyaml>=6.0
jsonschema>=4.22
rfc3339-validator>=0.1.4
```

### `backend/pytest.ini`

```ini
[pytest]
testpaths = tests
asyncio_mode = auto
asyncio_default_fixture_loop_scope = function
filterwarnings =
    ignore:Using `httpx` with `starlette.testclient` is deprecated
```

### `backend/.env.example`

```bash
# Supabase (solo backend; nunca exponer la clave de servicio al frontend)
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=

# Pipeline simulado (Fase 1)
PIPELINE_STUB_DELAY_SECONDS=2
# Etapa en la que se inyecta un fallo simulado (p1..p7). Vacío = sin fallo.
PIPELINE_STUB_FAIL_AT_STAGE=

# Método de generación aplicado cuando la solicitud no indica method_type
DEFAULT_METHOD_TYPE=llm_pipeline
```

### `backend/supabase/schema.sql`

```sql
-- =============================================================================
-- TestGen — esquema de base de datos (PostgreSQL / Supabase)
-- Fuente: docs/database.md. Fase 1: solo se usan documents, generations y
-- generation_stages; el resto de tablas se crea para fijar el contrato.
-- =============================================================================

create extension if not exists pgcrypto;

-- -----------------------------------------------------------------------------
-- 3.1 documents (sin cascada: borrar una generación nunca borra su documento)
-- -----------------------------------------------------------------------------
create table if not exists public.documents (
    id            uuid primary key default gen_random_uuid(),
    filename      text        not null,
    file_type     text        not null check (file_type in ('txt', 'pdf', 'docx')),
    size_bytes    bigint      not null check (size_bytes >= 0),
    storage_path  text        not null,
    checksum      text        not null,
    uploaded_at   timestamptz not null default now()
);

-- -----------------------------------------------------------------------------
-- 3.2 generations
-- -----------------------------------------------------------------------------
create table if not exists public.generations (
    id                  uuid primary key default gen_random_uuid(),
    document_id         uuid        not null references public.documents (id) on delete restrict,
    status              text        not null default 'queued'
                        check (status in ('queued', 'running', 'completed', 'failed')),
    clustering_enabled  boolean     not null default true,
    method_type         text        not null,
    config_snapshot     jsonb       not null default '{}'::jsonb,
    started_at          timestamptz,
    completed_at        timestamptz,
    error_message       text,
    created_at          timestamptz not null default now()
);

-- -----------------------------------------------------------------------------
-- 3.3 generation_stages
-- -----------------------------------------------------------------------------
create table if not exists public.generation_stages (
    id             uuid primary key default gen_random_uuid(),
    generation_id  uuid    not null references public.generations (id) on delete cascade,
    stage_key      text    not null check (stage_key in ('p1', 'p2', 'p3', 'p4', 'p5', 'p6', 'p7')),
    stage_order    integer not null check (stage_order between 1 and 7),
    status         text    not null default 'pending'
                   check (status in ('pending', 'running', 'completed', 'failed', 'skipped')),
    error_message  text,
    started_at     timestamptz,
    completed_at   timestamptz,
    constraint generation_stages_key_order_match check (stage_order = substring(stage_key from 2)::integer),
    constraint generation_stages_generation_key_uq unique (generation_id, stage_key),
    constraint generation_stages_generation_order_uq unique (generation_id, stage_order)
);

-- -----------------------------------------------------------------------------
-- 3.4 user_stories
-- -----------------------------------------------------------------------------
create table if not exists public.user_stories (
    id                 uuid primary key default gen_random_uuid(),
    generation_id      uuid not null references public.generations (id) on delete cascade,
    code               text,
    original_text      text not null,
    role               text,
    action             text,
    goal               text,
    validation_status  text,
    constraint user_stories_generation_code_uq unique (generation_id, code),
    constraint user_stories_generation_id_uq unique (generation_id, id)
);

-- -----------------------------------------------------------------------------
-- 3.5 functional_requirements
-- -----------------------------------------------------------------------------
create table if not exists public.functional_requirements (
    id             uuid primary key default gen_random_uuid(),
    generation_id  uuid not null references public.generations (id) on delete cascade,
    code           text not null,
    description    text not null,
    source_text    text,
    constraint functional_requirements_generation_code_uq unique (generation_id, code),
    constraint functional_requirements_generation_id_uq unique (generation_id, id)
);

-- -----------------------------------------------------------------------------
-- 3.6 user_story_requirements (FK compuestas: misma ejecución)
-- -----------------------------------------------------------------------------
create table if not exists public.user_story_requirements (
    generation_id   uuid not null references public.generations (id) on delete cascade,
    user_story_id   uuid not null,
    requirement_id  uuid not null,
    primary key (generation_id, user_story_id, requirement_id),
    foreign key (generation_id, user_story_id)
        references public.user_stories (generation_id, id) on delete cascade,
    foreign key (generation_id, requirement_id)
        references public.functional_requirements (generation_id, id) on delete cascade
);

-- -----------------------------------------------------------------------------
-- 3.7 clusters
-- -----------------------------------------------------------------------------
create table if not exists public.clusters (
    id             uuid primary key default gen_random_uuid(),
    generation_id  uuid not null references public.generations (id) on delete cascade,
    name           text not null,
    description    text,
    cluster_label  integer,
    constraint clusters_generation_id_uq unique (generation_id, id)
);

-- -----------------------------------------------------------------------------
-- 3.8 cluster_requirements
-- -----------------------------------------------------------------------------
create table if not exists public.cluster_requirements (
    generation_id           uuid not null references public.generations (id) on delete cascade,
    cluster_id              uuid not null,
    requirement_id          uuid not null,
    similarity_to_centroid  double precision,
    primary key (generation_id, cluster_id, requirement_id),
    foreign key (generation_id, cluster_id)
        references public.clusters (generation_id, id) on delete cascade,
    foreign key (generation_id, requirement_id)
        references public.functional_requirements (generation_id, id) on delete cascade
);

-- -----------------------------------------------------------------------------
-- 3.9 test_cases
-- -----------------------------------------------------------------------------
create table if not exists public.test_cases (
    id               uuid primary key default gen_random_uuid(),
    generation_id    uuid        not null references public.generations (id) on delete cascade,
    code             text        not null,
    title            text        not null,
    objective        text,
    preconditions    jsonb       not null default '[]'::jsonb,
    test_data        jsonb,
    expected_result  text,
    created_at       timestamptz not null default now(),
    constraint test_cases_generation_code_uq unique (generation_id, code),
    constraint test_cases_generation_id_uq unique (generation_id, id)
);

-- -----------------------------------------------------------------------------
-- 3.10 test_steps
-- -----------------------------------------------------------------------------
create table if not exists public.test_steps (
    id               uuid primary key default gen_random_uuid(),
    generation_id    uuid    not null references public.generations (id) on delete cascade,
    test_case_id     uuid    not null,
    step_number      integer not null check (step_number > 0),
    action           text    not null,
    expected_result  text,
    constraint test_steps_case_number_uq unique (test_case_id, step_number),
    foreign key (generation_id, test_case_id)
        references public.test_cases (generation_id, id) on delete cascade
);

-- -----------------------------------------------------------------------------
-- 3.11 requirement_test_cases
-- -----------------------------------------------------------------------------
create table if not exists public.requirement_test_cases (
    generation_id      uuid not null references public.generations (id) on delete cascade,
    requirement_id     uuid not null,
    test_case_id       uuid not null,
    relation_status    text not null default 'pending'
                       check (relation_status in ('pending', 'validated', 'rejected')),
    validation_method  text,
    validation_notes   text,
    primary key (generation_id, requirement_id, test_case_id),
    foreign key (generation_id, requirement_id)
        references public.functional_requirements (generation_id, id) on delete cascade,
    foreign key (generation_id, test_case_id)
        references public.test_cases (generation_id, id) on delete cascade
);

-- -----------------------------------------------------------------------------
-- 3.12 generation_metrics
-- -----------------------------------------------------------------------------
create table if not exists public.generation_metrics (
    id               uuid primary key default gen_random_uuid(),
    generation_id    uuid        not null references public.generations (id) on delete cascade,
    metric_name      text        not null,
    metric_value     double precision,
    numerator        double precision,
    denominator      double precision,
    formula_version  text        not null,
    details          jsonb,
    calculated_at    timestamptz not null default now()
);

-- -----------------------------------------------------------------------------
-- 3.13 metric_findings
-- -----------------------------------------------------------------------------
create table if not exists public.metric_findings (
    id                    uuid primary key default gen_random_uuid(),
    generation_metric_id  uuid        not null references public.generation_metrics (id) on delete cascade,
    finding_code          text        not null,
    severity              text        not null check (severity in ('info', 'warning', 'error')),
    message               text        not null,
    evidence              jsonb,
    created_at            timestamptz not null default now()
);

-- -----------------------------------------------------------------------------
-- 6. Índices
-- -----------------------------------------------------------------------------
create index if not exists generations_document_id_idx         on public.generations (document_id);
create index if not exists generations_status_idx              on public.generations (status);
create index if not exists generation_stages_generation_id_idx on public.generation_stages (generation_id);
create index if not exists user_stories_generation_id_idx      on public.user_stories (generation_id);
create index if not exists functional_requirements_generation_id_idx on public.functional_requirements (generation_id);
create index if not exists test_cases_generation_id_idx        on public.test_cases (generation_id);
create index if not exists generation_metrics_generation_id_idx on public.generation_metrics (generation_id);
create index if not exists metric_findings_generation_metric_id_idx on public.metric_findings (generation_metric_id);

-- -----------------------------------------------------------------------------
-- Seguridad: RLS activo sin políticas. Solo service_role (backend) accede.
-- -----------------------------------------------------------------------------
alter table public.documents               enable row level security;
alter table public.generations             enable row level security;
alter table public.generation_stages       enable row level security;
alter table public.user_stories            enable row level security;
alter table public.functional_requirements enable row level security;
alter table public.user_story_requirements enable row level security;
alter table public.clusters                enable row level security;
alter table public.cluster_requirements    enable row level security;
alter table public.test_cases              enable row level security;
alter table public.test_steps              enable row level security;
alter table public.requirement_test_cases  enable row level security;
alter table public.generation_metrics      enable row level security;
alter table public.metric_findings         enable row level security;

-- -----------------------------------------------------------------------------
-- RPC: crea la generación (queued) y sus 7 etapas (pending) en una transacción.
-- -----------------------------------------------------------------------------
create or replace function public.create_generation(
    p_document_id        uuid,
    p_clustering_enabled boolean,
    p_method_type        text,
    p_config_snapshot    jsonb
) returns uuid
language plpgsql
set search_path = public
as $$
declare
    v_generation_id uuid;
begin
    insert into public.generations (document_id, status, clustering_enabled, method_type, config_snapshot)
    values (p_document_id, 'queued', p_clustering_enabled, p_method_type, coalesce(p_config_snapshot, '{}'::jsonb))
    returning id into v_generation_id;

    insert into public.generation_stages (generation_id, stage_key, stage_order, status)
    select v_generation_id, 'p' || n, n, 'pending'
    from generate_series(1, 7) as n;

    return v_generation_id;
end;
$$;

-- -----------------------------------------------------------------------------
-- RPC: elimina la generación solo si está en un estado final.
-- Devuelve 'deleted', 'not_found' o 'in_progress'. El bloqueo FOR UPDATE evita
-- carreras con el pipeline, que actualiza la fila con guarda de estado.
-- -----------------------------------------------------------------------------
create or replace function public.delete_generation_if_final(p_id uuid)
returns text
language plpgsql
set search_path = public
as $$
declare
    v_status text;
begin
    select status into v_status
    from public.generations
    where id = p_id
    for update;

    if not found then
        return 'not_found';
    end if;

    if v_status in ('queued', 'running') then
        return 'in_progress';
    end if;

    delete from public.generations where id = p_id;
    return 'deleted';
end;
$$;

revoke execute on function public.create_generation(uuid, boolean, text, jsonb) from public, anon, authenticated;
revoke execute on function public.delete_generation_if_final(uuid) from public, anon, authenticated;
grant execute on function public.create_generation(uuid, boolean, text, jsonb) to service_role;
grant execute on function public.delete_generation_if_final(uuid) to service_role;
```

### `backend/supabase/seed.sql`

```sql
-- Documento de prueba para la Fase 1. El objeto de Storage no se crea: el
-- pipeline simulado no lee el archivo.
insert into public.documents (id, filename, file_type, size_bytes, storage_path, checksum, uploaded_at)
values (
    '6f9d1c2e-0a4b-4c8d-9e1f-2b3c4d5e6f70',
    'historias-release-1.txt',
    'txt',
    4821,
    'seed/6f9d1c2e-0a4b-4c8d-9e1f-2b3c4d5e6f70/historias-release-1.txt',
    '9b74c9897bac770ffc029102a200c5de',
    '2026-10-25T12:00:00Z'
)
on conflict (id) do nothing;
```

### `backend/ai_service/api/dependencies.py`

```python
"""Dependencias HTTP reutilizables."""

from fastapi import Request

from ai_service.services.generations import GenerationsService


def get_generations_service(request: Request) -> GenerationsService:
    """Servicio de generaciones construido en el `lifespan` de la aplicación."""
    return request.app.state.generations_service
```

### `backend/ai_service/api/errors.py`

```python
"""Conversión centralizada de excepciones al formato `{"error": {"code","message","details"}}`."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ai_service.core.errors import (
    AppError,
    DocumentNotFound,
    FeatureNotImplemented,
    GenerationInProgress,
    GenerationNotFound,
)

logger = logging.getLogger(__name__)

_STATUS_BY_ERROR: dict[type[AppError], int] = {
    DocumentNotFound: 404,
    GenerationNotFound: 404,
    GenerationInProgress: 409,
    FeatureNotImplemented: 501,
}

_LOCATION_PREFIXES = {"body", "query", "path", "header", "cookie"}


def error_response(status_code: int, code: str, message: str, details: Any = None) -> JSONResponse:
    """Construye una respuesta de error con el formato común."""
    body = {"error": {"code": code, "message": message, "details": details if details is not None else {}}}
    return JSONResponse(status_code=status_code, content=jsonable_encoder(body))


def _validation_details(exc: RequestValidationError) -> list[dict[str, str]]:
    details = []
    for error in exc.errors():
        location = [str(part) for part in error.get("loc", ())]
        if len(location) > 1 and location[0] in _LOCATION_PREFIXES:
            location = location[1:]
        details.append({"path": ".".join(location), "message": str(error.get("msg", "Valor inválido."))})
    return details


async def _handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response(
        400, "VALIDATION_ERROR", "La solicitud contiene datos inválidos.", _validation_details(exc)
    )


async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    status_code = _STATUS_BY_ERROR.get(type(exc), 500)
    if status_code == 500:
        logger.error("AppError sin estado HTTP asignado: %s", type(exc).__name__)
        return error_response(500, "INTERNAL_ERROR", "Ocurrió un error interno.")
    return error_response(status_code, exc.code, exc.message, exc.details)


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Error no controlado en %s %s", request.method, request.url.path)
    return error_response(500, "INTERNAL_ERROR", "Ocurrió un error interno.")


def register_exception_handlers(app: FastAPI) -> None:
    """Registra los manejadores globales en la aplicación."""
    app.add_exception_handler(RequestValidationError, _handle_validation)  # type: ignore[arg-type]
    app.add_exception_handler(AppError, _handle_app_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _handle_unexpected)
```

### `backend/ai_service/api/routes/generations.py`

```python
"""Controlador HTTP de generaciones. Sin reglas de negocio ni acceso a Supabase."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response

from ai_service.api.dependencies import get_generations_service
from ai_service.core.errors import FeatureNotImplemented
from ai_service.schemas.common import ErrorResponse
from ai_service.schemas.generations import CreateGenerationRequest, Generation, GenerationList, GenerationStatus
from ai_service.services.generations import GenerationsService

router = APIRouter(prefix="/generations", tags=["Generations"])

Service = Annotated[GenerationsService, Depends(get_generations_service)]

_ERRORS: dict[int | str, dict] = {
    400: {"model": ErrorResponse, "description": "Parámetros o cuerpo inválidos."},
    500: {"model": ErrorResponse, "description": "Error interno inesperado."},
}
_NOT_FOUND: dict[int | str, dict] = {404: {"model": ErrorResponse, "description": "No existe la generación."}}


@router.post(
    "",
    status_code=202,
    response_model=Generation,
    operation_id="createGeneration",
    responses={**_ERRORS, 404: {"model": ErrorResponse, "description": "No existe el documento."}},
)
async def create_generation(
    body: CreateGenerationRequest, background_tasks: BackgroundTasks, service: Service
) -> Generation:
    """Crea una generación (`queued`) y programa el pipeline P1–P7."""
    return await service.create(body, background_tasks)


@router.get("", response_model=GenerationList, operation_id="listGenerations", responses=_ERRORS)
async def list_generations(
    service: Service,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    document_id: Annotated[UUID | None, Query()] = None,
    status: Annotated[GenerationStatus | None, Query()] = None,
) -> GenerationList:
    """Lista generaciones por `created_at` descendente."""
    return await service.list(limit=limit, offset=offset, document_id=document_id, status=status)


@router.get(
    "/{generation_id}",
    response_model=Generation,
    operation_id="getGeneration",
    responses={**_ERRORS, **_NOT_FOUND},
)
async def get_generation(generation_id: UUID, service: Service) -> Generation:
    """Devuelve estado, configuración y etapas. Es el punto de polling."""
    return await service.get(generation_id)


@router.delete(
    "/{generation_id}",
    status_code=204,
    response_class=Response,
    operation_id="deleteGeneration",
    responses={
        **_ERRORS,
        **_NOT_FOUND,
        409: {"model": ErrorResponse, "description": "La generación está en procesamiento."},
    },
)
async def delete_generation(generation_id: UUID, service: Service) -> Response:
    """Elimina una generación final y sus datos dependientes."""
    await service.delete(generation_id)
    return Response(status_code=204)


@router.get(
    "/{generation_id}/events",
    operation_id="getGenerationEvents",
    responses={501: {"model": ErrorResponse, "description": "SSE aún no implementado."}},
)
async def get_generation_events(generation_id: UUID) -> None:
    """Reservado para SSE; responde 501 hasta que exista una implementación real."""
    raise FeatureNotImplemented(
        "La transmisión de eventos SSE está planificada. Use polling sobre GET /api/v1/generations/{generation_id}."
    )
```

### `backend/ai_service/api/routes/health.py`

```python
"""Endpoint de salud."""

from fastapi import APIRouter

from ai_service.schemas.common import Health

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=Health, operation_id="getHealth")
async def get_health() -> Health:
    """Comprueba que el servicio responde."""
    return Health()
```

### `backend/ai_service/clients/supabase.py`

```python
"""Cliente de Supabase con la clave de servicio. Solo lo usan los repositorios."""

from supabase import Client, create_client

from ai_service.config import Settings
from ai_service.core.errors import ConfigurationError


def create_supabase_client(settings: Settings) -> Client:
    """Crea el cliente o falla de forma explícita si faltan credenciales."""
    if not settings.supabase_url or settings.supabase_service_role_key is None:
        raise ConfigurationError("SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY son obligatorias.")
    return create_client(settings.supabase_url, settings.supabase_service_role_key.get_secret_value())
```

### `backend/ai_service/config.py`

```python
"""Configuración de la aplicación a partir de variables de entorno."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

StageKeyLiteral = Literal["p1", "p2", "p3", "p4", "p5", "p6", "p7"]


class Settings(BaseSettings):
    """Variables de entorno del backend. La clave de servicio nunca sale del servidor."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    supabase_url: str | None = None
    supabase_service_role_key: SecretStr | None = None

    pipeline_stub_delay_seconds: float = Field(default=2.0, ge=0)
    pipeline_stub_fail_at_stage: StageKeyLiteral | None = None
    default_method_type: str = Field(default="llm_pipeline", min_length=1)

    @field_validator("pipeline_stub_fail_at_stage", mode="before")
    @classmethod
    def _empty_as_none(cls, value: object) -> object:
        """Permite dejar la variable vacía en `.env` para desactivar el fallo simulado."""
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración cargada una sola vez por proceso."""
    return Settings()
```

### `backend/ai_service/core/errors.py`

```python
"""Excepciones de dominio. No conocen HTTP; `api/errors.py` las traduce."""

from typing import Any, ClassVar


class AppError(Exception):
    """Error de aplicación con código estable y mensaje seguro para el cliente."""

    code: ClassVar[str] = "INTERNAL_ERROR"
    default_message: ClassVar[str] = "Ocurrió un error interno."

    def __init__(self, message: str | None = None, details: dict[str, Any] | list[Any] | None = None) -> None:
        self.message = message or self.default_message
        self.details: dict[str, Any] | list[Any] = details if details is not None else {}
        super().__init__(self.message)


class DocumentNotFound(AppError):
    code = "DOCUMENT_NOT_FOUND"
    default_message = "El documento indicado no existe."


class GenerationNotFound(AppError):
    code = "GENERATION_NOT_FOUND"
    default_message = "La generación indicada no existe."


class GenerationInProgress(AppError):
    code = "GENERATION_IN_PROGRESS"
    default_message = "La generación está en procesamiento y no puede eliminarse."


class FeatureNotImplemented(AppError):
    code = "NOT_IMPLEMENTED"
    default_message = "Funcionalidad aún no implementada."


class InvalidStateTransition(Exception):
    """Una actualización con guarda de estado no afectó ninguna fila. Error interno."""


class ConfigurationError(Exception):
    """Falta configuración crítica para arrancar el servicio."""
```

### `backend/ai_service/core/logging.py`

```python
"""Configuración de logging del servicio."""

import logging

_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(level: int = logging.INFO) -> None:
    """Configura el logger raíz si aún no tiene manejadores."""
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=level, format=_FORMAT)
    else:
        root.setLevel(level)
```

### `backend/ai_service/core/time.py`

```python
"""Utilidades de fecha. Todas las marcas de tiempo son UTC."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Devuelve la fecha y hora actual con zona UTC."""
    return datetime.now(UTC)
```

### `backend/ai_service/main.py`

```python
"""Punto de entrada de la aplicación FastAPI."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ai_service.api.errors import register_exception_handlers
from ai_service.api.routes import generations, health
from ai_service.config import Settings, get_settings
from ai_service.core.logging import configure_logging
from ai_service.pipeline.stages import build_stub_stages
from ai_service.repositories.documents import DocumentsRepository
from ai_service.repositories.generations import GenerationsRepository
from ai_service.services.generations import GenerationsService
from ai_service.services.pipeline_runs import PipelineRunService, recover_interrupted_generations

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


def create_app(
    settings: Settings | None = None,
    *,
    generations_repository: GenerationsRepository | None = None,
    documents_repository: DocumentsRepository | None = None,
) -> FastAPI:
    """Construye la aplicación. Los repositorios se inyectan en tests; si no, se usa Supabase."""
    configure_logging()
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        generations_repo = generations_repository
        documents_repo = documents_repository
        if generations_repo is None or documents_repo is None:
            from ai_service.clients.supabase import create_supabase_client
            from ai_service.repositories.documents import SupabaseDocumentsRepository
            from ai_service.repositories.generations import SupabaseGenerationsRepository

            client = create_supabase_client(app_settings)
            generations_repo = generations_repo or SupabaseGenerationsRepository(client)
            documents_repo = documents_repo or SupabaseDocumentsRepository(client)

        # Supone un único proceso: nada activo puede seguir vivo tras el arranque.
        await recover_interrupted_generations(generations_repo)

        stages = build_stub_stages(
            app_settings.pipeline_stub_delay_seconds, app_settings.pipeline_stub_fail_at_stage
        )
        app.state.generations_service = GenerationsService(
            generations=generations_repo,
            documents=documents_repo,
            pipeline_runs=PipelineRunService(generations_repo, stages),
            default_method_type=app_settings.default_method_type,
        )
        logger.info("Servicio iniciado")
        yield

    app = FastAPI(title="TestGen API", version="2.0.0", lifespan=lifespan)
    register_exception_handlers(app)
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(generations.router, prefix=API_PREFIX)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("ai_service.main:app", host="127.0.0.1", port=8000)
```

### `backend/ai_service/pipeline/catalog.py`

```python
"""Catálogo de etapas P1–P7. El `name` visible de la API sale de aquí; no se almacena."""

from dataclasses import dataclass

from ai_service.schemas.generations import StageKey


@dataclass(frozen=True, slots=True)
class StageDefinition:
    key: StageKey
    name: str
    order: int


STAGE_CATALOG: tuple[StageDefinition, ...] = (
    StageDefinition(StageKey.P1, "Normalización de historias de usuario", 1),
    StageDefinition(StageKey.P2, "Extracción de requisitos funcionales", 2),
    StageDefinition(StageKey.P3, "Generación de embeddings", 3),
    StageDefinition(StageKey.P4, "Clustering semántico", 4),
    StageDefinition(StageKey.P5, "Construcción de contexto estructurado", 5),
    StageDefinition(StageKey.P6, "Generación de casos de prueba funcionales", 6),
    StageDefinition(StageKey.P7, "Evaluación de resultados", 7),
)

_BY_KEY: dict[StageKey, StageDefinition] = {stage.key: stage for stage in STAGE_CATALOG}


def get_stage_definition(key: StageKey) -> StageDefinition:
    """Devuelve la definición de catálogo de una etapa."""
    return _BY_KEY[key]
```

### `backend/ai_service/pipeline/context.py`

```python
"""Contexto tipado compartido entre etapas durante una ejecución."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PipelineConfiguration:
    """Configuración efectiva de la ejecución (valores por defecto ya aplicados)."""

    clustering_enabled: bool
    method_type: str


@dataclass(slots=True)
class PipelineContext:
    """Datos de una ejecución. Las fases posteriores añadirán aquí historias, requisitos, etc."""

    generation_id: UUID
    document_id: UUID
    configuration: PipelineConfiguration
```

### `backend/ai_service/pipeline/events.py`

```python
"""Eventos internos de progreso del pipeline (no son mensajes HTTP)."""

from datetime import datetime
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ai_service.core.time import utc_now
from ai_service.schemas.generations import StageKey


class _Event(BaseModel):
    model_config = ConfigDict(frozen=True)

    generation_id: UUID
    occurred_at: datetime = Field(default_factory=utc_now)


class StageStarted(_Event):
    type: Literal["stage_started"] = "stage_started"
    stage_key: StageKey


class StageCompleted(_Event):
    type: Literal["stage_completed"] = "stage_completed"
    stage_key: StageKey


class StageSkipped(_Event):
    type: Literal["stage_skipped"] = "stage_skipped"
    stage_key: StageKey


class StageFailed(_Event):
    type: Literal["stage_failed"] = "stage_failed"
    stage_key: StageKey
    error_message: str


class PipelineCompleted(_Event):
    type: Literal["pipeline_completed"] = "pipeline_completed"


class PipelineFailed(_Event):
    type: Literal["pipeline_failed"] = "pipeline_failed"
    error_message: str


PipelineEvent = Annotated[
    StageStarted | StageCompleted | StageSkipped | StageFailed | PipelineCompleted | PipelineFailed,
    Field(discriminator="type"),
]


class ProgressReporter(Protocol):
    """Receptor de eventos. Si `report` lanza, el orquestador se detiene (escritura no registrada)."""

    async def report(self, event: PipelineEvent) -> None: ...
```

### `backend/ai_service/pipeline/orchestrator.py`

```python
"""Orquestador P1–P7. No conoce Supabase ni FastAPI: solo ejecuta etapas y emite eventos."""

import logging
from collections.abc import Sequence

from ai_service.pipeline.catalog import get_stage_definition
from ai_service.pipeline.context import PipelineContext
from ai_service.pipeline.events import (
    PipelineCompleted,
    PipelineFailed,
    ProgressReporter,
    StageCompleted,
    StageFailed,
    StageSkipped,
    StageStarted,
)
from ai_service.pipeline.stages.base import StageBase

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Recorre las etapas en orden y publica el progreso mediante un `ProgressReporter`."""

    def __init__(self, stages: Sequence[StageBase], reporter: ProgressReporter) -> None:
        self._stages = sorted(stages, key=lambda stage: get_stage_definition(stage.key).order)
        self._reporter = reporter

    @staticmethod
    def should_skip(stage: StageBase, context: PipelineContext) -> bool:
        """P3/P4 se omiten sin clustering; cualquier etapa sin implementar también."""
        if not stage.implemented:
            return True
        return stage.requires_clustering and not context.configuration.clustering_enabled

    async def run(self, context: PipelineContext) -> bool:
        """Ejecuta el pipeline. Devuelve `True` si terminó sin fallos de etapa.

        Los errores del `reporter` (escrituras de estado) no se capturan: se propagan.
        """
        generation_id = context.generation_id
        for stage in self._stages:
            stage_key = stage.key
            if self.should_skip(stage, context):
                logger.info("Etapa omitida generation_id=%s stage_key=%s", generation_id, stage_key.value)
                await self._reporter.report(StageSkipped(generation_id=generation_id, stage_key=stage_key))
                continue

            await self._reporter.report(StageStarted(generation_id=generation_id, stage_key=stage_key))
            logger.info("Etapa iniciada generation_id=%s stage_key=%s", generation_id, stage_key.value)
            try:
                await stage.run(context)
            except Exception:
                logger.exception("Etapa fallida generation_id=%s stage_key=%s", generation_id, stage_key.value)
                name = get_stage_definition(stage_key).name
                await self._reporter.report(
                    StageFailed(
                        generation_id=generation_id,
                        stage_key=stage_key,
                        error_message=f"La etapa '{name}' falló durante la ejecución.",
                    )
                )
                await self._reporter.report(
                    PipelineFailed(
                        generation_id=generation_id,
                        error_message=f"La generación falló en la etapa '{name}'.",
                    )
                )
                return False

            await self._reporter.report(StageCompleted(generation_id=generation_id, stage_key=stage_key))
            logger.info("Etapa completada generation_id=%s stage_key=%s", generation_id, stage_key.value)

        await self._reporter.report(PipelineCompleted(generation_id=generation_id))
        logger.info("Pipeline completado generation_id=%s", generation_id)
        return True
```

### `backend/ai_service/pipeline/stages/__init__.py`

```python
"""Etapas P1–P7 y su construcción a partir de la configuración."""

from ai_service.pipeline.stages.base import StageBase, StubStage
from ai_service.pipeline.stages.p1_normalize import NormalizeStage
from ai_service.pipeline.stages.p2_requirements import RequirementsStage
from ai_service.pipeline.stages.p3_embeddings import EmbeddingsStage
from ai_service.pipeline.stages.p4_clustering import ClusteringStage
from ai_service.pipeline.stages.p5_context import ContextStage
from ai_service.pipeline.stages.p6_generation import GenerationStage
from ai_service.pipeline.stages.p7_evaluation import EvaluationStage

STUB_STAGE_CLASSES: tuple[type[StubStage], ...] = (
    NormalizeStage,
    RequirementsStage,
    EmbeddingsStage,
    ClusteringStage,
    ContextStage,
    GenerationStage,
    EvaluationStage,
)


def build_stub_stages(delay_seconds: float, fail_at_stage: str | None = None) -> list[StageBase]:
    """Instancia las siete etapas simuladas en orden, inyectando el fallo si se indica."""
    return [cls(delay_seconds, fail=cls.key.value == fail_at_stage) for cls in STUB_STAGE_CLASSES]


__all__ = ["StageBase", "StubStage", "build_stub_stages", "STUB_STAGE_CLASSES"]
```

### `backend/ai_service/pipeline/stages/base.py`

```python
"""Interfaz común de las etapas y stub simulado de la Fase 1."""

import asyncio
from abc import ABC, abstractmethod
from typing import ClassVar

from ai_service.pipeline.context import PipelineContext
from ai_service.schemas.generations import StageKey


class SimulatedStageError(RuntimeError):
    """Fallo inyectado mediante `PIPELINE_STUB_FAIL_AT_STAGE`."""


class StageBase(ABC):
    """Etapa del pipeline. `requires_clustering` la omite si el clustering está deshabilitado."""

    key: ClassVar[StageKey]
    implemented: ClassVar[bool] = True
    requires_clustering: ClassVar[bool] = False

    @abstractmethod
    async def run(self, context: PipelineContext) -> None:
        """Ejecuta la etapa sobre el contexto."""


class StubStage(StageBase):
    """Etapa simulada: espera `delay_seconds` y opcionalmente falla."""

    def __init__(self, delay_seconds: float, fail: bool = False) -> None:
        self._delay_seconds = delay_seconds
        self._fail = fail

    async def run(self, context: PipelineContext) -> None:
        await asyncio.sleep(self._delay_seconds)
        if self._fail:
            raise SimulatedStageError(f"Fallo simulado en {self.key.value} (generation_id={context.generation_id})")
```

### `backend/ai_service/pipeline/stages/p1_normalize.py`

```python
"""P1 — Normalización de historias de usuario. Fase 1: stub simulado."""

from typing import ClassVar

from ai_service.pipeline.stages.base import StubStage
from ai_service.schemas.generations import StageKey


class NormalizeStage(StubStage):
    key: ClassVar[StageKey] = StageKey.P1
```

### `backend/ai_service/pipeline/stages/p2_requirements.py`

```python
"""P2 — Extracción de requisitos funcionales. Fase 1: stub simulado."""

from typing import ClassVar

from ai_service.pipeline.stages.base import StubStage
from ai_service.schemas.generations import StageKey


class RequirementsStage(StubStage):
    key: ClassVar[StageKey] = StageKey.P2
```

### `backend/ai_service/pipeline/stages/p3_embeddings.py`

```python
"""P3 — Generación de embeddings. Fase 1: stub simulado."""

from typing import ClassVar

from ai_service.pipeline.stages.base import StubStage
from ai_service.schemas.generations import StageKey


class EmbeddingsStage(StubStage):
    key: ClassVar[StageKey] = StageKey.P3
    requires_clustering: ClassVar[bool] = True
```

### `backend/ai_service/pipeline/stages/p4_clustering.py`

```python
"""P4 — Clustering semántico. Fase 1: stub simulado."""

from typing import ClassVar

from ai_service.pipeline.stages.base import StubStage
from ai_service.schemas.generations import StageKey


class ClusteringStage(StubStage):
    key: ClassVar[StageKey] = StageKey.P4
    requires_clustering: ClassVar[bool] = True
```

### `backend/ai_service/pipeline/stages/p5_context.py`

```python
"""P5 — Construcción de contexto estructurado. Fase 1: stub simulado."""

from typing import ClassVar

from ai_service.pipeline.stages.base import StubStage
from ai_service.schemas.generations import StageKey


class ContextStage(StubStage):
    key: ClassVar[StageKey] = StageKey.P5
```

### `backend/ai_service/pipeline/stages/p6_generation.py`

```python
"""P6 — Generación de casos de prueba funcionales. Fase 1: stub simulado."""

from typing import ClassVar

from ai_service.pipeline.stages.base import StubStage
from ai_service.schemas.generations import StageKey


class GenerationStage(StubStage):
    key: ClassVar[StageKey] = StageKey.P6
```

### `backend/ai_service/pipeline/stages/p7_evaluation.py`

```python
"""P7 — Evaluación de resultados. Sin implementar: se registra como skipped. Fase 1: stub simulado."""

from typing import ClassVar

from ai_service.pipeline.stages.base import StubStage
from ai_service.schemas.generations import StageKey


class EvaluationStage(StubStage):
    key: ClassVar[StageKey] = StageKey.P7
    implemented: ClassVar[bool] = False
```

### `backend/ai_service/repositories/documents.py`

```python
"""Repositorio de documentos (Fase 1: solo lectura por id)."""

import asyncio
from typing import Protocol
from uuid import UUID

from supabase import Client

from ai_service.schemas.records import DocumentRecord

_COLUMNS = "id, filename, file_type, size_bytes, checksum, uploaded_at"


class DocumentsRepository(Protocol):
    """Contrato de acceso a `documents`."""

    async def get_by_id(self, document_id: UUID) -> DocumentRecord | None:
        """Devuelve el documento o `None` si no existe."""
        ...


class SupabaseDocumentsRepository:
    """Implementación sobre Supabase. El cliente síncrono se ejecuta en un hilo."""

    def __init__(self, client: Client) -> None:
        self._client = client

    async def get_by_id(self, document_id: UUID) -> DocumentRecord | None:
        def _query() -> list[dict]:
            response = (
                self._client.table("documents").select(_COLUMNS).eq("id", str(document_id)).limit(1).execute()
            )
            return response.data or []

        rows = await asyncio.to_thread(_query)
        return DocumentRecord.model_validate(rows[0]) if rows else None
```

### `backend/ai_service/repositories/generations.py`

```python
"""Repositorio de generaciones y etapas (`generations` + `generation_stages`)."""

import asyncio
import logging
from collections.abc import Callable, Collection
from datetime import datetime
from typing import Any, Protocol, TypeVar
from uuid import UUID

from postgrest.exceptions import APIError
from postgrest.types import CountMethod
from supabase import Client

from ai_service.core.errors import DocumentNotFound, GenerationInProgress, GenerationNotFound, InvalidStateTransition
from ai_service.schemas.generations import ACTIVE_GENERATION_STATUSES, GenerationStatus, StageKey, StageStatus
from ai_service.schemas.records import GenerationRecord

logger = logging.getLogger(__name__)

T = TypeVar("T")

_SELECT = "*, documents(filename), generation_stages(*)"
_FK_VIOLATION = "23503"
_RANGE_NOT_SATISFIABLE = "PGRST103"


class GenerationsRepository(Protocol):
    """Contrato de persistencia de generaciones. Lo cumplen Supabase y el fake en memoria."""

    async def create(
        self,
        *,
        document_id: UUID,
        clustering_enabled: bool,
        method_type: str,
        config_snapshot: dict[str, Any],
    ) -> UUID:
        """Crea la generación (`queued`) y sus 7 etapas (`pending`) de forma atómica."""
        ...

    async def get_by_id(self, generation_id: UUID) -> GenerationRecord | None:
        """Devuelve la generación con `document_name` y etapas ordenadas, o `None`."""
        ...

    async def list_generations(
        self,
        *,
        document_id: UUID | None,
        status: GenerationStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[GenerationRecord], int]:
        """Lista por `created_at` descendente y devuelve también el total exacto."""
        ...

    async def update_generation_status(
        self,
        generation_id: UUID,
        *,
        expected: Collection[GenerationStatus],
        status: GenerationStatus,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
    ) -> None:
        """Actualiza el estado solo si el actual está en `expected`; si no, `InvalidStateTransition`."""
        ...

    async def update_stage(
        self,
        generation_id: UUID,
        stage_key: StageKey,
        *,
        expected: StageStatus,
        status: StageStatus,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
    ) -> None:
        """Actualiza una etapa solo si su estado actual es `expected`; si no, `InvalidStateTransition`."""
        ...

    async def delete(self, generation_id: UUID) -> None:
        """Elimina una generación final. Lanza `GenerationNotFound` o `GenerationInProgress`."""
        ...

    async def mark_interrupted(self, *, message: str, at: datetime) -> list[UUID]:
        """Marca `failed` las generaciones activas y su etapa `running`. Devuelve sus ids."""
        ...


def _payload(**fields: Any) -> dict[str, Any]:
    """Construye el cuerpo de un UPDATE omitiendo `None` y serializando fechas en ISO 8601."""
    result: dict[str, Any] = {}
    for name, value in fields.items():
        if value is None:
            continue
        result[name] = value.isoformat() if isinstance(value, datetime) else str(value)
    return result


def _to_record(row: dict[str, Any]) -> GenerationRecord:
    document = row.get("documents") or {}
    stages = sorted(row.get("generation_stages") or [], key=lambda stage: stage["stage_order"])
    return GenerationRecord.model_validate({**row, "document_name": document.get("filename"), "stages": stages})


class SupabaseGenerationsRepository:
    """Implementación sobre Supabase. Las llamadas bloqueantes se ejecutan con `asyncio.to_thread`."""

    def __init__(self, client: Client) -> None:
        self._client = client

    @staticmethod
    async def _run(fn: Callable[[], T]) -> T:
        return await asyncio.to_thread(fn)

    async def create(
        self,
        *,
        document_id: UUID,
        clustering_enabled: bool,
        method_type: str,
        config_snapshot: dict[str, Any],
    ) -> UUID:
        params = {
            "p_document_id": str(document_id),
            "p_clustering_enabled": clustering_enabled,
            "p_method_type": method_type,
            "p_config_snapshot": config_snapshot,
        }
        try:
            response = await self._run(lambda: self._client.rpc("create_generation", params).execute())
        except APIError as exc:
            if exc.code == _FK_VIOLATION:
                raise DocumentNotFound() from exc
            raise
        return UUID(str(response.data))

    async def get_by_id(self, generation_id: UUID) -> GenerationRecord | None:
        response = await self._run(
            lambda: self._client.table("generations").select(_SELECT).eq("id", str(generation_id)).limit(1).execute()
        )
        rows = response.data or []
        return _to_record(rows[0]) if rows else None

    async def list_generations(
        self,
        *,
        document_id: UUID | None,
        status: GenerationStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[GenerationRecord], int]:
        def _filtered(columns: str, head: bool = False) -> Any:
            query = self._client.table("generations").select(columns, count=CountMethod.exact, head=head)
            if document_id is not None:
                query = query.eq("document_id", str(document_id))
            if status is not None:
                query = query.eq("status", status.value)
            return query

        def _page() -> Any:
            return (
                _filtered(_SELECT)
                .order("created_at", desc=True)
                .order("id", desc=True)
                .range(offset, offset + limit - 1)
                .execute()
            )

        try:
            response = await self._run(_page)
        except APIError as exc:
            # PostgREST responde 416 si el offset supera el total: página vacía.
            if exc.code != _RANGE_NOT_SATISFIABLE:
                raise
            count_response = await self._run(lambda: _filtered("id", head=True).execute())
            return [], count_response.count or 0
        return [_to_record(row) for row in response.data or []], response.count or 0

    async def update_generation_status(
        self,
        generation_id: UUID,
        *,
        expected: Collection[GenerationStatus],
        status: GenerationStatus,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
    ) -> None:
        payload = _payload(
            status=status.value, started_at=started_at, completed_at=completed_at, error_message=error_message
        )
        expected_values = [value.value for value in expected]
        response = await self._run(
            lambda: self._client.table("generations")
            .update(payload)
            .eq("id", str(generation_id))
            .in_("status", expected_values)
            .execute()
        )
        if not response.data:
            logger.warning(
                "Transición de generación rechazada generation_id=%s expected=%s target=%s",
                generation_id,
                expected_values,
                status.value,
            )
            raise InvalidStateTransition(f"generation {generation_id}: {expected_values} -> {status.value}")

    async def update_stage(
        self,
        generation_id: UUID,
        stage_key: StageKey,
        *,
        expected: StageStatus,
        status: StageStatus,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
    ) -> None:
        payload = _payload(
            status=status.value, started_at=started_at, completed_at=completed_at, error_message=error_message
        )
        response = await self._run(
            lambda: self._client.table("generation_stages")
            .update(payload)
            .eq("generation_id", str(generation_id))
            .eq("stage_key", stage_key.value)
            .eq("status", expected.value)
            .execute()
        )
        if not response.data:
            logger.warning(
                "Transición de etapa rechazada generation_id=%s stage_key=%s expected=%s target=%s",
                generation_id,
                stage_key.value,
                expected.value,
                status.value,
            )
            raise InvalidStateTransition(f"stage {generation_id}/{stage_key.value}: {expected.value} -> {status.value}")

    async def delete(self, generation_id: UUID) -> None:
        response = await self._run(
            lambda: self._client.rpc("delete_generation_if_final", {"p_id": str(generation_id)}).execute()
        )
        result = response.data
        if result == "not_found":
            raise GenerationNotFound()
        if result == "in_progress":
            raise GenerationInProgress()
        if result != "deleted":
            raise RuntimeError(f"Resultado inesperado de delete_generation_if_final: {result!r}")

    async def mark_interrupted(self, *, message: str, at: datetime) -> list[UUID]:
        active = [value.value for value in ACTIVE_GENERATION_STATUSES]
        response = await self._run(
            lambda: self._client.table("generations").select("id").in_("status", active).execute()
        )
        ids = [row["id"] for row in response.data or []]
        if not ids:
            return []

        failed = _payload(error_message=message, completed_at=at)
        await self._run(
            lambda: self._client.table("generation_stages")
            .update({"status": StageStatus.FAILED.value, **failed})
            .in_("generation_id", ids)
            .eq("status", StageStatus.RUNNING.value)
            .execute()
        )
        updated = await self._run(
            lambda: self._client.table("generations")
            .update({"status": GenerationStatus.FAILED.value, **failed})
            .in_("id", ids)
            .in_("status", active)
            .execute()
        )
        return [UUID(row["id"]) for row in updated.data or []]
```

### `backend/ai_service/repositories/in_memory.py`

```python
"""Repositorios FAKE en memoria para tests. Replican la semántica de las RPC y las guardas."""

import itertools
import logging
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from ai_service.core.errors import DocumentNotFound, GenerationInProgress, GenerationNotFound, InvalidStateTransition
from ai_service.core.time import utc_now
from ai_service.schemas.generations import (
    ACTIVE_GENERATION_STATUSES,
    GenerationStatus,
    StageKey,
    StageStatus,
)
from ai_service.schemas.records import DocumentRecord, GenerationRecord, StageRecord

logger = logging.getLogger(__name__)


@dataclass
class InMemoryStore:
    """Estado compartido por los repositorios en memoria."""

    documents: dict[UUID, DocumentRecord] = field(default_factory=dict)
    generations: dict[UUID, GenerationRecord] = field(default_factory=dict)
    insertion_order: dict[UUID, int] = field(default_factory=dict)
    _sequence: itertools.count = field(default_factory=itertools.count)

    def add_generation(self, record: GenerationRecord) -> None:
        """Inserta una generación ya construida (útil para preparar escenarios)."""
        self.generations[record.id] = record.model_copy(deep=True)
        self.insertion_order[record.id] = next(self._sequence)


class InMemoryDocumentsRepository:
    """Fake de `DocumentsRepository`."""

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def get_by_id(self, document_id: UUID) -> DocumentRecord | None:
        document = self._store.documents.get(document_id)
        return document.model_copy(deep=True) if document else None


class InMemoryGenerationsRepository:
    """Fake de `GenerationsRepository`."""

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def create(
        self,
        *,
        document_id: UUID,
        clustering_enabled: bool,
        method_type: str,
        config_snapshot: dict[str, Any],
    ) -> UUID:
        document = self._store.documents.get(document_id)
        if document is None:
            raise DocumentNotFound()
        record = GenerationRecord(
            id=uuid4(),
            document_id=document_id,
            document_name=document.filename,
            status=GenerationStatus.QUEUED,
            clustering_enabled=clustering_enabled,
            method_type=method_type,
            config_snapshot=dict(config_snapshot),
            created_at=utc_now(),
            stages=[
                StageRecord(stage_key=key, stage_order=order, status=StageStatus.PENDING)
                for order, key in enumerate(StageKey, start=1)
            ],
        )
        self._store.add_generation(record)
        return record.id

    async def get_by_id(self, generation_id: UUID) -> GenerationRecord | None:
        record = self._store.generations.get(generation_id)
        return record.model_copy(deep=True) if record else None

    async def list_generations(
        self,
        *,
        document_id: UUID | None,
        status: GenerationStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[GenerationRecord], int]:
        matches = [
            record
            for record in self._store.generations.values()
            if (document_id is None or record.document_id == document_id)
            and (status is None or record.status == status)
        ]
        matches.sort(key=lambda r: (r.created_at, self._store.insertion_order[r.id]), reverse=True)
        page = matches[offset : offset + limit]
        return [record.model_copy(deep=True) for record in page], len(matches)

    async def update_generation_status(
        self,
        generation_id: UUID,
        *,
        expected: Collection[GenerationStatus],
        status: GenerationStatus,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
    ) -> None:
        record = self._store.generations.get(generation_id)
        if record is None or record.status not in expected:
            logger.warning(
                "Transición de generación rechazada generation_id=%s target=%s", generation_id, status.value
            )
            raise InvalidStateTransition(f"generation {generation_id} -> {status.value}")
        record.status = status
        if started_at is not None:
            record.started_at = started_at
        if completed_at is not None:
            record.completed_at = completed_at
        if error_message is not None:
            record.error_message = error_message

    async def update_stage(
        self,
        generation_id: UUID,
        stage_key: StageKey,
        *,
        expected: StageStatus,
        status: StageStatus,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
    ) -> None:
        record = self._store.generations.get(generation_id)
        stage = next((s for s in record.stages if s.stage_key == stage_key), None) if record else None
        if stage is None or stage.status != expected:
            logger.warning(
                "Transición de etapa rechazada generation_id=%s stage_key=%s target=%s",
                generation_id,
                stage_key.value,
                status.value,
            )
            raise InvalidStateTransition(f"stage {generation_id}/{stage_key.value} -> {status.value}")
        stage.status = status
        if started_at is not None:
            stage.started_at = started_at
        if completed_at is not None:
            stage.completed_at = completed_at
        if error_message is not None:
            stage.error_message = error_message

    async def delete(self, generation_id: UUID) -> None:
        record = self._store.generations.get(generation_id)
        if record is None:
            raise GenerationNotFound()
        if record.status in ACTIVE_GENERATION_STATUSES:
            raise GenerationInProgress()
        del self._store.generations[generation_id]
        del self._store.insertion_order[generation_id]

    async def mark_interrupted(self, *, message: str, at: datetime) -> list[UUID]:
        interrupted: list[UUID] = []
        for record in self._store.generations.values():
            if record.status not in ACTIVE_GENERATION_STATUSES:
                continue
            for stage in record.stages:
                if stage.status == StageStatus.RUNNING:
                    stage.status = StageStatus.FAILED
                    stage.error_message = message
                    stage.completed_at = at
            record.status = GenerationStatus.FAILED
            record.error_message = message
            record.completed_at = at
            interrupted.append(record.id)
        return interrupted
```

### `backend/ai_service/schemas/common.py`

```python
"""Esquemas comunes: salud y formato de error."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class Health(BaseModel):
    status: Literal["ok"] = "ok"


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | list[Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Formato común `{"error": {"code", "message", "details"}}`."""

    error: ErrorDetail
```

### `backend/ai_service/schemas/generations.py`

```python
"""Esquemas HTTP de generaciones, alineados con `docs/openapi.yaml`."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GenerationStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class StageKey(StrEnum):
    P1 = "p1"
    P2 = "p2"
    P3 = "p3"
    P4 = "p4"
    P5 = "p5"
    P6 = "p6"
    P7 = "p7"


ACTIVE_GENERATION_STATUSES: frozenset[GenerationStatus] = frozenset(
    {GenerationStatus.QUEUED, GenerationStatus.RUNNING}
)


class GenerationConfiguration(BaseModel):
    """Parámetros de la ejecución (`clustering_enabled`, `method_type`, `config_snapshot`)."""

    model_config = ConfigDict(extra="forbid")

    semantic_clustering_enabled: bool = Field(default=True, strict=True)
    method_type: str | None = Field(
        default=None,
        description="Método de generación. Si se omite se aplica el valor por defecto del servidor.",
    )

    @field_validator("method_type", mode="before")
    @classmethod
    def _reject_explicit_null(cls, value: object) -> object:
        """El contrato define `method_type` como string: `null` explícito no es válido."""
        if value is None:
            raise ValueError("method_type debe ser un texto.")
        return value


class CreateGenerationRequest(BaseModel):
    """Cuerpo de `POST /api/v1/generations`."""

    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    configuration: GenerationConfiguration = Field(default_factory=GenerationConfiguration)


class GenerationStage(BaseModel):
    """Etapa P1–P7. `name` proviene del catálogo del código."""

    key: StageKey
    name: str
    status: StageStatus
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    order: int = Field(ge=1, le=7)


class MetricSummary(BaseModel):
    metric_name: str
    metric_value: float | None
    formula_version: str


class GenerationSummary(BaseModel):
    """Conteos calculados desde datos persistidos. No se usa en la Fase 1 (`summary = null`)."""

    user_stories_count: int | None = None
    requirements_count: int | None = None
    clusters_count: int | None = None
    test_cases_count: int | None = None
    validated_relations_count: int | None = None
    metrics: list[MetricSummary] = Field(default_factory=list)


class Generation(BaseModel):
    """Generación con su configuración y sus siete etapas."""

    id: UUID
    document_id: UUID
    document_name: str
    status: GenerationStatus
    configuration: GenerationConfiguration
    stages: list[GenerationStage]
    summary: GenerationSummary | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class Pagination(BaseModel):
    limit: int
    offset: int
    total: int


class GenerationList(BaseModel):
    items: list[Generation]
    pagination: Pagination
```

### `backend/ai_service/schemas/records.py`

```python
"""Modelos internos de persistencia (filas de Supabase). No se exponen en HTTP."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ai_service.schemas.generations import GenerationStatus, StageKey, StageStatus


class DocumentRecord(BaseModel):
    """Fila de `documents` (sin `storage_path`, que la Fase 1 no necesita)."""

    model_config = ConfigDict(extra="ignore")

    id: UUID
    filename: str
    file_type: str
    size_bytes: int
    checksum: str
    uploaded_at: datetime


class StageRecord(BaseModel):
    """Fila de `generation_stages`."""

    model_config = ConfigDict(extra="ignore")

    stage_key: StageKey
    stage_order: int
    status: StageStatus
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class GenerationRecord(BaseModel):
    """Fila de `generations` + `documents.filename` + sus etapas ordenadas."""

    model_config = ConfigDict(extra="ignore")

    id: UUID
    document_id: UUID
    document_name: str
    status: GenerationStatus
    clustering_enabled: bool
    method_type: str
    config_snapshot: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    stages: list[StageRecord] = Field(default_factory=list)
```

### `backend/ai_service/services/generations.py`

```python
"""Casos de uso de generaciones: crear, consultar, listar y eliminar."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol
from uuid import UUID

from ai_service.core.errors import DocumentNotFound, GenerationNotFound
from ai_service.pipeline.catalog import get_stage_definition
from ai_service.pipeline.context import PipelineConfiguration, PipelineContext
from ai_service.repositories.documents import DocumentsRepository
from ai_service.repositories.generations import GenerationsRepository
from ai_service.schemas.generations import (
    CreateGenerationRequest,
    Generation,
    GenerationConfiguration,
    GenerationList,
    GenerationStage,
    GenerationStatus,
    Pagination,
)
from ai_service.schemas.records import GenerationRecord
from ai_service.services.pipeline_runs import PipelineRunService

logger = logging.getLogger(__name__)


class TaskScheduler(Protocol):
    """Programa trabajo en segundo plano. `fastapi.BackgroundTasks` cumple este contrato."""

    def add_task(self, func: Callable[..., Awaitable[None]], *args: Any, **kwargs: Any) -> None: ...


def to_generation(record: GenerationRecord) -> Generation:
    """Construye la respuesta pública. `summary` es `null` en la Fase 1 (sin resultados persistidos)."""
    stages = []
    for stage in record.stages:
        definition = get_stage_definition(stage.stage_key)
        stages.append(
            GenerationStage(
                key=stage.stage_key,
                name=definition.name,
                status=stage.status,
                error_message=stage.error_message,
                started_at=stage.started_at,
                completed_at=stage.completed_at,
                order=stage.stage_order,
            )
        )
    return Generation(
        id=record.id,
        document_id=record.document_id,
        document_name=record.document_name,
        status=record.status,
        configuration=GenerationConfiguration(
            semantic_clustering_enabled=record.clustering_enabled,
            method_type=record.method_type,
        ),
        stages=stages,
        summary=None,
        error_message=record.error_message,
        created_at=record.created_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
    )


class GenerationsService:
    """Coordina documentos, generaciones y la ejecución del pipeline."""

    def __init__(
        self,
        generations: GenerationsRepository,
        documents: DocumentsRepository,
        pipeline_runs: PipelineRunService,
        default_method_type: str,
    ) -> None:
        self._generations = generations
        self._documents = documents
        self._pipeline_runs = pipeline_runs
        self._default_method_type = default_method_type

    async def create(self, request: CreateGenerationRequest, scheduler: TaskScheduler) -> Generation:
        """Valida el documento, crea la generación con sus etapas y programa el pipeline."""
        if await self._documents.get_by_id(request.document_id) is None:
            raise DocumentNotFound()

        requested = request.configuration
        configuration = PipelineConfiguration(
            clustering_enabled=requested.semantic_clustering_enabled,
            method_type=requested.method_type if requested.method_type is not None else self._default_method_type,
        )
        config_snapshot = {
            "semantic_clustering_enabled": configuration.clustering_enabled,
            "method_type": configuration.method_type,
        }
        generation_id = await self._generations.create(
            document_id=request.document_id,
            clustering_enabled=configuration.clustering_enabled,
            method_type=configuration.method_type,
            config_snapshot=config_snapshot,
        )
        record = await self._generations.get_by_id(generation_id)
        if record is None:
            raise RuntimeError(f"La generación {generation_id} no se pudo leer tras crearse")

        context = PipelineContext(
            generation_id=generation_id, document_id=request.document_id, configuration=configuration
        )
        scheduler.add_task(self._pipeline_runs.run, context)
        logger.info("Generación creada y programada generation_id=%s", generation_id)
        return to_generation(record)

    async def get(self, generation_id: UUID) -> Generation:
        """Devuelve el estado persistido de una generación."""
        record = await self._generations.get_by_id(generation_id)
        if record is None:
            raise GenerationNotFound()
        return to_generation(record)

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        document_id: UUID | None = None,
        status: GenerationStatus | None = None,
    ) -> GenerationList:
        """Lista generaciones paginadas, de la más reciente a la más antigua."""
        records, total = await self._generations.list_generations(
            document_id=document_id, status=status, limit=limit, offset=offset
        )
        return GenerationList(
            items=[to_generation(record) for record in records],
            pagination=Pagination(limit=limit, offset=offset, total=total),
        )

    async def delete(self, generation_id: UUID) -> None:
        """Elimina una generación final y sus datos dependientes."""
        await self._generations.delete(generation_id)
        logger.info("Generación eliminada generation_id=%s", generation_id)
```

### `backend/ai_service/services/pipeline_runs.py`

```python
"""Ejecución de una generación persistida: traduce eventos del pipeline en escrituras de estado.

Tabla de transiciones aplicada (pipeline-orchestration.md §5):

| Evento             | Etapa                    | Generación                                   |
|--------------------|--------------------------|----------------------------------------------|
| inicio (implícito) | —                        | queued → running, started_at                 |
| stage_started      | pending → running        | —                                            |
| stage_completed    | running → completed      | —                                            |
| stage_skipped      | pending → skipped        | —                                            |
| stage_failed       | running → failed + error | —                                            |
| pipeline_completed | —                        | running → completed (si 7 etapas finales ok) |
| pipeline_failed    | —                        | queued|running → failed + error, completed_at|
"""

import logging
from collections.abc import Sequence
from uuid import UUID

from ai_service.core.errors import InvalidStateTransition
from ai_service.core.time import utc_now
from ai_service.pipeline.context import PipelineContext
from ai_service.pipeline.events import (
    PipelineCompleted,
    PipelineEvent,
    PipelineFailed,
    StageCompleted,
    StageFailed,
    StageSkipped,
    StageStarted,
)
from ai_service.pipeline.orchestrator import PipelineOrchestrator
from ai_service.pipeline.stages.base import StageBase
from ai_service.repositories.generations import GenerationsRepository
from ai_service.schemas.generations import (
    ACTIVE_GENERATION_STATUSES,
    GenerationStatus,
    StageStatus,
)

logger = logging.getLogger(__name__)

INTERNAL_FAILURE_MESSAGE = "La generación falló por un error interno."
INTERNAL_STAGE_FAILURE_MESSAGE = "La etapa se interrumpió por un error interno."
INTERRUPTED_MESSAGE = "Ejecución interrumpida por reinicio del servicio."

_FINAL_STAGE_STATUSES = frozenset({StageStatus.COMPLETED, StageStatus.SKIPPED})


class RepositoryProgressReporter:
    """`ProgressReporter` que persiste cada evento a través del repositorio."""

    def __init__(self, repository: GenerationsRepository, generation_id: UUID) -> None:
        self._repository = repository
        self._generation_id = generation_id

    async def report(self, event: PipelineEvent) -> None:
        repo = self._repository
        gid = self._generation_id
        match event:
            case StageStarted():
                await repo.update_stage(
                    gid, event.stage_key, expected=StageStatus.PENDING, status=StageStatus.RUNNING,
                    started_at=event.occurred_at,
                )
            case StageCompleted():
                await repo.update_stage(
                    gid, event.stage_key, expected=StageStatus.RUNNING, status=StageStatus.COMPLETED,
                    completed_at=event.occurred_at,
                )
            case StageSkipped():
                await repo.update_stage(
                    gid, event.stage_key, expected=StageStatus.PENDING, status=StageStatus.SKIPPED,
                    completed_at=event.occurred_at,
                )
            case StageFailed():
                await repo.update_stage(
                    gid, event.stage_key, expected=StageStatus.RUNNING, status=StageStatus.FAILED,
                    completed_at=event.occurred_at, error_message=event.error_message,
                )
            case PipelineCompleted():
                await self._ensure_all_stages_final()
                await repo.update_generation_status(
                    gid, expected={GenerationStatus.RUNNING}, status=GenerationStatus.COMPLETED,
                    completed_at=event.occurred_at,
                )
            case PipelineFailed():
                await repo.update_generation_status(
                    gid, expected=ACTIVE_GENERATION_STATUSES, status=GenerationStatus.FAILED,
                    completed_at=event.occurred_at, error_message=event.error_message,
                )

    async def _ensure_all_stages_final(self) -> None:
        """Una generación solo se completa si sus 7 etapas están `completed` o `skipped`."""
        record = await self._repository.get_by_id(self._generation_id)
        if record is None:
            raise InvalidStateTransition(f"generation {self._generation_id} no existe")
        pending = [s.stage_key.value for s in record.stages if s.status not in _FINAL_STAGE_STATUSES]
        if len(record.stages) != 7 or pending:
            raise InvalidStateTransition(f"generation {self._generation_id}: etapas no finales {pending}")


class PipelineRunService:
    """Adapta una generación persistida a una ejecución del orquestador."""

    def __init__(self, repository: GenerationsRepository, stages: Sequence[StageBase]) -> None:
        self._repository = repository
        self._stages = stages

    async def run(self, context: PipelineContext) -> None:
        """Ejecuta el pipeline completo. Nunca propaga excepciones (corre en segundo plano)."""
        generation_id = context.generation_id
        try:
            await self._repository.update_generation_status(
                generation_id,
                expected={GenerationStatus.QUEUED},
                status=GenerationStatus.RUNNING,
                started_at=utc_now(),
            )
            logger.info("Pipeline iniciado generation_id=%s", generation_id)
            reporter = RepositoryProgressReporter(self._repository, generation_id)
            await PipelineOrchestrator(self._stages, reporter).run(context)
        except Exception:
            logger.exception("Error no previsto en el pipeline generation_id=%s", generation_id)
            await self._fail_safely(generation_id)

    async def _fail_safely(self, generation_id: UUID) -> None:
        """Marca `failed` la generación y su etapa `running`, si aún están activas."""
        now = utc_now()
        try:
            record = await self._repository.get_by_id(generation_id)
            if record is None or record.status not in ACTIVE_GENERATION_STATUSES:
                return
            for stage in record.stages:
                if stage.status == StageStatus.RUNNING:
                    await self._repository.update_stage(
                        generation_id, stage.stage_key, expected=StageStatus.RUNNING, status=StageStatus.FAILED,
                        completed_at=now, error_message=INTERNAL_STAGE_FAILURE_MESSAGE,
                    )
            await self._repository.update_generation_status(
                generation_id, expected=ACTIVE_GENERATION_STATUSES, status=GenerationStatus.FAILED,
                completed_at=now, error_message=INTERNAL_FAILURE_MESSAGE,
            )
        except Exception:
            # Sin escritura confirmada; la recuperación de arranque la marcará como interrumpida.
            logger.exception("No se pudo registrar el fallo generation_id=%s", generation_id)


async def recover_interrupted_generations(repository: GenerationsRepository) -> list[UUID]:
    """Recuperación de arranque: asume un único proceso, así que ninguna ejecución activa sigue viva."""
    interrupted = await repository.mark_interrupted(message=INTERRUPTED_MESSAGE, at=utc_now())
    for generation_id in interrupted:
        logger.warning("Generación interrumpida marcada como failed generation_id=%s", generation_id)
    return interrupted
```

### `backend/tests/conftest.py`

```python
"""Fixtures: app con repositorios en memoria, delay 0 y sin Supabase."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from ai_service.config import Settings
from ai_service.main import create_app
from ai_service.repositories.in_memory import (
    InMemoryDocumentsRepository,
    InMemoryGenerationsRepository,
    InMemoryStore,
)
from ai_service.schemas.records import DocumentRecord

DOCUMENT_ID = UUID("6f9d1c2e-0a4b-4c8d-9e1f-2b3c4d5e6f70")
DOCUMENT_NAME = "historias-release-1.txt"


@pytest.fixture
def store() -> InMemoryStore:
    store = InMemoryStore()
    store.documents[DOCUMENT_ID] = DocumentRecord(
        id=DOCUMENT_ID,
        filename=DOCUMENT_NAME,
        file_type="txt",
        size_bytes=4821,
        checksum="9b74c9897bac770ffc029102a200c5de",
        uploaded_at=datetime(2026, 10, 25, 12, 0, tzinfo=UTC),
    )
    return store


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {"pipeline_stub_delay_seconds": 0, **overrides}
    return Settings(_env_file=None, **values)


ClientFactory = Callable[..., TestClient]


@pytest.fixture
def client_factory(store: InMemoryStore) -> Iterator[ClientFactory]:
    """Crea clientes con ajustes opcionales; se cierran al terminar el test."""
    opened: list[TestClient] = []

    def factory(*, raise_server_exceptions: bool = True, generations_repository: Any = None, **overrides: Any) -> TestClient:
        app = create_app(
            make_settings(**overrides),
            generations_repository=generations_repository or InMemoryGenerationsRepository(store),
            documents_repository=InMemoryDocumentsRepository(store),
        )
        client = TestClient(app, raise_server_exceptions=raise_server_exceptions)
        client.__enter__()
        opened.append(client)
        return client

    yield factory
    for client in opened:
        client.__exit__(None, None, None)


@pytest.fixture
def client(client_factory: ClientFactory) -> TestClient:
    return client_factory()
```

### `backend/tests/factories.py`

```python
"""Constructores de generaciones en estados concretos para preparar escenarios."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from ai_service.repositories.in_memory import InMemoryStore
from ai_service.schemas.generations import GenerationStatus, StageKey, StageStatus
from ai_service.schemas.records import GenerationRecord, StageRecord

BASE_TIME = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)


def add_generation(
    store: InMemoryStore,
    *,
    document_id: UUID,
    status: GenerationStatus,
    stage_statuses: dict[StageKey, StageStatus] | None = None,
    minutes: int = 0,
) -> UUID:
    """Inserta una generación con estados de etapa explícitos (por defecto todas `pending`)."""
    statuses = stage_statuses or {}
    document = store.documents[document_id]
    record = GenerationRecord(
        id=uuid4(),
        document_id=document_id,
        document_name=document.filename,
        status=status,
        clustering_enabled=True,
        method_type="llm_pipeline",
        config_snapshot={"semantic_clustering_enabled": True, "method_type": "llm_pipeline"},
        created_at=BASE_TIME + timedelta(minutes=minutes),
        stages=[
            StageRecord(stage_key=key, stage_order=order, status=statuses.get(key, StageStatus.PENDING))
            for order, key in enumerate(StageKey, start=1)
        ],
    )
    store.add_generation(record)
    return record.id
```

### `backend/tests/test_contract.py`

```python
"""Las respuestas cumplen los esquemas de `docs/openapi.yaml` (criterio 10)."""

from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from ai_service.schemas.generations import GenerationStatus
from tests.conftest import DOCUMENT_ID, ClientFactory
from tests.factories import add_generation

SPEC_PATH = Path(__file__).resolve().parents[1] / "docs" / "openapi.yaml"
SPEC_URI = "urn:testgen:openapi"
URL = "/api/v1/generations"


@pytest.fixture(scope="module")
def validate():
    spec = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    registry = Registry().with_resource(SPEC_URI, Resource.from_contents(spec, default_specification=DRAFT202012))

    def _validate(instance: object, schema_name: str) -> None:
        schema = {"$ref": f"{SPEC_URI}#/components/schemas/{schema_name}"}
        validator = Draft202012Validator(
            schema, registry=registry, format_checker=Draft202012Validator.FORMAT_CHECKER
        )
        errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
        assert not errors, "\n".join(f"{list(e.path)}: {e.message}" for e in errors)

    return _validate


def test_health_contract(client: TestClient, validate) -> None:
    validate(client.get("/api/v1/health").json(), "Health")


def test_generation_contracts(client: TestClient, validate) -> None:
    created = client.post(URL, json={"document_id": str(DOCUMENT_ID)})
    validate(created.json(), "Generation")

    validate(client.get(f"{URL}/{created.json()['id']}").json(), "Generation")
    validate(client.get(URL).json(), "GenerationList")


def test_failed_generation_contract(client_factory: ClientFactory, validate) -> None:
    client = client_factory(pipeline_stub_fail_at_stage="p2")
    generation_id = client.post(URL, json={"document_id": str(DOCUMENT_ID)}).json()["id"]
    validate(client.get(f"{URL}/{generation_id}").json(), "Generation")


def test_error_contracts(client: TestClient, store, validate) -> None:
    active = add_generation(store, document_id=DOCUMENT_ID, status=GenerationStatus.RUNNING)
    responses = [
        client.post(URL, json={}),
        client.get(URL, params={"limit": 0}),
        client.get(f"{URL}/no-es-uuid"),
        client.post(URL, json={"document_id": str(uuid4())}),
        client.get(f"{URL}/{uuid4()}"),
        client.delete(f"{URL}/{active}"),
        client.get(f"{URL}/{uuid4()}/events"),
    ]
    assert [r.status_code for r in responses] == [400, 400, 400, 404, 404, 409, 501]
    for response in responses:
        validate(response.json(), "Error")
```

### `backend/tests/test_generations_api.py`

```python
"""Flujo HTTP de generaciones con el repositorio en memoria (criterios 1–8)."""

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from ai_service.pipeline.catalog import STAGE_CATALOG
from ai_service.repositories.in_memory import InMemoryGenerationsRepository, InMemoryStore
from ai_service.schemas.generations import GenerationStatus, StageKey, StageStatus
from ai_service.schemas.records import DocumentRecord
from tests.conftest import DOCUMENT_ID, DOCUMENT_NAME, ClientFactory
from tests.factories import BASE_TIME, add_generation

URL = "/api/v1/generations"


def _stages(body: dict) -> dict[str, dict]:
    return {stage["key"]: stage for stage in body["stages"]}


def assert_error(response, status_code: int, code: str) -> dict:
    assert response.status_code == status_code, response.text
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    return body["error"]


def test_health(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# 1 ---------------------------------------------------------------------------
def test_create_returns_202_with_pending_stages(client: TestClient) -> None:
    response = client.post(URL, json={"document_id": str(DOCUMENT_ID)})

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["document_id"] == str(DOCUMENT_ID)
    assert body["document_name"] == DOCUMENT_NAME
    assert body["configuration"] == {"semantic_clustering_enabled": True, "method_type": "llm_pipeline"}
    assert body["summary"] is None
    for field in ("error_message", "started_at", "completed_at"):
        assert field in body and body[field] is None
    assert [(s["key"], s["name"], s["order"]) for s in body["stages"]] == [
        (d.key.value, d.name, d.order) for d in STAGE_CATALOG
    ]
    for stage in body["stages"]:
        assert stage["status"] == "pending"
        assert stage["error_message"] is None and stage["started_at"] is None and stage["completed_at"] is None


def test_create_keeps_explicit_configuration(client: TestClient, store: InMemoryStore) -> None:
    payload = {
        "document_id": str(DOCUMENT_ID),
        "configuration": {"semantic_clustering_enabled": False, "method_type": "baseline"},
    }
    body = client.post(URL, json=payload).json()

    assert body["configuration"] == {"semantic_clustering_enabled": False, "method_type": "baseline"}
    record = store.generations[UUID(body["id"])]
    assert record.config_snapshot == {"semantic_clustering_enabled": False, "method_type": "baseline"}


# 2 ---------------------------------------------------------------------------
def test_happy_path_completes_with_p7_skipped(client: TestClient) -> None:
    generation_id = client.post(URL, json={"document_id": str(DOCUMENT_ID)}).json()["id"]

    body = client.get(f"{URL}/{generation_id}").json()

    assert body["status"] == "completed"
    assert body["started_at"] is not None and body["completed_at"] is not None
    assert body["error_message"] is None
    stages = _stages(body)
    for key in ("p1", "p2", "p3", "p4", "p5", "p6"):
        assert stages[key]["status"] == "completed"
        assert stages[key]["started_at"] is not None and stages[key]["completed_at"] is not None
    assert stages["p7"]["status"] == "skipped"
    assert stages["p7"]["started_at"] is None and stages["p7"]["completed_at"] is not None


# 3 ---------------------------------------------------------------------------
def test_clustering_disabled_skips_p3_p4(client: TestClient) -> None:
    payload = {"document_id": str(DOCUMENT_ID), "configuration": {"semantic_clustering_enabled": False}}
    generation_id = client.post(URL, json=payload).json()["id"]

    body = client.get(f"{URL}/{generation_id}").json()

    assert body["status"] == "completed"
    stages = _stages(body)
    for key in ("p3", "p4", "p7"):
        assert stages[key]["status"] == "skipped"
        assert stages[key]["started_at"] is None
        assert stages[key]["completed_at"] is not None
    for key in ("p1", "p2", "p5", "p6"):
        assert stages[key]["status"] == "completed"


# 4 ---------------------------------------------------------------------------
def test_injected_failure_at_p4(client_factory: ClientFactory) -> None:
    client = client_factory(pipeline_stub_fail_at_stage="p4")
    generation_id = client.post(URL, json={"document_id": str(DOCUMENT_ID)}).json()["id"]

    body = client.get(f"{URL}/{generation_id}").json()

    assert body["status"] == "failed"
    assert body["error_message"]
    assert body["completed_at"] is not None
    stages = _stages(body)
    assert [stages[k]["status"] for k in ("p1", "p2", "p3")] == ["completed"] * 3
    assert stages["p4"]["status"] == "failed"
    assert stages["p4"]["error_message"]
    assert "Traceback" not in stages["p4"]["error_message"]
    assert "Fallo simulado" not in stages["p4"]["error_message"]
    assert stages["p4"]["completed_at"] is not None
    for key in ("p5", "p6", "p7"):
        assert stages[key]["status"] == "pending"
        assert stages[key]["started_at"] is None and stages[key]["completed_at"] is None


# 5 ---------------------------------------------------------------------------
@pytest.mark.parametrize("status", [GenerationStatus.QUEUED, GenerationStatus.RUNNING])
def test_delete_active_generation_returns_409(client: TestClient, store: InMemoryStore, status) -> None:
    generation_id = add_generation(store, document_id=DOCUMENT_ID, status=status)

    response = client.delete(f"{URL}/{generation_id}")

    assert_error(response, 409, "GENERATION_IN_PROGRESS")
    assert generation_id in store.generations


@pytest.mark.parametrize("status", [GenerationStatus.COMPLETED, GenerationStatus.FAILED])
def test_delete_final_generation_returns_204(client: TestClient, store: InMemoryStore, status) -> None:
    generation_id = add_generation(store, document_id=DOCUMENT_ID, status=status)

    response = client.delete(f"{URL}/{generation_id}")

    assert response.status_code == 204
    assert response.content == b""
    assert generation_id not in store.generations
    assert DOCUMENT_ID in store.documents
    assert_error(client.get(f"{URL}/{generation_id}"), 404, "GENERATION_NOT_FOUND")


def test_delete_missing_generation_returns_404(client: TestClient) -> None:
    assert_error(client.delete(f"{URL}/{uuid4()}"), 404, "GENERATION_NOT_FOUND")


# 6 ---------------------------------------------------------------------------
def test_list_filters_order_and_pagination(client: TestClient, store: InMemoryStore) -> None:
    other_id = uuid4()
    store.documents[other_id] = DocumentRecord(
        id=other_id, filename="otro.pdf", file_type="pdf", size_bytes=10, checksum="x", uploaded_at=BASE_TIME
    )
    g0 = add_generation(store, document_id=DOCUMENT_ID, status=GenerationStatus.COMPLETED, minutes=0)
    g1 = add_generation(store, document_id=DOCUMENT_ID, status=GenerationStatus.FAILED, minutes=1)
    g2 = add_generation(store, document_id=other_id, status=GenerationStatus.COMPLETED, minutes=2)
    g3 = add_generation(store, document_id=DOCUMENT_ID, status=GenerationStatus.COMPLETED, minutes=3)

    body = client.get(URL).json()
    assert [item["id"] for item in body["items"]] == [str(g) for g in (g3, g2, g1, g0)]
    assert body["pagination"] == {"limit": 20, "offset": 0, "total": 4}
    assert len(body["items"][0]["stages"]) == 7

    body = client.get(URL, params={"limit": 2, "offset": 1}).json()
    assert [item["id"] for item in body["items"]] == [str(g2), str(g1)]
    assert body["pagination"] == {"limit": 2, "offset": 1, "total": 4}

    body = client.get(URL, params={"document_id": str(DOCUMENT_ID)}).json()
    assert [item["id"] for item in body["items"]] == [str(g) for g in (g3, g1, g0)]
    assert body["pagination"]["total"] == 3

    body = client.get(URL, params={"status": "completed", "document_id": str(DOCUMENT_ID)}).json()
    assert [item["id"] for item in body["items"]] == [str(g3), str(g0)]
    assert body["pagination"]["total"] == 2

    body = client.get(URL, params={"offset": 10}).json()
    assert body["items"] == [] and body["pagination"]["total"] == 4


# 7 ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"document_id": "no-es-uuid"},
        {"document_id": str(DOCUMENT_ID), "extra": 1},
        {"document_id": str(DOCUMENT_ID), "configuration": {"semantic_clustering_enabled": "si"}},
        {"document_id": str(DOCUMENT_ID), "configuration": {"method_type": None}},
        {"document_id": str(DOCUMENT_ID), "configuration": {"unknown": True}},
        {"document_id": str(DOCUMENT_ID), "configuration": None},
    ],
)
def test_invalid_body_returns_400(client: TestClient, payload: dict) -> None:
    error = assert_error(client.post(URL, json=payload), 400, "VALIDATION_ERROR")
    assert isinstance(error["details"], list) and error["details"]
    for detail in error["details"]:
        assert set(detail) == {"path", "message"}


def test_malformed_json_returns_400(client: TestClient) -> None:
    response = client.post(URL, content=b"{no json", headers={"content-type": "application/json"})
    assert_error(response, 400, "VALIDATION_ERROR")


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"status": "done"}])
def test_invalid_query_returns_400(client: TestClient, params: dict) -> None:
    error = assert_error(client.get(URL, params=params), 400, "VALIDATION_ERROR")
    assert error["details"][0]["path"] in params


@pytest.mark.parametrize("method", ["get", "delete"])
def test_malformed_uuid_returns_400(client: TestClient, method: str) -> None:
    error = assert_error(getattr(client, method)(f"{URL}/no-es-uuid"), 400, "VALIDATION_ERROR")
    assert error["details"][0]["path"] == "generation_id"


def test_unknown_document_returns_404(client: TestClient, store: InMemoryStore) -> None:
    assert_error(client.post(URL, json={"document_id": str(uuid4())}), 404, "DOCUMENT_NOT_FOUND")
    assert store.generations == {}


def test_unknown_generation_returns_404(client: TestClient) -> None:
    assert_error(client.get(f"{URL}/{uuid4()}"), 404, "GENERATION_NOT_FOUND")


def test_unexpected_error_returns_500_without_trace(client_factory: ClientFactory, store: InMemoryStore) -> None:
    class BrokenRepository(InMemoryGenerationsRepository):
        async def list_generations(self, **kwargs):
            raise RuntimeError("secreto: postgres://user:pass@host")

    client = client_factory(raise_server_exceptions=False, generations_repository=BrokenRepository(store))
    response = client.get(URL)

    error = assert_error(response, 500, "INTERNAL_ERROR")
    assert "secreto" not in response.text and "Traceback" not in response.text
    assert error["details"] == {}


# 8 ---------------------------------------------------------------------------
def test_events_returns_501(client: TestClient) -> None:
    assert_error(client.get(f"{URL}/{uuid4()}/events"), 501, "NOT_IMPLEMENTED")


def test_stage_keys_are_complete() -> None:
    assert [d.key for d in STAGE_CATALOG] == list(StageKey)
    assert StageStatus.SKIPPED.value == "skipped"
```

### `backend/tests/test_pipeline.py`

```python
"""Pruebas unitarias del orquestador y del servicio de ejecución."""

from uuid import uuid4

from ai_service.core.errors import InvalidStateTransition
from ai_service.pipeline.context import PipelineConfiguration, PipelineContext
from ai_service.pipeline.events import PipelineEvent
from ai_service.pipeline.orchestrator import PipelineOrchestrator
from ai_service.pipeline.stages import build_stub_stages
from ai_service.repositories.in_memory import InMemoryGenerationsRepository
from ai_service.schemas.generations import GenerationStatus, StageStatus
from ai_service.services.pipeline_runs import INTERNAL_FAILURE_MESSAGE, PipelineRunService
from tests.conftest import DOCUMENT_ID
from tests.factories import add_generation


class RecordingReporter:
    def __init__(self) -> None:
        self.events: list[PipelineEvent] = []

    async def report(self, event: PipelineEvent) -> None:
        self.events.append(event)


def _context(clustering: bool = True) -> PipelineContext:
    return PipelineContext(
        generation_id=uuid4(),
        document_id=DOCUMENT_ID,
        configuration=PipelineConfiguration(clustering_enabled=clustering, method_type="llm_pipeline"),
    )


def _summary(events: list[PipelineEvent]) -> list[str]:
    return [f"{e.type}:{getattr(e, 'stage_key', '')}" for e in events]


async def test_orchestrator_event_sequence_without_clustering() -> None:
    reporter = RecordingReporter()
    ok = await PipelineOrchestrator(build_stub_stages(0), reporter).run(_context(clustering=False))

    assert ok is True
    assert _summary(reporter.events) == [
        "stage_started:p1", "stage_completed:p1",
        "stage_started:p2", "stage_completed:p2",
        "stage_skipped:p3", "stage_skipped:p4",
        "stage_started:p5", "stage_completed:p5",
        "stage_started:p6", "stage_completed:p6",
        "stage_skipped:p7",
        "pipeline_completed:",
    ]


async def test_orchestrator_stops_after_failure() -> None:
    reporter = RecordingReporter()
    ok = await PipelineOrchestrator(build_stub_stages(0, "p2"), reporter).run(_context())

    assert ok is False
    assert _summary(reporter.events) == [
        "stage_started:p1", "stage_completed:p1", "stage_started:p2", "stage_failed:p2", "pipeline_failed:",
    ]


class FlakyRepository(InMemoryGenerationsRepository):
    """Falla la escritura que marca `running` la etapa P3."""

    async def update_stage(self, generation_id, stage_key, **kwargs):
        if stage_key.value == "p3" and kwargs["status"] == StageStatus.RUNNING:
            raise ConnectionError("supabase caído")
        await super().update_stage(generation_id, stage_key, **kwargs)


async def test_failed_state_write_marks_generation_failed(store) -> None:
    repo = FlakyRepository(store)
    generation_id = add_generation(store, document_id=DOCUMENT_ID, status=GenerationStatus.QUEUED)
    context = _context()
    context.generation_id = generation_id

    await PipelineRunService(repo, build_stub_stages(0)).run(context)

    record = await repo.get_by_id(generation_id)
    assert record.status == GenerationStatus.FAILED
    assert record.error_message == INTERNAL_FAILURE_MESSAGE
    assert record.completed_at is not None
    statuses = {s.stage_key.value: s.status for s in record.stages}
    assert statuses["p2"] == StageStatus.COMPLETED
    assert statuses["p3"] == StageStatus.PENDING


async def test_guarded_update_rejects_invalid_transition(store) -> None:
    repo = InMemoryGenerationsRepository(store)
    generation_id = add_generation(store, document_id=DOCUMENT_ID, status=GenerationStatus.COMPLETED)

    try:
        await repo.update_generation_status(
            generation_id, expected={GenerationStatus.RUNNING}, status=GenerationStatus.FAILED
        )
    except InvalidStateTransition:
        pass
    else:
        raise AssertionError("se esperaba InvalidStateTransition")
    assert (await repo.get_by_id(generation_id)).status == GenerationStatus.COMPLETED


async def test_run_does_not_reopen_final_generation(store) -> None:
    repo = InMemoryGenerationsRepository(store)
    generation_id = add_generation(store, document_id=DOCUMENT_ID, status=GenerationStatus.FAILED)
    context = _context()
    context.generation_id = generation_id

    await PipelineRunService(repo, build_stub_stages(0)).run(context)

    record = await repo.get_by_id(generation_id)
    assert record.status == GenerationStatus.FAILED
    assert all(s.status == StageStatus.PENDING for s in record.stages)
```

### `backend/tests/test_recovery.py`

```python
"""Recuperación de ejecuciones interrumpidas al arrancar (criterio 9)."""

from ai_service.schemas.generations import GenerationStatus, StageKey, StageStatus
from ai_service.services.pipeline_runs import INTERRUPTED_MESSAGE
from tests.conftest import DOCUMENT_ID, ClientFactory
from tests.factories import add_generation


def test_startup_marks_active_generations_failed(client_factory: ClientFactory, store) -> None:
    running = add_generation(
        store,
        document_id=DOCUMENT_ID,
        status=GenerationStatus.RUNNING,
        stage_statuses={StageKey.P1: StageStatus.COMPLETED, StageKey.P2: StageStatus.RUNNING},
    )
    queued = add_generation(store, document_id=DOCUMENT_ID, status=GenerationStatus.QUEUED)
    completed = add_generation(
        store,
        document_id=DOCUMENT_ID,
        status=GenerationStatus.COMPLETED,
        stage_statuses={key: StageStatus.COMPLETED for key in StageKey},
    )

    client = client_factory()  # el lifespan ejecuta la recuperación

    body = client.get(f"/api/v1/generations/{running}").json()
    assert body["status"] == "failed"
    assert body["error_message"] == INTERRUPTED_MESSAGE
    assert body["completed_at"] is not None
    stages = {s["key"]: s for s in body["stages"]}
    assert stages["p1"]["status"] == "completed"
    assert stages["p2"]["status"] == "failed"
    assert stages["p2"]["error_message"] == INTERRUPTED_MESSAGE
    assert stages["p2"]["completed_at"] is not None
    assert all(stages[k]["status"] == "pending" for k in ("p3", "p4", "p5", "p6", "p7"))

    body = client.get(f"/api/v1/generations/{queued}").json()
    assert body["status"] == "failed"
    assert body["error_message"] == INTERRUPTED_MESSAGE
    assert all(s["status"] == "pending" for s in body["stages"])

    assert client.get(f"/api/v1/generations/{completed}").json()["status"] == "completed"

    # Tras la recuperación, la generación ya es final y puede eliminarse.
    assert client.delete(f"/api/v1/generations/{running}").status_code == 204
```

## 4. Comandos

```bash
# Desde backend/
py -3.12 -m venv .venv                 # Windows (Linux/macOS: python3.12 -m venv .venv)
.venv\Scripts\Activate.ps1             # Windows PowerShell (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt

cp .env.example .env                   # y completar SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY

# Aplicar esquema y seed (cadena de conexión de Supabase: Project Settings → Database)
psql "$SUPABASE_DB_URL" -f supabase/schema.sql
psql "$SUPABASE_DB_URL" -f supabase/seed.sql
# Alternativa: pegar ambos archivos en el SQL Editor de Supabase, en ese orden.

# Ejecutar la API (UN solo worker: ver supuesto 22)
uvicorn ai_service.main:app --reload
# o: python -m ai_service.main

# Tests (sin Supabase, repositorio en memoria, delay 0)
pytest -q
```

### curl de prueba

```bash
API=http://localhost:8000/api/v1
DOC=6f9d1c2e-0a4b-4c8d-9e1f-2b3c4d5e6f70   # documento del seed

# 1. Crear (202 Accepted, 7 etapas pending)
GEN=$(curl -s -X POST "$API/generations" -H "Content-Type: application/json" \
  -d "{\"document_id\":\"$DOC\",\"configuration\":{\"semantic_clustering_enabled\":true}}" | jq -r .id)

# 2. Consultar con polling hasta estado final
while :; do
  S=$(curl -s "$API/generations/$GEN" | tee /dev/stderr | jq -r .status); echo
  [ "$S" = completed ] || [ "$S" = failed ] && break; sleep 2
done

# 3. Listar (filtros y paginación)
curl -s "$API/generations?document_id=$DOC&status=completed&limit=3&offset=0" | jq .

# 4. Borrar (204; 409 GENERATION_IN_PROGRESS si sigue queued/running; 404 si no existe)
curl -s -o /dev/null -w "%{http_code}\n" -X DELETE "$API/generations/$GEN"

# 5. Eventos SSE (501 NOT_IMPLEMENTED)
curl -s "$API/generations/$GEN/events" | jq .
```

## 5. Criterios de aceptación

Resultado: `pytest -q` → **41 passed**. Además se ejecutó una prueba de humo con uvicorn real
(repositorio en memoria, delay 0,3 s): el POST respondió en ~0,09 s y el polling mostró la secuencia
`running` → … → `completed` con P7 `skipped`.

| Criterio | Verificado con tests | Requiere Supabase real |
|---|---|---|
| POST → 202, 7 etapas `pending`, `document_name`, `configuration` y `config_snapshot` | ✅ `test_create_*` | — |
| Camino feliz: p1–p6 `completed`, p7 `skipped`, generación `completed` con fechas | ✅ `test_happy_path_*` | — |
| Clustering deshabilitado: p3/p4 `skipped` sin `started_at` y con `completed_at` | ✅ `test_clustering_disabled_*`, `test_orchestrator_event_sequence_*` | — |
| Fallo en p4: p4 `failed` con mensaje seguro, p5–p7 `pending`, generación `failed` con `error_message`/`completed_at` | ✅ `test_injected_failure_at_p4` | — |
| DELETE 409 (`queued`/`running`), 204 (`completed`/`failed`), 404; el documento se conserva | ✅ `test_delete_*` | Bloqueo `FOR UPDATE` y cascada real de la RPC |
| Listado: filtros, orden `created_at desc`, limit/offset, total exacto, offset fuera de rango | ✅ `test_list_*` (fake) | `count=exact`, select embebido y manejo de `PGRST103` |
| Errores: 400 VALIDATION_ERROR (cuerpo, JSON roto, limit 0/101, offset −1, status inválido, UUID), 404, 500 sin trazas; formato común | ✅ `test_invalid_*`, `test_malformed_*`, `test_unknown_*`, `test_unexpected_error_*` | — |
| `/events` → 501 | ✅ `test_events_returns_501` | — |
| Recuperación de arranque (`queued`/`running` → `failed`, etapa `running` → `failed`, `pending` intactas) | ✅ `test_recovery.py` (fake) | Las tres llamadas PostgREST de `mark_interrupted` |
| Contrato: respuestas válidas según openapi.yaml (Generation, GenerationList, Error, Health; formatos uuid/date-time) | ✅ `test_contract.py` | — |
| Una escritura de estado fallida se trata como error y marca la generación `failed` | ✅ `test_failed_state_write_*` | — |
| Guarda `WHERE status = esperado` → `InvalidStateTransition`; un estado final no se reabre | ✅ `test_guarded_update_*`, `test_run_does_not_reopen_*` (fake) | La guarda real `.in_("status", …)` / `.eq("status", …)` |
| `schema.sql`: 13 tablas, PK/FK compuestas, CHECK, UNIQUE e índices; aplicación sin errores | ❌ | ✅ Aplicar en Supabase |
| RPC `create_generation` atómica (generación + 7 etapas) y FK → `DocumentNotFound` | ❌ | ✅ |
| RPC `delete_generation_if_final` (`deleted`/`not_found`/`in_progress`) | Semántica replicada en el fake | ✅ |
| Cliente Supabase ejecutado con `asyncio.to_thread` sin bloquear el bucle | ❌ (inspección de código) | ✅ |
| La clave de servicio no sale del backend (`SecretStr`, no se registra ni se devuelve) | Inspección de código | — |
| Arranque sin credenciales → error explícito | Verificado manualmente (`ConfigurationError`) | — |

**Pendiente de la Fase 1 que requiere entorno real:** aplicar `schema.sql` y `seed.sql`, levantar
uvicorn contra Supabase y ejecutar los cinco curl de la sección 4. Ningún test toca Supabase.

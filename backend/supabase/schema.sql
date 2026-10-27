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

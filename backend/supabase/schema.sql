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
    error_code     text,                                  -- D-28: código estable del StageError
    warnings       jsonb   not null default '[]'::jsonb,  -- D-35: avisos no bloqueantes
    llm_runs       jsonb   not null default '[]'::jsonb,  -- D-35: consumo del LLM por llamada
    runtime_info   jsonb,                                 -- D-34/D-35: configuración efectiva de la etapa
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
    -- D-27: clasificación de P2 (explica por qué una HU no tiene RF)
    classification            text,
    classification_rationale  text,
    clarification_items       jsonb not null default '[]'::jsonb,
    -- Orden de aparición en el documento (base 1). Los listados ordenan por esta columna.
    position           integer check (position > 0),
    constraint user_stories_validation_status_check
        check (validation_status in ('valid', 'valid_with_warnings', 'invalid')),
    constraint user_stories_classification_check
        check (classification in ('candidata_funcional', 'requiere_aclaracion', 'no_aplicable')),
    constraint user_stories_generation_code_uq unique (generation_id, code),
    constraint user_stories_generation_id_uq unique (generation_id, id),
    constraint user_stories_generation_position_uq unique (generation_id, position)
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
-- 3.8b unassigned_requirements (D-32): RF que P4 no asignó a ningún cluster.
-- Se guardan y se muestran; por ahora no generan casos de prueba.
-- -----------------------------------------------------------------------------
create table if not exists public.unassigned_requirements (
    generation_id   uuid not null references public.generations (id) on delete cascade,
    requirement_id  uuid not null,
    primary key (generation_id, requirement_id),
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
-- 5. Migración aditiva para esquemas ya desplegados (Fase 3, D-26 a D-35).
-- Repite las columnas y restricciones añadidas arriba; es idempotente.
-- -----------------------------------------------------------------------------
alter table public.generation_stages
    add column if not exists error_code   text,
    add column if not exists warnings     jsonb not null default '[]'::jsonb,
    add column if not exists llm_runs     jsonb not null default '[]'::jsonb,
    add column if not exists runtime_info jsonb;

alter table public.user_stories
    add column if not exists classification           text,
    add column if not exists classification_rationale text,
    add column if not exists clarification_items      jsonb not null default '[]'::jsonb,
    add column if not exists position                 integer check (position > 0);

alter table public.user_stories drop constraint if exists user_stories_validation_status_check;
alter table public.user_stories add constraint user_stories_validation_status_check
    check (validation_status in ('valid', 'valid_with_warnings', 'invalid'));
alter table public.user_stories drop constraint if exists user_stories_classification_check;
alter table public.user_stories add constraint user_stories_classification_check
    check (classification in ('candidata_funcional', 'requiere_aclaracion', 'no_aplicable'));
alter table public.user_stories drop constraint if exists user_stories_generation_position_uq;
alter table public.user_stories add constraint user_stories_generation_position_uq
    unique (generation_id, position);

-- -----------------------------------------------------------------------------
-- 6. Índices
-- -----------------------------------------------------------------------------
-- Criterio:
--  * Los UNIQUE y PRIMARY KEY ya crean un índice B-tree. Ese índice sirve para
--    filtrar por su primera columna sola (prefijo izquierdo), por lo que NO se
--    crea un índice simple sobre generation_id donde ya existe un UNIQUE que
--    empieza por esa columna.
--  * PostgreSQL NO indexa automáticamente las columnas de una FOREIGN KEY. Se
--    indexa el "otro lado" de las tablas puente para consultas inversas de
--    trazabilidad y para que los borrados en cascada no recorran la tabla.

-- Limpieza de índices redundantes (si el esquema ya estaba desplegado).
-- generation_stages  -> cubierto por generation_stages_generation_key_uq (generation_id, stage_key)
-- user_stories       -> cubierto por user_stories_generation_code_uq (generation_id, code)
-- functional_requirements -> cubierto por functional_requirements_generation_code_uq
-- test_cases         -> cubierto por test_cases_generation_code_uq
drop index if exists public.generation_stages_generation_id_idx;
drop index if exists public.user_stories_generation_id_idx;
drop index if exists public.functional_requirements_generation_id_idx;
drop index if exists public.test_cases_generation_id_idx;

-- Índices necesarios (columnas sin ningún UNIQUE/PK que empiece por ellas).
create index if not exists generations_document_id_idx         on public.generations (document_id);
create index if not exists generations_status_idx              on public.generations (status);
create index if not exists generation_metrics_generation_id_idx on public.generation_metrics (generation_id);
create index if not exists metric_findings_generation_metric_id_idx on public.metric_findings (generation_metric_id);
-- test_steps: su UNIQUE empieza por test_case_id; sin esto el cascade desde
-- generations recorre la tabla completa.
create index if not exists test_steps_generation_id_idx         on public.test_steps (generation_id);

-- Tablas puente: la PK cubre un sentido; estos cubren el sentido inverso y los
-- borrados en cascada desde functional_requirements / test_cases.
create index if not exists user_story_requirements_req_idx
    on public.user_story_requirements (generation_id, requirement_id);
create index if not exists cluster_requirements_req_idx
    on public.cluster_requirements (generation_id, requirement_id);
create index if not exists requirement_test_cases_tc_idx
    on public.requirement_test_cases (generation_id, test_case_id);

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
alter table public.unassigned_requirements enable row level security;
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

-- -----------------------------------------------------------------------------
-- RPC de persistencia por etapa (D-30). PostgREST no ofrece transacciones entre
-- tablas: cada función escribe todo el resultado de una etapa (o unidad de P6)
-- en una sola transacción. Las referencias llegan por `code` y se traducen a
-- `id` dentro de la generación; un código inexistente aborta todo (23503).
-- -----------------------------------------------------------------------------

-- P1: historias de usuario (user_stories). Idempotente por (generation_id, code) — T-01.
-- p_payload = [{ "id"?, "code", "position", "original_text", "role"?, "action"?, "goal"?, "validation_status" }]
create or replace function public.persist_p1_user_stories(
    p_generation_id uuid,
    p_payload       jsonb
) returns void
language plpgsql
set search_path = public
as $$
begin
    insert into public.user_stories (id, generation_id, code, position, original_text, role, action, goal, validation_status)
    select coalesce(s.id, gen_random_uuid()), p_generation_id, s.code, s.position, s.original_text, s.role, s.action, s.goal, s.validation_status
    from jsonb_to_recordset(coalesce(p_payload, '[]'::jsonb))
         as s(id uuid, code text, position integer, original_text text, role text, action text, goal text, validation_status text)
    on conflict (generation_id, code) do update
        set position          = excluded.position,
            original_text     = excluded.original_text,
            role              = excluded.role,
            action            = excluded.action,
            goal              = excluded.goal,
            validation_status = excluded.validation_status;
end;
$$;

-- P2: clasificación de HU + RF + user_story_requirements.
-- p_payload = {
--   "classifications": [{ "user_story_code", "classification", "classification_rationale", "clarification_items": [] }],
--   "requirements":    [{ "id"?, "code", "description", "source_text"?, "user_story_codes": [] }]
-- }
create or replace function public.persist_p2_requirements(
    p_generation_id uuid,
    p_payload       jsonb
) returns void
language plpgsql
set search_path = public
as $$
declare
    v_expected integer;
    v_updated  integer;
    v_missing  text;
begin
    -- T-02: rechazar user_story_code duplicados en el payload con un mensaje claro.
    select c.user_story_code into v_missing
    from jsonb_to_recordset(coalesce(p_payload -> 'classifications', '[]'::jsonb)) as c(user_story_code text)
    group by c.user_story_code
    having count(*) > 1
    limit 1;
    if found then
        raise exception 'persist_p2_requirements: la HU % aparece 2 o más veces en el payload', v_missing
            using errcode = '23505';
    end if;

    v_expected := jsonb_array_length(coalesce(p_payload -> 'classifications', '[]'::jsonb));

    update public.user_stories us
    set classification           = c.classification,
        classification_rationale = c.classification_rationale,
        clarification_items      = coalesce(c.clarification_items, '[]'::jsonb)
    from jsonb_to_recordset(coalesce(p_payload -> 'classifications', '[]'::jsonb))
         as c(user_story_code text, classification text, classification_rationale text, clarification_items jsonb)
    where us.generation_id = p_generation_id
      and us.code = c.user_story_code;
    get diagnostics v_updated = row_count;

    if v_updated <> v_expected then
        raise exception 'persist_p2_requirements: % de % clasificaciones apuntan a HU inexistentes',
            v_expected - v_updated, v_expected using errcode = '23503';
    end if;

    insert into public.functional_requirements (id, generation_id, code, description, source_text)
    select coalesce(r.id, gen_random_uuid()), p_generation_id, r.code, r.description, r.source_text
    from jsonb_to_recordset(coalesce(p_payload -> 'requirements', '[]'::jsonb))
         as r(id uuid, code text, description text, source_text text)
    on conflict (generation_id, code) do update           -- T-01: idempotencia por clave
        set description = excluded.description,
            source_text  = excluded.source_text;

    select l.user_story_code into v_missing
    from jsonb_to_recordset(coalesce(p_payload -> 'requirements', '[]'::jsonb))
             as r(code text, user_story_codes jsonb)
         cross join lateral jsonb_array_elements_text(r.user_story_codes) as l(user_story_code)
         left join public.user_stories us
             on us.generation_id = p_generation_id and us.code = l.user_story_code
    where us.id is null
    limit 1;

    if found then
        raise exception 'persist_p2_requirements: la HU % no existe en la generación', v_missing
            using errcode = '23503';
    end if;

    insert into public.user_story_requirements (generation_id, user_story_id, requirement_id)
    select distinct p_generation_id, us.id, fr.id
    from jsonb_to_recordset(coalesce(p_payload -> 'requirements', '[]'::jsonb))
             as r(code text, user_story_codes jsonb)
         cross join lateral jsonb_array_elements_text(r.user_story_codes) as l(user_story_code)
         join public.functional_requirements fr
             on fr.generation_id = p_generation_id and fr.code = r.code
         join public.user_stories us
             on us.generation_id = p_generation_id and us.code = l.user_story_code
    on conflict (generation_id, user_story_id, requirement_id) do nothing;  -- T-01
end;
$$;

-- P4: clusters + cluster_requirements + unassigned_requirements.
-- p_payload = {
--   "clusters": [{ "id", "name", "description"?, "cluster_label"?,
--                  "assignments": [{ "requirement_code", "similarity_to_centroid"? }] }],
--   "unassigned_requirement_codes": []
-- }
create or replace function public.persist_p4_clusters(
    p_generation_id uuid,
    p_payload       jsonb
) returns void
language plpgsql
set search_path = public
as $$
declare
    v_missing text;
begin
    if exists (
        select 1
        from jsonb_to_recordset(coalesce(p_payload -> 'clusters', '[]'::jsonb)) as c(id uuid)
        where c.id is null
    ) then
        raise exception 'persist_p4_clusters: todo cluster debe traer su id' using errcode = '23502';
    end if;

    insert into public.clusters (id, generation_id, name, description, cluster_label)
    select c.id, p_generation_id, c.name, c.description, c.cluster_label
    from jsonb_to_recordset(coalesce(p_payload -> 'clusters', '[]'::jsonb))
         as c(id uuid, name text, description text, cluster_label integer)
    on conflict (id) do update                              -- T-01: idempotencia por clave
        set name           = excluded.name,
            description    = excluded.description,
            cluster_label  = excluded.cluster_label;

    with codes as (
        select a.requirement_code as code
        from jsonb_to_recordset(coalesce(p_payload -> 'clusters', '[]'::jsonb)) as c(assignments jsonb)
             cross join lateral jsonb_to_recordset(coalesce(c.assignments, '[]'::jsonb)) as a(requirement_code text)
        union
        select jsonb_array_elements_text(coalesce(p_payload -> 'unassigned_requirement_codes', '[]'::jsonb))
    )
    select codes.code into v_missing
    from codes
         left join public.functional_requirements fr
             on fr.generation_id = p_generation_id and fr.code = codes.code
    where fr.id is null
    limit 1;

    if found then
        raise exception 'persist_p4_clusters: el RF % no existe en la generación', v_missing
            using errcode = '23503';
    end if;

    insert into public.cluster_requirements (generation_id, cluster_id, requirement_id, similarity_to_centroid)
    select p_generation_id, c.id, fr.id, a.similarity_to_centroid
    from jsonb_to_recordset(coalesce(p_payload -> 'clusters', '[]'::jsonb)) as c(id uuid, assignments jsonb)
         cross join lateral jsonb_to_recordset(coalesce(c.assignments, '[]'::jsonb))
             as a(requirement_code text, similarity_to_centroid double precision)
         join public.functional_requirements fr
             on fr.generation_id = p_generation_id and fr.code = a.requirement_code
    on conflict (generation_id, cluster_id, requirement_id) do nothing;  -- T-01

    insert into public.unassigned_requirements (generation_id, requirement_id)
    select distinct p_generation_id, fr.id
    from jsonb_array_elements_text(coalesce(p_payload -> 'unassigned_requirement_codes', '[]'::jsonb)) as u(code)
         join public.functional_requirements fr
             on fr.generation_id = p_generation_id and fr.code = u.code
    on conflict (generation_id, requirement_id) do nothing;  -- T-01
end;
$$;

-- P6: una unidad de contexto = casos + pasos + vínculos RF–CP (D-15: todo o nada).
-- p_payload = {
--   "test_cases": [{ "id", "code", "title", "objective"?, "preconditions": [], "test_data"?,
--                    "expected_result"?, "steps": [{ "step_number", "action", "expected_result"? }],
--                    "requirement_codes": [] }]
-- }
-- Los vínculos se insertan siempre en `pending`, sin método de validación, y los
-- códigos de RF repetidos en un mismo caso se eliminan antes de insertar.
create or replace function public.persist_p6_unit(
    p_generation_id uuid,
    p_payload       jsonb
) returns void
language plpgsql
set search_path = public
as $$
declare
    v_missing text;
begin
    if exists (
        select 1
        from jsonb_to_recordset(coalesce(p_payload -> 'test_cases', '[]'::jsonb)) as t(id uuid)
        where t.id is null
    ) then
        raise exception 'persist_p6_unit: todo caso de prueba debe traer su id' using errcode = '23502';
    end if;

    select l.code into v_missing
    from jsonb_to_recordset(coalesce(p_payload -> 'test_cases', '[]'::jsonb)) as t(requirement_codes jsonb)
         cross join lateral jsonb_array_elements_text(coalesce(t.requirement_codes, '[]'::jsonb)) as l(code)
         left join public.functional_requirements fr
             on fr.generation_id = p_generation_id and fr.code = l.code
    where fr.id is null
    limit 1;

    if found then
        raise exception 'persist_p6_unit: el RF % no existe en la generación', v_missing
            using errcode = '23503';
    end if;

    insert into public.test_cases (id, generation_id, code, title, objective, preconditions, test_data, expected_result)
    select t.id, p_generation_id, t.code, t.title, t.objective,
           coalesce(t.preconditions, '[]'::jsonb), t.test_data, t.expected_result
    from jsonb_to_recordset(coalesce(p_payload -> 'test_cases', '[]'::jsonb))
         as t(id uuid, code text, title text, objective text, preconditions jsonb, test_data jsonb, expected_result text)
    on conflict (generation_id, code) do update            -- T-01: idempotencia por clave
        set title           = excluded.title,
            objective       = excluded.objective,
            preconditions   = excluded.preconditions,
            test_data       = excluded.test_data,
            expected_result = excluded.expected_result;

    insert into public.test_steps (generation_id, test_case_id, step_number, action, expected_result)
    select p_generation_id, t.id, s.step_number, s.action, s.expected_result
    from jsonb_to_recordset(coalesce(p_payload -> 'test_cases', '[]'::jsonb)) as t(id uuid, steps jsonb)
         cross join lateral jsonb_to_recordset(coalesce(t.steps, '[]'::jsonb))
             as s(step_number integer, action text, expected_result text)
    on conflict (test_case_id, step_number) do nothing;  -- T-01

    insert into public.requirement_test_cases (generation_id, requirement_id, test_case_id)
    select distinct p_generation_id, fr.id, t.id
    from jsonb_to_recordset(coalesce(p_payload -> 'test_cases', '[]'::jsonb)) as t(id uuid, requirement_codes jsonb)
         cross join lateral jsonb_array_elements_text(coalesce(t.requirement_codes, '[]'::jsonb)) as l(code)
         join public.functional_requirements fr
             on fr.generation_id = p_generation_id and fr.code = l.code
    on conflict (generation_id, requirement_id, test_case_id) do nothing;  -- T-01
end;
$$;

revoke execute on function public.create_generation(uuid, boolean, text, jsonb) from public, anon, authenticated;
revoke execute on function public.delete_generation_if_final(uuid) from public, anon, authenticated;
revoke execute on function public.persist_p1_user_stories(uuid, jsonb) from public, anon, authenticated;
revoke execute on function public.persist_p2_requirements(uuid, jsonb) from public, anon, authenticated;
revoke execute on function public.persist_p4_clusters(uuid, jsonb) from public, anon, authenticated;
revoke execute on function public.persist_p6_unit(uuid, jsonb) from public, anon, authenticated;
grant execute on function public.create_generation(uuid, boolean, text, jsonb) to service_role;
grant execute on function public.delete_generation_if_final(uuid) to service_role;
grant execute on function public.persist_p1_user_stories(uuid, jsonb) to service_role;
grant execute on function public.persist_p2_requirements(uuid, jsonb) to service_role;
grant execute on function public.persist_p4_clusters(uuid, jsonb) to service_role;
grant execute on function public.persist_p6_unit(uuid, jsonb) to service_role;

-- -----------------------------------------------------------------------------
-- Storage: bucket privado para POST /api/v1/documents (DOCUMENTS_BUCKET).
-- service_role bypasa RLS; sin políticas para anon/authenticated.
-- -----------------------------------------------------------------------------
insert into storage.buckets (id, name, public)
values ('docs_testgen', 'docs_testgen', false)
on conflict (id) do nothing;
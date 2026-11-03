-- The desk's record. Every firm sees only its own clients and notices (forced row-level security on
-- app.firm_id); the group mailroom sees documents that are not yet routed and a tax-number index without
-- names; group operations sees aggregates. The runtime role cannot delete or change the schema.

create table firms (id text primary key, name text not null, city text not null, land text not null);

create table people (
  id text primary key,
  firm_id text references firms(id),          -- null: group staff (mailroom, operations)
  name text not null,
  role text not null check (role in ('clerk', 'advisor', 'mailroom', 'group_ops'))
);

create table clients (
  id text primary key,
  firm_id text not null references firms(id),
  kind text not null,
  name text not null,
  steuernummer text not null unique,
  address text not null,
  land text not null,
  municipality text
);

create table filed_returns (
  firm_id text not null references firms(id),
  client_id text not null references clients(id),
  kind text not null,
  year int not null,
  fields jsonb not null,
  primary key (client_id, kind, year)
);

create table onfile (
  id bigserial primary key,
  firm_id text not null references firms(id),
  client_id text not null references clients(id),
  kind text not null,
  year int not null,
  date date not null,
  messbetrag bigint not null
);

create table history (
  id bigserial primary key,
  firm_id text not null references firms(id),
  client_id text not null references clients(id),
  year int not null,
  kind text not null,
  reason text,
  text text not null,
  objection boolean not null,
  outcome text
);

create table documents (
  id text primary key,
  firm_id text references firms(id),          -- null until the mailroom routes it
  channel text not null,
  received_at date not null,
  meta jsonb not null,
  sha256 text not null,
  path text not null
);

create table notices (
  id text primary key references documents(id),
  firm_id text not null references firms(id),
  client_id text references clients(id),
  kind text,
  tax_year int,
  authority text,
  notice_date date,
  action text not null,
  reasons jsonb not null,
  parsed jsonb not null,
  findings jsonb not null,
  explanation jsonb not null,
  tax_effect bigint not null default 0,
  status text not null default 'open' check (status in ('open', 'done')),
  outcome text,
  decided_by text references people(id),
  decided_at timestamptz,
  created_at timestamptz not null default now()
);

create table deadlines (
  id bigserial primary key,
  firm_id text not null references firms(id),
  notice_id text not null references notices(id),
  due date not null,
  bekanntgabe date not null,
  basis text not null,
  rules jsonb not null,
  notes jsonb not null,
  later_possible date,
  status text not null default 'proposed' check (status in ('proposed', 'confirmed', 'done', 'cancelled')),
  proposed_by text not null,                  -- 'desk' or a person
  confirmed_by text references people(id),
  confirmed_at timestamptz,
  -- a deadline is confirmed by someone other than whoever proposed it (Fristenkontrolle, four eyes)
  constraint second_person check (confirmed_by is null or confirmed_by <> proposed_by),
  constraint confirmed_has_person check (status <> 'confirmed' or confirmed_by is not null)
);

create table drafts (
  id bigserial primary key,
  firm_id text not null references firms(id),
  notice_id text not null references notices(id),
  kind text not null check (kind in ('objection', 'client_letter')),
  text text not null,
  citations jsonb not null,
  verification jsonb not null,
  written_by text not null,                   -- 'template' or the model id
  status text not null default 'draft' check (status in ('draft', 'released')),
  released_by text references people(id),
  released_at timestamptz,
  constraint released_by_person check (status <> 'released' or released_by is not null),
  constraint only_verified_released check (status <> 'released' or (verification ->> 'ok')::boolean)
);

create table corrections (
  id bigserial primary key,
  firm_id text not null references firms(id),
  notice_id text not null references notices(id),
  field text not null,
  old_value bigint,
  new_value bigint not null,
  label text,
  by_person text not null references people(id),
  at timestamptz not null default now()
);

-- layouts are the towns', not the clients': shared across the group, holding no client data
create table layout_memory (
  authority text not null,
  field text not null,
  label text not null,
  learned_from bigint references corrections(id),
  uses int not null default 0,
  primary key (authority, field, label)
);

create table audit_log (
  id bigserial primary key,
  firm_id text,
  actor text not null,
  on_behalf_of text,
  action text not null,
  subject text,
  detail jsonb not null default '{}',
  at timestamptz not null default now()
);

create table outbox (
  id bigserial primary key,
  firm_id text not null references firms(id),
  topic text not null,
  payload jsonb not null,
  created_at timestamptz not null default now(),
  sent_at timestamptz
);

create function forbid_change() returns trigger language plpgsql as $$
begin
  raise exception '% is append-only', tg_table_name;
end $$;
create trigger audit_append_only before update or delete on audit_log for each row execute function forbid_change();

create function frozen_after_confirm() returns trigger language plpgsql as $$
begin
  if old.status = 'confirmed' and (new.due <> old.due or new.confirmed_by is distinct from old.confirmed_by) then
    raise exception 'a confirmed deadline cannot be moved; cancel it and propose a new one';
  end if;
  return new;
end $$;
create trigger deadline_frozen before update on deadlines for each row execute function frozen_after_confirm();

create function released_is_final() returns trigger language plpgsql as $$
begin
  if old.status = 'released' then
    raise exception 'a released draft cannot be changed';
  end if;
  return new;
end $$;
create trigger draft_final before update on drafts for each row execute function released_is_final();

-- routing for the mailroom: tax number -> firm, nothing else
create function route_taxno(digits text) returns text language sql security definer stable as $$
  select firm_id from clients where regexp_replace(steuernummer, '\D', '', 'g') = digits
$$;

-- row-level security
do $$
declare t text;
begin
  foreach t in array array['clients', 'filed_returns', 'onfile', 'history', 'notices', 'deadlines', 'drafts',
                           'corrections', 'outbox'] loop
    execute format('alter table %I enable row level security', t);
    execute format('alter table %I force row level security', t);
    execute format($p$create policy firm_only on %I using (firm_id = current_setting('app.firm_id', true))
                   with check (firm_id = current_setting('app.firm_id', true))$p$, t);
  end loop;
end $$;

alter table documents enable row level security;
alter table documents force row level security;
create policy firm_docs on documents using (firm_id = current_setting('app.firm_id', true))
  with check (firm_id = current_setting('app.firm_id', true) or
              (firm_id is null and current_setting('app.scope', true) = 'mailroom'));
create policy mailroom_docs on documents using (firm_id is null and current_setting('app.scope', true) = 'mailroom');
-- the mailroom routes a document to a firm once, and sees nothing of it afterwards
create function route_document(doc text, firm text) returns void language plpgsql security definer as $$
begin
  if current_setting('app.scope', true) is distinct from 'mailroom' then
    raise exception 'only the mailroom routes documents';
  end if;
  update documents set firm_id = firm where id = doc and firm_id is null;
end $$;

alter table audit_log enable row level security;
alter table audit_log force row level security;
create policy audit_firm on audit_log using (firm_id = current_setting('app.firm_id', true) or
                                             current_setting('app.scope', true) in ('mailroom', 'group_ops'))
  with check (true);

-- group operations: numbers per firm, no client data. These run as tnd_reporting (bypasses RLS, owns nothing
-- else) and return aggregates only.
create function firm_metrics() returns table(firm_id text, action text, notices bigint, open bigint)
  language sql security definer stable as $$
  select firm_id, action, count(*), count(*) filter (where status = 'open') from notices group by 1, 2
$$;
create function deadline_metrics() returns table(firm_id text, proposed bigint, confirmed bigint, done bigint)
  language sql security definer stable as $$
  select firm_id, count(*) filter (where status = 'proposed'), count(*) filter (where status = 'confirmed'),
         count(*) filter (where status = 'done') from deadlines group by 1
$$;
create function correction_metrics() returns table(firm_id text, field text, corrections bigint)
  language sql security definer stable as $$
  select firm_id, field, count(*) from corrections group by 1, 2
$$;

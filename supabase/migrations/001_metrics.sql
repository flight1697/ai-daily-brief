create table if not exists public.runs (
  run_id uuid primary key,
  target_date date not null,
  started_at timestamptz not null,
  finished_at timestamptz,
  collected integer not null default 0,
  in_window integer not null default 0,
  deduplicated integer not null default 0,
  selected integer not null default 0,
  source_errors integer not null default 0,
  llm_used boolean not null default false,
  email_status text not null,
  duration_seconds double precision not null default 0
);

create table if not exists public.source_runs (
  run_id uuid not null references public.runs(run_id) on delete cascade,
  target_date date not null,
  source_name text not null,
  source_type text not null,
  collected_count integer not null default 0,
  status text not null,
  error_message text not null default '',
  duration_seconds double precision not null default 0,
  primary key (run_id, source_name)
);

create table if not exists public.deliveries (
  message_id text primary key,
  run_id uuid references public.runs(run_id) on delete set null,
  target_date date,
  recipient text not null default '',
  subject text not null default '',
  status text not null,
  sent_at timestamptz,
  delivered_at timestamptz,
  bounced_at timestamptz,
  complained_at timestamptz,
  last_event_at timestamptz not null default now(),
  event_payload jsonb not null default '{}'::jsonb
);

create index if not exists source_runs_target_date_idx on public.source_runs(target_date);
create index if not exists runs_target_date_idx on public.runs(target_date);
create index if not exists deliveries_target_date_idx on public.deliveries(target_date);

alter table public.runs enable row level security;
alter table public.source_runs enable row level security;
alter table public.deliveries enable row level security;

create or replace view public.daily_metrics with (security_invoker = true) as
select
  target_date,
  count(*) as attempts,
  max(collected) as collected,
  max(in_window) as in_window,
  max(deduplicated) as deduplicated,
  max(selected) as selected,
  bool_or(email_status like 'sent:%') as sent,
  min(source_errors) as source_errors,
  max(duration_seconds) as duration_seconds
from public.runs
group by target_date;

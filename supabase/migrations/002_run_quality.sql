create table if not exists public.run_quality (
  run_id uuid primary key references public.runs(run_id) on delete cascade,
  target_date date not null,
  passed boolean not null,
  item_count integer not null default 0,
  source_count integer not null default 0,
  category_count integer not null default 0,
  official_count integer not null default 0,
  multi_source_count integer not null default 0,
  official_ratio double precision not null default 0,
  multi_source_ratio double precision not null default 0,
  summary_completeness double precision not null default 0,
  average_score double precision not null default 0,
  blocking_reasons jsonb not null default '[]'::jsonb,
  warnings jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists run_quality_target_date_idx
  on public.run_quality(target_date);

alter table public.run_quality enable row level security;

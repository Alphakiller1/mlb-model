-- Model lean tracking: record at build time, grade after finals.
-- Idempotent upsert key: (slate_date, game_pk, source, market, selection, line).

create table if not exists model_leans (
  lean_id uuid primary key default gen_random_uuid(),
  slate_date date not null,
  game_pk bigint,
  source text not null,
  market text not null,
  selection text not null,
  line numeric,
  model_value numeric,
  model_prob numeric,
  edge numeric,
  lean text not null,
  model_version text not null default 'unknown',
  recorded_at timestamptz not null default now(),
  settled boolean not null default false,
  won boolean,
  push boolean not null default false,
  realized_value numeric,
  settled_at timestamptz,
  unique (slate_date, game_pk, source, market, selection, line)
);

create index if not exists idx_model_leans_slate
  on model_leans(slate_date, settled);

create index if not exists idx_model_leans_source
  on model_leans(source, market, settled);

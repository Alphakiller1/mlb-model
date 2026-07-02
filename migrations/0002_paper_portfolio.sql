create table if not exists paper_positions (
  position_id uuid primary key default gen_random_uuid(),
  game_pk bigint not null references games(game_pk),
  market_type text not null,
  selection text not null,
  line numeric,
  entry_odds int not null,
  model_probability numeric not null,
  market_probability numeric,
  stake_units numeric not null check (stake_units >= 0),
  strategy_version text not null,
  status text not null default 'open'
    check (status in ('open', 'won', 'lost', 'push', 'void')),
  entry_time timestamptz not null default now(),
  settled_time timestamptz,
  pnl_units numeric,
  notes text
);

create index if not exists idx_paper_positions_open
  on paper_positions(status, game_pk);

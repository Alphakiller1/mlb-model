create table if not exists player_prop_outcomes (
  game_pk bigint not null,
  player_id bigint,
  player_name text not null,
  stat_key text not null check (stat_key in ('K', 'BB', 'ER', 'Outs')),
  value numeric not null,
  source text,
  final_at timestamptz,
  created_at timestamptz not null default now(),
  primary key (game_pk, player_name, stat_key)
);

create index if not exists idx_player_prop_outcomes_game_stat
  on player_prop_outcomes(game_pk, stat_key);

create index if not exists idx_player_prop_outcomes_player_id
  on player_prop_outcomes(player_id)
  where player_id is not null;

alter table if exists model_predictions
  add column if not exists actual_player_name text,
  add column if not exists actual_prop_stat text,
  add column if not exists actual_prop_value numeric;

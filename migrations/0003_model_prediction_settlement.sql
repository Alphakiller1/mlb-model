alter table if exists model_predictions
  add column if not exists settled boolean not null default false,
  add column if not exists won boolean,
  add column if not exists push boolean not null default false,
  add column if not exists settled_time timestamptz,
  add column if not exists actual_winner text,
  add column if not exists actual_home_runs int,
  add column if not exists actual_away_runs int,
  add column if not exists actual_total_runs int,
  add column if not exists actual_margin_home numeric;

create index if not exists idx_model_predictions_settlement
  on model_predictions(settled, game_pk);

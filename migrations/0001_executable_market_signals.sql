-- Point-in-time execution fields required by the MLB Model promotion gate.
-- Historical rows remain null and are intentionally ineligible for promotion.
alter table prediction_market_snapshots
  add column if not exists signal_time timestamptz,
  add column if not exists entry_prob numeric,
  add column if not exists signal_delta numeric,
  add column if not exists entry_source text;

create index if not exists idx_pm_signal_time
  on prediction_market_snapshots(signal_time)
  where signal_time is not null;

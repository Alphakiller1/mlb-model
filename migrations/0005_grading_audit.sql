-- Grading audit: explicit ungradeable reasons, void status, closing-line value,
-- build run lineage, and multi-sport readiness for the shared warehouse.

alter table model_leans add column if not exists ungraded_reason text;
alter table model_leans add column if not exists void boolean not null default false;
alter table model_leans add column if not exists closing_odds numeric;
alter table model_leans add column if not exists clv_pts numeric;
alter table model_leans add column if not exists run_id text;
alter table model_leans add column if not exists sport text not null default 'mlb';

create index if not exists idx_model_leans_void
  on model_leans(void, settled);
create index if not exists idx_model_leans_sport
  on model_leans(sport, slate_date);

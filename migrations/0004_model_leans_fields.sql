-- Extend model_leans for correct settlement and audit.
alter table model_leans add column if not exists entry_odds numeric;
alter table model_leans add column if not exists pitcher_name text;

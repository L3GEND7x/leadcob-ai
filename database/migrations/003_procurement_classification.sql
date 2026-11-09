-- v0.2.1 — opcional: a aplicação já aplica estas alterações no startup (ensure_schema).
-- Para PostgreSQL gerenciado manualmente:
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS source_key VARCHAR(180);
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS relevance VARCHAR(20);
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS relevance_reason TEXT;
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS opportunity_class VARCHAR(30);
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS evidence_level VARCHAR(30);
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS commercial_signal VARCHAR(30);
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS deadline TIMESTAMPTZ;
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS estimated_value DOUBLE PRECISION;
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS modality_name VARCHAR(80);
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS origin_url VARCHAR(1000);
CREATE UNIQUE INDEX IF NOT EXISTS uq_opportunities_source_key ON opportunities (source_key);

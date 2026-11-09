-- Aplicar apenas em bancos criados na versão 0.1 que ainda não possuem source_key.
ALTER TABLE opportunities ADD COLUMN source_key VARCHAR(180);
CREATE UNIQUE INDEX uq_opportunities_source_key ON opportunities (source_key);
CREATE TABLE capture_runs (
  id SERIAL PRIMARY KEY, source_name VARCHAR(120) NOT NULL, status VARCHAR(30) NOT NULL DEFAULT 'running',
  records_seen INTEGER NOT NULL DEFAULT 0, records_created INTEGER NOT NULL DEFAULT 0, records_skipped INTEGER NOT NULL DEFAULT 0,
  message TEXT NOT NULL DEFAULT '', started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), finished_at TIMESTAMPTZ NULL
);

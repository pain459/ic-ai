CREATE SCHEMA IF NOT EXISTS incident;

CREATE TABLE IF NOT EXISTS incident.incidents (
  incident_id        BIGINT PRIMARY KEY,
  title              TEXT,
  service            TEXT,
  subdept            TEXT,
  severity           TEXT,
  status             TEXT,
  start_time         TIMESTAMPTZ,
  end_time           TIMESTAMPTZ,
  ttm_minutes        DOUBLE PRECISION,
  root_cause_type    TEXT,
  root_cause_text    TEXT,
  impact_summary     TEXT,
  raw_json           JSONB NOT NULL,
  created_at         TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS incident.followups (
  id            BIGSERIAL PRIMARY KEY,
  incident_id   BIGINT REFERENCES incident.incidents(incident_id) ON DELETE CASCADE,
  action_text   TEXT,
  owner         TEXT,
  due_date      DATE,
  status        TEXT,
  raw_json      JSONB,
  created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_incidents_service ON incident.incidents(service);
CREATE INDEX IF NOT EXISTS idx_incidents_root_cause_type ON incident.incidents(root_cause_type);
CREATE INDEX IF NOT EXISTS idx_incidents_raw_json_gin ON incident.incidents USING GIN (raw_json);

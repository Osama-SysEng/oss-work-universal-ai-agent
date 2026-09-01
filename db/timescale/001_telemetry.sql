-- OSS-Work telemetry schema for PostgreSQL + TimescaleDB.
-- Apply only in a controlled staging environment after review.
-- Tenant context must be set with SET LOCAL app.organization_id = '<uuid>' per transaction.

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS telemetry_events (
    event_id UUID NOT NULL,
    organization_id UUID NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL CHECK (length(source) BETWEEN 1 AND 80),
    kind TEXT NOT NULL CHECK (length(kind) BETWEEN 1 AND 120),
    request_id TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (event_id, event_time),
    UNIQUE (organization_id, request_id)
);

SELECT create_hypertable('telemetry_events', by_range('event_time'), if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS telemetry_events_org_time_idx ON telemetry_events (organization_id, event_time DESC);
CREATE INDEX IF NOT EXISTS telemetry_events_kind_time_idx ON telemetry_events (organization_id, kind, event_time DESC);

ALTER TABLE telemetry_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE telemetry_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS telemetry_events_tenant_policy ON telemetry_events;
CREATE POLICY telemetry_events_tenant_policy ON telemetry_events
    USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid)
    WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id UUID NOT NULL,
    organization_id UUID NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    outcome TEXT NOT NULL,
    request_id TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (event_id, event_time)
);

SELECT create_hypertable('audit_events', by_range('event_time'), if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS audit_events_org_time_idx ON audit_events (organization_id, event_time DESC);
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS audit_events_tenant_policy ON audit_events;
CREATE POLICY audit_events_tenant_policy ON audit_events
    USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid)
    WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid);

CREATE MATERIALIZED VIEW IF NOT EXISTS telemetry_hourly
WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '1 hour', event_time) AS bucket,
       organization_id,
       kind,
       count(*) AS event_count,
       count(DISTINCT source) AS source_count
FROM telemetry_events
GROUP BY bucket, organization_id, kind
WITH NO DATA;

SELECT add_continuous_aggregate_policy('telemetry_hourly',
    start_offset => INTERVAL '7 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour')
WHERE NOT EXISTS (
    SELECT 1 FROM timescaledb_information.jobs
    WHERE proc_name = 'policy_refresh_continuous_aggregate'
      AND config->>'mat_hypertable_id' = (SELECT id::text FROM _timescaledb_catalog.hypertable WHERE table_name = 'telemetry_hourly' LIMIT 1)
);

-- Keep raw events only as long as policy allows; choose a period with the data owner.
-- SELECT add_retention_policy('telemetry_events', INTERVAL '90 days');

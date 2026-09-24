-- ============================================================
-- OSS Work — Migration 001: Bootstrap Schema
-- ============================================================

CREATE TABLE IF NOT EXISTS task_requests (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         VARCHAR(64) NOT NULL UNIQUE,
    sender_type     VARCHAR(32) NOT NULL,
    priority        SMALLINT NOT NULL DEFAULT 50,
    safety_policy_id INTEGER NOT NULL DEFAULT 1,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS task_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_request_id UUID NOT NULL REFERENCES task_requests(id) ON DELETE CASCADE,
    status VARCHAR(32) NOT NULL,
    data JSONB,
    errors JSONB,
    latency_ms INTEGER,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_request_id UUID NOT NULL REFERENCES task_requests(id) ON DELETE CASCADE,
    agent_type VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS decision_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_request_id UUID NOT NULL REFERENCES task_requests(id) ON DELETE CASCADE,
    agent_type VARCHAR(64) NOT NULL,
    decision_type VARCHAR(64) NOT NULL,
    detail JSONB NOT NULL,
    justification TEXT,
    agent_name VARCHAR(64) NOT NULL DEFAULT 'system',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(256) NOT NULL UNIQUE,
    version VARCHAR(64) NOT NULL,
    source VARCHAR(256) NOT NULL,
    installed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_agent_runs_started ON agent_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_decision_records_created ON decision_records(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_task_requests_created ON task_requests(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_task_results_request_id ON task_results(task_request_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_request_id ON agent_runs(task_request_id);

-- TimescaleDB hypertables (if extension available)
SELECT create_hypertable('agent_runs', 'started_at', if_not_exists => TRUE);
SELECT create_hypertable('decision_records', 'created_at', if_not_exists => TRUE);

-- Seed default safety policy
INSERT INTO safety_policies (name, description, level, action_threshold, max_sensitive_ops, max_write_ops)
VALUES ('standard', 'Standard safety — read allowed, write gated, external simulation only',
        1, 50, 3, 3)
ON CONFLICT (name) DO NOTHING;

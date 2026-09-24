"""
Full PostgreSQL schema for OSS Work.
Includes: users, interactions, user_profiles, skills, model_usage.
Extended with TimescaleDB hypertables for telemetry.
"""

-- ═══════════════════════════════════════════════════════════════
-- OSS WORK — COMPLETE POSTGRESQL SCHEMA
-- ═══════════════════════════════════════════════════════════════

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For full-text search

-- ── Users ─────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_chat_id VARCHAR(50) UNIQUE,
    username VARCHAR(100),
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    language_preference VARCHAR(10) DEFAULT 'ar',
    subscription_tier VARCHAR(20) DEFAULT 'free',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_active TIMESTAMPTZ DEFAULT NOW(),
    total_tasks INT DEFAULT 0,
    total_tokens INT DEFAULT 0,
    CONSTRAINT users_telegram_unique UNIQUE (telegram_chat_id)
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_users_telegram ON users(telegram_chat_id);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- ── Interactions ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS interactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    task TEXT NOT NULL,
    completed_thought TEXT,  -- Ultra IQ completion
    agents_used TEXT[],
    model_used VARCHAR(50),
    result JSONB,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    tokens_in INT DEFAULT 0,
    tokens_out INT DEFAULT 0,
    tokens_used INT DEFAULT 0,
    latency_ms INT,
    invented BOOLEAN DEFAULT FALSE,  -- Ultra IQ invention flag
    imagination_threads INT DEFAULT 0,
    imagination_confidence FLOAT,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- Full-text search index on tasks
CREATE INDEX IF NOT EXISTS idx_interactions_task_fts ON interactions USING gin(to_tsvector('arabic', task));

-- Index for user lookups
CREATE INDEX IF NOT EXISTS idx_interactions_user ON interactions(user_id);
CREATE INDEX IF NOT EXISTS idx_interactions_timestamp ON interactions(timestamp);
CREATE INDEX IF NOT EXISTS idx_interactions_status ON interactions(status);

-- TimescaleDB hypertable for time-series queries
SELECT create_hypertable('interactions', 'timestamp', if_not_exists => TRUE);

-- Continuous aggregate for hourly stats
CREATE MATERIALIZED VIEW IF NOT EXISTS interactions_hourly_agg
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', timestamp) AS bucket,
    user_id,
    COUNT(*) AS task_count,
    SUM(tokens_used) AS total_tokens,
    AVG(latency_ms) AS avg_latency,
    COUNT(*) FILTER (WHERE status = 'completed') AS completed_count,
    COUNT(*) FILTER (WHERE status = 'failed') AS failed_count,
    COUNT(*) FILTER (WHERE invented = TRUE) AS invented_count
FROM interactions
GROUP BY bucket, user_id
WITH NO DATA;

-- ── User Profiles ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    expertise_level VARCHAR(20) DEFAULT 'intermediate',
    preferred_language VARCHAR(10) DEFAULT 'ar',
    preferred_model VARCHAR(50),
    active_domains TEXT[],
    task_success_rate FLOAT DEFAULT 0.0,
    total_tasks INT DEFAULT 0,
    imagination_requests INT DEFAULT 0,
    average_latency_ms INT DEFAULT 0,
    preferred_communication_style VARCHAR(50) DEFAULT 'balanced',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Skills ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) UNIQUE NOT NULL,
    source VARCHAR(50) NOT NULL,  -- github/npm/pip/huggingface
    version VARCHAR(30),
    capability VARCHAR(100),
    description TEXT,
    install_path TEXT,
    repository_url TEXT,
    stars INT DEFAULT 0,
    active BOOLEAN DEFAULT TRUE,
    installed_at TIMESTAMPTZ DEFAULT NOW(),
    checksum VARCHAR(32),
    last_used TIMESTAMPTZ,
    usage_count INT DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_skills_capability ON skills(capability);
CREATE INDEX IF NOT EXISTS idx_skills_active ON skills(active);

-- ── Model Usage ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS model_usage (
    id BIGSERIAL PRIMARY KEY,
    model_id VARCHAR(50) NOT NULL,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    provider VARCHAR(50),
    tokens_in INT DEFAULT 0,
    tokens_out INT DEFAULT 0,
    cost_usd FLOAT DEFAULT 0.0,
    latency_ms INT,
    success BOOLEAN,
    task_type VARCHAR(50),
    route VARCHAR(20),  -- api, browser, local, fallback
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_model_usage_model ON model_usage(model_id);
CREATE INDEX IF NOT EXISTS idx_model_usage_timestamp ON model_usage(timestamp);

-- TimescaleDB hypertable
SELECT create_hypertable('model_usage', 'timestamp', if_not_exists => TRUE);

-- ── Agent Execution Logs ───────────────────────────────────────

CREATE TABLE IF NOT EXISTS agent_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    agent_type VARCHAR(50) NOT NULL,
    task TEXT,
    status VARCHAR(20) NOT NULL,
    execution_time_ms INT,
    tokens_used INT DEFAULT 0,
    result_summary JSONB,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_executions_agent ON agent_executions(agent_type);
CREATE INDEX IF NOT EXISTS idx_agent_executions_timestamp ON agent_executions(timestamp);

-- ── Audit Log ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    actor VARCHAR(100),
    target VARCHAR(200),
    outcome VARCHAR(50),
    details JSONB,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);

-- ── Rate Limiting ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS rate_limits (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    window_start TIMESTAMPTZ NOT NULL,
    request_count INT DEFAULT 0,
    token_count INT DEFAULT 0
);

-- ── Notifications ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    message TEXT,
    type VARCHAR(50) DEFAULT 'info',
    read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON notifications(user_id, read) WHERE NOT read;

-- ── Comments / Feedback ───────────────────────────────────────

CREATE TABLE IF NOT EXISTS feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    interaction_id UUID REFERENCES interactions(id) ON DELETE CASCADE,
    rating INT CHECK (rating >= 1 AND rating <= 5),
    comment TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Row-Level Security (multi-tenant) ─────────────────────────

ALTER TABLE interactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE skills ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

-- Policy: users can only see their own data
CREATE POLICY user_isolation_policy ON users
    FOR ALL USING (telegram_chat_id = current_setting('app.current_user_chat_id', TRUE));

CREATE POLICY interactions_isolation_policy ON interactions
    FOR ALL USING (
        user_id IN (
            SELECT id FROM users WHERE telegram_chat_id = current_setting('app.current_user_chat_id', TRUE)
        )
    );

-- ── Sample Data (for testing) ──────────────────────────────────

-- Insert a test user (only if not exists)
INSERT INTO users (telegram_chat_id, username, first_name, language_preference, subscription_tier)
VALUES ('test_user_001', 'osswork_test', 'OSS Work', 'ar', 'free')
ON CONFLICT (telegram_chat_id) DO NOTHING;

-- Insert a test interaction
INSERT INTO interactions (user_id, task, status, agents_used, model_used, result, tokens_used, latency_ms, invented)
SELECT id, 'Test task for schema verification', 'completed', ARRAY['orchestrator', 'code'], 'gemini_flash',
       '{"status": "completed", "data": {"result": "success"}}'::jsonb,
       150, 2500, FALSE
FROM users WHERE telegram_chat_id = 'test_user_001'
LIMIT 1;

-- Insert a test profile
INSERT INTO user_profiles (user_id, expertise_level, preferred_language, task_success_rate, total_tasks)
SELECT id, 'advanced', 'ar', 0.95, 1
FROM users WHERE telegram_chat_id = 'test_user_001'
ON CONFLICT (user_id) DO NOTHING;

-- ── Views for dashboards ──────────────────────────────────────

-- User stats view
CREATE OR REPLACE VIEW user_stats AS
SELECT
    u.id,
    u.telegram_chat_id,
    u.username,
    u.first_name,
    u.language_preference,
    u.subscription_tier,
    u.total_tasks,
    COALESCE(up.task_success_rate, 0) AS success_rate,
    COUNT(i.id) AS total_interactions,
    COUNT(i.id) FILTER (WHERE i.status = 'completed') AS completed_tasks,
    COUNT(i.id) FILTER (WHERE i.status = 'failed') AS failed_tasks,
    COALESCE(SUM(i.tokens_used), 0) AS total_tokens,
    AVG(i.latency_ms) AS avg_latency,
    MAX(i.timestamp) AS last_activity
FROM users u
LEFT JOIN interactions i ON u.id = i.user_id
LEFT JOIN user_profiles up ON u.id = up.user_id
GROUP BY u.id, up.task_success_rate;

-- Model usage dashboard view
CREATE OR REPLACE VIEW model_usage_dashboard AS
SELECT
    model_id,
    provider,
    COUNT(*) AS request_count,
    SUM(tokens_in + tokens_out) AS total_tokens,
    AVG(latency_ms) AS avg_latency,
    AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) AS success_rate,
    DATE_TRUNC('day', timestamp) AS day
FROM model_usage
GROUP BY model_id, provider, DATE_TRUNC('day', timestamp);

-- ── Function: Update user last active ─────────────────────────

CREATE OR REPLACE FUNCTION update_user_last_active(p_chat_id VARCHAR)
RETURNS VOID AS $$
BEGIN
    UPDATE users
    SET last_active = NOW()
    WHERE telegram_chat_id = p_chat_id;
END;
$$ LANGUAGE plpgsql;

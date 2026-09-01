from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_timescale_migration_contains_core_controls():
    sql = (ROOT / "db" / "timescale" / "001_telemetry.sql").read_text(encoding="utf-8")
    assert "create_hypertable" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "WITH (timescaledb.continuous)" in sql
    assert "UNIQUE (organization_id, request_id)" in sql


def test_staging_database_is_loopback_only_and_requires_secrets():
    compose = (ROOT / "deploy" / "docker-compose.timescale.yml").read_text(encoding="utf-8")
    assert '127.0.0.1:${TIMESCALE_PORT:-6543}:5432' in compose
    assert "POSTGRES_PASSWORD_FILE" in compose
    assert "TIMESCALE_IMAGE:?" in compose


def test_frontend_contains_no_live_network_route():
    frontend = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "web" / "src").rglob("*.tsx"))
    assert "fetch(" not in frontend
    assert "child_process" not in frontend

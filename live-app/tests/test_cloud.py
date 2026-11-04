"""The Supabase capability layer (osv_cloud): config discovery, scaffold
generation, and the live smoke probe — all offline with a mocked urlopen.
Competitive-analysis origin: OnSpace.AI's managed backend is Supabase (their
own FAQ says so); this gives OSS Work's agent the same power."""

import osv_agent as ag
import osv_cloud as cloud


def _clear_env(monkeypatch):
    for k in ("OSV_SUPABASE_URL", "OSV_SUPABASE_ANON_KEY",
              "OSV_SUPABASE_SERVICE_KEY", "SUPABASE_URL", "SUPABASE_ANON_KEY"):
        monkeypatch.delenv(k, raising=False)


def test_missing_keys_gets_the_remedy_not_a_fake_success(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    ok, msg = cloud.tool_supabase_status(ag.AgentContext(tmp_path, "t"))
    assert not ok
    assert "supabase.com" in msg and "OSV_SUPABASE_URL" in msg


def test_status_pings_the_real_rest_root(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("OSV_SUPABASE_URL", "https://abc.supabase.co")
    monkeypatch.setenv("OSV_SUPABASE_ANON_KEY", "anon123")
    seen = {}

    def fake_http(url, headers, timeout=15):
        seen.update(url=url, headers=headers)
        return 200, "[]"

    monkeypatch.setattr(cloud, "_http", fake_http)
    ok, msg = cloud.tool_supabase_status(ag.AgentContext(tmp_path, "t"))
    assert ok and "يستجيب" in msg
    assert seen["url"].endswith("/rest/v1/")
    assert seen["headers"]["apikey"] == "anon123"
    assert seen["headers"]["Authorization"] == "Bearer anon123"


def test_status_reports_a_bad_key_honestly(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("OSV_SUPABASE_URL", "https://abc.supabase.co")
    monkeypatch.setenv("OSV_SUPABASE_ANON_KEY", "wrong")
    monkeypatch.setattr(cloud, "_http", lambda u, h, timeout=15: (401, "{}"))
    ok, msg = cloud.tool_supabase_status(ag.AgentContext(tmp_path, "t"))
    assert not ok and "401" in msg


def test_setup_writes_four_files_and_never_the_service_key(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("OSV_SUPABASE_URL", "https://abc.supabase.co")
    monkeypatch.setenv("OSV_SUPABASE_ANON_KEY", "anon123")
    monkeypatch.setenv("OSV_SUPABASE_SERVICE_KEY", "SECRET-SERVICE-KEY")
    ctx = ag.AgentContext(tmp_path, "t")
    ok, msg = cloud.tool_supabase_setup(ctx, title="عيادة الأسنان")
    assert ok and "4" in msg
    schema = (tmp_path / "supabase" / "schema.sql").read_text(encoding="utf-8")
    js = (tmp_path / "supabase" / "client.js").read_text(encoding="utf-8")
    steps = (tmp_path / "supabase" / "SETUP-STEPS.md").read_text(encoding="utf-8")
    assert "enable row level security" in schema
    assert "auth.uid() = user_id" in schema
    assert js.count("https://abc.supabase.co") == 1 and "anon123" in js
    assert "SQL Editor" in steps
    all_text = "".join(
        p.read_text(encoding="utf-8") for p in (tmp_path / "supabase").iterdir())
    assert "SECRET-SERVICE-KEY" not in all_text  # service key written NOWHERE


def test_smoke_reads_the_table_and_diagnoses_missing_schema(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("OSV_SUPABASE_URL", "https://abc.supabase.co")
    monkeypatch.setenv("OSV_SUPABASE_ANON_KEY", "anon123")
    ctx = ag.AgentContext(tmp_path, "t")

    monkeypatch.setattr(cloud, "_http", lambda u, h, timeout=15: (200, "[{}]"))
    ok, msg = cloud.tool_supabase_smoke(ctx, "items")
    assert ok and "حي" in msg

    monkeypatch.setattr(cloud, "_http",
                        lambda u, h, timeout=15: (404, '{"code":"PGRST205"}'))
    ok, msg = cloud.tool_supabase_smoke(ctx, "items")
    assert not ok and "schema.sql" in msg and "SQL Editor" in msg


def test_agent_tools_registry_exposes_the_three(monkeypatch):
    for name in ("supabase_status", "supabase_setup", "supabase_smoke"):
        assert name in ag.TOOLS, name
        assert name in ag.EXECUTABLE, name

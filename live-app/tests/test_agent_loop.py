"""The agent loop: honesty rules, adaptive effort, self-check, loop recovery.

Converted from the measured session of 1 Nov 2026 (lessons 38-40) into the
permanent regression suite. Everything runs OFFLINE (the LLM is mocked)."""

import json
import time

import oss_work_live as m
import osv_agent as ag


def _ctx(tmp):
    return ag.AgentContext(tmp, "t")


# ---------------------------------------------------------------- dual-process

def test_task_weight_simple_is_low():
    assert ag.task_weight("اشرح لي الفرق بين list و tuple") == "low"


def test_task_weight_multi_part_build_is_hard():
    assert ag.task_weight("ابنِ مشروعاً كاملاً: واجهة + خلفية + اختبارات") == "hard"


def test_task_weight_long_text_is_hard():
    assert ag.task_weight("وصف طويل " * 30) == "hard"


# ---------------------------------------------------------------- self-check

def test_done_over_unexecuted_tests_bounces_then_runs_them(tmp_path, monkeypatch):
    """The model wrote tests but never ran them → bounced once; the second
    reply runs the test via REAL bash inside the workspace."""
    replies = [
        # reply 1: writes module+test then declares done → must bounce
        ('```json\n{"tool": "write_file", "args": {"path": "calc.py", '
         '"content": "def add(a, b):\\n    return a - b\\n"}}\n```\n'
         '```json\n{"tool": "write_file", "args": {"path": "test_calc.py", '
         '"content": "from calc import add\\nassert add(2, 3) == 5\\n"}}\n```\n'
         '```json\n{"tool": "done", "args": {"answer": "أنجزت!"}}\n```'),
        # reply 2: runs the (failing) test for real → done accepted, but the
        # mandatory honesty note must relay the failure
        ('```json\n{"tool": "bash", "args": {"command": "python test_calc.py"}}'
         '\n```\n'
         '```json\n{"tool": "done", "args": {"answer": "شغّلته"}}\n```'),
    ]
    calls = []

    def fake_gw(cfg, msgs, effort="none", timeout=300, max_tokens=3000):
        calls.append(msgs[-1]["content"])
        return [replies[len(calls) - 1]]

    monkeypatch.setattr(m, "_gw_stream", fake_gw)
    ctx = ag.AgentContext(tmp_path, "t")
    final, _ok = ag.run_agent("اكتب وحدة calc مع اختبارها", ctx,
                              [{}], lambda e: None, max_steps=6)
    assert any("لم تشغّلها" in c for c in calls)          # the bounce fired
    assert any(s["tool"] == "bash" for s in ctx.steps)    # ran the tests for real
    assert (tmp_path / "calc.py").is_file()
    assert "[ملاحظة النظام" in final or "فشل" in final     # failure not hidden


# ---------------------------------------------------------------- loop recovery

def test_infinite_loop_gets_nudge_then_honest_stop(tmp_path, monkeypatch):
    same = '```json\n{"tool": "list_dir", "args": {"path": "."}}\n```'
    calls = []

    def fake_gw(cfg, msgs, effort="none", timeout=300, max_tokens=3000):
        calls.append(msgs[-1]["content"])
        return [same]

    monkeypatch.setattr(m, "_gw_stream", fake_gw)
    final, ok = ag.run_agent("افحص المساحة", _ctx(tmp_path), [{}],
                             lambda e: None, max_steps=14)
    assert any("غيّر استراتيجيتك" in c for c in calls)   # first loop → nudge
    assert not ok and "حلقة مكررة" in final              # second → honest stop


# ---------------------------------------------------------------- require_steps

def test_done_without_successful_work_is_bounced(tmp_path, monkeypatch):
    replies = [
        '```json\n{"tool": "done", "args": {"answer": "أنجزت بلا عمل!"}}\n```',
        ('```json\n{"tool": "write_file", "args": {"path": "hello.py", '
         '"content": "print(1)"}}\n```\n'
         '```json\n{"tool": "done", "args": {"answer": "كتبت فعلاً"}}\n```'),
    ]
    calls = []

    def fake_gw(cfg, msgs, effort="none", timeout=300, max_tokens=3000):
        calls.append(msgs[-1]["content"])
        return [replies[len(calls) - 1]]

    monkeypatch.setattr(m, "_gw_stream", fake_gw)
    final, ok = ag.run_agent("اكتب ملف hello.py", _ctx(tmp_path), [{}],
                             lambda e: None, max_steps=6, require_steps=1)
    assert ok and final == "كتبت فعلاً"
    assert (tmp_path / "hello.py").is_file()
    assert any("ممنوع الإنهاء" in c for c in calls)


def test_failed_write_does_not_count_toward_require_steps(tmp_path, monkeypatch):
    """A FAILED action is not work: done right after it must bounce."""
    replies = [
        ('```json\n{"tool": "bash", "args": {"command": "exit 3"}}\n```\n'
         '```json\n{"tool": "done", "args": {"answer": "أنجزت"}}\n```'),
        ('```json\n{"tool": "write_file", "args": {"path": "ok.txt", '
         '"content": "x"}}\n```\n'
         '```json\n{"tool": "done", "args": {"answer": "الآن أنجزت فعلاً"}}\n```'),
    ]
    calls = []

    def fake_gw(cfg, msgs, effort="none", timeout=300, max_tokens=3000):
        calls.append(msgs[-1]["content"])
        return [replies[len(calls) - 1]]

    monkeypatch.setattr(m, "_gw_stream", fake_gw)
    _final, ok = ag.run_agent("مهمة", _ctx(tmp_path), [{}], lambda e: None,
                              max_steps=6, require_steps=1)
    assert ok
    assert any("ممنوع الإنهاء" in c for c in calls)


# ------------------------------------------------- the 8 Nov 2026 live flaw

def test_build_task_zero_step_done_bounces_then_builds(tmp_path, monkeypatch):
    """Job j1794130293-1: "ابن لي موقع لمتابعة كرة القدم" — the model submitted
    a textual PLAN as done with ZERO tools. Production passed require_steps=0
    so the old gate never fired. The build-task auto-floor must bounce it, and
    the second reply (a real write) completes."""
    task = "ابن لي موقع لمتابعة كرة القدم احداث ومباريات"
    assert ag._is_build_task(task)
    replies = [
        '```json\n{"tool": "done", "args": {"answer": "1. الخطة 2. الخطة"}}\n```',
        ('```json\n{"tool": "write_file", "args": {"path": "index.html", '
         '"content": "<h1>الفرق</h1>"}}\n```\n'
         '```json\n{"tool": "done", "args": {"answer": "بنيت الصفحة"}}\n```'),
    ]
    calls = []

    def fake_gw(cfg, msgs, effort="none", timeout=300, max_tokens=3000):
        calls.append(msgs[-1]["content"])
        return [replies[len(calls) - 1]]

    monkeypatch.setattr(m, "_gw_stream", fake_gw)
    final, ok = ag.run_agent(task, _ctx(tmp_path), [{}], lambda e: None,
                             max_steps=6)          # NO require_steps passed —
    assert ok and "بنيت الصفحة" == final           # the floor comes from _is_build_task
    assert (tmp_path / "index.html").is_file()
    assert any("ممنوع الإنهاء" in c for c in calls)


def test_build_task_refusing_to_act_dies_honestly_not_fakely(tmp_path, monkeypatch):
    """After the one bounce the model STILL plans instead of building: the
    job must end ok=False with a mandatory disclosure — never a fake
    «اكتمل» driven by a plan text."""
    task = "ابن لي متجراً بسيطاً"
    assert ag._is_build_task(task)

    def fake_gw(cfg, msgs, effort="none", timeout=300, max_tokens=3000):
        return ['```json\n{"tool": "done", "args": {"answer": "الخطة فقط"}}\n```']

    monkeypatch.setattr(m, "_gw_stream", fake_gw)
    final, ok = ag.run_agent(task, _ctx(tmp_path), [{}], lambda e: None,
                             max_steps=6)
    assert ok is False
    assert "خطة فقط" in final
    assert "إفصاح نظامي" in final and "لا شيء بُني" in final


def test_chat_task_first_turn_done_is_still_accepted(tmp_path, monkeypatch):
    """Pure chat has no workspace contract: one-turn done stays legitimate —
    the floor must NOT probe every conversational answer."""
    assert not ag._is_build_task("ما هي عاصمة فرنسا؟")
    assert not ag._is_build_task("اشرح لي الفرق بين list و tuple")

    def fake_gw(cfg, msgs, effort="none", timeout=300, max_tokens=3000):
        return ['```json\n{"tool": "done", "args": {"answer": "الرياض"}}\n```']

    monkeypatch.setattr(m, "_gw_stream", fake_gw)
    final, ok = ag.run_agent("ما هي عاصمة الدولة المصرية القديمة؟",
                             _ctx(tmp_path), [{}], lambda e: None, max_steps=4)
    assert ok and final == "الرياض"


def test_all_providers_refused_reports_who_and_why(tmp_path, monkeypatch):
    """Job j1794130293-1 also proved a SECOND flaw: with every provider down
    the loop returned ("", False) — the UI showed a bare فشل with no reason.
    The honest death must name each provider and its remedy."""
    task = "اشرح لي التراث"
    assert not ag._is_build_task(task)

    def dead_gw(cfg, msgs, effort="none", timeout=300, max_tokens=3000):
        raise ConnectionError(f"[WinError 10061] {cfg.get('provider')} refused")

    monkeypatch.setattr(m, "_gw_stream", dead_gw)
    chain = [{"provider": "oss_local"}, {"provider": "gemini"}]
    final, ok = ag.run_agent(task, _ctx(tmp_path), chain, lambda e: None,
                             max_steps=4)
    assert ok is False and final          # NOT the silent empty string
    assert "oss_local" in final and "gemini" in final
    assert "127.0.0.1:11400" in final and "أعد إرسال المهمة نفسها" in final


# ---------------------------------------------------------------- honesty relay

def test_hidden_failure_is_appended_to_final(tmp_path, monkeypatch):
    """A tool failure the model's done-answer ignores gets appended verbatim."""
    replies = [
        ('```json\n{"tool": "bash", '
         '"args": {"command": "python missing_script_xyz.py"}}\n```\n'
         '```json\n{"tool": "done", "args": {"answer": "كل شيء تمام"}}\n```'),
    ]

    def fake_gw(cfg, msgs, effort="none", timeout=300, max_tokens=3000):
        return [replies[0]]

    monkeypatch.setattr(m, "_gw_stream", fake_gw)
    final, ok = ag.run_agent("مهمة", _ctx(tmp_path), [{}], lambda e: None,
                             max_steps=4, require_steps=0)
    # ok=True (final text exists) but the failed bash step MUST surface
    assert "[ملاحظة النظام" in final
    assert ok is True


# ------------------------------------------------- the 2 Nov 2026 live flaw

def test_truncated_action_is_nudged_to_split_then_work_accepted(tmp_path, monkeypatch):
    """A write_file action bigger than the token limit gets CUT mid-JSON →
    parse fails → the loop used to ship the RAW JSON as the final answer with
    ZERO steps (the user saw raw ```json text and nothing built). The fix:
    one split-the-file nudge, then the retry lands real files."""
    huge = '{"tool": "write_file", "args": {"path": "school.html", "content": "' \
        + ("ب" * 5000)      # starts like a real action, never closes
    calls = []

    def fake_gw(cfg, msgs, effort="none", timeout=300, max_tokens=3000):
        calls.append((msgs[-1]["content"], max_tokens))
        if len(calls) == 1:
            return ['```json\n' + huge]        # truncated mid-content
        return [('```json\n{"tool": "write_file", "args": {"path": "index.html", '
                '"content": "<h1>مدرسة</h1>"}}\n```\n'
                '```json\n{"tool": "done", "args": {"answer": "بدأت الصفحة الرئيسية"}}\n```')]

    monkeypatch.setattr(m, "_gw_stream", fake_gw)
    ctx = ag.AgentContext(tmp_path, "t")
    final, ok = ag.run_agent("ابن لي موقعاً لمدارس", ctx, [{}], lambda e: None,
                             max_steps=6)
    assert ok is True                                   # the work LANDED
    assert (tmp_path / "index.html").is_file()          # real file, not prose
    assert "انقطع" in calls[1][0]                        # the split nudge was sent
    assert not final.startswith("```json")              # raw JSON never shipped


def test_repeated_truncation_dies_honestly_not_as_raw_json(tmp_path, monkeypatch):
    """If the model keeps truncating even after the nudge, the loop dies with
    an honest 'nothing executed' — the raw JSON is NEVER the answer."""
    huge = '{"tool": "write_file", "args": {"path": "x.html", "content": "' \
        + ("ب" * 5000)
    calls = []

    def fake_gw(cfg, msgs, effort="none", timeout=300, max_tokens=3000):
        calls.append(msgs[-1]["content"])
        return ['```json\n' + huge]                     # truncates forever

    monkeypatch.setattr(m, "_gw_stream", fake_gw)
    ctx = ag.AgentContext(tmp_path, "t")
    final, ok = ag.run_agent("مهمة بناء", ctx, [{}], lambda e: None, max_steps=6)
    assert ok is False
    assert "لا شيء نُفذ" in final
    assert "```json" not in final                       # never the raw command


def test_hard_build_gets_real_token_room(tmp_path, monkeypatch):
    """Root cause of the flaw: 3000-3500 max_tokens cannot hold a real HTML
    file. A build task must reserve room for the file itself."""
    seen = []

    def fake_gw(cfg, msgs, effort="none", timeout=300, max_tokens=3000):
        seen.append(max_tokens)
        return ['```json\n{"tool": "done", "args": {"answer": "تم"}}\n```']

    monkeypatch.setattr(m, "_gw_stream", fake_gw)
    ag.run_agent("ابنِ مشروعاً كاملاً: واجهة + خلفية + اختبارات", _ctx(tmp_path),
                 [{}], lambda e: None, max_steps=2)
    assert seen[0] >= 8000


def test_parse_actions_tolerates_fence_without_json_tag():
    assert ag.parse_actions('```\n{"tool": "bash", "args": {"command": "dir"}}\n```')


# ------------------------------------------------- fullstack completeness gate

def test_wants_fullstack_flags_build_tasks_with_layers():
    assert ag._wants_fullstack(
        "ابن لي موقعاً لمدارس يشمل كل الخدمات التعليمية وطريقة التسجيل سواء معلم او طالب")
    assert ag._wants_fullstack("أنشئ تطبيق بواجهة وخلفية وقاعدة بيانات")
    assert not ag._wants_fullstack("اكتب لي صفحة هبوط بسيطة لشركة")
    assert not ag._wants_fullstack("اشرح لي الفرق بين list و tuple")


def test_fullstack_done_is_bounced_until_backend_exists(tmp_path, monkeypatch):
    """The 2 Nov feedback: the task asked واجهة+خلفية+قاعدة بيانات — the model
    wrote index.html only and declared done. The gate bounces ONCE demanding
    the real layers; the second wave lands server.py + schema.sql and passes."""
    calls = []

    def fake_gw(cfg, msgs, effort="none", timeout=300, max_tokens=3000):
        calls.append(msgs[-1]["content"])
        if len(calls) == 1:
            return [('```json\n{"tool": "write_file", "args": {"path": "index.html", '
                     '"content": "<h1>مدرسة</h1>"}}\n```\n'
                     '```json\n{"tool": "done", "args": {"answer": "تم بناء الموقع"}}\n```')]
        if len(calls) == 2:
            # the bounce MUST name the missing layers concretely
            assert "schema.sql" in calls[-1] and "server.py" in calls[-1]
            return [('```json\n{"tool": "write_file", "args": {"path": "schema.sql", '
                     '"content": "CREATE TABLE students(id INTEGER PRIMARY KEY, name TEXT);"}}\n```\n'
                     '```json\n{"tool": "write_file", "args": {"path": "server.py", '
                     '"content": "from http.server import HTTPServer"}}\n```')]
        return ['```json\n{"tool": "done", "args": {"answer": "أُنشئت القاعدة والخادم"}}\n```']

    monkeypatch.setattr(m, "_gw_stream", fake_gw)
    ctx = ag.AgentContext(tmp_path, "t")
    _final, ok = ag.run_agent(
        "ابن لي موقعاً لمدارس بواجهة وخلفية وقاعدة بيانات وطريقة تسجيل",
        ctx, [{}], lambda e: None, max_steps=8)
    assert ok is True
    assert (tmp_path / "server.py").is_file()        # the REAL layers landed
    assert (tmp_path / "schema.sql").is_file()
    assert (tmp_path / "index.html").is_file()
    assert any("schema.sql" in c for c in calls[1:])  # the bounce fired once


# ------------------------------------------------- honest death credits work

def test_ws_files_lists_relative_names_not_pyc(tmp_path):
    (tmp_path / "server.py").write_text("x", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "server.cpython-314.pyc").write_text(
        "x", encoding="utf-8")
    assert ag._ws_files(tmp_path) == ["server.py"]


def test_truncation_death_credits_what_landed(tmp_path, monkeypatch):
    """The 2 Nov live death said 'nothing executed' while server.py and
    schema.sql sat in the workspace — honest failure must credit real work."""
    huge = "x" * 40000
    calls = []

    def fake_gw(cfg, msgs, effort="none", timeout=300, max_tokens=3000):
        calls.append(msgs[-1]["content"])
        return ['```json\n' + huge]          # always truncated

    monkeypatch.setattr(m, "_gw_stream", fake_gw)
    (tmp_path / "server.py").write_text("s", encoding="utf-8")
    final, ok = ag.run_agent("مهمة", ag.AgentContext(tmp_path, "t"), [{}],
                             lambda e: None, max_steps=8)
    assert ok is False                        # honest death, no fake success
    assert "server.py" in final               # ...but credits what DID land
    assert any("8192" in c for c in calls)    # 2nd nudge teaches the physics


# ---------------------------------------------------------------- smoke gate

GOOD_SERVER = '''from http.server import HTTPServer, BaseHTTPRequestHandler
import json

class H(BaseHTTPRequestHandler):
    def _j(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self._j(200, {"ok": True})

    def do_POST(self):
        if self.path == '/api/register':
            n = int(self.headers.get('Content-Length', 0))
            d = json.loads(self.rfile.read(n))
            self._j(200, {"registered": d["email"]})
        else:
            self._j(404, {"error": "not found"})

    def log_message(self, *a):
        pass

if __name__ == '__main__':
    HTTPServer(('', 8000), H).serve_forever()
'''

DEADLOCK_SERVER = GOOD_SERVER.replace(
    "            n = int(self.headers.get('Content-Length', 0))\n"
    "            d = json.loads(self.rfile.read(n))",
    "            d = json.loads(self.rfile.read())")   # the live 3 Nov bug

# The 4 Nov restaurant crash: a POST /api/orders handler that passes early
# validation ({} → clean 400) but dies with an unhandled exception
# (double fetchone → TypeError → dropped connection) once the body is VALID
# and the settings row exists. Registration probes passed; the generic probe
# with a canonical body must catch it.
CRASH_SERVER = GOOD_SERVER.replace(
    '''        else:
            self._j(404, {"error": "not found"})''',
    '''        elif self.path == '/api/orders':
            n = int(self.headers.get('Content-Length', 0))
            d = json.loads(self.rfile.read(n))
            if not d.get('items'):
                self._j(400, {"error": "Order must have at least one item"})
                return
            conn = __import__('sqlite3').connect(':memory:')
            cur = conn.execute("SELECT value FROM settings WHERE key='x'")
            cur.fetchone()                        # consumes the row
            v = float(cur.fetchone()['value'])    # second call: None['value']
            self._j(200, {"total": v})
        else:
            self._j(404, {"error": "not found"})''')


def test_smoke_test_boots_and_probes_a_working_server(tmp_path):
    ok, detail = ag._smoke_test(_ws_with(tmp_path, GOOD_SERVER))
    assert ok, detail


def test_smoke_test_catches_the_live_rfile_deadlock(tmp_path):
    ok, detail = ag._smoke_test(_ws_with(tmp_path, DEADLOCK_SERVER))
    assert not ok
    assert "علّق" in detail or "فشلاً" in detail


def test_smoke_generic_post_probe_passes_validation_4xx(tmp_path):
    """POST {} to every /api route: 4xx validation replies are HEALTHY —
    the gate must accept the good server unchanged (no false bounce)."""
    ok, detail = ag._smoke_test(_ws_with(tmp_path, GOOD_SERVER))
    assert ok, detail


def test_smoke_generic_post_probe_catches_crashing_write_path(tmp_path):
    """A POST route that passes early validation but drops the connection on
    a valid body is an unhandled crash → the gate bounces with the endpoint
    and the remedy."""
    ok, detail = ag._smoke_test(_ws_with(tmp_path, CRASH_SERVER))
    assert not ok
    assert "/api/orders" in detail
    assert "ينهار" in detail


# --- the 4 Nov ghost-job bug: a bash child that never exits (the agent's own
# test server) survives the timeout kill when launched through a stub
# (cmd /c → python), keeps the pipes open, and communicate() waits for its
# EOF forever — the job loop thread froze at 34 events for an hour with
# state=running. The fix kills the WHOLE tree via taskkill /T.

def test_tool_bash_timeout_kills_the_whole_tree(tmp_path, monkeypatch):
    """A never-exiting child (and its grandchild, both holding the pipes) must
    not defeat the bash timeout: the tool returns the tree-kill message and
    the call terminates quickly."""
    monkeypatch.setattr(ag, "BASH_TIMEOUT_S", 3)
    ctx = ag.AgentContext(tmp_path, "t")
    (tmp_path / "hang_helper.py").write_text(
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])\n"
        "time.sleep(300)\n", encoding="utf-8")
    t0 = time.monotonic()
    ok, obs = ag.tool_bash(ctx, "python hang_helper.py")
    took = time.monotonic() - t0
    assert not ok
    assert took < 60, f"tool_bash hung {took:.0f}s past its 3s timeout"
    assert "شجرته" in obs


def test_tool_bash_normal_command_still_works(tmp_path):
    """The Popen rewrite must not break plain fast commands."""
    ctx = ag.AgentContext(tmp_path, "t")
    ok, obs = ag.tool_bash(ctx, "echo hello")
    assert ok and "hello" in obs


def _ws_with(ws, server_src: str):
    d = ws / "school_site"
    d.mkdir(parents=True, exist_ok=True)
    (d / "server.py").write_text(server_src, encoding="utf-8")
    return ws


def test_fullstack_done_with_broken_server_is_bounced_then_fixed(
        tmp_path, monkeypatch):
    """The smoke gate in the loop: wave 1 ships the DEADLOCK server + done →
    the gate bounces with the mechanical finding; wave 2 fixes it → done is
    accepted because the REAL smoke passes."""
    calls = []
    dead = json.dumps(DEADLOCK_SERVER)
    good = json.dumps(GOOD_SERVER)

    def fake_gw(cfg, msgs, effort="none", timeout=300, max_tokens=3000):
        calls.append(msgs[-1]["content"])
        src = good if len(calls) >= 2 else dead
        return [('```json\n{"tool": "write_file", "args": {"path": '
                 '"school_site/server.py", "content": ' + src + '}}\n```\n'
                 '```json\n{"tool": "done", "args": {"answer": "تم بناء '
                 'النظام"}}\n```')]

    monkeypatch.setattr(m, "_gw_stream", fake_gw)
    _final, ok = ag.run_agent(
        "ابن لي موقعاً لمدارس بواجهة وخلفية وقاعدة بيانات وتسجيل",
        ag.AgentContext(tmp_path, "t"), [{}], lambda e: None, max_steps=8)
    assert ok is True
    assert (tmp_path / "school_site" / "server.py").is_file()
    assert any("بوابة الدخان" in c for c in calls[1:])   # bounce fired once


def test_simple_static_done_never_bounces(tmp_path, monkeypatch):
    """Control: a task WITHOUT backend keywords accepts a static page —
    the gate must not over-trigger."""
    calls = []

    def fake_gw(cfg, msgs, effort="none", timeout=300, max_tokens=3000):
        calls.append(msgs[-1]["content"])
        return [('```json\n{"tool": "write_file", "args": {"path": "landing.html", '
                 '"content": "<h1>هبوط</h1>"}}\n```\n'
                 '```json\n{"tool": "done", "args": {"answer": "تم"}}\n```')]

    monkeypatch.setattr(m, "_gw_stream", fake_gw)
    _final, ok = ag.run_agent("اكتب لي صفحة هبوط بسيطة",
                              ag.AgentContext(tmp_path, "t"),
                              [{}], lambda e: None, max_steps=6)
    assert ok is True
    assert (tmp_path / "landing.html").is_file()
    assert len(calls) == 1                            # single wave, no bounce

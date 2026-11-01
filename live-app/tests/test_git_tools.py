"""Git tools against REAL git in a REAL temp workspace.

Auto-init, identity setup (local only), commit/diff/log roundtrip, and the
containment law: the allowlist refuses everything else — push is banned
forever."""
import subprocess

import pytest

import osv_agent as ag
import osv_git as gt


@pytest.fixture()
def ctx(tmp_path):
    return ag.AgentContext(tmp_path, "git-test", extra_tools=gt.git_tools())


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          check=False)


def test_status_on_bare_dir_auto_inits(ctx, tmp_path):
    ok, _out = ctx.tools["git_status"]["fn"](ctx)
    assert ok
    assert (tmp_path / ".git").is_dir()            # the auto-init really ran


def test_commit_roundtrip_with_real_git(ctx, tmp_path):
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n",
                                      encoding="utf-8")
    ok, out = ctx.tools["git_commit"]["fn"](ctx, message="أول التزام: جمع صحيح")
    assert ok
    assert "أول التزام" in out
    log_ok, log = ctx.tools["git_log"]["fn"](ctx)
    assert log_ok and "أول التزام" in log
    # clean tree now — status says so honestly
    ok, out = ctx.tools["git_commit"]["fn"](ctx, message="لا شيء")
    assert ok and "لا شيء للالتزام" in out


def test_local_identity_set_never_global(ctx, tmp_path):
    (tmp_path / "x.txt").write_text("hi", encoding="utf-8")
    ctx.tools["git_commit"]["fn"](ctx, message="identity")
    p = _git(tmp_path, "config", "--local", "user.name")
    assert p.returncode == 0 and "OS_V1 Agent" in p.stdout


def test_diff_shows_changes(ctx, tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    ctx.tools["git_commit"]["fn"](ctx, message="base")
    (tmp_path / "a.py").write_text("x = 2  # changed\n", encoding="utf-8")
    ok, out = ctx.tools["git_diff"]["fn"](ctx)
    assert ok and "a.py" in out


def test_push_and_dangerous_subcommands_are_refused(ctx):
    for banned in ("push", "remote", "clone", "fetch", "reset", "clean"):
        ok, out = gt._git(ctx, banned, [])
        assert not ok, banned
        assert "غير مسموح" in out
    ok, out = gt._git(ctx, "push", ["origin", "main"])
    assert not ok and "محظور" in out


def test_commit_without_message_is_guidance(ctx):
    ok, out = ctx.tools["git_commit"]["fn"](ctx, message="  ")
    assert not ok and "message" in out


def test_uncommitted_work_shown_in_status(ctx, tmp_path):
    (tmp_path / "new.py").write_text("y = 2\n", encoding="utf-8")
    ok, out = ctx.tools["git_status"]["fn"](ctx)
    assert ok and "new.py" in out

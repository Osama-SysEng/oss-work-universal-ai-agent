"""Program control: only what the user allowed."""

from __future__ import annotations

import sys
from pathlib import Path

from osv1.tools.program_tools import ProgramRunner, allowlist_from_env


def test_nothing_runs_without_an_allowlist(tmp_path: Path) -> None:
    runner = ProgramRunner(allowlist=[], workspace=tmp_path)
    result = runner.run("python", "--version")
    assert result.ok is False
    assert "no program is allowed" in result.error


def test_a_program_outside_the_allowlist_is_refused(tmp_path: Path) -> None:
    runner = ProgramRunner(allowlist=["git"], workspace=tmp_path)
    result = runner.run("python", "--version")
    assert result.ok is False
    assert "not on the allowlist" in result.error


def test_an_allowed_program_runs_from_the_workspace(tmp_path: Path) -> None:
    runner = ProgramRunner(allowlist=["python"], workspace=tmp_path)
    result = runner.run(sys.executable, "-c \"print('from the program')\"")
    assert result.ok is True, result.error
    assert "from the program" in result.output
    assert result.data["working_directory"] == str(tmp_path.resolve())


def test_the_program_does_not_inherit_the_environment(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OSS_V1_TEST_SECRET", "do-not-leak")
    runner = ProgramRunner(allowlist=["python"], workspace=tmp_path)
    result = runner.run(sys.executable, "-c \"import os;print(os.environ.get('OSS_V1_TEST_SECRET','absent'))\"")
    assert "absent" in result.output


def test_a_missing_program_is_reported(tmp_path: Path) -> None:
    runner = ProgramRunner(allowlist=["definitely-not-installed"], workspace=tmp_path)
    result = runner.run("definitely-not-installed")
    assert result.ok is False
    assert "not found" in result.error


def test_the_allowlist_can_be_read_from_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("OSS_V1_PROGRAM_ALLOWLIST", "git, python ,node")
    assert allowlist_from_env() == ["git", "python", "node"]


def test_the_allowlist_check_ignores_the_path(tmp_path: Path) -> None:
    runner = ProgramRunner(allowlist=["python"], workspace=tmp_path)
    assert runner.allowed("python") is True
    assert runner.allowed(sys.executable) is True
    assert runner.allowed("powershell") is False


def test_a_windows_style_path_is_understood_on_any_platform(tmp_path: Path) -> None:
    from osv1.tools.program_tools import program_name

    assert program_name(r"C:\Python\python.exe") == "python"
    assert program_name("/usr/bin/python3") == "python3"
    assert program_name("python") == "python"

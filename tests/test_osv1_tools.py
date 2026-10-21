"""The tool layer: files, code, sandbox, spreadsheet, dashboard, REA, synthesis."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from osv1.tools.app_synthesis import AppSynthesis
from osv1.tools.code_tools import CodeTools, analyze_source
from osv1.tools.dashboard import build_dashboard_html
from osv1.tools.file_tools import FileTools
from osv1.tools.rea import ReaEngine
from osv1.tools.sandbox import run_python
from osv1.tools.spreadsheet import Sheet, Workbook, evaluate_formula

# ── files ──────────────────────────────────────────────────


def test_file_tools_refuse_a_path_outside_the_granted_root(tmp_path: Path) -> None:
    tools = FileTools(allowed_roots=[tmp_path / "inside"])
    result = tools.read_file(tmp_path / "outside.txt")
    assert result.ok is False
    assert "outside the granted roots" in result.error


def test_file_tools_read_search_and_write(tmp_path: Path) -> None:
    tools = FileTools(allowed_roots=[tmp_path])
    (tmp_path / "a.txt").write_text("alpha beta", encoding="utf-8")
    (tmp_path / "b.txt").write_text("beta gamma", encoding="utf-8")
    assert tools.read_file(tmp_path / "a.txt").ok is True
    found = tools.search_files("beta")
    assert found.ok is True
    assert found.data["count"] == 2
    written = tools.write_file(tmp_path / "c.txt", "content")
    assert written.ok is True
    assert (tmp_path / "c.txt").read_text(encoding="utf-8") == "content"


def test_writing_a_file_records_how_to_undo_it(tmp_path: Path) -> None:
    tools = FileTools(allowed_roots=[tmp_path])
    (tmp_path / "a.txt").write_text("old", encoding="utf-8")
    result = tools.write_file(tmp_path / "a.txt", "new")
    assert result.reversible is True
    assert "restore" in result.rollback.lower()


def test_deleting_a_file_is_marked_as_irreversible(tmp_path: Path) -> None:
    tools = FileTools(allowed_roots=[tmp_path])
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    result = tools.delete_file(tmp_path / "a.txt")
    assert result.ok is True
    assert result.reversible is False
    assert not (tmp_path / "a.txt").exists()


# ── code ──────────────────────────────────────────────────


def test_static_analysis_finds_a_syntax_error() -> None:
    analyzer, _ = analyze_source("def broken(:\n    pass")
    assert analyzer.errors
    assert analyzer.errors[0]["code"] == "syntax-error"


def test_static_analysis_finds_a_possible_secret() -> None:
    # The key is assembled at run time so the repository never holds a
    # string that looks like a real credential.
    source = 'API_KEY = "sk-' + ("a" * 24) + '"\n'
    analyzer, _ = analyze_source(source)
    assert any(finding["code"] == "possible-secret" for finding in analyzer.findings)


def test_static_analysis_counts_the_structure() -> None:
    analyzer, summary = analyze_source("import os\n\nclass A:\n    def b(self):\n        return 1\n")
    assert analyzer.metrics["class_count"] == 1
    assert analyzer.metrics["function_count"] == 1
    assert summary["imports"] == ["os"]


def test_code_tools_report_the_analysis() -> None:
    result = CodeTools().analyze("x = 1\n")
    assert result.ok is True
    assert result.data["metrics"]["function_count"] == 0


# ── sandbox ───────────────────────────────────────────────


def test_the_sandbox_runs_code_and_returns_the_output() -> None:
    result = run_python("print('inside the sandbox')")
    assert result.ok is True
    assert "inside the sandbox" in result.stdout


def test_the_sandbox_blocks_the_network() -> None:
    result = run_python(
        "import socket\n"
        "try:\n"
        "    socket.socket()\n"
        "    print('NETWORK ALLOWED')\n"
        "except OSError as error:\n"
        "    print('BLOCKED')\n"
    )
    assert "BLOCKED" in result.stdout
    assert "NETWORK ALLOWED" not in result.stdout


def test_the_sandbox_does_not_pass_the_parent_environment() -> None:
    os.environ["OSS_V1_TEST_SECRET"] = "do-not-leak"
    try:
        result = run_python("import os\nprint(os.environ.get('OSS_V1_TEST_SECRET', 'absent'))")
        assert "absent" in result.stdout
    finally:
        os.environ.pop("OSS_V1_TEST_SECRET", None)


def test_the_sandbox_stops_code_that_runs_too_long() -> None:
    result = run_python("while True:\n    pass\n", timeout=2.0)
    assert result.timed_out is True
    assert result.ok is False


def test_the_sandbox_reports_a_failing_program() -> None:
    result = run_python("raise SystemExit(3)")
    assert result.ok is False
    assert result.returncode == 3


# ── spreadsheet ───────────────────────────────────────────


def test_a_sheet_is_read_from_csv() -> None:
    sheet = Sheet.from_csv("name,amount\na,10\nb,20\n")
    assert sheet.headers == ["name", "amount"]
    assert len(sheet.rows) == 2


def test_duplicate_rows_are_removed() -> None:
    workbook = Workbook([Sheet.from_csv("email\na@x\na@x\nb@x\n", name="leads")])
    result = workbook.remove_duplicates("leads", ["email"])
    assert result["duplicates_removed"] == 1
    assert len(workbook.sheet("leads").rows) == 2


def test_rows_are_added_filtered_and_sorted() -> None:
    workbook = Workbook([Sheet.from_csv("name,score\na,10\nb,30\n", name="s")])
    workbook.add_rows("s", [{"name": "c", "score": "20"}])
    assert len(workbook.sheet("s").rows) == 3
    workbook.sort_rows("s", "score")
    assert workbook.sheet("s").rows[0]["name"] == "a"
    workbook.filter_rows("s", "name", "b")
    assert len(workbook.sheet("s").rows) == 1


def test_a_computed_column_uses_a_safe_expression() -> None:
    workbook = Workbook([Sheet.from_csv("qty,price\n2,10\n3,5\n", name="s")])
    result = workbook.compute_column("s", "total", "=qty * price")
    assert result["ok"] is True
    assert workbook.sheet("s").rows[0]["total"] == 20


def test_a_formula_cannot_call_anything() -> None:
    try:
        evaluate_formula("__import__('os').system('echo hi')", {})
    except Exception as exc:  # noqa: BLE001 - the point is that it refuses
        assert "unsupported" in str(exc).lower() or "parse" in str(exc).lower()
    else:
        raise AssertionError("the formula evaluator accepted a call")


def test_a_group_sum_totals_the_values() -> None:
    workbook = Workbook([Sheet.from_csv("team,amount\na,10\na,5\nb,7\n", name="s")])
    totals = workbook.group_sum("s", "team", "amount")
    assert totals[0]["team"] == "a"
    assert totals[0]["amount"] == 15


def test_an_xlsx_workbook_round_trips(tmp_path: Path) -> None:
    workbook = Workbook([Sheet.from_csv("name,amount\na,10\nb,20\n", name="data")])
    path = workbook.write_xlsx(tmp_path / "book.xlsx")
    assert path.exists()
    restored = Workbook.read_xlsx(path)
    sheet = restored.sheet("data")
    assert sheet is not None
    assert sheet.headers == ["name", "amount"]
    assert len(sheet.rows) == 2
    assert sheet.rows[0]["name"] == "a"
    assert sheet.rows[0]["amount"] == "10"


# ── dashboard ─────────────────────────────────────────────


def test_a_dashboard_is_self_contained(tmp_path: Path) -> None:
    sheet = Sheet.from_csv("name,amount\na,10\nb,20\n")
    document = build_dashboard_html(title="Sales", sheet=sheet)
    assert "http://" not in document.replace("http://127.0.0.1", "")
    assert "Sales" in document
    assert "<svg" in document
    assert "cdn" not in document.lower()


# ── REA ───────────────────────────────────────────────────


def test_rea_refuses_to_analyse_without_an_authorization_basis(tmp_path: Path) -> None:
    target = tmp_path / "a.py"
    target.write_text("print(1)\n", encoding="utf-8")
    result = ReaEngine().analyze(str(target))
    assert result["ok"] is False
    assert "authorization basis" in result["error"]


def test_rea_reports_structure_with_evidence(tmp_path: Path) -> None:
    target = tmp_path / "a.py"
    target.write_text("import os\n\nclass A:\n    def b(self):\n        return 1\n", encoding="utf-8")
    result = ReaEngine().analyze(str(target), authorization_basis="the user owns this file")
    assert result["ok"] is True
    assert result["findings"]
    assert result["findings"][0]["limitations"]
    assert result["sha256"]


def test_rea_refuses_a_commercial_engine(tmp_path: Path) -> None:
    target = tmp_path / "a.bin"
    target.write_bytes(b"\x00\x01")
    result = ReaEngine().analyze(str(target), authorization_basis="owned", engine="ida")
    assert result["ok"] is False
    assert "licence" in result["error"]


# ── app synthesis ─────────────────────────────────────────


def test_synthesis_builds_a_tool_and_its_test(tmp_path: Path) -> None:
    source = tmp_path / "data.csv"
    source.write_text("name,amount\na,1\n", encoding="utf-8")
    result = AppSynthesis(skills_dir=tmp_path / "skills").synthesize(str(source))
    assert result["ok"] is True
    tool = Path(result["tool"])
    assert tool.is_file()
    assert "def read_rows" in tool.read_text(encoding="utf-8")
    assert Path(result["test"]).is_file()
    assert Path(result["skill"]).is_file()


def test_a_generated_tool_actually_works(tmp_path: Path) -> None:
    import importlib.util

    source = tmp_path / "data.csv"
    source.write_text("name,amount\na,1\n", encoding="utf-8")
    result = AppSynthesis(skills_dir=tmp_path / "skills").synthesize(str(source))
    spec = importlib.util.spec_from_file_location("generated", result["tool"])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = module.read_rows(str(source))
    assert rows == [{"name": "a", "amount": "1"}]


def test_the_analysis_states_its_limits(tmp_path: Path) -> None:
    source = tmp_path / "data.json"
    source.write_text('{"a": 1}', encoding="utf-8")
    analysis = AppSynthesis().analyze_format(str(source))
    assert analysis.format == "json"
    assert analysis.limitations

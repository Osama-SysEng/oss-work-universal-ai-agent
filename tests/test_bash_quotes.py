# -*- coding: utf-8 -*-
"""17 Nov live regression: cmd /c strips quotes from `python -c "..."`.

The live job j1794741485-3 asked for an Excel file; the brain ran
`python -c "import openpyxl; print(...)"` through cmd, got
`SyntaxError: unterminated string` and concluded the library was missing.
The launcher now runs plain commands as argv so quotes reach python intact.
"""
import os

import pytest

import osv_bash


@pytest.mark.skipif(os.name != "nt", reason="Windows cmd quoting only")
def test_python_c_quotes_survive():
    argv = osv_bash.build_argv(
        'python -c "import openpyxl; print(openpyxl.__version__)"')
    assert argv[:2] == ["python", "-c"], argv
    assert argv[2] == "import openpyxl; print(openpyxl.__version__)", argv


@pytest.mark.skipif(os.name != "nt", reason="Windows cmd quoting only")
def test_builtin_still_uses_cmd():
    assert osv_bash.build_argv("dir")[:2] == ["cmd", "/c"]
    assert osv_bash.build_argv("echo hi > out.txt")[:2] == ["cmd", "/c"]


def test_shell_metachars_never_bypass_shell():
    assert osv_bash.plain_argv("python a.py | findstr x") is None
    assert osv_bash.plain_argv("python a.py && python b.py") is None
    assert osv_bash.plain_argv("python a.py > log.txt") is None


def test_quoted_path_with_spaces_kept_whole():
    argv = osv_bash.plain_argv('python "C:\\my dir\\s.py"')
    if argv is None:                       # python not on PATH: shell lane
        pytest.skip("python not resolvable on PATH")
    assert argv[1] == "C:\\my dir\\s.py", argv

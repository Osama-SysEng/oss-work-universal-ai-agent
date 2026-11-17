"""Shared Windows command launcher for OSS Work tools.

17 Nov live: `cmd /c python -c "import openpyxl; print(...)"` strips the
quotes on Windows, so the model saw `SyntaxError: unterminated string` and
concluded the library was missing (it was installed: 3.1.5), then burned
the run on a Linux-style venv command. Any command with no shell syntax
whose first token is a real executable is launched as argv instead of
through cmd, so quoting reaches the program intact. Builtins and shell
operators still go through cmd.
"""
from __future__ import annotations

import os
import re
import shutil

_SHELL_META = re.compile(r"[|&<>^%\n]")


def plain_argv(command: str) -> list[str] | None:
    """Return argv for a shell-free command, or None when cmd is required."""
    if os.name != "nt" or not (command or "").strip():
        return None
    if _SHELL_META.search(command):
        return None
    tokens: list[str] = []
    cur, quote = "", ""
    for ch in command:
        if quote:
            if ch == quote:
                quote = ""
            else:
                cur += ch
        elif ch in ('"', "'"):
            quote = ch
        elif ch.isspace():
            if cur:
                tokens.append(cur)
                cur = ""
        else:
            cur += ch
    if cur:
        tokens.append(cur)
    if not tokens or shutil.which(tokens[0]) is None:
        return None                   # builtins (dir/copy/start) need cmd
    return tokens


def build_argv(command: str) -> list[str]:
    """argv for subprocess: direct for plain commands, shell wrapper otherwise."""
    argv = plain_argv(command)
    if argv is not None:
        return argv
    return ["cmd", "/c", command] if os.name == "nt" else ["bash", "-c", command]

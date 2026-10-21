"""Sandbox for untrusted code (spec sections 13, 16, and 19).

Cloned repositories and generated code run here, with no network and no
inherited secrets. The enforcement is deliberately honest about its reach:

- Network is blocked for Python children by installing a ``sitecustomize``
  that refuses to create sockets. A child that compiles native code or uses
  a different runtime can still get around that, so the limit is documented
  as Python-level enforcement, not an operating-system jail.
- The environment is rebuilt from scratch: the parent's variables, including
  any token that happens to live there, never reach the child.
- The child works in a throwaway directory and is killed on timeout.

For a real OS-level jail, run the same tool inside a container or a virtual
machine; the tool interface does not change.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

BLOCK_NETWORK_SITECUSTOMIZE = '''
"""Installed by OSS Work to block network access inside the sandbox."""
import socket

_real_socket = socket.socket


class _BlockedSocket(_real_socket):  # pragma: no cover - defensive
    def __init__(self, *args, **kwargs):
        raise OSError("network access is disabled inside the OSS Work sandbox")


def _blocked(*args, **kwargs):
    raise OSError("network access is disabled inside the OSS Work sandbox")


socket.socket = _blocked
socket.create_connection = _blocked
socket.socketpair = _blocked
'''


@dataclass
class SandboxResult:
    """What a sandboxed run produced."""

    ok: bool
    stdout: str = ""
    stderr: str = ""
    returncode: int = -1
    timed_out: bool = False
    workdir: str = ""
    duration_s: float = 0.0
    notes: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "stdout": self.stdout[-8000:],
            "stderr": self.stderr[-4000:],
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "workdir": self.workdir,
            "duration_s": round(self.duration_s, 3),
            "notes": list(self.notes),
        }


def sandbox_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """A minimal environment for a child process. The parent's env is dropped."""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONHASHSEED": "0",
        "LANG": "C.UTF-8",
        "HOME": os.environ.get("TEMP", tempfile.gettempdir()),
    }
    if os.name == "nt":
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
        env["TEMP"] = os.environ.get("TEMP", tempfile.gettempdir())
    if extra:
        env.update(extra)
    return env


def run_python(
    code: str,
    *,
    timeout: float = 20.0,
    workdir: str | None = None,
    files: dict[str, str] | None = None,
    extra_env: dict[str, str] | None = None,
) -> SandboxResult:
    """Run Python source in a temporary, network-less, secret-less directory."""
    import time

    base = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="ossv1-sandbox-"))
    base.mkdir(parents=True, exist_ok=True)
    guard_dir = base / ".ossv1_guard"
    guard_dir.mkdir(parents=True, exist_ok=True)
    (guard_dir / "sitecustomize.py").write_text(BLOCK_NETWORK_SITECUSTOMIZE, encoding="utf-8")

    for name, content in (files or {}).items():
        target = base / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    script = base / "_ossv1_entry.py"
    script.write_text(code, encoding="utf-8")

    env = sandbox_env(extra_env)
    existing_path = env.get("PATH", "")
    env["PYTHONPATH"] = f"{guard_dir}{os.pathsep}{existing_path}" if existing_path else str(guard_dir)

    started = time.time()
    try:
        completed = subprocess.run(  # noqa: S603 - fixed interpreter, scrubbed env, no shell
            [sys.executable, str(script)],
            cwd=str(base),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return SandboxResult(
            ok=False,
            stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
            stderr="execution exceeded the time limit and was stopped",
            returncode=-1,
            timed_out=True,
            workdir=str(base),
            duration_s=time.time() - started,
            notes=("network blocked for Python children", "environment scrubbed of inherited variables"),
        )
    finally:
        shutil.rmtree(guard_dir, ignore_errors=True)

    return SandboxResult(
        ok=completed.returncode == 0,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
        returncode=completed.returncode,
        timed_out=False,
        workdir=str(base),
        duration_s=time.time() - started,
        notes=("network blocked for Python children", "environment scrubbed of inherited variables"),
    )

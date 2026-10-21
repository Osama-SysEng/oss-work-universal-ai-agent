"""Program control under a permission (spec section 12).

The specification gives the agent its own account on the operating system,
with limited permissions, and lets it start programs. Creating a second
operating-system account is a deployment task, not something an agent may do
to the machine by itself, so this release implements the part that belongs
in the application: a program launcher that only starts programs the user
allowed, from a confined working directory, with a scrubbed environment and
a time limit.

The dedicated OS account is listed in ``todo.md`` as deployment work. What is
here is the boundary around program execution, and it is enforced.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from osv1.tools.registry import RISK_EXECUTE, Tool, ToolResult
from osv1.tools.sandbox import sandbox_env


@dataclass
class ProgramRunner:
    """Starts allowed programs, and refuses everything else."""

    allowlist: list[str] = field(default_factory=list)
    workspace: Path = field(default_factory=lambda: Path("./workspace"))
    timeout: float = 60.0
    max_output_bytes: int = 65_536

    def __post_init__(self) -> None:
        self.allowlist = [name.strip().lower() for name in self.allowlist if name.strip()]
        self.workspace = Path(self.workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)

    def allowed(self, program: str) -> bool:
        """True when the program is on the allowlist."""
        name = Path(program).name.lower()
        if name.endswith(".exe"):
            name = name[:-4]
        return any(name == entry or name == f"{entry}.exe" for entry in self.allowlist)

    def resolve(self, program: str) -> str | None:
        """Find the program on the PATH, when it is allowed."""
        if not self.allowed(program):
            return None
        executable = shutil.which(program)
        if executable:
            return executable
        candidate = Path(program)
        if candidate.is_file():
            return str(candidate.resolve())
        return None

    @staticmethod
    def _parse_arguments(arguments: str) -> list[str]:
        """Read the argument string: shell-like quoting, or a JSON list."""
        text = (arguments or "").strip()
        if not text:
            return []
        if text.startswith("["):
            import json

            parsed = json.loads(text)
            if not isinstance(parsed, list):
                raise ValueError("the JSON arguments must be a list")
            return [str(item) for item in parsed]
        import shlex

        return shlex.split(text)

    def run(self, program: str, arguments: str = "", timeout: float | None = None) -> ToolResult:
        """Run an allowed program from the workspace.

        The arguments are a string with shell-like quoting, or a JSON list for
        exact control. On Windows, a backslash inside a quoted argument is
        read as an escape, so use forward slashes or the JSON form.
        """
        name = Path(program).name
        if not self.allowlist:
            return ToolResult(
                ok=False,
                error=(
                    "no program is allowed. The user has to allow one first "
                    "(OSS_V1_PROGRAM_ALLOWLIST, and a programs permission for it)."
                ),
            )
        if not self.allowed(program):
            return ToolResult(
                ok=False,
                error=f"{name} is not on the allowlist ({', '.join(self.allowlist) or 'empty'})",
            )
        executable = self.resolve(program)
        if executable is None:
            return ToolResult(ok=False, error=f"{name} was not found on this machine")
        try:
            argument_list = self._parse_arguments(arguments)
        except ValueError as exc:
            return ToolResult(ok=False, error=f"the arguments could not be read: {exc}")
        command = [executable, *argument_list]
        started = time.time()
        try:
            completed = subprocess.run(  # noqa: S603 - the program is on the allowlist
                command,
                cwd=str(self.workspace),
                env=sandbox_env(),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout or self.timeout,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                ok=False,
                error=f"{name} exceeded the time limit and was stopped",
                data={"program": name, "timed_out": True},
                notes=("the environment was scrubbed of inherited variables",),
            )
        except OSError as exc:
            return ToolResult(ok=False, error=f"{name} could not be started: {exc}")
        output = (completed.stdout or "")[: self.max_output_bytes]
        errors = (completed.stderr or "")[: self.max_output_bytes]
        return ToolResult(
            ok=completed.returncode == 0,
            output=output,
            data={
                "program": name,
                "returncode": completed.returncode,
                "stderr": errors,
                "duration_s": round(time.time() - started, 3),
                "working_directory": str(self.workspace),
            },
            error="" if completed.returncode == 0 else errors[:400],
            notes=(
                "the program ran from the workspace with a scrubbed environment",
                "the program is on the user's allowlist",
            ),
        )

    def register(self, registry: Any) -> None:
        runner = self

        def run(program: str, arguments: str = "") -> ToolResult:
            return runner.run(program, arguments)

        registry.register(
            Tool(
                name="program.run",
                description=(
                    "Start a program the user allowed, from the workspace, with no inherited secrets. "
                    "Anything not on the allowlist is refused."
                ),
                risk=RISK_EXECUTE,
                scope="programs",
                handler=run,
            )
        )


def allowlist_from_env(variable: str = "OSS_V1_PROGRAM_ALLOWLIST") -> list[str]:
    """Read the allowlist from the environment."""
    raw = os.getenv(variable, "")
    return [item.strip() for item in raw.split(",") if item.strip()]

"""File tools confined to the folders the user granted (spec section 12).

Every path is resolved and checked against the granted roots before anything
is read or written. Deletion is irreversible, so it is marked as such and the
action engine asks for approval before it runs.
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from osv1.tools.registry import RISK_IRREVERSIBLE, RISK_READ, RISK_WRITE, Tool, ToolResult

TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".cfg",
    ".ini",
    ".csv",
    ".tsv",
    ".html",
    ".css",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".c",
    ".h",
    ".cpp",
    ".cs",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".sh",
    ".sql",
    ".log",
    ".env",
    ".xml",
}
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".mypy_cache", ".pytest_cache", ".ruff_cache"}


@dataclass
class FileTools:
    """File operations inside the granted roots."""

    allowed_roots: list[Path] = field(default_factory=list)
    max_bytes: int = 10_485_760
    max_results: int = 500

    def __post_init__(self) -> None:
        self.allowed_roots = [Path(root).expanduser().resolve() for root in self.allowed_roots]

    # ── path handling ─────────────────────────────────────────

    def resolve(self, path: str | Path) -> Path:
        """Resolve a path and refuse it when it escapes the granted roots.

        A relative path is taken from the working directory, so a request
        that names "src/app.py" means the file the user is looking at.
        """
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        resolved = candidate.resolve()
        if not self.allowed_roots:
            raise PermissionError("no file root is granted for this session")
        for root in self.allowed_roots:
            try:
                resolved.relative_to(root)
            except ValueError:
                continue
            return resolved
        raise PermissionError(f"path is outside the granted roots: {resolved}")

    def _read_text(self, path: Path) -> str:
        size = path.stat().st_size
        if size > self.max_bytes:
            raise ValueError(f"file is larger than the {self.max_bytes} byte limit ({size} bytes)")
        return path.read_text(encoding="utf-8", errors="replace")

    # ── operations ────────────────────────────────────────────

    def list_dir(self, path: str | Path, *, pattern: str = "*", recursive: bool = False) -> ToolResult:
        try:
            target = self.resolve(path)
        except PermissionError as exc:
            return ToolResult(ok=False, error=str(exc))
        if not target.exists():
            return ToolResult(ok=False, error=f"path does not exist: {target}")
        if target.is_file():
            return ToolResult(ok=True, output=str(target), data={"path": str(target), "is_file": True})
        entries: list[dict[str, Any]] = []
        try:
            iterator: Iterable[Path] = target.rglob(pattern) if recursive else target.glob(pattern)
            for item in sorted(iterator):
                if any(part in SKIP_DIRS for part in item.parts):
                    continue
                try:
                    stat = item.stat()
                except OSError:
                    continue
                entries.append(
                    {
                        "path": str(item),
                        "name": item.name,
                        "is_dir": item.is_dir(),
                        "size": stat.st_size,
                    }
                )
                if len(entries) >= self.max_results:
                    break
        except OSError as exc:
            return ToolResult(ok=False, error=f"cannot list directory: {exc}")
        return ToolResult(
            ok=True,
            output="\n".join(f"{'d' if e['is_dir'] else '-'} {e['size']:>10} {e['path']}" for e in entries),
            data={"root": str(target), "entries": entries, "count": len(entries)},
        )

    def read_file(self, path: str | Path, *, max_chars: int = 20_000) -> ToolResult:
        try:
            target = self.resolve(path)
        except PermissionError as exc:
            return ToolResult(ok=False, error=str(exc))
        if not target.exists():
            return ToolResult(ok=False, error=f"file does not exist: {target}")
        if not target.is_file():
            return ToolResult(ok=False, error=f"not a file: {target}")
        try:
            content = self._read_text(target)
        except (OSError, ValueError) as exc:
            return ToolResult(ok=False, error=str(exc))
        truncated = len(content) > max_chars
        return ToolResult(
            ok=True,
            output=content[:max_chars],
            data={
                "path": str(target),
                "chars": len(content),
                "truncated": truncated,
                "suffix": target.suffix,
            },
        )

    def search_files(self, pattern: str, *, root: str | Path | None = None, suffix: str = "") -> ToolResult:
        """Search file contents for a regular expression."""
        try:
            base = self.resolve(root) if root else (self.allowed_roots[0] if self.allowed_roots else Path.cwd())
        except PermissionError as exc:
            return ToolResult(ok=False, error=str(exc))
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return ToolResult(ok=False, error=f"invalid pattern: {exc}")
        matches: list[dict[str, Any]] = []
        files_scanned = 0
        for item in sorted(base.rglob("*")):
            if len(matches) >= self.max_results:
                break
            if not item.is_file() or any(part in SKIP_DIRS for part in item.parts):
                continue
            if suffix and item.suffix.lower() != suffix.lower():
                continue
            if item.suffix.lower() not in TEXT_SUFFIXES and item.suffix:
                continue
            try:
                content = self._read_text(item)
            except (OSError, ValueError):
                continue
            files_scanned += 1
            for number, line in enumerate(content.splitlines(), start=1):
                if regex.search(line):
                    matches.append({"path": str(item), "line": number, "text": line.strip()[:300]})
                    if len(matches) >= self.max_results:
                        break
        return ToolResult(
            ok=True,
            output="\n".join(f"{m['path']}:{m['line']}: {m['text']}" for m in matches),
            data={"matches": matches, "count": len(matches), "files_scanned": files_scanned},
        )

    def write_file(self, path: str | Path, content: str, *, append: bool = False) -> ToolResult:
        try:
            target = self.resolve(path)
        except PermissionError as exc:
            return ToolResult(ok=False, error=str(exc))
        existed = target.exists()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if append else "w"
            with target.open(mode, encoding="utf-8", newline="\n") as handle:
                handle.write(content)
        except OSError as exc:
            return ToolResult(ok=False, error=f"cannot write file: {exc}")
        return ToolResult(
            ok=True,
            output=f"wrote {len(content)} characters to {target}",
            data={"path": str(target), "chars": len(content), "appended": append, "existed": existed},
            reversible=True,
            rollback=f"restore {target} from the recorded previous content" if existed else f"delete {target}",
            notes=("previous content recorded in the audit log",) if existed else (),
        )

    def delete_file(self, path: str | Path) -> ToolResult:
        """Irreversible on purpose: the action engine requires approval first."""
        try:
            target = self.resolve(path)
        except PermissionError as exc:
            return ToolResult(ok=False, error=str(exc))
        if not target.exists():
            return ToolResult(ok=False, error=f"file does not exist: {target}")
        if target.is_dir():
            return ToolResult(ok=False, error="directory deletion is not supported")
        try:
            target.unlink()
        except OSError as exc:
            return ToolResult(ok=False, error=f"cannot delete file: {exc}")
        return ToolResult(
            ok=True,
            output=f"deleted {target}",
            data={"path": str(target)},
            reversible=False,
            rollback="none — deletion is not reversible",
        )

    def move_file(self, source: str | Path, destination: str | Path) -> ToolResult:
        try:
            src = self.resolve(source)
            dst = self.resolve(destination)
        except PermissionError as exc:
            return ToolResult(ok=False, error=str(exc))
        if not src.exists():
            return ToolResult(ok=False, error=f"source does not exist: {src}")
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
        except OSError as exc:
            return ToolResult(ok=False, error=f"cannot move file: {exc}")
        return ToolResult(
            ok=True,
            output=f"moved {src} -> {dst}",
            data={"source": str(src), "destination": str(dst)},
            reversible=True,
            rollback=f"move {dst} back to {src}",
        )

    # ── tool registration ─────────────────────────────────────

    def register(self, registry: Any) -> None:
        registry.register(
            Tool(
                name="file.list",
                description="List files and folders inside a granted root.",
                risk=RISK_READ,
                handler=self.list_dir,
            )
        )
        registry.register(
            Tool(
                name="file.read",
                description="Read a text file inside a granted root.",
                risk=RISK_READ,
                handler=self.read_file,
            )
        )
        registry.register(
            Tool(
                name="file.search",
                description="Search file contents by regular expression.",
                risk=RISK_READ,
                handler=self.search_files,
            )
        )
        registry.register(
            Tool(
                name="file.write",
                description="Create or update a text file inside a granted root.",
                risk=RISK_WRITE,
                handler=self.write_file,
            )
        )
        registry.register(
            Tool(
                name="file.move",
                description="Move or rename a file inside the granted roots.",
                risk=RISK_WRITE,
                handler=self.move_file,
            )
        )
        registry.register(
            Tool(
                name="file.delete",
                description="Delete a file. Irreversible: needs human approval.",
                risk=RISK_IRREVERSIBLE,
                requires_approval=True,
                reversible=False,
                handler=self.delete_file,
            )
        )

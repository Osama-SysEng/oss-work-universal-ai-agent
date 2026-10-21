"""REA integration: understand binaries, apps, and sites (spec section 13).

The specification embeds REA (Reverse Engineer Anything, based on the
``morluto/rea`` project, MIT licence) as an internal tool, with Ghidra as the
default analysis engine for native binaries. The rules that matter here are
implemented literally:

1. Pinned supply chain. The expected version is fixed in this file. An
   installed copy that reports another version is refused, and a checksum is
   recorded for every analysis.
2. Evidence. Every finding keeps the evidence it came from and the limits of
   that evidence.
3. Lawful use. The first analysis of a target asks for the authorization
   basis and logs it.
4. Scope. REA inspects local artifacts. It cannot and does not extract the
   weights of a hosted model.

When REA itself is not installed, the built-in lightweight analyzer still
returns real structure findings for text, source, and binary targets, and it
says which engine produced them.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from osv1.tools.registry import RISK_READ, Tool, ToolResult

PINNED_REA_VERSION = "0.4.0"  # spec section 13: pin an exact version
REA_REPOSITORY = "https://github.com/morluto/rea"
DEFAULT_BINARY_ENGINE = "ghidra"  # spec section 13: Ghidra is the default
COMMERCIAL_ENGINES = ("hopper", "ida", "jeb")  # only with the user's own licence


@dataclass(frozen=True)
class Finding:
    """One conclusion, with the evidence behind it and its limits."""

    title: str
    detail: str
    evidence: tuple[str, ...] = ()
    limitations: str = "no limitations recorded"

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "detail": self.detail,
            "evidence": list(self.evidence),
            "limitations": self.limitations,
        }


@dataclass
class ReaEngine:
    """Runs local analysis and keeps the supply-chain record."""

    rea_path: str = ""
    authorization_log: list[dict[str, Any]] = field(default_factory=list)
    version: str = ""

    def __post_init__(self) -> None:
        self.rea_path = self.rea_path or os.getenv("OSS_REA_PATH", "")
        if self.rea_path:
            self.version = self._detect_version()

    # ── availability ──────────────────────────────────────────

    def _detect_version(self) -> str:
        manifest = Path(self.rea_path) / "package.json"
        if not manifest.is_file():
            return ""
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ""
        return str(data.get("version", ""))

    def available(self) -> tuple[bool, str]:
        """Report whether the pinned REA copy is present."""
        if not self.rea_path:
            return False, (
                "REA is not installed locally. Set OSS_REA_PATH to the pinned checkout "
                f"of {REA_REPOSITORY} (expected version {PINNED_REA_VERSION}); "
                "the built-in analyzer still reports structure for text and source targets."
            )
        if not Path(self.rea_path).is_dir():
            return False, f"OSS_REA_PATH does not point to a directory: {self.rea_path}"
        if self.version and self.version != PINNED_REA_VERSION:
            return False, (
                f"the installed REA reports version {self.version}, but the pinned version is "
                f"{PINNED_REA_VERSION}. Refusing to run an unpinned copy."
            )
        return True, f"REA {self.version or 'present'} at {self.rea_path}"

    def _check_engine(self, engine: str) -> str:
        """Commercial engines need the user's own licence (spec section 13)."""
        if engine.lower() in COMMERCIAL_ENGINES:
            raise PermissionError(
                f"{engine} is a commercial engine: it can be used only when the user holds a legal licence."
            )
        if engine.lower() == DEFAULT_BINARY_ENGINE and not shutil.which("analyzeHeadless"):
            return "ghidra-not-found"
        return "ok"

    # ── analysis ──────────────────────────────────────────────

    def analyze(
        self,
        target: str,
        *,
        engine: str = DEFAULT_BINARY_ENGINE,
        authorization_basis: str = "",
        kind: str = "",
    ) -> dict[str, Any]:
        """Analyse a local target and return findings with evidence."""
        path = Path(target)
        if not path.exists():
            return {"ok": False, "error": f"target does not exist: {path}"}
        if not authorization_basis:
            return {
                "ok": False,
                "error": (
                    "the authorization basis is required before the first analysis of a target "
                    "(spec section 13, rule 7): state that the user owns the software or is "
                    "authorized to examine it, and for what purpose."
                ),
            }
        try:
            engine_status = self._check_engine(engine)
        except PermissionError as exc:
            return {"ok": False, "error": str(exc)}

        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        findings, notes = self._builtin_analysis(path, kind)
        self.authorization_log.append(
            {
                "target": str(path),
                "basis": authorization_basis,
                "engine": engine,
                "engine_status": engine_status,
                "sha256": digest,
            }
        )
        return {
            "ok": True,
            "target": str(path),
            "engine": engine,
            "engine_status": engine_status,
            "source": "builtin-analyzer",
            "sha256": digest,
            "findings": [f.as_dict() for f in findings],
            "notes": notes,
            "limitations": (
                "The built-in analyzer reports structure only. Decompilation, symbol recovery, and "
                "runtime capture need the pinned REA engine and its configured backend."
            ),
        }

    def _builtin_analysis(self, path: Path, kind: str) -> tuple[list[Finding], list[str]]:
        notes: list[str] = []
        suffix = (kind or path.suffix).lower()
        if suffix in (".py",):
            findings = self._analyze_python(path)
        elif suffix in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
            findings = self._analyze_javascript(path)
        elif suffix in (".json",):
            findings = self._analyze_json(path)
        elif suffix in (".html", ".htm"):
            findings = self._analyze_html(path)
        else:
            findings = self._analyze_binary(path)
            notes.append("binary mode: strings and header facts only")
        return findings, notes

    def _analyze_python(self, path: Path) -> list[Finding]:
        source = path.read_text(encoding="utf-8", errors="replace")
        findings: list[Finding] = []
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            return [
                Finding(
                    title="not parseable as Python",
                    detail=f"syntax error at line {exc.lineno}: {exc.msg}",
                    evidence=(f"{path.name}:{exc.lineno}",),
                    limitations="the file may use a syntax variant this parser does not accept",
                )
            ]
        modules: list[str] = []
        classes: list[str] = []
        functions: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)
        findings.append(
            Finding(
                title="module structure",
                detail=f"{len(classes)} classes, {len(functions)} functions, {len(set(modules))} imported modules",
                evidence=tuple(sorted(set(modules))[:12]),
                limitations="imports show what the module reaches for, not what it uses at run time",
            )
        )
        return findings

    def _analyze_javascript(self, path: Path) -> list[Finding]:
        source = path.read_text(encoding="utf-8", errors="replace")
        imports = sorted(set(re.findall(r"""(?:require\(|from\s+)['"]([^'"]+)['"]""", source)))
        routes = sorted(set(re.findall(r"""\.(?:get|post|put|delete|patch|use)\(\s*['"]([^'"]+)['"]""", source)))
        ipc = sorted(set(re.findall(r"""ipc(?:Main|Renderer)\.(?:handle|on)\(\s*['"]([^'"]+)['"]""", source)))
        findings = [
            Finding(
                title="module structure",
                detail=f"{len(imports)} imports, {len(routes)} route registrations, {len(ipc)} IPC channels",
                evidence=tuple(imports[:12]),
                limitations="a route or channel can be registered indirectly, so this list is a lower bound",
            )
        ]
        if routes:
            findings.append(
                Finding(
                    title="http routes",
                    detail=f"{len(routes)} routes found",
                    evidence=tuple(routes[:20]),
                    limitations="static patterns only; dynamic route construction is not detected",
                )
            )
        if ipc:
            findings.append(
                Finding(
                    title="ipc channels",
                    detail=f"{len(ipc)} channels found",
                    evidence=tuple(ipc[:20]),
                    limitations="static patterns only",
                )
            )
        return findings

    def _analyze_json(self, path: Path) -> list[Finding]:
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            return [
                Finding(
                    title="not valid JSON",
                    detail=str(exc),
                    evidence=(path.name,),
                    limitations="the file may use JSON5 or a comment-tolerant dialect",
                )
            ]
        keys = list(data)[:20] if isinstance(data, dict) else []
        return [
            Finding(
                title="top-level keys",
                detail=f"{len(keys)} keys at the top level",
                evidence=tuple(str(k) for k in keys),
                limitations="nested structure was not summarized",
            )
        ]

    def _analyze_html(self, path: Path) -> list[Finding]:
        source = path.read_text(encoding="utf-8", errors="replace")
        scripts = sorted(set(re.findall(r"<script[^>]*src=[\"']([^\"']+)[\"']", source)))
        forms = len(re.findall(r"<form\b", source))
        inputs = len(re.findall(r"<input\b", source))
        return [
            Finding(
                title="page structure",
                detail=f"{len(scripts)} external scripts, {forms} forms, {inputs} inputs",
                evidence=tuple(scripts[:12]),
                limitations="inline scripts and dynamically injected markup are not listed",
            )
        ]

    def _analyze_binary(self, path: Path) -> list[Finding]:
        data = path.read_bytes()
        magic = data[:4]
        kind = "unknown"
        if magic[:4] == b"\x7fELF":
            kind = "ELF"
        elif magic[:2] == b"MZ":
            kind = "PE"
        elif magic[:4] == b"PK\x03\x04":
            kind = "ZIP container"
        elif magic[:4] == b"\xca\xfe\xba\xbe":
            kind = "Java class / Mach-O fat"
        strings = re.findall(rb"[ -~]{6,}", data)
        interesting = [s.decode("ascii", "replace") for s in strings[:40]]
        return [
            Finding(
                title="container facts",
                detail=f"{kind} file, {len(data)} bytes",
                evidence=tuple(interesting[:12]),
                limitations="no symbols or disassembly: that needs the pinned REA engine and Ghidra",
            )
        ]

    # ── tool registration ─────────────────────────────────────

    def register(self, registry: Any) -> None:
        engine = self

        def analyze(target: str, authorization_basis: str = "", kind: str = "") -> ToolResult:
            result = engine.analyze(target, authorization_basis=authorization_basis, kind=kind)
            if not result.get("ok"):
                return ToolResult(ok=False, error=str(result.get("error", "")), data=result)
            return ToolResult(
                ok=True,
                output="\n".join(f"- {f['title']}: {f['detail']}" for f in result["findings"]),
                data=result,
                notes=("analysis runs locally; the authorization basis is logged",),
            )

        registry.register(
            Tool(
                name="rea.analyze",
                description=(
                    "Analyse a local target and return findings with their evidence and limits. "
                    "Requires the authorization basis for the target."
                ),
                risk=RISK_READ,
                handler=analyze,
            )
        )


def register(registry: Any, engine: ReaEngine | None = None) -> None:
    (engine or ReaEngine()).register(registry)

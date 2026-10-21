"""App Synthesis: build an equivalent tool inside OS_V1 (spec section 13).

The pattern the specification describes is: understand a file format, then
build the tool that handles it inside the system, instead of depending on a
licensed program. This module implements that pattern for the formats the
system actually meets.

For every target it produces three things:

1. an analysis of the format — what it is, what fields it carries, and what
   the analysis could not determine;
2. a generated Python tool that reads and writes that format;
3. a smoke test that the system runs to prove the generated tool works.

The generated tool is written into the skills directory, so it is picked up as
a reusable skill (spec section 14) instead of being a one-off script.
"""

from __future__ import annotations

import csv
import json
import sqlite3
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from osv1.tools.registry import RISK_READ, RISK_WRITE, Tool, ToolResult

SUPPORTED_FORMATS = ("csv", "tsv", "json", "html", "text", "sqlite", "zip")


@dataclass
class FormatAnalysis:
    """What the system understands about a file format."""

    path: str
    format: str
    mime: str = ""
    size: int = 0
    fields: list[str] = field(default_factory=list)
    sample: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "format": self.format,
            "mime": self.mime,
            "size": self.size,
            "fields": self.fields,
            "sample": self.sample,
            "notes": self.notes,
            "limitations": self.limitations,
        }


@dataclass
class AppSynthesis:
    """Understands formats and generates the matching tools."""

    skills_dir: Path = field(default_factory=lambda: Path("./skills-osv1"))

    # ── analysis ──────────────────────────────────────────────

    def analyze_format(self, path: str) -> FormatAnalysis:
        target = Path(path)
        if not target.exists():
            raise FileNotFoundError(f"target does not exist: {target}")
        size = target.stat().st_size
        suffix = target.suffix.lower()
        if suffix in (".csv", ".tsv"):
            return self._analyze_delimited(target, size)
        if suffix == ".json":
            return self._analyze_json(target, size)
        if suffix in (".html", ".htm"):
            return self._analyze_html(target, size)
        if suffix in (".db", ".sqlite", ".sqlite3"):
            return self._analyze_sqlite(target, size)
        if suffix == ".zip":
            return self._analyze_zip(target, size)
        return FormatAnalysis(
            path=str(target),
            format="text",
            mime="text/plain",
            size=size,
            notes=["no structured reader was needed; the file is treated as text"],
            limitations=["binary content would be returned as replacement characters"],
        )

    def _analyze_delimited(self, target: Path, size: int) -> FormatAnalysis:
        delimiter = "\t" if target.suffix.lower() == ".tsv" else ","
        text = target.read_text(encoding="utf-8", errors="replace")
        rows = list(csv.reader(text.splitlines(), delimiter=delimiter))
        headers = rows[0] if rows else []
        sample = [", ".join(row[:6]) for row in rows[1:4]]
        return FormatAnalysis(
            path=str(target),
            format="tsv" if delimiter == "\t" else "csv",
            mime="text/csv",
            size=size,
            fields=[str(h) for h in headers],
            sample=sample,
            notes=[f"{max(0, len(rows) - 1)} data rows detected"],
            limitations=["quoted fields spanning several lines are not analysed"],
        )

    def _analyze_json(self, target: Path, size: int) -> FormatAnalysis:
        text = target.read_text(encoding="utf-8", errors="replace")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            return FormatAnalysis(
                path=str(target),
                format="json",
                mime="application/json",
                size=size,
                limitations=[f"the file does not parse as JSON: {exc}"],
            )
        if isinstance(data, dict):
            fields = [str(key) for key in data]
        elif isinstance(data, list) and data and isinstance(data[0], dict):
            fields = [str(key) for key in data[0]]
        else:
            fields = []
        return FormatAnalysis(
            path=str(target),
            format="json",
            mime="application/json",
            size=size,
            fields=fields,
            sample=[
                json.dumps(item, ensure_ascii=False)[:160] for item in (data[:2] if isinstance(data, list) else [data])
            ],
            notes=[f"top level is {type(data).__name__}"],
            limitations=["nested objects are not summarized field by field"],
        )

    def _analyze_html(self, target: Path, size: int) -> FormatAnalysis:
        text = target.read_text(encoding="utf-8", errors="replace")
        import re

        title = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.S | re.I)
        headings = re.findall(r"<h[1-3][^>]*>(.*?)</h[1-3]>", text, flags=re.S | re.I)
        return FormatAnalysis(
            path=str(target),
            format="html",
            mime="text/html",
            size=size,
            fields=["title", "headings"],
            sample=[title.group(1).strip()[:120]] if title else [],
            notes=[f"{len(headings)} headings detected"],
            limitations=["rendered layout is not analysed; only the markup"],
        )

    def _analyze_sqlite(self, target: Path, size: int) -> FormatAnalysis:
        try:
            with sqlite3.connect(f"file:{target}?mode=ro", uri=True) as connection:
                tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
                columns: list[str] = []
                for table in tables:
                    for row in connection.execute(f'PRAGMA table_info("{table}")'):
                        columns.append(f"{table}.{row[1]}")
        except sqlite3.Error as exc:
            return FormatAnalysis(
                path=str(target),
                format="sqlite",
                mime="application/vnd.sqlite3",
                size=size,
                limitations=[f"the database did not open: {exc}"],
            )
        return FormatAnalysis(
            path=str(target),
            format="sqlite",
            mime="application/vnd.sqlite3",
            size=size,
            fields=columns,
            notes=[f"{len(tables)} tables: {', '.join(tables[:10])}"],
            limitations=["row contents are not sampled"],
        )

    def _analyze_zip(self, target: Path, size: int) -> FormatAnalysis:
        try:
            with zipfile.ZipFile(target) as archive:
                names = archive.namelist()
        except zipfile.BadZipFile as exc:
            return FormatAnalysis(
                path=str(target),
                format="zip",
                mime="application/zip",
                size=size,
                limitations=[f"the archive did not open: {exc}"],
            )
        return FormatAnalysis(
            path=str(target),
            format="zip",
            mime="application/zip",
            size=size,
            fields=names[:20],
            notes=[f"{len(names)} entries"],
            limitations=["entry contents are not extracted"],
        )

    # ── synthesis ─────────────────────────────────────────────

    def synthesize(self, path: str, *, out_dir: str | None = None) -> dict[str, Any]:
        """Understand a format, then build the matching tool inside the system."""
        analysis = self.analyze_format(path)
        target_dir = Path(out_dir) if out_dir else self.skills_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        module_name = f"{analysis.format}_tool"
        module_path = target_dir / f"{module_name}.py"
        module_path.write_text(self._tool_source(analysis), encoding="utf-8")

        test_path = target_dir / f"test_{module_name}.py"
        test_path.write_text(self._test_source(analysis), encoding="utf-8")

        skill_path = target_dir / f"SKILL_{module_name}.md"
        skill_path.write_text(
            self._skill_source(analysis, module_path, test_path),
            encoding="utf-8",
        )
        return {
            "ok": True,
            "analysis": analysis.as_dict(),
            "tool": str(module_path),
            "test": str(test_path),
            "skill": str(skill_path),
            "note": "the generated tool is a starting point: review it before trusting it with real data",
        }

    def _tool_source(self, analysis: FormatAnalysis) -> str:
        # The path is normalised to forward slashes so the generated docstring
        # never carries a Windows backslash escape.
        source_path = analysis.path.replace("\\", "/")
        header = rf'''"""Generated by OSS Work / OS_V1 (App Synthesis) for the {analysis.format} format.

Source format analysis: {source_path}
Fields: {", ".join(analysis.fields) if analysis.fields else "none detected"}

This tool was generated from the analysis of one sample file. Review it before
using it on data you care about.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

'''
        if analysis.format in ("csv", "tsv"):
            delimiter = "\\t" if analysis.format == "tsv" else ","
            body = f'''
DELIMITER = "{delimiter}"


def read_rows(path: str) -> list[dict]:
    """Read the file into a list of dictionaries."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return list(csv.DictReader(text.splitlines(), delimiter=DELIMITER))


def write_rows(path: str, rows: list[dict]) -> str:
    """Write rows back to the file."""
    if not rows:
        raise ValueError("no rows to write")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), delimiter=DELIMITER)
        writer.writeheader()
        writer.writerows(rows)
    return str(target)


def column_values(path: str, column: str) -> list[str]:
    """Return one column as a list of strings."""
    return [str(row.get(column, "")) for row in read_rows(path)]
'''
        elif analysis.format == "json":
            body = '''
def read_json(path: str):
    """Read the file as JSON."""
    return json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))


def write_json(path: str, data, indent: int = 2) -> str:
    """Write data back as JSON."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")
    return str(target)


def records(data) -> list[dict]:
    """Return a list of dictionaries from either shape."""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [data]
    return []
'''
        elif analysis.format == "html":
            body = '''
import re


def extract_text(path: str) -> str:
    """Return the visible text of the page."""
    source = Path(path).read_text(encoding="utf-8", errors="replace")
    source = re.sub(r"<(script|style)[^>]*>.*?</\\1>", " ", source, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", source)
    return re.sub(r"\\s+", " ", text).strip()


def extract_links(path: str) -> list[str]:
    """Return every link target in the page."""
    source = Path(path).read_text(encoding="utf-8", errors="replace")
    return re.findall(r'href=["\\\']([^"\\\']+)["\\\']', source, flags=re.I)
'''
        elif analysis.format == "sqlite":
            body = '''
import sqlite3


def list_tables(path: str) -> list[str]:
    """List the tables in the database."""
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        return [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]


def read_table(path: str, table: str, limit: int = 1000) -> list[dict]:
    """Read rows from one table."""
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(f'SELECT * FROM "{table}" LIMIT ?', (limit,)).fetchall()
    return [dict(row) for row in rows]
'''
        else:
            body = '''
def read_text(path: str) -> str:
    """Read the file as text."""
    return Path(path).read_text(encoding="utf-8", errors="replace")


def write_text(path: str, content: str) -> str:
    """Write text to the file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return str(target)
'''
        return header + body

    def _test_source(self, analysis: FormatAnalysis) -> str:
        if analysis.format in ("csv", "tsv"):
            return (
                '"""Smoke test for the generated csv tool."""\n\n'
                "import importlib.util\nimport tempfile\nfrom pathlib import Path\n\n"
                "def load():\n"
                "    spec = importlib.util.spec_from_file_location('generated_tool', Path(__file__).with_name('csv_tool.py'))\n"
                "    module = importlib.util.module_from_spec(spec)\n"
                "    spec.loader.exec_module(module)\n"
                "    return module\n\n"
                "def test_round_trip():\n"
                "    module = load()\n"
                "    rows = [{'a': '1', 'b': '2'}]\n"
                "    with tempfile.TemporaryDirectory() as folder:\n"
                "        path = str(Path(folder) / 'sample.csv')\n"
                "        module.write_rows(path, rows)\n"
                "        assert module.read_rows(path) == rows\n"
            )
        if analysis.format == "json":
            return (
                '"""Smoke test for the generated json tool."""\n\n'
                "import importlib.util\nimport tempfile\nfrom pathlib import Path\n\n"
                "def load():\n"
                "    spec = importlib.util.spec_from_file_location('generated_tool', Path(__file__).with_name('json_tool.py'))\n"
                "    module = importlib.util.module_from_spec(spec)\n"
                "    spec.loader.exec_module(module)\n"
                "    return module\n\n"
                "def test_round_trip():\n"
                "    module = load()\n"
                "    data = {'a': 1}\n"
                "    with tempfile.TemporaryDirectory() as folder:\n"
                "        path = str(Path(folder) / 'sample.json')\n"
                "        module.write_json(path, data)\n"
                "        assert module.read_json(path) == data\n"
            )
        return (
            '"""Smoke test for the generated tool."""\n\n'
            "import importlib.util\nfrom pathlib import Path\n\n"
            "def load():\n"
            f"    spec = importlib.util.spec_from_file_location('generated_tool', Path(__file__).with_name('{analysis.format}_tool.py'))\n"
            "    module = importlib.util.module_from_spec(spec)\n"
            "    spec.loader.exec_module(module)\n"
            "    return module\n\n"
            "def test_module_loads():\n"
            "    assert load() is not None\n"
        )

    def _skill_source(self, analysis: FormatAnalysis, module_path: Path, test_path: Path) -> str:
        return (
            f"---\nname: {analysis.format}-tool\ndescription: Read and write {analysis.format} files "
            f"with the tool generated for this format.\n---\n\n"
            f"# {analysis.format} tool\n\n"
            f"Generated by OSS Work / OS_V1 from the analysis of `{analysis.path}`.\n\n"
            f"## When to use\n"
            f"Use it whenever a task involves a {analysis.format} file.\n\n"
            f"## Files\n"
            f"- Tool: `{module_path.name}`\n"
            f"- Smoke test: `{test_path.name}`\n\n"
            f"## Known limits\n"
            + "".join(f"- {limit}\n" for limit in (analysis.limitations or ["none recorded"]))
            + "\n## Review before use\n"
            "The tool was generated from one sample file. Run the smoke test, then read the\n"
            "code before pointing it at data that matters.\n"
        )

    # ── tool registration ─────────────────────────────────────

    def register(self, registry: Any) -> None:
        synthesis = self

        def analyze(path: str) -> ToolResult:
            try:
                analysis = synthesis.analyze_format(path)
            except (FileNotFoundError, OSError) as exc:
                return ToolResult(ok=False, error=str(exc))
            return ToolResult(ok=True, output=f"format: {analysis.format}", data=analysis.as_dict())

        def synthesize(path: str, out_dir: str = "") -> ToolResult:
            try:
                result = synthesis.synthesize(path, out_dir=out_dir or None)
            except (FileNotFoundError, OSError) as exc:
                return ToolResult(ok=False, error=str(exc))
            return ToolResult(ok=True, output=result["note"], data=result)

        registry.register(
            Tool(
                name="format.analyze",
                description="Understand a file format: its fields, its structure, and the limits of that analysis.",
                risk=RISK_READ,
                handler=analyze,
            )
        )
        registry.register(
            Tool(
                name="format.synthesize",
                description="Understand a file format and build the matching tool inside OSS Work.",
                risk=RISK_WRITE,
                handler=synthesize,
            )
        )

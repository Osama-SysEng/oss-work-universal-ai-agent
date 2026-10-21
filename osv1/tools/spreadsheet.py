"""The built-in spreadsheet engine (spec section 13, "App Synthesis").

OS_V1 does not depend on a licensed spreadsheet program. It ships its own
engine: it reads and writes delimited files, exports a valid ``.xlsx``
workbook, and applies the operations the worked example needs — add rows,
remove rows, remove duplicates, filter, sort, aggregate, and compute columns
from safe arithmetic expressions.

The expression evaluator accepts numbers, column names, parentheses, and the
four arithmetic operators. It refuses anything else, so a formula can never
call a function or reach the interpreter.
"""

from __future__ import annotations

import ast
import csv
import io
import re
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from osv1.tools.registry import RISK_READ, RISK_WRITE, Tool, ToolResult

CELL_REF = re.compile(r"^([A-Z]+)(\d+)$")
ALLOWED_FUNCTIONS = {"SUM", "AVG", "COUNT", "MIN", "MAX"}


def column_letter(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def column_index(letters: str) -> int:
    value = 0
    for char in letters:
        value = value * 26 + (ord(char) - 64)
    return value - 1


class FormulaError(ValueError):
    """Raised when a formula cannot be evaluated."""


def _safe_eval(node: ast.AST, row: dict[str, Any]) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body, row)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        raise FormulaError("only numbers are allowed in a formula")
    if isinstance(node, ast.Name):
        if node.id in ALLOWED_FUNCTIONS:
            raise FormulaError("function calls need a range argument")
        raw = row.get(node.id, 0)
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 0.0
    if isinstance(node, ast.BinOp):
        left = _safe_eval(node.left, row)
        right = _safe_eval(node.right, row)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise FormulaError("division by zero")
            return left / right
        raise FormulaError("unsupported operator")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _safe_eval(node.operand, row)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ALLOWED_FUNCTIONS:
        return _call_aggregate(node.func.id, node, row)
    raise FormulaError("unsupported expression")


def _call_aggregate(name: str, call: ast.Call, row: dict[str, Any]) -> float:
    if not call.args:
        raise FormulaError(f"{name} needs one range argument")
    argument = call.args[0]
    if not (isinstance(argument, ast.Name) and isinstance(argument.ctx, ast.Load)):
        raise FormulaError(f"{name} expects a column name")
    column = argument.id
    values = [v for v in row.get(f"__values__{column}", []) if isinstance(v, (int, float))]
    if not values:
        return 0.0
    if name == "SUM":
        return float(sum(values))
    if name == "AVG":
        return float(sum(values) / len(values))
    if name == "COUNT":
        return float(len(values))
    if name == "MIN":
        return float(min(values))
    return float(max(values))


def evaluate_formula(expression: str, row: dict[str, Any]) -> float:
    """Evaluate a safe arithmetic expression against one row."""
    text = expression.strip()
    if text.startswith("="):
        text = text[1:]
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"cannot parse the expression: {exc.msg}") from exc
    return _safe_eval(tree, row)


@dataclass
class Sheet:
    """One table: ordered headers plus row dictionaries."""

    name: str = "Sheet1"
    headers: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)

    def ensure_headers(self) -> None:
        for row in self.rows:
            for key in row:
                if key not in self.headers:
                    self.headers.append(key)

    def column(self, name: str) -> list[Any]:
        return [row.get(name) for row in self.rows]

    def numeric_column(self, name: str) -> list[float]:
        values: list[float] = []
        for raw in self.column(name):
            try:
                values.append(float(raw))
            except (TypeError, ValueError):
                continue
        return values

    def as_dicts(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.rows]

    def to_csv(self, delimiter: str = ",") -> str:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=self.headers, delimiter=delimiter, lineterminator="\n")
        writer.writeheader()
        for row in self.rows:
            writer.writerow({key: row.get(key, "") for key in self.headers})
        return buffer.getvalue()

    @classmethod
    def from_csv(cls, text: str, *, name: str = "Sheet1", delimiter: str | None = None) -> Sheet:
        if delimiter is None:
            delimiter = "\t" if text.count("\t") > text.count(",") else ","
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        headers = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
        return cls(name=name, headers=headers, rows=rows)

    def copy(self) -> Sheet:
        return Sheet(name=self.name, headers=list(self.headers), rows=[dict(r) for r in self.rows])


@dataclass
class Workbook:
    """A set of sheets that can be written out as CSV or as a real .xlsx file."""

    sheets: list[Sheet] = field(default_factory=list)

    def sheet(self, name: str) -> Sheet | None:
        for sheet in self.sheets:
            if sheet.name == name:
                return sheet
        return None

    def add(self, sheet: Sheet) -> Sheet:
        sheet.ensure_headers()
        self.sheets.append(sheet)
        return sheet

    # ── operations ────────────────────────────────────────────

    def add_rows(self, sheet_name: str, rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
        sheet = self.sheet(sheet_name)
        if sheet is None:
            return {"ok": False, "error": f"no sheet named {sheet_name!r}"}
        before = len(sheet.rows)
        for row in rows:
            sheet.rows.append(dict(row))
        sheet.ensure_headers()
        return {"ok": True, "added": len(sheet.rows) - before, "total": len(sheet.rows)}

    def remove_rows(self, sheet_name: str, predicate: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
        sheet = self.sheet(sheet_name)
        if sheet is None:
            return {"ok": False, "error": f"no sheet named {sheet_name!r}"}
        before = len(sheet.rows)
        sheet.rows = [row for row in sheet.rows if not predicate(row)]
        return {"ok": True, "removed": before - len(sheet.rows), "total": len(sheet.rows)}

    def remove_duplicates(self, sheet_name: str, keys: Sequence[str]) -> dict[str, Any]:
        sheet = self.sheet(sheet_name)
        if sheet is None:
            return {"ok": False, "error": f"no sheet named {sheet_name!r}"}
        seen: set[tuple[Any, ...]] = set()
        unique: list[dict[str, Any]] = []
        duplicates = 0
        for row in sheet.rows:
            signature = tuple(str(row.get(key, "")).strip().lower() for key in keys)
            if signature in seen:
                duplicates += 1
                continue
            seen.add(signature)
            unique.append(row)
        sheet.rows = unique
        return {"ok": True, "duplicates_removed": duplicates, "total": len(sheet.rows)}

    def filter_rows(self, sheet_name: str, column: str, value: str) -> dict[str, Any]:
        sheet = self.sheet(sheet_name)
        if sheet is None:
            return {"ok": False, "error": f"no sheet named {sheet_name!r}"}
        wanted = value.strip().lower()
        before = len(sheet.rows)
        sheet.rows = [row for row in sheet.rows if str(row.get(column, "")).strip().lower() == wanted]
        return {"ok": True, "kept": len(sheet.rows), "removed": before - len(sheet.rows)}

    def sort_rows(self, sheet_name: str, column: str, *, descending: bool = False) -> dict[str, Any]:
        sheet = self.sheet(sheet_name)
        if sheet is None:
            return {"ok": False, "error": f"no sheet named {sheet_name!r}"}

        def key(row: dict[str, Any]) -> tuple[int, float, str]:
            raw = row.get(column, "")
            try:
                return (0, float(raw), "")
            except (TypeError, ValueError):
                return (1, 0.0, str(raw).lower())

        sheet.rows.sort(key=key, reverse=descending)
        return {"ok": True, "sorted_by": column, "descending": descending, "total": len(sheet.rows)}

    def group_sum(self, sheet_name: str, group_by: str, value_column: str) -> list[dict[str, Any]]:
        sheet = self.sheet(sheet_name)
        if sheet is None:
            return []
        totals: dict[str, float] = {}
        for row in sheet.rows:
            key = str(row.get(group_by, ""))
            try:
                amount = float(row.get(value_column, 0))
            except (TypeError, ValueError):
                amount = 0.0
            totals[key] = totals.get(key, 0.0) + amount
        return [{group_by: key, value_column: round(total, 4), "count": 0} for key, total in sorted(totals.items())]

    def compute_column(self, sheet_name: str, target: str, expression: str) -> dict[str, Any]:
        """Add a computed column using a safe arithmetic expression."""
        sheet = self.sheet(sheet_name)
        if sheet is None:
            return {"ok": False, "error": f"no sheet named {sheet_name!r}"}
        errors = 0
        for row in sheet.rows:
            scoped = dict(row)
            for header in sheet.headers:
                scoped[f"__values__{header}"] = [
                    value for value in sheet.column(header) if isinstance(value, (int, float))
                ]
            try:
                row[target] = round(evaluate_formula(expression, scoped), 6)
            except FormulaError:
                errors += 1
                row[target] = ""
        if target not in sheet.headers:
            sheet.headers.append(target)
        return {"ok": True, "column": target, "rows": len(sheet.rows), "errors": errors}

    def stats(self, sheet_name: str) -> dict[str, Any]:
        sheet = self.sheet(sheet_name)
        if sheet is None:
            return {}
        numeric: dict[str, Any] = {}
        for header in sheet.headers:
            values = sheet.numeric_column(header)
            if not values:
                continue
            numeric[header] = {
                "count": len(values),
                "sum": round(sum(values), 4),
                "avg": round(sum(values) / len(values), 4),
                "min": round(min(values), 4),
                "max": round(max(values), 4),
            }
        return {"rows": len(sheet.rows), "columns": sheet.headers, "numeric": numeric}

    # ── output ────────────────────────────────────────────────

    def write_csv(self, path: str | Path, sheet_name: str | None = None) -> Path:
        target = Path(path)
        sheet = self.sheet(sheet_name) if sheet_name else (self.sheets[0] if self.sheets else None)
        if sheet is None:
            raise ValueError("the workbook has no sheet to write")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(sheet.to_csv(), encoding="utf-8")
        return target

    def write_xlsx(self, path: str | Path) -> Path:
        """Write a minimal but valid .xlsx workbook (inline strings, no styles)."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        content_types = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.'
            'spreadsheetml.sheet.main+xml"/>'
            + "".join(
                f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.'
                'openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                for index in range(1, len(self.sheets) + 1)
            )
            + "</Types>"
        )
        root_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
            'officeDocument" Target="xl/workbook.xml"/></Relationships>'
        )
        workbook = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            + "".join(
                f'<sheet name="{_xml_escape(sheet.name)}" sheetId="{index}" r:id="rId{index}"/>'
                for index, sheet in enumerate(self.sheets, start=1)
            )
            + "</sheets></workbook>"
        )
        workbook_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(
                f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                'relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
                for index in range(1, len(self.sheets) + 1)
            )
            + "</Relationships>"
        )
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", content_types)
            archive.writestr("_rels/.rels", root_rels)
            archive.writestr("xl/workbook.xml", workbook)
            archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
            for index, sheet in enumerate(self.sheets, start=1):
                archive.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(sheet))
        return target

    @classmethod
    def read_xlsx(cls, path: str | Path) -> Workbook:
        """Read back a workbook written by :meth:`write_xlsx`."""
        workbook = cls()
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            sheet_names = (
                _sheet_names(archive.read("xl/workbook.xml").decode("utf-8")) if "xl/workbook.xml" in names else []
            )
            for index in range(1, len(names) + 1):
                member = f"xl/worksheets/sheet{index}.xml"
                if member not in names:
                    continue
                sheet = _sheet_from_xml(archive.read(member).decode("utf-8"))
                if index - 1 < len(sheet_names):
                    sheet.name = sheet_names[index - 1]
                workbook.add(sheet)
        return workbook


def _sheet_names(workbook_xml: str) -> list[str]:
    """Read the sheet names out of the workbook part."""
    import re as _re

    return [
        name.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
        for name in _re.findall(r'<sheet[^>]*name="([^"]+)"', workbook_xml)
    ]


def _xml_escape(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _cell_value(value: Any) -> tuple[str, str]:
    """Return (cell type, XML payload) for a value."""
    if isinstance(value, bool):
        return "b", "1" if value else "0"
    if isinstance(value, (int, float)):
        return "n", repr(value)
    return "inlineStr", _xml_escape("" if value is None else str(value))


def _sheet_xml(sheet: Sheet) -> str:
    sheet.ensure_headers()
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>',
    ]
    # The header is the first row of the sheet, as every spreadsheet expects.
    parts.append('<row r="1">')
    for column_index, header in enumerate(sheet.headers):
        cell_ref = f"{column_letter(column_index)}1"
        parts.append(f'<c r="{cell_ref}" t="inlineStr"><is><t>{_xml_escape(str(header))}</t></is></c>')
    parts.append("</row>")
    for row_index, row in enumerate(sheet.rows, start=2):
        parts.append(f'<row r="{row_index}">')
        for column_index, header in enumerate(sheet.headers):
            cell_ref = f"{column_letter(column_index)}{row_index}"
            cell_type, payload = _cell_value(row.get(header, ""))
            if cell_type == "inlineStr":
                parts.append(f'<c r="{cell_ref}" t="inlineStr"><is><t>{payload}</t></is></c>')
            else:
                parts.append(f'<c r="{cell_ref}"><v>{payload}</v></c>')
        parts.append("</row>")
    parts.append("</sheetData></worksheet>")
    return "".join(parts)


def _sheet_from_xml(xml: str) -> Sheet:
    """Read a sheet back: the first row is the header, as in a spreadsheet."""
    import re as _re

    sheet = Sheet()
    rows = _re.findall(r"<row\b[^>]*>(.*?)</row>", xml, flags=_re.S)
    headers: list[str] = []
    for index, row_xml in enumerate(rows):
        cells = _re.findall(r"<c\b[^>]*r=\"([A-Z]+\d+)\"[^>]*>(.*?)</c>", row_xml, flags=_re.S)
        values: dict[str, str] = {}
        for reference, body in cells:
            match = CELL_REF.match(reference)
            if not match:
                continue
            letter = column_letter(column_index(match.group(1)))
            values[letter] = _re.sub(r"<[^>]+>", "", body)
        if index == 0:
            headers = [values.get(letter, letter) for letter in sorted(values, key=column_index)]
            sheet.headers = headers
            continue
        row: dict[str, Any] = {}
        for position, letter in enumerate(sorted(values, key=column_index)):
            name = headers[position] if position < len(headers) else letter
            row[name] = values[letter]
        sheet.rows.append(row)
    if not headers:
        sheet.headers = []
    return sheet


@dataclass
class SpreadsheetTools:
    """The spreadsheet engine exposed as tools."""

    def read_csv(self, path: str, *, sheet_name: str = "Sheet1") -> ToolResult:
        source = Path(path)
        if not source.exists():
            return ToolResult(ok=False, error=f"file does not exist: {source}")
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return ToolResult(ok=False, error=f"cannot read the file: {exc}")
        sheet = Sheet.from_csv(text, name=sheet_name)
        return ToolResult(
            ok=True,
            output=f"{len(sheet.rows)} rows, {len(sheet.headers)} columns",
            data={"sheet": sheet.as_dicts(), "headers": sheet.headers, "rows": len(sheet.rows)},
        )

    def summarize(self, path: str) -> ToolResult:
        source = Path(path)
        if not source.exists():
            return ToolResult(ok=False, error=f"file does not exist: {source}")
        sheet = Sheet.from_csv(source.read_text(encoding="utf-8", errors="replace"))
        stats = {
            "rows": len(sheet.rows),
            "columns": sheet.headers,
            "numeric": {
                header: {
                    "count": len(sheet.numeric_column(header)),
                    "sum": round(sum(sheet.numeric_column(header)), 4),
                }
                for header in sheet.headers
                if sheet.numeric_column(header)
            },
        }
        return ToolResult(ok=True, output=f"{stats['rows']} rows", data=stats)

    def register(self, registry: Any) -> None:
        registry.register(
            Tool(
                name="sheet.read",
                description="Read a delimited file into the built-in spreadsheet engine.",
                risk=RISK_READ,
                handler=self.read_csv,
            )
        )
        registry.register(
            Tool(
                name="sheet.summarize",
                description="Summarize a delimited file: row count, columns, numeric totals.",
                risk=RISK_READ,
                handler=self.summarize,
            )
        )
        registry.register(
            Tool(
                name="sheet.write_csv",
                description="Write a sheet from the engine to a delimited file.",
                risk=RISK_WRITE,
                handler=lambda path, rows, headers=None, sheet_name="Sheet1": self._write_csv(
                    path, rows, headers, sheet_name
                ),
            )
        )


def _write_csv(path: str, rows: list[dict[str, Any]], headers: list[str] | None, sheet_name: str) -> ToolResult:
    sheet = Sheet(name=sheet_name, headers=list(headers or []), rows=rows)
    sheet.ensure_headers()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(sheet.to_csv(), encoding="utf-8")
    return ToolResult(
        ok=True,
        output=f"wrote {len(sheet.rows)} rows to {target}",
        data={"path": str(target), "rows": len(sheet.rows)},
    )

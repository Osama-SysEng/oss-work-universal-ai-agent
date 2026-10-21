"""Dashboard builder: a self-contained interactive HTML view of a dataset.

The worked example in spec section 13 asks for an interactive dashboard built
from a sheet. The output is a single HTML file with inline CSS, inline SVG
charts, and plain JavaScript — no CDN, no build step, no network. It opens
from the local file system and keeps working with the network switched off.
"""

from __future__ import annotations

import html
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from osv1.tools.registry import RISK_READ, RISK_WRITE, Tool, ToolResult
from osv1.tools.spreadsheet import Sheet


def _fmt(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return f"{int(round(value)):,}"
    return f"{value:,.2f}"


def _bar_chart(pairs: Sequence[tuple[str, float]], *, title: str, width: int = 720, height: int = 260) -> str:
    if not pairs:
        return '<p class="empty">no numeric data to chart</p>'
    label_width = 180
    chart_width = width - label_width - 60
    max_value = max(abs(value) for _, value in pairs) or 1.0
    row_height = max(18, min(34, height // max(1, len(pairs))))
    parts = [f"<h3>{html.escape(title)}</h3>", f'<svg viewBox="0 0 {width} {height}" role="img" class="chart">']
    for index, (label, value) in enumerate(pairs):
        y = index * row_height + 4
        bar = max(2, int(chart_width * abs(value) / max_value))
        parts.append(
            f'<text x="0" y="{y + row_height - 6}" class="label">{html.escape(str(label)[:24])}</text>'
            f'<rect x="{label_width}" y="{y}" width="{bar}" height="{row_height - 8}" class="bar" />'
            f'<text x="{label_width + bar + 6}" y="{y + row_height - 6}" class="value">{html.escape(_fmt(value))}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _kpi_cards(stats: dict[str, Any]) -> str:
    cards = [
        f'<div class="kpi"><div class="kpi-label">rows</div><div class="kpi-value">{_fmt(stats.get("rows", 0))}</div></div>'
    ]
    numeric = stats.get("numeric", {})
    for header, values in list(numeric.items())[:4]:
        cards.append(
            f'<div class="kpi"><div class="kpi-label">{html.escape(header)}</div>'
            f'<div class="kpi-value">{_fmt(values.get("sum", 0))}</div>'
            f'<div class="kpi-sub">avg {_fmt(values.get("avg", 0))} · max {_fmt(values.get("max", 0))}</div></div>'
        )
    return "".join(cards)


def build_dashboard_html(
    *,
    title: str,
    sheet: Sheet,
    group_by: str = "",
    value_column: str = "",
) -> str:
    """Render an interactive dashboard for one sheet."""
    sheet.ensure_headers()
    headers = sheet.headers
    rows = sheet.as_dicts()
    stats = {
        "rows": len(rows),
        "numeric": {
            header: {
                "count": len(sheet.numeric_column(header)),
                "sum": round(sum(sheet.numeric_column(header)), 4),
                "avg": round(sum(sheet.numeric_column(header)) / max(1, len(sheet.numeric_column(header))), 4),
                "max": round(max(sheet.numeric_column(header)), 4),
            }
            for header in headers
            if sheet.numeric_column(header)
        },
    }
    chart_pairs: list[tuple[str, float]] = []
    if group_by and value_column and group_by in headers:
        totals: dict[str, float] = {}
        for row in rows:
            key = str(row.get(group_by, ""))
            try:
                amount = float(row.get(value_column, 0))
            except (TypeError, ValueError):
                amount = 0.0
            totals[key] = totals.get(key, 0.0) + amount
        chart_pairs = sorted(totals.items(), key=lambda item: item[1], reverse=True)[:12]
    else:
        numeric_headers = [h for h in headers if sheet.numeric_column(h)]
        if numeric_headers:
            header = numeric_headers[0]
            values = sheet.numeric_column(header)
            chart_pairs = [(f"row {i + 1}", value) for i, value in enumerate(values[:12])]

    table_head = "".join(f"<th>{html.escape(str(header))}</th>" for header in headers)
    table_rows = []
    for row in rows[:500]:
        cells = "".join(f"<td>{html.escape(str(row.get(header, '')))}</td>" for header in headers)
        table_rows.append(f"<tr>{cells}</tr>")

    payload = json.dumps({"headers": headers, "rows": rows}, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{html.escape(title)}</title>
<style>
  :root {{ color-scheme: dark; --bg:#0f1216; --panel:#171c22; --line:#242c35; --text:#e6edf3; --muted:#8b949e; --accent:#4f9dff; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; padding:24px; background:var(--bg); color:var(--text);
         font:14px/1.5 "Segoe UI", system-ui, sans-serif; }}
  h1 {{ font-size:20px; margin:0 0 4px; }}
  h3 {{ font-size:14px; margin:0 0 10px; color:var(--muted); text-transform:uppercase; letter-spacing:.06em; }}
  .muted {{ color:var(--muted); margin:0 0 20px; }}
  .kpis {{ display:flex; flex-wrap:wrap; gap:12px; margin-bottom:20px; }}
  .kpi {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:14px 16px; min-width:150px; }}
  .kpi-label {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.06em; }}
  .kpi-value {{ font-size:22px; font-weight:600; margin-top:4px; }}
  .kpi-sub {{ color:var(--muted); font-size:12px; margin-top:2px; }}
  .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:16px; margin-bottom:20px; }}
  .chart {{ width:100%; height:auto; }}
  .chart .label {{ fill:var(--muted); font-size:12px; }}
  .chart .value {{ fill:var(--text); font-size:12px; }}
  .chart .bar {{ fill:var(--accent); rx:3; }}
  .table-tools {{ display:flex; gap:10px; margin-bottom:10px; }}
  input {{ background:#0d1117; border:1px solid var(--line); border-radius:8px; color:var(--text); padding:8px 10px; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th, td {{ text-align:left; padding:7px 10px; border-bottom:1px solid var(--line); white-space:nowrap; }}
  th {{ color:var(--muted); font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:.05em; }}
  tbody tr:hover {{ background:#1c232b; }}
  .empty {{ color:var(--muted); }}
  .footer {{ color:var(--muted); font-size:12px; margin-top:16px; }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<p class="muted">Generated locally by OSS Work / OS_V1 — no network, no external assets.</p>
<div class="kpis">{_kpi_cards(stats)}</div>
<div class="panel">{_bar_chart(chart_pairs, title=(f"{value_column} by {group_by}" if group_by and value_column else "values"))}</div>
<div class="panel">
  <h3>rows</h3>
  <div class="table-tools">
    <input id="filter" placeholder="filter rows…" />
    <input id="col" placeholder="column" />
  </div>
  <table id="data">
    <thead><tr>{table_head}</tr></thead>
    <tbody></tbody>
  </table>
</div>
<p class="footer">{len(rows)} rows loaded{"" if len(rows) <= 500 else " (first 500 shown)"}.</p>
<script>
const DATA = {payload};
const table = document.getElementById('data');
const tbody = table.querySelector('tbody');
const filterInput = document.getElementById('filter');
const columnInput = document.getElementById('col');
function escapeText(value) {{
  const div = document.createElement('div');
  div.textContent = value == null ? '' : String(value);
  return div.innerHTML;
}}
function render() {{
  const needle = filterInput.value.trim().toLowerCase();
  const column = columnInput.value.trim();
  const index = column ? DATA.headers.indexOf(column) : -1;
  const rows = DATA.rows.filter(row => {{
    if (index >= 0) return String(row[DATA.headers[index]] ?? '').toLowerCase().includes(needle);
    return Object.values(row).some(value => String(value ?? '').toLowerCase().includes(needle));
  }});
  tbody.innerHTML = rows.slice(0, 500).map(row =>
    '<tr>' + DATA.headers.map(h => '<td>' + escapeText(row[h]) + '</td>').join('') + '</tr>'
  ).join('');
}}
filterInput.addEventListener('input', render);
columnInput.addEventListener('input', render);
render();
</script>
</body>
</html>
"""


@dataclass
class DashboardTools:
    """Builds dashboards from a sheet and writes them next to the data."""

    def build(
        self,
        path: str,
        *,
        out_path: str = "",
        title: str = "",
        group_by: str = "",
        value_column: str = "",
    ) -> ToolResult:
        source = Path(path)
        if not source.exists():
            return ToolResult(ok=False, error=f"file does not exist: {source}")
        sheet = Sheet.from_csv(source.read_text(encoding="utf-8", errors="replace"))
        document = build_dashboard_html(
            title=title or f"Dashboard — {source.stem}",
            sheet=sheet,
            group_by=group_by,
            value_column=value_column,
        )
        target = Path(out_path) if out_path else source.with_suffix(".dashboard.html")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(document, encoding="utf-8")
        return ToolResult(
            ok=True,
            output=f"dashboard written to {target}",
            data={"path": str(target), "rows": len(sheet.rows), "bytes": len(document)},
        )

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
                name="dashboard.build",
                description="Build a self-contained interactive HTML dashboard from a delimited file.",
                risk=RISK_WRITE,
                handler=self.build,
            )
        )

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

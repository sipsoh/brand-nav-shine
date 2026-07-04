"""The coverage contract auditor (docs/engineering/coverage-contract.md).

Invariant: every profiled column of the primary table is represented on the
dashboard, or excluded with a computed reason. No third state.

Runs after chart execution on the FINISHED spec (so it guards the LLM planner
exactly as it guards the fallback planner). Planner heuristics decide how
WELL a column is shown; this module guarantees THAT it is shown:

- represented(chart): the column appears in a chart querySpec (measure,
  dimension, or date axis);
- represented(kpi): a KPI's source trace cites the column specifically;
- represented(table): the self-heal path — anything unaccounted is appended
  to a backstop data_table widget, so novel column shapes can never silently
  vanish;
- excluded(reason): only for columns that cannot display anything —
  `all null` and `constant (single value: X)` — with the reason on record.

The resulting ledger is written to spec["coverage"] for rendering ("N/N
columns represented") and for the eval harness's universal invariant.
"""

import logging

import pandas as pd

from app.services.profiler import json_safe

logger = logging.getLogger(__name__)

MAX_TABLE_ROWS = 10
MAX_TABLE_COLUMNS = 8


def audit_and_backstop(spec: dict, df: pd.DataFrame, table_id: str) -> None:
    """Mutates spec: appends a backstop data_table for unrepresented columns
    (if any) and writes the spec["coverage"] ledger over df's columns."""
    column_names = [str(c) for c in df.columns]
    status: dict[str, tuple[str, str | None]] = {}

    chart_columns, kpi_columns = _represented_columns(spec, total_columns=len(column_names))
    for name in column_names:
        if name in chart_columns:
            status[name] = ("chart", None)
        elif name in kpi_columns:
            status[name] = ("kpi", None)

    # Exclusions: only columns that cannot display anything.
    for name in column_names:
        if name in status:
            continue
        series = df[name].dropna()
        if series.empty:
            status[name] = ("excluded", "all null")
        elif series.nunique() <= 1:
            sample = str(series.iloc[0])[:40]
            status[name] = ("excluded", f"constant (single value: {sample})")

    # Self-heal: everything else goes into the backstop table.
    leftover = [name for name in column_names if name not in status]
    if leftover:
        _append_backstop_table(spec, df, table_id, leftover, column_names)
        for name in leftover:
            status[name] = ("table", None)

    represented = sum(1 for state, _ in status.values() if state != "excluded")
    spec["coverage"] = {
        "columnsTotal": len(column_names),
        "columnsRepresented": represented,
        "columns": [
            {"name": name, "status": status[name][0], "reason": status[name][1]}
            for name in column_names
        ],
    }


def _represented_columns(spec: dict, total_columns: int) -> tuple[set[str], set[str]]:
    chart_columns: set[str] = set()
    kpi_columns: set[str] = set()
    for section in spec.get("sections", []):
        for widget in section.get("widgets", []):
            if widget.get("type") == "chart":
                query_spec = (widget.get("chart") or {}).get("querySpec") or {}
                chart_columns.update(m["column"] for m in query_spec.get("measures", []))
                chart_columns.update(query_spec.get("dimensions") or [])
                if query_spec.get("dateColumn"):
                    chart_columns.add(query_spec["dateColumn"])
            elif widget.get("type") == "kpi":
                trace = (widget.get("kpi") or {}).get("sourceTrace") or {}
                columns = trace.get("columns") or []
                # A trace citing (nearly) every column is an aggregate over
                # the whole table (row count), not a representation of any
                # specific column.
                if 0 < len(columns) < max(2, total_columns):
                    kpi_columns.update(columns)
    return chart_columns, kpi_columns


def _append_backstop_table(
    spec: dict, df: pd.DataFrame, table_id: str, leftover: list[str], all_columns: list[str]
) -> None:
    # Anchor the rows with an identity-ish column (most-unique non-leftover
    # textual column) so a row of leftover values is recognizable.
    anchor = None
    candidates = [
        name
        for name in all_columns
        if name not in leftover and not pd.api.types.is_numeric_dtype(df[name])
    ]
    if candidates:
        anchor = max(candidates, key=lambda name: df[name].nunique())

    shown = ([anchor] if anchor else []) + leftover
    shown = shown[:MAX_TABLE_COLUMNS]
    dropped = len(([anchor] if anchor else []) + leftover) - len(shown)

    # Top rows by the largest numeric leftover column when one exists —
    # a meaningful order beats file order for an executive skim.
    frame = df[shown]
    numeric_leftovers = [c for c in leftover if c in shown and pd.api.types.is_numeric_dtype(df[c])]
    if numeric_leftovers:
        sort_by = max(numeric_leftovers, key=lambda c: float(df[c].abs().sum()))
        frame = frame.sort_values(by=sort_by, ascending=False)
        note = f"Top {min(MAX_TABLE_ROWS, len(frame))} rows by {sort_by}."
    else:
        note = f"First {min(MAX_TABLE_ROWS, len(frame))} rows."
    if dropped > 0:
        note += f" {dropped} more column(s) available in the source data."
    frame = frame.head(MAX_TABLE_ROWS)

    def cell(value):
        if pd.isna(value):
            return None
        if isinstance(value, pd.Timestamp):
            return value.isoformat(sep=" ")[:19]
        value = json_safe(value)
        return value if isinstance(value, (int, float, bool)) or value is None else str(value)

    widget = {
        "id": "w_backstop_table",
        "type": "data_table",
        "title": "More from your data",
        "size": "full",
        "table": {
            "columns": [str(c) for c in frame.columns],
            "rows": [[cell(v) for v in row] for row in frame.itertuples(index=False)],
            "note": note,
            "sourceTrace": {
                "tableId": table_id,
                "columns": [str(c) for c in frame.columns],
                "filters": [],
                "calculation": (
                    "coverage backstop: columns not shown in charts/KPIs, "
                    f"{note[0].lower()}{note[1:]}"
                )[:500],
                "rowCount": int(len(frame)),
                "generatedBy": "code",
            },
        },
    }
    section = {
        "id": "sec_details",
        "title": "More from your data",
        "layout": "full_width",
        "widgets": [widget],
    }
    # Before the appendix if one exists, else at the end.
    sections = spec.get("sections", [])
    appendix_index = next(
        (i for i, s in enumerate(sections) if s.get("layout") == "appendix"), len(sections)
    )
    sections.insert(appendix_index, section)

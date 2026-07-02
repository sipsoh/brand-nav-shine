"""Execute validated querySpecs against normalized DataFrames.

This is the only path from a spec to chart data — deterministic pandas code,
never an LLM (SETUP.md §9.8).
"""

from dataclasses import dataclass

import pandas as pd

from app.services.profiler import json_safe

GRAIN_FREQ = {"day": "D", "week": "W-MON", "month": "MS", "quarter": "QS", "year": "YS"}
AGGREGATIONS = {
    "sum": "sum",
    "avg": "mean",
    "median": "median",
    "min": "min",
    "max": "max",
    "count": "count",
    "count_distinct": "nunique",
}
DEFAULT_LIMIT = 50


class QueryError(Exception):
    pass


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[dict]
    source_row_count: int


def execute_query(df: pd.DataFrame, spec: dict) -> QueryResult:
    measures = spec.get("measures") or []
    dimensions = spec.get("dimensions") or []
    date_column = spec.get("dateColumn")
    date_grain = spec.get("dateGrain")
    limit = spec.get("limit") or DEFAULT_LIMIT

    if not measures:
        raise QueryError("querySpec has no measures.")

    used_columns = {m["column"] for m in measures} | set(dimensions)
    if date_column:
        used_columns.add(date_column)
    missing = used_columns - set(df.columns)
    if missing:
        raise QueryError(f"querySpec references unknown column(s): {sorted(missing)}")

    aggregations = {}
    for measure in measures:
        aggregation = measure["aggregation"]
        if aggregation not in AGGREGATIONS:
            raise QueryError(f"Unsupported aggregation '{aggregation}'.")
        alias = measure.get("alias") or f"{aggregation}_{measure['column']}"
        aggregations[alias] = pd.NamedAgg(
            column=measure["column"], aggfunc=AGGREGATIONS[aggregation]
        )

    work = df.dropna(subset=[m["column"] for m in measures], how="all")
    groupers: list = []
    if date_column and date_grain:
        if date_grain not in GRAIN_FREQ:
            raise QueryError(f"Unsupported dateGrain '{date_grain}'.")
        if not pd.api.types.is_datetime64_any_dtype(work[date_column]):
            raise QueryError(f"'{date_column}' is not a date column.")
        groupers.append(pd.Grouper(key=date_column, freq=GRAIN_FREQ[date_grain]))
    groupers.extend(dimensions)

    if groupers:
        grouped = work.groupby(groupers, observed=True, dropna=True).agg(**aggregations)
        grouped = grouped.reset_index()
        if date_column and date_grain:
            grouped = grouped.sort_values(by=date_column)
        else:
            grouped = grouped.sort_values(by=list(aggregations)[0], ascending=False)
        grouped = grouped.head(limit)
    else:
        row = {}
        for alias, named_agg in aggregations.items():
            series = work[named_agg.column].dropna()
            row[alias] = getattr(series, named_agg.aggfunc)() if len(series) else None
        grouped = pd.DataFrame([row])

    rows = [
        {str(key): json_safe(value) for key, value in record.items()}
        for record in grouped.to_dict(orient="records")
    ]
    return QueryResult(
        columns=[str(c) for c in grouped.columns],
        rows=rows,
        source_row_count=int(len(work)),
    )

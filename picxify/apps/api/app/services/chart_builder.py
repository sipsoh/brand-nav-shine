"""Build ECharts options from executed query results — code only (SETUP.md §9.8)."""

from app.services.query_runner import QueryResult

PALETTE = ["#10b981", "#0ea5e9", "#f59e0b", "#8b5cf6", "#f43f5e", "#14b8a6", "#a3e635", "#64748b"]

CARTESIAN = {"line", "area", "bar", "stacked_bar"}
CIRCULAR = {"pie", "donut"}
MAX_PIVOT_SERIES = 6


class ChartBuildError(Exception):
    pass


def build_echarts_option(chart_type: str, result: QueryResult, query_spec: dict) -> dict:
    if not result.rows:
        raise ChartBuildError("Query returned no data.")

    category_column = _category_column(query_spec, result)
    measure_columns = [c for c in result.columns if c != category_column]
    if not measure_columns:
        raise ChartBuildError("No measure columns in query result.")

    # Date grain + a dimension + one measure: pivot into one series per
    # dimension value (e.g. revenue over time, split by region).
    dimensions = query_spec.get("dimensions") or []
    if (
        chart_type in CARTESIAN
        and query_spec.get("dateColumn")
        and dimensions
        and len(measure_columns) >= 2
    ):
        return _pivoted_cartesian(
            chart_type, result, query_spec["dateColumn"], dimensions[0],
            [c for c in measure_columns if c != dimensions[0]][0],
        )

    if chart_type in CARTESIAN:
        return _cartesian(chart_type, result, category_column, measure_columns)
    if chart_type == "horizontal_bar":
        return _horizontal_bar(result, category_column, measure_columns[0])
    if chart_type in CIRCULAR:
        return _circular(chart_type, result, category_column, measure_columns[0])
    if chart_type == "funnel":
        return _funnel(result, category_column, measure_columns[0])
    raise ChartBuildError(f"Unsupported chart type '{chart_type}'.")


def _category_column(query_spec: dict, result: QueryResult) -> str:
    if query_spec.get("dateColumn") and query_spec.get("dateGrain"):
        return query_spec["dateColumn"]
    dimensions = query_spec.get("dimensions") or []
    if dimensions:
        return dimensions[0]
    return result.columns[0]


def _base() -> dict:
    return {
        "color": PALETTE,
        "tooltip": {"trigger": "axis"},
        "grid": {"left": 48, "right": 24, "top": 32, "bottom": 40, "containLabel": True},
    }


def _categories(result: QueryResult, column: str) -> list:
    return [str(row.get(column)) for row in result.rows]


def _pivoted_cartesian(chart_type, result, date_column, dimension_column, measure) -> dict:
    categories = sorted({str(row.get(date_column)) for row in result.rows})
    totals: dict[str, float] = {}
    for row in result.rows:
        key = str(row.get(dimension_column))
        totals[key] = totals.get(key, 0) + (row.get(measure) or 0)
    top_values = [
        name for name, _ in sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    ][:MAX_PIVOT_SERIES]

    cells: dict[tuple[str, str], float] = {}
    for row in result.rows:
        cells[(str(row.get(dimension_column)), str(row.get(date_column)))] = row.get(measure)

    option = _base()
    option["xAxis"] = {"type": "category", "data": categories}
    option["yAxis"] = {"type": "value"}
    option["legend"] = {"top": 0, "type": "scroll"}
    option["series"] = [
        {
            "name": name,
            "type": "line" if chart_type in {"line", "area"} else "bar",
            "stack": "total" if chart_type in {"stacked_bar", "area"} else None,
            "smooth": chart_type in {"line", "area"},
            "areaStyle": {"opacity": 0.25} if chart_type == "area" else None,
            "emphasis": {"focus": "series"},
            "data": [cells.get((name, category)) for category in categories],
        }
        for name in top_values
    ]
    return option


def _cartesian(chart_type, result, category_column, measure_columns) -> dict:
    option = _base()
    option["xAxis"] = {"type": "category", "data": _categories(result, category_column)}
    option["yAxis"] = {"type": "value"}
    option["series"] = []
    for measure in measure_columns:
        series = {
            "name": measure,
            "type": "line" if chart_type in {"line", "area"} else "bar",
            "data": [row.get(measure) for row in result.rows],
            "smooth": chart_type in {"line", "area"},
        }
        if chart_type == "area":
            series["areaStyle"] = {"opacity": 0.25}
        if chart_type == "stacked_bar":
            series["stack"] = "total"
        option["series"].append(series)
    if len(measure_columns) > 1:
        option["legend"] = {"top": 0}
    return option


def _horizontal_bar(result, category_column, measure) -> dict:
    option = _base()
    # Reverse so the largest value renders at the top.
    rows = list(reversed(result.rows))
    option["xAxis"] = {"type": "value"}
    option["yAxis"] = {"type": "category", "data": [str(r.get(category_column)) for r in rows]}
    option["series"] = [{"name": measure, "type": "bar", "data": [r.get(measure) for r in rows]}]
    return option


def _circular(chart_type, result, category_column, measure) -> dict:
    return {
        "color": PALETTE,
        "tooltip": {"trigger": "item"},
        "legend": {"top": 0, "type": "scroll"},
        "series": [
            {
                "type": "pie",
                "radius": ["45%", "72%"] if chart_type == "donut" else "72%",
                "avoidLabelOverlap": True,
                "itemStyle": {"borderRadius": 4, "borderColor": "#fff", "borderWidth": 2},
                "data": [
                    {"name": str(row.get(category_column)), "value": row.get(measure)}
                    for row in result.rows
                ],
            }
        ],
    }


def _funnel(result, category_column, measure) -> dict:
    return {
        "color": PALETTE,
        "tooltip": {"trigger": "item"},
        "series": [
            {
                "type": "funnel",
                "sort": "descending",
                "gap": 2,
                "label": {"show": True, "position": "inside"},
                "data": [
                    {"name": str(row.get(category_column)), "value": row.get(measure)}
                    for row in result.rows
                ],
            }
        ],
    }

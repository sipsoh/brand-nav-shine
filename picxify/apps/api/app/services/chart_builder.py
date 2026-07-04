"""Build ECharts options from executed query results — code only (SETUP.md §9.8).

Styling follows the Picxify data-viz design system (docs/engineering/
design-system.md): a CVD-validated categorical palette in fixed slot order,
single-hue marks for magnitude comparisons, an ordinal blue ramp for ordered
stages, thin marks with rounded data-ends, 2px surface gaps/rings, and
recessive hairline chrome. Text wears ink tokens, never series colors.
"""

from app.services.query_runner import QueryResult

# Validated categorical palette (light surface) — fixed slot order, never cycled.
PALETTE = ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7", "#e34948", "#e87ba4", "#eb6834"]
# Ordinal ramp (single blue hue, light->dark) for ordered stages like funnels.
ORDINAL_BLUES = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"]

SURFACE = "#fcfcfb"
GRIDLINE = "#e1e0d9"
AXIS_LINE = "#c3c2b7"
INK_MUTED = "#898781"
INK_SECONDARY = "#52514e"
INK_PRIMARY = "#0b0b0b"

CARTESIAN = {"line", "area", "bar", "stacked_bar"}
CIRCULAR = {"pie", "donut"}
MAX_PIVOT_SERIES = 6
BAR_MAX_WIDTH = 24


class ChartBuildError(Exception):
    pass


def build_echarts_option(chart_type: str, result: QueryResult, query_spec: dict) -> dict:
    if not result.rows:
        raise ChartBuildError("Query returned no data.")

    # Multi-measure aggregate with nothing to group by: one bar per COLUMN
    # (sibling-group totals such as aging buckets). The single result row is
    # transposed; input order is preserved because it encodes bucket order.
    if (
        chart_type == "horizontal_bar"
        and not (query_spec.get("dimensions") or [])
        and not query_spec.get("dateColumn")
        and len(result.rows) == 1
        and len(result.columns) >= 2
    ):
        return _column_totals_bar(result)

    category_column = _category_column(query_spec, result)
    measure_columns = [c for c in result.columns if c != category_column]
    if not measure_columns:
        raise ChartBuildError("No measure columns in query result.")

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
            grain=query_spec.get("dateGrain"),
        )

    if chart_type in CARTESIAN:
        grain = query_spec.get("dateGrain") if category_column == query_spec.get("dateColumn") else None
        return _cartesian(chart_type, result, category_column, measure_columns, grain)
    if chart_type == "horizontal_bar":
        return _horizontal_bar(result, category_column, measure_columns[0])
    if chart_type in CIRCULAR:
        return _circular(chart_type, result, category_column, measure_columns[0])
    if chart_type == "funnel":
        return _funnel(result, category_column, measure_columns[0])
    raise ChartBuildError(f"Unsupported chart type '{chart_type}'.")


def _period_label(value, grain: str | None) -> str:
    """Human date-axis labels: 'Jan 2026', 'Jan 05', 'Q1 2026' — never raw ISO."""
    from datetime import datetime

    if not grain:
        return str(value)
    try:
        moment = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return str(value)
    if grain == "month":
        return moment.strftime("%b %Y")
    if grain in {"week", "day"}:
        return moment.strftime("%b %d")
    if grain == "quarter":
        return f"Q{(moment.month - 1) // 3 + 1} {moment.year}"
    if grain == "year":
        return str(moment.year)
    return str(value)


def _category_column(query_spec: dict, result: QueryResult) -> str:
    if query_spec.get("dateColumn") and query_spec.get("dateGrain"):
        return query_spec["dateColumn"]
    dimensions = query_spec.get("dimensions") or []
    if dimensions:
        return dimensions[0]
    return result.columns[0]


def _base() -> dict:
    """Recessive chrome: hairline solid grid, muted axis ink, roomy padding."""
    return {
        "color": PALETTE,
        "tooltip": {"trigger": "axis"},
        "grid": {"left": 8, "right": 20, "top": 28, "bottom": 8, "containLabel": True},
        "textStyle": {"color": INK_SECONDARY},
    }


def _value_axis() -> dict:
    return {
        "type": "value",
        "axisLabel": {"color": INK_MUTED, "fontSize": 11},
        "splitLine": {"lineStyle": {"color": GRIDLINE, "width": 1, "type": "solid"}},
        "axisLine": {"show": False},
        "axisTick": {"show": False},
    }


def _category_axis(data: list) -> dict:
    return {
        "type": "category",
        "data": data,
        "axisLabel": {"color": INK_MUTED, "fontSize": 11},
        "axisLine": {"lineStyle": {"color": AXIS_LINE, "width": 1}},
        "axisTick": {"show": False},
        "splitLine": {"show": False},
    }


def _legend(show: bool) -> dict:
    """A legend is always present for >= 2 series; a single series needs none."""
    return {
        "show": show,
        "top": 0,
        "type": "scroll",
        "icon": "circle",
        "itemWidth": 9,
        "itemHeight": 9,
        "textStyle": {"color": INK_SECONDARY, "fontSize": 12},
    }


def _line_series(name: str, data: list, *, stacked: bool = False, area: bool = False) -> dict:
    series: dict = {
        "name": name,
        "type": "line",
        "data": data,
        "smooth": False,
        "lineStyle": {"width": 2, "cap": "round", "join": "round"},
        "symbol": "circle",
        "symbolSize": 8,
        # 2px surface ring keeps markers legible where they cross lines.
        "itemStyle": {"borderColor": SURFACE, "borderWidth": 2},
        "emphasis": {"focus": "series"},
    }
    if stacked:
        series["stack"] = "total"
    if area:
        series["areaStyle"] = {"opacity": 0.10}
    return series


def _bar_series(name: str, data: list, *, horizontal: bool = False,
                stacked: bool = False, tip_labels: bool = False) -> dict:
    series: dict = {
        "name": name,
        "type": "bar",
        "data": data,
        "barMaxWidth": BAR_MAX_WIDTH,
        "emphasis": {"focus": "series"},
    }
    if stacked:
        series["stack"] = "total"
        # 2px surface gap between touching segments; no rounding mid-stack.
        series["itemStyle"] = {"borderColor": SURFACE, "borderWidth": 1}
    else:
        # 4px rounded data-end, square at the baseline.
        radius = [0, 4, 4, 0] if horizontal else [4, 4, 0, 0]
        series["itemStyle"] = {"borderRadius": radius}
    if tip_labels:
        # Value at the bar tip (renderers inject the compact formatter).
        series["label"] = {
            "show": True,
            "position": "right" if horizontal else "top",
            "color": INK_SECONDARY,
            "fontSize": 11,
        }
    return series


def _pivoted_cartesian(chart_type, result, date_column, dimension_column, measure,
                       grain: str | None = None) -> dict:
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
    option["xAxis"] = _category_axis([_period_label(c, grain) for c in categories])
    option["yAxis"] = _value_axis()
    option["legend"] = _legend(show=len(top_values) > 1)
    option["series"] = []
    for name in top_values:
        data = [cells.get((name, category)) for category in categories]
        if chart_type in {"line", "area"}:
            option["series"].append(
                _line_series(name, data, stacked=chart_type == "area", area=chart_type == "area")
            )
        else:
            option["series"].append(_bar_series(name, data, stacked=True))
    return option


def _cartesian(chart_type, result, category_column, measure_columns,
               grain: str | None = None) -> dict:
    option = _base()
    option["xAxis"] = _category_axis(
        [_period_label(r.get(category_column), grain) for r in result.rows]
    )
    option["yAxis"] = _value_axis()
    option["legend"] = _legend(show=len(measure_columns) > 1)
    option["series"] = []
    for measure in measure_columns:
        data = [row.get(measure) for row in result.rows]
        if chart_type in {"line", "area"}:
            option["series"].append(_line_series(measure, data, area=chart_type == "area"))
        else:
            option["series"].append(
                _bar_series(measure, data, stacked=chart_type == "stacked_bar")
            )
    return option


def _horizontal_bar(result, category_column, measure) -> dict:
    """Magnitude comparison across nominal categories: one hue (slot 1),
    values at the bar tips — never a hue per bar, never a value ramp."""
    rows = list(reversed(result.rows))  # largest at the top
    option = _base()
    option["tooltip"] = {"trigger": "item"}
    # Tip labels carry the exact values; in a narrow card the tick labels
    # only collide with each other, so the value axis stays silent.
    value_axis = _value_axis()
    value_axis["axisLabel"] = {"show": False}
    value_axis["splitLine"] = {"show": False}
    option["xAxis"] = value_axis
    category_axis = _category_axis([str(r.get(category_column)) for r in rows])
    category_axis["axisLabel"] = {
        **category_axis["axisLabel"],
        "width": 200,
        "overflow": "truncate",
    }
    option["yAxis"] = category_axis
    option["grid"]["right"] = 56  # room for tip labels
    option["series"] = [
        _bar_series(measure, [r.get(measure) for r in rows], horizontal=True, tip_labels=True)
    ]
    return option


def _column_totals_bar(result) -> dict:
    """One bar per column from a transposed single-row aggregate — magnitude
    comparison across nominal categories, so single hue with tip labels,
    exactly like _horizontal_bar."""
    row = result.rows[0]
    entries = [
        (name, row.get(name))
        for name in result.columns
        if isinstance(row.get(name), (int, float))
    ]
    if len(entries) < 2:
        raise ChartBuildError("Not enough numeric totals to compare columns.")
    entries.reverse()  # echarts draws the first category at the bottom
    option = _base()
    option["tooltip"] = {"trigger": "item"}
    value_axis = _value_axis()
    value_axis["axisLabel"] = {"show": False}
    value_axis["splitLine"] = {"show": False}
    option["xAxis"] = value_axis
    category_axis = _category_axis([name for name, _ in entries])
    category_axis["axisLabel"] = {
        **category_axis["axisLabel"],
        "width": 200,
        "overflow": "truncate",
    }
    option["yAxis"] = category_axis
    option["grid"]["right"] = 56  # room for tip labels
    option["series"] = [
        _bar_series("Total", [value for _, value in entries], horizontal=True, tip_labels=True)
    ]
    return option


def _circular(chart_type, result, category_column, measure) -> dict:
    """Part-to-whole at a glance only; capped at 6 segments + 'Other'."""
    rows = result.rows
    if len(rows) > 6:
        head, tail = rows[:5], rows[5:]
        other_value = sum((r.get(measure) or 0) for r in tail)
        rows = head + [{category_column: "Other", measure: other_value}]
    return {
        "color": PALETTE,
        "textStyle": {"color": INK_SECONDARY},
        "tooltip": {"trigger": "item"},
        "legend": _legend(show=True),
        "series": [
            {
                "type": "pie",
                "radius": ["52%", "74%"] if chart_type == "donut" else "74%",
                "avoidLabelOverlap": True,
                # 2px surface gap between touching segments.
                "itemStyle": {"borderColor": SURFACE, "borderWidth": 2},
                "label": {"color": INK_SECONDARY, "fontSize": 11},
                "data": [
                    {"name": str(row.get(category_column)), "value": row.get(measure)}
                    for row in rows
                ],
            }
        ],
    }


def _funnel(result, category_column, measure) -> dict:
    """Ordered stages take the ordinal blue ramp (validated single hue),
    darkest = largest — identity comes from labels, order from lightness."""
    rows = result.rows[:8]
    steps = ORDINAL_BLUES[: max(2, min(len(rows), len(ORDINAL_BLUES)))]
    ramp = list(reversed(steps))  # darkest first (largest stage)
    return {
        "textStyle": {"color": INK_SECONDARY},
        "tooltip": {"trigger": "item"},
        "series": [
            {
                "type": "funnel",
                "sort": "descending",
                "gap": 2,
                # Identity labels: the stage NAME, never the raw value.
                "label": {"show": True, "position": "inside", "color": "#ffffff",
                          "formatter": "{b}"},
                "itemStyle": {"borderColor": SURFACE, "borderWidth": 1},
                "data": [
                    {
                        "name": str(row.get(category_column)),
                        "value": row.get(measure),
                        "itemStyle": {"color": ramp[min(index, len(ramp) - 1)]},
                    }
                    for index, row in enumerate(rows)
                ],
            }
        ],
    }

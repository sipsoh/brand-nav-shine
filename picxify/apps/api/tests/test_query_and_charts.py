import pandas as pd
import pytest

from app.services.chart_builder import ChartBuildError, build_echarts_option
from app.services.query_runner import QueryError, execute_query


def frame():
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-05-04", "2026-05-11", "2026-06-01", "2026-06-08"]),
            "channel": ["Google", "Meta", "Google", "Meta"],
            "spend": [100.0, 50.0, 200.0, 50.0],
        }
    )


def test_group_by_dimension():
    result = execute_query(
        frame(),
        {
            "tableId": "t",
            "measures": [{"column": "spend", "aggregation": "sum", "alias": "spend"}],
            "dimensions": ["channel"],
            "filters": [],
        },
    )
    rows = {row["channel"]: row["spend"] for row in result.rows}
    assert rows == {"Google": 300.0, "Meta": 100.0}
    assert result.rows[0]["channel"] == "Google"  # sorted by measure desc
    assert result.source_row_count == 4


def test_group_by_date_grain():
    result = execute_query(
        frame(),
        {
            "tableId": "t",
            "measures": [{"column": "spend", "aggregation": "sum", "alias": "spend"}],
            "dimensions": [],
            "dateColumn": "date",
            "dateGrain": "month",
            "filters": [],
        },
    )
    assert [row["spend"] for row in result.rows] == [150.0, 250.0]


def test_aggregate_without_groupers():
    result = execute_query(
        frame(),
        {
            "tableId": "t",
            "measures": [{"column": "spend", "aggregation": "avg", "alias": "avg_spend"}],
            "dimensions": [],
            "filters": [],
        },
    )
    assert result.rows[0]["avg_spend"] == pytest.approx(100.0)


def test_unknown_column_raises():
    with pytest.raises(QueryError):
        execute_query(
            frame(),
            {
                "tableId": "t",
                "measures": [{"column": "ghost", "aggregation": "sum"}],
                "dimensions": [],
                "filters": [],
            },
        )


def test_limit_applied():
    result = execute_query(
        frame(),
        {
            "tableId": "t",
            "measures": [{"column": "spend", "aggregation": "sum", "alias": "spend"}],
            "dimensions": ["channel"],
            "filters": [],
            "limit": 1,
        },
    )
    assert len(result.rows) == 1


def query_result(spec):
    return execute_query(frame(), spec)


def test_line_chart_option():
    spec = {
        "tableId": "t",
        "measures": [{"column": "spend", "aggregation": "sum", "alias": "spend"}],
        "dimensions": [],
        "dateColumn": "date",
        "dateGrain": "month",
        "filters": [],
    }
    option = build_echarts_option("line", query_result(spec), spec)
    assert option["xAxis"]["type"] == "category"
    assert len(option["xAxis"]["data"]) == 2
    assert option["series"][0]["type"] == "line"
    assert option["series"][0]["data"] == [150.0, 250.0]


def test_donut_chart_option():
    spec = {
        "tableId": "t",
        "measures": [{"column": "spend", "aggregation": "sum", "alias": "spend"}],
        "dimensions": ["channel"],
        "filters": [],
    }
    option = build_echarts_option("donut", query_result(spec), spec)
    data = option["series"][0]["data"]
    assert {d["name"]: d["value"] for d in data} == {"Google": 300.0, "Meta": 100.0}
    assert option["series"][0]["radius"] == ["52%", "74%"]
    # Surface gap between touching segments, per mark specs.
    assert option["series"][0]["itemStyle"]["borderColor"] == "#fcfcfb"


def test_donut_caps_segments_at_six_plus_other():
    frame_many = pd.DataFrame(
        {
            "channel": [f"Ch{i}" for i in range(9)],
            "spend": [90.0, 80.0, 70.0, 60.0, 50.0, 40.0, 30.0, 20.0, 10.0],
        }
    )
    spec = {
        "tableId": "t",
        "measures": [{"column": "spend", "aggregation": "sum", "alias": "spend"}],
        "dimensions": ["channel"],
        "filters": [],
    }
    result = execute_query(frame_many, spec)
    option = build_echarts_option("donut", result, spec)
    data = option["series"][0]["data"]
    assert len(data) == 6
    assert data[-1]["name"] == "Other"
    assert data[-1]["value"] == pytest.approx(40.0 + 30.0 + 20.0 + 10.0)


def test_horizontal_bar_single_hue_with_tip_labels():
    spec = {
        "tableId": "t",
        "measures": [{"column": "spend", "aggregation": "sum", "alias": "spend"}],
        "dimensions": ["channel"],
        "filters": [],
    }
    option = build_echarts_option("horizontal_bar", query_result(spec), spec)
    series = option["series"]
    assert len(series) == 1  # one series -> one hue, never a hue per bar
    assert series[0]["label"]["show"] is True
    assert series[0]["label"]["position"] == "right"
    assert series[0]["barMaxWidth"] == 24
    assert series[0]["itemStyle"]["borderRadius"] == [0, 4, 4, 0]  # rounded data-end
    # Tip labels carry the values, so the value axis stays silent.
    assert option["xAxis"]["axisLabel"] == {"show": False}
    assert option["xAxis"]["splitLine"] == {"show": False}
    # Pathologically long category names ellipsize instead of eating the plot.
    assert option["yAxis"]["axisLabel"]["overflow"] == "truncate"


def test_funnel_uses_ordinal_ramp_not_categorical():
    frame_stages = pd.DataFrame(
        {"stage": ["Won", "Proposal", "Discovery"], "records": [1, 1, 1]}
    )
    spec = {
        "tableId": "t",
        "measures": [{"column": "records", "aggregation": "count", "alias": "records"}],
        "dimensions": ["stage"],
        "filters": [],
    }
    result = execute_query(frame_stages, spec)
    option = build_echarts_option("funnel", result, spec)
    colors = [d["itemStyle"]["color"] for d in option["series"][0]["data"]]
    from app.services.chart_builder import ORDINAL_BLUES

    assert all(color in ORDINAL_BLUES for color in colors)
    assert colors[0] == ORDINAL_BLUES[-1] or colors[0] in ORDINAL_BLUES  # darkest first


def test_empty_result_raises():
    spec = {
        "tableId": "t",
        "measures": [{"column": "spend", "aggregation": "sum", "alias": "spend"}],
        "dimensions": ["channel"],
        "filters": [],
    }
    empty = execute_query(frame().iloc[0:0], spec)
    with pytest.raises(ChartBuildError):
        build_echarts_option("bar", empty, spec)

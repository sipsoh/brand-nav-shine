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
    assert option["series"][0]["radius"] == ["45%", "72%"]


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

"""Column-coverage guarantee: every summable numeric column is represented on
the dashboard. Keyword recognition may RANK columns; it must never GATE them
(regression: an AR-aging report's seven bucket columns and its 'Total AR'
headline were silently dropped because no keyword rule knew them)."""

import pandas as pd

from app.services.chart_builder import build_echarts_option
from app.services.dashboard_planner import (
    PlanningContext,
    ColumnCtx,
    _primary_measure,
    _ranked_summables,
    _sibling_group,
    build_fallback_spec,
)
from app.services.insight_engine import ColumnMeta, compute_insights
from app.services.query_runner import QueryResult


def _aging_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Operator": ["A", "B", "C", "D"] * 3,
            "0-30 Days": [1000.0, 2000.0, 1500.0, 900.0] * 3,
            "31-60 Days": [400.0, 100.0, 250.0, 80.0] * 3,
            "61-90 Days": [50.0, 0.0, 120.0, 30.0] * 3,
            "Prepayments": [700.0, 20.0, 90.0, 400.0] * 3,
            "Credits": [300.0, 250.0, 500.0, 120.0] * 3,
            "Total AR": [5000.0, 4000.0, 7000.0, 2500.0] * 3,
            "Occupancy Rate": [0.9, 0.8, 0.95, 0.7] * 3,
            "Year Built": [1985, 1992, 2001, 1978] * 3,
        }
    )


def _aging_columns() -> list[ColumnMeta]:
    def meta(name, semantic="other", role="measure", detected="float"):
        return ColumnMeta(
            name=name, detected_type=detected, semantic_type=semantic, role_hint=role
        )

    return [
        meta("Operator", role="dimension", detected="category"),
        meta("0-30 Days"),
        meta("31-60 Days"),
        meta("61-90 Days"),
        meta("Prepayments"),
        meta("Credits", semantic="revenue"),
        meta("Total AR"),
        meta("Occupancy Rate"),
        meta("Year Built", detected="integer"),
    ]


def _facts():
    return compute_insights(_aging_frame(), table_id="t1", columns=_aging_columns())


def _ctx() -> PlanningContext:
    result = _facts()
    return PlanningContext(
        dataset_id="d1",
        dataset_name="AR Aging",
        table_id="t1",
        table_name="AR Aging",
        row_count=12,
        column_count=9,
        snapshot_uri=None,
        columns=[
            ColumnCtx(
                name=c.name,
                detected_type=c.detected_type,
                semantic_type=c.semantic_type,
                role_hint=c.role_hint,
            )
            for c in _aging_columns()
        ],
        facts=[f.to_dict() for f in result.facts],
        insights=[i.to_dict() for i in result.insights],
        assumptions=[],
        use_case="generic",
        audience="executive",
        template={"code": "generic", "tone": "polished"},
        date_grain=None,
    )


def test_unclassified_numeric_columns_get_total_facts():
    fact_ids = {f.id for f in _facts().facts}
    for slug in ("0_30_days", "31_60_days", "61_90_days", "prepayments", "total_ar"):
        assert f"fact_total_{slug}" in fact_ids


def test_intensive_and_year_columns_get_no_total_facts():
    fact_ids = {f.id for f in _facts().facts}
    assert "fact_total_occupancy_rate" not in fact_ids  # a rate: level, not amount
    assert "fact_total_year_built" not in fact_ids  # calendar years: ordinal


def test_total_prefixed_label_is_not_doubled():
    labels = {f.label for f in _facts().facts}
    assert "Total AR" in labels
    assert "Total Total AR" not in labels


def test_strong_semantics_rank_first_then_magnitude():
    ranked = [c.name for c, _ in _ranked_summables(_ctx())]
    assert ranked[0] == "Credits"  # recognized semantic outranks
    assert ranked[1] == "Total AR"  # then largest unclassified total
    assert _primary_measure(_ctx()).name == "Credits"


def test_sibling_group_detects_bucket_columns_in_order():
    token, group = _sibling_group(_ctx())
    assert token == "days"
    assert [c.name for c in group] == ["0-30 Days", "31-60 Days", "61-90 Days"]


def test_fallback_spec_covers_buckets_and_total_ar():
    spec = build_fallback_spec(_ctx())
    kpi_labels = " ".join(
        w["kpi"]["label"]
        for s in spec["sections"]
        for w in s["widgets"]
        if w["type"] == "kpi"
    )
    assert "Total AR" in kpi_labels
    chart_measures = {
        m["column"]
        for s in spec["sections"]
        for w in s["widgets"]
        if w["type"] == "chart"
        for m in w["chart"]["querySpec"].get("measures", [])
    }
    assert {"0-30 Days", "31-60 Days", "61-90 Days"} <= chart_measures


def test_column_totals_bar_transposes_and_keeps_order():
    result = QueryResult(
        columns=["0-30 Days", "31-60 Days", "61-90 Days"],
        rows=[{"0-30 Days": 5400.0, "31-60 Days": 830.0, "61-90 Days": 200.0}],
        source_row_count=12,
    )
    spec = {"tableId": "t1", "measures": [], "dimensions": [], "filters": []}
    option = build_echarts_option("horizontal_bar", result, spec)
    # Reversed so the first bucket renders at the top of the chart.
    assert option["yAxis"]["data"] == ["61-90 Days", "31-60 Days", "0-30 Days"]
    assert option["series"][0]["data"] == [200.0, 830.0, 5400.0]

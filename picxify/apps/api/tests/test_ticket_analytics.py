"""Count-based analytics for operational data (tickets/cases) — no strong measure."""

import types

import pandas as pd
import pytest

from app.services.dashboard_pipeline import GenerationError, select_primary_table
from app.services.dashboard_planner import (
    ColumnCtx,
    PlanningContext,
    build_fallback_spec,
    execute_charts,
)
from app.services.insight_engine import ColumnMeta, compute_insights
from app.services.semantic_mapper import ColumnInput, TableInput, map_dataset
from app.services.spec_validator import assert_source_traces, validate_spec
from app.services.templates import select_template


def ticket_frame():
    # June coverage runs to the 25th so the month counts as complete.
    dates = pd.to_datetime(
        ["2026-03-02", "2026-03-10", "2026-05-04", "2026-05-11", "2026-05-18",
         "2026-06-01", "2026-06-12", "2026-06-25"]
    )
    return pd.DataFrame(
        {
            "number": [f"INC{i}" for i in range(8)],
            "created": dates,
            "service_offering": ["Network", "Network", "Entra", "Network", "Entra",
                                 "Network", "Network", "Entra"],
            "state": ["Closed"] * 8,
            "duration": [100.0, 200.0, 150.0, 120.0, 180.0, 90.0, 110.0, 160.0],
        }
    )


TICKET_META = [
    ColumnMeta("number", "id", "id", "id"),
    ColumnMeta("created", "date", "date", "date"),
    ColumnMeta("service_offering", "category", "channel", "dimension"),
    ColumnMeta("state", "category", "status", "dimension"),
    ColumnMeta("duration", "float", "duration", "measure"),
]


def test_count_based_trend_when_no_strong_measure():
    result = compute_insights(ticket_frame(), "tbl_1", TICKET_META)
    trend = next(f for f in result.facts if f.id.startswith("fact_trend_records"))
    # March: 2 tickets ... May: 3, June: 3 -> 0% MoM
    assert trend.value == pytest.approx(0.0)
    trend_insight = next(i for i in result.insights if i.insight_type == "trend")
    assert trend_insight.severity == "neutral"
    assert "records" in trend_insight.headline


def test_duration_gets_average_not_total():
    result = compute_insights(ticket_frame(), "tbl_1", TICKET_META)
    fact_ids = {f.id for f in result.facts}
    assert "fact_avg_duration" in fact_ids
    assert "fact_total_duration" not in fact_ids
    avg = next(f for f in result.facts if f.id == "fact_avg_duration")
    assert avg.value == pytest.approx(138.75)


def test_top_contributor_by_record_count():
    result = compute_insights(ticket_frame(), "tbl_1", TICKET_META)
    top = next(f for f in result.facts if f.id == "fact_top_service_offering_records")
    assert top.value == pytest.approx(5 / 8)  # Network: 5 of 8 tickets


def make_ticket_ctx(df):
    columns = [ColumnCtx(m.name, m.detected_type, m.semantic_type, m.role_hint)
               for m in TICKET_META]
    result = compute_insights(df, "tbl_1", TICKET_META)
    return PlanningContext(
        dataset_id="ds_1",
        dataset_name="Ticket Analysis",
        table_id="tbl_1",
        table_name="Tickets",
        row_count=len(df),
        column_count=len(df.columns),
        snapshot_uri="x.parquet",
        columns=columns,
        facts=[f.to_dict() for f in result.facts],
        insights=[i.to_dict() for i in result.insights],
        assumptions=[],
        use_case="operations",
        audience="team",
        template=select_template("operations"),
        date_grain="month",
    )


def test_ticket_dashboard_uses_counts_and_avg_duration():
    df = ticket_frame()
    spec = build_fallback_spec(make_ticket_ctx(df))
    execute_charts(spec, {"tbl_1": df})
    validate_spec(spec)
    assert_source_traces(spec)

    charts = {
        w["id"]: w["chart"]
        for s in spec["sections"]
        for w in s["widgets"]
        if w["type"] == "chart"
    }
    # Trend and breakdown count records; nothing sums duration.
    assert charts["w_chart_trend"]["querySpec"]["measures"][0]["aggregation"] == "count"
    assert charts["w_chart_breakdown"]["querySpec"]["measures"][0]["aggregation"] == "count"
    assert charts["w_chart_avg_measure"]["querySpec"]["measures"][0]["aggregation"] == "avg"
    for chart in charts.values():
        for m in chart["querySpec"]["measures"]:
            assert not (m["column"] == "duration" and m["aggregation"] == "sum")

    kpi_ids = {w["id"] for s in spec["sections"] for w in s["widgets"] if w["type"] == "kpi"}
    assert "w_kpi_avg_measure" in kpi_ids


def test_operations_use_case_detected():
    table = TableInput(
        name="Tickets",
        columns=[
            ColumnInput("Number", "number", "id", None, 1.0, []),
            ColumnInput("Created", "created", "date", None, 0.9, []),
            ColumnInput("State", "state", "category", None, 0.01, []),
            ColumnInput("Duration", "duration", "float", None, 0.8, []),
        ],
    )
    mapping = map_dataset([table], filename="Ticket_Analysis_2026.xlsx")
    assert mapping.use_case_candidates[0]["useCase"] == "operations"
    assert mapping.column_mappings["Duration"].semantic_type == "duration"


def fake_table(id_, name, row_count, columns, quality):
    return types.SimpleNamespace(
        id=id_, name=name, row_count=row_count,
        profile={"columns": columns, "qualityScore": quality},
    )


def test_primary_table_prefers_clean_named_sheets():
    helper = fake_table(
        "t1", "NEW DATA SHEET", 7583,
        ["unnamed_0", "unnamed_1", "facility_ci_created", "duration_calc"], 0.2,
    )
    clean = fake_table(
        "t2", "Tickets", 7581,
        ["number", "location", "service_offering", "state", "created", "duration"], 0.85,
    )
    assert select_primary_table([helper, clean]).name == "Tickets"


def test_primary_table_respects_explicit_request():
    a = fake_table("t1", "A", 10, ["x"], 0.9)
    b = fake_table("t2", "B", 10, ["y"], 0.9)
    assert select_primary_table([a, b], requested_table_id="t1").name == "A"
    with pytest.raises(GenerationError):
        select_primary_table([a, b], requested_table_id="ghost")


def test_partial_current_period_excluded_from_trend():
    # Jan (28) + Mar (14) + 2 days of Apr (span > 70 days -> monthly grain):
    # the partial April must be excluded, comparing Mar vs Jan (empty Feb skipped).
    dates = (
        [f"2026-01-{d:02d}" for d in range(1, 29)]      # 28 in January
        + [f"2026-03-{d:02d}" for d in range(1, 15)]    # 14 in March
        + ["2026-04-01", "2026-04-02"]                  # partial April
    )
    df = pd.DataFrame({"number": [f"T{i}" for i in range(len(dates))],
                       "created": pd.to_datetime(dates)})
    meta = [
        ColumnMeta("number", "id", "id", "id"),
        ColumnMeta("created", "date", "date", "date"),
    ]
    result = compute_insights(df, "tbl_1", meta)
    trend = next(f for f in result.facts if f.id.startswith("fact_trend_records"))
    assert trend.value == pytest.approx(14 / 28 - 1)  # -50%, Mar vs Jan
    assert "partial current month excluded" in trend.source_trace.calculation


def test_skewed_distribution_not_reported_as_outliers():
    # Long-tail data where MAD flags >10% of values: no outlier insight.
    values = [10.0] * 60 + [10_000.0 * (i + 1) for i in range(40)]
    df = pd.DataFrame({"duration": values})
    meta = [ColumnMeta("duration", "float", "duration", "measure")]
    result = compute_insights(df, "tbl_1", meta)
    assert not any(i.insight_type == "outlier" for i in result.insights)


def test_hour_minute_text_not_parsed_as_dates():
    from app.services.normalization import normalize_table

    df = pd.DataFrame({"hrs": ["20 Hours", "3 Hours", "0 Hours"],
                       "close_date": ["2026-05-04", "2026-05-11", "2026-06-01"]})
    result = normalize_table(df)
    assert not str(result.dataframe["hrs"].dtype).startswith("datetime")
    assert str(result.dataframe["close_date"].dtype).startswith("datetime")

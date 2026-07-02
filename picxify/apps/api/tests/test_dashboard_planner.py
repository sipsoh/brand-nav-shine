import pandas as pd

from app.services.dashboard_planner import (
    ColumnCtx,
    PlanningContext,
    build_fallback_spec,
    execute_charts,
    plan_dashboard,
)
from app.services.insight_engine import ColumnMeta, compute_insights
from app.services.spec_validator import assert_source_traces, validate_spec
from app.services.templates import select_template


def marketing_df():
    return pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2026-03-02", "2026-03-09", "2026-05-04", "2026-05-11", "2026-06-01", "2026-06-08"]
            ),
            "campaign": ["A", "B", "A", "B", "A", "A"],
            "spend": [100.0, 100.0, 150.0, 50.0, 300.0, 100.0],
        }
    )


def make_ctx(df) -> PlanningContext:
    columns = [
        ColumnCtx("date", "date", "date", "date"),
        ColumnCtx("campaign", "category", "campaign", "dimension"),
        ColumnCtx("spend", "float", "cost", "measure"),
    ]
    meta = [ColumnMeta(c.name, c.detected_type, c.semantic_type, c.role_hint) for c in columns]
    result = compute_insights(df, "tbl_1", meta)
    return PlanningContext(
        dataset_id="ds_1",
        dataset_name="June Campaigns",
        table_id="tbl_1",
        table_name="campaigns",
        row_count=len(df),
        column_count=len(df.columns),
        snapshot_uri="workspaces/x/datasets/y/tables/campaigns.parquet",
        columns=columns,
        facts=[f.to_dict() for f in result.facts],
        insights=[i.to_dict() for i in result.insights],
        assumptions=[
            {
                "id": "asm_1",
                "label": "Detected this as a marketing dataset.",
                "status": "needs_review",
                "confidence": 0.85,
                "editable": True,
                "source": "semantic_mapper",
                "affectedColumns": [],
            }
        ],
        use_case="marketing",
        audience="client",
        template=select_template("marketing"),
        date_grain="month",
    )


def test_fallback_spec_validates_and_charts_execute():
    df = marketing_df()
    ctx = make_ctx(df)
    spec, planner = plan_dashboard(ctx, llm=None)
    assert planner == "fallback"

    execute_charts(spec, {"tbl_1": df})
    validate_spec(spec)
    assert_source_traces(spec)

    widget_types = {
        w["type"] for section in spec["sections"] for w in section["widgets"]
    }
    assert {"kpi", "chart", "insight_card", "text"} <= widget_types

    charts = [
        w["chart"]
        for section in spec["sections"]
        for w in section["widgets"]
        if w["type"] == "chart"
    ]
    assert charts, "expected at least one chart"
    for chart in charts:
        assert chart["echartsOption"].get("series"), "chart option must be built by code"
        assert chart["sourceTrace"]["generatedBy"] == "code"
        assert chart["sourceTrace"]["rowCount"] > 0

    assert spec["insights"], "top-level insights should be present"
    assert spec["actions"], "actions should be present"


def test_kpi_values_are_backed_by_facts():
    from app.services.dashboard_planner import _acceptable_kpi_values

    df = marketing_df()
    ctx = make_ctx(df)
    spec = build_fallback_spec(ctx)
    fact_values = _acceptable_kpi_values(ctx.facts)
    kpi_count = 0
    for section in spec["sections"]:
        for widget in section["widgets"]:
            if widget["type"] == "kpi":
                kpi_count += 1
                assert str(widget["kpi"]["value"]) in fact_values
    assert kpi_count >= 2


def test_kpi_values_are_human_formatted():
    from app.services.dashboard_planner import compact_number, format_kpi_value

    assert format_kpi_value(48200.0, "currency") == "$48.2K"
    assert format_kpi_value(0.6125, "percent") == "61%"
    assert format_kpi_value(7581, "number") == "7,581"
    assert format_kpi_value(222134.4, "number") == "222.1K"
    assert compact_number(1_250_000) == "1.2M"  # round-half-even
    assert format_kpi_value("already formatted", None) == "already formatted"


def test_broken_chart_widgets_are_dropped_not_rendered():
    df = marketing_df()
    ctx = make_ctx(df)
    spec = build_fallback_spec(ctx)
    # Sabotage one chart with a nonexistent column.
    for section in spec["sections"]:
        for widget in section["widgets"]:
            if widget["id"] == "w_chart_breakdown":
                widget["chart"]["querySpec"]["dimensions"] = ["ghost_column"]
    execute_charts(spec, {"tbl_1": df})
    widget_ids = {w["id"] for s in spec["sections"] for w in s["widgets"]}
    assert "w_chart_breakdown" not in widget_ids
    assert "w_chart_trend" in widget_ids
    validate_spec(spec)


class BrokenLLM:
    def complete_json(self, system, user, schema, schema_name):
        return {"garbage": True}


def test_invalid_llm_plan_falls_back():
    df = marketing_df()
    ctx = make_ctx(df)
    spec, planner = plan_dashboard(ctx, llm=BrokenLLM())
    assert planner == "fallback"
    execute_charts(spec, {"tbl_1": df})
    validate_spec(spec)


class HallucinatingLLM:
    """Returns a schema-valid spec whose KPI value and insight id are invented."""

    def __init__(self, base_spec):
        self.base_spec = base_spec

    def complete_json(self, system, user, schema, schema_name):
        import copy

        spec = copy.deepcopy(self.base_spec)
        trace = {
            "tableId": "tbl_1",
            "columns": ["spend"],
            "filters": [],
            "calculation": "made up",
            "rowCount": 6,
            "generatedBy": "code",
        }
        spec["sections"][0]["widgets"].append(
            {
                "id": "w_fake_kpi",
                "type": "kpi",
                "title": "Fake KPI",
                "kpi": {"value": 999999, "label": "Invented number", "sourceTrace": trace},
            }
        )
        spec["sections"][0]["widgets"].append(
            {
                "id": "w_fake_insight",
                "type": "insight_card",
                "title": "Fake insight",
                "insight": {
                    "id": "insight_invented",
                    "headline": "Invented finding",
                    "detail": "Not computed by code.",
                    "severity": "positive",
                    "confidence": 0.99,
                    "facts": [],
                    "sourceTrace": trace,
                },
            }
        )
        return spec


def test_llm_hallucinations_are_guarded():
    df = marketing_df()
    ctx = make_ctx(df)
    base = build_fallback_spec(ctx)
    spec, planner = plan_dashboard(ctx, llm=HallucinatingLLM(base))
    assert planner == "llm"
    widget_ids = {w["id"] for s in spec["sections"] for w in s["widgets"]}
    assert "w_fake_kpi" not in widget_ids
    assert "w_fake_insight" not in widget_ids
    # Legitimate widgets survive.
    assert "w_kpi_rows" in widget_ids
    execute_charts(spec, {"tbl_1": df})
    validate_spec(spec)
    assert_source_traces(spec)

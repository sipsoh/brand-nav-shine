"""Dashboard planning (SETUP.md §9.7).

Two planners produce a DashboardSpec draft:
1. A deterministic fallback that fills the selected template from computed
   facts/insights — always available, always valid.
2. An optional LLM planner constrained to the canonical schema, whose output is
   validated, repaired at most once, and then passed through hard guards:
   insights are swapped back to the code-computed versions by id, KPI values
   must match a computed fact, charts are always re-executed by code. Any
   failure at any step falls back to (1).

Chart echartsOptions are never taken from a model — `execute_charts` builds
them from querySpecs after planning.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.prompts.dashboard_planner_prompt import PROMPT_VERSION, REPAIR_PROMPT, SYSTEM_PROMPT
from app.services.chart_builder import ChartBuildError, build_echarts_option
from app.services.llm import LLMClient, LLMUnavailable
from app.services.query_runner import QueryError, execute_query
from app.services.spec_validator import SpecValidationError, validate_spec

logger = logging.getLogger(__name__)

SPEC_VERSION = "0.1.0"
MAX_SPEC_INSIGHTS = 6
MAX_INSIGHT_CARDS = 4


@dataclass
class ColumnCtx:
    name: str
    detected_type: str
    semantic_type: str | None
    role_hint: str | None


@dataclass
class PlanningContext:
    dataset_id: str
    dataset_name: str
    table_id: str
    table_name: str
    row_count: int
    column_count: int
    snapshot_uri: str | None
    columns: list[ColumnCtx]
    facts: list[dict]  # ComputedFact.to_dict() shapes (with ids)
    insights: list[dict]  # ComputedInsight.to_dict() shapes (with insightType)
    assumptions: list[dict]  # canonical assumption shapes
    use_case: str
    audience: str
    template: dict
    date_grain: str | None
    title_hint: str | None = None
    extra_metadata: dict = field(default_factory=dict)


def plan_dashboard(ctx: PlanningContext, llm: LLMClient | None) -> tuple[dict, str]:
    """Returns (spec, planner_name). Charts still need execute_charts()."""
    if llm is None:
        return build_fallback_spec(ctx), "fallback"
    try:
        spec = _plan_with_llm(ctx, llm)
        return spec, "llm"
    except Exception as error:
        logger.warning("LLM planner failed (%s); using fallback planner.", error)
        return build_fallback_spec(ctx), "fallback"


# --- shared conversions ---------------------------------------------------


def compact_number(value: float) -> str:
    magnitude = abs(value)
    if magnitude >= 1e9:
        return f"{value / 1e9:,.1f}B"
    if magnitude >= 1e6:
        return f"{value / 1e6:,.1f}M"
    if magnitude >= 10_000:
        return f"{value / 1e3:,.1f}K"
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.1f}"


def format_kpi_value(value, unit: str | None) -> str | float | int:
    """Human-scale KPI display values; raw numbers stay in the source trace."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return value
    if unit == "percent":
        return f"{value * 100:.0f}%"
    if unit == "currency":
        return f"${compact_number(value)}"
    return compact_number(value)


def to_spec_fact(fact: dict) -> dict | None:
    """Canonical `fact` shape: no id field, value must be a scalar."""
    if fact.get("value") is None:
        return None
    return {
        "label": fact["label"],
        "value": fact["value"],
        "unit": fact.get("unit"),
        "sourceTrace": fact["sourceTrace"],
    }


def to_spec_insight(insight: dict) -> dict:
    """Canonical `insight` shape: drops insightType and per-fact ids."""
    facts = [f for f in (to_spec_fact(fact) for fact in insight.get("facts", [])) if f]
    return {
        "id": insight["id"],
        "headline": insight["headline"][:140],
        "detail": insight["detail"][:500],
        "severity": insight["severity"],
        "confidence": insight["confidence"],
        "facts": facts,
        "sourceTrace": insight["sourceTrace"],
    }


def _fact_by_prefix(ctx: PlanningContext, prefix: str) -> dict | None:
    return next((f for f in ctx.facts if f["id"].startswith(prefix)), None)


def _columns_by_role(ctx: PlanningContext, role: str) -> list[ColumnCtx]:
    return [c for c in ctx.columns if c.role_hint == role]


# Mirrors insight_engine.STRONG_SEMANTICS: measures whose sums mean something.
# Ratings and durations are explicitly absent — they are averaged, never summed.
STRONG_MEASURE_PRIORITY = ["revenue", "cost", "money", "conversion", "engagement", "quantity"]


def _primary_measure(ctx: PlanningContext) -> ColumnCtx | None:
    """The measure worth summing. Durations and unclassified numerics are
    excluded — without a strong measure the dashboard counts records instead."""
    measures = [
        c for c in _columns_by_role(ctx, "measure") if c.semantic_type in STRONG_MEASURE_PRIORITY
    ]
    measures.sort(key=lambda c: STRONG_MEASURE_PRIORITY.index(c.semantic_type))
    return measures[0] if measures else None


def _average_measure(ctx: PlanningContext) -> ColumnCtx | None:
    """Duration or rating: measures that only make sense averaged."""
    return next(
        (c for c in _columns_by_role(ctx, "measure") if c.semantic_type in {"duration", "rating"}),
        None,
    )


def _count_column(ctx: PlanningContext) -> str:
    id_column = next((c for c in ctx.columns if c.role_hint == "id"), None)
    return id_column.name if id_column else ctx.columns[0].name


def _ranked_dimensions(ctx: PlanningContext) -> list[ColumnCtx]:
    priority = ["campaign", "channel", "segment", "region", "stage", "status", "owner"]
    dimensions = [c for c in _columns_by_role(ctx, "dimension") if c.semantic_type != "id"]
    dimensions.sort(
        key=lambda c: priority.index(c.semantic_type)
        if c.semantic_type in priority
        else len(priority)
    )
    return dimensions


def _primary_dimension(ctx: PlanningContext) -> ColumnCtx | None:
    dimensions = _ranked_dimensions(ctx)
    return dimensions[0] if dimensions else None


# --- deterministic fallback planner ----------------------------------------


def build_fallback_spec(ctx: PlanningContext) -> dict:
    title = (ctx.title_hint or f"{ctx.dataset_name} Report").strip()[:120]
    if len(title) < 3:
        title = "Picxify Report"

    sections = []
    hero = _hero_section(ctx)
    if hero:
        sections.append(hero)
    sections.extend(_chart_sections(ctx))
    insight_section = _insights_section(ctx)
    if insight_section:
        sections.append(insight_section)
    sections.append(_appendix_section(ctx))

    return {
        "version": SPEC_VERSION,
        "dashboard": {
            "title": title,
            "subtitle": f"Generated by Picxify from {ctx.row_count:,} rows of {ctx.table_name}",
            "useCase": ctx.use_case,
            "audience": ctx.audience,
            "theme": {"name": "picxify-default", "tone": ctx.template.get("tone", "polished")},
            "generatedAt": datetime.now(timezone.utc).isoformat(),
        },
        "dataSources": [
            {
                "datasetId": ctx.dataset_id,
                "tableId": ctx.table_id,
                "displayName": ctx.table_name,
                "rowCount": ctx.row_count,
                "columnCount": ctx.column_count,
                "snapshotUri": ctx.snapshot_uri,
            }
        ],
        "assumptions": ctx.assumptions,
        "sections": sections,
        "insights": [to_spec_insight(i) for i in ctx.insights[:MAX_SPEC_INSIGHTS]],
        "actions": _actions(ctx),
    }


def _kpi_widget(widget_id: str, title: str, fact: dict, *, value=None,
                change_label=None, direction=None) -> dict:
    return {
        "id": widget_id,
        "type": "kpi",
        "title": title[:100],
        "kpi": {
            "value": value if value is not None
            else format_kpi_value(fact["value"], fact.get("unit")),
            "label": fact["label"][:100],
            "changeLabel": change_label,
            "direction": direction,
            "sourceTrace": fact["sourceTrace"],
        },
    }


def _hero_section(ctx: PlanningContext) -> dict | None:
    widgets: list[dict] = []

    headlines = [i["headline"] for i in ctx.insights[:3]]
    if headlines:
        widgets.append(
            {
                "id": "w_exec_summary",
                "type": "text",
                "title": "Executive summary",
                "markdown": "\n".join(f"- {headline}" for headline in headlines),
            }
        )

    row_fact = _fact_by_prefix(ctx, "fact_row_count")
    if row_fact:
        widgets.append(_kpi_widget("w_kpi_rows", "Rows analyzed", row_fact))

    measure = _primary_measure(ctx)
    if measure:
        total_fact = _fact_by_prefix(ctx, f"fact_total_{_slug(measure.name)}")
        if total_fact:
            widgets.append(
                _kpi_widget("w_kpi_total", f"Total {measure.name}"[:100], total_fact)
            )

    average = _average_measure(ctx)
    if average:
        avg_fact = _fact_by_prefix(ctx, f"fact_avg_{_slug(average.name)}")
        if avg_fact:
            widgets.append(
                _kpi_widget("w_kpi_avg_measure", f"Average {average.name}"[:100], avg_fact)
            )

    trend_fact = _fact_by_prefix(ctx, "fact_trend_")
    if trend_fact and isinstance(trend_fact["value"], (int, float)):
        change = float(trend_fact["value"])
        widgets.append(
            _kpi_widget(
                "w_kpi_trend",
                trend_fact["label"][:100],
                trend_fact,
                value=f"{change * 100:+.0f}%",
                change_label="vs previous period",
                direction="up" if change > 0 else "down" if change < 0 else "flat",
            )
        )

    win_fact = _fact_by_prefix(ctx, "fact_win_rate")
    if win_fact and isinstance(win_fact["value"], (int, float)):
        widgets.append(
            _kpi_widget(
                "w_kpi_win_rate",
                "Win rate",
                win_fact,
                value=f"{float(win_fact['value']) * 100:.0f}%",
            )
        )

    if not widgets:
        return None
    return {"id": "sec_hero", "title": "Highlights", "layout": "hero", "widgets": widgets}


def _chart_sections(ctx: PlanningContext) -> list[dict]:
    """Two aligned chart sections: time-series charts full-width under
    'Performance over time', dimension charts in a uniform 'Breakdowns' grid."""
    time_widgets, breakdown_widgets = _build_chart_widgets(ctx)
    sections = []
    if time_widgets:
        sections.append(
            {
                "id": "sec_time",
                "title": "Performance over time",
                "layout": "full_width",
                "widgets": time_widgets,
            }
        )
    if breakdown_widgets:
        sections.append(
            {
                "id": "sec_breakdowns",
                "title": "Breakdowns",
                "layout": "grid",
                "widgets": breakdown_widgets,
            }
        )
    return sections


def _build_chart_widgets(ctx: PlanningContext) -> tuple[list[dict], list[dict]]:
    time_widgets: list[dict] = []
    breakdown_widgets: list[dict] = []
    measure = _primary_measure(ctx)
    average = _average_measure(ctx)
    dates = _columns_by_role(ctx, "date")
    dimensions = _ranked_dimensions(ctx)
    dimension = dimensions[0] if dimensions else None
    secondary = dimensions[1] if len(dimensions) > 1 else None
    stage = next((c for c in ctx.columns if c.semantic_type in {"stage", "status"}), None)

    # Without a strong measure, count records instead of summing arbitrary numbers.
    if measure:
        metric_measures = [{"column": measure.name, "aggregation": "sum", "alias": measure.name}]
        metric_label = measure.name
    else:
        metric_measures = [
            {"column": _count_column(ctx), "aggregation": "count", "alias": "records"}
        ]
        metric_label = "records"

    if dates and ctx.date_grain:
        time_widgets.append(
            _chart_widget(
                "w_chart_trend",
                f"{metric_label} over time",
                "line",
                {
                    "tableId": ctx.table_id,
                    "measures": metric_measures,
                    "dimensions": [],
                    "dateColumn": dates[0].name,
                    "dateGrain": ctx.date_grain,
                    "filters": [],
                },
                size="xl",
            )
        )

    if dimension and dates and ctx.date_grain:
        time_widgets.append(
            _chart_widget(
                "w_chart_mix",
                f"{metric_label} over time by {dimension.name}",
                "stacked_bar",
                {
                    "tableId": ctx.table_id,
                    "measures": metric_measures,
                    "dimensions": [dimension.name],
                    "dateColumn": dates[0].name,
                    "dateGrain": ctx.date_grain,
                    "filters": [],
                    "limit": 500,
                },
                size="xl",
            )
        )

    if dimension:
        # Magnitude comparison across nominal categories -> single-hue bars
        # (a donut is for part-to-whole at a glance, not comparing values).
        breakdown_widgets.append(
            _chart_widget(
                "w_chart_breakdown",
                f"{metric_label} by {dimension.name}",
                "horizontal_bar",
                {
                    "tableId": ctx.table_id,
                    "measures": metric_measures,
                    "dimensions": [dimension.name],
                    "filters": [],
                    "limit": 8,
                },
                size="md",
            )
        )

    if secondary is not None and secondary is not stage:
        breakdown_widgets.append(
            _chart_widget(
                "w_chart_secondary",
                f"{metric_label} by {secondary.name}",
                "horizontal_bar",
                {
                    "tableId": ctx.table_id,
                    "measures": metric_measures,
                    "dimensions": [secondary.name],
                    "filters": [],
                    "limit": 8,
                },
                size="md",
            )
        )

    if average and dimension:
        breakdown_widgets.append(
            _chart_widget(
                "w_chart_avg_measure",
                f"Average {average.name} by {dimension.name}",
                "horizontal_bar",
                {
                    "tableId": ctx.table_id,
                    "measures": [
                        {
                            "column": average.name,
                            "aggregation": "avg",
                            "alias": f"avg_{_slug(average.name)}",
                        }
                    ],
                    "dimensions": [dimension.name],
                    "filters": [],
                    "limit": 8,
                },
                size="md",
            )
        )

    if stage is not None and stage is not dimension:
        breakdown_widgets.append(
            _chart_widget(
                "w_chart_funnel",
                f"Records by {stage.name}",
                "funnel" if _funnel_reads_as_flow(ctx, stage) else "horizontal_bar",
                {
                    "tableId": ctx.table_id,
                    "measures": [{"column": stage.name, "aggregation": "count", "alias": "records"}],
                    "dimensions": [stage.name],
                    "filters": [],
                    "limit": 8,
                },
                size="md",
            )
        )

    return time_widgets, breakdown_widgets


def _funnel_reads_as_flow(ctx: PlanningContext, stage: ColumnCtx) -> bool:
    """A funnel is for ordered pipeline flow (Lead -> Qualified -> Won).

    Status columns (Open/Closed/Pending) are nominal states, and any
    distribution where one value dwarfs the rest collapses the remaining
    wedges into unreadable slivers — both read better as bars.
    """
    if stage.semantic_type != "stage":
        return False
    counts = sorted(
        (
            int(fact["value"])
            for fact in ctx.facts
            if str(fact.get("id", "")).startswith("fact_stage_")
            and isinstance(fact.get("value"), (int, float))
        ),
        reverse=True,
    )
    if len(counts) < 3:
        return False
    return counts[1] >= counts[0] * 0.25


def _chart_widget(
    widget_id: str, title: str, chart_type: str, query_spec: dict, size: str = "md"
) -> dict:
    return {
        "id": widget_id,
        "type": "chart",
        "title": title[:100],
        "size": size,
        "chart": {
            "chartType": chart_type,
            "querySpec": query_spec,
            "echartsOption": {},
            "sourceTrace": _trace_for_query(query_spec, 0),
        },
    }


def _insights_section(ctx: PlanningContext) -> dict | None:
    widgets = [
        {
            "id": f"w_insight_{index}",
            "type": "insight_card",
            "title": insight["headline"][:100],
            "insight": to_spec_insight(insight),
        }
        for index, insight in enumerate(ctx.insights[:MAX_INSIGHT_CARDS])
    ]
    if not widgets:
        return None
    return {
        "id": "sec_insights",
        "title": "What stands out",
        "layout": "narrative",
        "widgets": widgets,
    }


def _appendix_section(ctx: PlanningContext) -> dict:
    return {
        "id": "sec_appendix",
        "title": "Sources and assumptions",
        "layout": "appendix",
        "widgets": [
            {"id": "w_assumptions", "type": "assumption_panel", "title": "Assumptions"},
            {"id": "w_sources", "type": "source_panel", "title": "Data sources"},
        ],
    }


def _actions(ctx: PlanningContext) -> list[dict]:
    actions: list[dict] = []
    for insight in ctx.insights:
        if insight.get("insightType") == "outlier":
            actions.append(
                {
                    "label": "Review flagged outlier values"[:120],
                    "priority": "high",
                    "rationale": insight["headline"][:300],
                    "sourceInsightId": insight["id"],
                }
            )
        elif insight.get("insightType") == "trend" and insight["severity"] == "negative":
            actions.append(
                {
                    "label": "Investigate the recent decline"[:120],
                    "priority": "high",
                    "rationale": insight["headline"][:300],
                    "sourceInsightId": insight["id"],
                }
            )
        elif insight.get("insightType") == "top_contributor":
            actions.append(
                {
                    "label": "Check concentration risk on the top contributor"[:120],
                    "priority": "medium",
                    "rationale": insight["headline"][:300],
                    "sourceInsightId": insight["id"],
                }
            )
        elif insight.get("insightType") == "data_quality":
            actions.append(
                {
                    "label": "Resolve data quality caveats before sharing"[:120],
                    "priority": "medium",
                    "rationale": insight["headline"][:300],
                    "sourceInsightId": insight["id"],
                }
            )
        if len(actions) >= 4:
            break
    if not actions:
        actions.append(
            {
                "label": "Review the dashboard with your team",
                "priority": "low",
                "rationale": "No urgent anomalies were detected in this dataset.",
                "sourceInsightId": None,
            }
        )
    return actions


# --- LLM planner ------------------------------------------------------------


def _plan_with_llm(ctx: PlanningContext, llm: LLMClient) -> dict:
    from app.services.spec_validator import _validator

    schema = _validator().schema
    payload = json.dumps(
        {
            "template": ctx.template,
            "audience": ctx.audience,
            "useCase": ctx.use_case,
            "titleHint": ctx.title_hint,
            "dataSource": {
                "datasetId": ctx.dataset_id,
                "tableId": ctx.table_id,
                "displayName": ctx.table_name,
                "rowCount": ctx.row_count,
                "columnCount": ctx.column_count,
            },
            "columns": [
                {
                    "name": c.name,
                    "detectedType": c.detected_type,
                    "semanticType": c.semantic_type,
                    "role": c.role_hint,
                }
                for c in ctx.columns
            ],
            "computedFacts": ctx.facts,
            "insights": [to_spec_insight(i) for i in ctx.insights[:MAX_SPEC_INSIGHTS]],
            "assumptions": ctx.assumptions,
            "allowedChartTypes": ["line", "area", "bar", "horizontal_bar", "stacked_bar",
                                  "donut", "pie", "funnel"],
            "dateGrain": ctx.date_grain,
        },
        default=str,
    )

    spec = llm.complete_json(SYSTEM_PROMPT, payload, schema, schema_name="dashboard_spec")
    try:
        validate_spec(spec)
    except SpecValidationError as error:
        repair_user_prompt = REPAIR_PROMPT.format(
            errors="\n".join(error.errors[:10]), spec=json.dumps(spec, default=str)
        )
        spec = llm.complete_json(
            SYSTEM_PROMPT, repair_user_prompt, schema, schema_name="dashboard_spec"
        )
        validate_spec(spec)

    return _enforce_guards(ctx, spec)


def _enforce_guards(ctx: PlanningContext, spec: dict) -> dict:
    """Make an LLM-planned spec trustworthy: known insights only, fact-backed
    KPIs only, code-built charts only."""
    spec["version"] = SPEC_VERSION
    spec["dashboard"]["generatedAt"] = datetime.now(timezone.utc).isoformat()

    known_insights = {i["id"]: to_spec_insight(i) for i in ctx.insights}
    spec["insights"] = [
        known_insights[i["id"]] for i in spec.get("insights", []) if i.get("id") in known_insights
    ]

    acceptable_values = _acceptable_kpi_values(ctx.facts)
    for section in spec.get("sections", []):
        kept = []
        for widget in section.get("widgets", []):
            widget_type = widget.get("type")
            if widget_type == "insight_card":
                insight_id = (widget.get("insight") or {}).get("id")
                if insight_id not in known_insights:
                    logger.warning("Dropping insight widget with unknown id %r", insight_id)
                    continue
                widget["insight"] = known_insights[insight_id]
            elif widget_type == "kpi":
                value = (widget.get("kpi") or {}).get("value")
                if str(value) not in acceptable_values:
                    logger.warning("Dropping KPI widget with unbacked value %r", value)
                    continue
            elif widget_type == "chart":
                chart = widget.get("chart") or {}
                chart["echartsOption"] = {}  # always rebuilt by code
            kept.append(widget)
        section["widgets"] = kept
    spec["sections"] = [s for s in spec.get("sections", []) if s.get("widgets")]
    if not spec["sections"]:
        raise SpecValidationError(["LLM spec has no valid sections after guarding"])
    return spec


def _acceptable_kpi_values(facts: list[dict]) -> set[str]:
    values: set[str] = set()
    for fact in facts:
        value = fact.get("value")
        if value is None:
            continue
        values.add(str(value))
        values.add(str(format_kpi_value(value, fact.get("unit"))))
        if isinstance(value, (int, float)):
            values.add(f"{value * 100:+.0f}%")
            values.add(f"{value * 100:.0f}%")
            values.add(f"{value:,.2f}")
            values.add(f"{value:,.0f}")
            values.add(compact_number(float(value)))
            values.add(f"${compact_number(float(value))}")
    return values


# --- chart execution --------------------------------------------------------


def execute_charts(spec: dict, frames: dict) -> None:
    """Run every chart's querySpec with code and attach echartsOption + a real
    sourceTrace. Widgets whose queries fail are dropped, not rendered wrong."""
    for section in spec.get("sections", []):
        kept = []
        for widget in section.get("widgets", []):
            if widget.get("type") != "chart":
                kept.append(widget)
                continue
            chart = widget.get("chart") or {}
            query_spec = chart.get("querySpec")
            df = frames.get((query_spec or {}).get("tableId"))
            if not query_spec or df is None:
                logger.warning("Dropping chart %r: no querySpec/table.", widget.get("id"))
                continue
            try:
                result = execute_query(df, query_spec)
                chart["echartsOption"] = build_echarts_option(
                    chart.get("chartType", "bar"), result, query_spec
                )
            except (QueryError, ChartBuildError) as error:
                logger.warning("Dropping chart %r: %s", widget.get("id"), error)
                continue
            chart["sourceTrace"] = _trace_for_query(query_spec, result.source_row_count)
            kept.append(widget)
        section["widgets"] = kept
    spec["sections"] = [s for s in spec.get("sections", []) if s.get("widgets")]


def _trace_for_query(query_spec: dict, row_count: int) -> dict:
    measures = ", ".join(
        f"{m['aggregation']}({m['column']})" for m in query_spec.get("measures", [])
    )
    group_bits = list(query_spec.get("dimensions") or [])
    if query_spec.get("dateColumn") and query_spec.get("dateGrain"):
        group_bits.insert(0, f"{query_spec['dateColumn']} by {query_spec['dateGrain']}")
    calculation = measures + (f" grouped by {', '.join(group_bits)}" if group_bits else "")
    columns = sorted(
        {m["column"] for m in query_spec.get("measures", [])}
        | set(query_spec.get("dimensions") or [])
        | ({query_spec["dateColumn"]} if query_spec.get("dateColumn") else set())
    )
    return {
        "tableId": query_spec.get("tableId", ""),
        "columns": columns,
        "filters": query_spec.get("filters", []),
        "calculation": calculation[:500],
        "rowCount": row_count,
        "generatedBy": "code",
    }


def _slug(name: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_") or "x"


PLANNER_PROMPT_VERSION = PROMPT_VERSION

"""Insight engine (SETUP.md §9.6): computed facts, computed by code, always traced.

Every fact and insight produced here carries a sourceTrace with
generatedBy="code". The LLM never touches these numbers — later milestones only
narrate them.
"""

from dataclasses import dataclass, field

import pandas as pd

from app.services.profiler import json_safe

MEASURE_PRIORITY = ["revenue", "cost", "money", "conversion", "engagement", "rating",
                    "quantity", "duration", "other"]
DIMENSION_PRIORITY = ["campaign", "channel", "stage", "status", "segment", "region", "owner",
                      "account", "customer", "other"]
# Measures whose sums are business-meaningful. Without one of these, analytics
# switch to record counts (e.g. tickets per month) — summing a duration, a
# rating, or an arbitrary numeric column produces impressive-looking nonsense.
STRONG_SEMANTICS = {"revenue", "cost", "money", "conversion", "engagement", "quantity"}
# Measures that are only meaningful as averages.
AVERAGE_SEMANTICS = {"duration", "rating"}
TOP_CONTRIBUTOR_THRESHOLD = 0.30
OUTLIER_ROBUST_Z = 3.5
MAX_DIMENSION_PAIRS = 3


@dataclass
class ColumnMeta:
    name: str
    detected_type: str
    semantic_type: str | None
    role_hint: str | None


@dataclass
class SourceTrace:
    table_id: str
    columns: list[str]
    calculation: str
    row_count: int
    filters: list[str] = field(default_factory=list)
    generated_by: str = "code"

    def to_dict(self) -> dict:
        return {
            "tableId": self.table_id,
            "columns": self.columns,
            "filters": self.filters,
            "calculation": self.calculation,
            "rowCount": self.row_count,
            "generatedBy": self.generated_by,
        }


@dataclass
class ComputedFact:
    id: str
    label: str
    value: object
    unit: str | None
    source_trace: SourceTrace

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "value": json_safe(self.value),
            "unit": self.unit,
            "sourceTrace": self.source_trace.to_dict(),
        }


@dataclass
class ComputedInsight:
    id: str
    headline: str
    detail: str
    insight_type: str
    severity: str  # positive | negative | neutral | warning | opportunity
    confidence: float
    facts: list[ComputedFact]
    source_trace: SourceTrace

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "headline": self.headline,
            "detail": self.detail,
            "insightType": self.insight_type,
            "severity": self.severity,
            "confidence": self.confidence,
            "facts": [fact.to_dict() for fact in self.facts],
            "sourceTrace": self.source_trace.to_dict(),
        }


@dataclass
class InsightResult:
    facts: list[ComputedFact] = field(default_factory=list)
    insights: list[ComputedInsight] = field(default_factory=list)


def compute_insights(df: pd.DataFrame, table_id: str, columns: list[ColumnMeta]) -> InsightResult:
    result = InsightResult()
    measures = _ordered(columns, "measure", MEASURE_PRIORITY)
    dimensions = _ordered(columns, "dimension", DIMENSION_PRIORITY)
    date_column = next((c for c in columns if c.role_hint == "date"), None)
    strong = [m for m in measures if m.semantic_type in STRONG_SEMANTICS]
    primary = strong[0] if strong else None  # None -> count-based analytics

    _overview_facts(df, table_id, measures, result)
    if date_column is not None:
        _trend(df, table_id, date_column, primary, result)
    for dimension in dimensions[:MAX_DIMENSION_PAIRS]:
        _top_contributor(df, table_id, dimension, primary, result)
    for measure in measures:
        _outliers(df, table_id, measure, result)
    stage_column = next(
        (c for c in columns if c.semantic_type in {"stage", "status"}), None
    )
    if stage_column is not None:
        _funnel(df, table_id, stage_column, measures[0] if measures else None, result)
    return result


def _ordered(columns: list[ColumnMeta], role: str, priority: list[str]) -> list[ColumnMeta]:
    matching = [c for c in columns if c.role_hint == role]

    def rank(column: ColumnMeta) -> int:
        semantic = column.semantic_type or "other"
        return priority.index(semantic) if semantic in priority else len(priority)

    return sorted(matching, key=rank)


def _unit_for(measure: ColumnMeta) -> str | None:
    if measure.detected_type == "currency":
        return "currency"
    if measure.detected_type == "percent":
        return "percent"
    return "number"


def _overview_facts(df, table_id, measures: list[ColumnMeta], result: InsightResult) -> None:
    result.facts.append(
        ComputedFact(
            id="fact_row_count",
            label="Rows analyzed",
            value=len(df),
            unit="number",
            source_trace=SourceTrace(
                table_id=table_id,
                columns=[c for c in df.columns],
                calculation="count(*) of normalized rows",
                row_count=len(df),
            ),
        )
    )
    for measure in measures:
        series = df[measure.name].dropna()
        if series.empty:
            continue
        if measure.semantic_type in STRONG_SEMANTICS:
            result.facts.append(
                ComputedFact(
                    id=f"fact_total_{_slug(measure.name)}",
                    label=f"Total {measure.name}",
                    value=round(float(series.sum()), 4),
                    unit=_unit_for(measure),
                    source_trace=SourceTrace(
                        table_id=table_id,
                        columns=[measure.name],
                        calculation=f"sum({measure.name}) across all rows",
                        row_count=int(series.count()),
                    ),
                )
            )
        elif measure.semantic_type in AVERAGE_SEMANTICS:
            # Averages are meaningful for durations and ratings; totals are not.
            result.facts.append(
                ComputedFact(
                    id=f"fact_avg_{_slug(measure.name)}",
                    label=f"Average {measure.name}",
                    value=round(float(series.mean()), 4),
                    unit=_unit_for(measure),
                    source_trace=SourceTrace(
                        table_id=table_id,
                        columns=[measure.name],
                        calculation=f"avg({measure.name}) across all rows",
                        row_count=int(series.count()),
                    ),
                )
            )


def _trend(df, table_id, date_column: ColumnMeta, measure: ColumnMeta | None,
           result: InsightResult) -> None:
    """Trend of the primary strong measure, or of record counts when no
    business measure exists (e.g. ticket volume per month)."""
    used_columns = [date_column.name] + ([measure.name] if measure else [])
    frame = df[used_columns].dropna(subset=[date_column.name])
    if measure is not None:
        frame = frame.dropna(subset=[measure.name])
    if len(frame) < 4 or not pd.api.types.is_datetime64_any_dtype(frame[date_column.name]):
        return
    span_days = (frame[date_column.name].max() - frame[date_column.name].min()).days
    if span_days >= 70:
        freq, grain_label, insight_suffix = "MS", "month", "MoM"
    else:
        freq, grain_label, insight_suffix = "W-MON", "week", "WoW"

    grouper = pd.Grouper(key=date_column.name, freq=freq)
    if measure is not None:
        grouped = frame.groupby(grouper)[measure.name].sum().dropna()
        metric_label = measure.name
        calculation = f"sum({measure.name}) grouped by {grain_label}"
    else:
        grouped = frame.groupby(grouper).size()
        # Interior gaps show up as zero-count bins; comparing against an empty
        # period is meaningless, so compare active periods only.
        grouped = grouped[grouped > 0]
        metric_label = "records"
        calculation = f"count(*) grouped by {grain_label}"
    # A partial current period (data ends mid-month/mid-week) would fake a
    # decline; compare the two most recent COMPLETE periods instead.
    partial_note = ""
    if len(grouped) >= 2:
        last_start = grouped.index[-1]
        period_days = 7 if freq.startswith("W") else int(last_start.days_in_month)
        coverage_days = (frame[date_column.name].max() - last_start).days + 1
        if coverage_days < 0.8 * period_days:
            grouped = grouped.iloc[:-1]
            partial_note = f"; partial current {grain_label} excluded"
    if len(grouped) < 2:
        return
    last, previous = float(grouped.iloc[-1]), float(grouped.iloc[-2])
    if previous == 0:
        return
    change = last / previous - 1

    trace = SourceTrace(
        table_id=table_id,
        columns=used_columns,
        calculation=(
            f"{calculation}; last {grain_label} / previous {grain_label} - 1{partial_note}"
        ),
        row_count=len(frame),
    )
    fact = ComputedFact(
        id=f"fact_trend_{_slug(metric_label)}_{insight_suffix.lower()}",
        label=f"{metric_label} {insight_suffix} change",
        value=round(change, 4),
        unit="percent",
        source_trace=trace,
    )
    result.facts.append(fact)

    direction = "up" if change > 0 else "down"
    if measure is None:
        severity = "neutral"  # more records is not inherently good or bad
    else:
        is_cost = measure.semantic_type == "cost"
        severity = "positive" if (change > 0) != is_cost else "negative"
    result.insights.append(
        ComputedInsight(
            id=f"insight_trend_{_slug(metric_label)}",
            headline=(
                f"{metric_label} {'are' if measure is None else 'is'} "
                f"{direction} {abs(change) * 100:.0f}% {insight_suffix}"
            ),
            detail=(
                f"Comparing the most recent {grain_label} to the one before, "
                f"{metric_label} moved from {previous:,.0f} to {last:,.0f}."
                if measure is None
                else f"Comparing the most recent {grain_label} to the one before, "
                f"{metric_label} moved from {previous:,.2f} to {last:,.2f}."
            ),
            insight_type="trend",
            severity=severity,
            confidence=0.9,
            facts=[fact],
            source_trace=trace,
        )
    )


def _top_contributor(df, table_id, dimension: ColumnMeta, measure: ColumnMeta | None,
                     result: InsightResult) -> None:
    metric_label = measure.name if measure else "records"
    used_columns = [dimension.name] + ([measure.name] if measure else [])
    frame = df[used_columns].dropna(subset=[dimension.name])
    if measure is not None:
        frame = frame.dropna(subset=[measure.name])
    if frame.empty:
        return
    if measure is not None:
        totals = frame.groupby(dimension.name)[measure.name].sum().sort_values(ascending=False)
        aggregation = f"sum({measure.name})"
    else:
        totals = frame.groupby(dimension.name).size().sort_values(ascending=False)
        aggregation = "count(*)"
    overall = float(totals.sum())
    if overall == 0 or len(totals) < 2:
        return
    top_name, top_value = str(totals.index[0]), float(totals.iloc[0])
    share = top_value / overall

    trace = SourceTrace(
        table_id=table_id,
        columns=used_columns,
        calculation=f"{aggregation} grouped by {dimension.name}; top share of total",
        row_count=len(frame),
    )
    fact = ComputedFact(
        id=f"fact_top_{_slug(dimension.name)}_{_slug(metric_label)}",
        label=f"Share of {metric_label} from top {dimension.name} ('{top_name}')",
        value=round(share, 4),
        unit="percent",
        source_trace=trace,
    )
    result.facts.append(fact)

    # Composition facts for the top segments.
    for name, value in totals.head(3).items():
        result.facts.append(
            ComputedFact(
                id=f"fact_comp_{_slug(dimension.name)}_{_slug(str(name))}_{_slug(metric_label)}",
                label=f"{metric_label} from {dimension.name} '{name}'",
                value=round(float(value), 4),
                unit=_unit_for(measure) if measure else "number",
                source_trace=SourceTrace(
                    table_id=table_id,
                    columns=used_columns,
                    calculation=f"{aggregation} where {dimension.name} = '{name}'",
                    row_count=int((frame[dimension.name] == name).sum()),
                    filters=[f"{dimension.name} = '{name}'"],
                ),
            )
        )

    if share >= TOP_CONTRIBUTOR_THRESHOLD:
        result.insights.append(
            ComputedInsight(
                id=f"insight_top_{_slug(dimension.name)}_{_slug(metric_label)}",
                headline=(
                    f"'{top_name}' accounts for {share * 100:.0f}% of {metric_label}"
                ),
                detail=(
                    f"Across {len(totals)} {dimension.name} values, '{top_name}' contributes "
                    f"{top_value:,.0f} of {overall:,.0f} total {metric_label}."
                ),
                insight_type="top_contributor",
                severity="neutral",
                confidence=0.9,
                facts=[fact],
                source_trace=trace,
            )
        )


def _outliers(df, table_id, measure: ColumnMeta, result: InsightResult) -> None:
    series = df[measure.name].dropna().astype(float)
    if len(series) < 8:
        return
    median = float(series.median())
    mad = float((series - median).abs().median())
    if mad == 0:
        return
    robust_z = 0.6745 * (series - median) / mad
    outliers = series[robust_z.abs() > OUTLIER_ROBUST_Z]
    if outliers.empty:
        return
    if len(outliers) / len(series) > 0.10:
        # A third of the data being "outliers" means a skewed distribution,
        # not anomalies — reporting it as outliers would be misleading.
        return

    trace = SourceTrace(
        table_id=table_id,
        columns=[measure.name],
        calculation=(
            f"median absolute deviation outlier test on {measure.name} "
            f"(robust z > {OUTLIER_ROBUST_Z})"
        ),
        row_count=len(series),
    )
    fact = ComputedFact(
        id=f"fact_outliers_{_slug(measure.name)}",
        label=f"Outlier values in {measure.name}",
        value=int(len(outliers)),
        unit="number",
        source_trace=trace,
    )
    result.facts.append(fact)
    example = float(outliers.iloc[0])
    result.insights.append(
        ComputedInsight(
            id=f"insight_outliers_{_slug(measure.name)}",
            headline=f"{len(outliers)} unusual value(s) in {measure.name}",
            detail=(
                f"{len(outliers)} of {len(series)} values deviate strongly from the median "
                f"of {median:,.2f} (example: {example:,.2f}). Worth verifying before sharing."
            ),
            insight_type="outlier",
            severity="warning",
            confidence=0.8,
            facts=[fact],
            source_trace=trace,
        )
    )


WON_VALUES = {"won", "win", "closed won", "closed_won", "success"}
LOST_VALUES = {"lost", "lose", "closed lost", "closed_lost", "churned"}


def _funnel(df, table_id, stage_column: ColumnMeta, measure: ColumnMeta | None,
            result: InsightResult) -> None:
    series = df[stage_column.name].dropna().astype(str)
    if series.empty:
        return
    counts = series.value_counts()

    trace = SourceTrace(
        table_id=table_id,
        columns=[stage_column.name],
        calculation=f"count(*) grouped by {stage_column.name}",
        row_count=len(series),
    )
    for name, count in counts.head(8).items():
        result.facts.append(
            ComputedFact(
                id=f"fact_stage_{_slug(str(name))}",
                label=f"Rows in {stage_column.name} '{name}'",
                value=int(count),
                unit="number",
                source_trace=SourceTrace(
                    table_id=table_id,
                    columns=[stage_column.name],
                    calculation=f"count(*) where {stage_column.name} = '{name}'",
                    row_count=int(count),
                    filters=[f"{stage_column.name} = '{name}'"],
                ),
            )
        )

    lowered = series.str.lower()
    won = int(lowered.isin(WON_VALUES).sum())
    lost = int(lowered.isin(LOST_VALUES).sum())
    if won + lost >= 5:
        win_rate = won / (won + lost)
        fact = ComputedFact(
            id="fact_win_rate",
            label="Win rate",
            value=round(win_rate, 4),
            unit="percent",
            source_trace=SourceTrace(
                table_id=table_id,
                columns=[stage_column.name],
                calculation=f"count won / (count won + count lost) from {stage_column.name}",
                row_count=won + lost,
                filters=[f"{stage_column.name} in won/lost values"],
            ),
        )
        result.facts.append(fact)
        result.insights.append(
            ComputedInsight(
                id="insight_win_rate",
                headline=f"Win rate is {win_rate * 100:.0f}%",
                detail=f"Of {won + lost} closed records, {won} were won and {lost} were lost.",
                insight_type="funnel",
                severity="positive" if win_rate >= 0.5 else "neutral",
                confidence=0.9,
                facts=[fact],
                source_trace=fact.source_trace,
            )
        )


def quality_insights(findings, table_id: str) -> list[ComputedInsight]:
    """Promote warning/critical data-quality findings into insights."""
    insights: list[ComputedInsight] = []
    for finding in findings:
        if finding.severity == "info":
            continue
        trace = SourceTrace(
            table_id=table_id,
            columns=[finding.meta.get("column")] if finding.meta.get("column") else ["*"],
            calculation=f"data quality check: {finding.finding_type}",
            row_count=int(finding.meta.get("count", 0) or 0),
        )
        insights.append(
            ComputedInsight(
                id=f"insight_quality_{finding.finding_type}_{str(finding.id)[:8]}",
                headline=finding.message,
                detail="Surfaced from data profiling. Review before sharing externally.",
                insight_type="data_quality",
                severity="warning" if finding.severity == "warning" else "negative",
                confidence=1.0,
                facts=[],
                source_trace=trace,
            )
        )
    return insights


def _slug(name: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_") or "x"

import pandas as pd
import pytest

from app.services.insight_engine import ColumnMeta, compute_insights
from app.services.text_insights import compute_text_themes


def meta(name, detected="float", semantic=None, role="measure"):
    return ColumnMeta(name=name, detected_type=detected, semantic_type=semantic, role_hint=role)


def marketing_frame():
    # Spans > 70 days (monthly grain); June runs to the 25th so it counts as
    # a complete month for the trend comparison.
    dates = pd.to_datetime(
        ["2026-03-02", "2026-03-09", "2026-05-04", "2026-05-11", "2026-06-01", "2026-06-25"]
    )
    return pd.DataFrame(
        {
            "date": dates,
            "campaign": ["A", "B", "A", "B", "A", "A"],
            "spend": [100.0, 100.0, 150.0, 50.0, 300.0, 100.0],
        }
    )


MARKETING_META = [
    meta("date", detected="date", semantic="date", role="date"),
    meta("campaign", detected="category", semantic="campaign", role="dimension"),
    meta("spend", detected="float", semantic="cost", role="measure"),
]


def test_trend_mom_change_is_computed_correctly():
    result = compute_insights(marketing_frame(), "tbl_1", MARKETING_META)
    trend_facts = [f for f in result.facts if f.id.startswith("fact_trend_spend")]
    assert len(trend_facts) == 1
    # May: 150+50=200 -> June: 300+100=400 -> +100% MoM
    assert trend_facts[0].value == pytest.approx(1.0)
    trend_insights = [i for i in result.insights if i.insight_type == "trend"]
    assert len(trend_insights) == 1
    # Spend is a cost: going up reads as negative.
    assert trend_insights[0].severity == "negative"


def test_top_contributor_share():
    result = compute_insights(marketing_frame(), "tbl_1", MARKETING_META)
    top_facts = [f for f in result.facts if f.id == "fact_top_campaign_spend"]
    assert len(top_facts) == 1
    # A: 650 of 800 total -> 81.25%
    assert top_facts[0].value == pytest.approx(0.8125)
    assert any(i.insight_type == "top_contributor" for i in result.insights)


def test_outlier_detection_with_mad():
    # One outlier among 16 values (6%) — under the 10% skew cap, so it reports.
    frame = pd.DataFrame(
        {"amount": [10.0, 11.0, 9.0, 10.5, 9.5, 10.2, 9.8, 10.1, 10.3, 9.7,
                    10.4, 9.9, 10.6, 9.6, 10.05, 500.0]}
    )
    result = compute_insights(frame, "tbl_1", [meta("amount", semantic="revenue")])
    outlier_insights = [i for i in result.insights if i.insight_type == "outlier"]
    assert len(outlier_insights) == 1
    assert outlier_insights[0].facts[0].value == 1


def test_no_outlier_insight_for_clean_data():
    frame = pd.DataFrame({"amount": [10.0, 11.0, 9.0, 10.5, 9.5, 10.2, 9.8, 10.1]})
    result = compute_insights(frame, "tbl_1", [meta("amount", semantic="revenue")])
    assert not any(i.insight_type == "outlier" for i in result.insights)


def test_funnel_win_rate():
    frame = pd.DataFrame(
        {
            "stage": ["Won", "Won", "Lost", "Won", "Lost", "Negotiation", "Discovery"],
            "amount": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
        }
    )
    columns = [
        meta("stage", detected="category", semantic="stage", role="dimension"),
        meta("amount", detected="currency", semantic="revenue"),
    ]
    result = compute_insights(frame, "tbl_1", columns)
    win_facts = [f for f in result.facts if f.id == "fact_win_rate"]
    assert len(win_facts) == 1
    assert win_facts[0].value == pytest.approx(0.6)  # 3 won / 5 closed
    assert any(i.id == "insight_win_rate" for i in result.insights)


def test_every_fact_and_insight_has_a_complete_source_trace():
    result = compute_insights(marketing_frame(), "tbl_1", MARKETING_META)
    assert result.facts and result.insights
    for fact in result.facts:
        trace = fact.to_dict()["sourceTrace"]
        assert trace["tableId"] == "tbl_1"
        assert trace["columns"]
        assert trace["calculation"]
        assert trace["generatedBy"] == "code"
    for insight in result.insights:
        payload = insight.to_dict()
        assert payload["sourceTrace"]["generatedBy"] == "code"
        for fact in payload["facts"]:
            assert fact["sourceTrace"]["calculation"]


COMMENTS = pd.DataFrame(
    {
        "comment": [
            "Export to PDF cut off my chart.",
            "Love the share page!",
            "PDF export is broken on wide tables.",
            "Sharing with my client was seamless.",
            "The export margins are wrong.",
        ]
    }
)


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload

    def complete_json(self, system, user, schema, schema_name):
        return self.payload


def test_text_themes_counts_come_from_code_not_model():
    payload = {
        "themes": [
            {
                "label": "Export/PDF issues",
                "sentiment": "negative",
                "commentIndexes": [0, 2, 4, 4, 99],  # duplicate + out-of-range
                "summary": "Users report broken PDF exports.",
            }
        ]
    }
    insights = compute_text_themes(COMMENTS, "tbl_1", "comment", llm=FakeLLM(payload))
    assert len(insights) == 1
    # 99 dropped, duplicate 4 deduped -> count is 3, derived by code.
    assert insights[0].facts[0].value == 3
    assert insights[0].source_trace.generated_by == "model_supported_by_code"
    assert "Export to PDF cut off my chart." in insights[0].detail


def test_text_themes_skip_without_llm():
    assert compute_text_themes(COMMENTS, "tbl_1", "comment", llm=None) == []


def test_text_theme_with_only_invalid_indexes_is_dropped():
    payload = {
        "themes": [
            {
                "label": "Ghost theme",
                "sentiment": "neutral",
                "commentIndexes": [50, 60],
                "summary": "Points at comments that do not exist.",
            }
        ]
    }
    assert compute_text_themes(COMMENTS, "tbl_1", "comment", llm=FakeLLM(payload)) == []

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "packages" / "schemas" / "dashboard_spec.schema.json"
)


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def source_trace() -> dict:
    return {
        "tableId": "tbl_campaigns",
        "columns": ["date", "spend"],
        "filters": [],
        "calculation": "sum(spend) grouped by week",
        "rowCount": 120,
        "generatedBy": "code",
    }


def minimal_valid_spec() -> dict:
    return {
        "version": "0.1.0",
        "dashboard": {
            "title": "June Paid Media Report",
            "subtitle": "Campaign performance for June",
            "useCase": "marketing",
            "audience": "client",
            "theme": {"name": "picxify-default", "tone": "polished"},
            "generatedAt": "2026-07-01T12:00:00Z",
        },
        "dataSources": [
            {
                "datasetId": "ds_1",
                "tableId": "tbl_campaigns",
                "displayName": "campaigns.csv",
                "rowCount": 120,
                "columnCount": 6,
            }
        ],
        "assumptions": [
            {
                "id": "asm_1",
                "label": "Assumed 'conversions' represents successful campaign outcomes.",
                "status": "needs_review",
                "confidence": 0.89,
                "editable": True,
                "source": "semantic_mapper",
            }
        ],
        "sections": [
            {
                "id": "sec_hero",
                "title": "Executive summary",
                "layout": "hero",
                "widgets": [
                    {
                        "id": "w_kpi_spend",
                        "type": "kpi",
                        "title": "Total spend",
                        "kpi": {
                            "value": 48200,
                            "label": "Total spend",
                            "sourceTrace": source_trace(),
                        },
                    },
                    {
                        "id": "w_chart_trend",
                        "type": "chart",
                        "title": "Spend over time",
                        "chart": {
                            "chartType": "line",
                            "querySpec": {
                                "tableId": "tbl_campaigns",
                                "measures": [{"column": "spend", "aggregation": "sum"}],
                                "dimensions": ["date"],
                                "dateColumn": "date",
                                "dateGrain": "week",
                                "filters": [],
                            },
                            "sourceTrace": source_trace(),
                        },
                    },
                ],
            }
        ],
        "insights": [
            {
                "id": "ins_1",
                "headline": "Spend concentrated in two campaigns",
                "detail": "Two campaigns account for most of total spend.",
                "severity": "neutral",
                "confidence": 0.9,
                "facts": [
                    {
                        "label": "Share of spend from top 2 campaigns",
                        "value": 0.63,
                        "unit": "percent",
                        "sourceTrace": source_trace(),
                    }
                ],
                "sourceTrace": source_trace(),
            }
        ],
        "actions": [
            {
                "label": "Review budget allocation for low-performing campaigns",
                "priority": "medium",
                "rationale": "Spend is concentrated; verify it matches strategy.",
            }
        ],
    }


def test_schema_is_valid_draft_2020_12(validator):
    # check_schema in the fixture already raised if the schema itself were malformed.
    assert validator is not None


def test_minimal_spec_validates(validator):
    validator.validate(minimal_valid_spec())


def test_unknown_widget_type_is_rejected(validator):
    spec = minimal_valid_spec()
    spec["sections"][0]["widgets"][0]["type"] = "hologram"
    with pytest.raises(ValidationError):
        validator.validate(spec)


def test_insight_without_source_trace_is_rejected(validator):
    spec = minimal_valid_spec()
    del spec["insights"][0]["sourceTrace"]
    with pytest.raises(ValidationError):
        validator.validate(spec)


def test_source_trace_generated_by_is_constrained(validator):
    spec = minimal_valid_spec()
    spec["insights"][0]["sourceTrace"]["generatedBy"] = "model"
    with pytest.raises(ValidationError):
        validator.validate(spec)


def test_wrong_spec_version_is_rejected(validator):
    spec = minimal_valid_spec()
    spec["version"] = "9.9.9"
    with pytest.raises(ValidationError):
        validator.validate(spec)


def test_query_spec_requires_filters_key(validator):
    spec = minimal_valid_spec()
    del spec["sections"][0]["widgets"][1]["chart"]["querySpec"]["filters"]
    with pytest.raises(ValidationError):
        validator.validate(spec)


def test_unexpected_top_level_key_is_rejected(validator):
    spec = minimal_valid_spec()
    spec["freeformHtml"] = "<script>alert(1)</script>"
    with pytest.raises(ValidationError):
        validator.validate(spec)

from app.services.semantic_mapper import (
    ColumnInput,
    TableInput,
    map_dataset,
)


def make_column(name, detected_type, unique_ratio=0.5, examples=None):
    return ColumnInput(
        name=name,
        normalized_name=name.lower().replace(" ", "_"),
        detected_type=detected_type,
        role_hint=None,
        unique_ratio=unique_ratio,
        examples=examples or [],
    )


def marketing_table():
    return TableInput(
        name="campaigns",
        columns=[
            make_column("date", "date"),
            make_column("campaign", "category"),
            make_column("channel", "category"),
            make_column("spend", "float"),
            make_column("conversions", "integer"),
            make_column("revenue", "float"),
        ],
    )


def test_marketing_dataset_detected():
    mapping = map_dataset([marketing_table()], filename="campaigns.csv")
    assert mapping.use_case_candidates[0]["useCase"] == "marketing"
    assert mapping.column_mappings["spend"].semantic_type == "cost"
    assert mapping.column_mappings["campaign"].semantic_type == "campaign"
    assert mapping.column_mappings["conversions"].semantic_type == "conversion"
    assert mapping.column_mappings["date"].role == "date"
    assert mapping.used_llm is False


def test_sales_dataset_detected():
    table = TableInput(
        name="pipeline",
        columns=[
            make_column("deal_id", "id", unique_ratio=1.0),
            make_column("account", "category"),
            make_column("stage", "category"),
            make_column("amount", "currency"),
            make_column("close_date", "date"),
        ],
    )
    mapping = map_dataset([table], filename="sales_pipeline.csv")
    assert mapping.use_case_candidates[0]["useCase"] == "sales"
    assert mapping.column_mappings["amount"].semantic_type == "revenue"
    assert mapping.column_mappings["stage"].semantic_type == "stage"


def test_survey_dataset_detected():
    table = TableInput(
        name="responses",
        columns=[
            make_column("respondent_id", "id", unique_ratio=1.0),
            make_column("nps_score", "integer"),
            make_column("ease_of_use", "integer"),
            make_column("comment", "text"),
        ],
    )
    # Rating detection: nps_score and ease_of_use only match "rating" via
    # nps/score patterns, so name the file neutrally to test signal-based detection.
    mapping = map_dataset([table], filename="responses.csv")
    assert mapping.use_case_candidates[0]["useCase"] == "survey"


def test_generic_fallback_and_use_case_assumption():
    table = TableInput(
        name="stuff",
        columns=[make_column("alpha", "float"), make_column("beta", "category")],
    )
    mapping = map_dataset([table], filename="stuff.csv")
    assert mapping.use_case_candidates[0]["useCase"] == "generic"
    assert any("generic" in a["label"] for a in mapping.assumptions)


def test_prepayments_column_is_not_misread_as_owner():
    # 'prepayments' contains the substring 'rep' ('p-REP-ayments'); the owner
    # rule must not fire on that, or a currency measure gets relabeled as a
    # group-by dimension (regression: produced a nonsense "Credits by
    # Prepayments" breakdown chart on a real AR-aging report).
    table = TableInput(
        name="ar_aging",
        columns=[
            make_column("prepayments", "float"),
            make_column("credits", "float"),
            make_column("sales_rep", "category"),
        ],
    )
    mapping = map_dataset([table], filename="ar_aging.xlsx")
    assert mapping.column_mappings["prepayments"].role == "measure"
    assert mapping.column_mappings["prepayments"].semantic_type != "owner"
    # The real 'rep' column (underscore-delimited token) should still match.
    assert mapping.column_mappings["sales_rep"].semantic_type == "owner"


def test_multiple_date_columns_produce_assumption():
    table = TableInput(
        name="deals",
        columns=[
            make_column("created_date", "date"),
            make_column("close_date", "date"),
            make_column("amount", "currency"),
        ],
    )
    mapping = map_dataset([table], filename="deals.csv")
    assert any("primary timeline" in a["label"] for a in mapping.assumptions)


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload

    def complete_json(self, system, user, schema, schema_name):
        return self.payload


def test_llm_output_is_merged_when_valid():
    payload = {
        "useCaseCandidates": [{"useCase": "client_report", "confidence": 0.9}],
        "columnMappings": [
            {"column": "spend", "semanticType": "cost", "role": "measure", "confidence": 0.99}
        ],
        "assumptions": [
            {"label": "Assumed spend is media cost.", "confidence": 0.9, "editable": True}
        ],
    }
    mapping = map_dataset([marketing_table()], filename="campaigns.csv", llm=FakeLLM(payload))
    assert mapping.used_llm is True
    assert mapping.use_case_candidates[0]["useCase"] == "client_report"
    assert mapping.column_mappings["spend"].confidence == 0.99


def test_llm_hallucinated_column_is_dropped():
    payload = {
        "useCaseCandidates": [{"useCase": "marketing", "confidence": 0.9}],
        "columnMappings": [
            {
                "column": "profit_margin",  # does not exist
                "semanticType": "revenue",
                "role": "measure",
                "confidence": 0.99,
            }
        ],
        "assumptions": [],
    }
    mapping = map_dataset([marketing_table()], filename="campaigns.csv", llm=FakeLLM(payload))
    assert "profit_margin" not in mapping.column_mappings
    # Heuristic mappings survive.
    assert mapping.column_mappings["spend"].semantic_type == "cost"


def test_invalid_llm_output_falls_back_to_heuristics():
    class BrokenLLM:
        def complete_json(self, system, user, schema, schema_name):
            return {"nonsense": True}

    mapping = map_dataset([marketing_table()], filename="campaigns.csv", llm=BrokenLLM())
    assert mapping.used_llm is False
    assert mapping.use_case_candidates[0]["useCase"] == "marketing"

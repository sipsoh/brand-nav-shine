"""The coverage contract (docs/engineering/coverage-contract.md): every
column represented or excluded with a computed reason — no third state."""

import pandas as pd

from app.services.coverage import audit_and_backstop


def _spec_with_one_chart() -> dict:
    return {
        "sections": [
            {
                "id": "s1",
                "title": "Breakdowns",
                "layout": "grid",
                "widgets": [
                    {
                        "id": "w1",
                        "type": "chart",
                        "title": "Amount by Region",
                        "chart": {
                            "chartType": "horizontal_bar",
                            "querySpec": {
                                "tableId": "t1",
                                "measures": [{"column": "Amount", "aggregation": "sum"}],
                                "dimensions": ["Region"],
                                "filters": [],
                            },
                            "echartsOption": {"series": [{}]},
                            "sourceTrace": {},
                        },
                    }
                ],
            },
            {"id": "sec_appendix", "title": "Sources", "layout": "appendix", "widgets": []},
        ]
    }


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Region": ["W", "E", "W", "S"],
            "Amount": [10.0, 20.0, 30.0, 40.0],
            "Notes": ["a", "b", "c", "d"],  # unrepresented -> self-heals
            "Blank": [None, None, None, None],  # all null -> excluded
            "Scope": ["FY26", "FY26", "FY26", "FY26"],  # constant -> excluded
        }
    )


def test_unaccounted_columns_self_heal_into_backstop_table():
    spec = _spec_with_one_chart()
    audit_and_backstop(spec, _frame(), table_id="t1")
    tables = [
        w for s in spec["sections"] for w in s["widgets"] if w["type"] == "data_table"
    ]
    assert len(tables) == 1
    assert "Notes" in tables[0]["table"]["columns"]
    assert tables[0]["table"]["sourceTrace"]["generatedBy"] == "code"
    # Inserted before the appendix, not after it.
    layouts = [s["layout"] for s in spec["sections"]]
    assert layouts.index("full_width") < layouts.index("appendix")


def test_ledger_accounts_for_every_column_with_reasons():
    spec = _spec_with_one_chart()
    audit_and_backstop(spec, _frame(), table_id="t1")
    ledger = {c["name"]: c for c in spec["coverage"]["columns"]}
    assert ledger["Region"]["status"] == "chart"
    assert ledger["Amount"]["status"] == "chart"
    assert ledger["Notes"]["status"] == "table"
    assert ledger["Blank"]["status"] == "excluded"
    assert ledger["Blank"]["reason"] == "all null"
    assert ledger["Scope"]["status"] == "excluded"
    assert "constant" in ledger["Scope"]["reason"]
    assert spec["coverage"]["columnsTotal"] == 5
    assert spec["coverage"]["columnsRepresented"] == 3


def test_fully_covered_spec_gets_no_backstop_table():
    spec = _spec_with_one_chart()
    df = _frame()[["Region", "Amount"]]
    audit_and_backstop(spec, df, table_id="t1")
    assert not any(
        w["type"] == "data_table" for s in spec["sections"] for w in s["widgets"]
    )
    assert spec["coverage"]["columnsRepresented"] == 2


def test_whole_table_kpi_trace_does_not_count_as_representation():
    spec = _spec_with_one_chart()
    spec["sections"][0]["widgets"].append(
        {
            "id": "w_rows",
            "type": "kpi",
            "title": "Rows analyzed",
            "kpi": {
                "value": 4,
                "label": "Rows analyzed",
                "sourceTrace": {
                    # Cites every column — an aggregate over the table, not a
                    # representation of 'Notes' specifically.
                    "columns": ["Region", "Amount", "Notes", "Blank", "Scope"],
                },
            },
        }
    )
    audit_and_backstop(spec, _frame(), table_id="t1")
    ledger = {c["name"]: c for c in spec["coverage"]["columns"]}
    assert ledger["Notes"]["status"] == "table"


def test_backstop_rows_sorted_by_largest_numeric_leftover():
    spec = _spec_with_one_chart()
    df = _frame().assign(Fees=[5.0, 300.0, 20.0, 1.0])
    audit_and_backstop(spec, df, table_id="t1")
    table = next(
        w["table"] for s in spec["sections"] for w in s["widgets"] if w["type"] == "data_table"
    )
    fees_index = table["columns"].index("Fees")
    assert table["rows"][0][fees_index] == 300.0
    assert "Fees" in table["note"]

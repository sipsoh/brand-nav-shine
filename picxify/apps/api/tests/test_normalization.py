import pandas as pd

from app.services.normalization import normalize_table, snake_case


def note_types(result):
    return {note.finding_type for note in result.notes}


def test_snake_case():
    assert snake_case("Deal Amount") == "deal_amount"
    assert snake_case("  Close-Date (UTC) ") == "close_date_utc"
    assert snake_case("???") == "column"


def test_blank_rows_and_columns_removed():
    df = pd.DataFrame(
        {
            "a": [1, None, 3],
            "b": ["x", None, "z"],
            "empty": [None, None, None],
        }
    )
    result = normalize_table(df)
    assert result.dataframe.shape == (2, 2)
    assert {"blank_rows_removed", "blank_columns_removed"} <= note_types(result)


def test_duplicate_columns_renamed():
    df = pd.DataFrame([[1, 2, 3]], columns=["spend", "spend", "clicks"])
    result = normalize_table(df)
    assert list(result.dataframe.columns) == ["spend", "spend_2", "clicks"]
    assert "duplicate_columns_renamed" in note_types(result)


def test_footer_total_rows_removed():
    df = pd.DataFrame(
        {
            "campaign": ["Spring", "Summer", "Grand Total"],
            "spend": [100.0, 200.0, 300.0],
        }
    )
    result = normalize_table(df)
    assert len(result.dataframe) == 2
    assert "footer_rows_removed" in note_types(result)


def test_currency_strings_converted():
    df = pd.DataFrame({"spend": ["$1,250.00", "$980.50", "$640.00"]})
    result = normalize_table(df)
    assert result.dataframe["spend"].tolist() == [1250.0, 980.5, 640.0]
    assert result.type_hints["spend"] == "currency"


def test_percent_strings_converted():
    df = pd.DataFrame({"ctr": ["2.5%", "3.1%", "1.9%"]})
    result = normalize_table(df)
    assert result.dataframe["ctr"].tolist() == [2.5, 3.1, 1.9]
    assert result.type_hints["ctr"] == "percent"


def test_dates_parsed_across_formats():
    df = pd.DataFrame({"close_date": ["2026-05-04", "2026-05-11", "2026-06-01"]})
    result = normalize_table(df)
    assert str(result.dataframe["close_date"].dtype).startswith("datetime64")


def test_mixed_content_column_left_alone():
    df = pd.DataFrame({"notes": ["call back", "$100", "next week"]})
    result = normalize_table(df)
    assert result.dataframe["notes"].tolist() == ["call back", "$100", "next week"]

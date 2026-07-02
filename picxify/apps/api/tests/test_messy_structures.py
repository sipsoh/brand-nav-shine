"""Messy real-world structures: banner rows, headers not on row 1, scattered
blocks, merged two-row headers, crosstab (wide-period) layouts, European
numbers, and encoding fallbacks."""

from io import BytesIO

import pandas as pd
import pytest

from app.services.normalization import normalize_table
from app.services.parser import parse_csv, parse_excel


def excel_bytes(grid: list[list], sheet: str = "Sheet1", extra: dict | None = None) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(grid).to_excel(writer, sheet_name=sheet, index=False, header=False)
        for name, other in (extra or {}).items():
            pd.DataFrame(other).to_excel(writer, sheet_name=name, index=False, header=False)
    return buffer.getvalue()


# --- Excel structure detection ----------------------------------------------


def test_banner_rows_skipped_and_header_detected():
    grid = [
        ["ACME CORP — Q2 EXPORT", None, None],
        [None, None, None],
        ["Region", "Orders", "Revenue"],
        ["West", 10, 1200.5],
        ["East", 7, 950.0],
        ["South", 12, 1800.0],
    ]
    tables = parse_excel("report.xlsx", excel_bytes(grid))
    assert len(tables) == 1
    df = tables[0].dataframe
    assert list(df.columns) == ["Region", "Orders", "Revenue"]
    assert len(df) == 3
    assert pd.api.types.is_numeric_dtype(df["Revenue"])  # not left as objects
    kinds = {n.finding_type for n in tables[0].notes}
    assert "banner_rows_skipped" in kinds


def test_two_row_merged_header_flattened():
    grid = [
        ["Region", "Q1", None, "Q2", None],
        [None, "Revenue", "Orders", "Revenue", "Orders"],
        ["West", 100.0, 5, 130.0, 6],
        ["East", 90.0, 4, 120.0, 7],
    ]
    tables = parse_excel("report.xlsx", excel_bytes(grid))
    df = tables[0].dataframe
    assert list(df.columns) == [
        "Region", "Q1 Revenue", "Q1 Orders", "Q2 Revenue", "Q2 Orders",
    ]
    kinds = {n.finding_type for n in tables[0].notes}
    assert "merged_header_flattened" in kinds


def test_vertical_blocks_split_into_separate_tables():
    grid = [
        ["Metric", "Value"],
        ["Report Year", 2026],
        ["Prepared By", "Ops"],
        [None, None],
        [None, None],
        ["Date", "Amount"],
        ["2026-01-05", 100.0],
        ["2026-01-12", 140.0],
        ["2026-01-19", 90.0],
    ]
    tables = parse_excel("report.xlsx", excel_bytes(grid, sheet="Data"))
    names = [t.name for t in tables]
    assert names == ["Data (block 1)", "Data (block 2)"]
    assert list(tables[1].dataframe.columns) == ["Date", "Amount"]
    assert len(tables[1].dataframe) == 3
    kinds = {n.finding_type for t in tables for n in t.notes}
    assert "sheet_split_into_blocks" in kinds


def test_side_by_side_tables_split():
    grid = [
        ["Team", "Wins", None, "Month", "Sessions"],
        ["North", 5, None, "Jan 2026", 900],
        ["South", 8, None, "Feb 2026", 1100],
        ["East", 3, None, "Mar 2026", 1250],
    ]
    tables = parse_excel("report.xlsx", excel_bytes(grid, sheet="Pair"))
    assert [t.name for t in tables] == ["Pair (block 1)", "Pair (block 2)"]
    assert list(tables[0].dataframe.columns) == ["Team", "Wins"]
    assert list(tables[1].dataframe.columns) == ["Month", "Sessions"]


def test_blank_and_duplicate_headers_get_names():
    grid = [
        ["Order", "Cost", None, "Cost"],
        ["A-1", 10.0, "Yes", 10.0],
        ["A-2", 12.0, None, 12.0],
    ]
    tables = parse_excel("report.xlsx", excel_bytes(grid))
    df = tables[0].dataframe
    assert list(df.columns) == ["Order", "Cost", "column_3", "Cost"]
    normalized = normalize_table(df)
    # Duplicate 'Cost' resolved downstream.
    assert list(normalized.dataframe.columns) == ["Order", "Cost", "column_3", "Cost_2"]


def test_single_blank_header_cell_never_merges_with_stringy_data_row():
    # One blank header cell is not a merged span. The first data row here is
    # almost all strings (ids, currency, dates, statuses) and must never be
    # consumed as header labels ("Cost $1,195.93").
    grid = [
        ["Work Order", "Site", "Cost", "Opened", "Status", None],
        ["WO-1", "Northgate", "$1,195.93", "1/5/2026", "Closed", "Yes"],
        ["WO-2", "Riverside", "$840.00", "1/9/2026", "Open", None],
        ["WO-3", "Summit", "$212.50", "2/1/2026", "Closed", "Yes"],
    ]
    tables = parse_excel("ops.xlsx", excel_bytes(grid))
    df = tables[0].dataframe
    assert list(df.columns) == ["Work Order", "Site", "Cost", "Opened", "Status", "column_6"]
    assert len(df) == 3  # no data row eaten
    assert df["Work Order"].tolist() == ["WO-1", "WO-2", "WO-3"]


def test_headerless_numeric_block_gets_auto_columns():
    grid = [
        ["West", 10, 1200.5],
        ["East", 7, 950.0],
        ["South", 12, 1800.0],
    ]
    tables = parse_excel("report.xlsx", excel_bytes(grid))
    df = tables[0].dataframe
    assert list(df.columns) == ["column_1", "column_2", "column_3"]
    assert len(df) == 3  # no data row was eaten as a header
    kinds = {n.finding_type for n in tables[0].notes}
    assert "no_header_detected" in kinds


def test_crosstab_year_headers_recognized():
    grid = [
        ["Region", 2024, 2025, 2026],
        ["West", 100.0, 110.0, 125.0],
        ["East", 90.0, 95.0, 105.0],
        ["South", 70.0, 80.0, 85.0],
    ]
    tables = parse_excel("report.xlsx", excel_bytes(grid))
    df = tables[0].dataframe
    assert list(df.columns) == ["Region", "2024", "2025", "2026"]
    assert len(df) == 3


def test_clean_sheet_unchanged():
    grid = [
        ["Date", "Channel", "Spend"],
        ["2026-05-04", "Google", 100.0],
        ["2026-05-11", "Meta", 50.0],
    ]
    tables = parse_excel("clean.xlsx", excel_bytes(grid))
    assert [t.name for t in tables] == ["Sheet1"]
    assert list(tables[0].dataframe.columns) == ["Date", "Channel", "Spend"]
    assert tables[0].notes == []


# --- CSV robustness ----------------------------------------------------------


def test_csv_latin1_encoding_fallback():
    text = "Kunde,Región,Betrag\nMüller,Süd,100\nBäcker,Nord,200\n"
    table = parse_csv("latin.csv", text.encode("latin-1"))
    assert len(table.dataframe) == 2
    assert any(n.finding_type == "encoding_detected" for n in table.notes)


def test_csv_semicolon_euro_numbers_and_dayfirst_dates():
    text = (
        "Datum;Kunde;Umsatz\n"
        "13.02.2026;Müller GmbH;€ 1.234,56\n"
        "27.02.2026;Weber KG;€ 2.500,00\n"
        "05.03.2026;Fischer AG;€ 980,25\n"
    )
    table = parse_csv("euro.csv", text.encode("utf-8"))
    normalized = normalize_table(table.dataframe)
    df = normalized.dataframe
    assert df["Umsatz"].tolist() == pytest.approx([1234.56, 2500.0, 980.25])
    assert normalized.type_hints.get("Umsatz") == "currency"
    assert pd.api.types.is_datetime64_any_dtype(df["Datum"])
    assert df["Datum"].iloc[0].month == 2 and df["Datum"].iloc[0].day == 13


# --- wide-period unpivot ------------------------------------------------------


def test_wide_period_columns_unpivot_to_long():
    df = pd.DataFrame(
        {
            "Region": ["West", "East"],
            "Jan 2026": [100.0, 90.0],
            "Feb 2026": [110.0, 95.0],
            "Mar 2026": [120.0, 99.0],
        }
    )
    normalized = normalize_table(df, table_name="Revenue by Region")
    out = normalized.dataframe
    assert set(out.columns) == {"Region", "Period", "Revenue"}
    assert len(out) == 6
    assert pd.api.types.is_datetime64_any_dtype(out["Period"])
    assert sorted(out["Period"].dt.month.unique().tolist()) == [1, 2, 3]
    kinds = {n.finding_type for n in normalized.notes}
    assert "wide_periods_unpivoted" in kinds


def test_unpivot_requires_three_periods_and_numeric_bodies():
    two_periods = pd.DataFrame(
        {"Region": ["W"], "Jan 2026": [1.0], "Feb 2026": [2.0]}
    )
    assert "Period" not in normalize_table(two_periods).dataframe.columns

    text_body = pd.DataFrame(
        {
            "Region": ["W", "E"],
            "Jan 2026": ["a", "b"],
            "Feb 2026": ["c", "d"],
            "Mar 2026": ["e", "f"],
        }
    )
    assert "Period" not in normalize_table(text_body).dataframe.columns

"""Messy real-world structures: banner rows, headers not on row 1, scattered
blocks, merged two-row headers, crosstab (wide-period) layouts, European
numbers, and encoding fallbacks."""

from io import BytesIO

import pandas as pd
import pytest

from app.services.normalization import normalize_table
from app.services.parser import RawTable, add_join_candidates, add_union_candidates, parse_csv, parse_excel


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
    # The leading label column gets the human default name "Category".
    assert list(df.columns) == ["Category", "column_2", "column_3"]
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


def test_single_blank_row_splits_when_next_row_is_a_header():
    grid = [
        ["Code", "Meaning"],
        ["A", "Active"],
        ["C", "Cancelled"],
        [None, None],
        ["Date", "Amount"],
        ["2026-01-05", 100.0],
        ["2026-01-12", 140.0],
    ]
    tables = parse_excel("ops.xlsx", excel_bytes(grid, sheet="Ops"))
    assert [t.name for t in tables] == ["Ops (block 1)", "Ops (block 2)"]
    assert list(tables[1].dataframe.columns) == ["Date", "Amount"]


def test_grouped_report_with_blank_spacer_rows_stays_one_table():
    # Blank rows between GROUPS of data rows are layout, not new tables.
    grid = [
        ["Account", "Amount"],
        ["AC-1", 100.0],
        ["AC-2", 120.0],
        [None, None],
        ["AC-3", 90.0],
        ["AC-4", 60.0],
    ]
    tables = parse_excel("grouped.xlsx", excel_bytes(grid, sheet="Report"))
    assert [t.name for t in tables] == ["Report"]
    assert len(tables[0].dataframe.dropna(how="all")) == 4


def test_three_row_merged_header_flattened():
    grid = [
        ["Region", "2025", None, None, None],
        [None, "H1", None, "H2", None],
        [None, "Revenue", "Orders", "Revenue", "Orders"],
        ["West", 100.0, 5, 130.0, 6],
        ["East", 90.0, 4, 120.0, 7],
    ]
    tables = parse_excel("report.xlsx", excel_bytes(grid))
    assert list(tables[0].dataframe.columns) == [
        "Region",
        "2025 H1 Revenue",
        "2025 H1 Orders",
        "2025 H2 Revenue",
        "2025 H2 Orders",
    ]


def test_placeholder_null_tokens_cleared_so_numbers_coerce():
    df = pd.DataFrame({"revenue": ["1,200.00", "N/A", "980.00", "-", "1,500.00"]})
    normalized = normalize_table(df)
    values = normalized.dataframe["revenue"].tolist()
    assert values[0] == pytest.approx(1200.0)
    assert pd.isna(values[1]) and pd.isna(values[3])
    kinds = {n.finding_type for n in normalized.notes}
    assert "placeholder_nulls" in kinds
    assert "type_converted" in kinds  # the column still became numeric


def test_trailing_minus_and_space_thousands():
    df = pd.DataFrame({"betrag": ["1 234,56", "2 500,00", "1 000,00-"]})
    normalized = normalize_table(df)
    assert normalized.dataframe["betrag"].tolist() == pytest.approx([1234.56, 2500.0, -1000.0])


def test_repeated_header_rows_inside_data_removed():
    df = pd.DataFrame(
        {
            "Region": ["West", "Region", "East"],
            "Revenue": ["100.00", "Revenue", "90.00"],
        }
    )
    normalized = normalize_table(df)
    assert len(normalized.dataframe) == 2
    assert normalized.dataframe["Revenue"].tolist() == pytest.approx([100.0, 90.0])
    kinds = {n.finding_type for n in normalized.notes}
    assert "repeated_header_rows_removed" in kinds


def test_month_only_pivot_unpivots_with_string_periods():
    df = pd.DataFrame(
        {
            "Product": ["A", "B"],
            "Jan": [10.0, 20.0],
            "Feb": [11.0, 21.0],
            "Mar": [12.0, 22.0],
        }
    )
    normalized = normalize_table(df, table_name="Sales by Product")
    out = normalized.dataframe
    assert set(out.columns) == {"Product", "Period", "Sales"}
    assert sorted(out["Period"].unique().tolist()) == ["Feb", "Jan", "Mar"]
    assert len(out) == 6  # no invented dates
    assert not pd.api.types.is_datetime64_any_dtype(out["Period"])


def test_union_combines_disjoint_same_schema_sheets():
    jan = pd.DataFrame({"Date": ["2026-01-05"], "Revenue": [100.0]})
    feb = pd.DataFrame({"Date": ["2026-02-03"], "Revenue": [120.0]})
    mar = pd.DataFrame({"Date": ["2026-03-02"], "Revenue": [90.0]})
    from app.services.parser import RawTable

    tables = add_union_candidates(
        [RawTable("Jan", jan), RawTable("Feb", feb), RawTable("Mar", mar)]
    )
    names = [t.name for t in tables]
    assert "Combined (3 sheets)" in names
    combined = next(t for t in tables if t.name.startswith("Combined"))
    assert list(combined.dataframe.columns) == ["Source Sheet", "Date", "Revenue"]
    assert len(combined.dataframe) == 3


def test_union_skipped_for_master_plus_filtered_views():
    # A master sheet and per-category tabs holding the SAME rows must not be
    # double-counted.
    master = pd.DataFrame({"Id": ["T1", "T2", "T3"], "Amount": [1.0, 2.0, 3.0]})
    cat_a = master.iloc[:2].copy()
    cat_b = master.iloc[2:].copy()
    from app.services.parser import RawTable

    tables = add_union_candidates(
        [RawTable("Master", master), RawTable("Cat A", cat_a), RawTable("Cat B", cat_b)]
    )
    assert not any(t.name.startswith("Combined") for t in tables)


def test_mid_table_total_rows_and_net_lines_dropped():
    df = pd.DataFrame(
        {
            "Line": ["Consulting", "Retainers", "Total Income", "Rent", "Net Income"],
            "Amount": [100.0, 50.0, 150.0, 40.0, 110.0],
        }
    )
    normalized = normalize_table(df)
    assert normalized.dataframe["Line"].tolist() == ["Consulting", "Retainers", "Rent"]
    assert normalized.dataframe["Amount"].sum() == pytest.approx(190.0)


def test_total_column_dropped_before_unpivot():
    df = pd.DataFrame(
        {
            "Region": ["West", "East"],
            "Jan 2026": [100.0, 90.0],
            "Feb 2026": [110.0, 95.0],
            "Mar 2026": [120.0, 99.0],
            "Grand Total": [330.0, 284.0],
        }
    )
    normalized = normalize_table(df, table_name="Revenue by Region")
    out = normalized.dataframe
    assert "Grand Total" not in out.columns
    assert out["Revenue"].sum() == pytest.approx(614.0)  # totals not double-counted


def test_grouped_merged_labels_forward_filled():
    df = pd.DataFrame(
        {
            "Category": ["Beverages", None, None, "Food", None],
            "Item": ["Espresso", "Latte", "Tea", "Bagel", "Salad"],
            "Amount": [1.0, 2.0, 3.0, 4.0, 5.0],
        }
    )
    normalized = normalize_table(df)
    assert normalized.dataframe["Category"].tolist() == [
        "Beverages", "Beverages", "Beverages", "Food", "Food",
    ]
    kinds = {n.finding_type for n in normalized.notes}
    assert "grouped_labels_filled" in kinds


def test_units_row_under_header_skipped():
    grid = [
        ["Month", "Revenue", "Orders"],
        [None, "USD", "count"],
        ["Jan 2026", 100.0, 5],
        ["Feb 2026", 120.0, 7],
    ]
    tables = parse_excel("units.xlsx", excel_bytes(grid))
    df = tables[0].dataframe
    assert len(df) == 2
    assert df["Revenue"].tolist() == [100.0, 120.0]
    kinds = {n.finding_type for n in tables[0].notes}
    assert "units_row_skipped" in kinds


def test_transposed_table_flipped_to_records():
    grid = [
        ["Metric", "Store A", "Store B", "Store C", "Store D"],
        ["Revenue", 100.0, 120.0, 90.0, 105.0],
        ["Orders", 11, 14, 9, 12],
        ["Manager", "Kim", "Ray", "Ana", "Lee"],
    ]
    tables = parse_excel("stores.xlsx", excel_bytes(grid))
    df = tables[0].dataframe
    assert list(df.columns) == ["Record", "Revenue", "Orders", "Manager"]
    assert len(df) == 4
    assert df["Record"].tolist() == ["Store A", "Store B", "Store C", "Store D"]
    assert df["Revenue"].tolist() == [100.0, 120.0, 90.0, 105.0]


def test_regular_wide_table_not_transposed():
    grid = [
        ["Region", "Jan", "Feb", "Mar", "Apr"],
        ["West", 1.0, 2.0, 3.0, 4.0],
        ["East", 5.0, 6.0, 7.0, 8.0],
    ]
    tables = parse_excel("wide.xlsx", excel_bytes(grid))
    # All rows numeric-homogeneous -> no field-type variety -> stays as-is.
    assert "Record" not in tables[0].dataframe.columns


def test_excel_serial_dates_on_date_named_column():
    df = pd.DataFrame({"Order Date": [46023, 46054, 46085], "Amount": [1.0, 2.0, 3.0]})
    normalized = normalize_table(df)
    dates = normalized.dataframe["Order Date"]
    assert pd.api.types.is_datetime64_any_dtype(dates)
    assert dates.iloc[0] == pd.Timestamp(2026, 1, 1)


def test_compact_yyyymmdd_dates_on_date_named_column():
    df = pd.DataFrame({"Created": [20260105, 20260212, 20260320], "Sales": [1.0, 2.0, 3.0]})
    normalized = normalize_table(df)
    dates = normalized.dataframe["Created"]
    assert pd.api.types.is_datetime64_any_dtype(dates)
    assert dates.iloc[1] == pd.Timestamp(2026, 2, 12)
    # A plain numeric column with a non-date name stays numeric.
    other = normalize_table(pd.DataFrame({"Score": [20260105, 20260212, 20260320]}))
    assert pd.api.types.is_numeric_dtype(other.dataframe["Score"])


def test_iso_codes_suffixes_and_swiss_thousands():
    df = pd.DataFrame(
        {
            "amount": ["1,234.56 USD", "999.00 USD", "2,500.00 USD"],
            "fees": ["1'234.50 CHF", "2'000.00 CHF", "900.25 CHF"],
            "pipeline": ["$1.2M", "$800.5k", "$2B"],
        }
    )
    normalized = normalize_table(df)
    out = normalized.dataframe
    assert out["amount"].tolist() == pytest.approx([1234.56, 999.0, 2500.0])
    assert out["fees"].tolist() == pytest.approx([1234.50, 2000.0, 900.25])
    assert out["pipeline"].tolist() == pytest.approx([1_200_000.0, 800_500.0, 2_000_000_000.0])
    assert normalized.type_hints.get("amount") == "currency"
    assert normalized.type_hints.get("pipeline") == "currency"


def test_csv_preamble_lines_skipped():
    # Comma-bearing metadata lines defeat the sniffer's own skip logic, so
    # the retry path has to find the real header.
    text = (
        "Sales Export Report,,\n"
        "Generated: 2026-07-01,by reporting-suite,\n"
        "\n"
        "Date,Region,Revenue\n"
        "2026-01-05,West,100.00\n"
        "2026-01-06,East,90.00\n"
    )
    table = parse_csv("report.csv", text.encode("utf-8"))
    assert list(table.dataframe.columns) == ["Date", "Region", "Revenue"]
    assert len(table.dataframe) == 2
    assert any(n.finding_type == "banner_rows_skipped" for n in table.notes)


def test_ohlc_open_is_not_engagement():
    from app.services.semantic_mapper import ColumnInput, TableInput, map_dataset

    columns = [
        ColumnInput("Date", "date", "date", "date", 1.0, []),
        ColumnInput("Open", "open", "float", "measure", 0.9, []),
        ColumnInput("High", "high", "float", "measure", 0.9, []),
        ColumnInput("Low", "low", "float", "measure", 0.9, []),
        ColumnInput("Close", "close", "float", "measure", 0.9, []),
    ]
    mapping = map_dataset([TableInput("prices", columns)], filename="stock_prices.csv", llm=None)
    assert mapping.column_mappings["Open"].semantic_type == "other"
    assert mapping.column_mappings["Close"].semantic_type == "other"


def test_join_candidate_enriches_fact_with_dimension_columns():
    orders = pd.DataFrame(
        {
            "order_id": [f"O{i}" for i in range(20)],
            "customer_id": [f"C{i % 6}" for i in range(20)],
            "amount": [float(i) for i in range(20)],
        }
    )
    customers = pd.DataFrame(
        {
            "customer_id": [f"C{i}" for i in range(6)],
            "name": [f"Customer {i}" for i in range(6)],
        }
    )
    tables = add_join_candidates([RawTable("Orders", orders), RawTable("Customers", customers)])
    names = [t.name for t in tables]
    assert "Orders + Customers (joined)" in names
    joined = next(t for t in tables if t.name == "Orders + Customers (joined)")
    assert len(joined.dataframe) == 20  # fact row count preserved, no fan-out
    assert "Customers: name" in joined.dataframe.columns
    kinds = {n.finding_type for n in joined.notes}
    assert "relational_join_applied" in kinds


def test_join_skipped_for_coincidental_column_name_unrelated_values():
    # Both have an 'id' column, but the value domains don't overlap at all —
    # a same-named column from two unrelated systems must not be joined.
    left = pd.DataFrame({"id": [f"L{i}" for i in range(10)], "value": range(10)})
    right = pd.DataFrame({"id": [f"R{i}" for i in range(10)], "label": list("abcdefghij")})
    tables = add_join_candidates([RawTable("Left", left), RawTable("Right", right)])
    assert len(tables) == 2  # no join candidate added


def test_join_skipped_when_dimension_key_is_not_unique_enough():
    # 'category' repeats heavily on BOTH sides -> neither is a real key.
    left = pd.DataFrame({"category": (["A", "B"] * 10), "value": range(20)})
    right = pd.DataFrame({"category": (["A", "B"] * 5), "extra": range(10)})
    tables = add_join_candidates([RawTable("Left", left), RawTable("Right", right)])
    assert len(tables) == 2


def test_join_skipped_for_row_aligned_companion_sheet():
    # A helper/pivot-support sheet built alongside the main sheet (same row
    # count, unique per-row values) is NOT a dimension — joining it in just
    # bolts unrelated helper columns onto the real table. Real customer data
    # hit this: a 'NEW DATA SHEET' with ~as many rows as 'Tickets' sharing a
    # unique 'Number' column (both derived from the same underlying rows).
    main = pd.DataFrame(
        {
            "Number": [f"T{i}" for i in range(200)],
            "Duration": [float(i) for i in range(200)],
        }
    )
    helper = pd.DataFrame(
        {
            "Number": [f"T{i}" for i in range(198)],  # unique, near-total containment
            "Resolution Category": ["A", "B"] * 99,
        }
    )
    tables = add_join_candidates([RawTable("Tickets", main), RawTable("Helper Sheet", helper)])
    assert len(tables) == 2  # no join: helper is nearly as large as the fact table


def test_join_skipped_for_identical_schema_tables():
    # Same columns on both sides is a union candidate, not a join.
    a = pd.DataFrame({"id": [f"A{i}" for i in range(10)], "value": range(10)})
    b = pd.DataFrame({"id": [f"B{i}" for i in range(10)], "value": range(10)})
    tables = add_join_candidates([RawTable("A", a), RawTable("B", b)])
    assert len(tables) == 2


def test_join_candidates_capped():
    # Many mutually-joinable table pairs must not explode the candidate list.
    base = pd.DataFrame({"key": [f"K{i}" for i in range(20)], "value": range(20)})
    dims = [
        pd.DataFrame({"key": [f"K{i}" for i in range(20)], "label": [str(n)] * 20})
        for n in range(8)
    ]
    tables = [RawTable("Fact", base)] + [RawTable(f"Dim{i}", d) for i, d in enumerate(dims)]
    result = add_join_candidates(tables)
    joined_count = sum(1 for t in result if "joined" in t.name)
    assert joined_count <= 4


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

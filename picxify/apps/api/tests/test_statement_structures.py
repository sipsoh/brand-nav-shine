"""Financial-statement structures (from a real Yardi 12-month accrual export):
page-break continuation blocks, label-column subtotals verified numerically,
and content-based names for blank-headed label columns."""

import pandas as pd

from app.services.normalization import TransformNote, normalize_table
from app.services.parser import extract_tables


def _statement_grid(gap_rows: int = 2) -> pd.DataFrame:
    rows: list[list] = [
        ["The Lodge at Test (t01)"] + [None] * 4,
        [None, None, "Jun 2025", "Jul 2025", "Aug 2025"],
        ["4010-0000", "     Market Rent", 100.0, 110.0, 120.0],
        ["4020-0000", "     Care Income", 50.0, 55.0, 60.0],
        ["4999-9999", "   TOTAL REVENUE", 150.0, 165.0, 180.0],
    ]
    rows.extend([[None] * 5] * gap_rows)  # page-break artifact
    rows.extend(
        [
            ["5010-0000", "     Payroll", 80.0, 82.0, 84.0],
            ["5020-0000", "     Utilities", 20.0, 21.0, 22.0],
            ["5999-9999", "   TOTAL OPERATING EXPENSES", 100.0, 103.0, 106.0],
            ["6890-9999", " NET OPERATING INCOME", 50.0, 62.0, 74.0],
            ["9999-8006", "     Total Census", 40.0, 41.0, 42.0],
        ]
    )
    return pd.DataFrame(rows)


def test_headerless_continuation_block_is_merged():
    tables = extract_tables("Report1", _statement_grid())
    assert len(tables) == 1
    table = tables[0]
    assert table.name == "Report1"  # no "(block N)" suffix
    assert table.dataframe.shape[0] == 8
    note_types = {n.finding_type for n in table.notes}
    assert "continuation_block_merged" in note_types
    assert "no_header_detected" not in note_types  # header inherited


def test_separate_headered_tables_are_not_merged():
    grid = pd.DataFrame(
        [
            ["Region", "Amount", None],
            ["West", 10.0, None],
            ["East", 20.0, None],
            [None, None, None],
            [None, None, None],
            ["Owner", "Quota", None],
            ["Dana", 100.0, None],
            ["Priya", 120.0, None],
        ]
    )
    tables = extract_tables("Sheet1", grid)
    assert len(tables) == 2  # the second block announces its own header


def test_blank_label_headers_named_code_and_category():
    tables = extract_tables("Report1", _statement_grid())
    assert list(tables[0].dataframe.columns[:2]) == ["Code", "Category"]


def test_subtotals_in_second_column_dropped_and_verified():
    tables = extract_tables("Report1", _statement_grid())
    normalized = normalize_table(tables[0].dataframe, table_name="Report1")
    labels = set(normalized.dataframe["Category"].astype(str))
    assert "TOTAL REVENUE" not in labels  # verified: sum of the two details
    assert "TOTAL OPERATING EXPENSES" not in labels
    assert "NET OPERATING INCOME" not in labels  # derived line, label-only drop
    assert "Market Rent" in labels
    # A statistical row that merely STARTS with 'Total' is real data: its
    # values match no prefix sum, so it must survive.
    assert "Total Census" in labels
    footer_notes = [n for n in normalized.notes if n.finding_type == "footer_rows_removed"]
    assert footer_notes and footer_notes[0].meta["count"] == 3


def test_sign_flipped_subtotal_still_verifies():
    from app.services.normalization import _drop_footer_rows

    df = pd.DataFrame(
        {
            "Code": ["5010", "5020", "5999"],
            "Category": ["Payroll", "Utilities", "TOTAL EXPENSES"],
            "Jan": [80.0, 20.0, -100.0],  # expense total shown negative
        }
    )
    notes: list[TransformNote] = []
    out = _drop_footer_rows(df, notes)
    assert "TOTAL EXPENSES" not in set(out["Category"])


def test_unverifiable_total_label_is_kept():
    from app.services.normalization import _drop_footer_rows

    df = pd.DataFrame(
        {
            "Code": ["a1", "a2", "a3"],
            "Category": ["Move-ins", "Move-outs", "Total Occupancy %"],
            "Jan": [5.0, 3.0, 92.4],  # matches no prefix sum
        }
    )
    notes: list[TransformNote] = []
    out = _drop_footer_rows(df, notes)
    assert "Total Occupancy %" in set(out["Category"])

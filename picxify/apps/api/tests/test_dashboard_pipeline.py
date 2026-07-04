from dataclasses import dataclass

import pandas as pd

from app.services.dashboard_pipeline import _pick_date_grain


@dataclass
class FakeColumn:
    name: str
    role_hint: str | None


def test_constant_date_column_yields_no_grain():
    # A single-period snapshot report (every row shares one date) has no
    # trend to show. Regression: this used to still return "week", which
    # made the planner build a one-point "Performance over time" chart
    # mislabeled as a trend (real report: an AR-aging snapshot where every
    # row's 'Period' was May 2026).
    df = pd.DataFrame({"period": pd.to_datetime(["2026-05-01"] * 5)})
    columns = [FakeColumn(name="period", role_hint="date")]
    assert _pick_date_grain(df, columns) is None


def test_short_span_date_column_yields_week_grain():
    df = pd.DataFrame(
        {"synced_at": pd.to_datetime(["2026-06-08", "2026-06-09", "2026-06-11"])}
    )
    columns = [FakeColumn(name="synced_at", role_hint="date")]
    assert _pick_date_grain(df, columns) == "week"


def test_long_span_date_column_yields_month_grain():
    df = pd.DataFrame(
        {"date": pd.to_datetime(["2026-01-01", "2026-04-01", "2026-07-01"])}
    )
    columns = [FakeColumn(name="date", role_hint="date")]
    assert _pick_date_grain(df, columns) == "month"


def test_no_date_column_yields_no_grain():
    df = pd.DataFrame({"amount": [1, 2, 3]})
    columns = [FakeColumn(name="amount", role_hint="measure")]
    assert _pick_date_grain(df, columns) is None

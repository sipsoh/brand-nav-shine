"""Picxify eval harness (SETUP.md §18.4): run fixture workbooks through the
full pipeline (parse -> profile -> map -> generate) and check expectations.

Usage (from apps/api, venv active):
    python -m evals.run_evals
Exit code is non-zero if any expectation fails.
"""

import sys
import warnings
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

warnings.filterwarnings("ignore")

FIXTURES = Path(__file__).resolve().parents[3] / "packages" / "sample-data" / "complex"

# Per-fixture expectations: the "golden" behavior this harness protects.
EXPECTATIONS = {
    "saas_sales_pipeline.xlsx": {
        # This workbook also has a small 'Reps' sheet (Owner -> Quota, one
        # row per rep). The join engine now recognizes it as a real
        # dimension and enriches Pipeline with quota context — a genuine
        # improvement over the plain Pipeline sheet, not a regression.
        "use_case": "sales",
        "primary_sheet": "Pipeline + Rep Quotas (joined)",
        "required_kpi_tokens": ["deal amount", "win rate"],
        "chart_aggregations_forbidden": [],
    },
    "ecommerce_orders.xlsx": {
        "use_case": "sales",  # revenue + status; acceptable until an e-com template exists
        "primary_sheet": "Orders",
        "required_kpi_tokens": ["total revenue", "mom change"],
        # The per-unit price must never become the summed headline metric.
        "chart_aggregations_forbidden": [("Unit Price", "sum")],
    },
    "financial_statement.xlsx": {
        "use_case": None,  # any; the check that matters is sheet selection
        "primary_sheet": "Monthly",
        "required_kpi_tokens": ["total revenue"],
        "chart_aggregations_forbidden": [],
    },
    "hr_roster.xlsx": {
        "use_case": None,
        "primary_sheet": "Roster",
        "required_kpi_tokens": ["average performance score"],
        # Ratings must never be summed into charts.
        "chart_aggregations_forbidden": [("Performance Score", "sum")],
    },
    "website_analytics.xlsx": {
        "use_case": None,
        "primary_sheet": "Daily",
        # Conversions outrank sessions as the headline — the right executive call.
        "required_kpi_tokens": ["total conversions"],
        # A percent-rate column must never be summed.
        "chart_aggregations_forbidden": [("Bounce Rate", "sum")],
    },
    "nonprofit_donations.xlsx": {
        "use_case": None,
        "primary_sheet": "Donations",
        "required_kpi_tokens": ["total amount"],
        "chart_aggregations_forbidden": [],
    },
    "inventory_snapshot.xlsx": {
        "use_case": None,
        "primary_sheet": "Stock",
        "required_kpi_tokens": ["total on hand qty"],
        "chart_aggregations_forbidden": [("Unit Cost", "sum")],
    },
    "real_estate_portfolio.xlsx": {
        "use_case": None,
        "primary_sheet": "Portfolio",
        "required_kpi_tokens": ["total monthly rent"],
        "chart_aggregations_forbidden": [("Occupancy Rate", "sum"), ("Year Built", "sum")],
    },
    "restaurant_pos.xlsx": {
        "use_case": None,
        "primary_sheet": "Daily Sales",
        "required_kpi_tokens": ["total gross sales"],
        "chart_aggregations_forbidden": [],
    },
    "pivot_wide_report.xlsx": {
        # Pivot-shaped data (months as columns) is unpivoted to long form, so
        # a real revenue trend must come out the other side.
        "use_case": None,
        "primary_sheet": "Revenue by Region",
        "required_kpi_tokens": ["total revenue"],
        "chart_aggregations_forbidden": [],
    },
    "messy_ops_report.xlsx": {
        # Banner rows above the table, header on sheet row 4, currency strings
        # with accounting negatives, a blank + a duplicate header, a Grand
        # Total row, and a loose footnote block. Must still read cleanly.
        "use_case": None,
        "primary_sheet": "Export",
        "required_kpi_tokens": ["total cost"],
        "chart_aggregations_forbidden": [],
    },
    "scattered_report.xlsx": {
        # Several tables scattered per sheet: the KPI block above the real
        # table must not poison it; the 300-row donations table wins.
        "use_case": None,
        "primary_sheet": "Dashboard Data (block 2)",
        "required_kpi_tokens": ["total amount"],
        "chart_aggregations_forbidden": [],
    },
    "euro_sales.csv": {
        # Semicolon CSV, day-first dates, "€ 1.234,56" numbers, German headers.
        "use_case": None,
        "primary_sheet": "euro_sales",
        "required_kpi_tokens": ["total umsatz"],
        "chart_aggregations_forbidden": [],
    },
    "monthly_tabs.xlsx": {
        # One dataset split across six disjoint month tabs: combined into a
        # single table so the dashboard covers the whole period.
        "use_case": None,
        "primary_sheet": "Combined (6 sheets)",
        "required_kpi_tokens": ["total revenue"],
        "chart_aggregations_forbidden": [],
    },
    "month_only_pivot.xlsx": {
        # Month columns with no year anywhere still unpivot (periods stay as
        # month names — no invented dates). Value column named from the sheet.
        "use_case": None,
        "primary_sheet": "Sales by Product",
        "required_kpi_tokens": ["total sales"],
        "chart_aggregations_forbidden": [],
    },
    "single_gap_scatter.xlsx": {
        # A lookup block and the real table separated by ONE blank row.
        "use_case": None,
        "primary_sheet": "Ops Data (block 2)",
        "required_kpi_tokens": ["total amount"],
        "chart_aggregations_forbidden": [],
    },
    "dirty_values.csv": {
        # Placeholder nulls (N/A, -), accounting negatives, percent strings,
        # and a repeated header line mid-file.
        "use_case": None,
        "primary_sheet": "dirty_values",
        "required_kpi_tokens": ["total revenue"],
        "chart_aggregations_forbidden": [("Discount", "sum")],
    },
    "financial_pl_statement.xlsx": {
        # QuickBooks-style P&L: banner block, month columns + Total column,
        # mid-table Total Income/Expenses rows, Net Income line. None of the
        # derived lines may double-count.
        "use_case": None,
        "primary_sheet": "Profit and Loss",
        "required_kpi_tokens": ["total value"],
        "chart_aggregations_forbidden": [],
    },
    "pivot_with_totals.xlsx": {
        # Crosstab with a Grand Total column AND a Total row.
        "use_case": None,
        "primary_sheet": "Revenue by Region",
        "required_kpi_tokens": ["total revenue"],
        "chart_aggregations_forbidden": [],
    },
    "grouped_merged_labels.xlsx": {
        # Vertically merged category labels (NaN runs under each group name).
        "use_case": None,
        "primary_sheet": "Category Sales",
        "required_kpi_tokens": ["total amount"],
        "chart_aggregations_forbidden": [],
    },
    "units_row_report.xlsx": {
        # A units row (USD / count / %) sits under the header.
        "use_case": None,
        "primary_sheet": "Monthly",
        "required_kpi_tokens": ["total revenue"],
        "chart_aggregations_forbidden": [("Refund Rate", "sum")],
    },
    "transposed_metrics.xlsx": {
        # Fields as rows, stores as columns: flipped to records.
        "use_case": None,
        "primary_sheet": "Store Metrics",
        "required_kpi_tokens": ["total revenue"],
        "chart_aggregations_forbidden": [],
    },
    "serial_dates.xlsx": {
        # Order dates as raw Excel serial numbers.
        "use_case": None,
        "primary_sheet": "Orders",
        "required_kpi_tokens": ["total amount", "mom change"],
        "chart_aggregations_forbidden": [],
    },
    "compact_dates.csv": {
        # Dates as YYYYMMDD integers.
        "use_case": None,
        "primary_sheet": "compact_dates",
        "required_kpi_tokens": ["total sales", "mom change"],
        "chart_aggregations_forbidden": [],
    },
    "currency_codes.csv": {
        # "1,234.56 USD", Swiss "1'234.56 CHF", and "$1.2M" suffixes.
        "use_case": None,
        "primary_sheet": "currency_codes",
        "required_kpi_tokens": ["total amount"],
        "chart_aggregations_forbidden": [],
    },
    "bank_statement.csv": {
        # Debit/Credit split columns; credits are money in.
        "use_case": None,
        "primary_sheet": "bank_statement",
        "required_kpi_tokens": ["total credit"],
        "chart_aggregations_forbidden": [],
    },
    "pipe_export.txt": {
        # Pipe-delimited .txt.
        "use_case": None,
        "primary_sheet": "pipe_export",
        "required_kpi_tokens": ["total revenue"],
        "chart_aggregations_forbidden": [],
    },
    "csv_with_preamble.csv": {
        # Title/metadata lines above the real CSV header.
        "use_case": None,
        "primary_sheet": "csv_with_preamble",
        "required_kpi_tokens": ["total revenue"],
        "chart_aggregations_forbidden": [],
    },
    "quoted_newlines.csv": {
        # Quoted fields with embedded newlines and commas.
        "use_case": None,
        "primary_sheet": "quoted_newlines",
        "required_kpi_tokens": ["total revenue"],
        "chart_aggregations_forbidden": [],
    },
    "stock_prices.csv": {
        # OHLC candles: 'Open' is a price, not engagement; prices never sum.
        "use_case": None,
        "primary_sheet": "stock_prices",
        "required_kpi_tokens": ["total volume"],
        "chart_aggregations_forbidden": [("Open", "sum"), ("Close", "sum")],
    },
    "pdf_revenue_report.pdf": {
        # A clean single-page PDF export: digital text-layer table extraction.
        "use_case": None,
        "primary_sheet": "Page 1",
        "required_kpi_tokens": ["total revenue"],
        "chart_aggregations_forbidden": [],
    },
    "pdf_multipage_orders.pdf": {
        # A table pdfplumber only sees one page at a time; pages must
        # recombine into a single 140-row table.
        "use_case": None,
        "primary_sheet": "Combined (5 pages)",
        "required_kpi_tokens": ["total amount"],
        "chart_aggregations_forbidden": [],
    },
    "scanned_donation_summary.pdf": {
        # No text layer at all — OCR fallback, and the low-confidence banner
        # must trip (checked separately, not via this token-based harness).
        "use_case": None,
        "primary_sheet": "Page 1 (scanned)",
        "required_kpi_tokens": ["total amount"],
        "chart_aggregations_forbidden": [],
    },
    ("join_orders.csv", "join_customers.csv"): {
        # Two related files uploaded together: orders (fact) + customers
        # (dimension) must join, enriching orders with segment/name.
        "dataset_name": "Orders + Customers",
        "use_case": None,
        "primary_sheet": "join_orders + join_customers (joined)",
        "required_kpi_tokens": ["total amount"],
        "chart_aggregations_forbidden": [],
    },
    "uncalculated_formula_report.xlsx": {
        # A 'Total' column is live formulas with no cached value (a report
        # tool that never ran a calc engine) — must fall back to a real
        # measure (Spend), never show a blank/zero 'Total' KPI.
        "use_case": "marketing",
        "primary_sheet": "Campaign Report",
        "required_kpi_tokens": ["total spend"],
        "chart_aggregations_forbidden": [("Total", "sum")],
    },
    "newline_headers_report.xlsx": {
        # Headers with an embedded newline ('Q1\nRevenue' typed with
        # Alt+Enter) must read as clean text, not a raw newline.
        "use_case": None,
        "primary_sheet": "Quarterly",
        "required_kpi_tokens": ["total q1 revenue"],
        "chart_aggregations_forbidden": [],
    },
    "numeric_percent.csv": {
        # Percent columns that were NEVER text (native floats from a BI
        # export) — one already a 0-1 fraction, one whole-number percent.
        "use_case": None,
        "primary_sheet": "numeric_percent",
        "required_kpi_tokens": ["rows analyzed"],
        "chart_aggregations_forbidden": [],
    },
}


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def get_bytes(self, key: str) -> bytes:
        return self.objects[key]

    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None:
        self.objects[key] = data


def run_fixture(filename: str, data: bytes) -> dict:
    return run_multi_file_fixture([(filename, data)])


def run_multi_file_fixture(files: list[tuple[str, bytes]], name: str | None = None) -> dict:
    """Like run_fixture, but for a dataset built from several files at once
    (the multi-file-join case) — mirrors what POST /datasets/from-file with
    fileIds does, minus the HTTP layer."""
    from app import models  # noqa: F401
    from app.db import Base
    from app.models import (
        Dashboard,
        DashboardVersion,
        Dataset,
        DatasetFile,
        GenerationJob,
        UploadedFile,
        User,
        Workspace,
    )
    from app.services.dashboard_pipeline import run_generate_dashboard
    from app.services.dataset_pipeline import run_parse_dataset

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    storage = FakeStorage()

    user = User(auth_user_id="eval", email="eval@picxify.local")
    db.add(user)
    db.flush()
    workspace = Workspace(name="Evals", created_by=user.id)
    db.add(workspace)
    db.flush()

    dataset_name = name or files[0][0].rsplit(".", 1)[0].replace("_", " ").title()
    dataset = Dataset(
        workspace_id=workspace.id,
        source_type="file",
        name=dataset_name,
        created_by=user.id,
    )
    db.add(dataset)
    db.flush()

    for position, (filename, data) in enumerate(files):
        object_key = f"upload-{position}"
        storage.objects[object_key] = data
        uploaded = UploadedFile(
            workspace_id=workspace.id,
            uploaded_by=user.id,
            original_filename=filename,
            size_bytes=len(data),
            object_key=object_key,
            status="uploaded",
        )
        db.add(uploaded)
        db.flush()
        if position == 0:
            dataset.file_id = uploaded.id
        db.add(DatasetFile(dataset_id=dataset.id, file_id=uploaded.id, position=position))

    parse_job = GenerationJob(
        workspace_id=workspace.id, user_id=user.id, dataset_id=dataset.id,
        job_type="parse_dataset",
    )
    db.add(parse_job)
    db.commit()
    run_parse_dataset(db, storage, dataset.id, parse_job.id)
    db.refresh(parse_job)
    if parse_job.status != "succeeded":
        return {"error": f"parse failed: {parse_job.error_message}"}

    dashboard = Dashboard(
        workspace_id=workspace.id, dataset_id=dataset.id, title="Eval", created_by=user.id
    )
    db.add(dashboard)
    db.flush()
    generate_job = GenerationJob(
        workspace_id=workspace.id, user_id=user.id, dataset_id=dataset.id,
        dashboard_id=dashboard.id, job_type="generate_dashboard", input={"audience": "executive"},
    )
    db.add(generate_job)
    db.commit()
    run_generate_dashboard(db, storage, dashboard.id, generate_job.id)
    db.refresh(generate_job)
    if generate_job.status != "succeeded":
        return {"error": f"generate failed: {generate_job.error_message}"}

    version = db.scalar(
        select(DashboardVersion).where(DashboardVersion.dashboard_id == dashboard.id)
    )
    return {"spec": version.spec}


def check(filename: str, spec: dict, expect: dict) -> list[str]:
    problems: list[str] = []
    if expect["use_case"] and spec["dashboard"]["useCase"] != expect["use_case"]:
        problems.append(
            f"use case = {spec['dashboard']['useCase']!r}, expected {expect['use_case']!r}"
        )
    sheet = spec["dataSources"][0]["displayName"]
    if sheet != expect["primary_sheet"]:
        problems.append(f"built from sheet {sheet!r}, expected {expect['primary_sheet']!r}")

    kpi_labels = []
    chart_specs = []
    for section in spec["sections"]:
        for widget in section["widgets"]:
            if widget["type"] == "kpi":
                kpi_labels.append(widget["kpi"]["label"])
            if widget["type"] == "chart":
                chart_specs.append(widget["chart"]["querySpec"])

    joined = " ".join(kpi_labels).lower()
    for token in expect["required_kpi_tokens"]:
        if token not in joined:
            problems.append(f"expected a KPI mentioning {token!r}; KPIs = {kpi_labels}")

    for column, aggregation in expect["chart_aggregations_forbidden"]:
        for query_spec in chart_specs:
            for measure in query_spec.get("measures", []):
                if measure["column"] == column and measure["aggregation"] == aggregation:
                    problems.append(f"chart uses forbidden {aggregation}({column})")

    # Universal invariants.
    for section in spec["sections"]:
        for widget in section["widgets"]:
            if widget["type"] == "chart" and not widget["chart"].get("echartsOption", {}).get(
                "series"
            ):
                problems.append(f"chart {widget['id']} has no rendered series")
    return problems


def main() -> int:
    from app.services.spec_validator import assert_source_traces, validate_spec

    failures = 0
    for key, expect in EXPECTATIONS.items():
        # A tuple key is a multi-file fixture (e.g. orders.csv + customers.csv
        # uploaded together, to prove the join/union candidate machinery).
        multi = isinstance(key, tuple)
        filenames = list(key) if multi else [key]
        filename = " + ".join(filenames)
        files = [(name, (FIXTURES / name).read_bytes()) for name in filenames]
        result = run_multi_file_fixture(files, name=expect.get("dataset_name")) if multi else run_fixture(*files[0])
        if "error" in result:
            print(f"✗ {filename}: {result['error']}")
            failures += 1
            continue
        spec = result["spec"]
        try:
            validate_spec(spec)
            assert_source_traces(spec)
        except Exception as error:
            print(f"✗ {filename}: spec invalid: {error}")
            failures += 1
            continue
        problems = check(filename, spec, expect)
        sheet = spec["dataSources"][0]["displayName"]
        use_case = spec["dashboard"]["useCase"]
        if problems:
            print(f"✗ {filename} (sheet={sheet}, useCase={use_case})")
            for problem in problems:
                print(f"    - {problem}")
            failures += 1
        else:
            kpis = [
                w["kpi"]["label"]
                for s in spec["sections"]
                for w in s["widgets"]
                if w["type"] == "kpi"
            ]
            print(f"✓ {filename} (sheet={sheet}, useCase={use_case}, KPIs={kpis})")
    print(f"\n{len(EXPECTATIONS) - failures}/{len(EXPECTATIONS)} fixtures passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

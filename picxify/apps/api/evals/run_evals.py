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
        "use_case": "sales",
        "primary_sheet": "Pipeline",
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
}


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def get_bytes(self, key: str) -> bytes:
        return self.objects[key]

    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None:
        self.objects[key] = data


def run_fixture(filename: str, data: bytes) -> dict:
    from app import models  # noqa: F401
    from app.db import Base
    from app.models import Dashboard, DashboardVersion, Dataset, GenerationJob, UploadedFile, User, Workspace
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
    storage.objects["upload"] = data
    uploaded = UploadedFile(
        workspace_id=workspace.id,
        uploaded_by=user.id,
        original_filename=filename,
        size_bytes=len(data),
        object_key="upload",
        status="uploaded",
    )
    db.add(uploaded)
    db.flush()
    dataset = Dataset(
        workspace_id=workspace.id,
        file_id=uploaded.id,
        name=filename.rsplit(".", 1)[0].replace("_", " ").title(),
        source_type="file",
        created_by=user.id,
    )
    db.add(dataset)
    db.flush()
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
    for filename, expect in EXPECTATIONS.items():
        data = (FIXTURES / filename).read_bytes()
        result = run_fixture(filename, data)
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

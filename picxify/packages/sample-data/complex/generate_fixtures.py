"""Deterministic generator for the complex Excel eval fixtures.

Each workbook reproduces real-world mess: multi-sheet layouts with summary and
lookup tabs, currency strings (including accounting negatives), mixed date
formats, footer totals, blank rows, title rows above headers, and mostly-null
columns. Regenerate with:

    python packages/sample-data/complex/generate_fixtures.py
"""

import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent
random.seed(20260702)

REGIONS = ["West", "East", "Central", "South"]
OWNERS = ["Dana Reyes", "Marcus Cole", "Priya Patel", "Tom Alvarez", "Jin Park"]
STAGES = ["Prospecting", "Discovery", "Proposal", "Negotiation", "Closed Won", "Closed Lost"]
STAGE_WEIGHTS = [0.12, 0.18, 0.2, 0.15, 0.2, 0.15]


def money(value: float) -> str:
    return f"${value:,.2f}"


def mixed_date(day: date, style: int) -> str:
    if style == 0:
        return day.isoformat()
    if style == 1:
        return day.strftime("%m/%d/%Y")
    return day.strftime("%b %d, %Y")


def spread_dates(start: date, days: int, n: int) -> list[date]:
    return [start + timedelta(days=random.randrange(days)) for _ in range(n)]


def sales_pipeline() -> None:
    start = date(2026, 1, 5)
    rows = []
    for i in range(600):
        created = start + timedelta(days=random.randrange(150))
        stage = random.choices(STAGES, weights=STAGE_WEIGHTS)[0]
        amount = random.choice([2_500, 5_000, 8_000, 12_000, 24_000, 45_000, 80_000]) * (
            0.8 + random.random() * 0.6
        )
        rows.append(
            {
                "Deal ID": f"D-{4000 + i}",
                "Account": f"{random.choice(['Acme', 'Borealis', 'Cedar', 'Deltona', 'Everline', 'Fairway'])} {random.choice(['Health', 'Logistics', 'Retail', 'Labs', 'Partners'])}",
                "Owner": random.choice(OWNERS),
                "Region": random.choice(REGIONS),
                "Segment": random.choices(["SMB", "Mid-Market", "Enterprise"], [0.5, 0.35, 0.15])[0],
                "Stage": stage,
                "Deal Amount": money(amount),
                "Created Date": mixed_date(created, random.randrange(3)),
                "Close Date": (created + timedelta(days=random.randrange(20, 90))).isoformat()
                if stage.startswith("Closed")
                else None,
            }
        )
    df = pd.DataFrame(rows)
    # A couple of blank rows and a grand-total footer, like a human-exported report.
    blank = {c: None for c in df.columns}
    total = dict(blank)
    total["Deal ID"] = "Grand Total"
    total["Deal Amount"] = money(sum(float(r["Deal Amount"].replace("$", "").replace(",", "")) for r in rows))
    df = pd.concat([df, pd.DataFrame([blank, blank, total])], ignore_index=True)

    reps = pd.DataFrame(
        {"Owner": OWNERS, "Quota": [money(q) for q in [400_000, 380_000, 420_000, 350_000, 400_000]]}
    )
    summary = pd.DataFrame(
        {
            "Unnamed helper": ["Won", "Lost", "Open"],
            "Count": [
                sum(1 for r in rows if r["Stage"] == "Closed Won"),
                sum(1 for r in rows if r["Stage"] == "Closed Lost"),
                sum(1 for r in rows if not r["Stage"].startswith("Closed")),
            ],
        }
    )
    with pd.ExcelWriter(OUT / "saas_sales_pipeline.xlsx", engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Pipeline", index=False)
        summary.to_excel(writer, sheet_name="Summary", index=False)
        reps.to_excel(writer, sheet_name="Rep Quotas", index=False)


def ecommerce_orders() -> None:
    products = [
        ("Trail Backpack 40L", "Outdoor", 89.0),
        ("Insulated Bottle", "Outdoor", 24.0),
        ("Merino Hoodie", "Apparel", 120.0),
        ("Everyday Tee", "Apparel", 28.0),
        ("Camp Stove", "Outdoor", 65.0),
        ("Wool Socks 3pk", "Apparel", 22.0),
        ("Headlamp Pro", "Gear", 45.0),
        ("Dry Bag 20L", "Gear", 32.0),
    ]
    start = date(2026, 1, 1)
    rows = []
    for i in range(2200):
        name, category, price = random.choice(products)
        units = random.choices([1, 2, 3, 4], [0.6, 0.25, 0.1, 0.05])[0]
        status = random.choices(["Delivered", "Returned", "Cancelled"], [0.88, 0.08, 0.04])[0]
        ordered = start + timedelta(days=random.randrange(170))
        rows.append(
            {
                "Order ID": f"ORD-{100000 + i}",
                "Order Date": ordered,
                "Customer": f"customer{random.randrange(1, 900)}@example.com",
                "Product": name,
                "Category": category,
                "Units": units,
                "Unit Price": money(price),
                "Revenue": money(price * units if status != "Cancelled" else 0),
                "Region": random.choice(REGIONS),
                "Status": status,
            }
        )
    df = pd.DataFrame(rows)
    returns = df[df["Status"] == "Returned"].copy()
    with pd.ExcelWriter(OUT / "ecommerce_orders.xlsx", engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Orders", index=False)
        returns.to_excel(writer, sheet_name="Returns", index=False)


def financial_statement() -> None:
    months = pd.date_range("2025-07-01", periods=12, freq="MS")
    revenue = [round(180_000 * (1 + 0.03) ** i * (0.94 + random.random() * 0.12), 2) for i in range(12)]
    cogs = [round(r * (0.34 + random.random() * 0.05), 2) for r in revenue]
    opex = [round(95_000 * (0.97 + random.random() * 0.1), 2) for _ in range(12)]
    net = [round(r - c - o, 2) for r, c, o in zip(revenue, cogs, opex)]
    monthly = pd.DataFrame(
        {
            "Month": months,
            "Revenue": [money(v) for v in revenue],
            "COGS": [money(v) for v in cogs],
            "Operating Expenses": [money(v) for v in opex],
            # Accounting-style negatives for loss months.
            "Net Income": [money(v) if v >= 0 else f"(${abs(v):,.2f})" for v in net],
        }
    )
    # A presentation-style P&L sheet: title row, blank row, then data — the kind
    # of layout that defeats naive header detection. Sheet selection should
    # prefer the clean 'Monthly' sheet.
    pl_rows = [
        ["FY2026 Income Statement — Northwind Services LLC", None, None],
        [None, None, None],
        ["Line Item", "FY2025", "FY2026"],
        ["Revenue", money(sum(revenue) * 0.9), money(sum(revenue))],
        ["COGS", money(sum(cogs) * 0.92), money(sum(cogs))],
        ["Operating Expenses", money(sum(opex) * 0.97), money(sum(opex))],
        ["Net Income", money(sum(net) * 0.7), money(sum(net))],
    ]
    pl = pd.DataFrame(pl_rows)
    with pd.ExcelWriter(OUT / "financial_statement.xlsx", engine="openpyxl") as writer:
        pl.to_excel(writer, sheet_name="P&L", index=False, header=False)
        monthly.to_excel(writer, sheet_name="Monthly", index=False)


def hr_roster() -> None:
    departments = ["Engineering", "Sales", "Support", "Operations", "Finance", "Marketing"]
    first = ["Sam", "Jordan", "Ava", "Noah", "Mia", "Liam", "Zoe", "Eli", "Ruth", "Omar"]
    last = ["Nguyen", "Garcia", "Smith", "Chen", "Okafor", "Rossi", "Kim", "Silva", "Novak"]
    rows = []
    for i in range(850):
        hired = date(2019, 1, 1) + timedelta(days=random.randrange(2700))
        terminated = None
        status = "Active"
        if random.random() < 0.22:
            status = "Terminated"
            terminated = hired + timedelta(days=random.randrange(60, 1800))
        rows.append(
            {
                "Employee ID": f"E{2000 + i}",
                "Name": f"{random.choice(first)} {random.choice(last)}",
                "Department": random.choice(departments),
                "Location": random.choice(["Cleveland", "Austin", "Remote", "Tampa"]),
                "Hire Date": hired,
                "Termination Date": terminated,
                "Status": status,
                "Annual Salary": money(random.choice([52, 61, 74, 88, 104, 125, 150]) * 1000),
                "Performance Score": random.choices([2, 3, 4, 5], [0.08, 0.3, 0.42, 0.2])[0],
            }
        )
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(OUT / "hr_roster.xlsx", engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Roster", index=False)
        df[df["Status"] == "Terminated"].to_excel(writer, sheet_name="Terminations", index=False)


if __name__ == "__main__":
    sales_pipeline()
    ecommerce_orders()
    financial_statement()
    hr_roster()
    print("fixtures written to", OUT)

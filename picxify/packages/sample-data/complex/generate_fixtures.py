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


def website_analytics() -> None:
    """Marketing-ops data: engagement counts plus percent-string rates."""
    channels = ["Organic", "Paid Search", "Social", "Email", "Referral", "Direct"]
    start = date(2026, 1, 1)
    rows = []
    for day_offset in range(160):
        for channel in channels:
            sessions = random.randrange(180, 2200)
            rows.append(
                {
                    "Date": start + timedelta(days=day_offset),
                    "Channel": channel,
                    "Sessions": sessions,
                    "Pageviews": int(sessions * (1.6 + random.random() * 1.8)),
                    "Bounce Rate": f"{random.uniform(28, 71):.1f}%",
                    "Conversions": int(sessions * random.uniform(0.005, 0.04)),
                }
            )
    pd.DataFrame(rows).to_excel(OUT / "website_analytics.xlsx", sheet_name="Daily", index=False)


def nonprofit_donations() -> None:
    campaigns = ["Annual Gala", "Giving Tuesday", "Spring Appeal", "Monthly Giving", "Capital Fund"]
    start = date(2025, 9, 1)
    rows = []
    for i in range(1400):
        rows.append(
            {
                "Donation ID": f"DON-{50000 + i}",
                "Date": start + timedelta(days=random.randrange(280)),
                "Donor": f"Donor {random.randrange(1, 640)}",
                "Campaign": random.choice(campaigns),
                "Channel": random.choices(["Online", "Check", "Event", "Payroll"], [0.55, 0.2, 0.15, 0.1])[0],
                "Amount": money(random.choices([25, 50, 100, 250, 1000, 5000], [0.35, 0.25, 0.2, 0.12, 0.06, 0.02])[0]),
                "Recurring": random.choices(["Yes", "No"], [0.3, 0.7])[0],
            }
        )
    pd.DataFrame(rows).to_excel(OUT / "nonprofit_donations.xlsx", sheet_name="Donations", index=False)


def inventory_snapshot() -> None:
    categories = ["Fasteners", "Electrical", "Plumbing", "Safety", "Tools"]
    warehouses = ["CLE-01", "ATX-02", "TPA-03"]
    rows = []
    for i in range(1600):
        rows.append(
            {
                "Warehouse": random.choice(warehouses),
                "SKU": f"SKU-{7000 + i}",
                "Category": random.choice(categories),
                "On Hand Qty": random.randrange(0, 1200),
                "Reorder Point": random.randrange(20, 200),
                "Unit Cost": money(random.uniform(0.4, 90)),
                "Last Counted": date(2026, 5, 1) + timedelta(days=random.randrange(45)),
            }
        )
    pd.DataFrame(rows).to_excel(OUT / "inventory_snapshot.xlsx", sheet_name="Stock", index=False)


def real_estate_portfolio() -> None:
    cities = ["Cleveland", "Columbus", "Tampa", "Austin", "Raleigh"]
    types = ["Multifamily", "Retail", "Office", "Industrial"]
    rows = []
    for i in range(140):
        units = random.randrange(1, 220)
        rows.append(
            {
                "Property ID": f"PROP-{300 + i}",
                "City": random.choice(cities),
                "Type": random.choices(types, [0.5, 0.2, 0.15, 0.15])[0],
                "Units": units,
                "Sq Ft": units * random.randrange(650, 1400),
                "Monthly Rent": money(units * random.uniform(850, 1900)),
                "Occupancy Rate": f"{random.uniform(72, 100):.1f}%",
                "Year Built": random.randrange(1968, 2024),
                "Acquired": date(2015, 1, 1) + timedelta(days=random.randrange(3800)),
            }
        )
    pd.DataFrame(rows).to_excel(OUT / "real_estate_portfolio.xlsx", sheet_name="Portfolio", index=False)


def restaurant_pos() -> None:
    """High-volume daily POS export: revenue + discounts across stores."""
    stores = ["Downtown", "Airport", "Westside", "University"]
    categories = ["Entrees", "Beverages", "Desserts", "Appetizers"]
    start = date(2026, 1, 1)
    rows = []
    for day_offset in range(150):
        for store in stores:
            for category in categories:
                gross = random.uniform(300, 4200)
                rows.append(
                    {
                        "Date": start + timedelta(days=day_offset),
                        "Store": store,
                        "Category": category,
                        "Items Sold": random.randrange(25, 420),
                        "Gross Sales": money(gross),
                        "Discounts": money(gross * random.uniform(0.02, 0.11)),
                    }
                )
    pd.DataFrame(rows).to_excel(OUT / "restaurant_pos.xlsx", sheet_name="Daily Sales", index=False)


def pivot_wide_report() -> None:
    """Pivot-shaped data (months as columns) — the classic 'wrong shape' export.
    The bar is graceful handling: parse, profile, and a valid generic dashboard."""
    regions = ["West", "East", "Central", "South", "International"]
    months = [date(2026, m, 1).strftime("%b %Y") for m in range(1, 13)]
    rows = []
    for region in regions:
        row = {"Region": region}
        base = random.uniform(40_000, 120_000)
        for i, month in enumerate(months):
            row[month] = round(base * (1 + 0.02 * i) * (0.9 + random.random() * 0.2), 2)
        rows.append(row)
    with pd.ExcelWriter(OUT / "pivot_wide_report.xlsx", engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name="Revenue by Region", index=False)


def messy_ops_report() -> None:
    """The classic hand-exported mess: two banner rows above the table, the
    header on sheet row 4, currency strings with accounting negatives, a blank
    header cell, a duplicate column name, a Grand Total row, and a loose
    footnote two blank rows below the table."""
    sites = ["Northgate", "Riverside", "Elm Plaza", "Harbor Point", "Summit"]
    categories = ["HVAC", "Plumbing", "Electrical", "Janitorial", "Landscaping"]
    header = ["Work Order", "Site", "Category", "Cost", "Opened", "Status", "", "Cost"]
    grid: list[list] = [
        ["ACME FACILITIES — WORK ORDER EXPORT"] + [None] * 7,
        ["Generated 2026-06-30 by ops-suite v4.2"] + [None] * 7,
        [None] * 8,
        header,
    ]
    total = 0.0
    start = date(2026, 1, 5)
    for i in range(240):
        cost = random.choice([180, 240, 420, 660, 950, 1_400]) * (0.7 + random.random() * 0.8)
        refund = random.random() < 0.04
        total += -cost if refund else cost
        grid.append(
            [
                f"WO-{7000 + i}",
                random.choice(sites),
                random.choice(categories),
                f"(${cost:,.2f})" if refund else money(cost),
                mixed_date(start + timedelta(days=random.randrange(170)), random.randrange(3)),
                random.choices(["Closed", "Open", "In Progress"], [0.7, 0.18, 0.12])[0],
                random.choice(["Yes", None, None]),
                round(cost, 2),
            ]
        )
    grid.append(["Grand Total", None, None, money(total), None, None, None, None])
    grid.append([None] * 8)
    grid.append([None] * 8)
    grid.append(["Prepared by the facilities team — internal use only"] + [None] * 7)
    with pd.ExcelWriter(OUT / "messy_ops_report.xlsx", engine="openpyxl") as writer:
        pd.DataFrame(grid).to_excel(writer, sheet_name="Export", index=False, header=False)


def scattered_report() -> None:
    """Several tables scattered on single sheets: a small KPI block above the
    real table (two blank rows apart), and two tables side by side."""
    programs = ["Food Bank", "Youth Sports", "Adult Education", "Health Clinic"]
    channels = ["Online", "Mail", "Event", "Corporate"]
    start = date(2026, 1, 10)
    main: list[list] = [["Date", "Program", "Channel", "Amount"]]
    for _ in range(300):
        main.append(
            [
                (start + timedelta(days=random.randrange(160))).isoformat(),
                random.choice(programs),
                random.choice(channels),
                money(random.choice([25, 50, 100, 250, 500]) * (0.8 + random.random() * 0.6)),
            ]
        )
    kpi_block = [["Metric", "Value"], ["Report Year", 2026], ["Prepared By", "Development Office"]]
    sheet1 = kpi_block + [[None, None], [None, None]] + main

    left = [["Team", "Wins"]] + [[t, random.randrange(3, 20)] for t in ["North", "South", "East", "West", "Central", "Metro"]]
    right = [["Month", "Sessions"]] + [
        [date(2026, m, 1).strftime("%b %Y"), random.randrange(800, 2200)] for m in range(1, 7)
    ]
    sheet2 = [
        (left[i] if i < len(left) else [None, None]) + [None] + (right[i] if i < len(right) else [None, None])
        for i in range(max(len(left), len(right)))
    ]
    with pd.ExcelWriter(OUT / "scattered_report.xlsx", engine="openpyxl") as writer:
        pd.DataFrame(sheet1).to_excel(writer, sheet_name="Dashboard Data", index=False, header=False)
        pd.DataFrame(sheet2).to_excel(writer, sheet_name="Side By Side", index=False, header=False)


def euro_sales_csv() -> None:
    """A European export: semicolon delimiter, day-first dates, decimal commas
    with dot thousands separators, currency symbols, non-English headers."""
    kunden = ["Müller GmbH", "Schneider AG", "Fischer & Söhne", "Weber KG", "Becker SE"]
    regionen = ["Nord", "Süd", "Ost", "West"]
    lines = ["Datum;Kunde;Region;Umsatz;Menge"]
    start = date(2026, 1, 13)
    for _ in range(220):
        day = start + timedelta(days=random.randrange(160))
        amount = random.choice([950, 1_800, 3_600, 7_200, 12_500]) * (0.8 + random.random() * 0.5)
        euro = f"€ {amount:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
        lines.append(
            f"{day.strftime('%d.%m.%Y')};{random.choice(kunden)};"
            f"{random.choice(regionen)};{euro};{random.randrange(1, 40)}"
        )
    (OUT / "euro_sales.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sales_pipeline()
    ecommerce_orders()
    financial_statement()
    hr_roster()
    website_analytics()
    nonprofit_donations()
    inventory_snapshot()
    real_estate_portfolio()
    restaurant_pos()
    pivot_wide_report()
    messy_ops_report()
    scattered_report()
    euro_sales_csv()
    print("fixtures written to", OUT)

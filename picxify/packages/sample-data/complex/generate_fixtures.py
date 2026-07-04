"""Deterministic generator for the complex Excel eval fixtures.

Each workbook reproduces real-world mess: multi-sheet layouts with summary and
lookup tabs, currency strings (including accounting negatives), mixed date
formats, footer totals, blank rows, title rows above headers, and mostly-null
columns. Regenerate with:

    python packages/sample-data/complex/generate_fixtures.py
"""

import random
from datetime import date, timedelta
from io import BytesIO
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


def monthly_tabs() -> None:
    """One dataset split across six same-schema month tabs — the engine must
    combine them (they are disjoint) and analyze the whole year-to-date."""
    products = ["Starter", "Growth", "Scale", "Enterprise"]
    with pd.ExcelWriter(OUT / "monthly_tabs.xlsx", engine="openpyxl") as writer:
        for month in range(1, 7):
            rows = []
            for _ in range(random.randrange(60, 90)):
                day = date(2026, month, random.randrange(1, 28))
                units = random.randrange(1, 15)
                rows.append(
                    {
                        "Date": day.isoformat(),
                        "Product": random.choice(products),
                        "Units": units,
                        "Revenue": money(units * random.choice([49, 99, 249, 499])),
                    }
                )
            sheet = date(2026, month, 1).strftime("%b %Y")
            pd.DataFrame(rows).to_excel(writer, sheet_name=sheet, index=False)


def month_only_pivot() -> None:
    """Crosstab with month columns and NO year anywhere."""
    products = ["Espresso", "Filter", "Cold Brew", "Decaf", "Tea"]
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"]
    rows = []
    for product in products:
        row = {"Product": product}
        base = random.uniform(2_000, 9_000)
        for i, month in enumerate(months):
            row[month] = round(base * (0.9 + 0.05 * i) * (0.9 + random.random() * 0.2), 2)
        rows.append(row)
    with pd.ExcelWriter(OUT / "month_only_pivot.xlsx", engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name="Sales by Product", index=False)


def single_gap_scatter() -> None:
    """A lookup table and the real table separated by only ONE blank row —
    the header-after-blank rule must split them."""
    lookup = [["Code", "Meaning"], ["A", "Active"], ["C", "Cancelled"], ["P", "Pending"]]
    main: list[list] = [["Date", "Account", "Status Code", "Amount"]]
    start = date(2026, 2, 2)
    for i in range(180):
        main.append(
            [
                (start + timedelta(days=random.randrange(140))).isoformat(),
                f"AC-{1200 + i}",
                random.choice(["A", "C", "P"]),
                money(random.choice([120, 340, 780, 1_500]) * (0.8 + random.random() * 0.5)),
            ]
        )
    grid = lookup + [[None, None, None, None]] + main
    with pd.ExcelWriter(OUT / "single_gap_scatter.xlsx", engine="openpyxl") as writer:
        pd.DataFrame(grid).to_excel(writer, sheet_name="Ops Data", index=False, header=False)


def dirty_values_csv() -> None:
    """US-style export with placeholder nulls, accounting negatives, percent
    strings, and the header line repeated mid-file (page-break export)."""
    regions = ["West", "East", "Central", "South"]
    lines = ["Region,Month,Revenue,Discount"]
    for month in range(1, 7):
        for region in regions:
            revenue = random.choice([8_000, 12_000, 18_000, 26_000]) * (0.8 + random.random() * 0.5)
            refund = random.random() < 0.06
            rev = f'"({revenue:,.2f})"' if refund else f'"{revenue:,.2f}"'
            discount = random.choice(["N/A", "-", f"{random.randrange(2, 18)}%"])
            lines.append(f"{region},{date(2026, month, 1).strftime('%b %Y')},{rev},{discount}")
        if month == 3:
            lines.append("Region,Month,Revenue,Discount")  # repeated header
    (OUT / "dirty_values.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


# --- round 3: the scattered-data catalog -------------------------------------


def financial_pl_statement() -> None:
    """QuickBooks-style P&L: banner block, label column with section rows,
    month columns plus a Total column, mid-table Total Income/Total Expenses
    rows, and a Net Income line — all of which must not double-count."""
    months = [date(2026, m, 1).strftime("%b 2026") for m in range(1, 7)]
    income_lines = ["Consulting Revenue", "Retainer Fees", "Workshop Income"]
    expense_lines = ["Salaries", "Rent", "Software", "Travel", "Marketing"]

    def row(label, base):
        values = [round(base * (0.85 + random.random() * 0.3), 2) for _ in months]
        return [label, *values, round(sum(values), 2)]

    grid: list[list] = [
        ["Acme Consulting LLC"] + [None] * 7,
        ["Profit and Loss"] + [None] * 7,
        ["January - June 2026"] + [None] * 7,
        [None] * 8,
        [None, *months, "Total"],
        ["Income"] + [None] * 7,
    ]
    income_rows = [row(label, random.uniform(18_000, 40_000)) for label in income_lines]
    expense_rows = [row(label, random.uniform(4_000, 16_000)) for label in expense_lines]
    grid.extend(income_rows)
    grid.append(["Total Income", *[round(sum(r[i] for r in income_rows), 2) for i in range(1, 8)]])
    grid.append(["Expenses"] + [None] * 7)
    grid.extend(expense_rows)
    grid.append(["Total Expenses", *[round(sum(r[i] for r in expense_rows), 2) for i in range(1, 8)]])
    grid.append(
        [
            "Net Income",
            *[
                round(sum(r[i] for r in income_rows) - sum(r[i] for r in expense_rows), 2)
                for i in range(1, 8)
            ],
        ]
    )
    with pd.ExcelWriter(OUT / "financial_pl_statement.xlsx", engine="openpyxl") as writer:
        pd.DataFrame(grid).to_excel(writer, sheet_name="Profit and Loss", index=False, header=False)


def pivot_with_totals() -> None:
    """Crosstab with BOTH a Grand Total column and a Total row."""
    regions = ["West", "East", "Central", "South"]
    months = [date(2026, m, 1).strftime("%b 2026") for m in range(1, 7)]
    grid: list[list] = [["Region", *months, "Grand Total"]]
    column_sums = [0.0] * len(months)
    for region in regions:
        values = [round(random.uniform(20_000, 60_000), 2) for _ in months]
        for i, v in enumerate(values):
            column_sums[i] += v
        grid.append([region, *values, round(sum(values), 2)])
    grid.append(["Total", *[round(s, 2) for s in column_sums], round(sum(column_sums), 2)])
    with pd.ExcelWriter(OUT / "pivot_with_totals.xlsx", engine="openpyxl") as writer:
        pd.DataFrame(grid).to_excel(writer, sheet_name="Revenue by Region", index=False, header=False)


def grouped_merged_labels() -> None:
    """Vertically merged category labels: the group name appears once, blank
    for the rest of its group rows."""
    categories = {
        "Beverages": ["Espresso", "Latte", "Cold Brew", "Tea"],
        "Food": ["Croissant", "Bagel", "Salad", "Panini"],
        "Retail": ["Beans 1lb", "Mug", "Gift Card"],
    }
    grid: list[list] = [["Category", "Item", "Amount"]]
    for category, items in categories.items():
        for index, item in enumerate(items):
            grid.append(
                [category if index == 0 else None, item, money(random.uniform(800, 6_000))]
            )
    with pd.ExcelWriter(OUT / "grouped_merged_labels.xlsx", engine="openpyxl") as writer:
        pd.DataFrame(grid).to_excel(writer, sheet_name="Category Sales", index=False, header=False)


def units_row_report() -> None:
    """A units annotation row ('USD', 'count', '%') right under the header."""
    grid: list[list] = [
        ["Month", "Revenue", "Orders", "Refund Rate"],
        [None, "USD", "count", "%"],
    ]
    for m in range(1, 7):
        grid.append(
            [
                date(2026, m, 1).strftime("%b 2026"),
                round(random.uniform(30_000, 90_000), 2),
                random.randrange(200, 900),
                round(random.uniform(0.5, 4.0), 2),
            ]
        )
    with pd.ExcelWriter(OUT / "units_row_report.xlsx", engine="openpyxl") as writer:
        pd.DataFrame(grid).to_excel(writer, sheet_name="Monthly", index=False, header=False)


def transposed_metrics() -> None:
    """Fields as rows, one column per store — a transposed export."""
    stores = ["Store A", "Store B", "Store C", "Store D", "Store E", "Store F"]
    grid = [
        ["Metric", *stores],
        ["Revenue", *[round(random.uniform(80_000, 220_000), 2) for _ in stores]],
        ["Orders", *[random.randrange(900, 4_000) for _ in stores]],
        ["Manager", *["Kim", "Ray", "Ana", "Lee", "Sam", "Joy"]],
    ]
    with pd.ExcelWriter(OUT / "transposed_metrics.xlsx", engine="openpyxl") as writer:
        pd.DataFrame(grid).to_excel(writer, sheet_name="Store Metrics", index=False, header=False)


def serial_dates() -> None:
    """Order dates as raw Excel serial numbers (45000 ≈ 2023-03-15)."""
    rows = []
    base_serial = 46023  # 2026-01-01
    for i in range(200):
        rows.append(
            {
                "Order Date": base_serial + random.randrange(0, 170),
                "Channel": random.choice(["Web", "Store", "Phone"]),
                "Amount": round(random.uniform(40, 900), 2),
            }
        )
    with pd.ExcelWriter(OUT / "serial_dates.xlsx", engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name="Orders", index=False)


def compact_dates_csv() -> None:
    """Dates as YYYYMMDD integers."""
    lines = ["Created,Team,Sales"]
    for _ in range(180):
        month = random.randrange(1, 7)
        day = random.randrange(1, 28)
        lines.append(
            f"2026{month:02d}{day:02d},{random.choice(['North', 'South', 'East'])},"
            f"{random.uniform(500, 8000):.2f}"
        )
    (OUT / "compact_dates.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def currency_codes_csv() -> None:
    """ISO currency codes instead of symbols, Swiss apostrophe thousands, and
    compact k/M suffixes."""
    lines = ["Client,Amount,Fees,Pipeline Value"]
    for i in range(150):
        amount = f'"{random.uniform(900, 60000):,.2f} USD"'
        fees = f"{random.uniform(1000, 9000):,.2f}".replace(",", "'") + " CHF"
        pipeline = f"${random.choice([1.2, 2.5, 3.8, 0.9, 5.4])}M"
        lines.append(f"Client {i % 40},{amount},{fees},{pipeline}")
    (OUT / "currency_codes.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def bank_statement_csv() -> None:
    """Classic bank export: Debit and Credit as separate half-empty columns."""
    lines = ["Date,Description,Debit,Credit,Balance"]
    balance = 25_000.0
    start = date(2026, 1, 2)
    for i in range(160):
        day = start + timedelta(days=i)
        if random.random() < 0.55:
            debit = round(random.uniform(20, 2_400), 2)
            balance -= debit
            lines.append(f"{day.isoformat()},Payment {i},{debit},,{balance:.2f}")
        else:
            credit = round(random.uniform(500, 9_000), 2)
            balance += credit
            lines.append(f"{day.isoformat()},Deposit {i},,{credit},{balance:.2f}")
    (OUT / "bank_statement.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def pipe_export_txt() -> None:
    """Pipe-delimited .txt export."""
    lines = ["Date|Product|Region|Revenue"]
    start = date(2026, 1, 5)
    for _ in range(140):
        day = start + timedelta(days=random.randrange(160))
        lines.append(
            f"{day.isoformat()}|{random.choice(['Basic', 'Pro', 'Max'])}|"
            f"{random.choice(['NA', 'EMEA', 'APAC'])}|{random.uniform(200, 9000):.2f}"
        )
    (OUT / "pipe_export.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def csv_with_preamble() -> None:
    """Title and metadata lines above the real CSV header."""
    lines = [
        "Sales Export Report",
        "Generated: 2026-07-01 by reporting-suite",
        "Filters: region=All; period=H1",
        "",
        "Date,Region,Revenue",
    ]
    start = date(2026, 1, 5)
    for _ in range(150):
        day = start + timedelta(days=random.randrange(160))
        lines.append(
            f"{day.isoformat()},{random.choice(['West', 'East', 'North'])},"
            f"{random.uniform(300, 7000):.2f}"
        )
    (OUT / "csv_with_preamble.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def quoted_newlines_csv() -> None:
    """Quoted fields containing embedded newlines and commas."""
    lines = ["Date,Customer,Comment,Revenue"]
    start = date(2026, 2, 2)
    for i in range(120):
        day = start + timedelta(days=random.randrange(120))
        comment = f'"Follow-up needed,\nsee ticket #{1000 + i}"'
        lines.append(f"{day.isoformat()},Customer {i % 30},{comment},{random.uniform(100, 4000):.2f}")
    (OUT / "quoted_newlines.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def stock_prices_csv() -> None:
    """OHLC price data: 'Open' must read as a price, never email engagement,
    and prices must never be summed into a headline."""
    lines = ["Date,Open,High,Low,Close,Volume"]
    price = 42.0
    start = date(2026, 1, 2)
    for i in range(130):
        day = start + timedelta(days=i)
        drift = random.uniform(-1.5, 1.6)
        o = price
        c = max(5.0, price + drift)
        h = max(o, c) + random.uniform(0, 1.2)
        low = min(o, c) - random.uniform(0, 1.2)
        price = c
        lines.append(
            f"{day.isoformat()},{o:.2f},{h:.2f},{low:.2f},{c:.2f},{random.randrange(80_000, 900_000)}"
        )
    (OUT / "stock_prices.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def pdf_revenue_report() -> None:
    """A clean single-page PDF table export (a text-layer report, the kind a
    finance tool's 'Export to PDF' button produces)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

    rows = [["Region", "Month", "Revenue"]]
    for m in range(1, 5):
        month = date(2026, m, 1).strftime("%b 2026")
        for region in REGIONS:
            rows.append([region, month, money(random.uniform(8_000, 40_000))])
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    table = Table(rows)
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)]))
    doc.build([table])
    (OUT / "pdf_revenue_report.pdf").write_bytes(buffer.getvalue())


def pdf_multipage_orders() -> None:
    """A single long table pdfplumber can only see one page at a time — the
    engine must recombine the pages into one table."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

    rows = [["Order ID", "Customer", "Amount"]]
    for i in range(140):
        rows.append([f"O-{5000 + i}", f"Customer {i % 20}", money(random.uniform(50, 1_200))])
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    table = Table(rows, repeatRows=1)
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)]))
    doc.build([table])
    (OUT / "pdf_multipage_orders.pdf").write_bytes(buffer.getvalue())


def scanned_donation_summary() -> None:
    """An image-only PDF — no text layer at all, the shape of a scanned
    paper form. Exercises the OCR fallback path."""
    from PIL import Image, ImageDraw, ImageFont
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import Image as RLImage
    from reportlab.platypus import SimpleDocTemplate

    width, height = 1400, 900
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
    except OSError:
        font = ImageFont.load_default()
    programs = ["Food Bank", "Youth Sports", "Health Clinic", "Adult Education", "Senior Center"]
    rows = [("Program", "Amount")] + [
        (program, str(random.randrange(4_000, 22_000))) for program in programs
    ]
    for i, (left_cell, right_cell) in enumerate(rows):
        y = 60 + i * 80
        draw.text((80, y), left_cell, fill="black", font=font)
        draw.text((900, y), right_cell, fill="black", font=font)
    image_buffer = BytesIO()
    img.save(image_buffer, format="PNG")
    image_buffer.seek(0)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    doc.build([RLImage(image_buffer, width=500, height=500 * height // width)])
    (OUT / "scanned_donation_summary.pdf").write_bytes(buffer.getvalue())


def orders_customers_pair() -> None:
    """Two related CSVs meant to be uploaded together: orders.csv (a fact
    table, customer_id as a foreign key) and customers.csv (the dimension,
    customer_id unique) — proves the relational join candidate."""
    n_customers = 15
    customers = pd.DataFrame(
        {
            "customer_id": [f"C{i}" for i in range(n_customers)],
            "name": [f"Customer {i}" for i in range(n_customers)],
            "segment": random.choices(["SMB", "Mid-Market", "Enterprise"], k=n_customers),
        }
    )
    orders = pd.DataFrame(
        {
            "order_id": [f"O{i}" for i in range(250)],
            "customer_id": [f"C{random.randrange(n_customers)}" for _ in range(250)],
            "order_date": [
                (date(2026, 1, 5) + timedelta(days=random.randrange(160))).isoformat()
                for _ in range(250)
            ],
            "amount": [round(random.uniform(50, 2_000), 2) for _ in range(250)],
        }
    )
    customers.to_csv(OUT / "join_customers.csv", index=False)
    orders.to_csv(OUT / "join_orders.csv", index=False)


def uncalculated_formula_report() -> None:
    """A report-generation library wrote live formula cells for a computed
    column but never ran a calculation engine — the cells read as blank.
    Regions/channels are plain values so the rest of the table still
    analyzes; only the 'Total' column is affected."""
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Campaign Report"
    sheet.append(["Campaign", "Region", "Spend", "Multiplier", "Total"])
    start = date(2026, 1, 5)
    for i in range(160):
        row = 2 + i
        spend = round(random.uniform(200, 4_000), 2)
        sheet.append(
            [
                f"Campaign {i % 25}",
                random.choice(REGIONS),
                spend,
                round(random.uniform(1.05, 1.4), 2),
                f"=C{row}*D{row}",
            ]
        )
    workbook.save(OUT / "uncalculated_formula_report.xlsx")


def newline_headers_report() -> None:
    """Headers manually typed with Alt+Enter — a real habit in hand-built
    Excel reports ('Q1\\nRevenue' as one cell, not a merged two-row header)."""
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Quarterly"
    sheet.append(["Region", "Q1\nRevenue", "Q2\nRevenue", "Notes\nInternal"])
    for region in REGIONS:
        sheet.append(
            [
                region,
                round(random.uniform(40_000, 120_000), 2),
                round(random.uniform(40_000, 120_000), 2),
                "reviewed",
            ]
        )
    workbook.save(OUT / "newline_headers_report.xlsx")


def numeric_percent_csv() -> None:
    """A BI-tool export where percent columns are native numbers, never
    text — one column already 0-1 fractions, another as whole-number
    percents, both under unambiguous %/pct names."""
    lines = ["Region,Month,Conversion Pct,Growth %"]
    for m in range(1, 7):
        for region in REGIONS:
            conversion = round(random.uniform(0.02, 0.18), 4)  # already a fraction
            growth = round(random.uniform(-15, 40), 1)  # whole-number percent
            lines.append(f"{region},{date(2026, m, 1).strftime('%b 2026')},{conversion},{growth}")
    (OUT / "numeric_percent.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def ar_aging_snapshot() -> None:
    """A single-period AR-aging snapshot (every row shares one 'Period') with
    a 'Prepayments' currency column — a real report that tripped two engine
    bugs: 'Prepayments' misread as an 'owner' dimension (substring match on
    'rep'), and a constant date column still producing a fake weekly trend."""
    properties = [
        "Bluewater Bay", "Cedarlake", "Lakeshore", "West Lake", "Eden Prairie",
        "Overlook Village", "Gainesville", "McKinney", "Colonial Village",
        "Garden Village",
    ]
    operators = ["American House", "Claiborne", "Dial Senior Living", "Discovery"]
    rows = []
    for i, prop in enumerate(properties):
        rows.append(
            {
                "Operator": operators[i % len(operators)],
                "Property": prop,
                "Period": "May 2026",
                "0-30 Days": round(random.uniform(2_000, 40_000), 2),
                "31-60 Days": round(random.uniform(0, 15_000), 2),
                "61-90 Days": round(random.uniform(0, 8_000), 2),
                "Prepayments": round(random.uniform(0, 30_000), 2),
                "Credits": round(random.uniform(0, 20_000), 2),
                "Total AR": round(random.uniform(5_000, 90_000), 2),
                "Source Modified": (date(2026, 6, 8) + timedelta(days=i % 4)).isoformat(),
            }
        )
    df = pd.DataFrame(rows)
    df.to_excel(OUT / "ar_aging_snapshot.xlsx", sheet_name="AR Aging", index=False)


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
    monthly_tabs()
    month_only_pivot()
    single_gap_scatter()
    dirty_values_csv()
    financial_pl_statement()
    pivot_with_totals()
    grouped_merged_labels()
    units_row_report()
    transposed_metrics()
    serial_dates()
    compact_dates_csv()
    currency_codes_csv()
    bank_statement_csv()
    pipe_export_txt()
    csv_with_preamble()
    quoted_newlines_csv()
    stock_prices_csv()
    pdf_revenue_report()
    pdf_multipage_orders()
    scanned_donation_summary()
    orders_customers_pair()
    uncalculated_formula_report()
    newline_headers_report()
    numeric_percent_csv()
    ar_aging_snapshot()
    print("fixtures written to", OUT)

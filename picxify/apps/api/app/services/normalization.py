"""Table normalization: cleanup that must happen before profiling.

Every destructive or non-obvious transformation is recorded as a note so it can
surface as a data quality finding (SETUP.md §9.2/§9.4).
"""

import re
from dataclasses import dataclass, field

import pandas as pd

FOOTER_PATTERN = re.compile(
    r"^\s*((grand\s+)?(sub)?total[s]?\b|net\s+(income|profit|loss|revenue)\b)", re.IGNORECASE
)
# Covers "$1,234.56", "-$1,234", accounting negatives "($1,234.56)", and
# Swiss apostrophe thousands ("$1'234.56").
CURRENCY_PATTERN = re.compile(
    r"^\s*(-?[$€£]\s*[\d,']+(\.\d+)?|\(\s*[$€£]?\s*[\d,']+(\.\d+)?\s*\))\s*$"
)
PERCENT_PATTERN = re.compile(r"^\s*-?[\d,]+(\.\d+)?\s*%\s*$")
# Trailing minus ("1,234.56-") is SAP/accounting-export style.
NUMERIC_PATTERN = re.compile(r"^\s*-?[\d,']+(\.\d+)?\s*-?\s*$")
# "1234.56 USD" / "EUR 999" — ISO currency codes instead of symbols.
ISO_CODES = r"usd|eur|gbp|cad|aud|chf|jpy|inr|mxn|brl"
CODE_CURRENCY_PATTERN = re.compile(
    rf"^\s*(?:(?P<pre>{ISO_CODES})\s+)?-?[\d,'. ]+(?:\s*(?P<post>{ISO_CODES}))?\s*$",
    re.IGNORECASE,
)
# Compact magnitude suffixes: "$1.2M", "3.4k", "2B".
SUFFIX_NUMBER_PATTERN = re.compile(r"^\s*-?[$€£]?\s*\d+(\.\d+)?\s*[kKmMbB]\s*$")
SUFFIX_MULTIPLIERS = {"k": 1e3, "m": 1e6, "b": 1e9}
# European style: dot or space as thousands separator, comma as decimal
# ("1.234,56", "1 234,56"), optionally with a currency symbol and a trailing
# minus. Requires a comma-decimal or a separator group so it cannot swallow
# plain US-style numbers.
EURO_NUMERIC_PATTERN = re.compile(
    r"^\s*-?[$€£]?\s*(\d{1,3}([. ]\d{3})+(,\d+)?|\d+,\d+)\s*-?\s*$"
)

COERCION_THRESHOLD = 0.9  # fraction of non-null values that must parse


def _is_text_dtype(series: pd.Series) -> bool:
    # pandas 3.x uses a dedicated `str` dtype for string columns; older versions
    # (and mixed columns) use `object`. Treat both as text.
    return pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)


@dataclass
class TransformNote:
    finding_type: str
    severity: str
    message: str
    column: str | None = None
    meta: dict = field(default_factory=dict)


@dataclass
class NormalizedTable:
    dataframe: pd.DataFrame
    # column name -> "currency" | "percent" hint discovered during coercion
    type_hints: dict[str, str]
    notes: list[TransformNote]


def snake_case(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", str(name).strip()).strip("_").lower()
    return cleaned or "column"


def normalize_table(dataframe: pd.DataFrame, table_name: str | None = None) -> NormalizedTable:
    df = dataframe.copy()
    notes: list[TransformNote] = []
    type_hints: dict[str, str] = {}

    df = _drop_blank(df, notes)
    df = _dedupe_columns(df, notes)
    df = _drop_repeated_header_rows(df, notes)
    df = _drop_footer_rows(df, notes)
    df = _trim_strings(df)
    df = _null_placeholder_tokens(df, notes)
    df = _fill_grouped_labels(df, notes)
    df = _coerce_numeric_strings(df, notes, type_hints)
    df = _coerce_dates(df, notes)
    df = _coerce_serial_dates(df, notes)
    df = _unpivot_wide_periods(df, notes, table_name)
    df = _stringify_mixed_columns(df, notes)

    duplicate_rows = int(df.duplicated().sum())
    if duplicate_rows:
        notes.append(
            TransformNote(
                finding_type="duplicate_rows",
                severity="warning",
                message=f"Detected {duplicate_rows} fully duplicated row(s). They were kept.",
                meta={"count": duplicate_rows},
            )
        )

    return NormalizedTable(dataframe=df.reset_index(drop=True), type_hints=type_hints, notes=notes)


def _drop_blank(df: pd.DataFrame, notes: list[TransformNote]) -> pd.DataFrame:
    before_rows, before_cols = df.shape
    df = df.dropna(how="all").dropna(axis=1, how="all")
    dropped_rows = before_rows - df.shape[0]
    dropped_cols = before_cols - df.shape[1]
    if dropped_rows:
        notes.append(
            TransformNote(
                finding_type="blank_rows_removed",
                severity="info",
                message=f"Removed {dropped_rows} fully blank row(s).",
                meta={"count": dropped_rows},
            )
        )
    if dropped_cols:
        notes.append(
            TransformNote(
                finding_type="blank_columns_removed",
                severity="info",
                message=f"Removed {dropped_cols} fully blank column(s).",
                meta={"count": dropped_cols},
            )
        )
    return df


def _dedupe_columns(df: pd.DataFrame, notes: list[TransformNote]) -> pd.DataFrame:
    seen: dict[str, int] = {}
    new_names: list[str] = []
    renamed: list[str] = []
    for original in df.columns:
        name = str(original)
        if name in seen:
            seen[name] += 1
            new_name = f"{name}_{seen[name]}"
            renamed.append(name)
            new_names.append(new_name)
        else:
            seen[name] = 1
            new_names.append(name)
    if renamed:
        notes.append(
            TransformNote(
                finding_type="duplicate_columns_renamed",
                severity="info",
                message=f"Renamed duplicate column name(s): {', '.join(sorted(set(renamed)))}.",
                meta={"columns": sorted(set(renamed))},
            )
        )
    df.columns = new_names
    return df


def _drop_footer_rows(df: pd.DataFrame, notes: list[TransformNote]) -> pd.DataFrame:
    """Total/subtotal rows double-count their detail rows wherever they sit —
    financial statements carry them mid-table ('Total Income'), not just at
    the bottom."""
    if df.empty:
        return df
    first_column = df.columns[0]
    mask = df[first_column].map(
        lambda v: isinstance(v, str) and bool(FOOTER_PATTERN.match(v))
    )
    dropped = int(mask.sum())
    if dropped:
        df = df[~mask]
        notes.append(
            TransformNote(
                finding_type="footer_rows_removed",
                severity="info",
                message=(
                    f"Excluded {dropped} summary/total row(s) so they do not "
                    "double-count the detail rows."
                ),
                meta={"count": dropped},
            )
        )
    return df


def _trim_strings(df: pd.DataFrame) -> pd.DataFrame:
    for column in df.columns:
        if _is_text_dtype(df[column]):
            df[column] = df[column].map(lambda v: v.strip() if isinstance(v, str) else v)
            df[column] = df[column].replace({"": None})
    return df


# Cell values that mean "no data" in hand-made spreadsheets. Left in place they
# poison type detection (a numeric column with 'N/A's reads as text).
NULL_TOKENS = {"n/a", "na", "n.a.", "-", "--", "—", "–", "none", "null", "nil", "tbd", "?", "#n/a", "#ref!", "#div/0!", "#value!"}


def _null_placeholder_tokens(df: pd.DataFrame, notes: list[TransformNote]) -> pd.DataFrame:
    replaced: dict[str, int] = {}
    for column in df.columns:
        if not _is_text_dtype(df[column]):
            continue
        mask = df[column].map(
            lambda v: isinstance(v, str) and v.strip().lower() in NULL_TOKENS
        )
        count = int(mask.sum())
        if count:
            df.loc[mask, column] = None
            replaced[str(column)] = count
    if replaced:
        total = sum(replaced.values())
        notes.append(
            TransformNote(
                finding_type="placeholder_nulls",
                severity="info",
                message=(
                    f"Treated {total} placeholder value(s) (N/A, -, none, …) as missing "
                    f"in: {', '.join(sorted(replaced))}."
                ),
                meta={"columns": replaced},
            )
        )
    return df


def _drop_repeated_header_rows(df: pd.DataFrame, notes: list[TransformNote]) -> pd.DataFrame:
    """Page-break exports repeat the header line mid-table; drop rows whose
    non-null cells all equal their own column names."""
    if df.empty:
        return df
    names = {str(c).strip().lower() for c in df.columns}

    def is_header_echo(row) -> bool:
        values = [v for v in row.tolist() if not pd.isna(v)]
        if len(values) < 2:
            return False
        return all(isinstance(v, str) and v.strip().lower() in names for v in values)

    mask = df.apply(is_header_echo, axis=1)
    dropped = int(mask.sum())
    if dropped:
        df = df[~mask]
        notes.append(
            TransformNote(
                finding_type="repeated_header_rows_removed",
                severity="info",
                message=f"Removed {dropped} repeated header row(s) inside the data.",
                meta={"count": dropped},
            )
        )
    return df


def _coerce_numeric_strings(
    df: pd.DataFrame, notes: list[TransformNote], type_hints: dict[str, str]
) -> pd.DataFrame:
    for column in df.columns:
        if not _is_text_dtype(df[column]):
            continue
        values = df[column].dropna()
        strings = values[values.map(lambda v: isinstance(v, str))]
        if len(strings) == 0 or len(strings) < len(values):
            continue

        def has_iso_code(value: str) -> bool:
            match = CODE_CURRENCY_PATTERN.match(value)
            return bool(match and (match.group("pre") or match.group("post")))

        currency_ratio = strings.map(
            lambda v: bool(CURRENCY_PATTERN.match(v)) or has_iso_code(v)
        ).mean()
        percent_ratio = strings.map(lambda v: bool(PERCENT_PATTERN.match(v))).mean()
        suffix_ratio = strings.map(lambda v: bool(SUFFIX_NUMBER_PATTERN.match(v))).mean()
        numeric_ratio = strings.map(
            lambda v: bool(NUMERIC_PATTERN.match(v)) or bool(SUFFIX_NUMBER_PATTERN.match(v))
        ).mean()
        euro_ratio = strings.map(lambda v: bool(EURO_NUMERIC_PATTERN.match(v))).mean()
        euro_style = euro_ratio >= COERCION_THRESHOLD and euro_ratio > numeric_ratio

        def to_number(value):
            if not isinstance(value, str):
                return value
            value = value.replace("−", "-")  # unicode minus
            negative = bool(re.match(r"^\s*\(.*\)\s*$", value))  # accounting negatives
            stripped = value.strip()
            if stripped.endswith("-") and not stripped.startswith("-"):
                negative = True  # SAP-style trailing minus ("1,234.56-")
                value = stripped[:-1]
            multiplier = 1.0
            suffix = value.strip()[-1:].lower()
            if SUFFIX_NUMBER_PATTERN.match(value) and suffix in SUFFIX_MULTIPLIERS:
                multiplier = SUFFIX_MULTIPLIERS[suffix]  # "$1.2M" -> x1e6
                value = value.strip()[:-1]
            value = re.sub(rf"(?i)\b({ISO_CODES})\b", "", value)  # "1234.56 USD"
            if euro_style:
                # "1.234,56" / "1 234,56" -> "1234.56"
                value = value.replace(".", "").replace(" ", "").replace(",", ".")
            cleaned = re.sub(r"[$€£,'%\s()]", "", value)
            if cleaned in {"", "-"}:
                return None
            try:
                number = float(cleaned)
            except ValueError:
                # Coercion fires at >= 90% parseable; the stragglers (stray
                # headers, typos) become nulls rather than crashing the job.
                return None
            return (-number if negative else number) * multiplier

        if euro_style:
            has_symbol = strings.map(lambda v: bool(re.search(r"[$€£]", v))).mean() >= 0.5
            df[column] = df[column].map(to_number)
            if has_symbol:
                type_hints[column] = "currency"
            notes.append(
                TransformNote(
                    finding_type="type_converted",
                    severity="info",
                    message=(
                        f"Converted '{column}' from European-formatted text "
                        "(1.234,56) to numbers."
                    ),
                    column=column,
                    meta={"to": "currency" if has_symbol else "number", "style": "european"},
                )
            )
            continue

        if currency_ratio >= COERCION_THRESHOLD:
            df[column] = df[column].map(to_number)
            type_hints[column] = "currency"
            notes.append(
                TransformNote(
                    finding_type="type_converted",
                    severity="info",
                    message=f"Converted '{column}' from text to currency values.",
                    column=column,
                    meta={"to": "currency"},
                )
            )
        elif percent_ratio >= COERCION_THRESHOLD:
            # Stored uniformly as 0-1 fractions ("45%" -> 0.45) so percent
            # formatting downstream can always multiply by 100.
            df[column] = df[column].map(to_number).map(
                lambda v: None if v is None else v / 100.0
            )
            type_hints[column] = "percent"
            notes.append(
                TransformNote(
                    finding_type="type_converted",
                    severity="info",
                    message=f"Converted '{column}' from text to percent values (0-1 fractions).",
                    column=column,
                    meta={"to": "percent"},
                )
            )
        elif numeric_ratio >= COERCION_THRESHOLD:
            df[column] = df[column].map(to_number)
            if (
                suffix_ratio >= 0.5
                and strings.map(lambda v: bool(re.search(r"[$€£]", v))).mean() >= 0.5
            ):
                type_hints[column] = "currency"  # "$1.2M" style
            notes.append(
                TransformNote(
                    finding_type="type_converted",
                    severity="info",
                    message=f"Converted '{column}' from text to numbers.",
                    column=column,
                    meta={"to": type_hints.get(column, "number")},
                )
            )
    return df


DATE_NAME = re.compile(
    r"date|(^|_)day($|_)|created|opened|closed|updated|modified|timestamp", re.IGNORECASE
)


def _coerce_serial_dates(df: pd.DataFrame, notes: list[TransformNote]) -> pd.DataFrame:
    """Two numeric date encodings, only trusted on date-named columns:
    Excel serials (45000 ≈ 2023) and compact ISO ints (20260213)."""
    for column in df.columns:
        if not DATE_NAME.search(str(column)):
            continue
        if not pd.api.types.is_numeric_dtype(df[column]):
            continue
        values = df[column].dropna()
        if len(values) < 3:
            continue
        whole = (values % 1 == 0).mean() >= 0.99
        as_serial = ((values >= 20000) & (values <= 60000)).mean()
        as_compact = ((values >= 19000101) & (values <= 21001231)).mean()
        if whole and as_serial >= 0.95:
            df[column] = pd.to_datetime(
                df[column], unit="D", origin="1899-12-30", errors="coerce"
            )
            style = "Excel serial numbers"
        elif whole and as_compact >= 0.95:
            parsed = pd.to_datetime(
                df[column].dropna().astype(int).astype(str),
                format="%Y%m%d",
                errors="coerce",
            )
            if parsed.notna().mean() < COERCION_THRESHOLD:
                continue
            df[column] = pd.to_datetime(
                df[column].map(lambda v: None if pd.isna(v) else str(int(v))),
                format="%Y%m%d",
                errors="coerce",
            )
            style = "YYYYMMDD integers"
        else:
            continue
        notes.append(
            TransformNote(
                finding_type="dates_parsed",
                severity="info",
                message=f"Parsed '{column}' as dates ({style}).",
                column=str(column),
                meta={"style": style},
            )
        )
    return df


def _fill_grouped_labels(df: pd.DataFrame, notes: list[TransformNote]) -> pd.DataFrame:
    """Vertically merged category cells (a group label written once, blank for
    the rest of its group) arrive as NaN runs under each value. Fill them so
    every row keeps its group; only the leading label column is considered."""
    if df.empty or df.shape[1] < 2:
        return df
    column = df.columns[0]
    series = df[column]
    if not _is_text_dtype(series):
        return df
    null_ratio = series.isna().mean()
    non_null = series.dropna()
    if not (0.2 <= null_ratio <= 0.95):
        return df
    if pd.isna(series.iloc[0]) or non_null.nunique() < 2:
        return df
    # Real merged labels repeat blocks: distinctly fewer values than rows.
    if non_null.nunique() > len(df) * 0.5:
        return df
    filled = int(series.isna().sum())
    df[column] = series.ffill()
    notes.append(
        TransformNote(
            finding_type="grouped_labels_filled",
            severity="info",
            message=(
                f"'{column}' looks like a merged group-label column; carried "
                f"{filled} label(s) down to their group rows."
            ),
            column=str(column),
            meta={"filled": filled},
        )
    )
    return df


PERIOD_HEADER = re.compile(
    r"^\s*(?:(?P<year_only>(19|20)\d{2})|"
    r"q(?P<quarter>[1-4])\s*[-/ ]?\s*(?P<q_year>(19|20)\d{2})|"
    r"(?P<month>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-/ ,]+(?P<m_year>(19|20)\d{2})|"
    r"(?P<iso_year>(19|20)\d{2})-(?P<iso_month>0[1-9]|1[0-2])(?:-\d{2})?)\s*$",
    re.IGNORECASE,
)
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
MONTH_ONLY = re.compile(
    r"^\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*$", re.IGNORECASE
)
MIN_PERIOD_COLUMNS = 3


def _parse_period_header(name: str):
    """'Jan 2026' / '2026-01' / 'Q1 2026' / '2026' -> period start date."""
    match = PERIOD_HEADER.match(str(name))
    if not match:
        return None
    groups = match.groupdict()
    if groups["year_only"]:
        return pd.Timestamp(int(groups["year_only"]), 1, 1)
    if groups["quarter"]:
        return pd.Timestamp(int(groups["q_year"]), (int(groups["quarter"]) - 1) * 3 + 1, 1)
    if groups["month"]:
        return pd.Timestamp(int(groups["m_year"]), MONTHS.index(groups["month"].lower()) + 1, 1)
    return pd.Timestamp(int(groups["iso_year"]), int(groups["iso_month"]), 1)


def _unpivot_wide_periods(
    df: pd.DataFrame, notes: list[TransformNote], table_name: str | None
) -> pd.DataFrame:
    """Crosstab reports ('Region | Jan 2026 | Feb 2026 | ...') reshape into
    long form so trends and breakdowns work. Only fires when the period
    columns clearly dominate and hold numbers."""
    # A 'Total'/'Grand Total' column beside the period columns would
    # double-count every row once unpivoted.
    total_columns = [
        c for c in df.columns if isinstance(c, str) and FOOTER_PATTERN.match(c)
    ]
    periods = {c: _parse_period_header(c) for c in df.columns}
    period_columns = [c for c, parsed in periods.items() if parsed is not None]
    month_only = False
    if len(period_columns) < MIN_PERIOD_COLUMNS:
        # "Product | Jan | Feb | ... " with no year anywhere: still a
        # crosstab. Periods stay as month names (no invented dates).
        month_columns = [c for c in df.columns if MONTH_ONLY.match(str(c))]
        if len(month_columns) >= MIN_PERIOD_COLUMNS:
            period_columns, month_only = month_columns, True
    id_columns = [c for c in df.columns if c not in period_columns and c not in total_columns]
    if len(period_columns) < MIN_PERIOD_COLUMNS or len(id_columns) > 3:
        return df
    if total_columns:
        df = df.drop(columns=total_columns)
        notes.append(
            TransformNote(
                finding_type="total_columns_removed",
                severity="info",
                message=(
                    f"Excluded total column(s) {', '.join(map(str, total_columns))} "
                    "before reshaping so periods are not double-counted."
                ),
                meta={"columns": [str(c) for c in total_columns]},
            )
        )
    numeric_columns = sum(
        1 for c in period_columns if pd.api.types.is_numeric_dtype(df[c])
    )
    if numeric_columns < len(period_columns) * 0.8:
        return df

    value_name = _measure_name(table_name)
    melted = df.melt(
        id_vars=id_columns,
        value_vars=period_columns,
        var_name="Period",
        value_name=value_name,
    )
    if not month_only:
        melted["Period"] = melted["Period"].map(lambda c: periods[c])
    melted = melted.dropna(subset=[value_name]).reset_index(drop=True)
    notes.append(
        TransformNote(
            finding_type="wide_periods_unpivoted",
            severity="info",
            message=(
                f"Reshaped {len(period_columns)} period column(s) "
                f"({period_columns[0]} … {period_columns[-1]}) into rows so "
                "trends can be analyzed."
                + (
                    " Month columns carried no year, so periods stay as month names."
                    if month_only
                    else ""
                )
            ),
            meta={
                "periodColumns": [str(c) for c in period_columns],
                "valueColumn": value_name,
                "monthOnly": month_only,
            },
        )
    )
    return melted


def _measure_name(table_name: str | None) -> str:
    """'Revenue by Region' -> 'Revenue'; anything unhelpful -> 'Value'."""
    if table_name and " by " in table_name.lower():
        lowered = table_name.lower()
        candidate = table_name[: lowered.index(" by ")].strip()
        if candidate and len(candidate) <= 40:
            return candidate
    return "Value"


def _stringify_mixed_columns(df: pd.DataFrame, notes: list[TransformNote]) -> pd.DataFrame:
    """Columns still holding a mix of Python types after coercion (e.g. numbers
    plus the odd 'Yes') become consistent text. Mixed columns cannot be
    aggregated meaningfully and cannot be written to Parquet."""
    for column in df.columns:
        if not pd.api.types.is_object_dtype(df[column]):
            continue
        non_null = df[column].dropna()
        if non_null.empty:
            continue
        # int/float mixes are numbers, not "mixed types" — grid-based Excel
        # extraction leaves them as objects until infer_objects runs.
        kinds = {
            "number" if isinstance(value, (int, float)) and not isinstance(value, bool)
            else type(value).__name__
            for value in non_null
        }
        if len(kinds) > 1:
            df[column] = df[column].map(lambda v: None if pd.isna(v) else str(v))
            notes.append(
                TransformNote(
                    finding_type="mixed_types_normalized",
                    severity="warning",
                    message=(
                        f"'{column}' mixes value types ({', '.join(sorted(kinds))}); "
                        "treated as text."
                    ),
                    column=str(column),
                    meta={"types": sorted(kinds)},
                )
            )
    return df


def _coerce_dates(df: pd.DataFrame, notes: list[TransformNote]) -> pd.DataFrame:
    for column in df.columns:
        if not _is_text_dtype(df[column]):
            continue
        values = df[column].dropna()
        if len(values) == 0 or not all(isinstance(v, str) for v in values):
            continue
        # Cheap pre-filter: dates need a digit plus a real date separator or a
        # month name. Space alone is not enough — '20 Hours' is not a date.
        date_hint = re.compile(
            r"[-/:.]|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", re.IGNORECASE
        )
        looks_datey = values.map(
            lambda v: bool(re.search(r"\d", v)) and bool(date_hint.search(v))
        ).mean()
        if looks_datey < COERCION_THRESHOLD:
            continue
        parsed = pd.to_datetime(values, errors="coerce", format="mixed", dayfirst=False)
        dayfirst = False
        # European day-first dates ("13.02.2026"): retry when month-first fails.
        retry = pd.to_datetime(values, errors="coerce", format="mixed", dayfirst=True)
        if retry.notna().mean() > parsed.notna().mean():
            parsed, dayfirst = retry, True
        parse_ratio = parsed.notna().mean()
        if parse_ratio >= COERCION_THRESHOLD:
            df[column] = pd.to_datetime(
                df[column], errors="coerce", format="mixed", dayfirst=dayfirst
            )
            failed = int(len(values) - parsed.notna().sum())
            notes.append(
                TransformNote(
                    finding_type="dates_parsed",
                    severity="info" if failed == 0 else "warning",
                    message=(
                        f"Parsed '{column}' as dates"
                        + (" (day-first format)" if dayfirst else "")
                        + "."
                        + (f" {failed} value(s) could not be parsed." if failed else "")
                    ),
                    column=column,
                    meta={"unparsed": failed, "dayfirst": dayfirst},
                )
            )
    return df

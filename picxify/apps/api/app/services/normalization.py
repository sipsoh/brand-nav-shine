"""Table normalization: cleanup that must happen before profiling.

Every destructive or non-obvious transformation is recorded as a note so it can
surface as a data quality finding (SETUP.md §9.2/§9.4).
"""

import re
from dataclasses import dataclass, field

import pandas as pd

FOOTER_PATTERN = re.compile(r"^\s*(grand\s+)?(sub)?total[s]?\b", re.IGNORECASE)
CURRENCY_PATTERN = re.compile(r"^\s*-?[$€£]\s*[\d,]+(\.\d+)?\s*$")
PERCENT_PATTERN = re.compile(r"^\s*-?[\d,]+(\.\d+)?\s*%\s*$")
NUMERIC_PATTERN = re.compile(r"^\s*-?[\d,]+(\.\d+)?\s*$")

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


def normalize_table(dataframe: pd.DataFrame) -> NormalizedTable:
    df = dataframe.copy()
    notes: list[TransformNote] = []
    type_hints: dict[str, str] = {}

    df = _drop_blank(df, notes)
    df = _dedupe_columns(df, notes)
    df = _drop_footer_rows(df, notes)
    df = _trim_strings(df)
    df = _coerce_numeric_strings(df, notes, type_hints)
    df = _coerce_dates(df, notes)
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
    if df.empty:
        return df
    first_column = df.columns[0]
    dropped = 0
    # Walk up from the bottom; totals live in trailing rows.
    while len(df) > 0:
        value = df.iloc[-1][first_column]
        if isinstance(value, str) and FOOTER_PATTERN.match(value):
            df = df.iloc[:-1]
            dropped += 1
        else:
            break
    if dropped:
        notes.append(
            TransformNote(
                finding_type="footer_rows_removed",
                severity="info",
                message=f"Excluded {dropped} summary/total row(s) so they do not distort analysis.",
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

        currency_ratio = strings.map(lambda v: bool(CURRENCY_PATTERN.match(v))).mean()
        percent_ratio = strings.map(lambda v: bool(PERCENT_PATTERN.match(v))).mean()
        numeric_ratio = strings.map(lambda v: bool(NUMERIC_PATTERN.match(v))).mean()

        def to_number(value):
            if not isinstance(value, str):
                return value
            cleaned = re.sub(r"[$€£,%\s]", "", value)
            if cleaned in {"", "-"}:
                return None
            try:
                return float(cleaned)
            except ValueError:
                # Coercion fires at >= 90% parseable; the stragglers (stray
                # headers, typos) become nulls rather than crashing the job.
                return None

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
            df[column] = df[column].map(to_number)
            type_hints[column] = "percent"
            notes.append(
                TransformNote(
                    finding_type="type_converted",
                    severity="info",
                    message=f"Converted '{column}' from text to percent values.",
                    column=column,
                    meta={"to": "percent"},
                )
            )
        elif numeric_ratio >= COERCION_THRESHOLD:
            df[column] = df[column].map(to_number)
            notes.append(
                TransformNote(
                    finding_type="type_converted",
                    severity="info",
                    message=f"Converted '{column}' from text to numbers.",
                    column=column,
                    meta={"to": "number"},
                )
            )
    return df


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
        kinds = {type(value).__name__ for value in non_null}
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
        parse_ratio = parsed.notna().mean()
        if parse_ratio >= COERCION_THRESHOLD:
            df[column] = pd.to_datetime(df[column], errors="coerce", format="mixed")
            failed = int(len(values) - parsed.notna().sum())
            notes.append(
                TransformNote(
                    finding_type="dates_parsed",
                    severity="info" if failed == 0 else "warning",
                    message=(
                        f"Parsed '{column}' as dates."
                        + (f" {failed} value(s) could not be parsed." if failed else "")
                    ),
                    column=column,
                    meta={"unparsed": failed},
                )
            )
    return df

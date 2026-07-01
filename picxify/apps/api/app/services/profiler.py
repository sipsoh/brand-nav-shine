"""Column and table profiling (SETUP.md §9.3).

The profiles produced here are the compact representation the AI layer sees in
later milestones — the raw data itself never goes to a model.
"""

import math
import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

MAX_EXAMPLES = 5
MAX_SAMPLE_ROWS = 5
MAX_TOP_CATEGORIES = 5
ID_PATTERN = re.compile(r"(^|_)(id|key|uuid|code)$")


@dataclass
class ColumnProfile:
    name: str
    normalized_name: str
    detected_type: str
    role_hint: str
    nullable_ratio: float
    unique_ratio: float
    stats: dict
    examples: list
    confidence: float


@dataclass
class TableProfile:
    row_count: int
    column_count: int
    columns: list[ColumnProfile]
    sample_rows: list[dict]
    quality_penalty: float = 0.0
    findings: list[dict] = field(default_factory=list)


def json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if hasattr(value, "item"):  # numpy scalar
        return json_safe(value.item())
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def profile_table(df: pd.DataFrame, type_hints: dict[str, str]) -> TableProfile:
    from app.services.normalization import snake_case

    row_count = len(df)
    columns: list[ColumnProfile] = []
    findings: list[dict] = []
    penalty = 0.0

    # Normalized names must be unique even when snake_case collides.
    used_normalized: dict[str, int] = {}

    for name in df.columns:
        series = df[name]
        normalized = snake_case(name)
        if normalized in used_normalized:
            used_normalized[normalized] += 1
            normalized = f"{normalized}_{used_normalized[normalized]}"
        else:
            used_normalized[normalized] = 1

        null_ratio = float(series.isna().mean()) if row_count else 0.0
        non_null = series.dropna()
        unique_ratio = float(non_null.nunique() / len(non_null)) if len(non_null) else 0.0

        detected_type, confidence = _detect_type(name, series, type_hints)
        role_hint = _role_hint(detected_type, unique_ratio)
        stats = _column_stats(series, detected_type)
        examples = [json_safe(v) for v in non_null.head(MAX_EXAMPLES).tolist()]

        if null_ratio >= 0.4:
            findings.append(
                {
                    "finding_type": "missing_values",
                    "severity": "critical",
                    "column": str(name),
                    "message": f"{round(null_ratio * 100)}% of rows are missing '{name}'.",
                    "meta": {"null_ratio": round(null_ratio, 4)},
                }
            )
            penalty += 0.15
        elif null_ratio >= 0.1:
            findings.append(
                {
                    "finding_type": "missing_values",
                    "severity": "warning",
                    "column": str(name),
                    "message": f"{round(null_ratio * 100)}% of rows are missing '{name}'.",
                    "meta": {"null_ratio": round(null_ratio, 4)},
                }
            )
            penalty += 0.05

        columns.append(
            ColumnProfile(
                name=str(name),
                normalized_name=normalized,
                detected_type=detected_type,
                role_hint=role_hint,
                nullable_ratio=round(null_ratio, 4),
                unique_ratio=round(unique_ratio, 4),
                stats=stats,
                examples=examples,
                confidence=confidence,
            )
        )

    sample_rows = [
        {str(k): json_safe(v) for k, v in row.items()}
        for row in df.head(MAX_SAMPLE_ROWS).to_dict(orient="records")
    ]

    return TableProfile(
        row_count=row_count,
        column_count=len(df.columns),
        columns=columns,
        sample_rows=sample_rows,
        quality_penalty=penalty,
        findings=findings,
    )


def _detect_type(name: str, series: pd.Series, type_hints: dict[str, str]) -> tuple[str, float]:
    hint = type_hints.get(str(name))
    if hint in {"currency", "percent"}:
        return hint, 0.95

    non_null = series.dropna()
    if len(non_null) == 0:
        return "unknown", 0.3

    if pd.api.types.is_bool_dtype(series):
        return "boolean", 0.95
    if pd.api.types.is_datetime64_any_dtype(series):
        has_time = bool((non_null.dt.hour != 0).any() or (non_null.dt.minute != 0).any())
        return ("datetime" if has_time else "date"), 0.95
    if pd.api.types.is_integer_dtype(series):
        if _looks_like_id(name, series):
            return "id", 0.8
        return "integer", 0.95
    if pd.api.types.is_float_dtype(series):
        return "float", 0.9

    # object dtype
    unique_ratio = non_null.nunique() / len(non_null)
    lengths = non_null.map(lambda v: len(str(v)))
    if _looks_like_id(name, series):
        return "id", 0.75
    if unique_ratio <= 0.5 and lengths.mean() <= 40:
        return "category", 0.8
    if lengths.mean() > 60:
        return "text", 0.8
    if unique_ratio > 0.95:
        return "id" if lengths.mean() <= 24 else "text", 0.6
    return "category" if lengths.mean() <= 40 else "text", 0.6


def _looks_like_id(name: str, series: pd.Series) -> bool:
    non_null = series.dropna()
    if len(non_null) == 0:
        return False
    unique_ratio = non_null.nunique() / len(non_null)
    return bool(ID_PATTERN.search(str(name).lower())) and unique_ratio > 0.9


def _role_hint(detected_type: str, unique_ratio: float) -> str:
    if detected_type in {"date", "datetime"}:
        return "date"
    if detected_type in {"integer", "float", "currency", "percent"}:
        return "measure"
    if detected_type == "id":
        return "id"
    if detected_type == "text":
        return "text"
    if detected_type == "boolean" or detected_type == "category":
        return "dimension"
    return "ignored"


def _column_stats(series: pd.Series, detected_type: str) -> dict:
    non_null = series.dropna()
    if len(non_null) == 0:
        return {}
    if detected_type in {"integer", "float", "currency", "percent"}:
        return {
            "min": json_safe(non_null.min()),
            "max": json_safe(non_null.max()),
            "mean": json_safe(round(float(non_null.mean()), 4)),
            "median": json_safe(float(non_null.median())),
            "std": json_safe(round(float(non_null.std()), 4)) if len(non_null) > 1 else 0,
        }
    if detected_type in {"date", "datetime"}:
        return {"min": json_safe(non_null.min()), "max": json_safe(non_null.max())}
    if detected_type in {"category", "boolean", "id"}:
        top = non_null.astype(str).value_counts().head(MAX_TOP_CATEGORIES)
        return {"topValues": [{"value": k, "count": int(v)} for k, v in top.items()]}
    if detected_type == "text":
        lengths = non_null.map(lambda v: len(str(v)))
        return {
            "lengthMin": int(lengths.min()),
            "lengthMean": round(float(lengths.mean()), 1),
            "lengthMax": int(lengths.max()),
        }
    return {}

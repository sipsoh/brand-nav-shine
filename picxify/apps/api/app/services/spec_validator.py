"""DashboardSpec validation against the canonical schema plus Picxify's own
source-trace completeness rule (SETUP.md §7.1)."""

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

# services -> app -> api -> apps -> picxify root
SCHEMA_PATH = (
    Path(__file__).resolve().parents[4]
    / "packages"
    / "schemas"
    / "dashboard_spec.schema.json"
)


class SpecValidationError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors[:5]))


@lru_cache
def _validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_spec(spec: dict) -> None:
    errors = [
        f"{'/'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message}"
        for error in _validator().iter_errors(spec)
    ]
    if errors:
        raise SpecValidationError(errors)


def assert_source_traces(spec: dict) -> None:
    """Every KPI, chart, and insight must be traceable — schema marks traces
    optional on kpi/chart payloads, Picxify does not."""
    errors: list[str] = []
    for section in spec.get("sections", []):
        for widget in section.get("widgets", []):
            widget_type = widget.get("type")
            if widget_type == "kpi" and not (widget.get("kpi") or {}).get("sourceTrace"):
                errors.append(f"kpi widget '{widget.get('id')}' has no sourceTrace")
            if widget_type == "chart" and not (widget.get("chart") or {}).get("sourceTrace"):
                errors.append(f"chart widget '{widget.get('id')}' has no sourceTrace")
            if widget_type == "insight_card" and not (widget.get("insight") or {}).get(
                "sourceTrace"
            ):
                errors.append(f"insight widget '{widget.get('id')}' has no sourceTrace")
            if widget_type == "data_table" and not (widget.get("table") or {}).get(
                "sourceTrace"
            ):
                errors.append(f"data_table widget '{widget.get('id')}' has no sourceTrace")
    for insight in spec.get("insights", []):
        if not insight.get("sourceTrace"):
            errors.append(f"insight '{insight.get('id')}' has no sourceTrace")
    if errors:
        raise SpecValidationError(errors)

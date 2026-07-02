"""Semantic mapping (SETUP.md §9.5): infer what columns and datasets mean.

Two layers:
1. A deterministic heuristic mapper (name patterns + detected types) that always
   runs and always produces a result — keyless dev and CI use only this.
2. An optional LLM pass, schema-constrained, whose output is validated against
   the actual columns before it can override the heuristics. If the model
   references unknown columns or fails entirely, the heuristics stand.
"""

import json
import logging
import re
from dataclasses import dataclass, field

import jsonschema

from app.prompts.semantic_mapper_prompt import (
    OUTPUT_SCHEMA,
    PROMPT_VERSION,
    SEMANTIC_TYPES,
    SYSTEM_PROMPT,
    USE_CASES,
)
from app.services.llm import LLMClient, LLMUnavailable

logger = logging.getLogger(__name__)


@dataclass
class ColumnInput:
    name: str
    normalized_name: str
    detected_type: str
    role_hint: str | None
    unique_ratio: float | None
    examples: list


@dataclass
class TableInput:
    name: str
    columns: list[ColumnInput]


@dataclass
class MappedColumn:
    semantic_type: str
    role: str
    confidence: float


@dataclass
class SemanticMapping:
    use_case_candidates: list[dict]
    column_mappings: dict[str, MappedColumn]  # keyed by original column name
    assumptions: list[dict]
    prompt_version: str = PROMPT_VERSION
    used_llm: bool = False


# (semantic_type, name regex, required detected types or None for any)
NAME_RULES: list[tuple[str, str, set[str] | None]] = [
    ("revenue", r"revenue|deal_amount|amount|sales|income|arr|mrr|price|value", {"integer", "float", "currency"}),
    ("cost", r"spend|cost|budget|expense|cac|cpa", {"integer", "float", "currency"}),
    ("conversion", r"conversion|signup|lead|purchase|order", {"integer", "float"}),
    ("engagement", r"impression|click|view|visit|session|open", {"integer", "float"}),
    ("rating", r"rating|score|nps|csat|stars", {"integer", "float"}),
    ("duration", r"duration|elapsed|aging|time_spent|resolution_time|handle_time", {"integer", "float"}),
    ("campaign", r"campaign|ad_group|adset", None),
    ("channel", r"channel|source|medium|platform", None),
    ("stage", r"stage|pipeline", None),
    ("status", r"status|state", None),
    ("region", r"region|country|state|city|geo|location", None),
    ("customer", r"customer|client|respondent|user_name|contact", None),
    ("account", r"account|company|organization", None),
    ("owner", r"owner|rep|salesperson|agent|assignee", None),
    ("segment", r"segment|tier|plan|cohort", None),
    ("comment", r"comment|feedback|note|response|review|message|text", None),
    ("quantity", r"count|quantity|qty|units|seats", {"integer", "float"}),
]


def map_dataset(
    tables: list[TableInput],
    filename: str,
    user_hints: str | None = None,
    llm: LLMClient | None = None,
) -> SemanticMapping:
    heuristic = _heuristic_mapping(tables, filename)
    if llm is None:
        return heuristic

    try:
        raw = llm.complete_json(
            SYSTEM_PROMPT, _build_user_prompt(tables, filename, user_hints), OUTPUT_SCHEMA,
            schema_name="semantic_mapping",
        )
        jsonschema.validate(raw, OUTPUT_SCHEMA)
    except (LLMUnavailable, jsonschema.ValidationError) as error:
        logger.warning("Semantic mapper LLM unavailable/invalid; using heuristics: %s", error)
        return heuristic

    return _merge_llm_output(heuristic, raw, tables)


def _all_columns(tables: list[TableInput]) -> list[ColumnInput]:
    return [column for table in tables for column in table.columns]


def _heuristic_mapping(tables: list[TableInput], filename: str) -> SemanticMapping:
    mappings: dict[str, MappedColumn] = {}
    for column in _all_columns(tables):
        mapped = _map_column(column)
        if mapped is not None:
            mappings[column.name] = mapped

    use_cases = _detect_use_cases(mappings, filename)
    assumptions = _build_assumptions(mappings, use_cases, tables)
    return SemanticMapping(
        use_case_candidates=use_cases, column_mappings=mappings, assumptions=assumptions
    )


def _map_column(column: ColumnInput) -> MappedColumn | None:
    if column.detected_type in {"date", "datetime"}:
        return MappedColumn(semantic_type="date", role="date", confidence=0.95)
    if column.detected_type == "id":
        return MappedColumn(semantic_type="id", role="id", confidence=0.85)

    name = column.normalized_name
    for semantic_type, pattern, allowed_types in NAME_RULES:
        if re.search(pattern, name):
            if allowed_types is not None and column.detected_type not in allowed_types:
                continue
            role = _role_for(semantic_type, column)
            confidence = 0.85 if allowed_types else 0.75
            return MappedColumn(semantic_type=semantic_type, role=role, confidence=confidence)

    if column.detected_type in {"integer", "float", "currency", "percent"}:
        return MappedColumn(semantic_type="other", role="measure", confidence=0.5)
    if column.detected_type == "category":
        return MappedColumn(semantic_type="other", role="dimension", confidence=0.5)
    if column.detected_type == "text":
        return MappedColumn(semantic_type="comment", role="text", confidence=0.5)
    return None


def _role_for(semantic_type: str, column: ColumnInput) -> str:
    if semantic_type in {"revenue", "cost", "conversion", "engagement", "rating", "quantity",
                         "duration"}:
        return "measure"
    if semantic_type == "comment":
        return "text"
    if semantic_type == "date":
        return "date"
    if semantic_type == "id":
        return "id"
    return "dimension"


def _detect_use_cases(mappings: dict[str, MappedColumn], filename: str) -> list[dict]:
    types = {m.semantic_type for m in mappings.values()}
    rating_count = sum(1 for m in mappings.values() if m.semantic_type == "rating")
    column_names = " ".join(name.lower() for name in mappings)
    respondent_signal = "respondent" in column_names or "question" in column_names
    scores: dict[str, float] = {}

    if "cost" in types and ({"campaign", "channel"} & types):
        scores["marketing"] = 0.85 + (0.05 if "conversion" in types else 0.0)
    if ({"stage", "status"} & types) and "revenue" in types:
        scores["sales"] = 0.85
    if "comment" in types and (rating_count >= 2 or (rating_count >= 1 and respondent_signal)):
        scores["survey"] = 0.85
    elif rating_count >= 1 and "comment" in types and ({"channel", "status"} & types):
        scores["customer_feedback"] = 0.8
    elif "comment" in types and len(types) <= 4:
        scores["customer_feedback"] = 0.6
    if "revenue" in types and "cost" in types and "date" in types and "campaign" not in types:
        scores.setdefault("finance", 0.55)
    # Ticket/case-style operational data: ids + status + dates, no money signals.
    if (
        "status" in types
        and "id" in types
        and "date" in types
        and not ({"revenue", "cost", "rating"} & types)
    ):
        scores.setdefault("operations", 0.7)

    lowered = filename.lower()
    for keyword, use_case in [
        ("campaign", "marketing"),
        ("marketing", "marketing"),
        ("pipeline", "sales"),
        ("sales", "sales"),
        ("survey", "survey"),
        ("feedback", "customer_feedback"),
        ("finance", "finance"),
        ("ticket", "operations"),
        ("incident", "operations"),
    ]:
        if keyword in lowered and use_case in USE_CASES:
            scores[use_case] = min(0.95, scores.get(use_case, 0.5) + 0.1)

    if not scores:
        scores["generic"] = 0.5

    candidates = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:3]
    return [{"useCase": use_case, "confidence": round(conf, 2)} for use_case, conf in candidates]


def _build_assumptions(
    mappings: dict[str, MappedColumn], use_cases: list[dict], tables: list[TableInput]
) -> list[dict]:
    assumptions: list[dict] = []

    top = use_cases[0]
    assumptions.append(
        {
            "label": f"Detected this as a {top['useCase'].replace('_', ' ')} dataset.",
            "confidence": top["confidence"],
            "editable": True,
            "affected_columns": [],
        }
    )

    date_columns = [name for name, m in mappings.items() if m.semantic_type == "date"]
    if len(date_columns) > 1:
        assumptions.append(
            {
                "label": f"Assumed '{date_columns[0]}' is the primary timeline "
                f"(also found: {', '.join(date_columns[1:])}).",
                "confidence": 0.7,
                "editable": True,
                "affected_columns": date_columns,
            }
        )

    for name, mapping in mappings.items():
        if mapping.semantic_type in {"other", "id"}:
            continue
        if mapping.confidence < 0.85:
            assumptions.append(
                {
                    "label": f"Assumed '{name}' represents {mapping.semantic_type}.",
                    "confidence": mapping.confidence,
                    "editable": True,
                    "affected_columns": [name],
                }
            )
        if len(assumptions) >= 8:
            break

    return assumptions


def _build_user_prompt(
    tables: list[TableInput], filename: str, user_hints: str | None
) -> str:
    payload = {
        "fileName": filename,
        "userHints": user_hints,
        "tables": [
            {
                "name": table.name,
                "columns": [
                    {
                        "name": c.name,
                        "detectedType": c.detected_type,
                        "roleHint": c.role_hint,
                        "uniqueRatio": c.unique_ratio,
                        "examples": c.examples[:3],
                    }
                    for c in table.columns
                ],
            }
            for table in tables
        ],
    }
    return json.dumps(payload, default=str)


def _merge_llm_output(
    heuristic: SemanticMapping, raw: dict, tables: list[TableInput]
) -> SemanticMapping:
    known_columns = {c.name for c in _all_columns(tables)}

    mappings = dict(heuristic.column_mappings)
    for item in raw.get("columnMappings", []):
        if item["column"] not in known_columns:
            logger.warning("LLM mapped unknown column %r; dropped.", item["column"])
            continue
        if item["semanticType"] not in SEMANTIC_TYPES:
            continue
        mappings[item["column"]] = MappedColumn(
            semantic_type=item["semanticType"],
            role=item["role"],
            confidence=max(0.0, min(1.0, float(item["confidence"]))),
        )

    use_cases = [
        {"useCase": c["useCase"], "confidence": max(0.0, min(1.0, float(c["confidence"])))}
        for c in raw.get("useCaseCandidates", [])
        if c["useCase"] in USE_CASES
    ] or heuristic.use_case_candidates

    assumptions = [
        {
            "label": a["label"],
            "confidence": max(0.0, min(1.0, float(a["confidence"]))),
            "editable": bool(a.get("editable", True)),
            "affected_columns": [
                col for col in a.get("affectedColumns", []) if col in known_columns
            ],
        }
        for a in raw.get("assumptions", [])[:10]
    ] or heuristic.assumptions

    return SemanticMapping(
        use_case_candidates=use_cases,
        column_mappings=mappings,
        assumptions=assumptions,
        used_llm=True,
    )

"""Semantic mapper prompt (SETUP.md §10.1). Versioned in source control per §23.4."""

PROMPT_VERSION = "semantic_mapper_v1"

SYSTEM_PROMPT = """You are Picxify's semantic data mapper. Your job is to infer what a dataset represents using column profiles, sample rows, file names, sheet names, and user hints.

Rules:
- Return only valid JSON matching the provided schema.
- Do not calculate business metrics.
- Assign confidence scores between 0 and 1.
- Prefer uncertainty over overclaiming.
- Create editable assumptions for ambiguous mappings.
- Identify likely dashboard use cases: client_report, marketing, sales, survey, customer_feedback, finance, operations, investor_update, generic.
- Mark columns as measure, dimension, date, id, text, or ignored.
"""

USE_CASES = [
    "client_report",
    "marketing",
    "sales",
    "survey",
    "customer_feedback",
    "finance",
    "operations",
    "investor_update",
    "generic",
]

SEMANTIC_TYPES = [
    "revenue",
    "cost",
    "conversion",
    "engagement",
    "duration",
    "date",
    "customer",
    "account",
    "owner",
    "region",
    "status",
    "stage",
    "channel",
    "campaign",
    "segment",
    "rating",
    "comment",
    "quantity",
    "id",
    "other",
]

ROLES = ["measure", "dimension", "date", "id", "text", "ignored"]

OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["useCaseCandidates", "columnMappings", "assumptions"],
    "properties": {
        "useCaseCandidates": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["useCase", "confidence"],
                "properties": {
                    "useCase": {"type": "string", "enum": USE_CASES},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
        "columnMappings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["column", "semanticType", "role", "confidence"],
                "properties": {
                    "column": {"type": "string"},
                    "semanticType": {"type": "string", "enum": SEMANTIC_TYPES},
                    "role": {"type": "string", "enum": ROLES},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
        "assumptions": {
            "type": "array",
            "maxItems": 10,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["label", "confidence", "editable"],
                "properties": {
                    "label": {"type": "string", "maxLength": 300},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "editable": {"type": "boolean"},
                    "affectedColumns": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}

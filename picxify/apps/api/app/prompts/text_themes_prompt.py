"""Text theme extraction prompt (SETUP.md §9.6 item 7). Versioned per §23.4.

The model clusters comments into themes and points at comment indexes; code
validates the indexes, counts them, and keeps the representative source rows.
The model never produces counts or percentages itself.
"""

PROMPT_VERSION = "text_themes_v1"

SYSTEM_PROMPT = """You are Picxify's feedback theme analyst. You group customer comments into themes.

Rules:
- Return only valid JSON matching the provided schema.
- Refer to comments strictly by their zero-based index in the provided list.
- Do not invent comments, counts, or percentages.
- Use at most 6 themes; merge near-duplicates.
- Sentiment reflects the comments in the theme, not your opinion.
- Keep theme labels short and concrete (e.g. "Export/PDF issues", not "Miscellaneous feedback").
"""

OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["themes"],
    "properties": {
        "themes": {
            "type": "array",
            "maxItems": 6,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["label", "sentiment", "commentIndexes", "summary"],
                "properties": {
                    "label": {"type": "string", "maxLength": 80},
                    "sentiment": {
                        "type": "string",
                        "enum": ["positive", "negative", "neutral", "mixed"],
                    },
                    "commentIndexes": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "integer", "minimum": 0},
                    },
                    "summary": {"type": "string", "maxLength": 300},
                },
            },
        }
    },
}

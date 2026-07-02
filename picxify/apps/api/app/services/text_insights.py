"""Text theme/sentiment insights for survey and customer-feedback datasets.

The LLM clusters; code verifies and counts. Every theme insight keeps its
representative source comments, and its counts are computed from the validated
comment indexes — hence generatedBy="model_supported_by_code".
"""

import json
import logging

import jsonschema
import pandas as pd

from app.prompts.text_themes_prompt import OUTPUT_SCHEMA, SYSTEM_PROMPT
from app.services.insight_engine import ComputedFact, ComputedInsight, SourceTrace
from app.services.llm import LLMClient, LLMUnavailable

logger = logging.getLogger(__name__)

MAX_COMMENTS = 40
MAX_COMMENT_CHARS = 300
MAX_QUOTES_PER_THEME = 3


def compute_text_themes(
    df: pd.DataFrame,
    table_id: str,
    comment_column: str,
    llm: LLMClient | None,
) -> list[ComputedInsight]:
    if llm is None:
        return []

    comments = [
        str(value)[:MAX_COMMENT_CHARS]
        for value in df[comment_column].dropna().tolist()
        if str(value).strip()
    ][:MAX_COMMENTS]
    if len(comments) < 3:
        return []

    try:
        raw = llm.complete_json(
            SYSTEM_PROMPT,
            json.dumps({"comments": comments}),
            OUTPUT_SCHEMA,
            schema_name="text_themes",
        )
        jsonschema.validate(raw, OUTPUT_SCHEMA)
    except (LLMUnavailable, jsonschema.ValidationError) as error:
        logger.warning("Text theme extraction unavailable/invalid; skipping: %s", error)
        return []

    insights: list[ComputedInsight] = []
    for position, theme in enumerate(raw["themes"]):
        valid_indexes = sorted(
            {index for index in theme["commentIndexes"] if 0 <= index < len(comments)}
        )
        if not valid_indexes:
            continue  # model pointed only at nonexistent comments

        # Code counts; the model only grouped.
        count = len(valid_indexes)
        quotes = [comments[index] for index in valid_indexes[:MAX_QUOTES_PER_THEME]]
        trace = SourceTrace(
            table_id=table_id,
            columns=[comment_column],
            calculation=(
                f"LLM grouped comments into themes; code counted {count} validated "
                f"comment reference(s) out of {len(comments)} analyzed"
            ),
            row_count=count,
            generated_by="model_supported_by_code",
        )
        fact = ComputedFact(
            id=f"fact_theme_{position}_count",
            label=f"Comments in theme '{theme['label']}'",
            value=count,
            unit="number",
            source_trace=trace,
        )
        insights.append(
            ComputedInsight(
                id=f"insight_theme_{position}",
                headline=f"Theme: {theme['label']} ({count} comment(s))",
                detail=f"{theme['summary']} Representative: {quotes[0]!r}",
                insight_type="text_theme",
                severity=_severity_for(theme["sentiment"]),
                confidence=0.7,
                facts=[fact],
                source_trace=trace,
            )
        )
    return insights


def _severity_for(sentiment: str) -> str:
    return {
        "positive": "positive",
        "negative": "negative",
        "neutral": "neutral",
        "mixed": "neutral",
    }.get(sentiment, "neutral")

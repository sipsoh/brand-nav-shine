"""Structure-detection confidence (SETUP.md-adjacent): how much the parser had
to *guess* about a table's shape, as opposed to how clean its values are.

Distinct from `profile.quality_penalty` (nulls, duplicate rows, mixed types —
data cleanliness). This score answers "did we have to make a structural
judgment call to read this file at all" — no header row found, a layout we
had to flip, sheets we chose to combine. Low confidence is a signal to the
user to check "Sources & assumptions," not a reason to block the dashboard.
"""

from dataclasses import dataclass

from app.services.normalization import TransformNote

# One penalty per finding TYPE (not per occurrence) — a note already
# aggregates however many rows/columns it affected.
STRUCTURE_PENALTIES: dict[str, float] = {
    "no_header_detected": 0.45,  # no header row found at all; columns auto-named
    "table_transposed": 0.15,  # inferred a fields-as-rows layout flip
    "sheet_split_into_blocks": 0.08,  # guessed where one table ends and another begins
    "sheets_combined": 0.08,  # assumed several sheets are one dataset
    "mixed_types_normalized": 0.06,  # a column held inconsistent value types
    "wide_periods_unpivoted": 0.05,  # assumed a crosstab reshape
    "small_blocks_skipped": 0.05,
    "grouped_labels_filled": 0.04,
    "blank_headers_named": 0.04,
    "merged_header_flattened": 0.03,
    "repeated_header_rows_removed": 0.03,
    "total_columns_removed": 0.03,
    "duplicate_columns_renamed": 0.02,
    "units_row_skipped": 0.02,
    "banner_rows_skipped": 0.02,  # a well-understood, low-risk pattern
    "encoding_detected": 0.02,
    # OCR has no ground truth to check itself against — always flag for
    # review, even when the extraction happens to look clean.
    "table_from_ocr": 0.45,
    "table_from_pdf": 0.05,  # extracted from a PDF's text layer
    "relational_join_applied": 0.05,  # inferred a fact/dimension relationship
}


@dataclass
class ConfidenceResult:
    score: float
    reasons: list[str]  # human labels for the notes that most hurt the score


def compute_structure_confidence(notes: list[TransformNote]) -> ConfidenceResult:
    seen_types: dict[str, TransformNote] = {}
    for note in notes:
        if note.finding_type in STRUCTURE_PENALTIES and note.finding_type not in seen_types:
            seen_types[note.finding_type] = note
    penalty = sum(STRUCTURE_PENALTIES[t] for t in seen_types)
    score = max(0.0, min(1.0, 1.0 - penalty))
    reasons = [
        note.message
        for _, note in sorted(
            seen_types.items(), key=lambda kv: STRUCTURE_PENALTIES[kv[0]], reverse=True
        )
    ][:3]
    return ConfidenceResult(score=round(score, 4), reasons=reasons)


# Below this, the dashboard shows a visible "double-check this" banner.
LOW_CONFIDENCE_THRESHOLD = 0.6

import pytest

from app.services.confidence import LOW_CONFIDENCE_THRESHOLD, compute_structure_confidence
from app.services.normalization import TransformNote


def test_clean_table_scores_full_confidence():
    result = compute_structure_confidence([])
    assert result.score == 1.0
    assert result.reasons == []


def test_no_header_detected_is_the_biggest_penalty():
    result = compute_structure_confidence(
        [TransformNote("no_header_detected", "warning", "No header row was found.")]
    )
    assert result.score == pytest.approx(0.55)
    assert result.score < LOW_CONFIDENCE_THRESHOLD


def test_low_risk_notes_barely_move_the_score():
    result = compute_structure_confidence(
        [
            TransformNote("banner_rows_skipped", "info", "Skipped 2 banner row(s)."),
            TransformNote("encoding_detected", "info", "Read using latin-1."),
        ]
    )
    assert result.score >= LOW_CONFIDENCE_THRESHOLD
    assert result.score == pytest.approx(0.96)


def test_same_finding_type_only_penalized_once():
    notes = [TransformNote("banner_rows_skipped", "info", "x")] * 5
    result = compute_structure_confidence(notes)
    assert result.score == pytest.approx(0.98)


def test_reasons_ranked_by_severity():
    result = compute_structure_confidence(
        [
            TransformNote("banner_rows_skipped", "info", "banner"),
            TransformNote("table_transposed", "info", "transposed"),
            TransformNote("units_row_skipped", "info", "units"),
        ]
    )
    assert result.reasons[0] == "transposed"  # biggest penalty (0.15) first


def test_score_floors_at_zero_for_compounding_penalties():
    notes = [
        TransformNote("no_header_detected", "warning", "x"),
        TransformNote("table_transposed", "info", "x"),
        TransformNote("sheet_split_into_blocks", "info", "x"),
        TransformNote("sheets_combined", "info", "x"),
        TransformNote("mixed_types_normalized", "warning", "x"),
        TransformNote("wide_periods_unpivoted", "info", "x"),
        TransformNote("small_blocks_skipped", "info", "x"),
        TransformNote("grouped_labels_filled", "info", "x"),
        TransformNote("blank_headers_named", "info", "x"),
        TransformNote("merged_header_flattened", "info", "x"),
    ]
    result = compute_structure_confidence(notes)
    assert 0.0 <= result.score <= 1.0

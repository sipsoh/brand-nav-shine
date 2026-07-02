"""File parsing: bytes in, raw pandas DataFrames out.

CSV goes through DuckDB's auto-detection (delimiter, header, types) with an
encoding-fallback retry; Excel is read as a raw cell grid and run through
structure detection, because real-world sheets are messy: title banners above
the table, the header on row 5, several tables scattered on one sheet, merged
two-row headers, blank header cells. Every structural decision is recorded as
a note so it surfaces to the user as a data-quality finding.

Normalization and profiling happen downstream — this layer only extracts
well-formed tables.
"""

import re
import tempfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

import duckdb
import pandas as pd

from app.services.normalization import TransformNote


class ParseError(Exception):
    """User-facing parse failure ("We could not detect a table in this file.")."""


@dataclass
class RawTable:
    name: str
    dataframe: pd.DataFrame
    notes: list[TransformNote] = field(default_factory=list)


# --- entry points -----------------------------------------------------------


def parse_file(filename: str, data: bytes) -> list[RawTable]:
    extension = Path(filename).suffix.lower()
    if extension in {".csv", ".tsv", ".txt"}:
        return [parse_csv(filename, data)]
    if extension in {".xlsx", ".xls"}:
        return parse_excel(filename, data)
    raise ParseError(f"Unsupported file type: {extension or 'unknown'}.")


def parse_csv(filename: str, data: bytes) -> RawTable:
    if not data.strip():
        raise ParseError("The file is empty.")
    notes: list[TransformNote] = []
    dataframe = _duckdb_csv(data)
    if dataframe is None:
        # Not valid UTF-8 (or otherwise unreadable): try common encodings and
        # re-encode to UTF-8 before giving up.
        for encoding in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
            try:
                text = data.decode(encoding)
            except (UnicodeDecodeError, UnicodeError):
                continue
            dataframe = _duckdb_csv(text.encode("utf-8"))
            if dataframe is not None:
                notes.append(
                    TransformNote(
                        finding_type="encoding_detected",
                        severity="info",
                        message=f"File was read using {encoding} text encoding.",
                        meta={"encoding": encoding},
                    )
                )
                break
    if dataframe is None or (dataframe.empty and dataframe.columns.empty):
        raise ParseError("We could not detect a table in this file.")
    return RawTable(name=Path(filename).stem, dataframe=dataframe, notes=notes)


def _duckdb_csv(data: bytes) -> pd.DataFrame | None:
    # DuckDB's sniffer wants a real file path.
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=True) as handle:
        handle.write(data)
        handle.flush()
        connection = None
        try:
            connection = duckdb.connect()
            return connection.read_csv(handle.name).df()
        except duckdb.Error:
            return None
        finally:
            if connection is not None:
                connection.close()


def parse_excel(filename: str, data: bytes) -> list[RawTable]:
    try:
        # header=None: read the raw cell grid; structure detection finds the
        # real header rows, which are very often not on row 1.
        sheets = pd.read_excel(BytesIO(data), sheet_name=None, header=None)
    except Exception as error:
        raise ParseError("We could not read this spreadsheet.") from error

    tables: list[RawTable] = []
    for sheet_name, grid in sheets.items():
        if grid.dropna(how="all").empty:
            continue  # skip empty sheets
        tables.extend(extract_tables(sheet_name, grid))
    if not tables:
        raise ParseError("The spreadsheet has no sheets with data.")
    return tables


# --- sheet structure detection ---------------------------------------------

MAX_HEADER_SCAN_ROWS = 12
MIN_TABLE_ROWS = 2  # data rows, excluding the header
MIN_TABLE_COLS = 2
PERIOD_YEAR_RANGE = range(1900, 2101)


def extract_tables(sheet_name: str, grid: pd.DataFrame) -> list[RawTable]:
    """Split a raw sheet grid into tables: vertical blocks separated by >= 2
    blank rows, then side-by-side blocks separated by fully blank columns,
    then header detection within each block."""
    blocks = []
    for row_lo, row_hi in _vertical_blocks(grid):
        band = grid.iloc[row_lo:row_hi]
        for col_lo, col_hi in _horizontal_blocks(band):
            blocks.append(band.iloc[:, col_lo:col_hi])

    candidates: list[tuple[pd.DataFrame, list[TransformNote]]] = []
    skipped_small = 0
    for block in blocks:
        built = _table_from_block(block)
        if built is None:
            skipped_small += 1
            continue
        candidates.append(built)

    if not candidates:
        # Nothing qualified (e.g. a sheet holding one KPI cell): fall back to
        # the whole sheet with first-row headers so we never lose data.
        fallback = grid.dropna(how="all").reset_index(drop=True)
        header = [_header_cell(v, i) for i, v in enumerate(fallback.iloc[0])]
        body = fallback.iloc[1:].reset_index(drop=True)
        body.columns = header
        return [RawTable(name=sheet_name, dataframe=body.infer_objects(), notes=[])]

    multiple = len(candidates) > 1
    tables: list[RawTable] = []
    for index, (dataframe, notes) in enumerate(candidates):
        name = f"{sheet_name} (block {index + 1})" if multiple else sheet_name
        if multiple:
            notes = [
                TransformNote(
                    finding_type="sheet_split_into_blocks",
                    severity="info",
                    message=(
                        f"Sheet '{sheet_name}' holds {len(candidates)} separate data blocks; "
                        f"this table is block {index + 1}."
                    ),
                    meta={"blocks": len(candidates), "block": index + 1},
                ),
                *notes,
            ]
        if skipped_small and index == 0:
            notes.append(
                TransformNote(
                    finding_type="small_blocks_skipped",
                    severity="info",
                    message=(
                        f"Skipped {skipped_small} tiny block(s) of loose cells on "
                        f"sheet '{sheet_name}' (not table-shaped)."
                    ),
                    meta={"count": skipped_small},
                )
            )
        tables.append(RawTable(name=name, dataframe=dataframe, notes=notes))
    return tables


def _vertical_blocks(grid: pd.DataFrame) -> list[tuple[int, int]]:
    """Contiguous row ranges separated by runs of >= 2 fully blank rows.
    (A single blank row is common inside one table — grouped reports.)"""
    filled = grid.notna().any(axis=1).tolist()
    blocks: list[tuple[int, int]] = []
    start: int | None = None
    blanks = 0
    for index, has_data in enumerate(filled):
        if has_data:
            if start is None:
                start = index
            blanks = 0
        else:
            if start is not None:
                blanks += 1
                if blanks >= 2:
                    blocks.append((start, index - blanks + 1))
                    start, blanks = None, 0
    if start is not None:
        end = len(filled)
        while end > start and not filled[end - 1]:
            end -= 1
        blocks.append((start, end))
    return blocks


def _horizontal_blocks(band: pd.DataFrame) -> list[tuple[int, int]]:
    """Side-by-side tables: column ranges separated by fully blank columns.
    Only splits when both sides are at least two columns wide."""
    filled = band.notna().any(axis=0).tolist()
    ranges: list[tuple[int, int]] = []
    start: int | None = None
    for index, has_data in enumerate(filled):
        if has_data and start is None:
            start = index
        elif not has_data and start is not None:
            ranges.append((start, index))
            start = None
    if start is not None:
        ranges.append((start, len(filled)))
    if len(ranges) <= 1 or any(hi - lo < MIN_TABLE_COLS for lo, hi in ranges):
        # Not a confident split: keep the whole band together.
        lo = min((r[0] for r in ranges), default=0)
        hi = max((r[1] for r in ranges), default=band.shape[1])
        return [(lo, hi)]
    return ranges


def _table_from_block(block: pd.DataFrame) -> tuple[pd.DataFrame, list[TransformNote]] | None:
    block = block.reset_index(drop=True)
    block = block.dropna(axis=1, how="all")
    if block.shape[1] < MIN_TABLE_COLS:
        return None

    notes: list[TransformNote] = []
    width = block.shape[1]
    header_rows: tuple[int, ...] | None = None
    banner_rows: list[int] = []

    for index in range(min(MAX_HEADER_SCAN_ROWS, len(block))):
        row = block.iloc[index]
        cells = row.notna().sum()
        if cells == 0:
            continue
        if _is_header_row(row, width):
            # Merged-cell spans leave MANY gaps in the top header row (each
            # span covers several columns); when the row below is a dense
            # all-string label row, the two form one header ("Region | Q1
            # [span] | Q2 [span]" over "· | Revenue | Orders"). A single
            # blank header cell is NOT a span — data rows full of currency/
            # date strings must never be eaten as header labels.
            spans = row.isna().sum() >= max(2, int(width * 0.3))
            if (
                spans
                and index + 1 < len(block)
                and _is_stringy_label_row(block.iloc[index + 1], width)
            ):
                header_rows = (index, index + 1)
            else:
                header_rows = (index,)
            break
        # Sparse stringy row directly above a dense header row: also a
        # merged-cell two-row header.
        if index + 1 < len(block) and _is_merged_header_top(row, width):
            below = block.iloc[index + 1]
            if _is_header_row(below, width):
                header_rows = (index, index + 1)
                break
        if cells <= max(2, int(width * 0.34)):
            banner_rows.append(index)  # title/logo/export-stamp line
            continue
        break  # a dense non-header row: this block starts with data

    if header_rows is None:
        data = block
        columns = [f"column_{i + 1}" for i in range(width)]
        notes.append(
            TransformNote(
                finding_type="no_header_detected",
                severity="warning",
                message="No header row was found; columns were auto-named.",
                meta={"columns": columns},
            )
        )
    else:
        if banner_rows:
            notes.append(
                TransformNote(
                    finding_type="banner_rows_skipped",
                    severity="info",
                    message=(
                        f"Skipped {len(banner_rows)} title/banner row(s) above the table."
                    ),
                    meta={"count": len(banner_rows)},
                )
            )
        if len(header_rows) == 2:
            top = block.iloc[header_rows[0]].ffill()
            bottom = block.iloc[header_rows[1]]
            columns = [
                _join_header(top.iloc[i], bottom.iloc[i], i) for i in range(width)
            ]
            notes.append(
                TransformNote(
                    finding_type="merged_header_flattened",
                    severity="info",
                    message="Combined a two-row (merged-cell) header into single column names.",
                    meta={"rows": list(header_rows)},
                )
            )
        else:
            columns = [
                _header_cell(v, i) for i, v in enumerate(block.iloc[header_rows[0]])
            ]
        if header_rows[0] > 0 and not banner_rows:
            notes.append(
                TransformNote(
                    finding_type="header_detected",
                    severity="info",
                    message=f"Detected the header on sheet row {header_rows[0] + 1}.",
                    meta={"row": header_rows[0] + 1},
                )
            )
        unnamed = [c for c in columns if c.startswith("column_")]
        if unnamed:
            notes.append(
                TransformNote(
                    finding_type="blank_headers_named",
                    severity="info",
                    message=f"Named {len(unnamed)} blank header cell(s): {', '.join(unnamed)}.",
                    meta={"columns": unnamed},
                )
            )
        data = block.iloc[header_rows[-1] + 1 :]

    data = data.reset_index(drop=True)
    if len(data.dropna(how="all")) < MIN_TABLE_ROWS:
        return None
    data.columns = columns
    # The grid read leaves everything as object; give numeric/datetime columns
    # their real dtypes so downstream profiling sees them.
    return data.infer_objects(), notes


def _is_header_row(row: pd.Series, width: int) -> bool:
    values = [v for v in row.tolist() if not pd.isna(v)]
    if len(values) < max(MIN_TABLE_COLS, int(width * 0.6)):
        return False
    strings = [v for v in values if isinstance(v, str) and v.strip()]
    if len(strings) >= len(values) * 0.5:
        return True
    # Crosstab headers ("Region | 2024 | 2025 | 2026" or month columns) are
    # mostly non-string but read as periods.
    period_cells = sum(1 for v in values if _looks_like_period(v))
    return len(strings) >= 1 and period_cells >= 3


def _is_merged_header_top(row: pd.Series, width: int) -> bool:
    values = [v for v in row.tolist() if not pd.isna(v)]
    if not (2 <= len(values) <= max(2, int(width * 0.7))):
        return False
    return all(isinstance(v, str) and v.strip() for v in values)


def _is_stringy_label_row(row: pd.Series, width: int) -> bool:
    """A dense, almost-entirely-string row — the bottom half of a merged
    header. The high string bar keeps real data rows (ids + numbers) out."""
    values = [v for v in row.tolist() if not pd.isna(v)]
    if len(values) < max(MIN_TABLE_COLS, int(width * 0.6)):
        return False
    strings = [v for v in values if isinstance(v, str) and v.strip()]
    return len(strings) >= len(values) * 0.8


def _looks_like_period(value) -> bool:
    import numbers

    if isinstance(value, numbers.Number) and not isinstance(value, bool):
        number = float(value)
        return number.is_integer() and int(number) in PERIOD_YEAR_RANGE
    if isinstance(value, str):
        return bool(
            re.match(
                r"^\s*((19|20)\d{2}|q[1-4]\s*[-/ ]?\s*(19|20)\d{2}|"
                r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-/ ,]*((19|20)\d{2})?)\s*$",
                value,
                re.IGNORECASE,
            )
        )
    return hasattr(value, "year")  # datetime-like header cells


def _header_cell(value, index: int) -> str:
    if pd.isna(value) or str(value).strip() == "":
        return f"column_{index + 1}"
    if hasattr(value, "strftime"):  # datetime header cells: keep them readable
        return value.strftime("%Y-%m-%d")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _join_header(top, bottom, index: int) -> str:
    top_text = "" if pd.isna(top) else str(top).strip()
    bottom_text = "" if pd.isna(bottom) else str(bottom).strip()
    if top_text and bottom_text and top_text.lower() != bottom_text.lower():
        return f"{top_text} {bottom_text}"
    return bottom_text or top_text or f"column_{index + 1}"

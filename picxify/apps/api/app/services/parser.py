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


def add_union_candidates(tables: list[RawTable]) -> list[RawTable]:
    """Workbooks often split ONE dataset across many same-schema sheets
    (per-month tabs, per-region tabs). When >= 3 sheets share an identical
    column signature, add a combined table with a 'Source Sheet' column as an
    extra candidate — table scoring decides whether it becomes the dashboard
    base. Original tables are always kept."""
    groups: dict[tuple, list[RawTable]] = {}
    for table in tables:
        signature = tuple(str(c) for c in table.dataframe.columns)
        if len(signature) >= 2:
            groups.setdefault(signature, []).append(table)

    combined: list[RawTable] = []
    for signature, members in groups.items():
        if len(members) < 3 or "Source Sheet" in signature:
            continue
        # Master-plus-filtered-views workbooks (a 'Tickets' sheet and per-
        # category tabs holding the SAME rows) must not be double-counted:
        # only disjoint slices union safely.
        bare = pd.concat([m.dataframe for m in members], ignore_index=True)
        try:
            duplicate_ratio = float(bare.duplicated().mean())
        except TypeError:  # unhashable cells: play safe, skip the union
            continue
        if duplicate_ratio > 0.02:
            continue
        frames = []
        for member in members:
            frame = member.dataframe.copy()
            frame.insert(0, "Source Sheet", member.name)
            frames.append(frame)
        union = pd.concat(frames, ignore_index=True)
        names = [m.name for m in members]
        combined.append(
            RawTable(
                name=f"Combined ({len(members)} sheets)",
                dataframe=union,
                notes=[
                    TransformNote(
                        finding_type="sheets_combined",
                        severity="info",
                        message=(
                            f"{len(members)} sheets share the same columns and were "
                            f"also combined into one table ({', '.join(names[:6])}"
                            + ("…" if len(names) > 6 else "")
                            + "). A 'Source Sheet' column says where each row came from."
                        ),
                        meta={"sheets": names},
                    )
                ],
            )
        )
    return tables + combined


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
            blocks.extend(_split_on_new_header(band.iloc[:, col_lo:col_hi]))

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


def _split_on_new_header(block: pd.DataFrame) -> list[pd.DataFrame]:
    """A single blank row inside a block usually separates groups WITHIN one
    table — but when the row after the blank looks like a fresh header, it is
    a new table. Grouped reports are safe: their continuation rows are data,
    not header-shaped."""
    block = block.reset_index(drop=True)
    width = block.shape[1]
    filled = block.notna().any(axis=1).tolist()
    cut_points: list[int] = []
    for index in range(2, len(block) - MIN_TABLE_ROWS):
        if (
            not filled[index - 1]
            and filled[index]
            and _is_label_only_header(block.iloc[index], width)
            and sum(filled[:index]) >= MIN_TABLE_ROWS
        ):
            cut_points.append(index)
    if not cut_points:
        return [block]
    pieces: list[pd.DataFrame] = []
    previous = 0
    for cut in cut_points:
        pieces.append(block.iloc[previous:cut])
        previous = cut
    pieces.append(block.iloc[previous:])
    return pieces


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
            # span covers several columns); while that is true and the row
            # below is a dense all-string label row, absorb it into the
            # header ("Region | Q1 [span] | Q2 [span]" over "· | Revenue |
            # Orders"), up to three rows deep. A single blank header cell is
            # NOT a span — data rows full of currency/date strings must
            # never be eaten as header labels.
            rows = [index]
            while (
                len(rows) < 3
                and block.iloc[rows[-1]].isna().sum() >= max(2, int(width * 0.3))
                and rows[-1] + 1 < len(block)
                and _is_stringy_label_row(block.iloc[rows[-1] + 1], width)
            ):
                rows.append(rows[-1] + 1)
            header_rows = tuple(rows)
            break
        # A run of sparse stringy rows directly above a dense header row:
        # a stacked merged-cell header (up to three levels).
        if _is_merged_header_top(row, width):
            run = [index]
            while (
                len(run) < 2
                and run[-1] + 1 < len(block)
                and _is_merged_header_top(block.iloc[run[-1] + 1], width)
            ):
                run.append(run[-1] + 1)
            below = run[-1] + 1
            if below < len(block) and _is_header_row(block.iloc[below], width):
                header_rows = (*run, below)
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
        if len(header_rows) > 1:
            # Span rows forward-fill across their merged range; the bottom
            # row holds the leaf labels as-is.
            levels = [block.iloc[r].ffill() for r in header_rows[:-1]]
            levels.append(block.iloc[header_rows[-1]])
            columns = [
                _join_header([level.iloc[i] for level in levels], i)
                for i in range(width)
            ]
            notes.append(
                TransformNote(
                    finding_type="merged_header_flattened",
                    severity="info",
                    message=(
                        f"Combined a {len(header_rows)}-row (merged-cell) header "
                        "into single column names."
                    ),
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


DATA_STRING = re.compile(
    r"^\s*([$€£(]|-?[\d,. ]+[%)-]?\s*$|\d{1,4}[-/.]\d{1,2}([-/.]\d{1,4})?)"
)


def _is_label_only_header(row: pd.Series, width: int) -> bool:
    """The strict header test used for SPLITTING a block at a single blank
    row: every cell must read as a label. Data rows full of ids, currency,
    or date strings must never trigger a split of a grouped report."""
    if not _is_header_row(row, width):
        return False
    values = [v for v in row.tolist() if not pd.isna(v)]
    strings = [v for v in values if isinstance(v, str)]
    non_strings = [v for v in values if not isinstance(v, str)]
    if any(not _looks_like_period(v) for v in non_strings):
        return False  # raw numbers that are not year/period headers -> data
    return not any(DATA_STRING.match(v) for v in strings)


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


def _join_header(parts: list, index: int) -> str:
    texts: list[str] = []
    for part in parts:
        text = "" if pd.isna(part) else str(part).strip()
        if text and (not texts or texts[-1].lower() != text.lower()):
            texts.append(text)
    return " ".join(texts) or f"column_{index + 1}"

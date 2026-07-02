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

import logging
import re
import tempfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

import duckdb
import pandas as pd

from app.services.normalization import TransformNote

logger = logging.getLogger(__name__)


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
    if extension == ".pdf":
        tables = parse_pdf(filename, data)
        if not tables:
            tables = parse_pdf_with_ocr(filename, data)
        if not tables:
            raise ParseError("We could not detect a table in this PDF.")
        return tables
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
    dataframe, skipped = _skip_csv_preamble(data, dataframe)
    if skipped:
        notes.append(
            TransformNote(
                finding_type="banner_rows_skipped",
                severity="info",
                message=f"Skipped {skipped} title/metadata line(s) above the CSV header.",
                meta={"count": skipped},
            )
        )
    return RawTable(name=Path(filename).stem, dataframe=dataframe, notes=notes)


def _skip_csv_preamble(data: bytes, parsed: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Report exports often stack title/metadata lines above the real header
    ("Sales Report,,\\nExported 2026-07-01,,\\n"). The sniffer then reads one
    wide column or a mangled header. Retry skipping 1-6 lines and keep the
    parse that yields the most real columns."""
    best, best_skip = parsed, 0

    def score(frame: pd.DataFrame) -> tuple[int, int]:
        named = sum(1 for c in frame.columns if not str(c).startswith("column"))
        return frame.shape[1], named

    if parsed.shape[1] >= 2 and score(parsed)[1] >= parsed.shape[1] * 0.6:
        return parsed, 0  # already clean
    for skip in range(1, 7):
        candidate = _duckdb_csv(data, skiprows=skip)
        if candidate is None or candidate.empty:
            continue
        if score(candidate) > score(best):
            best, best_skip = candidate, skip
    return best, best_skip


def _duckdb_csv(data: bytes, skiprows: int = 0) -> pd.DataFrame | None:
    # DuckDB's sniffer wants a real file path.
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=True) as handle:
        handle.write(data)
        handle.flush()
        connection = None
        try:
            connection = duckdb.connect()
            if skiprows:
                return connection.read_csv(handle.name, skiprows=skiprows).df()
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


def parse_pdf(filename: str, data: bytes) -> list[RawTable]:
    """Extract tables from a PDF's text layer, page by page. Each page's
    table becomes a raw grid fed through the same `extract_tables()`
    structure detector Excel uses — banners, header detection, and merged
    headers all apply for free. A long table pdfplumber can only see one page
    at a time comes back together automatically: same-schema page tables get
    recombined by `add_union_candidates` downstream, exactly like per-month
    Excel tabs.

    Pages with no extractable table AND no extractable text are scanned
    images; `parse_pdf_with_ocr` (used by dataset_pipeline when this returns
    nothing but the file has pages) picks those up via OCR.
    """
    import pdfplumber

    try:
        pdf = pdfplumber.open(BytesIO(data))
    except Exception as error:
        raise ParseError("We could not read this PDF.") from error

    tables: list[RawTable] = []
    try:
        for page_number, page in enumerate(pdf.pages, start=1):
            page_tables = page.extract_tables()
            for table_index, raw_rows in enumerate(page_tables, start=1):
                grid = _pdf_table_to_grid(raw_rows)
                if grid is None:
                    continue
                label = (
                    f"Page {page_number}"
                    if len(page_tables) == 1
                    else f"Page {page_number} table {table_index}"
                )
                extracted = extract_tables(label, grid)
                for table in extracted:
                    table.notes.append(
                        TransformNote(
                            finding_type="table_from_pdf",
                            severity="info",
                            message=f"Extracted from the PDF's text layer ({label}).",
                            meta={"page": page_number},
                        )
                    )
                tables.extend(extracted)
    finally:
        pdf.close()

    # Combining same-schema page tables (a table pdfplumber can only see one
    # page at a time) happens once, centrally, in dataset_pipeline — the same
    # place per-sheet Excel tabs get combined.
    return tables


def count_pdf_pages(data: bytes) -> int:
    import pdfplumber

    with pdfplumber.open(BytesIO(data)) as pdf:
        return len(pdf.pages)


def _ocr_available() -> bool:
    import pytesseract

    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


OCR_RESOLUTION = 200
OCR_MIN_CONFIDENCE = 20  # tesseract's 0-100 per-word confidence


def parse_pdf_with_ocr(filename: str, data: bytes) -> list[RawTable]:
    """Scanned pages have no text layer at all — `parse_pdf` finds nothing on
    them. Render each such page to an image and reconstruct a grid from
    tesseract's word-level bounding boxes (rows by line, columns by
    x-position clustering), then run it through the same structure detector
    everything else uses. OCR is inherently less reliable, so every table
    this produces carries an extra confidence penalty (`table_from_ocr`).

    Never raises: an environment without tesseract, or a page OCR can't make
    sense of, degrades to "no tables from this page," not a crash.
    """
    if not _ocr_available():
        return []
    import pdfplumber

    tables: list[RawTable] = []
    try:
        with pdfplumber.open(BytesIO(data)) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                if (page.extract_text() or "").strip():
                    continue  # has a real text layer; parse_pdf already covers it
                grid = _ocr_page_to_grid(page)
                if grid is None:
                    continue
                label = f"Page {page_number} (scanned)"
                extracted = extract_tables(label, grid)
                for table in extracted:
                    table.notes.append(
                        TransformNote(
                            finding_type="table_from_ocr",
                            severity="warning",
                            message=(
                                f"Extracted via OCR from a scanned page ({label}) — "
                                "double-check these values."
                            ),
                            meta={"page": page_number},
                        )
                    )
                tables.extend(extracted)
    except Exception:
        logger.exception("OCR extraction failed for %s; returning partial results.", filename)
    return tables


def _ocr_page_to_grid(page) -> pd.DataFrame | None:
    import pytesseract
    from pytesseract import Output

    image = page.to_image(resolution=OCR_RESOLUTION).original
    ocr = pytesseract.image_to_data(image, output_type=Output.DATAFRAME)
    words = ocr[ocr["text"].notna()].copy()
    words["conf"] = pd.to_numeric(words["conf"], errors="coerce")
    words = words[(words["conf"] > OCR_MIN_CONFIDENCE) & (words["text"].str.strip() != "")]
    if words.empty:
        return None

    # Rows by y-position, not tesseract's own (block, paragraph, line)
    # grouping: a wide gutter between columns makes tesseract's page
    # segmentation see two separate vertical "blocks," which would put an
    # entire column's words before the other column's instead of row by row.
    median_height = words["height"].median() or 20
    row_tolerance = median_height * 0.6
    by_top = words.sort_values("top")
    row_groups: list[list[int]] = []
    row_tops: list[float] = []
    for idx, top in zip(by_top.index, by_top["top"]):
        if row_groups and abs(top - row_tops[-1]) <= row_tolerance:
            row_groups[-1].append(idx)
            row_tops[-1] = words.loc[row_groups[-1], "top"].mean()
        else:
            row_groups.append([idx])
            row_tops.append(float(top))

    # Columns: cluster word left-edges by gap — a real column break shows up
    # as a much bigger horizontal gap than the space between words in a cell.
    lefts = sorted(words["left"].tolist())
    median_width = words["width"].median() or 20
    gap_threshold = max(30, median_width * 2)
    clusters: list[list[float]] = [[lefts[0]]]
    for x in lefts[1:]:
        if x - clusters[-1][-1] > gap_threshold:
            clusters.append([x])
        else:
            clusters[-1].append(x)
    centers = [sum(c) / len(c) for c in clusters]
    if len(centers) < 2:
        return None  # a single text blob, not a table

    def column_for(x: float) -> int:
        return min(range(len(centers)), key=lambda i: abs(centers[i] - x))

    rows: list[list[str | None]] = []
    for indices in row_groups:
        cells: list[str | None] = [None] * len(centers)
        for _, word in words.loc[indices].sort_values("left").iterrows():
            index = column_for(word["left"])
            cells[index] = f"{cells[index]} {word['text']}" if cells[index] else word["text"]
        rows.append(cells)

    grid = pd.DataFrame(rows)
    if grid.dropna(how="all").empty:
        return None
    return grid


def _pdf_table_to_grid(rows: list[list]) -> pd.DataFrame | None:
    if not rows:
        return None
    cleaned = [
        [_clean_pdf_cell(cell) for cell in row]
        for row in rows
    ]
    grid = pd.DataFrame(cleaned)
    if grid.dropna(how="all").empty:
        return None
    return grid


def _clean_pdf_cell(value):
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text if text else None


def _is_pdf_page_table(table: RawTable) -> bool:
    return any(n.finding_type == "table_from_pdf" for n in table.notes)


def add_union_candidates(tables: list[RawTable]) -> list[RawTable]:
    """Workbooks often split ONE dataset across many same-schema sheets
    (per-month tabs, per-region tabs); a PDF table pdfplumber can only see one
    page at a time is the same shape of problem. When several tables share an
    identical column signature, add a combined table with a provenance column
    as an extra candidate — table scoring decides whether it becomes the
    dashboard base. Original tables are always kept.

    PDF page tables union at >= 2 (a page break is an extraction artifact,
    not a deliberate split — unlike two Excel sheets, which need >= 3 to rule
    out coincidental same-shaped-but-unrelated tabs)."""
    groups: dict[tuple, list[RawTable]] = {}
    for table in tables:
        signature = tuple(str(c) for c in table.dataframe.columns)
        if len(signature) >= 2:
            groups.setdefault(signature, []).append(table)

    combined: list[RawTable] = []
    for signature, members in groups.items():
        if "Source Sheet" in signature or "Page" in signature:
            continue
        from_pdf = all(_is_pdf_page_table(m) for m in members)
        if len(members) < (2 if from_pdf else 3):
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
        provenance_column = "Page" if from_pdf else "Source Sheet"
        frames = []
        for member in members:
            frame = member.dataframe.copy()
            frame.insert(0, provenance_column, member.name)
            frames.append(frame)
        union = pd.concat(frames, ignore_index=True)
        names = [m.name for m in members]
        noun = "pages" if from_pdf else "sheets"
        combined.append(
            RawTable(
                name=f"Combined ({len(members)} {noun})",
                dataframe=union,
                notes=[
                    TransformNote(
                        finding_type="sheets_combined",
                        severity="info",
                        message=(
                            f"{len(members)} {noun} share the same columns and were "
                            f"also combined into one table ({', '.join(names[:6])}"
                            + ("…" if len(names) > 6 else "")
                            + f"). A '{provenance_column}' column says where each row came from."
                        ),
                        meta={"sheets": names},
                    )
                ],
            )
        )
    return tables + combined


MAX_JOIN_CANDIDATES = 4
JOIN_KEY_UNIQUE_RATIO = 0.95  # how unique a column must be to act as a dimension's key
JOIN_CONTAINMENT_RATIO = 0.8  # how much of the fact's keys must exist in the dimension
JOIN_MIN_DISTINCT_KEYS = 3  # a 2-value column ("Yes"/"No") is not a real key
# A real dimension collapses many fact rows down to few categories (orders
# -> customers, deals -> reps). Two sheets with near-equal row counts are
# more likely row-aligned companion/helper sheets (a pivot-support tab built
# alongside the main sheet) than a genuine fact/dimension pair, even if a
# column between them happens to look unique — joining those just bolts
# unrelated helper columns onto the real table.
JOIN_MAX_DIMENSION_TO_FACT_ROWS = 0.5


def add_join_candidates(tables: list[RawTable]) -> list[RawTable]:
    """Detect a primary-key/foreign-key relationship between two tables (an
    'orders' fact table and a 'customers' dimension table sharing a customer
    id) and add the enriched join as an extra candidate — same pattern as
    add_union_candidates: original tables are always kept, table scoring
    picks the winner. Works whether the tables came from one workbook or
    several uploaded files.

    Safety: a dimension key must be near-unique (so the join can never fan
    out and multiply the fact table's rows) and the fact's values must
    mostly exist in the dimension (so a coincidental same-named column on
    unrelated data — 'id' meaning different things in two systems — doesn't
    produce a nonsense join).
    """
    joined: list[RawTable] = []
    for i, left in enumerate(tables):
        if len(joined) >= MAX_JOIN_CANDIDATES:
            break
        for right in tables[i + 1 :]:
            if len(joined) >= MAX_JOIN_CANDIDATES:
                break
            candidate = _join_pair(left, right)
            if candidate is not None:
                joined.append(candidate)
    return tables + joined


def _shared_key_columns(left: pd.DataFrame, right: pd.DataFrame) -> list[tuple[str, str]]:
    def norm(name) -> str:
        return re.sub(r"[^a-z0-9]", "", str(name).lower())

    right_by_norm: dict[str, str] = {}
    for column in right.columns:
        right_by_norm.setdefault(norm(column), str(column))
    pairs = []
    for column in left.columns:
        match = right_by_norm.get(norm(column))
        if match is not None:
            pairs.append((str(column), match))
    return pairs


def _key_quality(series: pd.Series) -> tuple[float, int]:
    non_null = series.dropna()
    if len(non_null) < JOIN_MIN_DISTINCT_KEYS:
        return 0.0, 0
    try:
        distinct = non_null.nunique()
    except TypeError:
        return 0.0, 0  # unhashable values
    return distinct / len(non_null), distinct


def _join_pair(left: RawTable, right: RawTable) -> RawTable | None:
    left_df, right_df = left.dataframe, right.dataframe
    if left_df.shape[1] == right_df.shape[1] and list(left_df.columns) == list(right_df.columns):
        return None  # identical schema -> a union candidate, not a join

    best = None  # (containment, dimension_side, key_left, key_right)
    for key_left, key_right in _shared_key_columns(left_df, right_df):
        left_ratio, left_distinct = _key_quality(left_df[key_left])
        right_ratio, right_distinct = _key_quality(right_df[key_right])
        if left_distinct < JOIN_MIN_DISTINCT_KEYS or right_distinct < JOIN_MIN_DISTINCT_KEYS:
            continue
        # The dimension side is whichever is (more) unique; it must clear the
        # bar outright, or a join would risk fanning out the other side.
        if left_ratio >= JOIN_KEY_UNIQUE_RATIO and left_ratio >= right_ratio:
            dimension, fact, dim_key, fact_key = left, right, key_left, key_right
        elif right_ratio >= JOIN_KEY_UNIQUE_RATIO:
            dimension, fact, dim_key, fact_key = right, left, key_right, key_left
        else:
            continue
        if len(dimension.dataframe) > len(fact.dataframe) * JOIN_MAX_DIMENSION_TO_FACT_ROWS:
            continue  # not dimension-shaped: likely a row-aligned companion sheet
        fact_values = fact.dataframe[fact_key].dropna()
        dim_values = set(dimension.dataframe[dim_key].dropna())
        if len(fact_values) == 0 or not dim_values:
            continue
        try:
            containment = fact_values.isin(dim_values).mean()
        except TypeError:
            continue
        if containment < JOIN_CONTAINMENT_RATIO:
            continue
        if best is None or containment > best[0]:
            best = (containment, dimension, fact, dim_key, fact_key)

    if best is None:
        return None
    containment, dimension, fact, dim_key, fact_key = best

    dim_df = dimension.dataframe.drop_duplicates(subset=[dim_key], keep="first")
    other_columns = [c for c in dim_df.columns if c != dim_key]
    rename = {c: f"{dimension.name}: {c}" for c in other_columns}
    enrich = dim_df[[dim_key, *other_columns]].rename(columns=rename)
    merged = fact.dataframe.merge(
        enrich, left_on=fact_key, right_on=dim_key if dim_key == fact_key else dim_key,
        how="left", suffixes=("", f" ({dimension.name})"),
    )
    if dim_key != fact_key and dim_key in merged.columns:
        merged = merged.drop(columns=[dim_key])
    if len(merged) != len(fact.dataframe):
        return None  # guard tripped in practice (a near-unique key wasn't unique enough)

    return RawTable(
        name=f"{fact.name} + {dimension.name} (joined)",
        dataframe=merged,
        notes=[
            TransformNote(
                finding_type="relational_join_applied",
                severity="info",
                message=(
                    f"Joined '{fact.name}' to '{dimension.name}' on "
                    f"{fact_key} = {dim_key} ({containment * 100:.0f}% of rows matched) "
                    f"to enrich it with {dimension.name}'s columns."
                ),
                meta={
                    "factTable": fact.name,
                    "dimensionTable": dimension.name,
                    "factKey": fact_key,
                    "dimensionKey": dim_key,
                    "containment": round(float(containment), 4),
                },
            )
        ],
    )


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

    # A blank header over the leading label column ("" | Jan | Feb | ...) is
    # the classic accounting-export shape; "Category" reads better than
    # "column_1" everywhere downstream.
    if columns[0] == "column_1":
        leading = [v for v in data.iloc[:, 0].tolist() if not pd.isna(v)]
        if leading and all(isinstance(v, str) for v in leading):
            columns[0] = "Category"

    data = data.reset_index(drop=True)
    if len(data) > 0 and _is_units_row(data.iloc[0]):
        notes.append(
            TransformNote(
                finding_type="units_row_skipped",
                severity="info",
                message="Skipped a units row (USD / % / hrs) under the header.",
            )
        )
        data = data.iloc[1:].reset_index(drop=True)
    if len(data.dropna(how="all")) < MIN_TABLE_ROWS:
        return None
    data.columns = columns
    data = _maybe_transpose(data, notes)
    # The grid read leaves everything as object; give numeric/datetime columns
    # their real dtypes so downstream profiling sees them.
    return data.infer_objects(), notes


UNIT_TOKEN = re.compile(
    r"^\(?\s*(usd|eur|gbp|chf|cad|aud|[$€£%#]|count|units?|qty|hrs?|hours?|days?|"
    r"weeks?|kg|g|lbs?|pcs|pct|percent|x1000|000s?|in \w+)\s*\)?$",
    re.IGNORECASE,
)


def _is_units_row(row: pd.Series) -> bool:
    """A row of unit annotations right under the header ('USD', '%', 'hrs')."""
    values = [v for v in row.tolist() if not pd.isna(v)]
    if len(values) < 2 or not all(isinstance(v, str) for v in values):
        return False
    matches = sum(1 for v in values if UNIT_TOKEN.match(v))
    return matches >= max(2, int(len(values) * 0.6))


def _maybe_transpose(data: pd.DataFrame, notes: list[TransformNote]) -> pd.DataFrame:
    """Transposed exports put FIELDS in the first column and each record in a
    column ('Metric | Store A | Store B | …'). Signature: few rows, wider than
    tall, first column unique labels, and each ROW is type-homogeneous while
    columns are mixed. Conservative on purpose."""
    n_rows, n_cols = data.shape
    if not (2 <= n_rows <= 8 and n_cols > n_rows and n_cols >= 4):
        return data
    labels = data.iloc[:, 0]
    if labels.isna().any() or not all(isinstance(v, str) for v in labels):
        return data
    if labels.nunique() != len(labels):
        return data
    body = data.iloc[:, 1:]

    def kind(value):
        if isinstance(value, bool) or pd.isna(value):
            return None
        if isinstance(value, (int, float)):
            return "num"
        return "str" if isinstance(value, str) else "other"

    row_kinds = []
    for _, row in body.iterrows():
        kinds = {k for k in (kind(v) for v in row.tolist()) if k}
        row_kinds.append(kinds)
    rows_homogeneous = all(len(k) <= 1 for k in row_kinds)
    kinds_across_rows = {next(iter(k)) for k in row_kinds if k}
    if not rows_homogeneous or len(kinds_across_rows) < 2:
        return data  # nothing suggests fields-as-rows

    flipped = body.T.reset_index(drop=True)
    flipped.columns = [str(v).strip() for v in labels]
    flipped.insert(0, "Record", [str(c) for c in data.columns[1:]])
    notes.append(
        TransformNote(
            finding_type="table_transposed",
            severity="info",
            message=(
                "The table looked transposed (fields as rows, records as "
                "columns); flipped it so each row is one record."
            ),
            meta={"fields": [str(v) for v in labels]},
        )
    )
    return flipped


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

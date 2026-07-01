"""File parsing: bytes in, raw pandas DataFrames out.

CSV goes through DuckDB's auto-detection (delimiter, header, types); Excel goes
through openpyxl via pandas, one table per non-empty sheet. Normalization and
profiling happen downstream — this layer only extracts tables.
"""

import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import duckdb
import pandas as pd


class ParseError(Exception):
    """User-facing parse failure ("We could not detect a table in this file.")."""


@dataclass
class RawTable:
    name: str
    dataframe: pd.DataFrame


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
    # DuckDB's sniffer wants a real file path.
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=True) as handle:
        handle.write(data)
        handle.flush()
        try:
            connection = duckdb.connect()
            relation = connection.read_csv(handle.name)
            dataframe = relation.df()
        except duckdb.Error as error:
            raise ParseError("We could not detect a table in this file.") from error
        finally:
            try:
                connection.close()
            except UnboundLocalError:
                pass
    if dataframe.empty and dataframe.columns.empty:
        raise ParseError("We could not detect a table in this file.")
    return RawTable(name=Path(filename).stem, dataframe=dataframe)


def parse_excel(filename: str, data: bytes) -> list[RawTable]:
    try:
        sheets = pd.read_excel(BytesIO(data), sheet_name=None)
    except Exception as error:
        raise ParseError("We could not read this spreadsheet.") from error

    tables: list[RawTable] = []
    for sheet_name, dataframe in sheets.items():
        if dataframe.dropna(how="all").empty:
            continue  # skip empty sheets
        tables.append(RawTable(name=sheet_name, dataframe=dataframe))
    if not tables:
        raise ParseError("The spreadsheet has no sheets with data.")
    return tables

import re
from pathlib import PurePosixPath

from fastapi import HTTPException, status

# MVP input types (SETUP.md §2.1). Macro-enabled Office formats are rejected
# outright (§17.4) rather than stripped.
ALLOWED_EXTENSIONS = {".csv", ".tsv", ".txt", ".xlsx", ".xls"}
REJECTED_EXTENSIONS = {".xlsm", ".xlsb", ".xltm", ".docm", ".exe", ".js", ".sh", ".bat"}

ALLOWED_MIME_PREFIXES = (
    "text/csv",
    "text/tab-separated-values",
    "text/plain",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",  # browsers often send this for CSVs
)


def sanitize_filename(filename: str) -> str:
    """Strip any path components and unsafe characters; keep a readable name."""
    name = PurePosixPath(filename.replace("\\", "/")).name
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")
    return name[:200] or "upload"


def validate_upload(filename: str, mime_type: str | None, size_bytes: int, max_mb: int) -> str:
    """Validate and return the sanitized filename, or raise a friendly HTTP error."""
    safe_name = sanitize_filename(filename)
    extension = PurePosixPath(safe_name).suffix.lower()

    if extension in REJECTED_EXTENSIONS or extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                "This file type is not supported yet. "
                "Upload a CSV, TSV, TXT, XLSX, or XLS file."
            ),
        )

    if mime_type and not mime_type.lower().startswith(ALLOWED_MIME_PREFIXES):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="This file type is not supported yet.",
        )

    if size_bytes <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The file appears to be empty.",
        )

    if size_bytes > max_mb * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"This file is too large for your plan (max {max_mb} MB).",
        )

    return safe_name

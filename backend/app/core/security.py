from pathlib import Path
import re


def sanitize_csv_cell(value: any) -> str:
    """
    Prevents CSV / Formula Injection vulnerabilities (CWE-1236).
    If a cell value starts with '=', '+', '-', '@', tab, or carriage return,
    prefix it with a single quote (') to force spreadsheets to treat it as plain text.
    """
    if value is None:
        return ""
    str_val = str(value)
    if str_val and str_val[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{str_val}"
    return str_val


def validate_export_filename(filename: str) -> str:
    """
    Sanitizes export filenames to alphanumeric, hyphens, and underscores only.
    Strips directory traversal components safely.
    """
    base_name = Path(filename).name
    stem = Path(base_name).stem
    clean_stem = re.sub(r"[^a-zA-Z0-9_\-]", "_", stem)
    clean_stem = clean_stem.strip("_")
    if not clean_stem:
        clean_stem = "export"
    return f"{clean_stem}.csv"

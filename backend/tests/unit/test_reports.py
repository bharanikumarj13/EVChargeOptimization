import pytest
from app.core.security import sanitize_csv_cell, validate_export_filename


def test_sanitize_csv_cell_formula_injection():
    # Dangerous formula prefixes must be escaped with a single quote
    assert sanitize_csv_cell("=1+1") == "'=1+1"
    assert sanitize_csv_cell("+cmd|' /C calc'!A0") == "'+cmd|' /C calc'!A0"
    assert sanitize_csv_cell("-5+2") == "'-5+2"
    assert sanitize_csv_cell("@SUM(A1:A10)") == "'@SUM(A1:A10)"
    assert sanitize_csv_cell("\tTABBED") == "'\tTABBED"

    # Standard safe cells
    assert sanitize_csv_cell("STN-01") == "STN-01"
    assert sanitize_csv_cell(42.5) == "42.5"
    assert sanitize_csv_cell(None) == ""


def test_validate_export_filename():
    assert validate_export_filename("allocations.csv") == "allocations.csv"
    assert validate_export_filename("my_allocations") == "my_allocations.csv"
    # Strips directory traversal
    assert validate_export_filename("../../etc/passwd") == "passwd.csv"
    assert validate_export_filename("..\\..\\secret.csv") == "secret.csv"

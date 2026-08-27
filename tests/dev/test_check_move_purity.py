from scripts.dev.check_move_purity import check_move_purity

OLD = '''
import os

def alpha(a, b):
    """Docstring."""
    x = a + b
    return x

def beta():
    return 1
'''

NEW_CLEAN = '''
from .other import helper

def alpha(a, b):
    """Docstring."""
    x = a + b
    return x
'''

NEW_EDITED = '''
def alpha(a, b):
    """Docstring."""
    x = a - b
    return x
'''


def test_pure_move_reports_nothing():
    assert check_move_purity(OLD, NEW_CLEAN, ["alpha"]) == []


def test_edited_body_is_reported():
    assert check_move_purity(OLD, NEW_EDITED, ["alpha"]) == ["alpha"]


def test_missing_symbol_is_reported():
    assert check_move_purity(OLD, NEW_CLEAN, ["beta"]) == ["beta"]

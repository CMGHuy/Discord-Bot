"""Invariants the frozen redundancy matrix must satisfy.

These are not style checks. The matrix is pasted by hand from a measurement
script; every failure mode here mislabels weights silently rather than
raising, so it has to be asserted.
"""
from __future__ import annotations

import pytest

from swingbot.core.edge import confluence
from swingbot.core.market import levels


@pytest.fixture()
def m():
    return confluence.REDUNDANCY


def test_shape_is_square_and_matches_family_count(m):
    n = len(levels.ALL_STRATEGY_FAMILIES)
    assert len(m) == n
    assert all(len(row) == n for row in m)


def test_family_order_is_element_for_element(m):
    assert list(confluence.FAMILY_ORDER) == list(levels.ALL_STRATEGY_FAMILIES)


def test_diagonal_is_unit(m):
    for i in range(len(m)):
        assert m[i][i] == pytest.approx(1.0)


def test_symmetric(m):
    for i in range(len(m)):
        for j in range(len(m)):
            assert m[i][j] == pytest.approx(m[j][i]), f"asymmetry at ({i},{j})"


def test_every_entry_is_a_probability(m):
    for row in m:
        for v in row:
            assert 0.0 <= v <= 1.0


def test_provenance_comment_present():
    # The measuring commit must be recoverable from the source, or the
    # constant is unauditable.
    import inspect
    src = inspect.getsource(confluence)
    assert "measured-on:" in src, "REDUNDANCY needs a `measured-on:` provenance comment"

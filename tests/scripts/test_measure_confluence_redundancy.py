"""Tally -> symmetric redundancy matrix. Pure arithmetic, no data."""
from __future__ import annotations

import pytest

from scripts.backtest.measure_confluence_redundancy import tally_to_matrix


def test_unit_diagonal():
    tally = {(0, 0): 100, (1, 1): 50}
    m = tally_to_matrix(tally, n=2)
    assert m[0][0] == pytest.approx(1.0)
    assert m[1][1] == pytest.approx(1.0)


def test_symmetrised_conditional():
    # 0 landed 100x, 1 landed 50x, they co-occurred 25x.
    tally = {(0, 0): 100, (1, 1): 50, (0, 1): 25, (1, 0): 25}
    m = tally_to_matrix(tally, n=2)
    # (25/100 + 25/50) / 2 = (0.25 + 0.5) / 2 = 0.375
    assert m[0][1] == pytest.approx(0.375)
    assert m[1][0] == pytest.approx(0.375)


def test_never_observed_family_gets_zero_offdiagonal_and_unit_diagonal():
    # A family that never fired must not poison the matrix with a divide-by-zero
    # or an implicit 1.0 -- it is simply uninformative.
    tally = {(0, 0): 10, (1, 1): 0}
    m = tally_to_matrix(tally, n=2)
    assert m[1][1] == pytest.approx(1.0)
    assert m[0][1] == pytest.approx(0.0)


def test_entries_stay_in_unit_interval():
    tally = {(0, 0): 10, (1, 1): 10, (0, 1): 10, (1, 0): 10}
    m = tally_to_matrix(tally, n=2)
    for row in m:
        for v in row:
            assert 0.0 <= v <= 1.0

"""Participation-ratio reduction: N_eff = N^2 / sum(R[i][j]) over present families.

Pure arithmetic over hand-built matrices -- no market data, no config, no I/O.
"""
from __future__ import annotations

import math

import pytest

from swingbot.core.edge import confluence
from swingbot.core.market import levels


def _identity(n: int) -> list[list[float]]:
    return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]


def _ones(n: int) -> list[list[float]]:
    return [[1.0] * n for _ in range(n)]


def test_family_order_matches_levels_exactly():
    # An ordering drift here silently mislabels every weight in the matrix.
    assert list(confluence.FAMILY_ORDER) == list(levels.ALL_STRATEGY_FAMILIES)


def test_independent_families_give_neff_equal_n():
    m = _identity(len(confluence.FAMILY_ORDER))
    fams = list(confluence.FAMILY_ORDER[:5])
    assert confluence.effective_count(fams, m) == pytest.approx(5.0)


def test_perfectly_redundant_families_collapse_to_one():
    m = _ones(len(confluence.FAMILY_ORDER))
    fams = list(confluence.FAMILY_ORDER[:5])
    assert confluence.effective_count(fams, m) == pytest.approx(1.0)


def test_half_redundant_pair_lands_between():
    n = len(confluence.FAMILY_ORDER)
    m = _identity(n)
    m[0][1] = m[1][0] = 0.5
    fams = list(confluence.FAMILY_ORDER[:2])
    # 4 / (1 + 0.5 + 0.5 + 1) = 1.333...
    assert confluence.effective_count(fams, m) == pytest.approx(4.0 / 3.0)


@pytest.mark.parametrize("k", [0, 1])
def test_degenerate_counts_are_identity(k):
    m = _identity(len(confluence.FAMILY_ORDER))
    fams = list(confluence.FAMILY_ORDER[:k])
    assert confluence.effective_count(fams, m) == pytest.approx(float(k))


def test_neff_never_exceeds_n_over_random_matrices():
    # The safety property the whole plan rests on.
    import random
    rng = random.Random(11)
    n = len(confluence.FAMILY_ORDER)
    for _ in range(200):
        m = _identity(n)
        for i in range(n):
            for j in range(i + 1, n):
                v = rng.random()
                m[i][j] = m[j][i] = v
        k = rng.randint(1, n)
        fams = list(confluence.FAMILY_ORDER[:k])
        neff = confluence.effective_count(fams, m)
        assert 1.0 - 1e-9 <= neff <= k + 1e-9


def test_reduction_is_order_free():
    n = len(confluence.FAMILY_ORDER)
    m = _identity(n)
    m[0][3] = m[3][0] = 0.7
    m[1][3] = m[3][1] = 0.2
    a = confluence.effective_count([confluence.FAMILY_ORDER[i] for i in (0, 1, 3)], m)
    b = confluence.effective_count([confluence.FAMILY_ORDER[i] for i in (3, 0, 1)], m)
    assert a == pytest.approx(b)


def test_unknown_family_raises():
    m = _identity(len(confluence.FAMILY_ORDER))
    with pytest.raises(ValueError, match="unknown family"):
        confluence.effective_count(["Not A Family"], m)


def test_duplicate_families_are_collapsed():
    m = _identity(len(confluence.FAMILY_ORDER))
    fams = [confluence.FAMILY_ORDER[0], confluence.FAMILY_ORDER[0]]
    assert confluence.effective_count(fams, m) == pytest.approx(1.0)


def test_missing_matrix_raises_rather_than_defaulting():
    # Until Task 4 lands the constant there is no safe default: an implicit
    # identity would make this component a no-op that still passes its tests.
    with pytest.raises(ValueError, match="no redundancy matrix"):
        confluence.effective_count([confluence.FAMILY_ORDER[0]], None)


def test_int_form_floors_rather_than_rounds():
    n = len(confluence.FAMILY_ORDER)
    m = _identity(n)
    # Three families, one near-redundant pair -> N_eff just under 3.
    m[0][1] = m[1][0] = 0.001
    fams = list(confluence.FAMILY_ORDER[:3])
    assert confluence.effective_count(fams, m) < 3.0
    assert confluence.effective_count_int(fams, m) == 2

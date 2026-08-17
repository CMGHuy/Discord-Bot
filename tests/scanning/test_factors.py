import pytest
from swingbot.core.scanning.factors import (
    FactorResult, FactorContext, run_factors,
)


def _ctx(**kw):
    """Minimal context; every field defaults to None so a factor under test
    only has to supply what it reads."""
    return FactorContext(**kw)


def test_factor_result_carries_points_and_line():
    r = FactorResult(name="demo", points=7, line="demo scored (+7)")
    assert (r.name, r.points, r.line) == ("demo", 7, "demo scored (+7)")


def test_run_factors_sums_points_and_collects_breakdown():
    def f_a(ctx):
        return FactorResult("a", 5, "a (+5)")

    def f_b(ctx):
        return FactorResult("b", 3, "b (+3)")

    total, breakdown = run_factors([f_a, f_b], _ctx())
    assert total == 8
    assert breakdown == {"a": "a (+5)", "b": "b (+3)"}


def test_run_factors_skips_factors_returning_none():
    """A factor whose input is absent returns None and must not appear in the
    breakdown at all -- an absent reading must never render as a real one that
    happened to score zero."""
    def f_present(ctx):
        return FactorResult("present", 4, "present (+4)")

    def f_absent(ctx):
        return None

    total, breakdown = run_factors([f_present, f_absent], _ctx())
    assert total == 4
    assert "absent" not in breakdown


def test_run_factors_propagates_negative_points():
    def f_penalty(ctx):
        return FactorResult("penalty", -10, "penalty (-10)")

    total, _ = run_factors([f_penalty], _ctx())
    assert total == -10

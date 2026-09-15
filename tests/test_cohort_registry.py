import json

import pytest

from swingbot.core.backtesting import cohort_registry as cr


def test_blend_with_no_live_data_is_the_backtest_prior():
    assert cr.blend(None, 0, 0.40) == pytest.approx(0.40)


def test_blend_at_k_live_trades_is_the_midpoint():
    assert cr.blend(0.60, cr.K, 0.40) == pytest.approx(0.50)


def test_blend_far_past_k_is_dominated_by_live():
    assert cr.blend(0.60, cr.K * 99, 0.40) == pytest.approx(0.598, abs=1e-3)


def test_blend_with_no_backtest_data_is_the_live_estimate_unshrunk():
    """A cell the backtest never occupied has no prior to shrink toward --
    it must not silently dilute a real live estimate toward a fabricated
    zero (regression: emit_cohort_registry used to default a missing
    backtest cell's stats to 0.0, dragging a genuinely strong live-only
    cohort toward COHORT_TYPICAL/POOR)."""
    assert cr.blend(0.35, 150, None) == pytest.approx(0.35)


def test_blend_with_neither_side_is_zero():
    assert cr.blend(None, 0, None) == pytest.approx(0.0)


def test_band_poor_typical_strong_at_the_boundaries():
    pool = -0.136
    assert cr.band(pool - cr.BAND_R, pool) == "COHORT_POOR"
    assert cr.band(pool - cr.BAND_R + 1e-9, pool) == "COHORT_TYPICAL"
    assert cr.band(pool, pool) == "COHORT_TYPICAL"
    assert cr.band(pool + cr.BAND_R, pool) == "COHORT_STRONG"


def test_cohort_key_shape():
    assert cr.cohort_key("bullish", "bear_volatile") == "bullish|bear_volatile"


def _write_registry(tmp_path, cells, pool_mean_r=-0.136):
    path = tmp_path / "cohort_registry.json"
    path.write_text(
        json.dumps(
            {
                "run_date": "2026-09-14",
                "window": "TRAIN+LIVE",
                "pool_mean_r": pool_mean_r,
                "cells": cells,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_thin_cell_resolves_to_unknown(tmp_path):
    path = _write_registry(
        tmp_path,
        {
            "bullish|bull_quiet": {
                "n_live": 10,
                "n_backtest": 20,
                "win_rate_live": 50.0,
                "win_rate_backtest": 50.0,
                "expectancy_r_live": 0.0,
                "expectancy_r_backtest": 0.0,
            },
        },
    )
    cr.load_registry(path)
    assert cr.get_cohort("bullish", "bull_quiet").label == "COHORT_UNKNOWN"


def test_fat_poor_cell_is_labelled_poor(tmp_path):
    path = _write_registry(
        tmp_path,
        {
            "bearish|bear_volatile": {
                "n_live": 100,
                "n_backtest": 500,
                "win_rate_live": 41.0,
                "win_rate_backtest": 41.4,
                "expectancy_r_live": -0.38,
                "expectancy_r_backtest": -0.38,
            },
        },
    )
    cr.load_registry(path)
    cohort = cr.get_cohort("bearish", "bear_volatile")
    assert cohort.label == "COHORT_POOR"
    assert cohort.n_live == 100 and cohort.n_backtest == 500
    assert cohort.expectancy_r == pytest.approx(-0.38, abs=1e-6)
    assert cohort.run_date == "2026-09-14"


def test_missing_cell_resolves_to_unknown(tmp_path):
    cr.load_registry(_write_registry(tmp_path, {}))
    assert cr.get_cohort("bullish", "bull_quiet").label == "COHORT_UNKNOWN"


def test_none_regime_resolves_to_unknown(tmp_path):
    cr.load_registry(_write_registry(tmp_path, {}))
    assert cr.get_cohort("bullish", None).label == "COHORT_UNKNOWN"


def test_cell_with_no_backtest_occurrences_reads_as_the_live_number(tmp_path):
    """A regime the backtest window happened not to cover must not be
    diluted toward a fabricated zero-expectancy prior."""
    path = _write_registry(
        tmp_path,
        {
            "bearish|bear_volatile": {
                "n_live": 150,
                "n_backtest": 0,
                "win_rate_live": 60.0,
                "win_rate_backtest": None,
                "expectancy_r_live": 0.35,
                "expectancy_r_backtest": None,
            },
        },
    )
    cr.load_registry(path)
    cohort = cr.get_cohort("bearish", "bear_volatile")
    assert cohort.expectancy_r == pytest.approx(0.35)
    assert cohort.label == "COHORT_STRONG"

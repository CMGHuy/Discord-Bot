import logging

import numpy as np
import pandas as pd

from swingbot.core.marketdata import data_store
from swingbot.core.marketdata.data_refresh import _adjustment_ratio, _merge_save, _record
from swingbot.core.marketdata.data_store import cache_path


def _write_frame(base_dir, symbol, tf, start: str, end: str):
    idx = pd.date_range(start, end, freq="D")
    df = pd.DataFrame(
        {"Open": np.arange(len(idx), dtype=float),
         "High": np.arange(len(idx), dtype=float),
         "Low": np.arange(len(idx), dtype=float),
         "Close": np.arange(len(idx), dtype=float),
         "Volume": np.arange(len(idx), dtype=float)},
        index=idx,
    )
    data_store.save_to_disk(df, symbol, tf, base_dir=str(base_dir))


def test_record_logs_regression_but_still_adopts_the_new_earliest(tmp_path, caplog):
    """A ticker whose on-disk history genuinely shrank (a bug that has since
    been fixed, or Yahoo's rolling intraday window eroding a near-boundary
    archive) must be reported once -- but the stored `earliest` baseline
    must move to match reality, not freeze at a value the archive can never
    reach again. Freezing it is exactly what makes the alert repeat forever
    (production: AMD/hourly, CEG/hourly and ~50 others logging this on every
    4-hourly refresh tick since 2026-08-24, comparing against an unreachable
    2016 baseline against a CSV that has actually started at 2023-09-25 for
    months)."""
    _write_frame(tmp_path, "AAA", "daily", "2024-01-01", "2024-01-10")
    state = {"AAA|daily": {"earliest": "2016-01-01"}}

    with caplog.at_level(logging.ERROR, logger="swing-bot.data_refresh"):
        _record(state, "AAA", "daily", {"status": "fresh", "rows": 10}, str(tmp_path))

    assert "COVERAGE REGRESSION" in caplog.text
    assert state["AAA|daily"]["earliest"] == "2024-01-01"


def test_record_does_not_repeat_the_same_regression_forever(tmp_path, caplog):
    """Once a regression has been reported and its new (shallower) earliest
    adopted as the baseline, an unchanged archive must not re-trigger the
    same alert on the next refresh tick -- that repeat-forever behavior is
    the actual production bug, not the initial detection."""
    _write_frame(tmp_path, "AAA", "daily", "2024-01-01", "2024-01-10")
    state = {"AAA|daily": {"earliest": "2016-01-01"}}

    with caplog.at_level(logging.ERROR, logger="swing-bot.data_refresh"):
        _record(state, "AAA", "daily", {"status": "fresh", "rows": 10}, str(tmp_path))
        first_pass_errors = len(caplog.records)
        _record(state, "AAA", "daily", {"status": "fresh", "rows": 10}, str(tmp_path))

    assert len(caplog.records) == first_pass_errors  # no new error on the second, unchanged pass
    assert state["AAA|daily"]["earliest"] == "2024-01-01"


def test_record_no_regression_when_earliest_holds_or_deepens(tmp_path, caplog):
    _write_frame(tmp_path, "AAA", "daily", "2015-01-01", "2015-01-10")
    state = {"AAA|daily": {"earliest": "2016-01-01"}}

    with caplog.at_level(logging.ERROR, logger="swing-bot.data_refresh"):
        _record(state, "AAA", "daily", {"status": "fresh", "rows": 10}, str(tmp_path))

    assert "COVERAGE REGRESSION" not in caplog.text
    assert state["AAA|daily"]["earliest"] == "2015-01-01"


# ---------------------------------------------------------------------------
# _merge_save / _adjustment_ratio -- v56: re-adjust cached bars on a split/
# dividend detected between refreshes, instead of blindly unioning old-basis
# and new-basis prices (the actual cause of universe.data_quality_issues'
# ">40% bar without volume spike" flags firing live in production 2026-08-24).
# ---------------------------------------------------------------------------

def _price_frame(start: str, end: str, close: float, volume: float = 1000.0):
    idx = pd.date_range(start, end, freq="D")
    return pd.DataFrame(
        {"Open": close, "High": close, "Low": close, "Close": close, "Volume": volume},
        index=idx,
    )


def test_adjustment_ratio_none_when_prices_agree_on_overlap():
    existing = _price_frame("2024-01-01", "2024-01-10", close=100.0)
    fresh = _price_frame("2024-01-08", "2024-01-15", close=100.0)
    assert _adjustment_ratio(existing, fresh, "AAA", "daily") is None


def test_adjustment_ratio_none_within_normal_eod_noise():
    # 0.3% apart -- well inside real-world EOD rounding, nowhere near a split.
    existing = _price_frame("2024-01-01", "2024-01-10", close=100.0)
    fresh = _price_frame("2024-01-08", "2024-01-15", close=100.3)
    assert _adjustment_ratio(existing, fresh, "AAA", "daily") is None


def test_adjustment_ratio_detects_a_2_for_1_split(caplog):
    existing = _price_frame("2024-01-01", "2024-01-10", close=100.0)
    fresh = _price_frame("2024-01-08", "2024-01-15", close=50.0)   # 2:1 split re-adjusted the whole series
    with caplog.at_level(logging.WARNING, logger="swing-bot.data_refresh"):
        ratio = _adjustment_ratio(existing, fresh, "AAA", "daily")
    assert ratio == 0.5
    assert "adjustment-basis mismatch" in caplog.text


def test_merge_save_rescales_pre_overlap_bars_to_the_new_basis(tmp_path):
    existing = _price_frame("2024-01-01", "2024-01-10", close=100.0)
    fresh = _price_frame("2024-01-08", "2024-01-15", close=50.0)

    merged, added = _merge_save(existing, fresh, "AAA", "daily", str(tmp_path))

    # Every bar -- the pre-split tail AND the new post-split bars -- must
    # end up on the SAME (new) basis; before this fix, 2024-01-01..07 would
    # have stayed at 100 while 2024-01-08 onward became 50, a single-bar
    # cliff exactly matching universe.data_quality_issues' ">40% bar
    # without volume spike" detector.
    assert (merged["Close"] == 50.0).all()
    assert added == 5   # 2024-01-11..15, the only genuinely new dates

    # And the rescale is durable -- written to disk, not just returned.
    reloaded = pd.read_csv(cache_path("AAA", "daily", base_dir=str(tmp_path)), index_col=0)
    assert (reloaded["Close"] == 50.0).all()


def test_merge_save_does_not_rescale_when_no_adjustment_changed(tmp_path):
    existing = _price_frame("2024-01-01", "2024-01-10", close=100.0)
    fresh = _price_frame("2024-01-08", "2024-01-15", close=100.0)

    merged, added = _merge_save(existing, fresh, "AAA", "daily", str(tmp_path))

    assert (merged["Close"] == 100.0).all()
    assert added == 5

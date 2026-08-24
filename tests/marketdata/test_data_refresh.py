import logging

import numpy as np
import pandas as pd

from swingbot.core.marketdata import data_store
from swingbot.core.marketdata.data_refresh import _record


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

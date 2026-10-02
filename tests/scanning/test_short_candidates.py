"""V118-2: aligned reference windows and broad/isolated weakness modes."""
import datetime as dt
from types import SimpleNamespace

import numpy as np
import pandas as pd

from swingbot.core.scanning.short_candidates import (build_reference_rels,
                                                     select_mode)
from swingbot.core.scanning.short_reference import (align_completed,
                                                    etf_for_sector, return_63)

BEAR = SimpleNamespace(trend="bearish")
NEUTRAL = SimpleNamespace(trend="bullish")
END = pd.Timestamp("2026-09-18")                       # a Friday
AFTER_CLOSE = dt.datetime(2026, 9, 18, 22, 0, tzinfo=dt.timezone.utc)  # 18:00 ET
MID_SESSION = dt.datetime(2026, 9, 18, 16, 0, tzinfo=dt.timezone.utc)  # 12:00 ET
PANEL = [-0.20, -0.10, 0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35]


def frame(first, last, n=80, end=END):
    """Flat at `first` until the final bar, which closes at `last`."""
    idx = pd.bdate_range(end=end, periods=n)
    close = np.full(n, float(first))
    close[-1] = last
    return pd.DataFrame({"Close": close}, index=idx)


def test_broad_spy_bearish_laggard_selected():
    stock, spy = frame(100, 70), frame(100, 99)        # rel = -0.29 -> bottom of panel
    assert select_mode(stock, spy, None, spy_regime=BEAR,
                       reference_rels=PANEL, now=AFTER_CLOSE) == ("broad", None)


def test_broad_non_laggard_rejected():
    stock, spy = frame(100, 120), frame(100, 99)
    assert select_mode(stock, spy, None, spy_regime=BEAR,
                       reference_rels=PANEL, now=AFTER_CLOSE) == (None, "not_laggard")


def test_isolated_stock_below_sector_selected():
    stock, spy, sector = frame(100, 90), frame(100, 101), frame(100, 105)
    assert select_mode(stock, spy, sector, spy_regime=NEUTRAL,
                       reference_rels=PANEL, now=AFTER_CLOSE) == ("isolated", None)


def test_isolated_stock_above_sector_rejected():
    stock, spy, sector = frame(100, 110), frame(100, 101), frame(100, 105)
    assert select_mode(stock, spy, sector, spy_regime=NEUTRAL,
                       reference_rels=PANEL, now=AFTER_CLOSE) == (None, "not_laggard")


def test_missing_sector_rejected_when_isolated_needed():
    assert select_mode(frame(100, 90), frame(100, 101), None, spy_regime=NEUTRAL,
                       reference_rels=PANEL, now=AFTER_CLOSE) == (None, "missing_sector")


def test_stale_sector_rejected():
    stale = frame(100, 105, end=END - pd.Timedelta(days=1))
    assert select_mode(frame(100, 90), frame(100, 101), stale, spy_regime=NEUTRAL,
                       reference_rels=PANEL, now=AFTER_CLOSE) == (None, "unaligned_sector")


def test_missing_spy_and_one_day_spy_mismatch():
    stock = frame(100, 70)
    assert select_mode(stock, None, None, spy_regime=BEAR, reference_rels=PANEL,
                       now=AFTER_CLOSE) == (None, "missing_spy")
    lagged = frame(100, 99, end=END - pd.Timedelta(days=1))
    assert select_mode(stock, lagged, None, spy_regime=BEAR, reference_rels=PANEL,
                       now=AFTER_CLOSE) == (None, "unaligned_spy")


def test_short_history_rejected():
    assert select_mode(frame(100, 70, n=40), frame(100, 99, n=40), None,
                       spy_regime=BEAR, reference_rels=PANEL,
                       now=AFTER_CLOSE) == (None, "short_history")


def test_empty_panel_rejected_not_synthetic_fifty():
    assert select_mode(frame(100, 70), frame(100, 99), None, spy_regime=BEAR,
                       reference_rels=[], now=AFTER_CLOSE) == (None, "empty_panel")


def test_forming_today_bar_is_dropped():
    # Bar for 2026-09-18 is still forming at noon ET: both frames end 09-17.
    stock, spy = frame(100, 70), frame(100, 99)
    aligned = align_completed(stock, spy, None, MID_SESSION)
    assert aligned is not None and aligned[0].index[-1] == END - pd.Timedelta(days=1)
    # The forming bar's close (70) must not be what decides the mode.
    assert select_mode(stock, spy, None, spy_regime=BEAR, reference_rels=PANEL,
                       now=MID_SESSION)[0] is None


def test_truncation_at_t_equals_full_frame_with_forming_bar():
    t_stock, t_spy, t_sec = frame(100, 90), frame(100, 101), frame(100, 105)
    base = select_mode(t_stock, t_spy, t_sec, spy_regime=NEUTRAL,
                       reference_rels=PANEL, now=AFTER_CLOSE)
    nxt = END + pd.offsets.BDay(1)

    def extend(f, close):   # a future bar whose close flips the comparison
        return pd.concat([f, pd.DataFrame({"Close": [close]}, index=[nxt])])
    now_forming = dt.datetime(2026, 9, 21, 16, 0, tzinfo=dt.timezone.utc)
    full = select_mode(extend(t_stock, 200), extend(t_spy, 101), extend(t_sec, 105),
                       spy_regime=NEUTRAL, reference_rels=PANEL, now=now_forming)
    assert base == full == ("isolated", None)
    a = align_completed(t_stock, t_spy, t_sec, AFTER_CLOSE)
    b = align_completed(extend(t_stock, 200), extend(t_spy, 101), extend(t_sec, 105),
                        now_forming)
    assert return_63(a[0]) == return_63(b[0])


def test_reference_rels_pure_panel_skips_unaligned_and_short():
    spy = frame(100, 100)
    frames = {"A": frame(100, 110), "B": frame(100, 90),
              "OLD": frame(100, 90, end=END - pd.Timedelta(days=1)),
              "SHORT": frame(100, 90, n=30)}
    assert sorted(round(r, 2) for r in build_reference_rels(frames, spy, AFTER_CLOSE)) == [-0.1, 0.1]


def test_etf_for_sector_uses_the_single_fetch_mapping():
    from swingbot.core.scanning.fetch import _etf_symbol_of_sector
    table = _etf_symbol_of_sector()
    assert table
    sector, etf = next(iter(table.items()))
    assert etf_for_sector(sector) == etf
    assert etf_for_sector("No Such Sector") is None

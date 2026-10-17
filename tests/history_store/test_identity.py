"""Identity check (spec §2): a fresh Alpaca daily frame is accepted only when
its closes agree with data/backtest_cache (fallback market_data/daily) to 0.5%
by median over at least 250 finite overlapping bars. Bars before the
reference's first bar are dropped (ticker reuse, e.g. SNDK)."""
import math

import numpy as np
import pandas as pd
import pytest

from alpaca_history import identity


def _daily(n, close=10.0, start="2016-01-04"):
    idx = pd.DatetimeIndex(pd.bdate_range(start, periods=n), name="Date")
    closes = np.full(n, float(close)) if np.isscalar(close) else np.asarray(close, float)
    return pd.DataFrame({"Open": closes, "High": closes, "Low": closes,
                         "Close": closes, "Volume": np.full(n, 1e6)}, index=idx)


def _ref(frame, factor=1.0):
    return pd.DataFrame({"Close": frame["Close"] / factor}, index=frame.index)


# --- skips -------------------------------------------------------------------------

@pytest.mark.parametrize("ticker,reason", [
    ("XAUUSD", "skipped: spot metal (built from futures)"),
    ("xagusd", "skipped: spot metal (built from futures)"),
    ("GC=F", "skipped: futures"),
    ("^GSPC", "skipped: index"),
    ("SAP.DE", "skipped: not Alpaca-eligible"),
    ("EURUSD=X", "skipped: not Alpaca-eligible"),
    ("BTC-USD", "skipped: not Alpaca-eligible"),
    ("AAPL", None), ("SPY", None), ("BRK-B", None),
])
def test_skip_reason(ticker, reason):
    assert identity.skip_reason(ticker) == reason


# --- reference ---------------------------------------------------------------------

def _csv(folder, name, text):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text)


def test_reference_prefers_backtest_cache(tmp_path):
    _csv(tmp_path / "bc", "AAPL.csv", "Date,Open,High,Low,Close,Volume\n2016-01-04,1,1,1,10,5\n")
    _csv(tmp_path / "md", "AAPL.csv", "Date,Open,High,Low,Close,Volume\n2016-01-04,1,1,1,99,5\n")
    ref = identity.reference_frame("AAPL", backtest_dir=tmp_path / "bc", market_dir=tmp_path / "md")
    assert ref["Close"].tolist() == [10.0]


def test_reference_falls_back_to_market_data_and_normalises_tz(tmp_path):
    _csv(tmp_path / "md", "GC_F.csv",
         "Date,Open,High,Low,Close,Volume\n"
         "2016-01-05 00:00:00-05:00,1,1,1,11,5\n2016-01-04 00:00:00-05:00,1,1,1,10,5\n")
    ref = identity.reference_frame("GC=F", backtest_dir=tmp_path / "bc", market_dir=tmp_path / "md")
    assert ref.index.tz is None
    assert list(ref.index) == [pd.Timestamp("2016-01-04"), pd.Timestamp("2016-01-05")]
    assert ref["Close"].tolist() == [10.0, 11.0]


def test_reference_skips_a_file_without_close(tmp_path):
    _csv(tmp_path / "bc", "AAPL.csv", "Date,Open\n2016-01-04,1\n")
    _csv(tmp_path / "md", "AAPL.csv", "Date,Close\n2016-01-04,12\n")
    ref = identity.reference_frame("AAPL", backtest_dir=tmp_path / "bc", market_dir=tmp_path / "md")
    assert ref["Close"].tolist() == [12.0]


def test_no_reference_is_none(tmp_path):
    assert identity.reference_frame("AAPL", backtest_dir=tmp_path / "bc",
                                    market_dir=tmp_path / "md") is None


# --- identity_check ------------------------------------------------------------------

def test_agreeing_frame_is_ok():
    fresh = _daily(300)
    result, kept = identity.identity_check(fresh, _ref(fresh, 1.001))
    assert result.status == identity.OK
    assert result.median_ratio == pytest.approx(1.001)
    assert (result.overlap, result.dropped_before) == (300, None)
    pd.testing.assert_frame_equal(kept, fresh)


@pytest.mark.parametrize("factor,status", [
    (1.004, identity.OK), (0.996, identity.OK),
    (1.006, identity.PRICE_MISMATCH), (0.994, identity.PRICE_MISMATCH),
    (2.0, identity.PRICE_MISMATCH),
])
def test_tolerance_is_half_a_percent(factor, status):
    fresh = _daily(300)
    assert identity.identity_check(fresh, _ref(fresh, factor))[0].status == status


@pytest.mark.parametrize("n,status", [(249, identity.SHORT_OVERLAP), (250, identity.OK)])
def test_minimum_overlap_is_250_bars(n, status):
    fresh = _daily(n)
    result, _ = identity.identity_check(fresh, _ref(fresh))
    assert (result.status, result.overlap) == (status, n)


def test_nan_and_zero_closes_never_count_toward_the_overlap():
    fresh = _daily(300)
    ref = _ref(fresh)
    fresh.iloc[:60, fresh.columns.get_loc("Close")] = np.nan      # 60 NaN fresh closes
    ref.iloc[60:70, 0] = np.nan                                   # 10 NaN reference closes
    ref.iloc[70:75, 0] = 0.0                                      # 5 zero reference closes
    result, _ = identity.identity_check(fresh, ref)
    assert result.overlap == 225
    assert result.status == identity.SHORT_OVERLAP                # never a pass
    assert result.median_ratio is not None and not math.isnan(result.median_ratio)


def test_no_reference_is_flagged_and_the_frame_kept():
    fresh = _daily(300)
    result, kept = identity.identity_check(fresh, None)
    assert (result.status, result.overlap, result.median_ratio) == (identity.NO_REFERENCE, 0, None)
    assert kept is fresh


def test_bars_before_the_reference_start_are_dropped():
    """SNDK: Alpaca still serves the old SanDisk years; the reference is the
    new listing. Everything before its first bar goes."""
    fresh = _daily(600, close=np.r_[np.full(300, 55.0), np.full(300, 10.0)])
    new_listing = fresh.iloc[300:]
    result, kept = identity.identity_check(fresh, _ref(new_listing))
    assert result.dropped_before == new_listing.index[0].strftime("%Y-%m-%d")
    assert kept.index[0] == new_listing.index[0] and len(kept) == 300
    assert result.status == identity.OK and result.overlap == 300


def test_to_json_is_the_manifest_identity_object():
    result = identity.IdentityResult(identity.OK, 1.00012345678, 2710, None)
    assert result.to_json() == {"status": "ok", "median_ratio": 1.000123,
                                "overlap": 2710, "dropped_before": None}

import numpy as np
import pandas as pd

from swingbot.core.backtesting import asof_context as ac
from swingbot.core.edge import factors
from tests.helpers import make_ohlcv


def _universe(seed=1, n=300):
    rng = np.random.RandomState(seed)
    frames = {}
    for index, symbol in enumerate(["AAA", "BBB", "CCC", "DDD"]):
        closes = 100 * np.cumprod(1 + rng.normal(0.0002 * (index + 1), 0.01, n))
        frames[symbol] = make_ohlcv(list(closes), start="2024-01-02")
    spy = make_ohlcv(list(100 * np.cumprod(1 + rng.normal(0.0003, 0.008, n))), start="2024-01-02")
    etfs = {"XLK": make_ohlcv(list(100 * np.cumprod(1 + rng.normal(0.0005, 0.01, n))), start="2024-01-02"),
            "XLF": make_ohlcv(list(100 * np.cumprod(1 + rng.normal(0.0001, 0.01, n))), start="2024-01-02")}
    return frames, spy, etfs, {"AAA": "Technology", "BBB": "Technology", "CCC": "Financials"}, {"XLK": "Technology", "XLF": "Financials"}


def test_last_bar_matches_point_in_time_rs_percentile():
    frames, spy, etfs, sot, soe = _universe()
    asof = ac.build_asof(frames, spy, sector_of_ticker=sot, sector_etf_frames=etfs, sector_of_etf=soe)
    rels = [factors.relative_return(frame, spy) for frame in frames.values()]
    for symbol, frame in frames.items():
        assert asof[symbol]["rs_pctile"].iloc[-1] == factors.rs_percentile(frame, spy, universe_rels=rels)


def test_sector_and_combined():
    frames, spy, etfs, sot, soe = _universe()
    asof = ac.build_asof(frames, spy, sector_of_ticker=sot, sector_etf_frames=etfs, sector_of_etf=soe)
    expected = factors.sector_rs_percentile("Technology", etfs, spy, sector_of_etf=soe)
    assert asof["AAA"]["sector_pctile"].iloc[-1] == expected
    assert asof["AAA"]["rs_combined"].iloc[-1] == factors.rs_score(asof["AAA"]["rs_pctile"].iloc[-1], expected)
    assert np.isnan(asof["DDD"]["sector_pctile"].iloc[-1])
    assert asof["DDD"]["rs_combined"].iloc[-1] == asof["DDD"]["rs_pctile"].iloc[-1]


def test_regime_and_warmup_and_row_cleaning():
    frames, spy, etfs, sot, soe = _universe()
    asof = ac.build_asof(frames, spy, sector_of_ticker=sot, sector_etf_frames=etfs, sector_of_etf=soe)
    assert set(asof["AAA"]["regime2_state"].dropna().unique()) <= {"bull_quiet", "bull_volatile", "bear_quiet", "bear_volatile"}
    assert np.isnan(asof["AAA"]["rs_pctile"].iloc[:factors.RS_WINDOW]).all()
    early = ac.asof_row(asof["AAA"], asof["AAA"].index[5])
    assert early["rs_pctile"] is None and set(early) == set(ac.COLUMNS)
    assert ac.asof_row(asof["AAA"], pd.Timestamp("1999-01-01")) == {}

import numpy as np
import pytest

from tests.conftest import make_trend_df
from swingbot.core.edge.factors import relative_return, rs_percentile


def test_outperformer_beats_underperformer():
    spy = make_trend_df(200, +0.05)
    strong = make_trend_df(200, +0.30)
    weak = make_trend_df(200, -0.20)
    assert relative_return(strong, spy) > 0 > relative_return(weak, spy)
    rels = [relative_return(make_trend_df(200, p), spy)
            for p in (-0.2, -0.1, 0.0, 0.1, 0.2, 0.3)]
    assert rs_percentile(strong, spy, universe_rels=rels) > \
           rs_percentile(weak, spy, universe_rels=rels)
    assert rs_percentile(strong, spy, universe_rels=rels) >= 80.0


def test_neutral_without_universe():
    spy = make_trend_df(200, +0.05)
    assert rs_percentile(make_trend_df(200, +0.30), spy) == 50.0


def test_short_history_is_none():
    spy = make_trend_df(200, +0.05)
    assert relative_return(make_trend_df(30, +0.30), spy) is None


def test_rs_cache_roundtrip(tmp_path, monkeypatch):
    from swingbot.core.edge import factors
    monkeypatch.setattr(factors, "RS_CACHE_PATH", str(tmp_path / "rs_cache.json"))
    spy = make_trend_df(200, +0.05)
    cache = factors.refresh_rs_cache({"STRONG": make_trend_df(200, +0.30)}, spy)
    assert "STRONG" in cache["rels"]
    assert factors.load_rs_cache()["rels"] == cache["rels"]


def test_sector_rs_ranks_across_etfs():
    from swingbot.core.edge.factors import sector_rs_percentile
    spy = make_trend_df(200, +0.05)
    etf_dfs = {"XLE": make_trend_df(200, +0.40),
               "XLK": make_trend_df(200, +0.10),
               "XLU": make_trend_df(200, -0.10)}
    sectors = {"XLE": "Energy", "XLK": "Information Technology", "XLU": "Utilities"}
    hot = sector_rs_percentile("Energy", etf_dfs, spy, sector_of_etf=sectors)
    cold = sector_rs_percentile("Utilities", etf_dfs, spy, sector_of_etf=sectors)
    assert hot > cold
    assert sector_rs_percentile("Nonexistent", etf_dfs, spy, sector_of_etf=sectors) == 50.0


def test_rs_score_weights():
    from swingbot.core.edge.factors import rs_score
    assert rs_score(80.0, 40.0) == pytest.approx(0.7 * 80 + 0.3 * 40)


def test_clean_uptrend_aligns_fully():
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core.edge.factors import mtf_alignment
    rng = np.random.RandomState(1)
    df = make_ohlcv(list(100 * np.cumprod(1 + rng.normal(0.0012, 0.01, 400))))
    assert mtf_alignment(df, "bullish") == 3
    assert mtf_alignment(df, "bearish") == 0


def test_chop_scores_low():
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core.edge.factors import mtf_alignment
    rng = np.random.default_rng(7)
    level = 100.0
    prices = [level]
    for _ in range(399):
        level += -0.05 * (level - 100.0) + rng.normal(0, 1.0)
        prices.append(level)
    df = make_ohlcv(np.array(prices), spread_pct=2.0)
    assert mtf_alignment(df, "bullish") <= 1


def test_weekly_frame_shape():
    from swingbot.core.edge.factors import weekly_frame
    df = make_trend_df(400, +0.25)
    w = weekly_frame(df)
    assert list(w.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert len(w) < len(df) / 4


def test_breadth_split_universe():
    from swingbot.core.edge.factors import breadth_pct_above_50ema
    ups = {f"U{i}": make_trend_df(150, +0.3) for i in range(15)}
    downs = {f"D{i}": make_trend_df(150, -0.3) for i in range(15)}
    b = breadth_pct_above_50ema({**ups, **downs})
    assert b == pytest.approx(50.0, abs=1.0)


def test_breadth_none_when_universe_tiny():
    from swingbot.core.edge.factors import breadth_pct_above_50ema
    assert breadth_pct_above_50ema({"A": make_trend_df(150, +0.3)}) is None

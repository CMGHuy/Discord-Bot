import numpy as np

import swingbot.core.macro.sectors as sectors_mod
from swingbot.core.macro.sectors import SECTOR_ETFS, sector_bars
from tests.conftest import make_ohlcv


def test_sector_universe_complete():
    assert len(SECTOR_ETFS) == 11
    assert SECTOR_ETFS["XLK"] == "Technology"
    assert "XLRE" in SECTOR_ETFS and "XLC" in SECTOR_ETFS


def test_injectable_loader_and_missing_sector_skipped(caplog):
    frames = {t: make_ohlcv(np.full(150, 50.0)) for t in list(SECTOR_ETFS) + ["SPY"]}
    frames.pop("XLU")                       # simulate a missing cache file

    def loader(ticker):
        return frames.get(ticker)           # None for XLU

    bars = sector_bars(loader=loader)
    assert "XLU" not in bars                # skipped, not raised
    assert "SPY" in bars and "XLK" in bars
    assert len(bars) == 11                  # 10 sectors + SPY


def test_default_loader_survives_uncached_ticker():
    """The plan named swingbot.core.data.load_cached_daily, which does not
    exist; the real backtest cache is read via backtest_cache.cache_path.
    A ticker with no CSV must degrade to None, never raise."""
    assert sectors_mod._default_loader("NOT_A_REAL_TICKER_XYZ") is None


def _rs_universe():
    """XLE strictly outperforms (+0.3%/day), SPY flat, everyone else -0.1%/day."""
    n = 150
    bars = {"SPY": make_ohlcv(np.full(n, 100.0))}
    for t in SECTOR_ETFS:
        pct = 0.003 if t == "XLE" else -0.001
        bars[t] = make_ohlcv(100.0 * (1 + pct) ** np.arange(n))
    return bars


def test_xle_ranks_first():
    from swingbot.core.macro.sectors import laggards, leaders, sector_rs
    rows = sector_rs(_rs_universe())
    assert len(rows) == 11
    assert rows[0]["etf"] == "XLE" and rows[0]["rank"] == 1
    assert all(rows[i]["composite"] >= rows[i + 1]["composite"] for i in range(10))
    assert leaders(rows)[0]["etf"] == "XLE"
    assert "XLE" not in [r["etf"] for r in laggards(rows)]
    for w in (21, 63, 126):
        assert rows[0][f"rs_{w}"] > 0          # beat SPY on every window


def test_rs_short_history_skipped():
    from swingbot.core.macro.sectors import sector_rs
    bars = _rs_universe()
    bars["XLU"] = bars["XLU"].iloc[-50:]       # < max window + 1
    rows = sector_rs(bars)
    assert "XLU" not in [r["etf"] for r in rows]


def _ranked(order):
    """Build minimal rs_rows in the given etf order (rank 1 first)."""
    return [{"etf": t, "sector": SECTOR_ETFS[t], "rank": i + 1,
             "composite": float(len(order) - i)} for i, t in enumerate(order)]


def test_rotation_postures():
    from swingbot.core.macro.sectors import rotation_state
    risk_on = _ranked(["XLK", "XLY", "XLE", "XLC", "XLF", "XLV", "XLI",
                       "XLB", "XLP", "XLU", "XLRE"])
    assert rotation_state(risk_on)["posture"] == "risk_on"     # XLK+XLY+XLC in top 4
    risk_off = _ranked(["XLP", "XLU", "XLE", "XLV", "XLK", "XLY", "XLC",
                        "XLF", "XLI", "XLB", "XLRE"])
    assert rotation_state(risk_off)["posture"] == "risk_off"   # XLP+XLU+XLV in top 4
    mixed = _ranked(["XLK", "XLP", "XLE", "XLF", "XLY", "XLU", "XLV",
                     "XLC", "XLI", "XLB", "XLRE"])
    assert rotation_state(mixed)["posture"] == "mixed"         # 1 of each camp
    assert "XLK" in rotation_state(risk_on)["note"]            # note names leaders


def test_rotation_no_data_is_unknown():
    from swingbot.core.macro.sectors import rotation_state
    assert rotation_state([])["posture"] == "unknown"


def test_sector_of_static_map(tmp_path, monkeypatch):
    import swingbot.core.macro.sectors as sectors_mod
    from swingbot.core.jsonio import atomic_write_json
    path = tmp_path / "ticker_sectors.json"
    atomic_write_json(str(path), {"NVDA": "Technology", "XOM": "Energy"})
    monkeypatch.setattr(sectors_mod, "TICKER_SECTORS_PATH", str(path))
    sectors_mod._ticker_map_cache = None
    assert sectors_mod.sector_of("NVDA") == "Technology"
    assert sectors_mod.sector_of("nvda") == "Technology"       # case-insensitive
    assert sectors_mod.sector_of("ZZZZ") is None


def test_seed_map_uses_etf_sector_vocabulary():
    """The shipped seed must speak the same sector names as SECTOR_ETFS, or
    a ticker's sector can never be matched to its sector ETF."""
    import swingbot.core.macro.sectors as sectors_mod
    from swingbot.core.jsonio import read_json
    seed = read_json(sectors_mod.TICKER_SECTORS_PATH, default={}) or {}
    assert seed, "seed ticker_sectors.json is missing or empty"
    assert set(seed.values()) <= set(SECTOR_ETFS.values())

"""Regime and relative-strength calculations must share their benchmark data."""
import pandas as pd

from swingbot.core.scanning import scan_run


def test_get_regime_uses_the_provided_frame_without_refetching(monkeypatch):
    frame = pd.DataFrame({"Close": [100.0]})
    captured = []

    monkeypatch.setattr(scan_run.fetch, "_daily_frame_for",
                        lambda *_args: (_ for _ in ()).throw(AssertionError("refetch")))
    monkeypatch.setattr(scan_run, "get_market_regime",
                        lambda actual, ticker: captured.append((actual, ticker)) or "bull")

    assert scan_run.get_regime(frame) == "bull"
    assert captured == [(frame, scan_run.config.MARKET_REGIME_TICKER)]

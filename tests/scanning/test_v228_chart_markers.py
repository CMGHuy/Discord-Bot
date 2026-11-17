"""v228 -- the Discord trade-view chart marks a short-hold daily MFE/MAE.

`_excursion_markers` is the marker block that used to sit inline in
`regenerate_chart_for_trade`; these tests pin that its points are unchanged
and that it now carries `estimate`, decided by exit_quality.is_daily_estimate
(one rule with the admin SPA and the aggregates)."""
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.analytics import journal as journal_mod
from swingbot.core.scanning import lifecycle_embeds as embeds_mod


def _daily():
    idx = pd.bdate_range("2026-11-02", periods=10)
    highs = [101, 102, 103, 104, 105, 109, 104, 103, 102, 101]
    lows = [99, 98, 97, 96, 95, 94, 93, 97, 98, 99]
    return pd.DataFrame({"Open": 100.0, "High": [float(h) for h in highs],
                         "Low": [float(v) for v in lows], "Close": 100.0,
                         "Volume": 1_000.0}, index=idx)


def _trade(**overrides):
    trade = {
        "id": "t1", "ticker": "AAPL", "horizon_key": "4w", "strategy": "RSI",
        "entry": 100.0, "stop_loss": 98.0, "take_profit": 106.0,
        "direction": "bullish", "status": "loss",
        "opened_at": "2026-11-09T14:35:00+00:00",
        "closed_at": "2026-11-10T18:00:00+00:00",
    }
    trade.update(overrides)
    return trade


def _journal(monkeypatch, entry):
    class _Store:
        def get(self, trade_id):
            return entry
    monkeypatch.setattr(journal_mod, "JournalStore", _Store)


def _entry(**overrides):
    entry = {"trade_id": "t1", "mfe_r": 1.24, "mae_r": 1.0,
             "excursion_source": "daily", "holding_days": 1.1}
    entry.update(overrides)
    return entry


def test_markers_keep_todays_points_and_mark_a_short_daily_hold(monkeypatch):
    _journal(monkeypatch, _entry())
    markers = embeds_mod._excursion_markers(_trade(), _daily())
    # Window = 2026-11-09 .. 2026-11-10 (rows 5 and 6): High max 109 on the
    # 9th, Low min 93 on the 10th -- the same points the inline code chose.
    assert markers["mfe"] == (pd.Timestamp("2026-11-09"), 109.0)
    assert markers["mae"] == (pd.Timestamp("2026-11-10"), 93.0)
    assert markers["mfe_r"] == 1.24 and markers["mae_r"] == 1.0
    assert markers["estimate"] is True


def test_bearish_markers_mirror_the_points(monkeypatch):
    _journal(monkeypatch, _entry())
    markers = embeds_mod._excursion_markers(_trade(direction="bearish"), _daily())
    assert markers["mfe"] == (pd.Timestamp("2026-11-10"), 93.0)
    assert markers["mae"] == (pd.Timestamp("2026-11-09"), 109.0)


@pytest.mark.parametrize("overrides, expected", [
    ({"excursion_source": "5min"}, False),
    ({"excursion_source": "hourly"}, False),
    ({"excursion_source": "daily", "holding_days": 2.0}, False),
    ({"excursion_source": "daily", "holding_days": None}, True),   # unknown hold counts as short
    ({"excursion_source": None, "holding_days": 0.5}, False),
])
def test_estimate_follows_the_shared_rule(monkeypatch, overrides, expected):
    _journal(monkeypatch, _entry(**overrides))
    assert embeds_mod._excursion_markers(_trade(), _daily())["estimate"] is expected


def test_no_markers_without_an_entry_or_an_mfe(monkeypatch):
    _journal(monkeypatch, None)
    assert embeds_mod._excursion_markers(_trade(), _daily()) is None
    _journal(monkeypatch, _entry(mfe_r=None))
    assert embeds_mod._excursion_markers(_trade(), _daily()) is None


def test_no_markers_when_the_daily_window_is_empty(monkeypatch):
    _journal(monkeypatch, _entry())
    trade = _trade(opened_at="2026-12-01T14:35:00+00:00", closed_at="2026-12-02T15:00:00+00:00")
    assert embeds_mod._excursion_markers(trade, _daily()) is None


def test_regenerate_hands_the_estimate_flag_to_the_chart(monkeypatch, tmp_path):
    _journal(monkeypatch, _entry())
    monkeypatch.setattr(config, "TRADE_CHART_DIR", str(tmp_path))   # no cached PNG there
    monkeypatch.setattr(embeds_mod, "get_daily_data", lambda ticker: _daily())
    monkeypatch.setattr(embeds_mod, "get_currency_symbol", lambda ticker, default: default)
    captured = {}

    def _fake_generate(*args, **kwargs):
        captured.update(kwargs)
        return str(tmp_path / "fake_view.png")

    monkeypatch.setattr(embeds_mod, "generate_trade_chart", _fake_generate)
    embeds_mod.regenerate_chart_for_trade(_trade())
    assert captured["markers"]["estimate"] is True
    assert captured["markers"]["mfe"] == (pd.Timestamp("2026-11-09"), 109.0)


def test_a_marker_failure_still_draws_the_chart(monkeypatch, tmp_path):
    class _Broken:
        def get(self, trade_id):
            raise RuntimeError("journal down")
    monkeypatch.setattr(journal_mod, "JournalStore", _Broken)
    monkeypatch.setattr(config, "TRADE_CHART_DIR", str(tmp_path))
    monkeypatch.setattr(embeds_mod, "get_daily_data", lambda ticker: _daily())
    monkeypatch.setattr(embeds_mod, "get_currency_symbol", lambda ticker, default: default)
    captured = {}
    monkeypatch.setattr(embeds_mod, "generate_trade_chart",
                        lambda *a, **k: captured.update(k) or "x.png")
    assert embeds_mod.regenerate_chart_for_trade(_trade()) == "x.png"
    assert captured["markers"] is None

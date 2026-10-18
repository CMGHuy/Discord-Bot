"""v162 AH15: a live badge is pinned to the yfinance row of its key and ignores
TRAINING_DATA_SOURCE (training-only); active_rows still follows the training source."""
import dataclasses
import json
import logging

import pytest

from swingbot import config
from swingbot.core.backtesting import registry


def _row(strategy="RSI", horizon=None, source="strategy", **extra):
    row = {"source": source, "strategy": strategy, "horizon": horizon, "status": "WEAK",
           "n": 40, "win_rate": 55.0, "expectancy_r": 0.1, "window": "w",
           "run_date": "2026-10-01"}
    row.update(extra)
    return row


@pytest.fixture
def use_registry(tmp_path, monkeypatch):
    def _use(rows, preferred):
        monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", preferred, raising=False)
        path = tmp_path / "reg.json"
        path.write_text(json.dumps(rows), encoding="utf-8")
        registry.load_registry(path)
    yield _use
    registry.reload_registry()


def test_row_data_source_defaults_to_yfinance():
    assert registry.row_data_source(_row()) == "yfinance"
    assert registry.row_data_source(_row(data_source=None)) == "yfinance"
    assert registry.row_data_source(_row(data_source="alpaca")) == "alpaca"


def test_pick_prefers_then_falls_back_to_yfinance_only():
    yf, al = _row(n=1), _row(n=2, data_source="alpaca")
    assert registry._pick([yf, al], "alpaca") is al
    assert registry._pick([yf, al], "yfinance") is yf
    assert registry._pick([yf], "alpaca") is yf
    assert registry._pick([al], "yfinance") is None
    assert registry._pick([], "alpaca") is None


def test_yfinance_only_registry_answers_as_before(use_registry):
    use_registry([_row(status="VALIDATED", n=99, win_rate=81.0)], "alpaca")
    badge = registry.get_badge("strategy", "RSI")
    assert (badge.status, badge.n, badge.win_rate, badge.data_source) == ("VALIDATED", 99, 81.0, "yfinance")


def test_get_badge_ignores_training_source_and_uses_the_yfinance_row(use_registry):
    rows = [_row(n=10, win_rate=50.0, expectancy_r=0.05),
            _row(n=20, win_rate=60.0, expectancy_r=0.20, window="a", data_source="alpaca")]
    use_registry(rows, "alpaca")
    badge = registry.get_badge("strategy", "RSI")
    assert (badge.n, badge.win_rate, badge.expectancy_r, badge.window, badge.data_source) ==         (10, 50.0, 0.05, "w", "yfinance")


def test_yfinance_preference_ignores_alpaca_rows(use_registry):
    use_registry([_row(n=20, data_source="alpaca")], "yfinance")
    badge = registry.get_badge("strategy", "RSI")
    assert (badge.status, badge.n) == ("WEAK", 0)            # the default badge, not the Alpaca row


def test_each_chain_step_uses_the_yfinance_row_under_an_alpaca_preference(use_registry):
    rows = [_row(horizon="4w", n=11, data_source="alpaca"),
            _row(horizon="4w", n=12),
            _row(horizon=None, n=22, data_source="alpaca"),
            _row(horizon=None, n=23)]
    use_registry(rows, "alpaca")
    assert registry.get_badge("strategy", "RSI", "4w").n == 12        # exact key, yfinance row
    assert registry.get_badge("strategy", "RSI", "2m").n == 23        # pooled step, yfinance row


def test_an_alpaca_only_key_gives_the_default_badge_even_when_preferred(use_registry):
    use_registry([_row(n=20, data_source="alpaca")], "alpaca")
    assert (registry.get_badge("strategy", "RSI").n) == 0


def test_the_choice_is_logged_once_per_key(use_registry, caplog):
    use_registry([_row()], "alpaca")
    with caplog.at_level(logging.INFO, logger=registry.__name__):
        registry.get_badge("strategy", "RSI")
        registry.get_badge("strategy", "RSI")
    lines = [r.getMessage() for r in caplog.records if "registry badge" in r.getMessage()]
    assert lines == ["registry badge strategy/RSI/None: using the yfinance row (preferred yfinance)"]


# --- the committed (yfinance-only) registry answers exactly as before v162 ---------------

def _legacy_badge(records, source, strategy, horizon_key):
    """A verbatim copy of get_badge's pre-v162 lookup: first row in file order."""
    def find(src, strat, hz):
        for r in records:
            if r["source"] == src and r["strategy"] == strat and r.get("horizon") == hz:
                return r
        return None

    rec = (find(source, strategy, horizon_key)
           or find(source, strategy, None)
           or (source == "confluence" and (
               find("strategy", strategy, horizon_key)
               or find("strategy", strategy, None)))
           or find(source, "ALL", horizon_key)
           or find(source, "ALL", None))
    if rec is None:
        return registry.Badge(status="WEAK", n=0, win_rate=0.0, expectancy_r=0.0)
    run_date = rec.get("run_date", "")
    return registry.Badge(status=rec["status"], n=rec["n"], win_rate=rec["win_rate"],
                          expectancy_r=rec["expectancy_r"], window=rec.get("window", ""),
                          run_date=run_date, decay=registry.decay_for(run_date))


def _committed_queries(records):
    from swingbot.core.market.strategy_types import HORIZONS
    strategies = sorted({r["strategy"] for r in records} | {"No Such Strategy"})
    horizons = sorted({r.get("horizon") for r in records if r.get("horizon")}
                      | set(HORIZONS) | {"zz-unknown"}) + [None]
    for source in ("strategy", "confluence", "no-such-source"):
        for strategy in strategies:
            for hz in horizons:
                yield source, strategy, hz


@pytest.mark.parametrize("preferred", ["alpaca", "yfinance"])
def test_committed_registry_answers_exactly_as_before(monkeypatch, preferred):
    registry.reload_registry()
    try:
        records = registry.load_registry()
        assert records and not any(r.get("data_source") for r in records)
        monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", preferred, raising=False)
        for source, strategy, hz in _committed_queries(records):
            got = registry.get_badge(source, strategy, hz)
            want = _legacy_badge(records, source, strategy, hz)
            assert got.data_source == "yfinance"
            assert dataclasses.replace(got, data_source="yfinance") == want, (source, strategy, hz)
        assert registry.active_rows(records, preferred) == records
    finally:
        registry.reload_registry()


# --- one row per key for every reader that walks the registry -------------------------

def _pair():
    return [_row(strategy="Fibonacci", n=10, win_rate=81.6),
            _row(strategy="Fibonacci", n=20, win_rate=70.0, data_source="alpaca"),
            _row(strategy="RSI", n=30, data_source="alpaca")]


def test_active_rows_keeps_one_row_per_key():
    assert [(r["strategy"], r["n"]) for r in registry.active_rows(_pair(), "alpaca")] == \
        [("Fibonacci", 20), ("RSI", 30)]
    assert [(r["strategy"], r["n"]) for r in registry.active_rows(_pair(), "yfinance")] == \
        [("Fibonacci", 10)]                                  # RSI has no yfinance row: dropped


def test_active_rows_defaults_to_the_loaded_registry_and_config(use_registry):
    use_registry(_pair(), "alpaca")
    assert [r["n"] for r in registry.active_rows()] == [20, 30]


def test_admin_registry_rows_show_one_row_per_strategy(monkeypatch):
    from unittest.mock import patch
    from swingbot.admin import queries
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "alpaca", raising=False)
    with patch("swingbot.admin.queries.load_registry", return_value=_pair()), \
         patch("swingbot.admin.queries.load_snapshot", return_value={}), \
         patch("swingbot.admin.queries.refresh_snapshot", return_value={}):
        rows = queries._registry_rows()
    assert [(r["strategy"], r["n"]) for r in rows] == [("Fibonacci", 20), ("RSI", 30)]


def test_edge_decay_report_scores_one_row_per_key(monkeypatch):
    from unittest.mock import patch
    from swingbot.core.analytics import calibration
    from swingbot.core.analytics.insights import edge_decay_report
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance", raising=False)
    seen = []
    with patch("swingbot.core.backtesting.registry.load_registry", return_value=_pair()), \
         patch.object(calibration, "badge_drift",
                      side_effect=lambda closed, entries: seen.append(entries) or []):
        edge_decay_report([])
    assert [(r["strategy"], r["n"]) for r in seen[0]] == [("Fibonacci", 10)]


def test_snapshot_registry_entries_are_one_row_per_key(monkeypatch):
    from unittest.mock import patch
    from swingbot.core.analytics import snapshots
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "alpaca", raising=False)
    seen = []
    with patch("swingbot.core.tracking.performance.TradeLog") as log_cls, \
         patch("swingbot.core.planning.account.load_account_config",
               return_value={"base_balance": 0.0}), \
         patch("swingbot.core.backtesting.registry.load_registry", return_value=_pair()), \
         patch.object(snapshots, "build_snapshot",
                      side_effect=lambda closed, balance, entries, **kw: seen.append(entries) or {}), \
         patch.object(snapshots, "save_snapshot"):
        log_cls.return_value.get_trades.return_value = []
        snapshots.refresh_snapshot()
    assert [r["n"] for r in seen[0]] == [20, 30]

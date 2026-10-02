"""V118-7: the SHORT lane's per-item gates (confirmation, sector RS, RS gate, plan).

Part 1 characterises `short_run._qualified_items` on real bars (the committed
v74 AAPL fixture) BEFORE `qualify_short_item` was extracted from it, so the
extraction is proven behaviour-preserving: kept items, their v2 plan numbers,
the confirmation store and the funnel rows must stay exactly these values.
Part 2 pins the pure helper's own contract.
"""
import datetime as dt
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.infra.state import StateStore
from swingbot.core.scanning import analyze, scan_run, short_run
from swingbot.core.scanning.short_candidates import ShortCandidate
from swingbot.core.scanning.short_funnel import ShortFunnel

from tests.backtesting.test_v74_fixture import load_v74_fixture

DAY = "2025-01-10"
NOW = dt.datetime(2025, 1, 10, 23, 0, tzinfo=dt.timezone.utc)
CANDIDATE = ShortCandidate("AAA", "isolated", "short_universe", DAY, DAY, "ref-1")
# Fixture tuning: the live 2.0% stop floor builds almost no scenario on two
# tickers' bars (known-traps: the empty band); 0.5% makes AAPL's 2025-01-10
# bars yield two bearish scenarios (4w, 3m) at confidence 5.
HARD_FILTERS = dict(min_reward_pct=3.0, max_stop_loss_pct=7.0, min_stop_distance_pct=0.5,
                    min_risk_reward_ratio=1.5, mtf_adjacent_gate=False, confluence_deviation_pct=5.0)
REFERENCE_RELS = [0.3, 0.2, 0.25, 0.1, 0.15, 0.4]


class MemoryState(StateStore):
    """The real confirm/revoke state machine over a dict instead of Postgres."""

    def __init__(self):
        self.entries = {}

    def _read(self, key):
        return dict(self.entries.get(key, {}))

    def _write(self, key, entry):
        self.entries[key] = dict(entry)


def _stock():
    return load_v74_fixture()["AAPL"].loc[:DAY]


def _spy(stock):
    spy = stock.copy()
    close = 400 * (1.0006 ** np.arange(len(stock)))
    spy["Close"], spy["Open"], spy["High"], spy["Low"] = close, close, close * 1.005, close * 0.995
    return spy


@pytest.fixture
def offline(monkeypatch):
    """No journal, no stop flag, no Postgres: the analysis reads only its inputs."""
    monkeypatch.setattr(analyze.trade_log, "update_open_trades", lambda *a, **k: [])
    monkeypatch.setattr(analyze.trade_log, "get_stats", lambda *a, **k: {"win_rate": None, "closed": 0})
    monkeypatch.setattr(analyze, "_check_near_close", lambda *a, **k: [])
    monkeypatch.setattr(analyze.runstate, "is_stop_requested", lambda: False)
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(config, "RS_GATE", True)
    monkeypatch.setattr(config, "RS_LAGGARD_PERCENTILE", 25.0)
    monkeypatch.setattr(config, "SIGNAL_CONFIRMATION_SCANS", 1)
    state = MemoryState()
    monkeypatch.setattr(short_run, "state", state)
    monkeypatch.setattr(scan_run, "state", state)
    return state


def _items():
    stock = _stock()
    ctx = analyze.ExtraScanContext(
        regime=None, min_confluence=2, min_confidence=4,
        rs_cache={"rels": dict(enumerate(REFERENCE_RELS))}, spy_df=_spy(stock), live_prices={},
        hard_filters=HARD_FILTERS, opex_tier=None, now=NOW)
    return analyze.scan_extra_candidate(CANDIDATE, stock, ctx, ["2w", "4w", "2m", "3m"])


def _lane(funnel=None):
    return {"sector_of": {}, "etf_symbol_of": {}, "sector_frames": {}, "spy": _spy(_stock()),
            "regime": None, "regimes": None, "funnel": funnel}


def _kept(items, require_confirmation=True, funnel=None):
    kept = short_run._qualified_items(items, require_confirmation, {"AAA": _stock()}, _lane(funnel))
    return [(item.result.horizon_key, item.rs_combined,
             None if item.plan_v2 is None else (round(item.plan_v2.trigger_price, 6),
                                                 round(item.plan_v2.stop_loss, 6),
                                                 round(item.plan_v2.tp1, 6)))
            for item in kept]


GOLDEN_KEPT = [("4w", 0.0, (235.3463, 236.777322, 231.768746)),
               ("3m", 0.0, (235.3463, 236.649998, 232.087054))]


# --- Part 1: characterisation of the live merge, frozen before the extraction ------

def test_confirmed_items_keep_their_plans(offline):
    funnel = ShortFunnel()
    assert _kept(_items(), funnel=funnel) == GOLDEN_KEPT
    assert funnel.snapshot() == {"bearish/short_universe/isolated/plan/ok": 2,
                                 "bearish/short_universe/isolated/rs/ok": 2}


def test_an_already_confirmed_value_does_not_post_again(offline):
    items = _items()
    _kept(items)
    assert _kept(_items()) == []


def test_rs_leader_is_dropped_and_counted(offline):
    items = _items()
    items[0].rs_percentile = 99.0
    funnel = ShortFunnel()
    assert _kept(items, funnel=funnel) == GOLDEN_KEPT[1:]
    assert funnel.snapshot() == {"bearish/short_universe/isolated/plan/ok": 1,
                                 "bearish/short_universe/isolated/rs/ok": 1,
                                 "bearish/short_universe/isolated/rs/rs_blocked": 1}


def test_a_rejected_plan_revokes_its_confirmation(offline, monkeypatch):
    real = analyze.build_confluence_plan
    monkeypatch.setattr(analyze, "build_confluence_plan", lambda *a, **k: None)
    funnel = ShortFunnel()
    assert _kept(_items(), funnel=funnel) == []
    assert funnel.snapshot() == {"bearish/short_universe/isolated/plan/no_qualifying_target": 2,
                                 "bearish/short_universe/isolated/rs/ok": 2}
    assert all(entry.get("trend") is None for entry in offline.entries.values())
    monkeypatch.setattr(analyze, "build_confluence_plan", real)
    assert _kept(_items()) == GOLDEN_KEPT


def test_check_shows_an_unmet_item_without_a_plan(offline):
    items = _items()
    items[0].requirements = [SimpleNamespace(passed=False, label="x", detail="y", key="min_confluence")]
    kept = _kept(items, require_confirmation=False)
    assert kept == [("4w", 0.0, None), GOLDEN_KEPT[1]]
    assert offline.entries == {}

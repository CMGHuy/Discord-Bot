"""V191-12: a pending band plan's stop, ceiling and sizing input are fixed at
creation -- a knob flip changes none of them; a fill inside the stored
headroom fills, one past it cancels; the edge-of-headroom loss fits the budget."""
import pytest

from swingbot import config
from swingbot.core.planning import account
from swingbot.core.planning import gap_sizing as gs
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_manager_pending import _mgr, _pending

STOP, CEILING = 100.8, 4.25                       # 4.0% under the 105.0 trigger
STAMP = {"rule": gs.RULE_STOP, "down_gap_p99_pct": None, "n_down_gaps": 0,
         gs.BAND_KEY: gs.worst_fill_distance(STOP, CEILING, "bullish")}
CFG = {"balance": 10_000.0, "risk_pct": 1.0, "sizing_mode": "risk_pct", "position_pct": 10.0,
       "max_position_pct": 100.0, "max_position_value_absolute": 0, "max_risk_amount_absolute": 0}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)
    monkeypatch.setattr(account.opex, "size_mult", lambda *a, **k: 1.0)
    monkeypatch.setattr(account, "load_account_config", lambda: dict(CFG))


def _band_plan():
    return _pending(source="confluence", strategy="S/R Confluence", stop_loss=STOP,
                    stop_ceiling_pct=CEILING, stop_moved_by="floor", gap_sizing=dict(STAMP))


def _poll(tmp_path, price):
    store, mgr = _mgr(tmp_path, FakePriceFeed([("AAPL", price)]))
    store.add(_band_plan())
    return store, mgr.poll()


def test_a_fill_inside_the_stored_headroom_fills(tmp_path):
    store, events = _poll(tmp_path, 105.2)                  # 4.18% at the fill
    assert [e.transition for e in events] == ["filled"]


def test_a_fill_past_the_stored_headroom_cancels(tmp_path):
    _, events = _poll(tmp_path, 105.4)                      # 4.36% at the fill
    assert [e.transition for e in events] == ["cancelled_risk_cap"]
    assert events[0].detail["max_planned_loss_pct"] == pytest.approx(CEILING)


def test_a_knob_flip_changes_nothing_on_a_pending_band_plan(tmp_path, monkeypatch):
    before = gs.size_for_plan(_band_plan())
    monkeypatch.setattr(config, "CONFLUENCE_ATR_STOP_FLOOR", 0.0)
    monkeypatch.setattr(config, "LONG_GAP_SIZING", True)
    store, events = _poll(tmp_path, 105.2)
    plan = store.get("p1")
    assert (plan.stop_loss, plan.stop_ceiling_pct, plan.gap_sizing) == (STOP, CEILING, STAMP)
    assert gs.size_for_plan(plan, entry=105.0)["shares"] == before["shares"]


def test_an_account_change_resizes_on_the_same_stamped_distance(monkeypatch):
    monkeypatch.setattr(account, "load_account_config", lambda: {**CFG, "balance": 20_000.0})
    sizing = gs.size_for_plan(_band_plan())
    assert sizing[gs.BAND_KEY] == STAMP[gs.BAND_KEY]
    assert sizing["shares"] * STAMP[gs.BAND_KEY] <= 200.0 + 1e-9


def test_the_loss_at_the_edge_of_the_headroom_fits_the_budget():
    shares = gs.size_for_plan(_band_plan())["shares"]
    worst_fill = STOP + STAMP[gs.BAND_KEY]
    assert shares * (worst_fill - STOP) <= 100.0 + 1e-9

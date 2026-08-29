import datetime as dt
import pytest
from swingbot import config
from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_manager_active import _active
DAY1_A=dt.datetime(2026,8,27,10,0,tzinfo=US_MARKET_TZ); DAY1_B=dt.datetime(2026,8,27,14,0,tzinfo=US_MARKET_TZ); DAY2=dt.datetime(2026,8,28,10,0,tzinfo=US_MARKET_TZ)
@pytest.fixture(autouse=True)
def _rth_on(monkeypatch): monkeypatch.setattr(config,"INTRADAY_RTH_ONLY",True)
def _env(tmp_path,prices):
    feed=FakePriceFeed(); feed.set_series("AAPL",prices)
    store=PlanStore(path=str(tmp_path/"plans.json")); store.add(_active())
    return store,PlanManager(store,feed.get_price)
def test_tp1_stamps_runner_floor_session(tmp_path):
    store,mgr=_env(tmp_path,[110.5]); mgr.poll(now=DAY1_A)
    assert store.get("p1").runner_floor_session=="2026-08-27"
def test_runner_floor_waits_until_next_session(tmp_path):
    store,mgr=_env(tmp_path,[110.5,100.0]); mgr.poll(now=DAY1_A)
    assert mgr.poll(now=DAY1_B)==[]; assert store.get("p1").status=="PARTIAL"
def test_runner_floor_fires_next_session(tmp_path):
    store,mgr=_env(tmp_path,[110.5,100.0]); mgr.poll(now=DAY1_A)
    assert mgr.poll(now=DAY2)[0].detail["reason"]=="tp1_runner_be"
def test_tp2_waits_until_next_session(tmp_path):
    store,mgr=_env(tmp_path,[110.5,130.0,130.0]); p=store.get("p1"); p.tp2=125; store.update(p)
    mgr.poll(now=DAY1_A); assert mgr.poll(now=DAY1_B)==[]
    assert mgr.poll(now=DAY2)[0].detail["reason"]=="tp1_runner_tp2"
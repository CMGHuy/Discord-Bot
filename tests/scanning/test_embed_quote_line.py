"""v171 D5: the alert names the price it was built from; unchanged without a stamp."""
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.scanning import alert_embeds, snapshots
from swingbot.core.scanning.alert_embeds import build_embed, build_simple_alert, quote_line
from tests.scanning.test_embeds_v3 import PERF_STATS_EMPTY, make_item, make_plan_v2

T = "2026-10-15T15:00:00+00:00"


@pytest.fixture(autouse=True)
def _isolated_snapshots(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots, "_SNAPSHOT_PATH", str(tmp_path / "scan_snapshots.json"))


def _stamped(kind="trade", confirmed=True, session="regular", age=2, quote_at=T):
    plan = make_plan_v2()
    plan.issued_at = "2026-10-15T15:00:%02d+00:00" % age
    plan.quote_at, plan.quote_kind = (quote_at if confirmed else None), kind
    plan.quote_session, plan.price_confirmed = session, confirmed
    return plan


def test_no_stamp_no_line():
    assert quote_line(make_plan_v2()) is None
    assert quote_line(SimpleNamespace()) is None


@pytest.mark.parametrize("kwargs, text", [
    ({}, "Price: live trade, 2 s"),
    ({"kind": "mid", "age": 8, "session": "pre-market"}, "Price: bid/ask mid, 8 s, pre-market"),
    ({"kind": "yf-1m", "age": 20, "session": "after-hours"},
     "Price: Yahoo 1-min bar, 20 s, after-hours"),
    ({"kind": "scan", "confirmed": False}, "Price not confirmed live (scan price)"),
    ({"kind": "scan", "confirmed": False, "session": "pre-market"},   # Review Focus 5
     "Price not confirmed live (scan price), pre-market"),
])
def test_quote_line_copy(kwargs, text):
    assert quote_line(_stamped(**kwargs)) == text


def test_legacy_scenario_shows_the_kind_without_an_age():
    scenario = SimpleNamespace(quote_kind="trade", quote_at=T, quote_session="regular",
                               price_confirmed=True)
    assert quote_line(scenario) == "Price: live trade"


def _fields(embed):
    return [(f.name, f.value) for f in embed.fields]


def test_full_embed_adds_exactly_one_quote_field(monkeypatch, tmp_path):
    """Rendered before/after (alert-surface gate): the only difference is the field."""
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    plain = build_embed(make_item(plan_v2=make_plan_v2()), "why", PERF_STATS_EMPTY, None, None)
    monkeypatch.setattr(snapshots, "_SNAPSHOT_PATH", str(tmp_path / "second.json"))  # no diff field
    stamped = build_embed(make_item(plan_v2=_stamped(kind="mid", age=8, session="pre-market")),
                          "why", PERF_STATS_EMPTY, None, None)
    before, after = _fields(plain), _fields(stamped)
    added = [f for f in after if f not in before]
    assert added == [("Quote", "Price: bid/ask mid, 8 s, pre-market")]
    assert [f for f in after if f[0] != "Quote"] == before
    assert plain.description == stamped.description


def test_simple_alert_adds_the_same_line(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "off")
    item = make_item()
    item.plan.quote_kind, item.plan.quote_at = "scan", None
    item.plan.quote_session, item.plan.price_confirmed = "after-hours", False
    plain = _fields(build_simple_alert(make_item()))
    after = _fields(build_simple_alert(item))
    assert [f for f in after if f not in plain] == [
        ("Quote", "Price not confirmed live (scan price), after-hours")]


def test_unstamped_alerts_render_exactly_as_today(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    a = build_embed(make_item(plan_v2=make_plan_v2()), "why", PERF_STATS_EMPTY, None, None)
    assert "Quote" not in [f.name for f in a.fields]
    assert "Quote" not in [f.name for f in build_simple_alert(make_item()).fields]


def test_the_embed_reads_the_v2_plan_before_the_scenario():
    item = make_item(plan_v2=_stamped())
    item.plan.quote_kind, item.plan.price_confirmed = "scan", False
    assert alert_embeds._quote_fields(item) == [("Quote", "Price: live trade, 2 s", False)]

"""v117: the email/push alert prints the same stop figures as the Discord
alert when v115's clamp moved the v2 stop."""
import dataclasses

from swingbot import config
from swingbot.core.infra.notifier import _build_alert_texts
from tests.scanning.test_embeds_v3 import make_item, make_plan_v2


def _clamped_item():
    item = make_item(plan_v2=dataclasses.replace(make_plan_v2(), stop_loss=98.25))
    item.plan.stop_loss, item.plan.stop_distance_pct = 96.0, 4.0
    item.plan.risk_reward_ratio = 2.5
    return item


def _body(item):
    return _build_alert_texts(item, item.plan, item.conf)[1]


def test_a_clamped_stop_reads_the_same_in_the_push_body(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    body = _body(_clamped_item())
    assert "Stop-loss: " in body and "98.25  (-1.8%)" in body
    assert "R:R      : 5.7:1" in body  # 10.00 reward over 1.75 risk, as the embed
    assert "96.00" not in body and "4.0%" not in body and "2.5:1" not in body
    assert "Entry    : " in body and "Target 1 : " in body


def test_an_unclamped_priced_plan_keeps_the_scenario_figures(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item = make_item(plan_v2=dataclasses.replace(make_plan_v2(), tp1=120.0))
    body = _body(item)
    assert "95.00  (-5.0%)" in body
    assert "R:R      : 2.0:1" in body


def test_no_v2_plan_renders_the_scenario_figures(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item = _clamped_item()
    item.plan_v2 = None
    body = _body(item)
    assert "96.00  (-4.0%)" in body
    assert "R:R      : 2.5:1" in body

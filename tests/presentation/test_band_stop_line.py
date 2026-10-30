"""V191-13: a band plan's alert restates the rounded stop, its distance, TP1's
real R:R against it, the horizon and the expiry -- on every channel."""
import pytest

from swingbot import config
from swingbot.admin import app as _admin_app  # noqa: F401 -- registers API first
from swingbot.admin.api_v1 import trades
from swingbot.core.infra import notifier
from swingbot.core.planning.plan_types import plan_to_dict
from swingbot.core.presentation.band_stop import band_stop_line
from swingbot.core.presentation.instructions import Instruction
from swingbot.core.scanning import alert_embeds, execution_embeds
from tests.planning.test_plan_engine_model import _plan

FLOOR_LINE = ("ATR-band stop $96.00 (4.00% from entry, moved out to the ATR floor) · "
              "TP1 2.00R · 4-week swing · expires after 5 bars")


def _band(**kw):
    values = dict(source="confluence", stop_loss=96.0, tp1=108.0, stop_ceiling_pct=4.25,
                  stop_moved_by="floor")
    values.update(kw)
    return _plan(**values)


def test_the_floor_line():
    assert band_stop_line(_band()) == FLOOR_LINE


@pytest.mark.parametrize("moved,why", [("ceiling", "pulled in to the 2× ATR ceiling"),
                                       ("untouched", "at the level")])
def test_the_other_reasons(moved, why):
    assert f"(4.00% from entry, {why})" in band_stop_line(_band(stop_moved_by=moved))


def test_a_short_and_a_sub_dollar_plan():
    short = _plan(direction="bearish", stop_loss=104.0, tp1=92.0, stop_moved_by="floor")
    assert band_stop_line(short).startswith("ATR-band stop $104.00 (4.00% from entry")
    penny = _plan(trigger_price=0.85, stop_loss=0.8075, tp1=0.94, stop_moved_by="floor")
    assert band_stop_line(penny, currency="€").startswith("ATR-band stop €0.8075 (5.00% from entry")


def test_no_line_without_a_band():
    assert band_stop_line(None) is None
    assert band_stop_line(_plan()) is None                      # stop_moved_by None


def test_a_plan_doc_dict_reads_the_same():
    assert band_stop_line(plan_to_dict(_band())) == FLOOR_LINE


def test_every_channel_carries_it(monkeypatch):
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    monkeypatch.setattr(execution_embeds, "ticket_gap_line", lambda plan: None)
    monkeypatch.setattr(alert_embeds, "ticket_gap_line", lambda plan: None)
    item = type("Item", (), {"plan_v2": _band()})()
    assert execution_embeds.ticket_band_line(_band()) == FLOOR_LINE
    assert FLOOR_LINE in notifier._gap_risk_lines(item)
    assert (alert_embeds.BAND_STOP_FIELD, FLOOR_LINE, False) in alert_embeds._gap_risk_fields(item)
    ticket = execution_embeds._with_gap_line(Instruction("PLACE", "AAPL", "bullish", "Buy stop"), _band())
    assert ticket.lines == (FLOOR_LINE,)
    assert trades._band_stop_detail(plan_to_dict(_band())) == FLOOR_LINE
    assert trades._band_stop_detail({}) is None


def test_full_renderings_add_band_line_and_preserve_non_band_output(monkeypatch, tmp_path):
    from swingbot.core.db import notify
    from swingbot.core.planning import account
    from swingbot.core.scanning import snapshots
    from tests.planning.test_gap_sizing import CFG
    from tests.presentation.test_gap_risk_line import _renderings
    from tests.scanning.test_embeds_v3 import make_item

    # Publishing snapshot notifications is unrelated to the rendered alert.
    monkeypatch.setattr(notify, "publish", lambda *a, **kw: None)
    monkeypatch.setattr(snapshots, "_SNAPSHOT_PATH", str(tmp_path / "snapshots.json"))
    monkeypatch.setattr(account, "load_account_config", lambda: dict(CFG))
    monkeypatch.setattr(account.opex, "size_mult", lambda *a, **kw: 1.0)
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    item = make_item(plan_v2=_band())
    item.paper_logged = True
    for channel, text in _renderings(item).items():
        assert FLOOR_LINE in text, channel
    item.plan_v2 = _plan()
    before = _renderings(item)
    monkeypatch.setattr(execution_embeds, "ticket_band_line", lambda plan: None)
    monkeypatch.setattr(alert_embeds, "ticket_band_line", lambda plan: None)
    assert _renderings(item) == before


def test_band_line_precedes_gap_risk_in_all_order_blocks(monkeypatch):
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    monkeypatch.setattr(execution_embeds, "ticket_gap_line", lambda plan: "Risk from gap")
    monkeypatch.setattr(alert_embeds, "ticket_gap_line", lambda plan: "Risk from gap")
    item = type("Item", (), {"plan_v2": _band()})()
    assert notifier._gap_risk_lines(item) == [FLOOR_LINE, "Risk from gap"]
    assert [field[1] for field in alert_embeds._gap_risk_fields(item)] == [FLOOR_LINE, "Risk from gap"]
    instruction = Instruction("PLACE", "AAPL", "bullish", "Buy stop")
    assert execution_embeds._with_gap_line(instruction, _band()).lines == (FLOOR_LINE, "Risk from gap")



def test_detail_payload_exposes_band_line_and_legacy_uses_same_key(monkeypatch):
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    plan = plan_to_dict(_band())
    plan.pop("created_at")  # No calendar window is needed for the band detail.
    assert trades._plan_detail(plan, None)["band_stop_line"] == FLOOR_LINE
    assert trades._legacy_detail({})["band_stop_line"] is None


def test_unknown_horizon_and_entry_fallback_keep_the_line_usable():
    plan = plan_to_dict(_band())
    plan.update(trigger_price=None, entry_price=100.0, horizon_key="custom")
    assert band_stop_line(plan) == FLOOR_LINE.replace("4-week swing", "custom")

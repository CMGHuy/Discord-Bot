import swingbot.config as config
from swingbot.core.scanning.embeds import plan_numbers_for_display


def test_flag_on_display_numbers_come_from_plan(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    from tests.test_plan_engine_model import _plan
    item_plan = _plan(trigger_price=101.0, stop_loss=96.0, tp1=103.0, tp2=108.0)
    legacy = {"entry": 100.0, "stop_loss": 95.0, "take_profit": 106.0,
              "target2": None}
    nums = plan_numbers_for_display(item_plan, legacy)
    assert nums == {"entry": 101.0, "stop_loss": 96.0,
                    "take_profit": 103.0, "target2": 108.0}


def test_flag_shadow_display_numbers_stay_legacy(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "shadow")
    from tests.test_plan_engine_model import _plan
    nums = plan_numbers_for_display(_plan(), {"entry": 100.0, "stop_loss": 95.0,
                                              "take_profit": 106.0,
                                              "target2": None})
    assert nums["entry"] == 100.0


def test_no_plan_falls_back_to_legacy(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    legacy = {"entry": 100.0, "stop_loss": 95.0, "take_profit": 106.0,
              "target2": None}
    assert plan_numbers_for_display(None, legacy) == legacy

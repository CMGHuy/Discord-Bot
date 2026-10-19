"""v176: a give-back close names the level and the best price it came from."""
from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.scanning.embeds import build_plan_event_embed
from swingbot.core.scanning.lifecycle_embeds import _giveback_line
from tests.planning.test_plan_engine_model import _plan

RKLB = dict(ticker="RKLB", direction="bearish", entry_price=63.0, stop_loss=66.0,
            tp1=57.165, tp2=None)
LONG = dict(direction="bullish", entry_price=100.0, stop_loss=95.0, tp1=110.0, tp2=None)


def _giveback_leg(pct=5.0, extreme=49.94, stop=52.437):
    return {"fraction": 0.5, "exit_price": 52.60, "r": 3.47, "reason": "tp1_runner_trail",
            "stop_source": "giveback", "giveback_pct": pct,
            "giveback_extreme": extreme, "giveback_stop": stop}


def _closed(detail, **plan_kw):
    return build_plan_event_embed(_plan(**plan_kw), PlanEvent("p1", "closed", detail))


def _field(embed, name):
    return next((f for f in embed.fields if f.name == name), None)


def test_short_giveback_line_matches_the_spec_example():
    line = _giveback_line(_plan(**RKLB), {"leg": _giveback_leg()})
    assert line == "5% give-back from the low of 49.94: stop 52.44"


def test_long_giveback_line_says_high():
    leg = _giveback_leg(pct=5.0, extreme=120.0, stop=114.0)
    assert _giveback_line(_plan(**LONG), {"leg": leg}) == (
        "5% give-back from the high of 120.00: stop 114.00")


def test_fractional_percent_is_kept():
    leg = _giveback_leg(pct=7.5, extreme=120.0, stop=111.0)
    assert _giveback_line(_plan(**LONG), {"leg": leg}).startswith("7.5% give-back")


def test_no_line_for_a_trail_or_floor_close():
    for source in ("trail", "floor"):
        leg = {"reason": "tp1_runner_trail", "stop_source": source}
        assert _giveback_line(_plan(**LONG), {"leg": leg}) is None


def test_no_line_without_a_leg_or_a_stop_source():
    assert _giveback_line(_plan(**LONG), {}) is None
    assert _giveback_line(_plan(**LONG), {"leg": None}) is None
    assert _giveback_line(_plan(**LONG), {"leg": {"reason": "tp1_runner_trail"}}) is None


def test_no_line_when_a_giveback_leg_lacks_its_inputs():
    leg = {"reason": "tp1_runner_trail", "stop_source": "giveback"}
    assert _giveback_line(_plan(**LONG), {"leg": leg}) is None


def test_closed_embed_adds_the_giveback_field():
    e = _closed({"reason": "tp1_runner_trail", "exit_price": 52.60,
                 "leg": _giveback_leg()}, **RKLB)
    field = _field(e, "Give-back")
    assert field is not None
    assert field.value == "5% give-back from the low of 49.94: stop 52.44"
    assert field.inline is False
    assert _field(e, "Exit").value == "52.60"         # the existing field is kept


def test_closed_embed_has_no_giveback_field_for_a_trail_close():
    e = _closed({"reason": "tp1_runner_trail", "exit_price": 114.9,
                 "leg": {"reason": "tp1_runner_trail", "stop_source": "trail"}}, **LONG)
    assert _field(e, "Give-back") is None


def test_closed_embed_without_a_leg_is_unchanged():
    e = _closed({"reason": "loss", "exit_price": 94.0}, **LONG)
    assert _field(e, "Give-back") is None
    assert [f.name for f in e.fields] == ["Plan (v2)", "Exit"]

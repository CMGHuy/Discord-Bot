from swingbot.core.plan_manager import PlanEvent
from swingbot.core.scanning.embeds import build_plan_event_embed
from tests.test_plan_engine_model import _plan


def _embed(transition, detail=None, **plan_kw):
    return build_plan_event_embed(_plan(**plan_kw),
                                  PlanEvent("p1", transition, detail or {}))


def test_filled_embed():
    e = _embed("filled", {"entry_price": 106.0})
    assert "ENTRY TRIGGERED" in e.title and "🎯" in e.title
    assert any("106" in (f.value or "") for f in e.fields)


def test_expired_and_invalidated_embeds():
    assert "⏱" in _embed("cancelled_expired", {"bars_waited": 6}).title
    assert "❌" in _embed("cancelled_invalidated", {"live_price": 94.0}).title


def test_be_moved_embed():
    e = _embed("be_moved", {"working_stop": 100.0})
    assert "🛡" in e.title
    assert any("100" in (f.value or "") for f in e.fields)


def test_tp1_partial_embed_mentions_runner():
    e = _embed("tp1_partial", {"fraction": 0.5, "exit_price": 110.0, "r": 2.0})
    assert "💰" in e.title
    joined = " ".join(f.value or "" for f in e.fields)
    assert "runner" in joined.lower() and "break-even" in joined.lower()


def test_close_reasons_have_distinct_copy():
    titles = {r: _embed("closed", {"reason": r, "exit_price": 100.0}).title
              for r in ("loss", "scratch", "tp1_runner_be", "tp1_runner_tp2",
                        "tp1_runner_trail")}
    assert len(set(titles.values())) == 5

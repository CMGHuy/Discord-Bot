"""v79 guard: live confidence scoring reads an UNEXPANDED track record.

`analyze.py` feeds `trade_log.get_stats(base_level)`'s win rate into
`confidence.score_confidence` as `track_record`, where it can shift a
scenario's posted confidence level by +/-1. That formula pays every counted
win the scenario's own reward:risk -- but a scaled-out position's TP1 leg
banks roughly 1R, not the full RR. Counting TP1 legs as separate wins there
would systematically overstate the empirical win rate and silently re-tier
live alerts, which v79 never intended to touch.

So this one call site must keep passing `expand=False`. An AST check rather
than a behavioural one because reaching line 733 of `_scan_one` means
standing up a full scan (price frames, level maps, regime, HTF) for a
single keyword -- the assertion here is exactly the invariant, with none of
that surface area.
"""

import ast
import inspect

import pytest

from swingbot.core.scanning import analyze
from swingbot.core.scanning import confidence as confidence_mod
from swingbot.core.tracking.performance import TradeLog


def _get_stats_calls(module) -> list[ast.Call]:
    tree = ast.parse(inspect.getsource(module))
    return [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in ("get_stats", "get_extended_stats")
    ]


def test_analyze_reads_stats_with_leg_expansion_off():
    calls = _get_stats_calls(analyze)
    assert calls, "expected analyze.py to still build a track record from get_stats"
    for call in calls:
        kwargs = {kw.arg: kw.value for kw in call.keywords}
        assert "expand" in kwargs, (
            "analyze.py's get_stats call must pin expand explicitly -- the "
            "default is v79's leg-expanded win rate, which must not reach "
            "score_confidence"
        )
        assert isinstance(kwargs["expand"], ast.Constant) and kwargs["expand"].value is False


def test_confidence_expectancy_factor_is_unchanged_by_leg_expansion(tmp_path):
    """End of the same wire: the number analyze hands `score_confidence` for
    a scaled-out position is the pre-v79 blended one."""
    trade = {
        "status": "win", "shares": 10, "entry": 100.0, "direction": "bullish",
        "stop_loss": 95.0, "exit_price": 118.0, "confidence_level": 3,
        "legs": [
            {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"},
            {"fraction": 0.5, "exit_price": 90.0, "r": -0.5, "reason": "manual"},
        ],
    }
    log = TradeLog(path=str(tmp_path / "trades.json"))

    stats = log.get_stats(3, trades=[trade], expand=False)
    track_record = (stats["win_rate"], stats["closed"])
    assert track_record == (100.0, 1)

    # ...and not the leg-expanded (50.0, 2) the dashboards now show.
    expanded = log.get_stats(3, trades=[trade])
    assert (expanded["win_rate"], expanded["closed"]) == (50.0, 2)


def test_score_confidence_still_reads_track_record():
    """If the parameter ever goes away, the guard above is measuring nothing."""
    assert "track_record" in inspect.signature(confidence_mod.score_confidence).parameters

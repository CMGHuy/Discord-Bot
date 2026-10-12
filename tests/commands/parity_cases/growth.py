"""Reply-parity cases for swingbot/commands/growth.py (v153 SP7)."""
import os
import tempfile

from swingbot.commands import growth as growth_mod
from tests.commands.reply_harness import ParityCase

_BASE_STATS = {"expectancy_r": None, "n_closed": 0, "risk_pct": 1.0}


def _stub_stats(**extra):
    def stub(monkeypatch):
        monkeypatch.setattr(growth_mod, "_collect_stats", lambda target=10.0: {**_BASE_STATS, **extra})
    return stub


def _stub_stats_with_chart(monkeypatch):
    path = os.path.join(tempfile.mkdtemp(prefix="v153-growth-"), "mc_fan.png")
    with open(path, "wb") as f:
        f.write(b"\x89PNG")
    _stub_stats(mc_chart_path=path)(monkeypatch)


def _stub_kill(on: bool):
    state = {"on": on, "reason": "manual" if on else None}

    def stub(monkeypatch):
        monkeypatch.setattr("swingbot.core.edge.throttle.kill_state", lambda: dict(state))
        monkeypatch.setattr("swingbot.core.edge.throttle.set_kill",
                            lambda on, reason=None: {"on": on, "reason": reason})
    return stub


def _stub_portfolio(monkeypatch):
    state = {
        "open_heat": 4.5, "heat_cap": 6.0, "sector_heat": {"Technology": 2.5, "Energy": 1.0},
        "clusters": [["AAA", "BBB"]], "throttle_mult": 0.5, "paused": False,
        "kill": {"on": False, "reason": None},
        "growth": {"current_multiple": 1.32, "pct_to_target": 12.1},
    }
    # SP2 binds collect_portfolio_state under this local name in growth.py.
    monkeypatch.setattr(growth_mod, "_collect_portfolio_state", lambda: dict(state))


_GROWTH_PATH = {"realized_daily_growth": 0.001, "on_track_vs": {8: True},
                "current_multiple": 1.2, "pct_to_target": 8.0}

CASES = [
    ParityCase("growth_report", growth_mod.handle_growth, args=(5.0,), stub=_stub_stats()),
    ParityCase("growth_report_with_path_line", growth_mod.handle_growth,
               stub=_stub_stats(growth_path=_GROWTH_PATH)),
    ParityCase("growth_report_with_mc_chart", growth_mod.handle_growth,
               stub=_stub_stats_with_chart),
    ParityCase("growth_target_not_above_1x", growth_mod.handle_growth, args=(1.0,),
               stub=_stub_stats(), expect="error"),
    ParityCase("killswitch_status_off", growth_mod.handle_killswitch, stub=_stub_kill(False)),
    ParityCase("killswitch_status_on", growth_mod.handle_killswitch, args=("status",),
               stub=_stub_kill(True)),
    ParityCase("killswitch_on", growth_mod.handle_killswitch, args=("on",), stub=_stub_kill(False)),
    ParityCase("killswitch_off", growth_mod.handle_killswitch, args=("off",), stub=_stub_kill(True)),
    ParityCase("portfolio", growth_mod.handle_portfolio, stub=_stub_portfolio),
]

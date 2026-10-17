"""v158 WC10: every live backtest script takes --instrument (v136 rule 2).

v1, the default, runs exactly as before: the only new step is the guard, which
is silent under v1. v2 exits before any work, naming the script and the phase
that wires its v2 path (cli.require_v1)."""
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from swingbot.core.backtesting.instrument import cli

ROOT = Path(__file__).resolve().parents[2]
for _sub in ("scripts/backtest", "scripts/data"):
    if str(ROOT / _sub) not in sys.path:
        sys.path.insert(0, str(ROOT / _sub))

WALK_FORWARD = "phase 6 (cutover: walk-forward on the v2 folds)"

# script module -> (the argv it requires besides --instrument, the owner its v2 refusal names)
SCRIPTS = {
    "tune_exit_v2": ([], "phase 6 (cutover: v2 exit tuning on the purged folds)"),
    "tune_confluence_gates": ([], "phase 5 (scan replay under v2)"),
    "measure_arms": (["--knob", "X=1", "--stage", "pilot", "--out", "arms.json"],
                     "phase 5 (v2 stage table)"),
    "wf_run": ([], WALK_FORWARD),
    "wf_components": ([], WALK_FORWARD),
    "permutation_test": ([], WALK_FORWARD),
    "quarterly_revalidation": ([], WALK_FORWARD),
    "emit_cohort_registry": (["--backtest", "replay.json"],
                             "phase 6 (registry instrument_version column)"),
    "ablation": ([], WALK_FORWARD),
    "measure_strategy_arm": (["--strategy", "RSI", "--component-json", '{"X": 1}',
                              "--out", "arms.json"], WALK_FORWARD),
}


class _Reached(Exception):
    """Raised by the spy standing in for cli.require_v1: main got that far."""


def _main(monkeypatch, module, *extra):
    mod = importlib.import_module(module)
    monkeypatch.setattr(sys, "argv", [f"{module}.py", *SCRIPTS[module][0], *extra])
    return mod.main()


@pytest.mark.parametrize("module", sorted(SCRIPTS))
def test_help_lists_the_flag(module, monkeypatch, capsys):
    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, module, "--help")
    assert exc.value.code == 0
    assert "--instrument {v1,v2}" in capsys.readouterr().out


@pytest.mark.parametrize("module", sorted(SCRIPTS))
def test_v2_exits_naming_the_script_and_the_owning_phase(module, monkeypatch):
    with pytest.raises(SystemExit) as exc:
        _main(monkeypatch, module, "--instrument", "v2")
    message = str(exc.value)
    assert f"{module}.py: --instrument v2 is not wired yet" in message
    assert SCRIPTS[module][1] in message


@pytest.mark.parametrize("extra", [(), ("--instrument", "v1")], ids=["default", "explicit-v1"])
@pytest.mark.parametrize("module", sorted(SCRIPTS))
def test_v1_is_handed_to_the_guard_right_after_parsing(module, extra, monkeypatch):
    """The spy stops main at the guard, so nothing after it ran; under v1 (the
    default and explicit) the guard receives v1, and the real guard is silent
    for v1 (test_instrument_cli.py)."""
    seen = []

    def spy(spec, script, owner):
        seen.append((spec.version, script, owner))
        raise _Reached

    mod = importlib.import_module(module)
    monkeypatch.setattr(mod, "instrument_cli", SimpleNamespace(
        add_instrument_arg=cli.add_instrument_arg, spec_from_args=cli.spec_from_args,
        require_v1=spy))
    with pytest.raises(_Reached):
        _main(monkeypatch, module, *extra)
    assert seen == [("v1", f"{module}.py", SCRIPTS[module][1])]

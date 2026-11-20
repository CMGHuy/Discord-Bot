"""v238 V238-7: validate_component --gate additive, Stages -1 and 0, and the
flag-conflict table (old messages verbatim)."""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "scripts" / "backtest") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import validate_component as vc  # noqa: E402

OTHER_WR = next(name for name in vc.WR_STATISTICS if name != "standardised")


def _row(ticker, day, r, strategy="MACD"):
    entry = date(2021, 1, 4) + timedelta(days=day)
    return {"ticker": ticker, "strategy": strategy, "horizon_key": "3m",
            "entry_date": entry.isoformat(), "outcome": "win" if r > 0 else "loss",
            "r_multiple": r, "planned_rr": 2.0, "source": "strategy", "direction": "bullish"}


def _arms(n_added=40, drop=0):
    baseline = [_row(f"B{i % 8}", 7 * i, 2.0 if i % 3 == 0 else -1.0) for i in range(40)]
    added = [_row(f"A{i % 8}", 7 * i + 1, 2.0 if i % 2 == 0 else -1.0, strategy="Turtle Soup")
             for i in range(n_added)]
    return baseline, baseline[drop:] + added


def _write(tmp_path, baseline, component, provenance=None):
    blob = {"baseline": baseline, "component": component}
    blob["provenance"] = {"r_basis": "net"} if provenance is None else provenance
    if provenance == "absent":
        del blob["provenance"]
    path = tmp_path / "arms.json"
    path.write_text(json.dumps(blob), encoding="utf-8")
    return path


def _argv(path, stage, *extra, gate="additive"):
    return ["--gate", gate, "--stage", stage, "--arms", str(path), "--title", "t", "--window", "w",
            "--bespoke-instrument", "test fixture", "--resamples", "300", *extra]


@pytest.fixture(autouse=True)
def no_data(monkeypatch):
    monkeypatch.setattr(vc.cache_dir_source, "resolve", lambda args: None)


def _parser_error(capsys, argv):
    with pytest.raises(SystemExit) as caught:
        vc.main(argv)
    assert caught.value.code == 2
    return capsys.readouterr().err


def test_reachability_passes_an_add_only_net_arm(tmp_path, capsys):
    path = _write(tmp_path, *_arms())
    assert vc.main(_argv(path, "reachability")) == 0
    out = capsys.readouterr().out
    assert "added=40 displaced=0" in out and "REACHABLE" in out


def test_reachability_lists_each_displaced_row_with_its_cause(tmp_path, capsys):
    path = _write(tmp_path, *_arms(drop=2))
    assert vc.main(_argv(path, "reachability")) == 0
    out = capsys.readouterr().out
    assert "displaced=2" in out
    assert out.count(f"cause: {vc.DISPLACEMENT_CAUSE}") == 2


@pytest.mark.parametrize("provenance", ["absent", {}, {"r_basis": "gross"}, {"r_basis": "bogus"}])
def test_a_missing_or_non_net_basis_is_refused_even_when_bespoke(tmp_path, capsys, provenance):
    path = _write(tmp_path, *_arms(), provenance=provenance)
    assert vc.main(_argv(path, "reachability")) == 1
    err = capsys.readouterr().err
    assert err.startswith("refused:r-basis -- ") and err.rstrip().endswith("Budget intact.")


def test_the_basis_gate_never_fires_for_the_win_rate_gate(tmp_path, capsys):
    path = _write(tmp_path, *_arms(), provenance={"r_basis": "gross"})
    vc.main(_argv(path, "reachability", gate="win_rate"))
    assert "refused:r-basis" not in capsys.readouterr().err


def test_a_component_that_adds_nothing_is_misuse(tmp_path, capsys):
    baseline, _ = _arms()
    path = _write(tmp_path, baseline, baseline)
    assert vc.main(_argv(path, "reachability")) == 1
    err = capsys.readouterr().err
    assert err.startswith("ADDITIVE_GATE_MISUSE") and "--gate win_rate (v72)" in err


def test_a_changed_shared_row_is_misuse(tmp_path, capsys):
    baseline, component = _arms()
    component[0] = dict(component[0], r_multiple=5.0)
    path = _write(tmp_path, baseline, component)
    assert vc.main(_argv(path, "mde", "--expected-own-r", "0.5", "--expected-sd-r", "1")) == 1
    assert capsys.readouterr().err.startswith("ADDITIVE_GATE_MISUSE")


@pytest.mark.parametrize("flags", [["--expected-own-r", "0.5"],
                                   ["--expected-own-r", "0.5", "--expected-sd-r", "-1"]])
def test_stage0_refuses_missing_or_bad_frozen_inputs(tmp_path, capsys, flags):
    assert vc.main(_argv(_write(tmp_path, *_arms()), "mde", *flags)) == 1
    assert capsys.readouterr().err.startswith("refused:additive-mde-unfrozen -- ")


def test_stage0_resolves_when_the_frozen_effect_clears_the_mde(tmp_path, capsys):
    # MDE = (1.96 + 0.8416) * 1.0 / sqrt(40) = 0.443R < 0.5R
    path = _write(tmp_path, *_arms())
    assert vc.main(_argv(path, "mde", "--expected-own-r", "0.5", "--expected-sd-r", "1")) == 0
    out = capsys.readouterr().out
    assert "added N (closed)   : 40" in out and "RESOLVABLE" in out


def test_stage0_refuses_when_the_mde_exceeds_the_frozen_effect(tmp_path, capsys):
    path = _write(tmp_path, *_arms())
    assert vc.main(_argv(path, "mde", "--expected-own-r", "0.3", "--expected-sd-r", "1")) == 1
    err = capsys.readouterr().err
    assert err.startswith("refused:additive-mde -- ") and "budget intact" in err


ADDITIVE_CONFLICTS = [
    (["--gap-reclaim"], "the additive gate is a different gate"),
    (["--mechanism-json", "m.json"], "--mechanism-json replaces v72 clause 6; the additive gate has no"),
    (["--dryup-mechanism"], "--headroom-mechanism score v72 clause 6; the additive gate has no"),
    (["--headroom-mechanism"], "--headroom-mechanism score v72 clause 6; the additive gate has no"),
    (["--wr-statistic", OTHER_WR], "the additive gate judges win rate against its own break-even"),
    (["--train-effect-from-arms"], "the additive gate freezes --expected-own-r"),
]


@pytest.mark.parametrize("flags, message", ADDITIVE_CONFLICTS)
def test_additive_flag_conflicts(capsys, flags, message):
    assert message in _parser_error(capsys, _argv("a.json", "mde", *flags))


@pytest.mark.parametrize("flags", [["--expected-own-r", "0.2"], ["--expected-sd-r", "1"]])
def test_the_frozen_stage0_flags_need_the_additive_gate(capsys, flags):
    err = _parser_error(capsys, _argv("a.json", "mde", *flags, gate="win_rate"))
    assert "freeze the additive gate's Stage 0; pass --gate additive" in err


OLD_CONFLICTS = [
    (["--dryup-mechanism", "--headroom-mechanism"], "--dryup-mechanism and --headroom-mechanism are different clause-6 readings; pass one"),
    (["--gate", "harvest", "--mechanism-json", "m.json"], "--mechanism-json replaces v72 clause 6; the v92 harvest gate has no mechanism clause"),
    (["--gate", "harvest", "--dryup-mechanism"], "--dryup-mechanism scores v72 clause 6; the v92 harvest gate has no mechanism clause"),
    (["--gate", "harvest", "--wr-statistic", OTHER_WR], "--wr-statistic selects the v72 win-rate clause-1 statistic; the v92 harvest gate has no win-rate clause"),
    (["--gate", "harvest", "--gap-reclaim"], "--gap-reclaim scores the v72 win-rate funnel; the v92 harvest gate is a different gate"),
]


@pytest.mark.parametrize("flags, message", OLD_CONFLICTS)
def test_the_existing_conflict_messages_are_verbatim(capsys, flags, message):
    argv = ["--stage", "mde", "--arms", "a.json", "--title", "t", "--window", "w", *flags]
    assert message in _parser_error(capsys, argv)


def test_every_stage_has_an_additive_runner():
    assert set(vc._ADDITIVE_STAGES) == set(vc._STAGES)
    assert "additive" in vc._GATES


def test_the_stage_runner_honours_a_monkeypatched_stage(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(vc, "stage_mde", lambda args: seen.append(args.gate) or 0)
    monkeypatch.setattr(vc, "stage_additive_mde", lambda args: seen.append(args.gate) or 0)
    path = _write(tmp_path, *_arms())
    assert vc.main(_argv(path, "mde", gate="win_rate")) == 0
    assert vc.main(_argv(path, "mde")) == 0
    assert seen == ["win_rate", "additive"]

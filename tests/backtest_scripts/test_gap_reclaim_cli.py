"""V192-18: --gap-reclaim in the funnel judge and the permutation CLI, and the report script."""
import dataclasses
import importlib.util
import json
import runpy
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.backtesting.arms import gap_reclaim_census as census_mod
from swingbot.core.backtesting.arms.provenance import build_stamp
from swingbot.core.backtesting.arms.windows import ALL_HORIZONS, STAGES
from tests.backtesting.arms.test_gap_reclaim_clauses import veto_arms
from tests.backtesting.arms.test_gap_reclaim_report import _census_for
from tests.backtesting.test_validate_component_stamps import vc

ROOT = Path(__file__).resolve().parent.parent.parent
PERMUTATION = ROOT / "scripts" / "backtest" / "permutation_test.py"
_spec = importlib.util.spec_from_file_location("gap_reclaim_report_script",
                                               ROOT / "scripts" / "reports" / "gap_reclaim_report.py")
report_script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(report_script)

VETO = {"MARKET_ENTRY_NEXT_OPEN": True, "GAP_RECLAIM_ATR": 0.25}
NEXT_OPEN = {"MARKET_ENTRY_NEXT_OPEN": True}
BASELINE, COMPONENT, REPRICED = veto_arms()
UNIVERSE = sorted({t.ticker for t in BASELINE})


@pytest.fixture(autouse=True)
def _world(monkeypatch):
    from swingbot.core.marketdata import training_data
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance")   # v162: no store in tests
    training_data.reset()
    monkeypatch.setattr(vc, "_full_universe", lambda: UNIVERSE)
    monkeypatch.setattr(report_script, "_spy_frame", lambda: None)
    yield
    training_data.reset()


def write_arms(tmp_path, stage, *, name="arms", knobs=VETO, baseline_knobs=NEXT_OPEN, census=True,
               census_knobs=None, census_rows=None, component=None):
    stamp = build_stamp(stage=stage, signal_window=STAGES[stage].signal_window, universe=UNIVERSE,
                        horizons=ALL_HORIZONS, engines=("confluence", "strategy"), knob_delta=knobs,
                        engine_hash_baseline="h", engine_hash_component="h", changed_outcomes=1,
                        preregistration="docs/superpowers/specs/2026-10-24-v192-gap-toward-stop-reclaim-design.md",
                        baseline_knob_delta=baseline_knobs)
    path = tmp_path / f"{name}.json"
    rows = {"baseline": [dataclasses.asdict(t) for t in BASELINE],
            "component": [dataclasses.asdict(t) for t in (component or COMPONENT)]}
    path.write_text(json.dumps({"provenance": stamp, **rows}), encoding="utf-8")
    if census:
        census_rows = _census_for(BASELINE, REPRICED) if census_rows is None else census_rows
        side = {"knob_delta": census_knobs or knobs, "rows": census_rows,
                "summary": census_mod.reachability_summary(census_rows)}
        census_mod.sidecar_path(path).write_text(json.dumps(side), encoding="utf-8")
    return path


def _vc(*argv):
    return vc.main([*argv, "--title", "v192", "--window", "w", "--resamples", "200", "--gap-reclaim"])


# --- validate_component ------------------------------------------------------------------------

def test_reachability_prints_the_census_and_passes_an_armed_veto(tmp_path, capsys):
    out_json = tmp_path / "stage-1.json"
    assert _vc("--stage", "reachability", "--arms", str(write_arms(tmp_path, "pilot")),
               "--out-json", str(out_json)) == 0
    out = capsys.readouterr().out
    assert "REACHABLE" in out and '"armed": 30' in out
    assert json.loads(out_json.read_text())["verdict"] == census_mod.REACHABLE


def test_reachability_refuses_a_census_where_nothing_armed(tmp_path, capsys):
    flat = [dict(row, decision="open", reclaimed=False) for row in _census_for(BASELINE, REPRICED)]
    assert _vc("--stage", "reachability", "--arms", str(write_arms(tmp_path, "pilot", census_rows=flat))) == 1
    assert "refused:zero-diff" in capsys.readouterr().err


@pytest.mark.parametrize("stage,funnel", [("pilot", "reachability"), ("validation", "validation")])
def test_a_missing_census_is_refused(tmp_path, capsys, stage, funnel):
    path = write_arms(tmp_path, stage, census=False)
    assert _vc("--stage", funnel, "--arms", str(path), "--permutation-p", "0.01") == 1
    assert "refused:no-gap-reclaim-sidecar" in capsys.readouterr().err


def test_a_census_of_another_run_is_refused(tmp_path, capsys):
    path = write_arms(tmp_path, "validation", census_knobs={"MARKET_ENTRY_NEXT_OPEN": True, "GAP_RECLAIM_ATR": 0.5})
    assert _vc("--stage", "validation", "--arms", str(path), "--permutation-p", "0.01") == 1
    assert "refused:no-gap-reclaim-sidecar" in capsys.readouterr().err


def test_mde_uses_the_week_cluster_only_under_the_flag(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(vc, "mde_paired", lambda *a, **k: seen.append(k["cluster"]) or 1.0)
    path = write_arms(tmp_path, "selection")
    _vc("--stage", "mde", "--arms", str(path), "--train-effect-pp", "5")
    vc.main(["--stage", "mde", "--arms", str(path), "--title", "t", "--window", "w", "--train-effect-pp", "5"])
    assert seen == ["week", "ticker"]


def test_selection_reads_the_g_axis_and_ties_to_the_smaller_g(tmp_path, capsys):
    grid = []
    for g in ("0.1", "0.25", "0.5"):
        knobs = {"MARKET_ENTRY_NEXT_OPEN": True, "GAP_RECLAIM_ATR": float(g)}
        grid += ["--grid-arms", f"{g}={write_arms(tmp_path, 'selection', name=f'g{g}', knobs=knobs)}"]
    out_json = tmp_path / "stage1.json"
    assert _vc("--stage", "selection", *grid, "--out-json", str(out_json)) == 0
    out = capsys.readouterr().out
    assert "g=0.1 eligible=True" in out and "verdict=selected selected=0.1" in out
    assert json.loads(out_json.read_text())["selected"] == 0.1


def test_validation_scores_the_strata_and_writes_the_result(tmp_path, capsys):
    out_json = tmp_path / "stage3.json"
    assert _vc("--stage", "validation", "--arms", str(write_arms(tmp_path, "validation")),
               "--permutation-p", "0.01", "--out-json", str(out_json)) == 0
    result = json.loads(out_json.read_text())
    assert result["verdict"] == "PASS" and result["cluster"] == "week"
    assert result["split"]["repriced"] == 30 and result["split"]["removed"] == 60
    mechanism = next(c for c in result["clauses"] if c["name"] == "mechanism")
    assert mechanism["verdict"] == "PASS" and "unchanged" in mechanism["detail"]


@pytest.mark.parametrize("extra", [["--gate", "harvest"], ["--headroom-mechanism"], ["--wr-statistic", "pooled"]])
def test_conflicting_flags_are_a_parser_error(tmp_path, extra):
    with pytest.raises(SystemExit):
        _vc("--stage", "validation", "--arms", str(write_arms(tmp_path, "validation")), *extra)


# --- permutation_test --------------------------------------------------------------------------

def _permutation(argv):
    namespace = runpy.run_path(str(PERMUTATION))
    main = namespace["main"]
    main.__globals__["_full_universe"] = lambda: UNIVERSE
    return main(argv)


def test_permutation_runs_the_repriced_null_and_writes_its_json(tmp_path, capsys):
    out_json = tmp_path / "perm.json"
    path = write_arms(tmp_path, "validation")
    assert _permutation(["--arms", str(path), "--gap-reclaim", "--n", "50", "--out-json", str(out_json)]) == 0
    out = json.loads(out_json.read_text())
    assert out["repriced"] == 30 and out["n"] == 50 and out["verdict"] in ("REAL", "INDISTINGUISHABLE FROM LUCK")
    assert "re-priced trades held" in out["instrument"]


def test_permutation_without_the_flag_is_the_unchanged_v72_null(tmp_path, capsys):
    """veto_arms re-prices with the same outcome, so population_split sees no changed pair and
    the v72 removal-label null runs as today: no 'repriced' key, changed == 0."""
    path = write_arms(tmp_path, "validation")
    assert _permutation(["--arms", str(path), "--n", "20"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert "repriced" not in out and out["changed"] == 0


def test_permutation_refuses_a_missing_census(tmp_path, capsys):
    path = write_arms(tmp_path, "validation", census=False)
    assert _permutation(["--arms", str(path), "--gap-reclaim", "--n", "20"]) == 1
    assert "refused:no-gap-reclaim-sidecar" in capsys.readouterr().err


# --- gap_reclaim_report.py ---------------------------------------------------------------------

def _report(tmp_path, *extra):
    out_json, out_md = tmp_path / "report.json", tmp_path / "report.md"
    code = report_script.main(["--arms", str(write_arms(tmp_path, "validation")), "--out-json", str(out_json),
                               "--out-md", str(out_md), "--resamples", "200", *extra])
    return code, out_json, out_md


def test_the_report_script_writes_json_and_markdown(tmp_path):
    code, out_json, out_md = _report(tmp_path)
    assert code == 0
    data = json.loads(out_json.read_text())
    assert data["n"] == {"baseline": 300, "component": 270} and data["regime"] == {
        "unavailable": "no SPY frame in the selected training data"}
    md = out_md.read_text()
    for text in ("# v192 gap-reclaim report", "| removed |", "| repriced |", "Earnings proximity: unavailable"):
        assert text in md


def test_the_report_cuts_by_regime_when_spy_is_available(tmp_path, monkeypatch):
    import pandas as pd
    monkeypatch.setattr(report_script, "regime_series",
                        lambda spy: pd.Series(["bull_quiet"] * len(spy.index), index=spy.index))
    spy = pd.DataFrame({"Close": 1.0}, index=pd.to_datetime([t.entry_date for t in BASELINE]))
    section = report_script.regime_section(BASELINE, COMPONENT, spy)
    assert set(section) == {"bull_quiet", "unknown"}           # the added trades fall on Tuesdays
    assert section["bull_quiet"]["n_baseline"] == 300


def test_the_basis_section_reads_a_fold_train_basis_pair(tmp_path):
    basis = write_arms(tmp_path, "selection", name="basis", knobs=NEXT_OPEN, baseline_knobs=None, census=False)
    code, out_json, _ = _report(tmp_path, "--basis", str(basis))
    assert code == 0
    section = json.loads(out_json.read_text())["basis"]
    assert section["stage"] == "selection" and section["close_fill"]["n"] == 300 and section["next_open"]["n"] == 270


@pytest.mark.parametrize("stage,knobs,baseline_knobs,token", [
    ("validation", NEXT_OPEN, None, "refused:basis-on-validation"),
    ("selection", VETO, NEXT_OPEN, "refused:not-a-basis-pair"),
])
def test_a_wrong_basis_pair_is_refused(tmp_path, capsys, stage, knobs, baseline_knobs, token):
    basis = write_arms(tmp_path, stage, name="basis", knobs=knobs, baseline_knobs=baseline_knobs, census=False)
    code, out_json, _ = _report(tmp_path, "--basis", str(basis))
    assert code == 1 and token in capsys.readouterr().err and not out_json.exists()


def test_the_report_refuses_arms_without_a_census_or_whole_window_rows(tmp_path, capsys):
    path = write_arms(tmp_path, "validation", census=False)
    assert report_script.main(["--arms", str(path), "--out-json", str(tmp_path / "r.json"),
                               "--out-md", str(tmp_path / "r.md")]) == 1
    assert "refused:no-gap-reclaim-sidecar" in capsys.readouterr().err
    folds = tmp_path / "folds.json"
    folds.write_text(json.dumps({"provenance": {}, "folds": []}), encoding="utf-8")
    assert report_script.main(["--arms", str(folds), "--out-json", str(tmp_path / "r.json"),
                               "--out-md", str(tmp_path / "r.md")]) == 1
    assert "refused:no-whole-window" in capsys.readouterr().err

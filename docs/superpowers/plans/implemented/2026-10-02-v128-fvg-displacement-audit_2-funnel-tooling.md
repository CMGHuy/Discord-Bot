# v128 FVG lift audit, Part 2: funnel tooling (V128-4 .. V128-6)

> Header, Global Constraints, Review Focus, the spec-assumption table (A1–A12), the file map and `## Parallelisation` live in `2026-10-02-v128-fvg-displacement-audit_0-index.md`. Every task here implicitly includes those constraints. Work in the worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-02-v128-fvg-displacement-audit`; all paths below are relative to it.

# Phase 2 — Funnel tooling (script layer, outside `code_hash()`)

> `provenance.code_hash()` hashes `swingbot/` only. Everything in Phase 2 lives in `scripts/backtest/`, so editing it never invalidates an arm stamp. Phase 1 code must not change after V128-8 starts producing arms.

### Task V128-4: `validate_component.py`: harvest routing at walkforward and validation, `--mechanism-json`

**Files:**
- Modify: `scripts/backtest/validate_component.py`
- Create: `tests/backtesting/test_validate_component_v128.py`

**Interfaces:**
- Consumes: `acceptance.evaluate`, `ClauseResult`, `AcceptanceResult`, `CLOSED`, `DECIDED`, `VERSION`, `delta_expectancy_r`, `delta_standardised_win_rate`; `acceptance_harvest.evaluate_harvest`, `WIN_RATE_FLOOR_PP`, `HARVEST_VERSION`; `backtest_wf.gate`, `gate_win_rate`.
- Produces:
  - `--gate harvest --stage walkforward`: per-fold rows `{"test_years", "delta_expectancy_r", "n"}` with `n` = min closed-trade count of the two arms, judged by `backtest_wf.gate`. Prints `<VERDICT> -- stage 2 walkforward harvest expectancy fold gate (backtest_wf.gate)` and writes JSON `{"verdict", "gate": "harvest", "folds"}`.
  - `--gate harvest --stage validation`: `evaluate_harvest(..., stage="validation", permutation_p=...)`. The result clause names are `expectancy_gain, win_rate_floor, volume, permutation`, with `acceptance_version` 1.
  - `--mechanism-json PATH`: the file holds `dataclasses.asdict(ClauseResult)` for a clause named `mechanism`, and replaces v72 clause 6 at validation. Combining it with `--gate harvest` is a `parser.error` (exit 2).
  - `with_mechanism_clause(result: AcceptanceResult, clause: ClauseResult) -> AcceptanceResult`, public (V128-6 imports it). It raises `ValueError` unless `clause.name == "mechanism"`.
  - `load_clause(path) -> ClauseResult`.
  - The `--gate win_rate` path (the default) is unchanged: the same verdict line and the same JSON keys and key order. The only addition is a per-fold JSON row printed to stdout.

- [ ] **Step 1: Write the failing tests**

```python
# tests/backtesting/test_validate_component_v128.py
"""v128: --gate harvest at walkforward/validation, and --mechanism-json for v72 clause 6."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import validate_component as vc  # noqa: E402
from swingbot.core.backtesting.acceptance import ClauseResult, evaluate  # noqa: E402
from tests.backtesting.test_validate_component_cli import write_arms, write_folds  # noqa: E402

BESPOKE = ["--bespoke-instrument", "v128 unit fixture"]


def _run(*args):
    return vc.main([*args, *BESPOKE])


def test_harvest_walkforward_passes_when_expectancy_improves_every_fold(tmp_path, capsys):
    out = tmp_path / "wf.json"
    rc = _run("--stage", "walkforward", "--gate", "harvest", "--arms", str(write_folds(tmp_path, "improving")),
              "--title", "t", "--window", "w", "--out-json", str(out))
    assert rc == 0
    assert "harvest expectancy fold gate (backtest_wf.gate)" in capsys.readouterr().out
    blob = json.loads(out.read_text(encoding="utf-8"))
    assert blob["gate"] == "harvest"
    assert all(fold["delta_expectancy_r"] > 0 and fold["n"] >= 30 for fold in blob["folds"])


def test_harvest_walkforward_fails_when_expectancy_degrades(tmp_path):
    assert _run("--stage", "walkforward", "--gate", "harvest", "--arms",
                str(write_folds(tmp_path, "degrading")), "--title", "t", "--window", "w") == 1


def test_win_rate_walkforward_json_is_unchanged(tmp_path):
    out = tmp_path / "wf.json"
    _run("--stage", "walkforward", "--arms", str(write_folds(tmp_path, "improving")), "--title", "t",
         "--window", "w", "--out-json", str(out))
    blob = json.loads(out.read_text(encoding="utf-8"))
    assert set(blob) == {"verdict", "folds"}
    assert list(blob["folds"][0]) == ["test_years", "delta_win_rate_pp", "n"]


def test_harvest_validation_runs_the_v92_clauses_and_fails_without_a_permutation_p(tmp_path):
    out = tmp_path / "v.json"
    rc = _run("--stage", "validation", "--gate", "harvest", "--arms", str(write_arms(tmp_path)),
              "--title", "t", "--window", "w", "--resamples", "200", "--out-json", str(out))
    blob = json.loads(out.read_text(encoding="utf-8"))
    assert rc == 1 and blob["acceptance_version"] == 1
    assert [c["name"] for c in blob["clauses"]] == ["expectancy_gain", "win_rate_floor", "volume", "permutation"]
    assert next(c for c in blob["clauses"] if c["name"] == "permutation")["verdict"] == "FAIL"


def test_harvest_validation_passes_with_a_permutation_p(tmp_path):
    assert _run("--stage", "validation", "--gate", "harvest", "--arms", str(write_arms(tmp_path)),
                "--title", "t", "--window", "w", "--resamples", "200", "--permutation-p", "0.01") == 0


def test_mechanism_json_replaces_clause_6(tmp_path):
    injected = tmp_path / "mechanism.json"
    injected.write_text(json.dumps({"name": "mechanism", "verdict": "FAIL", "detail": "v128 injected",
                                    "value": None, "threshold": None}), encoding="utf-8")
    out = tmp_path / "v.json"
    rc = _run("--stage", "validation", "--arms", str(write_arms(tmp_path)), "--title", "t", "--window", "w",
              "--permutation-p", "0.01", "--resamples", "200", "--mechanism-json", str(injected),
              "--out-json", str(out))
    blob = json.loads(out.read_text(encoding="utf-8"))
    mechanism = next(c for c in blob["clauses"] if c["name"] == "mechanism")
    assert (rc, blob["verdict"], mechanism["detail"]) == (1, "FAIL", "v128 injected")


def test_with_mechanism_clause_recomputes_the_verdict(tmp_path):
    baseline, component = vc.load_arms(write_arms(tmp_path))
    result = evaluate(baseline, component, stage="walkforward", n_resamples=200)
    swapped = vc.with_mechanism_clause(result, ClauseResult("mechanism", "FAIL", "x"))
    assert swapped.verdict == "FAIL"
    assert [c.name for c in swapped.clauses] == [c.name for c in result.clauses]
    with pytest.raises(ValueError):
        vc.with_mechanism_clause(result, ClauseResult("volume", "PASS", "x"))


def test_mechanism_json_with_the_harvest_gate_is_rejected(tmp_path):
    with pytest.raises(SystemExit) as exc:
        _run("--stage", "validation", "--gate", "harvest", "--arms", str(write_arms(tmp_path)),
             "--title", "t", "--window", "w", "--mechanism-json", str(tmp_path / "m.json"))
    assert exc.value.code == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_validate_component_v128.py`
Expected: FAIL. The harvest walkforward test gets no `"gate"` key, and the harvest validation test gets v72 clause names. `--mechanism-json` gives `error: unrecognized arguments` (exit 2, so the injected test raises `SystemExit`), and `with_mechanism_clause` raises `AttributeError`.

- [ ] **Step 3: Implement**

Replace the two `acceptance` import lines and the `backtest_wf` import line at the top of `validate_component.py` with:

```python
import dataclasses
from swingbot.core.backtesting.acceptance import ALPHA, BOOTSTRAP_RESAMPLES, CLOSED, GEOMETRY_MAX_DROP_PCT, NON_INFERIORITY_R, VERSION as ACCEPTANCE_VERSION, VOLUME_MAX_CUT_PCT, ArmTrade, AcceptanceResult, ClauseResult, evaluate, delta_expectancy_r, delta_standardised_win_rate, mde_paired, mde_win_rate, project_target_n, render_json, render_markdown  # noqa: E402
from swingbot.core.backtesting.acceptance_harvest import HARVEST_VERSION, WIN_RATE_FLOOR_PP, evaluate_harvest, mde_expectancy_r  # noqa: E402
```

and

```python
from swingbot.core.backtesting.backtest_wf import gate as gate_expectancy, gate_win_rate  # noqa: E402
```

(`import dataclasses` joins the stdlib imports at the top of the file, after `import datetime as dt`.)

Replace `stage_walkforward` with:

```python
def _count(trades, outcomes):
    return sum(trade.outcome in outcomes for trade in trades)

def _fold_row(fold, harvest):
    """One fold's judge input. Harvest: dExpR over closed trades, judged by backtest_wf.gate
    (v128 frozen reading of 'the harvest gate's walk-forward rule'). Win rate: unchanged."""
    b, c = fold["baseline"], fold["component"]
    if harvest:
        return {"test_years": fold["test_year"], "delta_expectancy_r": delta_expectancy_r(b, c), "n": min(_count(b, CLOSED), _count(c, CLOSED))}
    return {"test_years": fold["test_year"], "delta_win_rate_pp": delta_standardised_win_rate(b, c), "n": min(_count(b, DECIDED), _count(c, DECIDED))}

def stage_walkforward(args):
    folds = load_folds(args.arms)
    if not _folds_are_well_formed(folds): print("REFUSED -- gate_win_rate requires exactly 3 folds with distinct test_year values."); return 1
    harvest = args.gate == "harvest"
    rows = [_fold_row(fold, harvest) for fold in folds]
    verdict = (gate_expectancy if harvest else gate_win_rate)({"folds": rows})
    label = "harvest expectancy fold gate (backtest_wf.gate)" if harvest else "win-rate consistency gate"
    print(f"{verdict} -- stage 2 walkforward {label}")
    for row in rows: print(json.dumps(row))
    payload = {"verdict": verdict, "gate": "harvest", "folds": rows} if harvest else {"verdict": verdict, "folds": rows}
    if args.out_json: Path(args.out_json).parent.mkdir(parents=True, exist_ok=True); Path(args.out_json).write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return 0 if verdict == "PASS" else 1
```

Replace `_write_skeleton` with:

```python
_SKELETON_CLAUSES = {
    "win_rate": (("win_rate", 0.0), ("profit_floor", NON_INFERIORITY_R), ("geometry", GEOMETRY_MAX_DROP_PCT), ("volume", VOLUME_MAX_CUT_PCT), ("permutation", ALPHA), ("mechanism", None)),
    "harvest": (("expectancy_gain", 0.0), ("win_rate_floor", WIN_RATE_FLOOR_PP), ("volume", VOLUME_MAX_CUT_PCT), ("permutation", ALPHA)),
}
_SKELETON_VERSION = {"win_rate": ACCEPTANCE_VERSION, "harvest": HARVEST_VERSION}

def _write_skeleton(args, stage):
    if not args.out_md and not args.out_json: return
    clauses = tuple(ClauseResult(name, "PENDING", "not yet run", None, threshold) for name, threshold in _SKELETON_CLAUSES[args.gate])
    result = AcceptanceResult(stage=stage, verdict="PENDING", seed=args.seed, clauses=clauses, strata=[], split={"removed": 0,"changed": 0,"unchanged": 0,"added": 0,"is_subset": False}, version=_SKELETON_VERSION[args.gate])
    markdown = render_markdown(result, title=args.title, window=args.window, notes="PRE-REGISTERED skeleton -- verdict pending.")
    if args.out_md: Path(args.out_md).parent.mkdir(parents=True, exist_ok=True); Path(args.out_md).write_text(markdown, encoding="utf-8")
    if args.out_json: Path(args.out_json).parent.mkdir(parents=True, exist_ok=True); Path(args.out_json).write_text(json.dumps(render_json(result), indent=1), encoding="utf-8")
```

Replace `_run_gate` with:

```python
def load_clause(path):
    return ClauseResult(**json.loads(Path(path).read_text(encoding="utf-8")))

def with_mechanism_clause(result, clause):
    """Swap a precomputed v72 clause 6 (v128's frozen baseline reading) into a gate result and recompute the verdict."""
    if clause.name != "mechanism":
        raise ValueError(f"expected a clause named 'mechanism', got {clause.name!r}")
    clauses = tuple(clause if c.name == "mechanism" else c for c in result.clauses)
    verdict = "FAIL" if any(c.verdict == "FAIL" for c in clauses) else "PASS"
    return dataclasses.replace(result, clauses=clauses, verdict=verdict)

def _evaluate(args, baseline, component, stage):
    common = dict(stage=stage, permutation_p=args.permutation_p, n_resamples=args.resamples, seed=args.seed)
    if args.gate == "harvest":
        return evaluate_harvest(baseline, component, **common)
    result = evaluate(baseline, component, **common)
    return with_mechanism_clause(result, load_clause(args.mechanism_json)) if args.mechanism_json else result

def _run_gate(args, stage):
    baseline, component = load_arms(args.arms); _write_skeleton(args, stage)
    result = _evaluate(args, baseline, component, stage)
    markdown = render_markdown(result, title=args.title, window=args.window, notes=_notes(args)); print(markdown)
    if args.out_md: Path(args.out_md).parent.mkdir(parents=True, exist_ok=True); Path(args.out_md).write_text(markdown, encoding="utf-8")
    if args.out_json: Path(args.out_json).parent.mkdir(parents=True, exist_ok=True); Path(args.out_json).write_text(json.dumps(render_json(result), indent=1), encoding="utf-8")
    return 0 if result.verdict == "PASS" else 1
```

In `main`, append `; parser.add_argument("--mechanism-json", default=None)` to the end of the second `parser.add_argument(...)` line. Replace `args = parser.parse_args(argv); refused = _stamp_gate(args)` with:

```python
    args = parser.parse_args(argv)
    if args.mechanism_json and args.gate == "harvest":
        parser.error("--mechanism-json replaces v72 clause 6; the v92 harvest gate has no mechanism clause")
    refused = _stamp_gate(args)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run each:
- `python scripts/dev/testrun.py file tests/backtesting/test_validate_component_v128.py`
- `python scripts/dev/testrun.py file tests/backtesting/test_validate_component_cli.py`
- `python scripts/dev/testrun.py file tests/backtesting/test_validate_component_stamps.py`

Expected: every one PASS.
Run: `python -m radon cc -s -n C scripts/backtest/validate_component.py`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/validate_component.py tests/backtesting/test_validate_component_v128.py
git commit -m "feat(v128): validate_component --gate harvest at walkforward/validation; --mechanism-json for clause 6"
```

### Task V128-5: `fvg_attribution.py`: baseline provenance, attribution, frozen clause 6, context slice

**Files:**
- Create: `scripts/backtest/fvg_attribution.py`
- Create: `tests/scripts/test_fvg_attribution.py`

**Interfaces:**
- Consumes: `fvg.find_fair_value_gaps_detailed`, `fvg.filter_gaps` (V128-1, keeps dict identity); `levels.collect_candidate_levels`, `levels.count_confirming_strategies(..., candidates=)`, `levels.CLUSTER_TOLERANCE_PCT`, `levels._cluster_levels` (parity only); `backtest_scenarios.levels_asof`, `build_confluence_plan`, `LEVEL_REFRESH_BARS`; `ConfluenceEngine.run_ticker`; `acceptance.ArmTrade`, `ClauseResult`, `win_rate`, `expectancy_r`; `provenance.code_hash`; `measure_arms.load_frame`; `config.FVG_LEVELS_MODE` (V128-2).
- Produces (`scripts/backtest/fvg_attribution.py`, importable with `scripts/backtest` on `sys.path`):
  - `CANDIDATES: dict[str, tuple[str, float]] = {"off": ("off", 1.5), "disp-1.0": ("displacement", 1.0), "disp-1.5": ("displacement", 1.5), "disp-2.0": ("displacement", 2.0)}`, plus `knob_delta(cid) -> dict` (the exact `measure_arms --knob` delta).
  - `BUCKETS = ("vote_only", "price_only", "both", "unaffected")`.
  - `cluster_members(candidates) -> list[tuple[float, list[tuple[float, str]]]]`, `filtered_mids(window, gaps, mode, k) -> list[float]`, `vote_lost(candidates, target, mids) -> bool`.
  - `record_ticker(ticker, df, horizons, signal_window) -> list[dict]`: one row per accepted baseline confluence plan, `{"key": [6 fields], "fvg_family": bool, "candidates": {cid: {"vote": bool, "price": bool}}}`.
  - `buckets_for(baseline, provenance: dict, cid, component) -> list[str]`, `mechanism_clause(baseline, buckets) -> ClauseResult`, `attribution(baseline, buckets, component) -> dict`, `context_slice(baseline, provenance) -> dict`.
  - CLI: `record --arms P --out P [--workers N]` (default: `backtest_scenarios._resolve_replay_workers(None)`, as `measure_arms.py`), `report --arms P --provenance P --candidate CID [--out-md P] [--out-json P] [--mechanism-json P]`, `context --arms P --provenance P [--out-md P]`. Refusal tokens on stderr with exit 1: `refused:code-mismatch`, `refused:not-baseline`, `refused:candidate-mismatch`, `refused:window-mismatch`.
- Frozen definitions (quoted in V128-7):
  - **Vote**: at the signal bar's window, FVG is among `count_confirming_strategies(... take_profit, 5.0)` families and drops out once the candidate's filtered FVG candidates are removed.
  - **Price**: at the level-map bar `levels_asof` actually used, the scenario's stop cluster or the plan's TP1 cluster has an FVG member whose price is a filtered mid.
  - **Entry** is the bar close for confluence plans, so it is never a level.
  - **Strategy rows** use the pairing proxy: absent from the candidate arm, or a different outcome or `r_multiple`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/scripts/test_fvg_attribution.py
"""v128 attribution helper: provenance, buckets, frozen clause 6, context slice."""
import inspect
import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import fvg_attribution as fa  # noqa: E402
from swingbot.core.backtesting import backtest_scenarios as bs  # noqa: E402
from swingbot.core.backtesting.acceptance import ArmTrade  # noqa: E402
from swingbot.core.backtesting.arms.engine import run_arm  # noqa: E402
from swingbot.core.backtesting.arms.provenance import build_stamp  # noqa: E402
from swingbot.core.market import fvg, levels  # noqa: E402
from swingbot.core.market.strategy_types import HORIZONS  # noqa: E402
from tests.backtesting.test_v74_fixture import load_v74_fixture  # noqa: E402
from tests.market.fvg_frames import BULL_THIRD, STRONG_BULL, WEAK_BULL, gap_frame, witness_frame  # noqa: E402


def _trade(ticker, outcome, *, source="confluence", day=1, horizon="3m", direction="bullish"):
    r = 2.0 if outcome == "win" else -1.0
    return ArmTrade(ticker, "S/R Confluence", horizon, f"2019-03-{day:02d}", outcome, r, 2.0, source, direction)


def _prov(trades, cid, vote=False, price=False, fvg_family=False):
    return {t.key: {"fvg_family": fvg_family, "candidates": {cid: {"vote": vote, "price": price}}} for t in trades}


def test_cluster_members_matches_levels_cluster_levels():
    frame = witness_frame()
    candidates = levels.collect_candidate_levels(frame, HORIZONS["3m"], float(frame["Close"].iloc[-1]))
    mine = fa.cluster_members(candidates)
    theirs = levels._cluster_levels(candidates)
    assert [mean for mean, _ in mine] == [level.price for level in theirs]
    assert [[label for _, label in members] for _, members in mine] == [level.sources for level in theirs]


def test_filtered_mids_follow_the_mode():
    strong, weak = gap_frame(STRONG_BULL, BULL_THIRD), gap_frame(WEAK_BULL, BULL_THIRD)
    strong_gaps, weak_gaps = fvg.find_fair_value_gaps_detailed(strong), fvg.find_fair_value_gaps_detailed(weak)
    assert fa.filtered_mids(strong, strong_gaps, "all", 1.5) == []
    assert fa.filtered_mids(strong, strong_gaps, "off", 1.5) == [101.25]
    assert fa.filtered_mids(strong, strong_gaps, "displacement", 1.5) == []
    assert fa.filtered_mids(weak, weak_gaps, "displacement", 1.5) == [101.25]


def test_vote_is_lost_only_when_no_kept_fvg_still_votes():
    candidates = [(101.25, "FVG (bullish)"), (150.0, "EMA20")]
    assert fa.vote_lost(candidates, 101.25, [101.25]) is True
    assert fa.vote_lost(candidates + [(101.30, "FVG (bullish)")], 101.25, [101.25]) is False
    assert fa.vote_lost(candidates, 101.25, []) is False
    assert fa.vote_lost([(150.0, "EMA20")], 101.25, [101.25]) is False


def test_buckets_cover_vote_price_both_and_unaffected():
    trades = [_trade("A", "loss", day=d) for d in range(1, 5)]
    prov = {}
    for trade, (vote, price) in zip(trades, [(True, False), (False, True), (True, True), (False, False)]):
        prov.update(_prov([trade], "off", vote, price))
    assert fa.buckets_for(trades, prov, "off", trades) == ["vote_only", "price_only", "both", "unaffected"]


def test_strategy_rows_use_the_pairing_proxy():
    kept, gone, moved = (_trade("S", "win", source="strategy", day=d) for d in (1, 2, 3))
    component = [kept, ArmTrade(**{**asdict(moved), "r_multiple": 1.5})]
    assert fa.buckets_for([kept, gone, moved], {}, "off", component) == ["unaffected", "price_only", "price_only"]


def test_a_baseline_confluence_trade_without_provenance_raises():
    with pytest.raises(KeyError, match="no provenance"):
        fa.buckets_for([_trade("A", "loss")], {}, "off", [])


def test_mechanism_passes_when_the_removed_trades_are_the_bad_ones():
    removed = [_trade(f"T{t}", "loss", day=d) for t in range(5) for d in (1, 2)]
    retained = [_trade(f"T{t}", o, day=d) for t in range(5) for d, o in ((3, "win"), (4, "loss"))]
    baseline = removed + retained
    buckets = ["vote_only"] * len(removed) + ["unaffected"] * len(retained)
    clause = fa.mechanism_clause(baseline, buckets)
    assert clause.name == "mechanism" and clause.verdict == "PASS"


def test_mechanism_fails_when_winners_are_removed_or_a_population_is_empty():
    winners = [_trade(f"T{t}", "win", day=1) for t in range(5)]
    losers = [_trade(f"T{t}", "loss", day=2) for t in range(5)]
    assert fa.mechanism_clause(winners + losers, ["price_only"] * 5 + ["unaffected"] * 5).verdict == "FAIL"
    assert fa.mechanism_clause(losers, ["unaffected"] * 5).verdict == "FAIL"


def test_attribution_reports_direction_and_flags_horizon_concentration():
    baseline = [_trade("A", "loss", day=d, horizon="3m") for d in (1, 2, 3)] + [_trade("A", "win", day=4, horizon="6m", direction="bearish")]
    info = fa.attribution(baseline, ["vote_only", "vote_only", "both", "unaffected"], baseline[:2])
    assert info["removed"]["n"] == 3 and info["top2_horizon_share"] == 1.0
    assert set(info["per_direction"]) == {"bullish", "bearish"}
    assert "OVER 80%" in fa.render_attribution("off", info)


def test_context_slice_splits_on_fvg_in_families():
    tagged, untagged = _trade("A", "win", day=1), _trade("A", "loss", day=2)
    prov = {**_prov([tagged], "off", fvg_family=True), **_prov([untagged], "off", fvg_family=False)}
    info = fa.context_slice([tagged, untagged, _trade("S", "win", source="strategy", day=3)], prov)
    assert (info["fvg_in_families"]["n"], info["fvg_not_in_families"]["n"], info["strategy_rows_excluded"]) == (1, 1, 1)


def test_replay_still_has_the_shape_the_recorder_patches():
    source = inspect.getsource(bs.replay_scenarios)
    assert "levels_asof(ticker, df, i, horizon_key, cache)" in source
    assert "build_confluence_plan(" in source and "tolerance_pct=5.0" in source
    assert fa.VOTE_TOLERANCE_PCT == 5.0


def _write_arms(tmp_path, knobs, baseline, component, engine_hash):
    stamp = build_stamp(stage="pilot", signal_window=("2018-06-01", "2020-12-31"), universe=["A"],
                        horizons=("3m",), engines=("confluence",), knob_delta=knobs,
                        engine_hash_baseline=engine_hash, engine_hash_component=engine_hash, changed_outcomes=1)
    path = tmp_path / "arms.json"
    path.write_text(json.dumps({"provenance": stamp, "baseline": [asdict(t) for t in baseline],
                                "component": [asdict(t) for t in component]}), encoding="utf-8")
    return path


def test_report_refuses_a_code_mismatch(tmp_path, capsys):
    trades = [_trade("A", "loss")]
    arms = _write_arms(tmp_path, {"FVG_LEVELS_MODE": "off"}, trades, [], "h")
    provenance = tmp_path / "prov.json"
    provenance.write_text(json.dumps({"engine_hash": "other", "signal_window": ["2018-06-01", "2020-12-31"],
                                      "rows": []}), encoding="utf-8")
    assert fa.main(["report", "--arms", str(arms), "--provenance", str(provenance), "--candidate", "off"]) == 1
    assert "refused:code-mismatch" in capsys.readouterr().err


def test_report_refuses_a_candidate_whose_knobs_differ(tmp_path, capsys):
    arms = _write_arms(tmp_path, {"FVG_LEVELS_MODE": "displacement", "FVG_DISPLACEMENT_ATR_K": 2.0}, [], [], "h")
    provenance = tmp_path / "prov.json"
    provenance.write_text(json.dumps({"engine_hash": "h", "signal_window": ["2018-06-01", "2020-12-31"],
                                      "rows": []}), encoding="utf-8")
    assert fa.main(["report", "--arms", str(arms), "--provenance", str(provenance), "--candidate", "disp-1.0"]) == 1
    assert "refused:candidate-mismatch" in capsys.readouterr().err


@pytest.mark.slow
def test_recorder_sees_every_baseline_confluence_trade_and_off_voids_every_fvg_vote():
    ticker, frame = sorted(load_v74_fixture().items())[0]
    window = ("1900-01-01", "2100-12-31")
    rows = fa.record_ticker(ticker, frame, ("3m",), window)
    arm = run_arm(ticker, frame, ("confluence",), ("3m",), window, {})
    assert arm, "fixture must produce confluence trades or this test proves nothing"
    assert {t.key for t in arm} <= {tuple(row["key"]) for row in rows}
    assert all(row["candidates"]["off"]["vote"] == row["fvg_family"] for row in rows)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_fvg_attribution.py`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'fvg_attribution'`.

- [ ] **Step 3: Implement**

```python
#!/usr/bin/env python3
"""v128 FVG provenance, attribution and the frozen clause-6 reading (script layer).

Nothing under swingbot/ imports this file, and provenance.code_hash() hashes
swingbot/ only, so editing it never invalidates an arm stamp.

record   replay the BASELINE confluence arm a stamped arms file describes, and for
         every accepted plan store, per frozen candidate, whether it loses the FVG
         vote (signal bar) or the stop/TP1 level it was built on (level-map bar).
report   join one candidate's arms with that record: attribution buckets,
         per-direction split, top-2 horizon share, and the frozen clause-6
         ClauseResult as JSON for validate_component.py --mechanism-json.
context  Stage 1 diagnostic: baseline confluence trades sliced by FVG-in-families.

Run: python scripts/backtest/fvg_attribution.py record --arms logs/v128/pilot-off.json --out logs/v128/provenance-pilot.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import uuid
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "data"), str(ROOT / "scripts" / "backtest")]

from swingbot import config  # noqa: E402
from swingbot.core.backtesting import backtest_scenarios as bs  # noqa: E402
from swingbot.core.backtesting.acceptance import ArmTrade, ClauseResult, expectancy_r, win_rate  # noqa: E402
from swingbot.core.backtesting.arms.confluence_engine import ConfluenceEngine  # noqa: E402
from swingbot.core.backtesting.arms.provenance import code_hash  # noqa: E402
from swingbot.core.market import fvg, levels  # noqa: E402
from swingbot.core.market.strategy_types import HORIZONS  # noqa: E402
from swingbot.scan_params import ScanParams  # noqa: E402

#: The frozen v128 candidates: id -> (FVG_LEVELS_MODE, FVG_DISPLACEMENT_ATR_K).
CANDIDATES = {"off": ("off", 1.5), "disp-1.0": ("displacement", 1.0),
              "disp-1.5": ("displacement", 1.5), "disp-2.0": ("displacement", 2.0)}
#: replay_scenarios' target-confluence tolerance (pinned by a source test).
VOTE_TOLERANCE_PCT = 5.0
BUCKETS = ("vote_only", "price_only", "both", "unaffected")
_BUCKET_OF = {(True, False): "vote_only", (False, True): "price_only",
              (True, True): "both", (False, False): "unaffected"}
LOG_DIR = ROOT / "logs"


def knob_delta(cid: str) -> dict:
    """The exact measure_arms --knob delta for a candidate."""
    mode, k = CANDIDATES[cid]
    return {"FVG_LEVELS_MODE": mode} if mode == "off" else {"FVG_LEVELS_MODE": mode, "FVG_DISPLACEMENT_ATR_K": k}


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)


def cluster_members(candidates, tolerance_pct: float = levels.CLUSTER_TOLERANCE_PCT) -> list:
    """levels._cluster_levels, but keeping each member's own price: [(mean, [(price, label), ...])]."""
    if not candidates:
        return []
    ordered = sorted(candidates, key=lambda c: c[0])
    clusters, bucket = [], [ordered[0]]
    for price, label in ordered[1:]:
        mean = sum(p for p, _ in bucket) / len(bucket)
        if mean > 0 and abs(price - mean) / mean * 100 <= tolerance_pct:
            bucket.append((price, label))
        else:
            clusters.append((sum(p for p, _ in bucket) / len(bucket), bucket))
            bucket = [(price, label)]
    clusters.append((sum(p for p, _ in bucket) / len(bucket), bucket))
    return clusters


def filtered_mids(window, gaps, mode: str, k: float) -> list:
    """Mids of the gaps `mode` drops at this window (all unfilled gaps minus the kept ones)."""
    kept = {id(gap) for gap in fvg.filter_gaps(window, gaps, mode, k)}
    return [gap["mid"] for gap in gaps if id(gap) not in kept]


def _is_filtered(price: float, label: str, mids) -> bool:
    return label.startswith("FVG") and any(_close(price, mid) for mid in mids)


def _families(candidates, target: float) -> list:
    return levels.count_confirming_strategies(None, None, None, target, VOTE_TOLERANCE_PCT,
                                              candidates=candidates)[1]


def vote_lost(candidates, target: float, mids) -> bool:
    """FVG votes for `target` with every gap, and stops voting once the filtered gaps are gone."""
    if not mids or "FVG" not in _families(candidates, target):
        return False
    remaining = [(p, s) for p, s in candidates if not _is_filtered(p, s, mids)]
    return "FVG" not in _families(remaining, target)


def _members_at(clusters, price: float) -> list:
    return next((members for mean, members in clusters if _close(mean, price)), [])


def _touches(members, mids) -> bool:
    return any(_is_filtered(p, s, mids) for p, s in members)


def _snapshot(memo: dict, df, index: int, horizon_key: str) -> dict:
    """Candidates, clusters and detailed gaps at df.iloc[:index + 1], under baseline config."""
    key = (horizon_key, index)
    if key not in memo:
        window = df.iloc[:index + 1]
        price = float(window["Close"].iloc[-1])
        candidates = levels.collect_candidate_levels(window, HORIZONS[horizon_key], price,
                                                     params=ScanParams.from_config())
        memo[key] = {"window": window, "candidates": candidates, "clusters": cluster_members(candidates),
                     "gaps": fvg.find_fair_value_gaps_detailed(window)}
    return memo[key]


def _candidate_flags(record: dict, signal: dict, level: dict) -> dict:
    stop = _members_at(level["clusters"], record["stop_level"])
    tp1 = _members_at(level["clusters"], record["tp1"])
    out = {}
    for cid, (mode, k) in CANDIDATES.items():
        signal_mids = filtered_mids(signal["window"], signal["gaps"], mode, k)
        level_mids = filtered_mids(level["window"], level["gaps"], mode, k)
        out[cid] = {"vote": vote_lost(signal["candidates"], record["take_profit"], signal_mids),
                    "price": bool(level_mids) and (_touches(stop, level_mids) or _touches(tp1, level_mids))}
    return out


@contextmanager
def _recording(log: list, level_bars: dict):
    """Observe replay_scenarios without changing it: which bar each level map was built
    on, and the scenario/plan behind every accepted confluence plan."""
    real_asof, real_build = bs.levels_asof, bs.build_confluence_plan

    def asof(ticker, df, bar_index, horizon_key, cache):
        key = (ticker, horizon_key, bar_index // bs.LEVEL_REFRESH_BARS)
        if key not in cache:
            level_bars[key] = bar_index
        return real_asof(ticker, df, bar_index, horizon_key, cache)

    def build(scenario, window, **kwargs):
        plan = real_build(scenario, window, **kwargs)
        if plan is not None:
            log.append({"signal_index": len(window) - 1, "horizon_key": kwargs["horizon_key"],
                        "take_profit": scenario.take_profit, "stop_level": scenario.stop_loss,
                        "tp1": plan.tp1, "strategy": plan.strategy, "direction": plan.direction})
        return plan

    with mock.patch.object(bs, "levels_asof", asof), mock.patch.object(bs, "build_confluence_plan", build):
        yield


def _provenance_row(ticker, df, record, level_bars, memo) -> dict:
    index, horizon = record["signal_index"], record["horizon_key"]
    level_index = level_bars[(ticker, horizon, index // bs.LEVEL_REFRESH_BARS)]
    signal = _snapshot(memo, df, index, horizon)
    level = _snapshot(memo, df, level_index, horizon)
    key = [ticker, record["strategy"], horizon, str(df.index[index].date()), "confluence", record["direction"]]
    return {"key": key, "fvg_family": "FVG" in _families(signal["candidates"], record["take_profit"]),
            "candidates": _candidate_flags(record, signal, level)}


def record_ticker(ticker, df, horizons, signal_window) -> list:
    """Every accepted baseline confluence plan for one ticker, with its FVG provenance."""
    log, level_bars, memo = [], {}, {}
    with _recording(log, level_bars):
        ConfluenceEngine().run_ticker(ticker, df, tuple(horizons), tuple(signal_window), ScanParams.from_config())
    return [_provenance_row(ticker, df, record, level_bars, memo) for record in log]


def _record_worker(task):
    ticker, horizons, window = task
    from measure_arms import load_frame
    frame = load_frame(ticker)
    if frame is None:
        raise RuntimeError(f"{ticker}: no cached frame")
    return ticker, record_ticker(ticker, frame, horizons, window)


def _progress(path, done, total):
    print(f"  [record] {done}/{total} tickers ({done / total * 100:.0f}%)", flush=True)
    try:
        path.write_text(f"{done}/{total} tickers ({done / total * 100:.0f}%)\n", encoding="utf-8")
    except OSError:
        pass


def _run_tasks(tasks, workers: int, progress_path) -> list:
    rows, done = [], 0
    if workers <= 1:
        results = (_record_worker(task) for task in tasks)
        for _, ticker_rows in results:
            rows.extend(ticker_rows); done += 1; _progress(progress_path, done, len(tasks))
        return rows
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(_record_worker, task) for task in tasks]):
            rows.extend(future.result()[1]); done += 1; _progress(progress_path, done, len(tasks))
    return rows


def _record_refusal(stamp: dict) -> str | None:
    if code_hash() != stamp["engine_hash"]["baseline"]:
        return "refused:code-mismatch -- swingbot/ changed since these arms were produced."
    if config.FVG_LEVELS_MODE != "all":
        return "refused:not-baseline -- the recorder replays the baseline arm; FVG_LEVELS_MODE must be all."
    return None


def cmd_record(args) -> int:
    stamp = json.loads(Path(args.arms).read_text(encoding="utf-8"))["provenance"]
    refusal = _record_refusal(stamp)
    if refusal:
        print(refusal, file=sys.stderr); return 1
    tasks = [(ticker, tuple(stamp["horizons"]), tuple(stamp["signal_window"])) for ticker in stamp["universe"]]
    LOG_DIR.mkdir(exist_ok=True)
    progress = LOG_DIR / f"fvg_attribution.{uuid.uuid4().hex[:8]}.progress"
    workers = bs._resolve_replay_workers(args.workers)       # the same pool sizing measure_arms uses
    rows = sorted(_run_tasks(tasks, workers, progress), key=lambda row: row["key"])
    progress.unlink(missing_ok=True)
    out = {"arms": str(args.arms), "signal_window": stamp["signal_window"],
           "engine_hash": stamp["engine_hash"]["baseline"], "rows": rows}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out), encoding="utf-8")
    print(f"recorded {len(rows)} baseline confluence plans -> {args.out}")
    return 0


def load_rows(path) -> tuple:
    """(baseline, component) ArmTrades; a walk-forward blob pools its three disjoint test folds."""
    blob = json.loads(Path(path).read_text(encoding="utf-8"))
    pairs = [(blob["baseline"], blob["component"])] if "baseline" in blob else \
        [(fold["baseline"], fold["component"]) for fold in blob["folds"]]
    return ([ArmTrade(**row) for base, _ in pairs for row in base],
            [ArmTrade(**row) for _, comp in pairs for row in comp])


def index_provenance(rows) -> dict:
    out = {}
    for row in rows:
        key = tuple(row["key"])
        if key in out:
            raise ValueError(f"duplicate provenance key {key}")
        out[key] = row
    return out


def _same_r(a, b) -> bool:
    return a == b if a is None or b is None else _close(a, b)


def _strategy_changed(trade, component_by_key) -> bool:
    other = component_by_key.get(trade.key)
    return other is None or other.outcome != trade.outcome or not _same_r(trade.r_multiple, other.r_multiple)


def _flags(trade, provenance, cid, component_by_key) -> tuple:
    if trade.source != "confluence":
        return False, _strategy_changed(trade, component_by_key)
    row = provenance.get(trade.key)
    if row is None:
        raise KeyError(f"no provenance for baseline confluence trade {trade.key} -- re-run record on these arms")
    flags = row["candidates"][cid]
    return flags["vote"], flags["price"]


def buckets_for(baseline, provenance, cid, component) -> list:
    component_by_key = {trade.key: trade for trade in component}
    return [_BUCKET_OF[_flags(trade, provenance, cid, component_by_key)] for trade in baseline]


def mechanism_clause(baseline, buckets) -> ClauseResult:
    """v128 frozen clause 6, on the BASELINE arm: removed = vote or price affected."""
    removed = [t for t, b in zip(baseline, buckets) if b != "unaffected"]
    retained = [t for t, b in zip(baseline, buckets) if b == "unaffected"]
    r_wr, k_wr, r_exp = win_rate(removed), win_rate(retained), expectancy_r(removed)
    if r_wr is None or k_wr is None or r_exp is None:
        return ClauseResult("mechanism", "FAIL", "v128 frozen reading: removed or retained baseline "
                            "population has no decided trades to compare", None, None)
    ok = r_wr < k_wr and r_exp <= 0.0
    return ClauseResult("mechanism", "PASS" if ok else "FAIL",
                        f"v128 frozen reading (baseline arm): removed {len(removed)} WR {r_wr:.2f}% vs "
                        f"retained {len(retained)} WR {k_wr:.2f}%, removed ExpR {r_exp:+.4f}R (must be <= 0)",
                        r_wr, k_wr)


def _stats(trades) -> dict:
    return {"n": len(trades), "win_rate": win_rate(trades), "expectancy_r": expectancy_r(trades)}


def top2_share(trades):
    if not trades:
        return None
    return sum(count for _, count in Counter(t.horizon_key for t in trades).most_common(2)) / len(trades)


def attribution(baseline, buckets, component) -> dict:
    by_bucket = {name: [t for t, b in zip(baseline, buckets) if b == name] for name in BUCKETS}
    removed = [t for t, b in zip(baseline, buckets) if b != "unaffected"]
    per_direction = {d: {"removed": _stats([t for t in removed if t.direction == d]),
                         "retained": _stats([t for t in by_bucket["unaffected"] if t.direction == d])}
                     for d in ("bullish", "bearish")}
    keys = {t.key for t in baseline}
    return {"buckets": {name: _stats(ts) for name, ts in by_bucket.items()}, "removed": _stats(removed),
            "retained": _stats(by_bucket["unaffected"]), "per_direction": per_direction,
            "top2_horizon_share": top2_share(removed),
            "replacements": sum(1 for t in component if t.key not in keys)}


def _fmt(stats) -> str:
    wr = "n/a" if stats["win_rate"] is None else f"{stats['win_rate']:.2f}%"
    exp = "n/a" if stats["expectancy_r"] is None else f"{stats['expectancy_r']:+.4f}R"
    return f"{stats['n']} | {wr} | {exp}"


def render_attribution(cid, info) -> str:
    lines = [f"### Attribution -- {cid} (diagnostic, never a gate)", "", "| Population | N | WR | ExpR |",
             "|---|---|---|---|"]
    lines += [f"| {name} | {_fmt(info['buckets'][name])} |" for name in BUCKETS]
    lines.append(f"| removed (vote or price) | {_fmt(info['removed'])} |")
    for direction, pair in info["per_direction"].items():
        lines.append(f"| removed, {direction} | {_fmt(pair['removed'])} |")
        lines.append(f"| retained, {direction} | {_fmt(pair['retained'])} |")
    share = info["top2_horizon_share"]
    lines += ["", f"Top-2 horizon share of removed: {'n/a' if share is None else f'{share:.1%}'}"
              + (" -- OVER 80%: the removed population sits in two horizons." if share and share > 0.8 else ""),
              f"Replacement trades (in the candidate arm, not in baseline): {info['replacements']}", ""]
    return "\n".join(lines)


def context_slice(baseline, provenance) -> dict:
    confluence = [t for t in baseline if t.source == "confluence"]
    tagged = [t for t in confluence if provenance[t.key]["fvg_family"]]
    untagged = [t for t in confluence if not provenance[t.key]["fvg_family"]]
    return {"fvg_in_families": _stats(tagged), "fvg_not_in_families": _stats(untagged),
            "strategy_rows_excluded": len(baseline) - len(confluence)}


def _load_pair(args):
    blob = json.loads(Path(args.arms).read_text(encoding="utf-8"))
    provenance = json.loads(Path(args.provenance).read_text(encoding="utf-8"))
    return blob["provenance"], provenance


def _pair_refusal(stamp, provenance) -> str | None:
    if provenance["engine_hash"] != stamp["engine_hash"]["baseline"]:
        return "refused:code-mismatch -- provenance and arms were produced on different swingbot/ code."
    if list(provenance["signal_window"]) != list(stamp["signal_window"]):
        return "refused:window-mismatch -- provenance covers a different signal window."
    return None


def _write(path, text):
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True); Path(path).write_text(text, encoding="utf-8")


def cmd_report(args) -> int:
    stamp, provenance = _load_pair(args)
    refusal = _pair_refusal(stamp, provenance)
    if refusal is None and stamp["knob_delta"] != knob_delta(args.candidate):
        refusal = f"refused:candidate-mismatch -- arms carry {stamp['knob_delta']}, not {args.candidate}."
    if refusal:
        print(refusal, file=sys.stderr); return 1
    baseline, component = load_rows(args.arms)
    buckets = buckets_for(baseline, index_provenance(provenance["rows"]), args.candidate, component)
    info, clause = attribution(baseline, buckets, component), mechanism_clause(baseline, buckets)
    text = render_attribution(args.candidate, info) + f"\nFrozen clause 6: **{clause.verdict}** -- {clause.detail}\n"
    print(text)
    _write(args.out_md, text)
    _write(args.out_json, json.dumps({"candidate": args.candidate, "attribution": info, "mechanism": asdict(clause)}, indent=1))
    _write(args.mechanism_json, json.dumps(asdict(clause), indent=1))
    return 0


def cmd_context(args) -> int:
    stamp, provenance = _load_pair(args)
    refusal = _pair_refusal(stamp, provenance)
    if refusal:
        print(refusal, file=sys.stderr); return 1
    baseline, _ = load_rows(args.arms)
    info = context_slice(baseline, index_provenance(provenance["rows"]))
    text = ("### Context slice -- baseline `all` arm, by FVG in confluence families\n\n"
            "**Confounded, diagnostic only:** FVG-tagged setups carry more families by construction. "
            "It explains; it never selects.\n\n| Slice | N | WR | ExpR |\n|---|---|---|---|\n"
            f"| FVG in families | {_fmt(info['fvg_in_families'])} |\n"
            f"| FVG not in families | {_fmt(info['fvg_not_in_families'])} |\n\n"
            f"Strategy-source rows excluded (no confluence families): {info['strategy_rows_excluded']}\n")
    print(text)
    _write(args.out_md, text)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    record = sub.add_parser("record"); record.add_argument("--arms", required=True); record.add_argument("--out", required=True)
    record.add_argument("--workers", type=int, default=None)
    report = sub.add_parser("report"); report.add_argument("--arms", required=True); report.add_argument("--provenance", required=True)
    report.add_argument("--candidate", required=True, choices=sorted(CANDIDATES))
    for flag in ("--out-md", "--out-json", "--mechanism-json"):
        report.add_argument(flag, default=None)
    context = sub.add_parser("context"); context.add_argument("--arms", required=True); context.add_argument("--provenance", required=True)
    context.add_argument("--out-md", default=None)
    args = parser.parse_args(argv)
    return {"record": cmd_record, "report": cmd_report, "context": cmd_context}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_fvg_attribution.py`
Expected: PASS, including the `slow` recorder test (the `file` profile does not deselect `slow`).
Run: `python -m radon cc -s -n C scripts/backtest/fvg_attribution.py`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/fvg_attribution.py tests/scripts/test_fvg_attribution.py
git commit -m "feat(v128): fvg_attribution.py -- baseline FVG provenance, attribution, frozen clause 6"
```

### Task V128-6: `fvg_select.py`: Stage 0 effects and the dual-gate Stage 1 judge

**Files:**
- Create: `scripts/backtest/fvg_select.py`
- Create: `tests/scripts/test_fvg_select.py`

**Interfaces:**
- Consumes: `validate_component.with_mechanism_clause`, `load_clause`, `load_arms` (V128-4); `fvg_attribution.CANDIDATES` (V128-5); `acceptance.evaluate`, `delta_expectancy_r`, `delta_standardised_win_rate`; `acceptance_harvest.evaluate_harvest`; `backtest_wf.plateau_report`.
- Produces:
  - `Cell(cid, eligible, delta_expectancy_r, delta_win_rate_pp, alert_cut_pct, failed)` (frozen dataclass).
  - `ELIGIBILITY_V72 = ("win_rate", "profit_floor", "geometry", "volume", "mechanism")` and `ELIGIBILITY_V92 = ("expectancy_gain", "win_rate_floor", "volume")`. These are the fold-train-applicable clauses; permutation is validation-only and SKIPPED at `stage="walkforward"`. Anything other than `PASS` (including `SKIPPED`) makes a cell ineligible.
  - `evaluate_cell(cid, baseline, component, mechanism: ClauseResult, *, refused, n_resamples, seed) -> Cell`, `k_plateau(cells, k) -> dict`, `select(cells: dict[str, Cell]) -> dict` with `verdict ∈ {SELECTED, NO_ELIGIBLE, SPIKE}`.
  - CLI `effects --arms P` prints `{"delta_win_rate_pp", "delta_expectancy_r", "baseline_n", "component_n"}`. CLI `select --arm CID=P (x4) --mechanism CID=P (x4) [--refused CID ...] [--resamples N] [--seed S] [--out-json P] [--out-md P]` exits 0 on `selected`, else 1. It refuses with `refused:baseline-drift` when the four arms' baselines differ.
- Frozen rule (spec, with the A3 reading): rank eligible contenders by largest ΔExpR (rounded to 4 dp), then smaller alert cut (2 dp), then `displacement` over `off`, then smaller `k` (the smaller change). A `k` contends only if `plateau_report(...)["is_plateau"]` holds and one grid neighbour is eligible. `off` contends on its clauses alone.

- [ ] **Step 1: Write the failing tests**

```python
# tests/scripts/test_fvg_select.py
"""v128 Stage 1 judge: both gates, k plateau with an eligible neighbour, at most one winner."""
import json
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import fvg_select as fs  # noqa: E402
from swingbot.core.backtesting.acceptance import ArmTrade, ClauseResult  # noqa: E402

DATES = [d.date().isoformat() for d in pd.bdate_range("2019-01-01", periods=100)]
PASSING = ClauseResult("mechanism", "PASS", "injected")


def _baseline():
    """25 tickers x 100 trades: 40 wins (+2R), 60 losses (-1R); baseline ExpR +0.20R."""
    return [ArmTrade(f"T{t}", "S/R Confluence", "3m", DATES[i], "win" if i < 40 else "loss",
                     2.0 if i < 40 else -1.0, 2.0, "confluence", "bullish") for t in range(25) for i in range(100)]


def _remove(baseline, *, losses=0, wins=0):
    out, seen = [], {}
    for trade in baseline:
        limit = losses if trade.outcome == "loss" else wins
        count = seen.get((trade.ticker, trade.outcome), 0)
        if count < limit:
            seen[(trade.ticker, trade.outcome)] = count + 1
            continue
        out.append(trade)
    return out


def _cell(cid, refused=False, **removal):
    base = _baseline()
    return fs.evaluate_cell(cid, base, _remove(base, **removal), PASSING, refused=refused, n_resamples=200, seed=42)


def _cells(off, d10, d15, d20):
    return {"off": _cell("off", **off), "disp-1.0": _cell("disp-1.0", **d10),
            "disp-1.5": _cell("disp-1.5", **d15), "disp-2.0": _cell("disp-2.0", **d20)}


def test_largest_dexpr_on_a_plateau_wins():
    result = fs.select(_cells({"losses": 1}, {"losses": 3}, {"losses": 2}, {"losses": 1}))
    assert (result["verdict"], result["winner"]) == (fs.SELECTED, "disp-1.0")
    assert result["plateaus"]["disp-1.0"]["passes"] is True


def test_off_is_eligible_on_its_clauses_alone():
    result = fs.select(_cells({"losses": 2}, {"wins": 2}, {"wins": 2}, {"wins": 2}))
    assert (result["verdict"], result["winner"]) == (fs.SELECTED, "off")
    assert "off" not in result["plateaus"]


def test_full_tie_prefers_displacement_then_the_smaller_k():
    result = fs.select(_cells({"losses": 2}, {"losses": 2}, {"losses": 2}, {"losses": 2}))
    assert result["winner"] == "disp-1.0"


def test_a_smaller_alert_cut_breaks_a_dexpr_tie():
    def cell(cid, cut):
        return fs.Cell(cid, True, 0.05, 1.0, cut, ())
    cells = {"off": cell("off", 2.0), "disp-1.0": cell("disp-1.0", 3.0),
             "disp-1.5": cell("disp-1.5", 3.0), "disp-2.0": cell("disp-2.0", 3.0)}
    assert fs.select(cells)["winner"] == "off"
    cells["disp-1.5"] = cell("disp-1.5", 1.0)
    assert fs.select(cells)["winner"] == "disp-1.5"


def test_an_isolated_eligible_k_is_a_spike():
    result = fs.select(_cells({"wins": 2}, {"wins": 2}, {"losses": 2}, {"wins": 1}))
    assert (result["verdict"], result["winner"]) == (fs.SPIKE, None)


def test_no_eligible_cell():
    result = fs.select(_cells({"wins": 2}, {"wins": 2}, {"wins": 2}, {"wins": 2}))
    assert result["verdict"] == fs.NO_ELIGIBLE


def test_a_refused_cell_is_ineligible_but_still_a_plateau_neighbour():
    cells = _cells({"wins": 2}, {"losses": 2}, {"losses": 2}, {"losses": 2})
    base = _baseline()
    cells["disp-1.5"] = fs.evaluate_cell("disp-1.5", base, _remove(base, losses=3), PASSING, refused=True,
                                         n_resamples=200, seed=42)
    assert cells["disp-1.5"].failed[0] == "refused"
    result = fs.select(cells)
    # 1.5's dExpR still shapes its neighbours' plateau, but a refused neighbour is not eligible.
    assert result["plateaus"]["disp-1.0"]["is_plateau"] is True
    assert result["plateaus"]["disp-1.0"]["eligible_neighbour"] is False
    assert (result["verdict"], result["winner"]) == (fs.SPIKE, None)


def test_both_gates_are_required():
    cell = _cell("off", wins=2)
    assert not cell.eligible
    assert "v72:win_rate" in cell.failed and "v92:expectancy_gain" in cell.failed


def test_a_failing_injected_mechanism_blocks_eligibility():
    base = _baseline()
    cell = fs.evaluate_cell("off", base, _remove(base, losses=2), ClauseResult("mechanism", "FAIL", "x"),
                            refused=False, n_resamples=200, seed=42)
    assert cell.failed == ("v72:mechanism",)


def test_plateau_with_a_missing_expectancy_fails():
    cells = {cid: fs.Cell(cid, True, 0.05, 1.0, 1.0, ()) for cid in ("off", "disp-1.0", "disp-1.5", "disp-2.0")}
    cells["disp-1.0"] = fs.Cell("disp-1.0", True, None, None, 1.0, ())
    assert fs.k_plateau(cells, 1.0)["passes"] is False


def _write(tmp_path, name, baseline, component):
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps({"provenance": {"knob_delta": {}}, "baseline": [asdict(t) for t in baseline],
                                "component": [asdict(t) for t in component]}), encoding="utf-8")
    return path


def test_select_refuses_baseline_drift(tmp_path, capsys):
    base = _baseline()
    mech = tmp_path / "m.json"
    mech.write_text(json.dumps(asdict(PASSING)), encoding="utf-8")
    argv = ["select"]
    for cid in ("off", "disp-1.0", "disp-1.5", "disp-2.0"):
        baseline = base[:-1] if cid == "disp-2.0" else base
        argv += ["--arm", f"{cid}={_write(tmp_path, cid, baseline, _remove(base, losses=1))}",
                 "--mechanism", f"{cid}={mech}"]
    assert fs.main(argv) == 1
    assert "refused:baseline-drift" in capsys.readouterr().err


def test_effects_prints_both_claims(tmp_path, capsys):
    base = _baseline()
    assert fs.main(["effects", "--arms", str(_write(tmp_path, "e", base, _remove(base, losses=2)))]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["delta_expectancy_r"] > 0 and out["delta_win_rate_pp"] > 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_fvg_select.py`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'fvg_select'`.

- [ ] **Step 3: Implement**

```python
#!/usr/bin/env python3
"""v128 Stage 0 effect printer and Stage 1 judge under BOTH gates (script layer).

Stage 1 scores each candidate's pooled fold-train arms (selection blob top level,
2018-06-01..2022-12-31) with acceptance.evaluate(stage="walkforward") -- clause 6
replaced by the frozen v128 baseline reading -- and
acceptance_harvest.evaluate_harvest(stage="walkforward"). Permutation is
validation-only and SKIPPED there. Frozen in
docs/superpowers/results/2026-10-02-v128-fvg-preregistration.md.

Run: python scripts/backtest/fvg_select.py select --arm off=logs/v128/selection-off.json ... --mechanism off=logs/v128/mechanism-selection-off.json ...
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "backtest")]

from fvg_attribution import CANDIDATES  # noqa: E402
from validate_component import load_arms, load_clause, with_mechanism_clause  # noqa: E402
from swingbot.core.backtesting.acceptance import BOOTSTRAP_RESAMPLES, delta_expectancy_r, delta_standardised_win_rate, evaluate  # noqa: E402
from swingbot.core.backtesting.acceptance_harvest import evaluate_harvest  # noqa: E402
from swingbot.core.backtesting.backtest_wf import plateau_report  # noqa: E402

ELIGIBILITY_V72 = ("win_rate", "profit_floor", "geometry", "volume", "mechanism")
ELIGIBILITY_V92 = ("expectancy_gain", "win_rate_floor", "volume")
K_GRID = (1.0, 1.5, 2.0)
K_CELL = {1.0: "disp-1.0", 1.5: "disp-1.5", 2.0: "disp-2.0"}
SELECTED, NO_ELIGIBLE, SPIKE = "selected", "no-eligible-cell", "spike"


@dataclass(frozen=True)
class Cell:
    cid: str
    eligible: bool
    delta_expectancy_r: float | None
    delta_win_rate_pp: float | None
    alert_cut_pct: float | None
    failed: tuple


def _failed(result, names, prefix) -> tuple:
    return tuple(f"{prefix}:{name}" for name in names if result.clause(name).verdict != "PASS")


def evaluate_cell(cid, baseline, component, mechanism, *, refused, n_resamples, seed) -> Cell:
    v72 = with_mechanism_clause(evaluate(baseline, component, stage="walkforward",
                                         n_resamples=n_resamples, seed=seed), mechanism)
    v92 = evaluate_harvest(baseline, component, stage="walkforward", n_resamples=n_resamples, seed=seed)
    failed = (("refused",) if refused else ()) + _failed(v72, ELIGIBILITY_V72, "v72") + _failed(v92, ELIGIBILITY_V92, "v92")
    return Cell(cid, not failed, delta_expectancy_r(baseline, component),
                delta_standardised_win_rate(baseline, component), v72.clause("volume").value, failed)


def _neighbours(k) -> list:
    i = K_GRID.index(k)
    return [K_GRID[j] for j in (i - 1, i + 1) if 0 <= j < len(K_GRID)]


def k_plateau(cells, k) -> dict:
    """plateau_report on pooled fold-train dExpR AND at least one eligible grid neighbour."""
    values = [cells[K_CELL[v]].delta_expectancy_r for v in K_GRID]
    needed = [values[K_GRID.index(v)] for v in [k, *_neighbours(k)]]
    if any(value is None for value in needed):
        return {"param": "FVG_DISPLACEMENT_ATR_K", "adopted": k, "is_plateau": False,
                "eligible_neighbour": False, "passes": False, "note": "missing dExpR"}
    report = plateau_report("FVG_DISPLACEMENT_ATR_K", list(K_GRID),
                            [0.0 if v is None else v for v in values], k)
    report["eligible_neighbour"] = any(cells[K_CELL[v]].eligible for v in _neighbours(k))
    report["passes"] = bool(report["is_plateau"] and report["eligible_neighbour"])
    return report


def _rank_key(cell) -> tuple:
    k = math.inf if cell.cid == "off" else CANDIDATES[cell.cid][1]
    return (-round(cell.delta_expectancy_r, 4), round(cell.alert_cut_pct, 2), cell.cid == "off", k)


def select(cells) -> dict:
    plateaus = {K_CELL[k]: k_plateau(cells, k) for k in K_GRID if cells[K_CELL[k]].eligible}
    pool = [cells["off"]] if cells["off"].eligible else []
    pool += [cells[cid] for cid, report in plateaus.items() if report["passes"]]
    if pool:
        verdict, winner = SELECTED, min(pool, key=_rank_key).cid
    else:
        verdict, winner = (SPIKE if any(c.eligible for c in cells.values()) else NO_ELIGIBLE), None
    return {"verdict": verdict, "winner": winner, "plateaus": plateaus,
            "cells": {cid: asdict(cell) for cid, cell in cells.items()}}


def _pairs(values) -> dict:
    out = {}
    for item in values:
        cid, _, path = item.partition("=")
        if cid not in CANDIDATES or not path:
            raise SystemExit(f"expected CID=PATH with CID in {sorted(CANDIDATES)}, got {item!r}")
        out[cid] = path
    if set(out) != set(CANDIDATES):
        raise SystemExit(f"need all four candidates {sorted(CANDIDATES)}, got {sorted(out)}")
    return out


def _render(result) -> str:
    lines = [f"### Stage 1 selection -- verdict **{result['verdict']}**, winner `{result['winner']}`", "",
             "| Cell | Eligible | dExpR | dWR (pp) | Alert cut % | Failed |", "|---|---|---|---|---|---|"]
    for cid, cell in result["cells"].items():
        dexp = "n/a" if cell["delta_expectancy_r"] is None else f"{cell['delta_expectancy_r']:+.4f}"
        dwr = "n/a" if cell["delta_win_rate_pp"] is None else f"{cell['delta_win_rate_pp']:+.2f}"
        lines.append(f"| {cid} | {cell['eligible']} | {dexp} | {dwr} | {cell['alert_cut_pct']} | "
                     f"{', '.join(cell['failed']) or '-'} |")
    lines += ["", "Plateau (k only; `off` is eligible on clauses alone):", ""]
    lines += [f"- `{cid}`: is_plateau={r['is_plateau']}, eligible_neighbour={r['eligible_neighbour']}, "
              f"passes={r['passes']}" for cid, r in result["plateaus"].items()]
    return "\n".join(lines) + "\n"


def cmd_select(args) -> int:
    arms, mechanisms = _pairs(args.arm), _pairs(args.mechanism)
    loaded = {cid: load_arms(path) for cid, path in arms.items()}
    baselines = {json.dumps([asdict(t) for t in base]) for base, _ in loaded.values()}
    if len(baselines) != 1:
        print("refused:baseline-drift -- the four candidate arms carry different baselines.", file=sys.stderr)
        return 1
    cells = {cid: evaluate_cell(cid, base, comp, load_clause(mechanisms[cid]), refused=cid in (args.refused or []),
                                n_resamples=args.resamples, seed=args.seed)
             for cid, (base, comp) in loaded.items()}
    result = select(cells)
    text = _render(result)
    print(text)
    for path, body in ((args.out_md, text), (args.out_json, json.dumps(result, indent=1))):
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True); Path(path).write_text(body, encoding="utf-8")
    return 0 if result["verdict"] == SELECTED else 1


def cmd_effects(args) -> int:
    baseline, component = load_arms(args.arms)
    print(json.dumps({"delta_win_rate_pp": delta_standardised_win_rate(baseline, component),
                      "delta_expectancy_r": delta_expectancy_r(baseline, component),
                      "baseline_n": len(baseline), "component_n": len(component)}))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    effects = sub.add_parser("effects"); effects.add_argument("--arms", required=True)
    sel = sub.add_parser("select")
    sel.add_argument("--arm", action="append", required=True); sel.add_argument("--mechanism", action="append", required=True)
    sel.add_argument("--refused", action="append", choices=sorted(CANDIDATES), default=None)
    sel.add_argument("--resamples", type=int, default=BOOTSTRAP_RESAMPLES); sel.add_argument("--seed", type=int, default=42)
    sel.add_argument("--out-json", default=None); sel.add_argument("--out-md", default=None)
    args = parser.parse_args(argv)
    return {"effects": cmd_effects, "select": cmd_select}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
```

`--resamples` defaults to `acceptance.BOOTSTRAP_RESAMPLES` (10,000), the value `validate_component.py` uses, so Stage 1 resamples exactly as the funnel does.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_fvg_select.py`
Expected: PASS.
Run: `python -m radon cc -s -n C scripts/backtest/fvg_select.py`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/fvg_select.py tests/scripts/test_fvg_select.py
git commit -m "feat(v128): fvg_select.py -- Stage 0 effects and the dual-gate Stage 1 judge"
```

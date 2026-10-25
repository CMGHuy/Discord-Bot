# v192 — Wait for a reclaim when a market plan's next open gaps toward its stop, Part 3: measurement code

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** bot patch
**Edge:** expectancy — see the index.
**Spec:** [2026-10-24-v192-gap-toward-stop-reclaim-design.md](../specs/2026-10-24-v192-gap-toward-stop-reclaim-design.md)
**Index:** [2026-10-24-v192-gap-toward-stop-reclaim_0-index.md](2026-10-24-v192-gap-toward-stop-reclaim_0-index.md) — Goal, Global Constraints, § Contracts, Review Focus, Parallelisation and the task ledger live there and bind every task below. **Never read a part whole:** `grep -n "^### Task V192-15:" -A 400 <this file>`.

**Scope of this part (V192-14..V192-16; V192-17..V192-19 continue in `_3b-judges-and-reports.md`):** the code the measurement runs of part 4 call, first half. The baseline knob delta in `measure_arms.py` and its stamp; the census of every next-open market decision, written as the `<out stem>.gap_reclaim.json` sidecar; the frozen strata (removed / re-priced / added / unchanged), the mechanism and volume clauses scored on them and the SKIPPED-fails verdict. Part 3b adds the re-priced-fixed permutation null, the Stage 1 cell, the ambiguous-bar sensitivity, the report, the CLI wiring, the report script and the autopsy `--entry-type` filter. No task here runs a measurement on real data: part 4 does, through `backtest-runner`.

**Where commands run:** every command below runs from the worktree root `.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim` (created in V192-1). Subagent shells reset their cwd between calls: prefix each command with `cd E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim &&`. Never edit the main tree's files from a task.

**Complexity:** after every code task run `python scripts/dev/complexity_gate.py`; it must pass (index § Global Constraints). `measure_arms.main` is cc 14 today: V192-14 moves its knob parsing and refusals into helpers so it ends lower, never higher. `validate_component.main` gains one branch only (the conflict check lives in a helper).

**Facts every task here relies on (verified on `main`, 2026-10-25):**

- Both arm engines drop `not_triggered` and `no_trade` results before building an `ArmTrade` (`arms/confluence_engine.py:8,30`; `StrategyEngine._skipped`). So a `gap_no_reclaim`, `open_through_stop` or `risk_cap` cancel never appears as a row: a `gap_no_reclaim` cancel of a plan the baseline filled is a baseline key **absent** from the component (the removed stratum), and an `open_through_stop` / `risk_cap` cancel is absent from both arms (excluded from both, as the spec says).
- `ArmTrade.key = (ticker, strategy, horizon_key, entry_date, source, direction)` (`acceptance.py:47`); `entry_date` is the **signal** date under v1, the same string `market_next_open._decision` writes as `NextOpenDecision.signal_date` (`str(df.index[signal_index].date())`, V192-6).
- `market_next_open.observing(callback)` (V192-6) calls `callback(NextOpenDecision)` in the **current process** only. The census therefore runs its own replay of the component arm (in a worker per ticker when parallel) instead of listening to `measure_arms`'s arm workers.
- `acceptance.evaluate` scores mechanism `SKIPPED` whenever `is_subset` is false, and its verdict ignores `SKIPPED` (`acceptance.py:584-597`, `:634`). The v192 arms are never a subset (re-priced pairs share a key with their baseline twin; `StrategyEngine.open_until` creates added trades).

---

# Phase 8 — The baseline knob delta and the census

### Task V192-14: `measure_arms.py --baseline-knob`; `baseline_knob_delta` stamp; refusals on it

**Model:** sonnet — a thread-through of one optional argument across a driver, its stamp and one judge, with tests that pin it; no rule logic.

**Files:**
- Modify: `scripts/backtest/measure_arms.py` (`_produce_population` `:166-178`, `produce` `:181-209`, `main` `:297-336`; new helpers `_deltas`, `_baseline_population_refusal`, `_refusal`)
- Modify: `swingbot/core/backtesting/arms/provenance.py` (`build_stamp` `:37-47`)
- Modify: `scripts/backtest/validate_component.py` (`stage_reachability` `:58-70`; new helper `_unreachable`)
- Test: `tests/backtest_scripts/test_measure_arms_baseline_delta.py` (create)

**Interfaces:**
- Consumes: `config.MARKET_ENTRY_NEXT_OPEN`, `config.GAP_RECLAIM_ATR`, their `REGISTRY` rows and the `apply_knobs` guard `knobs.GAP_RECLAIM_NEEDS_NEXT_OPEN = "GAP_RECLAIM_ATR > 0 needs MARKET_ENTRY_NEXT_OPEN on"` (V192-2); `parse_knob("MARKET_ENTRY_NEXT_OPEN=true") == ("MARKET_ENTRY_NEXT_OPEN", True)` (V192-2's test). Existing: `static_refusal`, `population_refusal`, `population_engine_for` (`arms/engine.py:55`), `_run_arm_all`, `run_arm`.
- Produces (index § Contracts):
  - `measure_arms.produce(stage, delta, *, baseline_delta=None, universe, spec=None, horizons=None, engines=DEFAULT_ENGINES, workers=None, progress_path=None, preregistration=None) -> dict` — the baseline arm (both the per-ticker and the population path) runs under `baseline_delta or {}`.
  - `measure_arms.main` accepts `--baseline-knob ATTR=value` (repeatable, optional, default none).
  - `provenance.build_stamp(..., baseline_knob_delta=None)` — key `"baseline_knob_delta"` written **only when non-empty**, so every stamp produced without the flag is key-for-key what it is today.
  - Refusal token for a baseline delta that would route to a different population engine than the component: `refused:baseline-population-mismatch`.
  - `validate_component.stage_reachability` classifies the stamped `baseline_knob_delta` with the same `reachability.classify` rule as `knob_delta` and prints it on its own line `baseline knobs: {...}` when non-empty.

**Why:** the spec's baseline arm is "every market plan fills at `Open[t+1]`" (`MARKET_ENTRY_NEXT_OPEN=true`), the component adds `GAP_RECLAIM_ATR=g`. Today the baseline delta is the literal `{}` in both producers (`measure_arms.py:173`, `:194`), so a run could only compare the veto against today's close fill, which would mix the next-open change into the veto's effect. The stamp must say what the baseline ran under, or a judge reading the file cannot tell a v192 pair from a close-fill pair.

- [ ] **Step 1: Write the failing tests** — create `tests/backtest_scripts/test_measure_arms_baseline_delta.py`

```python
"""V192-14: measure_arms --baseline-knob -- the baseline arm runs under its own delta, the stamp
records it beside knob_delta (absent when empty, so every older stamp is unchanged), and the static
and population refusals run on it before any compute. validate_component's reachability stage
classifies it too."""
import dataclasses
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import measure_arms as ma  # noqa: E402

from swingbot import config  # noqa: E402
from swingbot.core.backtesting.arms import provenance as pv  # noqa: E402
from swingbot.core.backtesting.arms.engine import run_arm  # noqa: E402
from swingbot.core.backtesting.arms.windows import ALL_HORIZONS, StageSpec  # noqa: E402
from tests.backtesting.test_v74_fixture import load_v74_fixture  # noqa: E402

FIXTURE = load_v74_fixture()
PILOT = StageSpec("pilot", ("2024-01-01", "2025-12-31"), full_width=False)
NEXT_OPEN = {"MARKET_ENTRY_NEXT_OPEN": True}
VETO = {"MARKET_ENTRY_NEXT_OPEN": True, "GAP_RECLAIM_ATR": 0.25}


@pytest.fixture(autouse=True)
def _world(monkeypatch):
    from swingbot.core.marketdata import training_data
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance")   # v162: no store in tests
    training_data.reset()
    monkeypatch.setattr(ma, "load_frame", lambda ticker: FIXTURE.get(ticker))
    monkeypatch.setattr(ma, "cached_universe", lambda: ["AAPL"])
    yield
    training_data.reset()


def _stamp(**over):
    kw = dict(stage="pilot", signal_window=("2018-06-01", "2020-12-31"), universe=["AAPL"],
              horizons=ALL_HORIZONS, engines=("confluence", "strategy"), knob_delta=VETO,
              engine_hash_baseline="h", engine_hash_component="h", changed_outcomes=1)
    kw.update(over)
    return pv.build_stamp(**kw)


def test_the_stamp_has_no_baseline_key_when_the_delta_is_empty():
    assert "baseline_knob_delta" not in _stamp()
    assert "baseline_knob_delta" not in _stamp(baseline_knob_delta={})
    assert "baseline_knob_delta" not in _stamp(baseline_knob_delta=None)


def test_the_stamp_records_a_non_empty_baseline_delta_beside_knob_delta():
    stamp = _stamp(baseline_knob_delta=NEXT_OPEN)
    assert stamp["baseline_knob_delta"] == NEXT_OPEN and stamp["knob_delta"] == VETO


def _recording(monkeypatch):
    seen = []

    def fake_run_arm(ticker, frame, engine_ids, horizons, signal_window, delta):
        seen.append(dict(delta))
        return []
    monkeypatch.setattr(ma, "run_arm", fake_run_arm)
    return seen


def test_produce_runs_the_baseline_under_its_own_delta(monkeypatch):
    seen = _recording(monkeypatch)
    blob = ma.produce("pilot", VETO, baseline_delta=NEXT_OPEN, universe=["AAPL"], spec=PILOT,
                      horizons=("4w",), engines=("confluence",), workers=1)
    assert seen == [NEXT_OPEN, VETO]
    assert blob["provenance"]["baseline_knob_delta"] == NEXT_OPEN


def test_produce_without_a_baseline_delta_is_todays_empty_baseline(monkeypatch):
    seen = _recording(monkeypatch)
    blob = ma.produce("pilot", NEXT_OPEN, universe=["AAPL"], spec=PILOT,
                      horizons=("4w",), engines=("confluence",), workers=1)
    assert seen == [{}, NEXT_OPEN]
    assert "baseline_knob_delta" not in blob["provenance"]


def test_the_population_path_takes_the_baseline_delta_too(monkeypatch):
    seen = []
    monkeypatch.setattr(ma, "population_engine_for", lambda delta: "pop")
    monkeypatch.setattr(ma, "population_symbols", lambda: [])
    monkeypatch.setattr(ma, "_population_arm",
                        lambda engine_id, frames, universe, horizons, window, delta: seen.append(dict(delta)) or [])
    blob = ma.produce("pilot", VETO, baseline_delta=NEXT_OPEN, universe=["AAPL"], spec=PILOT,
                      horizons=("4w",), workers=1)
    assert seen == [NEXT_OPEN, VETO]
    assert blob["provenance"]["engines"] == ["pop"]


def test_the_baseline_rows_are_the_rows_of_its_delta():
    blob = ma.produce("pilot", VETO, baseline_delta=NEXT_OPEN, universe=["AAPL"], spec=PILOT,
                      horizons=("4w",), engines=("confluence",), workers=1)
    direct = run_arm("AAPL", FIXTURE["AAPL"], ("confluence",), ("4w",), PILOT.signal_window, NEXT_OPEN)
    start, end = PILOT.signal_window
    assert blob["baseline"] == [dataclasses.asdict(t) for t in direct if start <= t.entry_date <= end]


def _main(tmp_path, *extra):
    return ma.main(["--knob", "MARKET_ENTRY_NEXT_OPEN=true", "--knob", "GAP_RECLAIM_ATR=0.25",
                    "--stage", "pilot", "--out", str(tmp_path / "arms.json"), "--workers", "1", *extra])


def test_main_passes_the_parsed_baseline_delta_to_produce(monkeypatch, tmp_path):
    captured = {}

    def fake_produce(stage, delta, **kw):
        captured.update(stage=stage, delta=delta, **kw)
        return {"provenance": {"changed_outcomes": 3}}
    monkeypatch.setattr(ma, "produce", fake_produce)
    monkeypatch.setattr(ma, "_write_sidecar_or_warn", lambda *a: None)
    monkeypatch.setattr(ma.training_data, "write_provenance", lambda out: None)
    assert _main(tmp_path, "--baseline-knob", "MARKET_ENTRY_NEXT_OPEN=true") == 0
    assert captured["delta"] == VETO and captured["baseline_delta"] == NEXT_OPEN


def test_main_without_the_flag_passes_an_empty_baseline_delta(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr(ma, "produce", lambda stage, delta, **kw: captured.update(kw) or
                        {"provenance": {"changed_outcomes": 3}})
    monkeypatch.setattr(ma, "_write_sidecar_or_warn", lambda *a: None)
    monkeypatch.setattr(ma.training_data, "write_provenance", lambda out: None)
    assert ma.main(["--knob", "MIN_REWARD_PCT=4", "--stage", "pilot",
                    "--out", str(tmp_path / "arms.json"), "--workers", "1"]) == 0
    assert captured["baseline_delta"] == {}


@pytest.mark.parametrize("knob,token", [
    ("STALL_EXIT_ENABLED=true", "refused:unreachable:journal_dependent"),
    ("LOG_LEVEL=DEBUG", "refused:unreachable:unclassified"),
    ("MIN_REWARD_PCT=abc", "refused:bad-knob"),
])
def test_a_bad_baseline_knob_is_refused_before_any_compute(monkeypatch, tmp_path, capsys, knob, token):
    monkeypatch.setattr(ma, "run_arm", lambda *a, **k: pytest.fail("computed"))
    assert _main(tmp_path, "--baseline-knob", knob) == 1
    assert token in capsys.readouterr().err
    assert not (tmp_path / "arms.json").exists()


def test_a_baseline_delta_routing_to_another_population_engine_is_refused(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(ma, "run_arm", lambda *a, **k: pytest.fail("computed"))
    monkeypatch.setattr(ma, "population_engine_for",
                        lambda delta: "pop" if "MIN_REWARD_PCT" in delta else None)
    monkeypatch.setattr(ma, "get_population_engine", lambda engine_id, **kw: object())
    assert _main(tmp_path, "--baseline-knob", "MIN_REWARD_PCT=4") == 1
    assert "refused:baseline-population-mismatch" in capsys.readouterr().err


def test_a_lone_gap_knob_in_the_baseline_trips_the_apply_knobs_guard(tmp_path):
    with pytest.raises(RuntimeError, match="needs MARKET_ENTRY_NEXT_OPEN on"):
        ma.main(["--knob", "MARKET_ENTRY_NEXT_OPEN=true", "--baseline-knob", "GAP_RECLAIM_ATR=0.25",
                 "--stage", "pilot", "--out", str(tmp_path / "arms.json"), "--workers", "1"])


# --- validate_component's reachability stage reads the baseline delta too -----------------------

def _vc_arms(tmp_path, baseline_delta):
    from tests.backtesting.test_validate_component_stamps import rows
    baseline, component = rows()
    stamp = _stamp(knob_delta={"MIN_REWARD_PCT": 4.0}, baseline_knob_delta=baseline_delta)
    path = tmp_path / "vc-arms.json"
    path.write_text(json.dumps({"provenance": stamp, "baseline": baseline, "component": component}),
                    encoding="utf-8")
    return path


def _reachability(path):
    from tests.backtesting.test_validate_component_stamps import vc
    return vc.main(["--stage", "reachability", "--arms", str(path), "--title", "t", "--window", "pilot"])


def test_reachability_prints_a_reachable_baseline_delta(tmp_path, capsys):
    assert _reachability(_vc_arms(tmp_path, NEXT_OPEN)) == 0
    out = capsys.readouterr().out
    assert "baseline knobs: {'MARKET_ENTRY_NEXT_OPEN': True}" in out and "REACHABLE" in out


def test_reachability_without_a_baseline_delta_prints_no_baseline_line(tmp_path, capsys):
    assert _reachability(_vc_arms(tmp_path, None)) == 0
    assert "baseline knobs:" not in capsys.readouterr().out


def test_reachability_refuses_an_unreachable_baseline_knob(tmp_path, capsys):
    assert _reachability(_vc_arms(tmp_path, {"STALL_EXIT_ENABLED": True})) == 1
    assert "refused:unreachable:journal_dependent" in capsys.readouterr().err
```

- [ ] **Step 2: Run them to see them fail**

```bash
python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_arms_baseline_delta.py
```

Expected: FAIL — `build_stamp() got an unexpected keyword argument 'baseline_knob_delta'`, `produce() got an unexpected keyword argument 'baseline_delta'`, `unrecognized arguments: --baseline-knob`.

- [ ] **Step 3: `provenance.build_stamp`** — replace the function (`swingbot/core/backtesting/arms/provenance.py:37-47`)

```python
def build_stamp(*, stage, signal_window, universe, horizons, engines, knob_delta,
                engine_hash_baseline, engine_hash_component, changed_outcomes,
                preregistration=None, baseline_knob_delta=None) -> dict:
    """The producer stamp. ``baseline_knob_delta`` (v192) is the config delta the BASELINE arm
    ran under; it is written only when non-empty, so a stamp made without one is key-for-key
    the pre-v192 stamp."""
    stamp = {"producer": "measure_arms", "producer_version": PRODUCER_VERSION,
             "stage": stage, "signal_window": list(signal_window), "universe": sorted(universe),
             "universe_count": len(universe), "horizons": list(horizons), "engines": list(engines),
             "knob_delta": dict(knob_delta),
             "engine_hash": {"baseline": engine_hash_baseline, "component": engine_hash_component},
             "changed_outcomes": int(changed_outcomes), "preregistration": preregistration,
             "git_head": git_head(),
             "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    if baseline_knob_delta:
        stamp["baseline_knob_delta"] = dict(baseline_knob_delta)
    return stamp
```

- [ ] **Step 4: `measure_arms.py` — producers**

Replace `_produce_population` (`:166-178`):

```python
def _produce_population(engine_id, universe, horizons, signal_window, delta, baseline_delta=None) -> tuple:
    """Load each frame once, then baseline (``baseline_delta``, by default none: the knob off) and
    component (the knob applied) over the identical frames. One process: the
    replay is cross-sectional per decision date, not per ticker."""
    frames = {symbol: frame for symbol in population_symbols()
              if (frame := load_frame(symbol)) is not None}
    baseline_hash = code_hash()
    baseline = _population_arm(engine_id, frames, universe, horizons, signal_window, dict(baseline_delta or {}))
    print(f"  [baseline] {len(baseline)} trades", flush=True)
    component_hash = code_hash()
    component = _population_arm(engine_id, frames, universe, horizons, signal_window, delta)
    print(f"  [component] {len(component)} trades", flush=True)
    return baseline_hash, baseline, component_hash, component
```

Replace `produce` (`:181-209`):

```python
def produce(stage, delta, *, universe, baseline_delta=None, spec=None, horizons=None, engines=DEFAULT_ENGINES,
            workers=None, progress_path=None, preregistration=None) -> dict:
    """v192: ``baseline_delta`` is the baseline arm's own config delta (default none, today's
    baseline); the stamp records it as ``baseline_knob_delta`` when non-empty."""
    spec = spec or windows.resolve(stage)
    horizons = tuple(horizons or windows.ALL_HORIZONS)
    baseline_delta = dict(baseline_delta or {})
    population = population_engine_for(delta)
    if population is not None:
        engines = (population,)
        baseline_hash, baseline, component_hash, component = _produce_population(
            population, universe, horizons, spec.signal_window, delta, baseline_delta)
    else:
        workers = _resolve_replay_workers(workers)
        total, counter = 2 * len(universe), [0]
        baseline_hash = code_hash()
        baseline = _run_arm_all("baseline", universe, engines, horizons, spec.signal_window, baseline_delta, workers, progress_path, counter, total)
        component_hash = code_hash()
        component = _run_arm_all("component", universe, engines, horizons, spec.signal_window, delta, workers, progress_path, counter, total)
    stamp = build_stamp(stage=stage, signal_window=spec.signal_window, universe=universe, horizons=horizons,
                        engines=engines, knob_delta=delta, engine_hash_baseline=baseline_hash,
                        engine_hash_component=component_hash, changed_outcomes=changed_outcomes(baseline, component),
                        preregistration=preregistration, baseline_knob_delta=baseline_delta)
    blob: dict = {"provenance": stamp}
    if spec.fold_key != "folds":
        blob["baseline"], blob["component"] = _rows(baseline, *spec.signal_window), _rows(component, *spec.signal_window)
    if spec.folds:
        blob[spec.fold_key] = [{spec.fold_label_key: label, "baseline": _rows(baseline, start, end),
                                "component": _rows(component, start, end)} for label, start, end in spec.folds]
    if progress_path is not None:
        Path(progress_path).unlink(missing_ok=True)
    return blob
```

(Every caller passes `universe` and the rest by keyword — `git grep -n "produce(" -- scripts tests` — so the new keyword breaks none of them.)

- [ ] **Step 5: `measure_arms.py` — parsing and refusals out of `main`**

Add after `population_refusal` (`:93`):

```python
def _baseline_population_refusal(delta: dict, baseline_delta: dict):
    """v192: the population path runs the baseline under the component's engine, so a baseline
    delta that would route to a different whole-scan engine cannot be honoured."""
    engine_id = population_engine_for(baseline_delta)
    if engine_id is None or engine_id == population_engine_for(delta):
        return None
    return "refused:baseline-population-mismatch", (
        f"the baseline delta routes to {engine_id}, the component to {population_engine_for(delta)}.")


def _refusal(delta: dict, baseline_delta: dict):
    """The first static or population refusal over the component delta, then the baseline delta."""
    return (static_refusal(delta) or population_refusal(delta) or static_refusal(baseline_delta)
            or population_refusal(baseline_delta) or _baseline_population_refusal(delta, baseline_delta))


def _unclassified(knobs) -> str | None:
    return next((knob.partition("=")[0] for knob in knobs
                 if reachability.classify(knob.partition("=")[0]) == reachability.UNCLASSIFIED), None)


def _deltas(args):
    """(component delta, baseline delta) parsed from --knob / --baseline-knob, or exit code 1 with
    the refusal on stderr when a knob is unknown or its value does not cast."""
    try:
        delta = dict(parse_knob(knob) for knob in args.knob)
        baseline_delta = dict(parse_knob(knob) for knob in args.baseline_knob)
    except ValueError as exc:
        unknown = _unclassified([*args.knob, *args.baseline_knob])
        print(f"{'refused:unreachable:unclassified' if unknown else 'refused:bad-knob'} -- {exc}", file=sys.stderr)
        return 1
    return delta, baseline_delta
```

Replace `main` (`:297-336`) with:

```python
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--knob", action="append", required=True)
    parser.add_argument("--baseline-knob", action="append", default=[],
                        help="v192: ATTR=value the BASELINE arm runs under (repeatable; default none)")
    parser.add_argument("--stage", required=True, choices=sorted(windows.STAGES))
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--preregistration", type=Path, default=None)
    from fetch_backtest_data import add_data_source_arg, apply_data_source
    add_data_source_arg(parser)
    instrument_cli.add_instrument_arg(parser)
    args = parser.parse_args(argv)
    instrument_cli.require_v1(instrument_cli.spec_from_args(args), "measure_arms.py",
                              "phase 5 (v2 stage table)")
    apply_data_source(args)
    deltas = _deltas(args)
    if isinstance(deltas, int):
        return deltas
    delta, baseline_delta = deltas
    refusal = _refusal(delta, baseline_delta)
    if refusal:
        print(f"{refusal[0]} -- {refusal[1]} Budget intact.", file=sys.stderr)
        return 1
    if args.stage == "validation" and not (args.preregistration and args.preregistration.exists()):
        print("refused:no-preregistration -- --stage validation needs --preregistration <committed doc>. This is the one shot.", file=sys.stderr)
        return 1
    universe = windows.universe_for(args.stage, cached_universe())
    LOG_DIR.mkdir(exist_ok=True)
    progress = LOG_DIR / f"measure_arms.{uuid.uuid4().hex[:8]}.progress"
    blob = produce(args.stage, delta, universe=universe, baseline_delta=baseline_delta, workers=args.workers,
                   progress_path=progress, preregistration=str(args.preregistration) if args.preregistration else None)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(blob), encoding="utf-8")
    training_data.write_provenance(args.out)
    _write_sidecar_or_warn(args.out, blob, delta, universe, windows.resolve(args.stage))
    if args.stage == "pilot" and blob["provenance"]["changed_outcomes"] == 0:
        print("refused:zero-diff -- the component changed no trade on the pilot slice. Budget intact.", file=sys.stderr)
        return 1
    return 0
```

Add one line to the module docstring after the v180 line:

```
v192: --baseline-knob ATTR=value runs the BASELINE arm under its own delta (stamped as baseline_knob_delta).
```

- [ ] **Step 6: `validate_component.stage_reachability`** — replace `:58-70`

```python
def _unreachable(delta):
    """The refusal line for the first knob of ``delta`` the replay cannot reach, else None."""
    for attr in delta:
        cls = reachability.classify(attr)
        if cls != reachability.REACHABLE:
            return f"refused:unreachable:{cls} -- {reachability.reason(attr)} Budget intact."
    return None

def stage_reachability(args):
    stamp = json.loads(Path(args.arms).read_text()).get("provenance") or {}
    delta, baseline_delta = stamp.get("knob_delta") or {}, stamp.get("baseline_knob_delta") or {}
    refusal = _unreachable(delta) or _unreachable(baseline_delta)
    if refusal:
        print(refusal, file=sys.stderr); return 1
    baseline, component = load_arms(args.arms); changed = changed_outcomes(baseline, component)
    print(f"knobs: {delta} baseline N={len(baseline)} component N={len(component)} changed outcomes: {changed}")
    if baseline_delta:
        print(f"baseline knobs: {baseline_delta}")
    split = population_split(baseline, component)
    print(f"split removed={len(split['removed'])} added={len(split['added'])} changed={len(split['changed'])} is_subset={split['is_subset']}")
    if not changed:
        print("refused:zero-diff -- the component reached no trade. Budget intact.", file=sys.stderr); return 1
    print("REACHABLE -- the component changes trades; Stage 0 may proceed."); return 0
```

The `knobs: ...` line and every refusal string keep today's text (`tests/backtesting/test_validate_component_stamps.py` pins them).

- [ ] **Step 7: Run the new tests, the existing driver and judge tests, and the gate**

```bash
python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_arms_baseline_delta.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_arms.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_arms_turtle_sidecar.py
python scripts/dev/testrun.py file tests/backtesting/arms/test_provenance.py
python scripts/dev/testrun.py file tests/backtesting/test_validate_component_stamps.py
python scripts/dev/testrun.py file tests/backtesting/arms/test_v192_flag_off_golden.py
python scripts/dev/complexity_gate.py
```

Expected: `0 failed` each; the gate passes (`main` drops from 14 to about 11; `_refusal` cc 5, `_deltas` cc 4).

- [ ] **Step 8: Commit (in the worktree)**

```bash
git add scripts/backtest/measure_arms.py swingbot/core/backtesting/arms/provenance.py scripts/backtest/validate_component.py tests/backtest_scripts/test_measure_arms_baseline_delta.py
git commit -m "feat(v192): measure_arms --baseline-knob -- baseline arm under its own delta, stamped baseline_knob_delta, refusals on it"
```

### Task V192-15: Census module and the `gap_reclaim` sidecar

**Model:** opus — the census is the only source of the re-priced stratum the gate is frozen on; a wrong key or a missed decision silently mislabels trades, and it must observe a replay running in worker processes.

**Files:**
- Create: `swingbot/core/backtesting/arms/gap_reclaim_census.py`
- Modify: `scripts/backtest/measure_arms.py` (new `GAP_RECLAIM_KNOB`, `gap_reclaim_sidecar`; one more `_SIDECARS` row `:276`; one docstring line)
- Test: `tests/backtesting/arms/test_gap_reclaim_census.py` (create)

**Interfaces:**
- Consumes: `market_next_open.NextOpenDecision` (fields `ticker, strategy, horizon_key, source, direction, signal_date, entry, stop, open_price, atr, reclaim_level, gap_atr, decision, reclaimed, ambiguous, fill_price`), `market_next_open.observing(callback)`, `market_next_open.NO_BAR = "no_bar"`, `market_next_open._emit` (tests only) — V192-6/V192-7; `gap_reclaim.FILL_OPEN`, `RECLAIM_WAIT`, `OPEN_THROUGH_STOP`, `RISK_CAP` (V192-4); `run_arm(ticker, df, engine_ids, horizons, signal_window, delta)` (`arms/engine.py:31`); `training_data.load_daily`, `training_data.select`, `training_data.active` (existing); `measure_arms._component_and_spans`, `_resolve_replay_workers`, `DEFAULT_ENGINES`, `windows.ALL_HORIZONS` (existing); `produce(..., baseline_delta=)` and the stamp key `baseline_knob_delta` (V192-14).
- Produces (index § Contracts, plus two in-part readers V192-18 calls):
  - `SIDECAR_SUFFIX = "gap_reclaim"`; `REACHABLE = "REACHABLE"`; `ZERO_DIFF = "refused:zero-diff"`; `KEY_FIELDS`; `GAP_GRID = (0.10, 0.25, 0.50)`; `GAP_ATR_QUANTILES`.
  - `row_key(row: dict) -> tuple` — `(ticker, strategy, horizon_key, signal_date, source, direction)`, equal to `ArmTrade.key` of the trade the same plan produced.
  - `census_ticker(ticker, df, engines, horizons, signal_window, delta) -> list[dict]` — `dataclasses.asdict(NextOpenDecision)` rows with `signal_date` inside the window.
  - `census(universe, engines, horizons, signal_window, delta, *, workers=None) -> list[dict]` — rows sorted by ticker, then replay order.
  - `reachability_summary(rows) -> dict` — `{"cells": [{horizon_key, direction, market_plans, filled_at_open, armed, reclaimed, ambiguous, gap_no_reclaim, open_through_stop, risk_cap, no_bar, reclaim_rate, ambiguous_share}], "total": {...same counts...}, "gap_atr": {"n", "q10".."q90", "share_at_or_above": {"0.1": .., "0.25": .., "0.5": ..}}, "verdict": REACHABLE | ZERO_DIFF}`.
  - `repriced_keys(rows) -> set[tuple]`, `ambiguous_keys(rows) -> set[tuple]`.
  - `sidecar_path(arms_path) -> Path` (`<stem>.gap_reclaim.json` beside the arms) and `load_sidecar(arms_path) -> dict | None` — the readers V192-18's CLIs use.
  - `measure_arms.GAP_RECLAIM_KNOB = "GAP_RECLAIM_ATR"`; `measure_arms.gap_reclaim_sidecar(blob, delta, universe, spec) -> dict | None`, registered in `_SIDECARS` as `("gap_reclaim", "gap_reclaim_sidecar")`. Sidecar keys: `knob_delta`, `baseline_knob_delta`, `signal_window`, `universe_count`, `summary`, `repriced_in_component`, `repriced_absent_from_component`, `rows`.

**Why a separate replay:** `observing` is in-process (V192-6), and `measure_arms` runs each arm in a `ProcessPoolExecutor`; a callback registered in the driver never sees a worker's decisions. The census therefore replays the **component** arm once more, observing inside each worker, and returns plain dicts. It costs one more arm's wall time per run; part 4's runner budgets for it. The arm rows are never touched, and a census failure only warns (the existing `_write_sidecar_or_warn` contract): V192-18's judges refuse a v192 validation without the sidecar.

- [ ] **Step 1: Write the failing tests** — create `tests/backtesting/arms/test_gap_reclaim_census.py`

```python
"""V192-15: the gap-reclaim census -- every next-open market decision the component replay makes,
keyed as ArmTrade.key -- and the measure_arms sidecar <out stem>.gap_reclaim.json."""
import dataclasses
import json
import sys
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.backtesting.acceptance import ArmTrade
from swingbot.core.backtesting.arms import gap_reclaim_census as grc
from swingbot.core.backtesting.arms.engine import run_arm
from swingbot.core.planning import gap_reclaim as gr
from swingbot.core.planning import market_next_open as mno
from tests.backtesting.test_v74_fixture import load_v74_fixture

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import measure_arms as ma  # noqa: E402

FIXTURE = load_v74_fixture()
WINDOW = ("1900-01-01", "2100-12-31")
VETO = {"MARKET_ENTRY_NEXT_OPEN": True, "GAP_RECLAIM_ATR": 0.10}
DECISIONS = {gr.FILL_OPEN, gr.RECLAIM_WAIT, gr.OPEN_THROUGH_STOP, gr.RISK_CAP, mno.NO_BAR}


@pytest.fixture(autouse=True)
def _legacy_source(monkeypatch):
    from swingbot.core.marketdata import training_data
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance")   # v162: no store in tests
    training_data.reset()
    yield
    training_data.reset()


def decision(**over):
    base = dict(ticker="AAA", strategy="RSI", horizon_key="4w", source="strategy", direction="bullish",
                signal_date="2021-03-01", entry=100.0, stop=95.0, open_price=99.0, atr=2.0,
                reclaim_level=99.8, gap_atr=0.5, decision=gr.RECLAIM_WAIT, reclaimed=False,
                ambiguous=False, fill_price=None)
    base.update(over)
    return mno.NextOpenDecision(**base)


def row(**over):
    return dataclasses.asdict(decision(**over))


def test_row_key_is_the_arm_trade_key():
    trade = ArmTrade("AAA", "RSI", "4w", "2021-03-01", "win", 1.0, 2.0, "strategy", "bullish")
    assert grc.row_key(row()) == trade.key


def _emitting_run_arm(monkeypatch, decisions_for, seen_deltas=None):
    def fake_run_arm(ticker, df, engine_ids, horizons, signal_window, delta):
        if seen_deltas is not None:
            seen_deltas.append(dict(delta))
        for item in decisions_for(ticker):
            mno._emit(item)
        return []
    monkeypatch.setattr(grc, "run_arm", fake_run_arm)


def test_census_ticker_keeps_only_decisions_inside_the_window(monkeypatch):
    deltas = []
    _emitting_run_arm(monkeypatch, lambda t: [decision(signal_date="2020-12-31"),
                                              decision(signal_date="2021-03-01"),
                                              decision(signal_date="2023-01-02")], deltas)
    rows = grc.census_ticker("AAA", object(), ("strategy",), ("4w",), ("2021-01-01", "2022-12-31"), VETO)
    assert [r["signal_date"] for r in rows] == ["2021-03-01"]
    assert rows[0] == row()
    assert deltas == [VETO]


def test_the_observer_is_released_after_the_census(monkeypatch):
    before = list(mno._OBSERVERS)
    _emitting_run_arm(monkeypatch, lambda t: [decision()])
    grc.census_ticker("AAA", object(), ("strategy",), ("4w",), WINDOW, VETO)
    assert mno._OBSERVERS == before


def test_census_skips_a_ticker_without_a_frame_and_sorts_by_ticker(monkeypatch, capsys):
    monkeypatch.setattr(grc, "load_frame", {"AAA": object(), "BBB": object()}.get)
    _emitting_run_arm(monkeypatch, lambda t: [decision(ticker=t)])
    rows = grc.census(["BBB", "ZZZ", "AAA"], ("strategy",), ("4w",), WINDOW, VETO, workers=1)
    assert [r["ticker"] for r in rows] == ["AAA", "BBB"]
    assert "[census] 3/3 (100%)" in capsys.readouterr().out


def _mixed_rows():
    return [
        row(decision=gr.FILL_OPEN, gap_atr=0.05, fill_price=99.0),
        row(signal_date="2021-03-02", reclaimed=True, ambiguous=True, fill_price=100.01, gap_atr=0.30),
        row(signal_date="2021-03-03", gap_atr=0.60),
        row(signal_date="2021-03-04", decision=gr.OPEN_THROUGH_STOP, gap_atr=2.6),
        row(signal_date="2021-03-05", decision=gr.RISK_CAP, gap_atr=0.12),
        row(signal_date="2021-03-08", direction="bearish", decision=gr.FILL_OPEN, gap_atr=-0.2),
        row(signal_date="2021-03-09", horizon_key="2w", decision=mno.NO_BAR, open_price=None, gap_atr=None),
    ]


def test_reachability_summary_counts_every_decision_kind():
    summary = grc.reachability_summary(_mixed_rows())
    total = summary["total"]
    assert (total["market_plans"], total["filled_at_open"], total["armed"], total["reclaimed"]) == (7, 2, 2, 1)
    assert (total["ambiguous"], total["gap_no_reclaim"], total["open_through_stop"]) == (1, 1, 1)
    assert (total["risk_cap"], total["no_bar"]) == (1, 1)
    assert total["reclaim_rate"] == 0.5 and total["ambiguous_share"] == 1.0
    assert [(c["horizon_key"], c["direction"], c["market_plans"]) for c in summary["cells"]] == [
        ("2w", "bullish", 1), ("4w", "bearish", 1), ("4w", "bullish", 5)]
    assert summary["verdict"] == grc.REACHABLE == "REACHABLE"


def test_reachability_summary_reports_the_gap_over_atr_distribution():
    gap = grc.reachability_summary(_mixed_rows())["gap_atr"]
    assert gap["n"] == 6
    assert gap["q50"] == pytest.approx(0.21)
    assert gap["share_at_or_above"] == {"0.1": pytest.approx(4 / 6), "0.25": pytest.approx(3 / 6),
                                        "0.5": pytest.approx(2 / 6)}


def test_no_armed_plan_is_zero_diff():
    summary = grc.reachability_summary([row(decision=gr.FILL_OPEN, gap_atr=0.01)])
    assert summary["verdict"] == grc.ZERO_DIFF == "refused:zero-diff"
    assert summary["total"]["reclaim_rate"] is None and summary["total"]["ambiguous_share"] is None


def test_an_empty_census_is_zero_diff_with_no_distribution():
    summary = grc.reachability_summary([])
    assert summary["verdict"] == grc.ZERO_DIFF and summary["cells"] == []
    assert summary["gap_atr"] == {"n": 0, "share_at_or_above": {}}


def test_repriced_and_ambiguous_keys():
    rows = _mixed_rows()
    assert grc.repriced_keys(rows) == {grc.row_key(rows[1])}
    assert grc.ambiguous_keys(rows) == {grc.row_key(rows[1])}
    assert grc.repriced_keys([]) == set() == grc.ambiguous_keys([])


def test_sidecar_path_and_loader(tmp_path):
    arms = tmp_path / "v192-g025-selection.json"
    assert grc.sidecar_path(arms) == tmp_path / "v192-g025-selection.gap_reclaim.json"
    assert grc.load_sidecar(arms) is None
    grc.sidecar_path(arms).write_text(json.dumps({"rows": []}), encoding="utf-8")
    assert grc.load_sidecar(arms) == {"rows": []}


# --- integration on the v74 AAPL fixture (V192-5..V192-7 behaviour) ---------------------------

def test_with_both_knobs_off_the_census_sees_nothing():
    assert grc.census_ticker("AAPL", FIXTURE["AAPL"], ("confluence", "strategy"), ("4w",), WINDOW, {}) == []


def test_the_veto_census_pairs_with_the_component_rows():
    rows = grc.census_ticker("AAPL", FIXTURE["AAPL"], ("confluence", "strategy"), ("4w",), WINDOW, VETO)
    component = run_arm("AAPL", FIXTURE["AAPL"], ("confluence", "strategy"), ("4w",), WINDOW, VETO)
    assert rows and {r["decision"] for r in rows} <= DECISIONS
    assert grc.repriced_keys(rows) <= {t.key for t in component}
    assert all(r["fill_price"] == r["open_price"] for r in rows if r["decision"] == gr.FILL_OPEN)
    assert all(r["reclaim_level"] is not None for r in rows if r["decision"] == gr.RECLAIM_WAIT)
    assert grc.reachability_summary(rows)["total"]["market_plans"] == len(rows)


# --- the measure_arms sidecar ------------------------------------------------------------------

def test_the_sidecar_row_is_registered_under_the_census_suffix():
    assert ("gap_reclaim", "gap_reclaim_sidecar") in ma._SIDECARS
    assert grc.SIDECAR_SUFFIX == "gap_reclaim" and ma.GAP_RECLAIM_KNOB == "GAP_RECLAIM_ATR"


@pytest.mark.parametrize("delta", [{"MARKET_ENTRY_NEXT_OPEN": True}, {"MIN_REWARD_PCT": 4.0},
                                   {"MARKET_ENTRY_NEXT_OPEN": True, "GAP_RECLAIM_ATR": 0.0}])
def test_no_sidecar_without_a_positive_gap_knob(monkeypatch, delta):
    monkeypatch.setattr(grc, "census", lambda *a, **k: pytest.fail("census ran"))
    assert ma.gap_reclaim_sidecar({}, delta, ["AAA"], ma.windows.resolve("pilot")) is None


def test_the_sidecar_carries_the_census_and_counts_repriced_component_rows(monkeypatch):
    calls = []
    census_rows = [row(reclaimed=True, fill_price=100.01), row(ticker="BBB", reclaimed=True, fill_price=100.01)]
    monkeypatch.setattr(grc, "census", lambda *a, **k: calls.append((a, k)) or census_rows)
    monkeypatch.setattr(ma, "_resolve_replay_workers", lambda workers: 1)
    trade = ArmTrade("AAA", "RSI", "4w", "2021-03-01", "win", 1.0, 2.0, "strategy", "bullish")
    blob = {"provenance": {"engines": ["strategy"], "horizons": ["4w"],
                           "baseline_knob_delta": {"MARKET_ENTRY_NEXT_OPEN": True}},
            "component": [dataclasses.asdict(trade)]}
    spec = ma.windows.resolve("pilot")
    side = ma.gap_reclaim_sidecar(blob, VETO, ["AAA", "BBB"], spec)
    assert calls == [((["AAA", "BBB"], ["strategy"], ["4w"], tuple(spec.signal_window), VETO), {"workers": 1})]
    assert side["repriced_in_component"] == 1 and side["repriced_absent_from_component"] == 1
    assert side["knob_delta"] == VETO and side["baseline_knob_delta"] == {"MARKET_ENTRY_NEXT_OPEN": True}
    assert side["universe_count"] == 2 and side["signal_window"] == list(spec.signal_window)
    assert side["summary"]["verdict"] == grc.REACHABLE and side["rows"] == census_rows


def _main(tmp_path, *knobs):
    return ma.main([*knobs, "--stage", "pilot", "--out", str(tmp_path / "arms.json"), "--workers", "1"])


@pytest.fixture
def fake_producer(monkeypatch):
    monkeypatch.setattr(ma, "cached_universe", lambda: ["AAA"])
    monkeypatch.setattr(ma, "produce", lambda stage, delta, **kw: {
        "provenance": {"changed_outcomes": 2, "engines": ["strategy"], "horizons": ["4w"]},
        "baseline": [], "component": []})
    monkeypatch.setattr(ma.training_data, "write_provenance", lambda out: None)
    monkeypatch.setattr(ma, "_resolve_replay_workers", lambda workers: 1)


def test_main_writes_the_gap_reclaim_sidecar_beside_the_arms(monkeypatch, tmp_path, fake_producer):
    monkeypatch.setattr(grc, "census", lambda *a, **k: [row(reclaimed=True, fill_price=100.01)])
    assert _main(tmp_path, "--knob", "MARKET_ENTRY_NEXT_OPEN=true", "--knob", "GAP_RECLAIM_ATR=0.25",
                 "--baseline-knob", "MARKET_ENTRY_NEXT_OPEN=true") == 0
    side = json.loads((tmp_path / "arms.gap_reclaim.json").read_text(encoding="utf-8"))
    assert side["summary"]["total"]["reclaimed"] == 1 and len(side["rows"]) == 1
    assert grc.load_sidecar(tmp_path / "arms.json") == side


def test_main_writes_no_gap_sidecar_for_the_next_open_basis_run(monkeypatch, tmp_path, fake_producer):
    monkeypatch.setattr(grc, "census", lambda *a, **k: pytest.fail("census ran"))
    assert _main(tmp_path, "--knob", "MARKET_ENTRY_NEXT_OPEN=true") == 0
    assert not (tmp_path / "arms.gap_reclaim.json").exists()


def test_a_census_failure_only_warns(monkeypatch, tmp_path, capsys, fake_producer):
    def boom(*a, **k):
        raise RuntimeError("frame store down")
    monkeypatch.setattr(grc, "census", boom)
    assert _main(tmp_path, "--knob", "MARKET_ENTRY_NEXT_OPEN=true", "--knob", "GAP_RECLAIM_ATR=0.25") == 0
    assert "gap_reclaim sidecar not written" in capsys.readouterr().err
    assert (tmp_path / "arms.json").exists() and not (tmp_path / "arms.gap_reclaim.json").exists()
```

Check the median in `test_reachability_summary_reports_the_gap_over_atr_distribution` by hand before running: the six non-None gaps sorted are `-0.2, 0.05, 0.12, 0.30, 0.60, 2.6`; `numpy.quantile(..., 0.5)` is the mean of the middle two, `(0.12 + 0.30) / 2 = 0.21`. At or above 0.10: `0.12, 0.30, 0.60, 2.6` (4); at or above 0.25: 3; at or above 0.5: 2.

- [ ] **Step 2: Run them to see them fail**

```bash
python scripts/dev/testrun.py file tests/backtesting/arms/test_gap_reclaim_census.py
```

Expected: FAIL at collection — `ModuleNotFoundError: No module named 'swingbot.core.backtesting.arms.gap_reclaim_census'`.

- [ ] **Step 3: Create `swingbot/core/backtesting/arms/gap_reclaim_census.py`**

```python
"""v192: the gap-reclaim census -- one row per next-open market decision the component replay makes.

The arm rows (ArmTrade) carry no fill price and no cancel reason, so the strata the v192 gate is
frozen on (removed / re-priced / added / unchanged; spec § Gate) cannot be read from them: a
reclaimed trade pairs on the same key as its baseline twin. This module replays the component
arm once more under ``market_next_open.observing`` and keeps every ``NextOpenDecision``, keyed
exactly as ``ArmTrade.key``. measure_arms writes the rows beside the stamped arms as
``<out stem>.gap_reclaim.json``; the stamped rows are never touched.

``observing`` is in-process, so each worker observes its own replay and returns plain dicts.
Descriptive input to the judges (V192-16..V192-18); it decides nothing by itself.
"""
from __future__ import annotations

import dataclasses
import json
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from swingbot.core.backtesting.arms.engine import run_arm
from swingbot.core.marketdata import training_data
from swingbot.core.planning import gap_reclaim, market_next_open

SIDECAR_SUFFIX = "gap_reclaim"
REACHABLE = "REACHABLE"
ZERO_DIFF = "refused:zero-diff"
KEY_FIELDS = ("ticker", "strategy", "horizon_key", "signal_date", "source", "direction")
#: The pre-registered g grid (spec § Definitions); the gap/ATR shares are reported against it.
GAP_GRID = (0.10, 0.25, 0.50)
GAP_ATR_QUANTILES = (0.10, 0.25, 0.50, 0.75, 0.90)

#: The daily-bar loader (the store measure_arms.load_frame reads); module-level so a test can swap it.
load_frame = training_data.load_daily


def row_key(row: dict) -> tuple:
    """The census row's pairing key, equal to ArmTrade.key of the trade the same plan produced
    (v1 writes the signal date as ArmTrade.entry_date)."""
    return tuple(row[field] for field in KEY_FIELDS)


def census_ticker(ticker, df, engines, horizons, signal_window, delta) -> list[dict]:
    """Every next-open market decision ``run_arm`` makes for one ticker under ``delta``, as dicts,
    limited to signal dates inside ``signal_window`` (the arm rows' own window rule)."""
    seen: list = []
    with market_next_open.observing(seen.append):
        run_arm(ticker, df, tuple(engines), tuple(horizons), tuple(signal_window), delta)
    start, end = signal_window
    return [dataclasses.asdict(item) for item in seen if start <= item.signal_date <= end]


def _census_task(task) -> tuple[str, list]:
    ticker, engines, horizons, signal_window, delta = task
    frame = load_frame(ticker)
    if frame is None:
        return ticker, []
    return ticker, census_ticker(ticker, frame, engines, horizons, signal_window, delta)


def _results(tasks, workers):
    if not workers or workers <= 1 or len(tasks) <= 1:
        yield from map(_census_task, tasks)
        return
    with ProcessPoolExecutor(max_workers=workers, initializer=training_data.select,
                             initargs=(training_data.active(),)) as pool:
        for future in as_completed([pool.submit(_census_task, task) for task in tasks]):
            yield future.result()


def census(universe, engines, horizons, signal_window, delta, *, workers=None) -> list[dict]:
    """The census over ``universe``: rows sorted by ticker, then replay order. ``workers`` > 1
    runs one task per ticker in a process pool; None or 1 runs in this process. A ticker with
    no frame contributes nothing (measure_arms has already failed the run on it)."""
    tasks = [(ticker, tuple(engines), tuple(horizons), tuple(signal_window), dict(delta))
             for ticker in universe]
    by_ticker: dict = {}
    for done, (ticker, rows) in enumerate(_results(tasks, workers), 1):
        by_ticker[ticker] = rows
        print(f"  [census] {done}/{len(tasks)} ({done * 100 // len(tasks)}%) {ticker}: "
              f"{len(rows)} decisions", flush=True)
    return [row for ticker in sorted(by_ticker) for row in by_ticker[ticker]]


def _count(rows, decision: str) -> int:
    return sum(1 for row in rows if row["decision"] == decision)


def _ratio(part: int, whole: int) -> float | None:
    return part / whole if whole else None


def _cell(rows) -> dict:
    armed = _count(rows, gap_reclaim.RECLAIM_WAIT)
    reclaimed = sum(1 for row in rows if row["reclaimed"])
    ambiguous = sum(1 for row in rows if row["ambiguous"])
    return {"market_plans": len(rows), "filled_at_open": _count(rows, gap_reclaim.FILL_OPEN),
            "armed": armed, "reclaimed": reclaimed, "ambiguous": ambiguous,
            "gap_no_reclaim": armed - reclaimed,
            "open_through_stop": _count(rows, gap_reclaim.OPEN_THROUGH_STOP),
            "risk_cap": _count(rows, gap_reclaim.RISK_CAP),
            "no_bar": _count(rows, market_next_open.NO_BAR),
            "reclaim_rate": _ratio(reclaimed, armed), "ambiguous_share": _ratio(ambiguous, reclaimed)}


def _gap_distribution(rows) -> dict:
    gaps = [row["gap_atr"] for row in rows if row["gap_atr"] is not None]
    if not gaps:
        return {"n": 0, "share_at_or_above": {}}
    quantiles = {f"q{round(q * 100):02d}": float(np.quantile(gaps, q)) for q in GAP_ATR_QUANTILES}
    shares = {str(g): sum(1 for gap in gaps if gap >= g) / len(gaps) for g in GAP_GRID}
    return {"n": len(gaps), **quantiles, "share_at_or_above": shares}


def reachability_summary(rows: list[dict]) -> dict:
    """Stage -1: per (horizon, direction) and in total, how many market plans the replay decided,
    how many armed the veto, reclaimed, were ambiguous, or cancelled at the open; the gap/ATR
    distribution (so a grid outside the real gap range shows as zero-diff, not a quiet no-op).
    No armed plan means the veto changed nothing: ``refused:zero-diff``."""
    by_cell = defaultdict(list)
    for row in rows:
        by_cell[(row["horizon_key"], row["direction"])].append(row)
    total = _cell(rows)
    return {"cells": [{"horizon_key": horizon, "direction": direction, **_cell(cell)}
                      for (horizon, direction), cell in sorted(by_cell.items())],
            "total": total, "gap_atr": _gap_distribution(rows),
            "verdict": REACHABLE if total["armed"] else ZERO_DIFF}


def repriced_keys(rows) -> set[tuple]:
    """Keys of the plans the veto filled on a same-session reclaim (the re-priced stratum)."""
    return {row_key(row) for row in rows if row["reclaimed"]}


def ambiguous_keys(rows) -> set[tuple]:
    """Keys of reclaim fills whose bar also reached the stop (booked -1R; the sensitivity set)."""
    return {row_key(row) for row in rows if row["ambiguous"]}


def sidecar_path(arms_path) -> Path:
    path = Path(arms_path)
    return path.with_name(f"{path.stem}.{SIDECAR_SUFFIX}.json")


def load_sidecar(arms_path) -> dict | None:
    """The census sidecar written beside ``arms_path``, or None when there is none."""
    path = sidecar_path(arms_path)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
```

- [ ] **Step 4: The sidecar builder in `scripts/backtest/measure_arms.py`**

Add after `turtle_soup_sidecar` (`:272`):

```python
GAP_RECLAIM_KNOB = "GAP_RECLAIM_ATR"


def gap_reclaim_sidecar(blob, delta, universe, spec) -> dict | None:
    """v192: every next-open market decision of the component arm (the census), replayed under
    the same delta. None unless the component sets GAP_RECLAIM_ATR > 0 (the next-open basis run
    has nothing to label). The stamped arm rows are never touched."""
    if not float(delta.get(GAP_RECLAIM_KNOB) or 0.0) > 0.0:
        return None
    from swingbot.core.backtesting.arms import gap_reclaim_census as grc
    stamp = blob.get("provenance") or {}
    rows = grc.census(universe, stamp.get("engines") or DEFAULT_ENGINES,
                      stamp.get("horizons") or windows.ALL_HORIZONS, tuple(spec.signal_window), delta,
                      workers=_resolve_replay_workers(None))
    component, _ = _component_and_spans(blob, spec)
    stamped = {grc.row_key(dict(row, signal_date=row["entry_date"])) for row in component}
    repriced = grc.repriced_keys(rows)
    return {"knob_delta": dict(delta), "baseline_knob_delta": stamp.get("baseline_knob_delta") or {},
            "signal_window": list(spec.signal_window), "universe_count": len(universe),
            "summary": grc.reachability_summary(rows),
            "repriced_in_component": len(repriced & stamped),
            "repriced_absent_from_component": len(repriced - stamped), "rows": rows}
```

Replace the `_SIDECARS` line (`:276`):

```python
#: (file suffix, builder name) per sidecar; looked up by name so a test can monkeypatch the builder.
#: "gap_reclaim" is gap_reclaim_census.SIDECAR_SUFFIX (pinned by test_gap_reclaim_census.py).
_SIDECARS = (("diagnostics", "compression_sidecar"), ("turtle_soup", "turtle_soup_sidecar"),
             ("gap_reclaim", "gap_reclaim_sidecar"))
```

Add one line to the module docstring after V192-14's line:

```
v192: --knob GAP_RECLAIM_ATR=g (> 0) also writes <out stem>.gap_reclaim.json, the census (see gap_reclaim_sidecar).
```

`repriced_absent_from_component` is a health count: a reclaimed plan whose walk booked `no_trade` has no arm row. Part 4 records it beside the strata; a large value means the census and the arm disagree and the run stops for review.

- [ ] **Step 5: Run the census tests, the neighbours and the gate**

```bash
python scripts/dev/testrun.py file tests/backtesting/arms/test_gap_reclaim_census.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_arms_turtle_sidecar.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_arms_baseline_delta.py
python scripts/dev/testrun.py file tests/backtesting/test_measure_compression_short.py
python scripts/dev/complexity_gate.py
```

Expected: `0 failed` each; the gate passes (`census` cc 3, `_results` cc 5, `gap_reclaim_sidecar` cc 4). If `test_the_veto_census_pairs_with_the_component_rows` finds no rows, the fixture has no market plan on the 4w horizon: widen its horizons to `("2w", "4w", "3m")` (the golden of V192-1 uses the same frame) rather than weaken the assertions.

- [ ] **Step 6: Commit (in the worktree)**

```bash
git add swingbot/core/backtesting/arms/gap_reclaim_census.py scripts/backtest/measure_arms.py tests/backtesting/arms/test_gap_reclaim_census.py
git commit -m "feat(v192): gap-reclaim census -- every next-open market decision keyed as ArmTrade.key, written as the measure_arms sidecar"
```

# Phase 9 — The frozen strata and the gate

### Task V192-16: Strata split, mechanism and volume clauses, SKIPPED-fails verdict

**Model:** opus — this is the pre-registered scoring the one VALIDATION shot is judged by; the strata, clause 6 and the SKIPPED rule are frozen by the spec and must not drift from it.

**Files:**
- Modify: `swingbot/core/backtesting/acceptance.py` (new `verdict_of` after `_clause_mechanism` `:607`; `evaluate` `:610-640` gains `skipped_fails`)
- Modify: `tests/backtesting/test_acceptance_gate.py` (append two tests)
- Create: `swingbot/core/backtesting/arms/gap_reclaim_clauses.py`
- Test: `tests/backtesting/arms/test_gap_reclaim_clauses.py` (create)

**Interfaces:**
- Consumes (all exist today): `ArmTrade` and `.key`, `win_rate`, `expectancy_r`, `DECIDED`, `ClauseResult`, `AcceptanceResult`, `evaluate(baseline, component, *, stage, permutation_p, n_resamples, seed, cluster, wr_statistic)`, `STAGES`, `VOLUME_MAX_CUT_PCT = 25.0`, `BOOTSTRAP_RESAMPLES` (`acceptance.py`); `cluster="week"` routes to `instrument.stats.week_cluster_bootstrap` (`acceptance.py:278-282`).
- Produces (index § Contracts):
  - `acceptance.verdict_of(clauses, *, skipped_fails: bool = False) -> str` — `"FAIL"` when any clause is `FAIL` (and, with `skipped_fails`, `SKIPPED`), else `"PASS"`.
  - `acceptance.evaluate(..., skipped_fails: bool = False)` — the default keeps every existing verdict byte for byte.
  - `gap_reclaim_clauses.CLUSTER = "week"`; `STRATA = ("removed", "repriced", "added", "unchanged")`.
  - `strata_split(baseline, component, repriced: set) -> dict` — `{"removed": [ArmTrade], "repriced": [(bt, ct)], "added": [ArmTrade], "unchanged": [(bt, ct)], "changed": [(bt, ct)], "is_subset": False}`; `changed` is the disclosure list of paired trades (re-priced or unchanged) whose outcome differs.
  - `mechanism_clause(split) -> ClauseResult` named `"mechanism"`; `volume_clause(baseline, split) -> ClauseResult` named `"volume"`.
  - `evaluate_gap_reclaim(baseline, component, repriced, *, stage, permutation_p=None, n_resamples=BOOTSTRAP_RESAMPLES, seed=42) -> AcceptanceResult` — `cluster="week"`, `split` holds the counts `removed, repriced, added, unchanged, changed, is_subset`.
  - `strata_rows(split) -> list[dict]` — one row per stratum: `stratum, n, decided, win_rate, expectancy_r, baseline_win_rate, baseline_expectancy_r` (the `baseline_*` pair only for the paired strata, else None).

**The frozen reading (spec § Gate, index § Global Constraints), restated so the code can be checked against it:**

| Stratum | Trades | Clause use |
|---|---|---|
| removed | baseline keys absent from the component (the `gap_no_reclaim` cancels) | clause 6 numerator; clause 4 cut = removed ÷ baseline N |
| re-priced | keys in the census's reclaimed set, present in both arms | reported (third row), decides nothing; inside geometry and clauses 1–2 as part of the component |
| added | component keys absent from the baseline (`StrategyEngine.open_until`) | reported; part of the component in clauses 1–3 |
| unchanged | every other paired key | clause 6 comparator: removed WR < unchanged WR and removed ExpR ≤ 0 |

Clauses 1 (ΔWR, standardised), 2 (ΔExpR lower bound > −0.01R) and 3 (geometry over the whole component, re-priced included) are `acceptance.evaluate`'s own, under `cluster="week"`. Clauses 4 and 6 are replaced by the strata versions: `acceptance._clause_volume` nets added trades against removed ones and `_clause_mechanism` returns `SKIPPED` for any non-subset pair. **A SKIPPED clause fails** (`skipped_fails=True`). The permutation clause is `SKIPPED` by design below VALIDATION (`acceptance._clause_permutation`), so at stage `walkforward` the verdict is scored without it; at `validation` it counts like every other clause.

- [ ] **Step 1: Write the failing acceptance tests** — append to `tests/backtesting/test_acceptance_gate.py`

```python
def test_verdict_of_ignores_skipped_by_default_and_fails_it_on_request():
    from swingbot.core.backtesting.acceptance import ClauseResult, verdict_of
    passed, skipped, failed = (ClauseResult("a", "PASS", ""), ClauseResult("b", "SKIPPED", ""),
                               ClauseResult("c", "FAIL", ""))
    assert verdict_of((passed, skipped)) == "PASS"
    assert verdict_of((passed, skipped), skipped_fails=True) == "FAIL"
    assert verdict_of((passed,), skipped_fails=True) == "PASS"
    assert verdict_of((passed, failed)) == "FAIL" == verdict_of((failed,), skipped_fails=True)
    assert verdict_of(()) == "PASS"


def test_evaluate_with_skipped_fails_fails_a_non_subset_feature():
    """The v192 opt-in: the same non-subset arms the default passes (mechanism SKIPPED) fail."""
    b, c = [], []
    for t in range(30):
        for i in range(10):
            b.append(mk(f"T{t}", "win" if i < 4 else "loss", date=f"2021-03-{i + 1:02d}"))
            c.append(mk(f"T{t}", "win" if i < 6 else "loss", date=f"2021-03-{i + 1:02d}"))
    default = evaluate(b, c, stage="walkforward", n_resamples=300, seed=42)
    strict = evaluate(b, c, stage="walkforward", n_resamples=300, seed=42, skipped_fails=True)
    assert default.verdict == "PASS" and strict.verdict == "FAIL"
    assert strict.clauses == default.clauses
```

- [ ] **Step 2: Write the failing clause tests** — create `tests/backtesting/arms/test_gap_reclaim_clauses.py`

```python
"""V192-16: the frozen v192 strata (removed / re-priced / added / unchanged), clause 6 scored
removed vs unchanged, clause 4 as removed / baseline N, and the SKIPPED-fails verdict."""
import datetime as dt

import pytest

from swingbot.core.backtesting import acceptance
from swingbot.core.backtesting.acceptance import ArmTrade
from swingbot.core.backtesting.arms import gap_reclaim_clauses as grc

FAST = dict(n_resamples=300, seed=42)


def mk(ticker, outcome, date, *, r=None, rr=2.0, strategy="RSI", horizon="4w", direction="bullish"):
    r = {"win": 2.0, "loss": -1.0}.get(outcome, 0.0) if r is None else r
    return ArmTrade(ticker, strategy, horizon, date, outcome, r, rr, "strategy", direction)


def _date(i: int, extra_days: int = 0) -> str:
    """One ISO week per index, so the week-cluster bootstrap has hundreds of clusters."""
    return (dt.date(2021, 1, 4) + dt.timedelta(days=7 * i + extra_days)).isoformat()


def veto_arms(n_tickers=30, removed=(8, 9), repriced_r=2.2, added=True):
    """Per ticker ten baseline trades, indices 0-3 wins (+2R) and 4-9 losses (-1R). The veto
    removes ``removed``, re-prices index 0 (same outcome, the larger R a fill at E gives) and the
    strategy engine adds one later win. Returns (baseline, component, repriced keys)."""
    baseline, component, repriced = [], [], set()
    for t in range(n_tickers):
        ticker = f"T{t:02d}"
        for i in range(10):
            trade = mk(ticker, "win" if i < 4 else "loss", _date(t * 10 + i))
            baseline.append(trade)
            if i in removed:
                continue
            if i == 0:
                repriced.add(trade.key)
                component.append(mk(ticker, "win", trade.entry_date, r=repriced_r))
            else:
                component.append(trade)
        if added:
            component.append(mk(ticker, "win", _date(t * 10 + 9, extra_days=1)))
    return baseline, component, repriced


# --- strata_split ------------------------------------------------------------------------------

def _small():
    a, b, c = mk("A", "win", "2021-01-04"), mk("B", "loss", "2021-01-11"), mk("C", "win", "2021-01-18")
    a2, d = mk("A", "win", "2021-01-04", r=2.3), mk("D", "win", "2021-01-25")
    ghost = mk("Z", "win", "2021-02-01")
    return [a, b, c], [a2, c, d], {a.key, ghost.key}, (a, b, c, a2, d)


def test_strata_split_labels_the_four_strata():
    baseline, component, repriced, (a, b, c, a2, d) = _small()
    split = grc.strata_split(baseline, component, repriced)
    assert split["removed"] == [b] and split["added"] == [d]
    assert split["repriced"] == [(a, a2)] and split["unchanged"] == [(c, c)]
    assert split["changed"] == [] and split["is_subset"] is False


def test_a_repriced_key_without_a_baseline_twin_is_ignored():
    baseline, component, repriced, _ = _small()
    split = grc.strata_split(baseline, component, repriced)
    assert sum(len(split[name]) for name in grc.STRATA) == 4      # the ghost key labels nothing


def test_outcome_flips_are_disclosed_from_both_paired_strata():
    baseline, component, repriced, (a, b, c, a2, d) = _small()
    a_lost, c_lost = mk("A", "loss", a.entry_date), mk("C", "loss", c.entry_date)
    split = grc.strata_split(baseline, [a_lost, c_lost, d], repriced)
    assert split["changed"] == [(a, a_lost), (c, c_lost)]


def test_strata_rows_report_each_stratum_with_its_baseline_twin():
    baseline, component, repriced, _ = _small()
    rows = {row["stratum"]: row for row in grc.strata_rows(grc.strata_split(baseline, component, repriced))}
    assert list(rows) == list(grc.STRATA) == ["removed", "repriced", "added", "unchanged"]
    assert (rows["removed"]["n"], rows["removed"]["win_rate"], rows["removed"]["expectancy_r"]) == (1, 0.0, -1.0)
    assert rows["removed"]["baseline_win_rate"] is None
    assert rows["repriced"]["expectancy_r"] == pytest.approx(2.3)
    assert rows["repriced"]["baseline_expectancy_r"] == pytest.approx(2.0)
    assert rows["added"]["decided"] == 1 and rows["unchanged"]["win_rate"] == 100.0


# --- clauses 4 and 6 ---------------------------------------------------------------------------

def test_mechanism_passes_when_the_veto_removes_losers():
    baseline, component, repriced = veto_arms()
    clause = grc.mechanism_clause(grc.strata_split(baseline, component, repriced))
    assert clause.name == "mechanism" and clause.verdict == "PASS"
    assert clause.value == 0.0 and clause.threshold == pytest.approx(300 / 7)   # 3 wins of 7 unchanged
    assert "unchanged" in clause.detail and "re-priced excluded" in clause.detail


def test_mechanism_fails_when_the_veto_removes_winners():
    baseline, component, repriced = veto_arms(removed=(2, 3))
    assert grc.mechanism_clause(grc.strata_split(baseline, component, repriced)).verdict == "FAIL"


def test_mechanism_fails_when_the_removed_population_is_empty():
    baseline, component, repriced = veto_arms(removed=())
    clause = grc.mechanism_clause(grc.strata_split(baseline, component, repriced))
    assert clause.verdict == "FAIL" and "no decided" in clause.detail


def test_volume_counts_removed_trades_only_added_ones_never_offset_them():
    baseline, component, repriced = veto_arms(removed=(7, 8, 9))
    clause = grc.volume_clause(baseline, grc.strata_split(baseline, component, repriced))
    assert clause.name == "volume" and clause.value == pytest.approx(30.0) and clause.verdict == "FAIL"
    netted = acceptance.evaluate(baseline, component, stage="walkforward", **FAST).clause("volume")
    assert netted.value == pytest.approx(20.0) and netted.verdict == "PASS"   # why the strata version exists


def test_volume_fails_an_empty_baseline():
    assert grc.volume_clause([], grc.strata_split([], [], set())).verdict == "FAIL"


# --- evaluate_gap_reclaim ----------------------------------------------------------------------

def test_a_loser_removing_veto_passes_validation_with_a_permutation_p():
    baseline, component, repriced = veto_arms()
    result = grc.evaluate_gap_reclaim(baseline, component, repriced, stage="validation",
                                      permutation_p=0.01, **FAST)
    assert result.verdict == "PASS", [(c.name, c.verdict, c.detail) for c in result.clauses]
    assert [c.name for c in result.clauses] == ["win_rate", "profit_floor", "geometry", "volume",
                                                "permutation", "mechanism"]
    assert result.cluster == grc.CLUSTER == "week"
    assert result.split == {"removed": 60, "repriced": 30, "added": 30, "unchanged": 210,
                            "changed": 0, "is_subset": False}


def test_the_stock_gate_would_have_skipped_clause_six_on_the_same_arms():
    baseline, component, _ = veto_arms()
    stock = acceptance.evaluate(baseline, component, stage="validation", permutation_p=0.01, **FAST)
    assert stock.clause("mechanism").verdict == "SKIPPED"


def test_validation_without_a_permutation_p_fails():
    baseline, component, repriced = veto_arms()
    result = grc.evaluate_gap_reclaim(baseline, component, repriced, stage="validation", **FAST)
    assert result.clause("permutation").verdict == "FAIL" and result.verdict == "FAIL"


def test_below_validation_the_by_design_permutation_skip_does_not_fail():
    baseline, component, repriced = veto_arms()
    result = grc.evaluate_gap_reclaim(baseline, component, repriced, stage="walkforward", **FAST)
    assert result.clause("permutation").verdict == "SKIPPED" and result.verdict == "PASS"


def test_any_other_skipped_clause_fails_the_gate(monkeypatch):
    baseline, component, repriced = veto_arms()
    skipped = acceptance.ClauseResult("geometry", "SKIPPED", "no planned RR or win R on either arm")
    monkeypatch.setattr(acceptance, "_clause_geometry", lambda b, c: skipped)
    result = grc.evaluate_gap_reclaim(baseline, component, repriced, stage="validation",
                                      permutation_p=0.01, **FAST)
    assert result.clause("geometry").verdict == "SKIPPED" and result.verdict == "FAIL"


def test_a_winner_removing_veto_fails_on_the_mechanism():
    baseline, component, repriced = veto_arms(removed=(2, 3))
    result = grc.evaluate_gap_reclaim(baseline, component, repriced, stage="validation",
                                      permutation_p=0.01, **FAST)
    assert result.clause("mechanism").verdict == "FAIL" and result.verdict == "FAIL"


def test_an_unknown_stage_is_refused():
    baseline, component, repriced = veto_arms(n_tickers=2)
    with pytest.raises(ValueError, match="stage must be one of"):
        grc.evaluate_gap_reclaim(baseline, component, repriced, stage="selection", **FAST)


def test_the_result_renders_through_the_stock_renderers():
    baseline, component, repriced = veto_arms()
    result = grc.evaluate_gap_reclaim(baseline, component, repriced, stage="validation",
                                      permutation_p=0.01, **FAST)
    payload = acceptance.render_json(result)
    assert payload["cluster"] == "week" and payload["split"]["repriced"] == 30
    assert "- removed: 60" in acceptance.render_markdown(result, title="v192", window="2024..2025")
```

Check the numbers by hand before running. Per ticker: removed 2 (indices 8, 9: losses), re-priced 1 (index 0), unchanged 7 (indices 1–7: 3 wins, 4 losses, WR 300/7 ≈ 42.86%), added 1. Over 30 tickers: removed 60, re-priced 30, unchanged 210, added 30. Baseline WR 40%, ExpR (8 − 6)/10 = 0.2R; component per ticker 9 trades, 5 wins (55.6%), ExpR (2.2 + 6 − 4 + 2)/9 ≈ 0.689R; mean win R 2.04 vs 2.0 (no drop); planned RR median 2.0 both. With `removed=(7, 8, 9)`: strata cut 90/300 = 30%; the stock netted cut is (300 − 240)/300 = 20%.

- [ ] **Step 3: Run them to see them fail**

```bash
python scripts/dev/testrun.py file tests/backtesting/test_acceptance_gate.py
python scripts/dev/testrun.py file tests/backtesting/arms/test_gap_reclaim_clauses.py
```

Expected: FAIL — `ImportError: cannot import name 'verdict_of'`, `evaluate() got an unexpected keyword argument 'skipped_fails'`, `ModuleNotFoundError: ... gap_reclaim_clauses`.

- [ ] **Step 4: `acceptance.py`** — add `verdict_of` after `_clause_mechanism` (`:607`) and give `evaluate` the opt-in

```python
def verdict_of(clauses, *, skipped_fails: bool = False) -> str:
    """The gate's verdict over ``clauses``: FAIL when any clause FAILs. v192: with
    ``skipped_fails`` a SKIPPED clause fails too (the spec's 'a SKIPPED clause counts as a fail'
    for a component whose every clause must be answerable); the default is today's rule."""
    blocking = ("FAIL", "SKIPPED") if skipped_fails else ("FAIL",)
    return "FAIL" if any(c.verdict in blocking for c in clauses) else "PASS"
```

In `evaluate`, add the keyword (last) and route the verdict through it:

```python
def evaluate(baseline, component, *, stage: str,
             permutation_p: float | None = None,
             n_resamples: int = BOOTSTRAP_RESAMPLES,
             seed: int = 42, cluster: str = "ticker",
             wr_statistic: str = "standardised",
             skipped_fails: bool = False) -> AcceptanceResult:
    """The gate. Every applicable clause must PASS.

    A SKIPPED clause never blocks a PASS, but it is always reported -- a
    skip is a fact about the measurement, not an absence of one. v192:
    ``skipped_fails=True`` makes it block (opt-in; every existing verdict
    is unchanged).
    """
```

and replace the line `verdict = "FAIL" if any(c.verdict == "FAIL" for c in clauses) else "PASS"` with:

```python
    verdict = verdict_of(clauses, skipped_fails=skipped_fails)
```

Nothing else in `evaluate` changes (cc unchanged: the `any` moved into `verdict_of`).

- [ ] **Step 5: Create `swingbot/core/backtesting/arms/gap_reclaim_clauses.py`**

```python
"""v192: the gap-reclaim veto's frozen scoring (spec § Gate).

The v192 arms are never a subset: a reclaimed trade fills at E in the component and at the open
in the baseline (same key, re-priced), and a cancelled baseline trade frees StrategyEngine's
``open_until`` for later signals (added). ``acceptance.population_split`` cannot tell re-priced
from unchanged, ``_clause_mechanism`` would return SKIPPED and ``_clause_volume`` nets added
trades against removed ones. The strata here are frozen before TRAIN:

- removed: baseline keys absent from the component (the gap_no_reclaim cancels);
- repriced: keys in the census's reclaimed set present in both arms (reported, decides nothing);
- added: component keys absent from the baseline;
- unchanged: every other paired key.

Clause 6 is removed vs unchanged; clause 4 is removed / baseline N; clauses 1-3 are acceptance's
own under the week-cluster bootstrap; a SKIPPED clause fails (the permutation clause is SKIPPED
by design below VALIDATION and is scored only there). Open-through-stop and risk-cap cancels are
absent from both arms (the engines drop not_triggered rows), so they are in no stratum.
"""
from __future__ import annotations

import dataclasses

from swingbot.core.backtesting import acceptance
from swingbot.core.backtesting.acceptance import (BOOTSTRAP_RESAMPLES, VOLUME_MAX_CUT_PCT,
                                                  AcceptanceResult, ClauseResult, expectancy_r,
                                                  win_rate)

CLUSTER = "week"
STRATA = ("removed", "repriced", "added", "unchanged")


def strata_split(baseline, component, repriced: set) -> dict:
    """Label every trade of both arms with its frozen stratum. ``repriced`` is the census's
    reclaimed key set; a key with no baseline twin labels nothing. ``changed`` discloses the
    paired trades (re-priced or unchanged) whose outcome differs."""
    b_by = {t.key: t for t in baseline}
    c_by = {t.key: t for t in component}
    pairs = [(bt, c_by[key]) for key, bt in b_by.items() if key in c_by]
    return {"removed": [t for key, t in b_by.items() if key not in c_by],
            "repriced": [pair for pair in pairs if pair[0].key in repriced],
            "added": [t for key, t in c_by.items() if key not in b_by],
            "unchanged": [pair for pair in pairs if pair[0].key not in repriced],
            "changed": [(bt, ct) for bt, ct in pairs if bt.outcome != ct.outcome],
            "is_subset": False}


def mechanism_clause(split: dict) -> ClauseResult:
    """v72 clause 6 on the v192 strata: are the trades the veto removed the bad ones? Removed WR
    must sit below the unchanged stratum's and removed ExpR at or below zero. Re-priced trades
    are excluded from the comparator (their R unit differs between the arms)."""
    removed, unchanged = split["removed"], [ct for _, ct in split["unchanged"]]
    r_wr, k_wr, r_exp = win_rate(removed), win_rate(unchanged), expectancy_r(removed)
    if r_wr is None or k_wr is None or r_exp is None:
        return ClauseResult("mechanism", "FAIL",
                            "removed or unchanged population has no decided trades to compare", None, None)
    ok = r_wr < k_wr and r_exp <= 0.0
    return ClauseResult(
        "mechanism", "PASS" if ok else "FAIL",
        f"removed WR {r_wr:.2f}% (n={len(removed)}) vs unchanged {k_wr:.2f}% (n={len(unchanged)}, "
        f"re-priced excluded), removed ExpR {r_exp:+.4f}R (must be <= 0)", r_wr, k_wr)


def volume_clause(baseline, split: dict) -> ClauseResult:
    """v72 clause 4 on the v192 strata: the alert cut is the removed trades over the baseline N;
    added trades never offset a removal."""
    if not baseline:
        return ClauseResult("volume", "FAIL", "empty baseline arm", None, VOLUME_MAX_CUT_PCT)
    cut = 100.0 * len(split["removed"]) / len(baseline)
    ok = cut <= VOLUME_MAX_CUT_PCT
    return ClauseResult("volume", "PASS" if ok else "FAIL",
                        f"removed {len(split['removed'])} of {len(baseline)} baseline trades: cut "
                        f"{cut:+.2f}% vs max {VOLUME_MAX_CUT_PCT:.1f}%", cut, VOLUME_MAX_CUT_PCT)


def _split_counts(split: dict) -> dict:
    return {**{name: len(split[name]) for name in STRATA}, "changed": len(split["changed"]),
            "is_subset": False}


def evaluate_gap_reclaim(baseline, component, repriced: set, *, stage: str, permutation_p=None,
                         n_resamples: int = BOOTSTRAP_RESAMPLES, seed: int = 42) -> AcceptanceResult:
    """The v192 gate: acceptance.evaluate's clauses 1-3 and 5 under ``cluster="week"``, clauses 4
    and 6 from the strata, and a SKIPPED clause fails. The permutation clause is SKIPPED by design
    below VALIDATION (``acceptance._clause_permutation``) and is scored only at VALIDATION."""
    base = acceptance.evaluate(baseline, component, stage=stage, permutation_p=permutation_p,
                               n_resamples=n_resamples, seed=seed, cluster=CLUSTER)
    split = strata_split(baseline, component, repriced)
    replaced = {"volume": volume_clause(baseline, split), "mechanism": mechanism_clause(split)}
    clauses = tuple(replaced.get(clause.name, clause) for clause in base.clauses)
    scored = clauses if stage == "validation" else tuple(c for c in clauses if c.name != "permutation")
    return dataclasses.replace(base, clauses=clauses, split=_split_counts(split),
                               verdict=acceptance.verdict_of(scored, skipped_fails=True))


def _row(name: str, trades, twins) -> dict:
    return {"stratum": name, "n": len(trades),
            "decided": sum(1 for t in trades if t.outcome in acceptance.DECIDED),
            "win_rate": win_rate(trades), "expectancy_r": expectancy_r(trades),
            "baseline_win_rate": None if twins is None else win_rate(twins),
            "baseline_expectancy_r": None if twins is None else expectancy_r(twins)}


def strata_rows(split: dict) -> list[dict]:
    """One reporting row per stratum, in STRATA order. Paired strata report the component
    version and, beside it, the baseline twins; removed rows are the baseline trades."""
    return [_row("removed", split["removed"], None),
            _row("repriced", [ct for _, ct in split["repriced"]], [bt for bt, _ in split["repriced"]]),
            _row("added", split["added"], None),
            _row("unchanged", [ct for _, ct in split["unchanged"]], [bt for bt, _ in split["unchanged"]])]
```

`acceptance.evaluate` raises `ValueError("stage must be one of ...")` for a stage outside `STAGES`, which `test_an_unknown_stage_is_refused` relies on; `dataclasses.replace` keeps `cluster="week"`, `seed`, `strata` and `wr_statistic` from the stock result.

- [ ] **Step 6: Run the tests, the neighbouring gate suites and the gate**

```bash
python scripts/dev/testrun.py file tests/backtesting/arms/test_gap_reclaim_clauses.py
python scripts/dev/testrun.py file tests/backtesting/test_acceptance_gate.py
python scripts/dev/testrun.py file tests/backtesting/test_acceptance_render.py
python scripts/dev/testrun.py file tests/backtesting/test_acceptance_cluster_unit.py
python scripts/dev/testrun.py file tests/backtesting/test_acceptance_v68_regression.py
python scripts/dev/complexity_gate.py
```

Expected: `0 failed` each; the gate passes (`evaluate` cc unchanged, `strata_split` cc 7, `mechanism_clause` cc 6, `evaluate_gap_reclaim` cc 3).

- [ ] **Step 7: Commit (in the worktree)**

```bash
git add swingbot/core/backtesting/acceptance.py tests/backtesting/test_acceptance_gate.py swingbot/core/backtesting/arms/gap_reclaim_clauses.py tests/backtesting/arms/test_gap_reclaim_clauses.py
git commit -m "feat(v192): frozen strata -- removed/re-priced/added/unchanged, clause 6 removed vs unchanged, volume on removals, SKIPPED fails"
```


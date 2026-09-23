# Standard Arm Producer — Part 2: Producer, funnel, proof

**Index:** `docs/superpowers/plans/2026-09-23-v100-arm-producer_0-index.md` — header block, Global Constraints, planning deviations and `## Parallelisation` live there and apply to every task below.
**Spec:** `docs/superpowers/specs/2026-09-23-v100-arm-producer.md`
**Bump:** none
**Edge:** none (integrity)

---

# Phase B — Producer and funnel

### Task V100-7: `measure_arms.py` producer CLI

**Files:**
- Create: `scripts/backtest/measure_arms.py`
- Test: `tests/scripts/test_measure_arms.py`

**Interfaces:**
- Consumes: everything in `arms/` (V100-1..6); `run_backtest_range._tickers_for_run`; `fetch_backtest_data.load_cached`; `backtest_scenarios._resolve_replay_workers`.
- Produces: `cached_universe() -> list[str]`; `load_frame(ticker)`; `static_refusal(delta) -> tuple[str, str] | None`; `produce(stage, delta, *, universe, spec=None, horizons=None, engines=DEFAULT_ENGINES, workers=None, progress_path=None, preregistration=None) -> dict`; `main(argv=None) -> int`. Output JSON: `{"provenance", "baseline", "component"}` (+ `"train_folds"` at selection); walkforward: `{"provenance", "folds": [{"test_year", "baseline", "component"}]}`.

- [ ] **Step 1: Write the failing test** — `tests/scripts/test_measure_arms.py`:

```python
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import measure_arms as ma  # noqa: E402

from swingbot import config  # noqa: E402
from swingbot.core.backtesting.arms.windows import StageSpec  # noqa: E402
from tests.backtesting.test_v74_fixture import load_v74_fixture  # noqa: E402

FIXTURE = load_v74_fixture()
# The v74 fixture spans 2024-2025; a test-only spec points the pilot there.
FIXTURE_PILOT = StageSpec("pilot", ("2024-01-01", "2025-12-31"), full_width=False)
FIXTURE_WF = StageSpec("walkforward", ("2024-01-01", "2025-12-31"), full_width=True,
                       folds=(("2024", "2024-01-01", "2024-12-31"),
                              ("2025", "2025-01-01", "2025-12-31")),
                       fold_key="folds", fold_label_key="test_year")


@pytest.fixture(autouse=True)
def fixture_frames(monkeypatch):
    monkeypatch.setattr(ma, "load_frame", lambda t: FIXTURE.get(t))


def test_static_refusal_happens_before_any_compute(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(ma, "run_arm", lambda *a, **k: pytest.fail("computed"))
    rc = ma.main(["--knob", "STALL_EXIT_ENABLED=true", "--stage", "pilot",
                  "--out", str(tmp_path / "x.json")])
    assert rc == 1
    assert "refused:unreachable:journal_dependent" in capsys.readouterr().err
    assert not (tmp_path / "x.json").exists()


def test_unclassified_knob_is_refused(capsys, tmp_path):
    rc = ma.main(["--knob", "LOG_LEVEL=DEBUG", "--stage", "pilot", "--out", str(tmp_path / "x.json")])
    assert rc == 1
    assert "refused:unreachable:unclassified" in capsys.readouterr().err


def test_validation_requires_a_preregistration(capsys, tmp_path):
    rc = ma.main(["--knob", "MIN_REWARD_PCT=4", "--stage", "validation",
                  "--out", str(tmp_path / "x.json")])
    assert rc == 1
    assert "--preregistration" in capsys.readouterr().err


def test_pilot_blob_is_stamped_keyed_and_paired():
    delta = {"MIN_REWARD_PCT": config.MIN_REWARD_PCT * 1.75 + 0.5}
    blob = ma.produce("pilot", delta, universe=["AAPL", "XOM"], spec=FIXTURE_PILOT,
                      horizons=("4w",), engines=("confluence",), workers=1)
    p = blob["provenance"]
    assert p["stage"] == "pilot" and p["universe_count"] == 2 and p["horizons"] == ["4w"]
    assert p["engine_hash"]["baseline"] == p["engine_hash"]["component"]
    assert p["changed_outcomes"] > 0
    assert blob["baseline"] and all("source" in r and "direction" in r for r in blob["baseline"])


def test_walkforward_blob_has_one_entry_per_fold():
    blob = ma.produce("walkforward", {}, universe=["AAPL"], spec=FIXTURE_WF,
                      horizons=("4w",), engines=("confluence",), workers=1)
    assert [f["test_year"] for f in blob["folds"]] == ["2024", "2025"]
    assert "baseline" not in blob
    for f in blob["folds"]:
        assert all(r["entry_date"].startswith(f["test_year"]) for r in f["baseline"])


def test_a_failing_ticker_fails_the_whole_run(monkeypatch):
    monkeypatch.setattr(ma, "load_frame", lambda t: None if t == "XOM" else FIXTURE[t])
    with pytest.raises(RuntimeError, match="XOM"):
        ma.produce("pilot", {}, universe=["AAPL", "XOM"], spec=FIXTURE_PILOT,
                   horizons=("4w",), engines=("confluence",), workers=1)


def test_progress_file_is_deleted_on_success(tmp_path):
    progress = tmp_path / "p.progress"
    ma.produce("pilot", {}, universe=["AAPL"], spec=FIXTURE_PILOT, horizons=("4w",),
               engines=("confluence",), workers=1, progress_path=progress)
    assert not progress.exists()
```

- [ ] **Step 2: Run — expect FAIL** (`ModuleNotFoundError: measure_arms`).

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_arms.py`

- [ ] **Step 3: Implement** `scripts/backtest/measure_arms.py`:

```python
#!/usr/bin/env python3
"""v100 standard arm producer -- the one instrument new pre-registrations use.

Runs baseline and component (a knob delta) through the replay engines over
the stage's signal window and width from arms/windows.py, pairs them by
key, and writes stamped arms JSON that validate_component.py accepts.

Refuses BEFORE compute when a knob is not reachable by the replay engines
(arms/reachability.py). A full-width run takes hours: dispatch it to the
backtest-runner subagent; progress is in logs/measure_arms.<run-id>.progress,
deleted on success.

Run:
  python scripts/backtest/measure_arms.py --knob MIN_STOP_DISTANCE_PCT=2.5 \\
      --stage pilot --out data/arms/min_stop_pilot.json
  python scripts/backtest/validate_component.py --stage reachability \\
      --arms data/arms/min_stop_pilot.json --title "..." --window pilot
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "data"))
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

from swingbot.core.backtesting.arms import reachability, windows  # noqa: E402
from swingbot.core.backtesting.arms.engine import DEFAULT_ENGINES, run_arm  # noqa: E402
from swingbot.core.backtesting.arms.knobs import parse_knob  # noqa: E402
from swingbot.core.backtesting.arms.pairing import changed_outcomes  # noqa: E402
from swingbot.core.backtesting.arms.provenance import build_stamp, code_hash  # noqa: E402
from swingbot.core.backtesting.backtest_scenarios import _resolve_replay_workers  # noqa: E402

LOG_DIR = ROOT / "logs"


def cached_universe() -> list[str]:
    from swingbot.core.marketdata.backtest_cache import cache_path
    from run_backtest_range import _tickers_for_run
    return sorted(t for t in _tickers_for_run(None) if cache_path(t).exists())


def load_frame(ticker):
    from fetch_backtest_data import load_cached
    return load_cached(ticker)


def static_refusal(delta: dict):
    for attr in delta:
        cls = reachability.classify(attr)
        if cls != reachability.REACHABLE:
            return f"refused:unreachable:{cls}", reachability.reason(attr)
    return None


def _worker(task):
    """Module-level so ProcessPoolExecutor can pickle it. Loads its own frame
    (shipping ~2MB frames across the process boundary costs more than a CSV
    read) and applies the knob delta inside this process."""
    ticker, engine_ids, horizons, signal_window, delta = task
    try:
        df = load_frame(ticker)
        if df is None:
            raise RuntimeError("no cached frame")
        trades = run_arm(ticker, df, engine_ids, horizons, signal_window, delta)
    except Exception as exc:
        raise RuntimeError(f"{ticker}: {exc!r}") from exc
    return ticker, trades


def _write_progress(path, done, total):
    if path is None:
        return
    try:
        Path(path).write_text(f"{done}/{total} ticker-arms ({done / total * 100:.0f}%)\n",
                              encoding="utf-8")
    except OSError:
        pass


def _run_arm_all(label, universe, engines, horizons, signal_window, delta, workers,
                 progress_path, counter, total):
    tasks = [(t, tuple(engines), tuple(horizons), signal_window, delta) for t in universe]
    by_ticker = {}

    def record(ticker, trades):
        by_ticker[ticker] = trades
        counter[0] += 1
        print(f"  [{label}] {counter[0]}/{total} {ticker}: {len(trades)} trades", flush=True)
        _write_progress(progress_path, counter[0], total)

    if workers <= 1 or len(tasks) <= 1:
        for task in tasks:
            record(*_worker(task))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for fut in as_completed([pool.submit(_worker, t) for t in tasks]):
                record(*fut.result())
    return [tr for t in sorted(by_ticker) for tr in by_ticker[t]]


def _rows(trades, start, end):
    return [dataclasses.asdict(t) for t in trades if start <= t.entry_date <= end]


def produce(stage, delta, *, universe, spec=None, horizons=None, engines=DEFAULT_ENGINES,
            workers=None, progress_path=None, preregistration=None) -> dict:
    spec = spec or windows.resolve(stage)
    horizons = tuple(horizons or windows.ALL_HORIZONS)
    workers = _resolve_replay_workers(workers)
    total, counter = 2 * len(universe), [0]
    hash_b = code_hash()
    baseline = _run_arm_all("baseline", universe, engines, horizons, spec.signal_window, {},
                            workers, progress_path, counter, total)
    hash_c = code_hash()
    component = _run_arm_all("component", universe, engines, horizons, spec.signal_window,
                             delta, workers, progress_path, counter, total)
    stamp = build_stamp(stage=stage, signal_window=spec.signal_window, universe=universe,
                        horizons=horizons, engines=engines, knob_delta=delta,
                        engine_hash_baseline=hash_b, engine_hash_component=hash_c,
                        changed_outcomes=changed_outcomes(baseline, component),
                        preregistration=preregistration)
    blob: dict = {"provenance": stamp}
    if spec.fold_key != "folds":
        start, end = spec.signal_window
        blob["baseline"], blob["component"] = _rows(baseline, start, end), _rows(component, start, end)
    if spec.folds:
        blob[spec.fold_key] = [
            {spec.fold_label_key: label, "baseline": _rows(baseline, s, e),
             "component": _rows(component, s, e)}
            for label, s, e in spec.folds]
    if progress_path is not None:
        Path(progress_path).unlink(missing_ok=True)
    return blob


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--knob", action="append", required=True, help="ATTR=value (repeatable)")
    ap.add_argument("--stage", required=True, choices=sorted(windows.STAGES))
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--preregistration", type=Path, default=None,
                    help="REQUIRED at --stage validation: the committed pre-registration doc")
    args = ap.parse_args(argv)

    try:
        delta = dict(parse_knob(k) for k in args.knob)
    except ValueError as exc:
        attr = next((k.partition("=")[0] for k in args.knob
                     if reachability.classify(k.partition("=")[0]) == reachability.UNCLASSIFIED), None)
        token = "refused:unreachable:unclassified" if attr else "refused:bad-knob"
        print(f"{token} -- {exc}", file=sys.stderr)
        return 1
    refusal = static_refusal(delta)
    if refusal:
        print(f"{refusal[0]} -- {refusal[1]} Budget intact.", file=sys.stderr)
        return 1
    if args.stage == "validation" and not (args.preregistration and args.preregistration.exists()):
        print("refused:no-preregistration -- --stage validation needs --preregistration "
              "<committed doc>. This is the one shot.", file=sys.stderr)
        return 1

    universe = windows.universe_for(args.stage, cached_universe())
    LOG_DIR.mkdir(exist_ok=True)
    progress = LOG_DIR / f"measure_arms.{uuid.uuid4().hex[:8]}.progress"
    print(f"stage={args.stage} tickers={len(universe)} knobs={delta} progress={progress}", flush=True)
    blob = produce(args.stage, delta, universe=universe, workers=args.workers,
                   progress_path=progress,
                   preregistration=str(args.preregistration) if args.preregistration else None)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(blob), encoding="utf-8")
    changed = blob["provenance"]["changed_outcomes"]
    print(f"[wrote {args.out}] changed outcomes: {changed}")
    if args.stage == "pilot" and changed == 0:
        print("refused:zero-diff -- the component changed no trade on the pilot slice. "
              "Budget intact.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Note `LOG_LEVEL` in the test: `parse_knob` succeeds for it (it is a config field), so `static_refusal` returns `refused:unreachable:unclassified` — the `except ValueError` branch handles names that are not config fields at all.

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/measure_arms.py tests/scripts/test_measure_arms.py
git commit -m "feat(v100): measure_arms producer CLI -- stamped, keyed, static-refusing"
```

---

### Task V100-8: Funnel guards in `validate_component.py`

**Files:**
- Modify: `scripts/backtest/validate_component.py`
- Modify: `tests/backtesting/test_validate_component_cli.py` (existing unstamped fixtures opt in to the bespoke override; MDE tests pin `--mde-method unpaired`)
- Test: `tests/backtesting/test_validate_component_stamps.py`

**Interfaces:**
- Consumes: `provenance.check_stamp`, `reachability.classify/reason/REACHABLE`, `pairing.changed_outcomes/overlap`, `acceptance.mde_paired`, `acceptance.delta_expectancy_r`, `acceptance_harvest.mde_expectancy_r`, `measure_arms.cached_universe`.
- Produces: new `--stage reachability`; flags `--bespoke-instrument REASON`, `--mde-method {paired,unpaired}` (default `paired`), `--gate {win_rate,harvest}` (default `win_rate`), `--train-effect-r`; `--observed-days` default becomes `None` (derived from the stamp's signal window, else 365); module-level `_full_universe()` (monkeypatchable).

- [ ] **Step 1: Write the failing test** — `tests/backtesting/test_validate_component_stamps.py`:

```python
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import validate_component as vc  # noqa: E402

from swingbot.core.backtesting.arms.provenance import build_stamp  # noqa: E402
from swingbot.core.backtesting.arms.windows import ALL_HORIZONS  # noqa: E402

UNIVERSE = [f"T{k}" for k in range(25)]


def rows(drop_from=8, flip=False):
    base, comp = [], []
    for k in range(25):
        for i in range(10):
            win = i < 4
            row = {"ticker": f"T{k}", "strategy": "MACD", "horizon_key": "3m",
                   "entry_date": f"2019-03-{i + 1:02d}", "outcome": "win" if win else "loss",
                   "r_multiple": 2.0 if win else -1.0, "planned_rr": 2.0,
                   "source": "strategy", "direction": "bullish"}
            base.append(row)
            if i < drop_from:
                comp.append(dict(row, outcome="win", r_multiple=2.0) if flip and i == 5 else row)
    return base, comp


def write(tmp_path, stage, knobs, base, comp, universe=UNIVERSE):
    window = ("2018-06-01", "2020-12-31") if stage == "pilot" else ("2018-06-01", "2022-12-31")
    stamp = build_stamp(stage=stage, signal_window=window, universe=universe,
                        horizons=ALL_HORIZONS, engines=("strategy",), knob_delta=knobs,
                        engine_hash_baseline="h", engine_hash_component="h",
                        changed_outcomes=0)
    p = tmp_path / "arms.json"
    p.write_text(json.dumps({"provenance": stamp, "baseline": base, "component": comp}))
    return p


@pytest.fixture(autouse=True)
def universe(monkeypatch):
    monkeypatch.setattr(vc, "_full_universe", lambda: UNIVERSE)


def test_reachability_passes_a_reachable_knob_that_changed_trades(tmp_path, capsys):
    arms = write(tmp_path, "pilot", {"MIN_REWARD_PCT": 4.0}, *rows())
    assert vc.main(["--stage", "reachability", "--arms", str(arms), "--title", "t",
                    "--window", "pilot"]) == 0
    assert "REACHABLE" in capsys.readouterr().out


def test_reachability_refuses_zero_diff(tmp_path, capsys):
    base, _ = rows()
    arms = write(tmp_path, "pilot", {"MIN_REWARD_PCT": 4.0}, base, list(base))
    assert vc.main(["--stage", "reachability", "--arms", str(arms), "--title", "t",
                    "--window", "pilot"]) == 1
    assert "refused:zero-diff" in capsys.readouterr().err


def test_reachability_refuses_an_unreachable_knob(tmp_path, capsys):
    arms = write(tmp_path, "pilot", {"RS_GATE": True}, *rows())
    assert vc.main(["--stage", "reachability", "--arms", str(arms), "--title", "t",
                    "--window", "pilot"]) == 1
    assert "refused:unreachable:live_scan_only" in capsys.readouterr().err


def test_unstamped_arms_are_refused(tmp_path, capsys):
    base, comp = rows()
    p = tmp_path / "a.json"
    p.write_text(json.dumps({"baseline": base, "component": comp}))
    assert vc.main(["--stage", "mde", "--arms", str(p), "--title", "t", "--window", "w",
                    "--train-effect-pp", "5"]) == 1
    assert "refused:unstamped" in capsys.readouterr().err


def test_bespoke_override_is_printed(tmp_path, capsys):
    base, comp = rows()
    p = tmp_path / "a.json"
    p.write_text(json.dumps({"baseline": base, "component": comp}))
    vc.main(["--stage", "mde", "--arms", str(p), "--title", "t", "--window", "w",
             "--train-effect-pp", "5", "--bespoke-instrument", "RS needs engine.py"])
    assert "BESPOKE INSTRUMENT: RS needs engine.py" in capsys.readouterr().out


def test_pilot_file_is_refused_at_mde(tmp_path, capsys):
    arms = write(tmp_path, "pilot", {"MIN_REWARD_PCT": 4.0}, *rows())
    assert vc.main(["--stage", "mde", "--arms", str(arms), "--title", "t", "--window", "w",
                    "--train-effect-pp", "5"]) == 1
    assert "refused:stage-mismatch" in capsys.readouterr().err


def test_narrow_selection_file_is_refused(tmp_path, capsys):
    arms = write(tmp_path, "selection", {"MIN_REWARD_PCT": 4.0}, *rows(), universe=UNIVERSE[:5])
    assert vc.main(["--stage", "mde", "--arms", str(arms), "--title", "t", "--window", "w",
                    "--train-effect-pp", "5"]) == 1
    assert "refused:narrow-universe" in capsys.readouterr().err


def test_mde_prints_paired_and_unpaired_and_gates_on_paired(tmp_path, capsys):
    arms = write(tmp_path, "selection", {"MIN_REWARD_PCT": 4.0}, *rows(flip=True))
    vc.main(["--stage", "mde", "--arms", str(arms), "--title", "t", "--window", "w",
             "--train-effect-pp", "5", "--target-days", "730"])
    out = capsys.readouterr().out
    assert "paired MDE" in out and "unpaired MDE" in out and "gating on: paired" in out


def test_harvest_gate_uses_expectancy(tmp_path, capsys):
    arms = write(tmp_path, "selection", {"MIN_REWARD_PCT": 4.0}, *rows(flip=True))
    vc.main(["--stage", "mde", "--arms", str(arms), "--title", "t", "--window", "w",
             "--gate", "harvest", "--train-effect-r", "0.05"])
    assert "dExpR" in capsys.readouterr().out
```

- [ ] **Step 2: Run — expect FAIL** (`argparse: invalid choice: 'reachability'`).

Run: `python scripts/dev/testrun.py file tests/backtesting/test_validate_component_stamps.py`

- [ ] **Step 3: Implement** in `scripts/backtest/validate_component.py`.

(a) Docstring: add under `Stages:` —

```
  reachability Stage -1 (v100). Reads a measure_arms.py PILOT file: refuses
               a knob the replay engines cannot reach, or a component that
               changed zero trades. Free; budget intact either way.
```

and replace "Arms come from a JSON file the component's own measurement script wrote." with "Arms come from scripts/backtest/measure_arms.py (stamped). Unstamped arms are refused unless --bespoke-instrument names why a bespoke instrument was needed; the reason is printed into the results doc."

(b) Imports — extend the `acceptance` import with `delta_expectancy_r, mde_paired`, and add:

```python
from swingbot.core.backtesting.acceptance_harvest import mde_expectancy_r  # noqa: E402
from swingbot.core.backtesting.arms import reachability  # noqa: E402
from swingbot.core.backtesting.arms.pairing import changed_outcomes, overlap  # noqa: E402
from swingbot.core.backtesting.arms.provenance import check_stamp  # noqa: E402
```

(c) Helpers, after `_folds_are_well_formed`:

```python
def _full_universe() -> list:
    sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
    from measure_arms import cached_universe
    return cached_universe()


def _stamp_gate(args) -> int | None:
    """v100: refuse arms the standard producer did not stamp, unless the
    run names why a bespoke instrument was needed."""
    if args.bespoke_instrument:
        print(f"BESPOKE INSTRUMENT: {args.bespoke_instrument}")
        return None
    blob = json.loads(Path(args.arms).read_text())
    token = check_stamp(blob, funnel_stage=args.stage, full_universe=_full_universe())
    if token:
        print(f"{token} -- see docs/claude/backtest-methodology.md (v100). Budget intact.",
              file=sys.stderr)
        return 1
    return None


def _stamp_observed_days(path) -> int | None:
    p = json.loads(Path(path).read_text()).get("provenance")
    if not p:
        return None
    import datetime as dt
    start, end = (dt.date.fromisoformat(d) for d in p["signal_window"])
    return (end - start).days + 1


def stage_reachability(args) -> int:
    blob = json.loads(Path(args.arms).read_text())
    delta = (blob.get("provenance") or {}).get("knob_delta") or {}
    for attr in delta:
        cls = reachability.classify(attr)
        if cls != reachability.REACHABLE:
            print(f"refused:unreachable:{cls} -- {reachability.reason(attr)} Budget intact.",
                  file=sys.stderr)
            return 1
    baseline, component = load_arms(args.arms)
    changed = changed_outcomes(baseline, component)
    print(f"knobs: {delta}  baseline N={len(baseline)}  component N={len(component)}  "
          f"changed outcomes: {changed}")
    if changed == 0:
        print("refused:zero-diff -- the component reached no trade. Budget intact.",
              file=sys.stderr)
        return 1
    print("\nREACHABLE -- the component changes trades; Stage 0 may proceed.")
    return 0
```

(d) Replace `stage_mde` with:

```python
def stage_mde(args) -> int:
    baseline, component = load_arms(args.arms)
    harvest = args.gate == "harvest"
    counted = ("win", "loss", "scratch", "timeout") if harvest else DECIDED
    observed = sum(1 for t in baseline if t.outcome in counted)
    observed_days = args.observed_days or _stamp_observed_days(args.arms) or 365
    target_n = project_target_n(observed_n=observed, observed_days=observed_days,
                                target_days=args.target_days)
    if harvest:
        unit, claimed = "R", args.train_effect_r
        unpaired = mde_expectancy_r(baseline, target_n=target_n)
        statistic = delta_expectancy_r
    else:
        unit, claimed = "pp", args.train_effect_pp
        unpaired = mde_win_rate(baseline, target_n=target_n)
        statistic = delta_standardised_win_rate
    paired = None
    if overlap(baseline, component) > 0:
        paired = mde_paired(baseline, component, statistic, observed_n=observed,
                            target_n=target_n, n_resamples=args.resamples, seed=args.seed)
    use_paired = args.mde_method == "paired" and paired is not None
    mde = paired if use_paired else unpaired
    label = "dExpR" if harvest else "dWR"
    print(f"observed N         : {observed} over {observed_days}d")
    print(f"projected target N : {target_n} over {args.target_days}d")
    print(f"paired MDE   ({label}): {'n/a' if paired is None else f'{paired:.4f}{unit}'}")
    print(f"unpaired MDE ({label}): {'n/a' if unpaired is None else f'{unpaired:.4f}{unit}'}")
    print(f"gating on: {'paired' if use_paired else 'unpaired'}")
    if mde is None:
        print("\nREFUSED -- no trades to estimate an MDE from.")
        return 1
    print(f"TRAIN effect claimed: {claimed:.4f}{unit}")
    if claimed < mde:
        print("\nREFUSED -- the TRAIN effect is below the minimum this sample can detect. "
              "The VALIDATION budget is NOT spent; record 'unresolvable, budget intact'.")
        return 1
    print("\nRESOLVABLE -- the shot may proceed.")
    return 0
```

(e) In `_run_gate` and `stage_walkforward`, prefix the results notes when bespoke: in `_run_gate` replace `notes=args.notes` (both the `render_markdown` call and nothing else) with `notes=_notes(args)`; in `stage_walkforward` insert `f"{_notes(args) or ''}"` as a line after the `Window:` line of `lines`. Add:

```python
def _notes(args) -> str | None:
    bespoke = getattr(args, "bespoke_instrument", None)
    if not bespoke:
        return args.notes
    prefix = f"BESPOKE INSTRUMENT (not measure_arms.py): {bespoke}."
    return f"{prefix} {args.notes}" if args.notes else prefix
```

(f) `main()`: make it accept `argv=None` and pass it to `ap.parse_args(argv)`; set `choices=("reachability", "mde", "walkforward", "validation")` on `--stage`; change `--observed-days` to `type=int, default=None`; add:

```python
    ap.add_argument("--bespoke-instrument", default=None, metavar="REASON",
                    help="accept unstamped arms; REASON is printed into the results doc")
    ap.add_argument("--mde-method", choices=("paired", "unpaired"), default="paired")
    ap.add_argument("--gate", choices=("win_rate", "harvest"), default="win_rate",
                    help="--stage mde: which Stage 0 statistic (harvest = dExpR)")
    ap.add_argument("--train-effect-r", type=float, default=0.0,
                    help="--stage mde --gate harvest: the dExpR the TRAIN grid claimed")
```

and, after parsing, before dispatch:

```python
    refused = _stamp_gate(args)
    if refused is not None:
        return refused
```

with `"reachability": stage_reachability` added to the dispatch table. Keep the existing `if __name__ == "__main__": sys.exit(main())` shape.

(g) `tests/backtesting/test_validate_component_cli.py`: change the `run` helper so pre-v100 unstamped fixtures opt in explicitly —

```python
def run(*args):
    # Pre-v100 fixtures are unstamped by construction; the stamp gate itself
    # is covered in test_validate_component_stamps.py.
    return subprocess.run([sys.executable, str(CLI), *args,
                           "--bespoke-instrument", "pre-v100 unstamped test fixture"],
                          capture_output=True, text=True)
```

and add `"--mde-method", "unpaired",` to both `test_mde_stage_*` invocations (their fixture has zero per-ticker variance, so a paired MDE is degenerate there — those two tests pin the unpaired path they were written for). In `test_validation_stage_writes_a_pending_skeleton_...`, add `"bespoke_instrument": None` to the fake `Args` dict.

- [ ] **Step 4: Run both files — expect PASS.**

```
python scripts/dev/testrun.py file tests/backtesting/test_validate_component_stamps.py
python scripts/dev/testrun.py file tests/backtesting/test_validate_component_cli.py
```

Then `git grep -ln "validate_component" tests` and run each remaining file (`test_armed_measurement.py`, `test_measure_strategy_arm.py`, `tests/scripts/test_measure_armed_entries.py`) — they only call `load_arms`/`load_folds`, expect PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/validate_component.py tests/backtesting/test_validate_component_stamps.py tests/backtesting/test_validate_component_cli.py
git commit -m "feat(v100): funnel Stage -1 reachability, stamp gate, paired Stage 0 MDE"
```

---

### Task V100-9: Observability test reads the registry

**Files:**
- Modify (rewrite): `tests/backtesting/test_knob_observability.py`

**Interfaces:**
- Consumes: `reachability.REGISTRY`, `engine.run_arm`, `load_v74_fixture`.

- [ ] **Step 1: Replace the file** with:

```python
"""Every searchable knob is classified in arms/reachability.py, and every
knob it calls fixture-observable really changes fixture OUTCOMES (v100:
outcomes, not selection-time plan fields, so exit knobs count)."""
import pytest

from swingbot import config
from swingbot.core.backtesting.arms import reachability as reach
from swingbot.core.backtesting.arms.engine import run_arm

from .test_v74_fixture import load_v74_fixture

PERTURB = {bool: lambda value: not value, int: lambda value: max(1, value + 1),
           float: lambda value: value * 1.75 + 0.5}
HORIZONS_UNDER_TEST = ("4w", "3m")
WINDOW = ("1900-01-01", "2100-12-31")
_BASELINES: dict = {}


def _run(engines, delta):
    rows = []
    for ticker, frame in load_v74_fixture().items():
        for t in run_arm(ticker, frame, engines, HORIZONS_UNDER_TEST, WINDOW, delta):
            r = None if t.r_multiple is None else round(t.r_multiple, 6)
            rows.append((t.key, t.outcome, r, t.planned_rr))
    return sorted(rows, key=repr)


def _baseline(engines):
    if engines not in _BASELINES:
        _BASELINES[engines] = _run(engines, {})
    return _BASELINES[engines]


def test_every_searchable_knob_is_classified():
    assert set(reach.REGISTRY) == set(config.searchable_attrs())


@pytest.mark.slow
@pytest.mark.parametrize("attr", sorted(a for a, r in reach.REGISTRY.items() if r.fixture_observable))
def test_knob_is_observable(attr):
    engines = tuple(sorted(reach.REGISTRY[attr].observed_by))
    current = getattr(config, attr)
    changed = _run(engines, {attr: PERTURB[type(current)](current)})
    assert changed != _baseline(engines), (
        f"{attr} is classified fixture_observable but changed nothing on the fixture; "
        "set fixture_observable=False in reachability.py and say why in its reason")
```

- [ ] **Step 2: Run** `python -m pytest tests/backtesting/test_knob_observability.py -v -m slow` (single file, slow marker — takes minutes).

- [ ] **Step 3: Reconcile honestly.** For each failing `attr`: set `fixture_observable=False` in `reachability.py` and extend its reason with `" Not observable on the two-ticker v74 fixture (verified <today's date>)."` — the knob stays `reachable`; the fixture is simply too small. Never change `PERTURB` or the fixture to force a pass. Record each flip for the results doc. Rerun until green, then run `python scripts/dev/testrun.py file tests/backtesting/arms/test_reachability.py`.

- [ ] **Step 4: Commit**

```bash
git add tests/backtesting/test_knob_observability.py swingbot/core/backtesting/arms/reachability.py
git commit -m "test(v100): knob observability reads the reachability registry, compares outcomes"
```

---

# Phase C — Documentation, proof, verification

### Task V100-10: Methodology docs + acceptance proof on real data

**Files:**
- Modify: `docs/claude/backtest-methodology.md`
- Modify: `.codex/AGENTS.md` (condensed, only if it describes the funnel — `grep -n "validate_component\|funnel\|Stage 0" .codex/AGENTS.md`)
- Modify: `.claude/skills/backtest-gate/SKILL.md` only if `grep -n "validate_component\|measure_" .claude/skills/backtest-gate/SKILL.md` shows it naming the stages or the bespoke-script pattern
- Create: `docs/superpowers/results/<YYYY-MM-DD>-v100-arm-producer-proof.md`

- [ ] **Step 1: Methodology doc.** In `docs/claude/backtest-methodology.md`, in the funnel table, add a first row:

```markdown
  | −1 `reachability` | pilot (2018-06..2020-12, 10 tickers) | free | knob not reachable by the replay engines, or zero changed outcomes ⇒ **refused, budget intact** |
```

and directly after the "Stage 2 being free and repeatable…" paragraph add:

```markdown
- **Standard arm producer (v100, `scripts/backtest/measure_arms.py`).** New
  pre-registrations produce arms with it, never with a new bespoke
  `measure_*.py`. It runs baseline and component (a `--knob ATTR=value`
  delta) through the confluence replay and a strategy engine built on
  `build_strategy_plan` — the live constructor, closing the
  `_trade_plan_at` gap that sank `DATA_DRIVEN_STOPS_ENABLED` and
  `STALL_EXIT_ENABLED` — pairs them by `ArmTrade.key`, and stamps the file.
  `validate_component.py` refuses unstamped arms (`refused:unstamped`)
  unless `--bespoke-instrument "<reason>"`, which the results doc prints;
  refuses Stages 0–3 below the full cached universe × all 10 horizons
  (`refused:narrow-universe`); and refuses stamps from the wrong stage, with
  mismatched engine code hashes, or touching 2024+ outside validation.
  `arms/reachability.py` classifies every searchable knob (`reachable` /
  `live_scan_only` / `journal_dependent` / `outside_replay`); a
  non-reachable knob is refused before compute. **Stage 0 gates on a paired
  MDE** (`acceptance.mde_paired`, ticker-cluster bootstrap SE of the delta)
  whenever the arms share keys — the unpaired formulas overstated the MDE for
  every subset and exit-only design. None of this reopens a closed row
  below: a better instrument is not a new hypothesis.
```

In the "Harvest acceptance gate (v92…)" bullet, replace the sentence beginning "A future harvest spec that relies on Stage 0…" with: "v100 added that paired variant: `acceptance.mde_paired(..., statistic=delta_expectancy_r)`, used by `validate_component.py --stage mde --gate harvest`."

- [ ] **Step 2: Codex mirror / skill.** If the greps above hit, add one condensed line each: "New pre-registrations produce arms with `scripts/backtest/measure_arms.py`; `validate_component.py` refuses unstamped arms unless `--bespoke-instrument`; Stage −1 `reachability` and a paired Stage 0 MDE precede the one shot." Do not copy the paragraph.

- [ ] **Step 3: Acceptance proof — dispatch to `backtest-runner`** (one run each; pilot and Stage −1/0 only; nothing spent):

```
python scripts/backtest/measure_arms.py --knob STALL_EXIT_ENABLED=true --stage pilot --out data/arms/v100_stall_pilot.json
python scripts/backtest/measure_arms.py --knob DATA_DRIVEN_STOPS_ENABLED=true --stage pilot --out data/arms/v100_dds_pilot.json
python scripts/backtest/measure_arms.py --knob MIN_STOP_DISTANCE_PCT=2.5 --stage pilot --out data/arms/v100_minstop_pilot.json
python scripts/backtest/validate_component.py --stage reachability --arms data/arms/v100_minstop_pilot.json --title "v100 proof" --window pilot
python scripts/backtest/validate_component.py --stage mde --arms data/arms/v100_minstop_pilot.json --title "v100 proof" --window pilot --train-effect-pp 1.0
python scripts/backtest/validate_component.py --stage mde --arms data/arms/v100_minstop_pilot.json --title "v100 proof" --window pilot --train-effect-pp 1.0 --bespoke-instrument "v100 instrument proof on the pilot slice -- not a hypothesis test"
```

  Expected: (1) and (2) exit 1 with `refused:unreachable:journal_dependent` and **no compute** (the guardrails hook denies commands naming a closed knob — `STALL_EXIT_ENABLED`, `DATA_DRIVEN_STOPS_ENABLED` are in `CLOSED_PREREGISTRATION_KNOBS`; if the hook blocks (1)/(2), record that the hook refused them first, which is the same outcome one layer earlier, and prove the producer's refusal with `python -m pytest tests/scripts/test_measure_arms.py::test_static_refusal_happens_before_any_compute -v` instead). (3) exits 0 with changed outcomes > 0. (4) `REACHABLE`. (5) `refused:stage-mismatch`. (6) prints paired and unpaired MDE side by side. Before running (3), confirm `MIN_STOP_DISTANCE_PCT` appears neither in `CLOSED_PREREGISTRATION_KNOBS` nor in the methodology closed table; if it does, pick another `reachable`, non-closed knob from `reachability.py` and say why in the results doc.

- [ ] **Step 4: Results doc** `docs/superpowers/results/<today>-v100-arm-producer-proof.md`: the six commands, their verbatim verdict lines, the pilot's baseline/component N and changed-outcome count, paired vs unpaired MDE, the seven planning deviations (header of this plan), every parity divergence from Task V100-5 Step 4, every `fixture_observable` flip from Task V100-9, and an explicit line: "Instrument proof only — no selection decision taken, no pre-registration opened or reopened, no VALIDATION shot spent."

- [ ] **Step 5: Delete the proof's arms files** (`data/arms/v100_*.json`, untracked) and confirm no `logs/measure_arms.*.progress` remains. Commit:

```bash
git add docs/claude/backtest-methodology.md docs/superpowers/results/ .codex/AGENTS.md .claude/skills/backtest-gate/SKILL.md
git commit -m "docs(v100): methodology for the standard arm producer; instrument proof results"
```

(`git add` of an unmodified path is a no-op; drop paths Step 2 did not touch if git complains.)

---

### Task V100-11: Full-suite verification and close-out

- [ ] **Step 1:** Dispatch the `test-runner` subagent: `python scripts/dev/testrun.py full`. Required verdict: `0 failed`, `0 xfailed`. A changed pass count is not a failure. On any failure: `superpowers:systematic-debugging`, fix, re-run **only the failing file** with `testrun.py file`, then one more full run.
- [ ] **Step 2:** `python -m py_compile scripts/backtest/measure_arms.py scripts/backtest/validate_component.py swingbot/core/backtesting/arms/*.py` — expect no output.
- [ ] **Step 3:** Close out per `docs/claude/document-lifecycle.md`: move this plan and its spec to `docs/superpowers/plans/implemented/` and `docs/superpowers/specs/implemented/` (check that doc for the exact spec destination), `Bump: none` so no `VERSION.json` change. Commit:

```bash
git add -A docs/superpowers/
git commit -m "docs(v100): close out plan and spec -- move to implemented/"
```

---

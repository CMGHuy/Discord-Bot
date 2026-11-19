# v238 — Replication ladder and additive gate: Part 3, additive funnel (V238-7..V238-8)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V238-8" -A 400 <this file>`).

**Spec:** [2026-11-16-v230-screen-v2-ladder-additive-gate-design.md](../specs/2026-11-16-v230-screen-v2-ladder-additive-gate-design.md) (`### Part C — the additive-strategy gate` "Stages" and "Costs are net on both arms", `## Testing` "Additive gate")
**Index:** [2026-11-19-v238-replication-ladder-additive-gate_0-index.md](2026-11-19-v238-replication-ladder-additive-gate_0-index.md) — Goal, `## Global Constraints`, `## Handoff` (rulings 2 and 6), `## Decisions this index fixes` (stage mapping for `--gate additive`, Stage 0 spread, `check_r_basis` under `--bespoke-instrument`) and `## Parallelisation` live there and bind every task below.

Funnel CLI, sequential (one file, `scripts/backtest/validate_component.py`). V238-7 needs V238-3 (`provenance.check_r_basis`, `R_BASIS_REFUSAL`) and V238-6 (`acceptance_additive.split_additive`, `mde_own_expectancy`, `stage0_refusal`); V238-8 needs V238-7 and V238-6/V238-6b (`evaluate_additive`, `AdditiveMisuse`, `disclosures`, `render_disclosures`). `acceptance_additive.py` and `arms/provenance.py` are imported, never edited here; `check_stamp` is not edited and behaves byte-identically for every gate.

Conventions both tasks share:

- **No ledger task may be split** (the plan is at the 20-task cap). Both tasks reference Part 2's contracts instead of restating them.
- `validate_component.main` is complexity 13 today. V238-7 moves the parser into `_build_parser()`, the five flag-conflict `if`s into the `_FLAG_CONFLICTS` table (messages verbatim) and the stage dict into `_STAGES` / `_ADDITIVE_STAGES`, so `main` drops to about 6 and the additive gate adds no branch to it.
- Stage tables map a stage to a **function name**, resolved through `globals()` at call time, so a test that monkeypatches `vc.stage_mde` (as `tests/backtest_scripts/test_validate_component_instrument.py:funnel` does) still takes effect, exactly as the old inline dict built inside `main` did.
- Every refusal prints one line on stderr that starts with its token and ends `Budget intact.`, and returns 1; a parser conflict exits 2 through `parser.error`.
- Test arms are written as JSON with `"provenance": {"r_basis": "net"}` and run with `--bespoke-instrument "test fixture"`, so `check_stamp` is skipped while `check_r_basis` still runs (index decision). Rows sit one per week so the week-cluster bootstrap has many clusters; tests pass `--resamples 300`.
- Tests go in `tests/backtesting/test_validate_component_additive*.py` (suite `backtesting-l-z`).

# Phase 3 — Additive funnel CLI

### Task V238-7: Funnel CLI: --gate additive dispatch, basis refusal, Stages −1 and 0

**Model:** opus — restructures a complexity-13 `main` with no behaviour change and wires a new gate's refusals into shared stage paths.

**Files:**
- Modify: `scripts/backtest/validate_component.py` (imports :14-21; new v238 block between `stage_selection` (ends :483) and `main`; `main` :486-516 rewritten around `_build_parser`)
- Test: `tests/backtesting/test_validate_component_additive.py` (create; suite `backtesting-l-z`)

**Interfaces:**
- Consumes: `provenance.check_r_basis`, `R_BASIS_REFUSAL` (V238-3); `acceptance_additive.split_additive`, `mde_own_expectancy` (`ValueError` on a bad `sd_r`), `stage0_refusal` (returns a whole line starting `refused:additive-mde`) (V238-4, V238-6); `arms.pairing.DuplicateKeyError` (exists, `pairing.py:9`); in-file `load_arms`, `_dump`, `_count`, `_wr_statistic`, `_gap_reclaim_conflict`, `_stamp_gate`, `CLOSED` (all exist).
- Produces (index ledger, final; V238-8 extends):
  - `--gate` choices `_GATES = ("win_rate", "harvest", "additive")`; flags `--expected-own-r`, `--expected-sd-r` (float, default `None`).
  - `_FLAG_CONFLICTS: tuple` of `check(args) -> str | None`; `_flag_conflict(args) -> str | None` (first message wins). v231 appends its `direction` entry here.
  - `_STAGES` / `_ADDITIVE_STAGES: dict[str, str]` (stage → function name); `_stage_runner(args)`. V238-8 replaces the three `_additive_pending` entries and deletes `_additive_pending`.
  - `_additive_basis_gate(args) -> int | None`; `_misuse_line(reason) -> int`; `_additive_arms(args) -> (baseline, component, split) | None`; `DISPLACEMENT_CAUSE`; `_print_displaced(split)`; `stage_additive_reachability(args)`; `stage_additive_mde(args)`.

Stage 0's N counts **closed** added rows (clause 1's population) from outcomes only; R is read only by the add-only check, never estimated. Missing or bad frozen inputs refuse with `refused:additive-mde-unfrozen`.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/test_validate_component_additive.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_validate_component_additive.py`
Expected: FAIL — `additive` is an invalid `--gate` choice; `vc._STAGES` does not exist.

- [ ] **Step 3: Extend the imports**

In `scripts/backtest/validate_component.py`, after line 15 (`acceptance_harvest` import) add:

```python
from swingbot.core.backtesting import acceptance_additive as additive  # noqa: E402
```

and change lines 20-21 to:

```python
from swingbot.core.backtesting.arms.pairing import DuplicateKeyError, changed_outcomes, overlap  # noqa: E402
from swingbot.core.backtesting.arms.provenance import check_r_basis, check_stamp  # noqa: E402
```

- [ ] **Step 4: Add the v238 block before `main`**

Insert between `stage_selection` and `main`:

```python
# --- v238: --gate additive (v230 spec Part C) ------------------------------------------

_GATES = ("win_rate", "harvest", "additive")
DISPLACEMENT_CAUSE = "not exposed by the replay"

#: stage -> function name, resolved at call time so a monkeypatched stage is honoured.
_STAGES = {"reachability": "stage_reachability", "mde": "stage_mde", "selection": "stage_selection",
           "walkforward": "stage_walkforward", "validation": "stage_validation"}
_ADDITIVE_STAGES = {"reachability": "stage_additive_reachability", "mde": "stage_additive_mde",
                    "selection": "_additive_pending", "walkforward": "_additive_pending",
                    "validation": "_additive_pending"}


def _stage_runner(args):
    """The stage callable for ``args.gate`` / ``args.stage``."""
    table = _ADDITIVE_STAGES if args.gate == "additive" else _STAGES
    return globals()[table[args.stage]]


def _additive_pending(args):
    print(f"refused:additive-stage-pending -- --gate additive --stage {args.stage} is not wired yet. "
          "Budget intact.", file=sys.stderr)
    return 1


def _when(predicate, message):
    return lambda args: message if predicate(args) else None


def _additive(args):
    return args.gate == "additive"


_MECHANISM_ADDITIVE = ("--dryup-mechanism and --headroom-mechanism score v72 clause 6; "
                       "the additive gate has no mechanism clause")

#: First message wins; the first five entries are main's pre-v238 checks, verbatim, in order.
_FLAG_CONFLICTS = (
    _when(lambda a: a.dryup_mechanism and a.headroom_mechanism,
          "--dryup-mechanism and --headroom-mechanism are different clause-6 readings; pass one"),
    _when(lambda a: a.mechanism_json and a.gate == "harvest",
          "--mechanism-json replaces v72 clause 6; the v92 harvest gate has no mechanism clause"),
    _when(lambda a: a.dryup_mechanism and a.gate == "harvest",
          "--dryup-mechanism scores v72 clause 6; the v92 harvest gate has no mechanism clause"),
    _when(lambda a: _wr_statistic(a) != "standardised" and a.gate == "harvest",
          "--wr-statistic selects the v72 win-rate clause-1 statistic; the v92 harvest gate has no win-rate clause"),
    _gap_reclaim_conflict,
    _when(lambda a: _additive(a) and a.gap_reclaim,
          "--gap-reclaim scores the v72 win-rate funnel; the additive gate is a different gate"),
    _when(lambda a: _additive(a) and a.mechanism_json,
          "--mechanism-json replaces v72 clause 6; the additive gate has no mechanism clause"),
    _when(lambda a: _additive(a) and (a.dryup_mechanism or a.headroom_mechanism), _MECHANISM_ADDITIVE),
    _when(lambda a: _additive(a) and _wr_statistic(a) != "standardised",
          "--wr-statistic selects the v72 win-rate clause-1 statistic; the additive gate judges win rate "
          "against its own break-even"),
    _when(lambda a: _additive(a) and a.train_effect_from_arms,
          "--train-effect-from-arms reads a v72/v92 TRAIN effect; the additive gate freezes --expected-own-r"),
    _when(lambda a: not _additive(a) and (a.expected_own_r is not None or a.expected_sd_r is not None),
          "--expected-own-r and --expected-sd-r freeze the additive gate's Stage 0; pass --gate additive"),
)


def _flag_conflict(args):
    for check in _FLAG_CONFLICTS:
        message = check(args)
        if message:
            return message
    return None


def _additive_basis_gate(args):
    """--gate additive only, under --bespoke-instrument too: both arms must be booked net."""
    if not _additive(args):
        return None
    token = check_r_basis(json.loads(Path(args.arms).read_text()))
    if token:
        print(f"{token} -- the additive gate needs arms booked net (provenance r_basis = net; "
              "measure_arms.py --r-basis net). Budget intact.", file=sys.stderr)
        return 1
    return None


def _misuse_line(reason):
    print(f"{reason} -- the additive gate takes a component that only adds rows; use --gate win_rate "
          "(v72) or harvest (v92). Budget intact.", file=sys.stderr)
    return 1


def _additive_arms(args):
    """(baseline, component, split) when the arms are add-only, else None after a refusal."""
    baseline, component = load_arms(args.arms)
    try:
        split = additive.split_additive(baseline, component)
    except DuplicateKeyError as error:
        print(f"refused:duplicate-key -- {error}. Budget intact.", file=sys.stderr)
        return None
    if split.misuse:
        _misuse_line(split.misuse)
        return None
    return baseline, component, split


def _print_displaced(split):
    for row in split.displaced:
        print(f"displaced: {row.ticker} {row.strategy} {row.horizon_key} {row.entry_date} "
              f"-- cause: {DISPLACEMENT_CAUSE}")


def stage_additive_reachability(args):
    """Stage -1 after the stamp and basis gates: the component must only add rows."""
    arms = _additive_arms(args)
    if arms is None:
        return 1
    baseline, component, split = arms
    print(f"additive split: baseline N={len(baseline)} component N={len(component)} "
          f"added={len(split.added)} displaced={len(split.displaced)}")
    _print_displaced(split)
    _dump(args.out_json, {"added": len(split.added), "displaced": len(split.displaced)})
    print("REACHABLE -- the component only adds rows; Stage 0 may proceed.")
    return 0


def _refuse_unfrozen(why):
    print(f"refused:additive-mde-unfrozen -- {why}. Budget intact.", file=sys.stderr)
    return 1


def stage_additive_mde(args):
    """Stage 0: the frozen own ExpR against the MDE at the closed added-row count (no R read)."""
    if args.expected_own_r is None or args.expected_sd_r is None:
        return _refuse_unfrozen("Stage 0 reads --expected-own-r and --expected-sd-r, both frozen "
                                "in the pre-registration")
    arms = _additive_arms(args)
    if arms is None:
        return 1
    n = _count(arms[2].added, CLOSED)
    try:
        mde = additive.mde_own_expectancy(n=n, sd_r=args.expected_sd_r)
    except ValueError as error:
        return _refuse_unfrozen(str(error))
    shown = "n/a" if mde is None else f"{mde:.4f}R"
    print(f"added N (closed)   : {n}\nfrozen own ExpR    : {args.expected_own_r:+.4f}R\n"
          f"frozen sd          : {args.expected_sd_r:.4f}R\nMDE                : {shown}")
    refusal = additive.stage0_refusal(n=n, expected_r=args.expected_own_r, sd_r=args.expected_sd_r)
    if refusal:
        print(refusal, file=sys.stderr)
        return 1
    print("RESOLVABLE -- the shot may proceed.")
    return 0
```

- [ ] **Step 5: Rewrite `main` around `_build_parser`**

Create `def _build_parser():` directly above `main` and **move** `main`'s lines 487-495 into it unchanged (from `parser = argparse.ArgumentParser(); ...` through `instrument_cli.add_instrument_arg(parser)`), with exactly two edits: in line 488 change `parser.add_argument("--gate", choices=("win_rate", "harvest"), default="win_rate")` to `parser.add_argument("--gate", choices=_GATES, default="win_rate")`, and insert these two lines just before `cache_dir_source.add_args(parser)`; end the function with `return parser`:

```python
    parser.add_argument("--expected-own-r", type=float, default=None, help="v238 additive Stage 0: frozen expected own net ExpR (half the selected ladder rung's net mean R)")
    parser.add_argument("--expected-sd-r", type=float, default=None, help="v238 additive Stage 0: frozen per-event net R standard deviation of that rung")
```

Then replace the rest of `main` (the old lines 486 and 496-516) with:

```python
def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    _instrument_gate(args)
    cache_dir_source.resolve(args)
    conflict = _flag_conflict(args)
    if conflict:
        parser.error(conflict)
    if args.stage == "selection":
        return _stage_runner(args)(args)
    if args.arms is None:
        parser.error("--arms is required for non-selection stages")
    refused = _stamp_gate(args)
    if refused is None:
        refused = _additive_basis_gate(args)
    if refused is not None:
        return refused
    return _stage_runner(args)(args)
```

- [ ] **Step 6: Run the new tests, the neighbours and the complexity gate**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_validate_component_additive.py`
Expected: every test passes, `0 failed`, `0 xfailed`.

Run `python scripts/dev/testrun.py file <f>` for each existing `tests/backtesting/test_validate_component_{cli,stamps,selection}.py` and `tests/backtest_scripts/test_validate_component_instrument.py`
Expected: all green, untouched (`main`'s behaviour does not move).

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0; `main` is now below 13.

- [ ] **Step 7: Commit**

```bash
git add scripts/backtest/validate_component.py tests/backtesting/test_validate_component_additive.py
git commit -m "feat(backtest): v238 validate_component --gate additive -- basis refusal, add-only split, Stage 0"
```

### Task V238-8: Funnel CLI: additive Stages 1–3 and reports

**Model:** opus — grid adoption, fold pooling and results-doc rendering for a new gate on a shared CLI, with the old selection refusals kept verbatim.

**Files:**
- Modify: `scripts/backtest/validate_component.py` (`backtest_wf` import :22; `stage_selection` :457-465 grid refusals moved into `_grid_or_refuse`; the v238 block from V238-7; `_build_parser`)
- Test: `tests/backtesting/test_validate_component_additive_stages.py` (create; suite `backtesting-l-z`)

**Interfaces:**
- Consumes: `acceptance_additive.evaluate_additive`, `AdditiveMisuse` (`.reason`), `CLAUSES`, `ADDITIVE_VERSION`, `split_additive` (V238-4..6); `disclosures(added, baseline) -> dict`, `render_disclosures(d) -> list[str]` (V238-6b); `provenance.check_r_basis` (V238-3); from V238-7 `_GATES`, `_ADDITIVE_STAGES`, `_FLAG_CONFLICTS`, `_when`, `_additive`, `_misuse_line`, `DISPLACEMENT_CAUSE`, `_build_parser`; existing `backtest_wf.plateau_report(param_name, grid, expectancies, adopted_value) -> dict`, `_parse_grid`, `_selection_input(path, full_universe)`, `_full_universe`, `load_arms`, `load_folds`, `_dump`, `_notes`, `render_markdown`, `render_json`, `DuplicateKeyError`.
- Produces (index ledger, final): `stage_additive_selection(args)`, `stage_additive_walkforward(args)`, `stage_additive_validation(args)` (replacing the three `_additive_pending` entries; `_additive_pending` is deleted); flags `--knob` (str, the plateau axis name, default `None` → `value`) and `--folds-arms` (Path, the Stage 2 arms file read by Stage 3); `_write_additive(args, result, extra) -> None` (prints the Markdown; writes `--out-md` and `--out-json`, the JSON being `render_json(result)` plus `"gate": "additive"` and `extra`).

Stage mapping (index `## Decisions this index fixes`): `selection` runs clauses 1–3 per `--grid-arms` cell, each cell through the existing selection stamp gate (`_selection_input`) and `check_r_basis`; the adopted cell is the highest own net ExpR among cells whose verdict is PASS, first in grid order on a tie; with two or more cells and an adopted one, `plateau_report` is printed and stored. `walkforward` runs clause 4 on the `--arms` file's `folds`, the clause's split taken over the folds' pooled rows. `validation` runs all four on `--arms`, clause 4 from `--folds-arms` (stamp-gated as `walkforward` unless `--bespoke-instrument`, always basis-gated). `render_markdown` reads the v72 split keys, so the report renders an add-only view (`removed` = displaced, `changed` = 0); the notes say so.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/test_validate_component_additive_stages.py`:

```python
"""v238 V238-8: validate_component --gate additive Stages 1-3 and the report."""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "scripts" / "backtest") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import validate_component as vc  # noqa: E402
from swingbot.core.backtesting import acceptance_additive as aa  # noqa: E402


def _row(ticker, day, r, *, year, strategy="MACD"):
    entry = date(year, 1, 4) + timedelta(days=day)
    return {"ticker": ticker, "strategy": strategy, "horizon_key": "3m",
            "entry_date": entry.isoformat(), "outcome": "win" if r > 0 else "loss",
            "r_multiple": r, "planned_rr": 2.0, "source": "strategy", "direction": "bullish"}


def _arms(*, n=60, win_r=2.0, good=True, year=2021, drop=0):
    """Added rows one per week; good = 2 wins in 3 (ExpR > 0), else 1 in 3 at 2R (ExpR 0)."""
    baseline = [_row(f"B{i % 6}", 7 * i, 2.0 if i % 2 == 0 else -1.0, year=year) for i in range(20)]
    wins = (lambda i: i % 3 != 0) if good else (lambda i: i % 3 == 0)
    added = [_row(f"A{i % 6}", 7 * i + 1, win_r if wins(i) else -1.0, year=year,
                  strategy="Turtle Soup") for i in range(n)]
    return baseline, baseline[drop:] + added


def _write(path, blob, basis="net"):
    path.write_text(json.dumps({**blob, "provenance": {"r_basis": basis}}), encoding="utf-8")
    return path


def _pair(tmp_path, name, arms, basis="net"):
    baseline, component = arms
    return _write(tmp_path / name, {"baseline": baseline, "component": component}, basis)


def _folds(tmp_path, good=(True, True, True), basis="net"):
    folds = []
    for year, ok in zip((2021, 2022, 2023), good):
        baseline, component = _arms(n=40, good=ok, year=year)
        folds.append({"test_year": year, "baseline": baseline, "component": component})
    return _write(tmp_path / "folds.json", {"folds": folds}, basis)


def _run(stage, *extra):
    return vc.main(["--gate", "additive", "--stage", stage, "--title", "t", "--window", "w",
                    "--resamples", "300", *extra])


@pytest.fixture(autouse=True)
def no_data(monkeypatch):
    monkeypatch.setattr(vc.cache_dir_source, "resolve", lambda args: None)
    monkeypatch.setattr(vc, "check_stamp", lambda *a, **k: None)
    monkeypatch.setattr(vc, "_selection_stamp_shape", lambda blob: None)
    monkeypatch.setattr(vc, "_full_universe", lambda: [])


def test_selection_one_cell_runs_clauses_1_to_3_week_clustered(tmp_path, capsys):
    cell = _pair(tmp_path, "c.json", _arms())
    out_json = tmp_path / "s.json"
    assert _run("selection", "--grid-arms", f"0.5={cell}", "--out-json", str(out_json)) == 0
    assert "adopted=0.5" in capsys.readouterr().out
    blob = json.loads(out_json.read_text(encoding="utf-8"))
    assert [c["name"] for c in blob["clauses"]] == list(aa.CLAUSES[:3])
    assert blob["gate"] == "additive" and blob["cluster"] == "week" and blob["plateau"] is None
    assert set(blob["disclosures"]) >= {"max_drawdown_r", "same_week_corr"}


def test_selection_adopts_the_highest_own_expr_and_prints_the_plateau(tmp_path, capsys):
    grid = [f"1.0={_pair(tmp_path, 'a.json', _arms())}",
            f"2.0={_pair(tmp_path, 'b.json', _arms(win_r=3.0))}",
            f"3.0={_pair(tmp_path, 'c.json', _arms(good=False))}"]
    argv = [item for cell in grid for item in ("--grid-arms", cell)]
    assert _run("selection", *argv, "--knob", "lookback") == 0
    out = capsys.readouterr().out
    assert "adopted=2.0" in out and 'plateau: {"param": "lookback"' in out


def test_selection_breaks_a_tie_by_grid_order(tmp_path, capsys):
    a, b = _pair(tmp_path, "a.json", _arms()), _pair(tmp_path, "b.json", _arms())
    assert _run("selection", "--grid-arms", f"1.0={a}", "--grid-arms", f"2.0={b}") == 0
    assert "adopted=1.0" in capsys.readouterr().out


def test_selection_with_no_passing_cell_fails(tmp_path, capsys):
    cell = _pair(tmp_path, "c.json", _arms(good=False))
    assert _run("selection", "--grid-arms", f"1.0={cell}") == 1
    assert "verdict=FAIL adopted=None" in capsys.readouterr().out


def test_selection_refuses_a_gross_cell(tmp_path, capsys):
    cell = _pair(tmp_path, "c.json", _arms(), basis="gross")
    assert _run("selection", "--grid-arms", f"1.0={cell}") == 1
    assert capsys.readouterr().err.startswith("refused:r-basis -- ")


def test_selection_refuses_a_misuse_cell(tmp_path, capsys):
    baseline, _ = _arms()
    cell = _pair(tmp_path, "c.json", (baseline, baseline))
    assert _run("selection", "--grid-arms", f"1.0={cell}") == 1
    assert capsys.readouterr().err.startswith("ADDITIVE_GATE_MISUSE")


def test_selection_keeps_the_old_grid_refusals(capsys):
    assert _run("selection") == 1
    assert capsys.readouterr().err.startswith("refused:no-grid -- --grid-arms is required.")


@pytest.mark.parametrize("good, code", [((True, True, True), 0), ((True, False, False), 1)])
def test_walkforward_runs_clause_4_on_the_folds(tmp_path, good, code):
    out_json = tmp_path / "w.json"
    assert _run("walkforward", "--arms", str(_folds(tmp_path, good)),
                "--bespoke-instrument", "x", "--out-json", str(out_json)) == code
    assert [c["name"] for c in json.loads(out_json.read_text())["clauses"]] == ["stability"]


def test_validation_needs_net_folds_arms(tmp_path, capsys):
    arms = _pair(tmp_path, "v.json", _arms())
    base = ["--arms", str(arms), "--bespoke-instrument", "x"]
    assert _run("validation", *base) == 1
    assert capsys.readouterr().err.startswith("refused:no-folds-arms -- ")
    assert _run("validation", *base, "--folds-arms", str(_folds(tmp_path, basis="gross"))) == 1
    assert capsys.readouterr().err.startswith("refused:r-basis -- ")


def test_validation_runs_all_four_and_writes_the_report(tmp_path, capsys):
    out_md, out_json = tmp_path / "v.md", tmp_path / "v.json"
    assert _run("validation", "--arms", str(_pair(tmp_path, "v.json", _arms(drop=1))),
                "--folds-arms", str(_folds(tmp_path)), "--bespoke-instrument", "x",
                "--out-md", str(out_md), "--out-json", str(out_json)) == 0
    blob = json.loads(out_json.read_text(encoding="utf-8"))
    assert [c["name"] for c in blob["clauses"]] == list(aa.CLAUSES)
    assert blob["split"] == {"added": 60, "displaced": 1} and len(blob["displaced"]) == 1
    md = out_md.read_text(encoding="utf-8")
    assert "never gating" in md and "## Displaced rows" in md
    assert f"cause: {vc.DISPLACEMENT_CAUSE}" in md and "- removed: 1" in md


def test_the_additive_only_flags_need_the_additive_gate(capsys):
    with pytest.raises(SystemExit):
        vc.main(["--stage", "mde", "--arms", "a.json", "--title", "t", "--window", "w",
                 "--knob", "lookback"])
    assert "--knob and --folds-arms belong to the additive gate" in capsys.readouterr().err


def test_every_additive_stage_is_wired():
    assert not hasattr(vc, "_additive_pending")
    assert all(callable(getattr(vc, name)) for name in vc._ADDITIVE_STAGES.values())
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_validate_component_additive_stages.py`
Expected: FAIL — `--knob` is unrecognised (exit 2) and the selection/walkforward/validation stages print `refused:additive-stage-pending`.

- [ ] **Step 3: Imports, flags, conflict entry, stage table**

Line 22 becomes:

```python
from swingbot.core.backtesting.backtest_wf import gate as gate_expectancy, gate_expectancy_harvest, gate_win_rate, plateau_report, win_rate_fold_row  # noqa: E402
```

In `_build_parser`, after the `--expected-sd-r` line:

```python
    parser.add_argument("--knob", default=None, help="v238 additive Stage 1: the grid axis name printed in the plateau report")
    parser.add_argument("--folds-arms", type=Path, default=None, help="v238 additive Stage 3: the Stage 2 arms file clause 4 reads")
```

Append to `_FLAG_CONFLICTS` (after the `--expected-own-r` entry):

```python
    _when(lambda a: not _additive(a) and (a.knob is not None or a.folds_arms is not None),
          "--knob and --folds-arms belong to the additive gate; pass --gate additive"),
```

In `_ADDITIVE_STAGES`, replace the three `"_additive_pending"` values with `"stage_additive_selection"`, `"stage_additive_walkforward"`, `"stage_additive_validation"`, and delete the `_additive_pending` function.

- [ ] **Step 4: Share the grid refusals with `stage_selection`**

Add above `stage_selection`, and replace its first eight lines (:458-465, the `try: grid = ...` through the `refused:no-grid` return) with `grid = _grid_or_refuse(args)` / `if grid is None: return 1`:

```python
def _grid_or_refuse(args):
    """The parsed --grid-arms cells, or None after the refusal line (messages unchanged)."""
    try:
        grid = _parse_grid(args.grid_arms)
    except ValueError as error:
        print(f"refused:malformed-grid -- {error}. Budget intact.", file=sys.stderr)
        return None
    if not grid:
        print("refused:no-grid -- --grid-arms is required. Budget intact.", file=sys.stderr)
        return None
    return grid
```

- [ ] **Step 5: Add Stages 1–3 and the report to the v238 block**

Append after `stage_additive_mde`:

```python
@dataclasses.dataclass(frozen=True)
class _AdditiveCell:
    value: float
    result: AcceptanceResult
    extra: dict

    @property
    def own_r(self):
        return self.result.clause(additive.CLAUSES[0]).value


def _additive_extra(baseline, split):
    return {"disclosures": additive.disclosures(split.added, baseline),
            "displaced": [{"key": list(row.key), "cause": DISPLACEMENT_CAUSE} for row in split.displaced],
            "unchanged": len(baseline) - len(split.displaced)}


def _additive_result(args, baseline, component, stage, folds=None):
    """(result, extra), or None after the misuse or duplicate-key refusal."""
    try:
        result = additive.evaluate_additive(baseline, component, stage=stage, folds=folds,
                                            n_resamples=args.resamples, seed=args.seed)
    except additive.AdditiveMisuse as misuse:
        _misuse_line(misuse.reason)
        return None
    except DuplicateKeyError as error:
        print(f"refused:duplicate-key -- {error}. Budget intact.", file=sys.stderr)
        return None
    return result, _additive_extra(baseline, additive.split_additive(baseline, component))


def _additive_markdown(args, result, extra):
    shown = dataclasses.replace(result, split={
        "removed": result.split["displaced"], "changed": 0, "unchanged": extra["unchanged"],
        "added": result.split["added"], "is_subset": False})
    notes = (f"Gate: additive (`acceptance_additive.py` v{additive.ADDITIVE_VERSION}); "
             "removed = displaced baseline rows, changed = 0 by the add-only rule.")
    if _notes(args):
        notes = f"{notes} {_notes(args)}"
    lines = [render_markdown(shown, title=args.title, window=args.window, notes=notes),
             *additive.render_disclosures(extra["disclosures"]), "", "## Displaced rows", ""]
    rows = [f"- {' '.join(str(part) for part in row['key'])} -- cause: {row['cause']}"
            for row in extra["displaced"]]
    return "\n".join(lines + (rows or ["- none"])) + "\n"


def _write_additive(args, result, extra):
    markdown = _additive_markdown(args, result, extra)
    print(markdown)
    if args.out_md:
        Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_md).write_text(markdown, encoding="utf-8")
    _dump(args.out_json, {**render_json(result), "gate": "additive", **extra})


def _finish_additive(args, baseline, component, stage, folds=None):
    found = _additive_result(args, baseline, component, stage, folds)
    if found is None:
        return 1
    _write_additive(args, *found)
    return 0 if found[0].verdict == "PASS" else 1


def _basis_refused(path, what):
    token = check_r_basis(json.loads(Path(path).read_text()))
    if token:
        print(f"{token} -- {what} must be booked net (provenance r_basis = net). Budget intact.",
              file=sys.stderr)
    return token is not None


def _additive_cell(args, value, path, full_universe):
    arms = _selection_input(path, full_universe)
    if arms is None or _basis_refused(path, f"selection cell {value}"):
        return None
    found = _additive_result(args, *arms, "selection")
    return None if found is None else _AdditiveCell(value, *found)


def _additive_cells(args, grid):
    full_universe = _full_universe()
    cells = []
    for value, path in grid:
        cell = _additive_cell(args, value, path, full_universe)
        if cell is None:
            return None
        cells.append(cell)
    return cells


def _adopt(cells):
    """Highest own net ExpR among cells passing clauses 1-3; first in grid order on a tie."""
    eligible = [cell for cell in cells if cell.result.verdict == "PASS"]
    if not eligible:
        return None
    best = max(cell.own_r for cell in eligible)
    return next(cell for cell in eligible if cell.own_r >= best - 1e-12)


def _plateau(args, cells, adopted):
    if len(cells) < 2 or adopted is None:
        return None
    expectancies = [float("nan") if cell.own_r is None else cell.own_r for cell in cells]
    report = plateau_report(args.knob or "value", [cell.value for cell in cells], expectancies,
                            adopted.value)
    print(f"plateau: {json.dumps(report)}")
    return report


def stage_additive_selection(args):
    """Stage 1: clauses 1-3 per --grid-arms cell, then adoption and the plateau report."""
    grid = _grid_or_refuse(args)
    cells = None if grid is None else _additive_cells(args, grid)
    if cells is None:
        return 1
    adopted = _adopt(cells)
    for cell in cells:
        print(f"{args.knob or 'value'}={cell.value} verdict={cell.result.verdict} own ExpR={cell.own_r}")
    print(f"verdict={'ADOPTED' if adopted else 'FAIL'} adopted={adopted.value if adopted else None}")
    shown = adopted or cells[0]
    _write_additive(args, shown.result, {
        **shown.extra, "plateau": _plateau(args, cells, adopted),
        "adopted": adopted.value if adopted else None,
        "cells": [{"value": c.value, "verdict": c.result.verdict, "own_r": c.own_r} for c in cells]})
    return 0 if adopted else 1


def stage_additive_walkforward(args):
    """Stage 2: clause 4 on the folds; the split is taken over the folds' pooled rows."""
    folds = load_folds(args.arms)
    baseline = [row for fold in folds for row in fold["baseline"]]
    component = [row for fold in folds for row in fold["component"]]
    return _finish_additive(args, baseline, component, "walkforward", folds)


def _folds_arms_refused(args):
    if args.folds_arms is None:
        print("refused:no-folds-arms -- Stage 3 reads clause 4 from the Stage 2 arms file "
              "(--folds-arms). Budget intact.", file=sys.stderr)
        return True
    if not args.bespoke_instrument:
        token = check_stamp(json.loads(Path(args.folds_arms).read_text()),
                            funnel_stage="walkforward", full_universe=_full_universe())
        if token:
            print(f"{token} -- --folds-arms stamp gate. Budget intact.", file=sys.stderr)
            return True
    return _basis_refused(args.folds_arms, "--folds-arms")


def stage_additive_validation(args):
    """Stage 3: the one VALIDATION shot, all four clauses."""
    if _folds_arms_refused(args):
        return 1
    baseline, component = load_arms(args.arms)
    return _finish_additive(args, baseline, component, "validation", load_folds(args.folds_arms))
```

- [ ] **Step 6: Run the new tests, the neighbours and the complexity gate**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_validate_component_additive_stages.py`
Expected: every test passes, `0 failed`, `0 xfailed`.

Run: `python scripts/dev/testrun.py file tests/backtesting/test_validate_component_additive.py` and `python scripts/dev/testrun.py file tests/backtesting/test_validate_component_selection.py`
Expected: both green (V238-7's tests and the old selection refusals untouched).

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (every new function under 15; `stage_selection` shrinks).

- [ ] **Step 7: Commit**

```bash
git add scripts/backtest/validate_component.py tests/backtesting/test_validate_component_additive_stages.py
git commit -m "feat(backtest): v238 validate_component --gate additive -- Stages 1-3, adoption, report with disclosures"
```


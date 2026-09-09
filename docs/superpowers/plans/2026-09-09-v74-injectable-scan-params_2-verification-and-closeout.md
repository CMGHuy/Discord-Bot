# v74 part 2 — Verification and close-out

Header, global constraints and parallelisation: `2026-09-09-v74-injectable-scan-params_0-index.md`. **Read that first** — its Global Constraints are part of every task below.

---

### Task C1: The committed fixture

**Files:**
- Create: `scripts/dev/make_v74_fixture.py`
- Create: `tests/fixtures/v74/AAPL.csv`, `tests/fixtures/v74/XOM.csv`
- Test: `tests/backtesting/test_v74_fixture.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `tests/fixtures/v74/` OHLCV CSVs and `load_v74_fixture() -> dict[str, DataFrame]` in `tests/backtesting/test_v74_fixture.py`, imported by C2 and C3.

The observability and parity tests need a frame that is **committed** (so the tests run anywhere), **small** (46 replays in C2), and **varied enough that most knobs can bite**. `data/backtest_cache/` is hidden by the root `.ignore` and is not committed, so a slice is copied into `tests/fixtures/`.

Two tickers, chosen for contrast: one high-beta large-cap tech (AAPL) and one energy name (XOM), so regime, RS and volume-profile knobs see genuinely different series. 500 daily bars covers the longest horizon's warmup.

- [ ] **Step 1: Write the failing test**

```python
# tests/backtesting/test_v74_fixture.py
"""The fixture is committed input to two other tests. If it drifts, both
silently change meaning -- so its shape is pinned here."""
from pathlib import Path

import pandas as pd

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "v74"
TICKERS = ("AAPL", "XOM")


def load_v74_fixture() -> dict:
    out = {}
    for sym in TICKERS:
        df = pd.read_csv(FIXTURE_DIR / f"{sym}.csv", index_col=0, parse_dates=True)
        out[sym] = df
    return out


def test_fixture_files_exist_and_have_the_expected_shape():
    frames = load_v74_fixture()
    assert set(frames) == set(TICKERS)
    for sym, df in frames.items():
        assert len(df) >= 500, f"{sym} has {len(df)} bars, need >=500"
        assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
        assert df.index.is_monotonic_increasing
        assert not df.isna().any().any(), f"{sym} has NaNs"


def test_fixture_is_deterministic_on_disk():
    """Two loads of the same file must be identical -- guards against a
    future task regenerating it with a different dtype or rounding."""
    a, b = load_v74_fixture(), load_v74_fixture()
    for sym in TICKERS:
        pd.testing.assert_frame_equal(a[sym], b[sym])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtesting/test_v74_fixture.py -v`
Expected: FAIL — `FileNotFoundError: .../tests/fixtures/v74/AAPL.csv`.

- [ ] **Step 3: Write minimal implementation**

```python
#!/usr/bin/env python3
# scripts/dev/make_v74_fixture.py
"""Cut the v74 test fixture out of the backtest cache.

Run once; the output is committed. data/backtest_cache/ is hidden by the
root .ignore and is not in git, so the tests cannot read it directly.

    python scripts/data/fetch_backtest_data.py     # if the cache is cold
    python scripts/dev/make_v74_fixture.py
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE = ROOT / "data" / "backtest_cache"
OUT = ROOT / "tests" / "fixtures" / "v74"
TICKERS = ("AAPL", "XOM")
BARS = 500


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for sym in TICKERS:
        src = CACHE / f"{sym}.csv"
        if not src.exists():
            print(f"MISSING {src} -- run scripts/data/fetch_backtest_data.py first")
            return 1
        df = pd.read_csv(src, index_col=0, parse_dates=True)
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna().tail(BARS)
        df = df.round(4)
        df.to_csv(OUT / f"{sym}.csv")
        print(f"wrote {OUT / f'{sym}.csv'}  ({len(df)} bars, "
              f"{df.index[0].date()}..{df.index[-1].date()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Run it: `python scripts/dev/make_v74_fixture.py`

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_v74_fixture.py`
Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add scripts/dev/make_v74_fixture.py tests/fixtures/v74/ tests/backtesting/test_v74_fixture.py
git commit -m "test(v74): commit the two-ticker fixture the seam tests read"
```

---

### Task C2: The observability test

**Files:**
- Create: `tests/backtesting/test_knob_observability.py`
- Test: itself

**Interfaces:**
- Consumes: `config.searchable_attrs()` (A2), `ScanParams` (A1), `replay_scenarios(params=...)` (B3), `load_v74_fixture` (C1).
- Produces: `EXEMPT` — the recorded list of knobs this harness cannot exercise, with a reason per entry.

**This is the task the whole plan exists for.** A knob that can be *set* but changes *nothing* is the failure that cost v49 its measurement and cost v34 a purpose-built instrument. After this task, that condition is a red test rather than a discovery made after a pre-registered shot is spent.

Marked `slow`: ~36 replays over 2 tickers.

- [ ] **Step 1: Write the failing test**

```python
# tests/backtesting/test_knob_observability.py
"""Every searchable knob must observably change the replay's output.

A knob that can be set but changes nothing produces grid cells that differ
only by noise, and an argmax over them is luck. v49's EFFECTIVE_CONFLUENCE
shipped a flag whose on-arm rejected every scenario by construction; v34
discovered mid-plan that the replay harness cannot see scanning/engine.py
gates at all. Both were found by hand, late. This finds them mechanically.

A knob that legitimately cannot bite on this fixture belongs in EXEMPT with
a stated reason -- never deleted from the searchable class to make the suite
green.
"""
import dataclasses

import pytest

from swingbot import config
from swingbot.core.backtesting.backtest_scenarios import replay_scenarios
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.scan_params import ScanParams

from .test_v74_fixture import load_v74_fixture

#: attr -> why this fixture cannot exercise it. Every entry is a real
#: limitation of the instrument, not a convenience.
EXEMPT = {
    "EARNINGS_BLACKOUT_DAYS":
        "needs an earnings date inside the fixture window; the fixture "
        "carries OHLCV only, no calendar.",
    "UNIVERSE_MIN_DOLLAR_VOL":
        "universe construction happens before replay; the fixture IS the "
        "universe, so the filter has nothing to remove.",
    "UNIVERSE_MIN_PRICE":
        "same as UNIVERSE_MIN_DOLLAR_VOL -- pre-replay universe filter.",
    "MAX_ALERTS_PER_SCAN":
        "a per-scan cap applied by scan_run's alerting path, which "
        "replay_scenarios does not run.",
    "MIN_ALERT_CONFIDENCE_LEVEL":
        "confidence scoring lives in core/scanning/confidence.py and is "
        "not computed by replay_scenarios. Spec finding: this is the known "
        "open case -- if v75 needs it, the replay must call the scorer.",
    "UNIFIED_CONFIDENCE": "same path as MIN_ALERT_CONFIDENCE_LEVEL.",
    "RS_GATE":
        "relative strength is cross-sectional; a 2-ticker fixture cannot "
        "form percentiles. v34 needed measure_rs_gate_effect.py for this.",
    "RS_LEADER_PERCENTILE": "same as RS_GATE -- cross-sectional.",
    "RS_LAGGARD_PERCENTILE": "same as RS_GATE -- cross-sectional.",
    "REGIME_GATES_ENABLED":
        "reads the market-regime ticker, which is not in the fixture.",
    "PLAN_ENGINE_V2":
        "a v1/v2 switch on the live plan path; replay_scenarios is v2-only "
        "by construction.",
}

PERTURB = {
    bool: lambda v: not v,
    int: lambda v: max(1, int(v) + 1),
    float: lambda v: float(v) * 1.75 + 0.5,
}


def _plan_key(ticker, hk, i, plan) -> tuple:
    """TradePlanV2's real price fields. Not asdict(): plan_id and created_at
    differ between two calls for reasons unrelated to params."""
    return (ticker, hk, int(i), plan.trigger_price, plan.entry_price,
            plan.stop_loss, plan.tp1, plan.tp2)


def _run(params) -> list:
    frames = load_v74_fixture()
    out = []
    for ticker, df in frames.items():
        for hk in ("4w", "3m"):
            for i, plan in replay_scenarios(ticker, df, hk, params=params):
                out.append(_plan_key(ticker, hk, i, plan))
    return out


@pytest.fixture(scope="module")
def baseline():
    return _run(ScanParams.from_config())


def _searchable_not_exempt():
    return [a for a in config.searchable_attrs() if a not in EXEMPT]


@pytest.mark.slow
@pytest.mark.parametrize("attr", _searchable_not_exempt())
def test_knob_is_observable(attr, baseline):
    base = ScanParams.from_config()
    field = attr.lower()
    current = getattr(base, field)
    perturb = PERTURB.get(type(current))
    if perturb is None:
        pytest.fail(f"{attr} is {type(current).__name__}; add a PERTURB rule "
                    f"or an EXEMPT entry with a reason")
    changed = _run(dataclasses.replace(base, **{field: perturb(current)}))
    assert changed != baseline, (
        f"{attr} changed nothing. Either the seam does not reach it (fix the "
        f"seam), or this harness cannot see it (move it to EXEMPT with a "
        f"reason, or reclassify it live_only in config.FIELDS). Do NOT "
        f"delete it from the searchable class to make this pass.")


def test_every_exempt_entry_is_actually_searchable():
    """EXEMPT must not accumulate stale names -- an entry for a knob that is
    no longer searchable is dead weight that hides the real list."""
    searchable = set(config.searchable_attrs())
    assert set(EXEMPT) <= searchable, f"stale EXEMPT entries: {set(EXEMPT) - searchable}"


def test_exempt_reasons_are_substantive():
    for attr, reason in EXEMPT.items():
        assert len(reason) > 40, f"{attr}'s exemption needs a real reason"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtesting/test_knob_observability.py -v -m slow`
Expected: FAIL — collection error if B3's `params=` keyword is missing, otherwise assorted `test_knob_is_observable` failures for knobs the seam has not reached.

- [ ] **Step 3: Make it pass — by fixing the seam, not the test**

For each failing knob, in this order:

1. **Is the value reaching the code that uses it?** `grep -n "config.<ATTR>" swingbot/` — a remaining global read means B1/B2/B3 missed a site. Thread it. This is the expected cause for most failures and the real deliverable of this task.
2. **Does the replay path execute that code at all?** If `replay_scenarios` never calls the consumer, the knob is invisible to this instrument: add an `EXEMPT` entry naming the module that owns it.
3. **Is the knob genuinely wall-clock or cross-sectional?** Reclassify it `live_only` in `config.FIELDS` (Task A2's list) and note the move in the commit message.

Never resolve a failure by removing the knob from `searchable` without one of these three justifications written down.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backtesting/test_knob_observability.py -v -m slow`
Expected: PASS. Record the final `EXEMPT` size in the commit message — that number is the honest measure of this harness's blind spots and Task D2 copies it into `known-traps.md`.

- [ ] **Step 5: Commit**

```bash
git add tests/backtesting/test_knob_observability.py swingbot/
git commit -m "test(v74): every searchable knob must observably change the replay"
```

---

### Task C3: The zero-observable-difference gate

**Files:**
- Create: `tests/backtesting/test_v74_no_behaviour_change.py`
- Create: `tests/fixtures/v74/golden_plans.json`

**Interfaces:**
- Consumes: `load_v74_fixture` (C1), `replay_scenarios` (B3).
- Produces: the golden file that pins pre-v74 behaviour.

Global constraint 1 says this refactor changes nothing the bot does. This is the gate on that claim, and it is the reason the bump is a patch.

**The golden file must be generated from code that predates the seam.** Generating it after the refactor would pin whatever the refactor produced, including a bug — the test would then be self-confirming and worthless.

- [ ] **Step 1: Generate the golden file from pre-v74 code**

```bash
git stash list                      # ensure nothing is stashed you need
git worktree add ../v74-baseline 58deb633
cd ../v74-baseline
python - <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, ".")
import pandas as pd
from swingbot.core.backtesting.backtest_scenarios import replay_scenarios, CONFLUENCE_GATES

FIX = Path("../Discord-Bot/tests/fixtures/v74")

def r(v):
    return None if v is None else round(float(v), 6)

rows = []
for sym in ("AAPL", "XOM"):
    df = pd.read_csv(FIX / f"{sym}.csv", index_col=0, parse_dates=True)
    for hk in ("4w", "3m"):
        for i, plan in replay_scenarios(sym, df, hk, gates=CONFLUENCE_GATES):
            rows.append([sym, hk, int(i), r(plan.trigger_price),
                         r(plan.entry_price), r(plan.stop_loss),
                         r(plan.tp1), r(plan.tp2)])
Path("../Discord-Bot/tests/fixtures/v74/golden_plans.json").write_text(
    json.dumps(rows, indent=1))
print(f"{len(rows)} plans pinned")
PY
cd ../Discord-Bot
git worktree remove ../v74-baseline
```

If C1's fixture does not exist at `58deb633`, copy it in before running: the worktree is a clean checkout and will not have it.

- [ ] **Step 2: Write the failing test**

```python
# tests/backtesting/test_v74_no_behaviour_change.py
"""v74 is a refactor. ScanParams.from_config() must reproduce, exactly, the
plans the pre-seam code produced -- global constraint 1, and the reason this
ships as a patch rather than a minor.

golden_plans.json was generated at 58deb633, before the seam existed. Do not
regenerate it from post-v74 code: a golden file produced by the code it
tests confirms nothing.
"""
import json
from pathlib import Path

from swingbot.core.backtesting.backtest_scenarios import replay_scenarios
from swingbot.scan_params import ScanParams

from .test_v74_fixture import load_v74_fixture

GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "v74" / "golden_plans.json"


def _r(v):
    return None if v is None else round(float(v), 6)


def test_from_config_reproduces_pre_v74_plans():
    expected = [tuple(row) for row in json.loads(GOLDEN.read_text())]
    params = ScanParams.from_config()
    got = []
    for sym, df in load_v74_fixture().items():
        for hk in ("4w", "3m"):
            for i, plan in replay_scenarios(sym, df, hk, params=params):
                got.append((sym, hk, int(i), _r(plan.trigger_price),
                            _r(plan.entry_price), _r(plan.stop_loss),
                            _r(plan.tp1), _r(plan.tp2)))
    assert len(got) == len(expected), (
        f"plan count moved: {len(expected)} -> {len(got)}. The seam changed "
        f"which setups qualify, which global constraint 1 forbids.")
    assert got == expected
```

- [ ] **Step 3: Run test to verify it fails, then passes**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_v74_no_behaviour_change.py`

If it fails: the seam changed behaviour. Find the cause. The three likely ones, in order — `scenario_gate_inputs` reordering a `max()` against a float, `passes_confluence` using `>=` where the original used `<` with a different default, and `build_level_map`'s flags resolving differently when `params` is None. Fix the seam. **Do not regenerate the golden file.**

- [ ] **Step 4: Commit**

```bash
git add tests/backtesting/test_v74_no_behaviour_change.py tests/fixtures/v74/golden_plans.json
git commit -m "test(v74): pin that the seam changes no plan the bot would build"
```

---

### Task D1: Make the dead gate loud

**Files:**
- Modify: `scripts/backtest/tune_strategy.py:154-159`
- Modify: `scripts/backtest/tune_confluence_gates.py:91`
- Modify: `scripts/backtest/tune_exit_v2.py:86`
- Modify: `scripts/backtest/run_confluence_validation.py:146`
- Modify: `scripts/backtest/run_backtest_range.py:9` (docstring only)
- Test: `tests/scripts/test_tuner_gate_loudness.py`

**Interfaces:**
- Consumes: nothing from earlier tasks. **Independent of the seam** — runnable in parallel with C1.
- Produces: `report_gate(rows, qualifying) -> dict` in `scripts/backtest/tune_strategy.py`.

The defect is not the number `80`. It is `sorted(qualifying or rows, ...)` at `tune_strategy.py:158` — a gate that disables itself in silence, so a results doc reads as though a gate applied when none did. Since the population sits near 35% and the floor is 80, `qualifying` has been empty on every recent run.

**What the threshold should become is v76's decision**, not this task's: post-v72 a feature is judged against the baseline it replaces, never an absolute floor. D1 stops the silent degradation and leaves the rule alone.

- [ ] **Step 1: Write the failing test**

```python
# tests/scripts/test_tuner_gate_loudness.py
"""A gate that silently disables itself is worse than no gate: the results
doc still reads as though one applied. tune_strategy.py has been in that
state since v31 retired the 80% floor it still filters on."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

from tune_strategy import report_gate  # noqa: E402


def _row(wr, er, n=100):
    return ({"k": 1}, {"n_eval": n, "win_rate": wr, "expectancy_r": er,
                       "excluded_share": 0.1})


def test_reports_ungated_when_nothing_qualifies():
    rows = [_row(35.0, 0.05), _row(36.0, 0.02)]
    got = report_gate(rows, [])
    assert got["gated"] is False
    assert got["n_qualifying"] == 0
    assert "UNGATED" in got["headline"]
    assert "80" in got["headline"]


def test_reports_gated_when_some_qualify():
    rows = [_row(85.0, 0.05), _row(36.0, 0.02)]
    got = report_gate(rows, [rows[0]])
    assert got["gated"] is True
    assert got["n_qualifying"] == 1
    assert "UNGATED" not in got["headline"]


def test_the_json_payload_carries_the_flag():
    """A results doc built from the JSON must be able to see this, not just
    someone who happened to read stdout."""
    got = report_gate([_row(35.0, 0.05)], [])
    assert set(got) >= {"gated", "n_qualifying", "n_rows", "headline"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/scripts/test_tuner_gate_loudness.py -v`
Expected: FAIL — `ImportError: cannot import name 'report_gate'`.

- [ ] **Step 3: Write minimal implementation**

Add to `scripts/backtest/tune_strategy.py` above `main()`:

```python
def report_gate(rows: list, qualifying: list) -> dict:
    """Say plainly whether the acceptance gate actually selected anything.

    The WR>=80 floor below was retired by v31 (docs/claude/backtest-
    methodology.md: "do not restore 80% for any run against the current
    engine"), and the confluence population sits near 35%, so `qualifying`
    is empty on every realistic run and the ranking below is an ungated
    argmax. That may still be a useful exploratory ordering -- it is NOT a
    gated selection, and a results doc must not read as though it were.
    Replacing the rule is v76's job; saying so out loud is this one's.
    """
    gated = bool(qualifying)
    headline = (f"{len(qualifying)}/{len(rows)} configs qualify "
                f"(WR>=80, ExpR>0, N>=30, excl<=50%)")
    if not gated:
        headline += ("  ***UNGATED***: no config cleared the gate, so the "
                     "ranking below is argmax over the FULL grid with no "
                     "acceptance applied. Do not report it as a selection.")
    return {"gated": gated, "n_qualifying": len(qualifying),
            "n_rows": len(rows), "headline": headline}
```

Replace lines 157–159 of `main()`:

```python
    gate_report = report_gate(rows, qualifying)
    print("\n" + gate_report["headline"])
    ranked = sorted(qualifying or rows,
                    key=lambda r: (r[1]["expectancy_r"] or -9), reverse=True)
```

and add `"gate": gate_report,` to the `payload` dict written by `--json`.

For the other four scripts, add a one-line comment above each retired-floor expression, no behaviour change:

```python
# v31 retired this 80% floor (live bar is 50); see docs/claude/backtest-
# methodology.md. It is left in place deliberately -- v76 replaces the rule
# for every tuner at once. v74 only ensures no script reports an ungated
# ranking as a gated selection.
```

`run_backtest_range.py:9`'s docstring says "PASS gate per spec: win_rate >= 80" — correct it to quote the live 50 and cite the methodology doc.

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/scripts/test_tuner_gate_loudness.py`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/ tests/scripts/test_tuner_gate_loudness.py
git commit -m "fix(v74): tuners can no longer report an ungated argmax as a gated selection"
```

---

### Task D2: Documentation and the Codex mirror

**Files:**
- Modify: `docs/claude/backtest-methodology.md`
- Modify: `docs/claude/known-traps.md`
- Modify: `.codex/AGENTS.md`

**Interfaces:**
- Consumes: C2's final `EXEMPT` list, B4's parity outcome.

- [ ] **Step 1: Add the searchability contract to `backtest-methodology.md`**

A new section after the acceptance-gates block:

```markdown
- **Searchability (v74).** Every `config.Field` carries a `search_class`:
  `searchable` (a decision knob the daily-bar replay can observe), `frozen`
  (injectable, but changing it needs its own pre-registration), `live_only`
  (wall-clock/intraday — this harness cannot measure it), `never`
  (measurement fidelity: `SLIPPAGE_BPS`, `COMMISSION_*` — tuning these is
  self-deception), `excluded`. `config.searchable_attrs()` is the only
  legitimate source for what a grid may vary.
  `tests/backtesting/test_knob_observability.py` asserts every searchable
  knob observably changes the replay; its `EXEMPT` dict is the maintained
  list of this harness's blind spots, each with a reason. **A knob that
  fails observability is not a broken test — it is the discovery that the
  instrument cannot see it.**
```

- [ ] **Step 2: Add the parity trap to `known-traps.md`**

Record, with `file:line`: that three gate definitions existed before v74 and `BASE_GATES` diverged from shipped values (`min_confluence` 1 vs 2, `min_risk_reward` 0.0 vs 1.5), so v68 measured a population the live bot never alerts on and v72's Task B1 fixture inherits it; that `ScanParams` is frozen and tuple-only because v75 pickles cells into a process pool; and — **if B4 took its "different" branch** — the live/replay gating divergence, with both expressions quoted verbatim.

- [ ] **Step 3: Mirror to `.codex/AGENTS.md`**

Condense Steps 1–2 into 4–6 lines under the existing testing/methodology section. Condensed to match, never copied verbatim; the sync is one-way.

- [ ] **Step 4: Verify no doc claims something the code does not do**

Run: `grep -rn "searchable_attrs\|search_class" docs/ .codex/ swingbot/ tests/ | head -20`
Every documented symbol must exist. A doc naming a symbol no task built is a placeholder.

- [ ] **Step 5: Commit**

```bash
git add docs/claude/ .codex/AGENTS.md
git commit -m "docs(v74): the searchability contract and the gate-parity trap"
```

---

### Task D3: Version bump and full-suite verification

**Files:**
- Modify: `VERSION.json`
- Modify: `data/version_history.json` (regenerated, not hand-edited)

**Interfaces:**
- Consumes: every preceding task.

This is the plan's **only** full-suite run.

- [ ] **Step 1: Confirm the branch is current before claiming anything**

```bash
git fetch origin
git status -sb
git log --oneline origin/main..HEAD | head -30
```

A local `main` behind `origin/main` invalidates every claim below. Reconcile before continuing.

- [ ] **Step 2: Run the full suite**

Run: `python scripts/dev/testrun.py full`
Expected: `0 failed`, `0 xfailed`. A *changed pass count* is not a failure — this plan adds tests. A changed count with any failure is.

Dispatch the `test-runner` subagent for this so ~1150 progress lines stay out of the session context.

- [ ] **Step 3: Bump `VERSION.json`**

`bot` patch only; `ui` untouched. If v72 has landed, `1.6.2 → 1.6.3`; if it has not, `1.6.1 → 1.6.2`. Read the file, do not assume. Set `bot_updated` to the current timestamp in the existing `YYYY-MM-DD HH-MM-SS` format.

The bump is a patch because Task C3 proves no observable difference — per `working-conventions.md` the test is observable difference, not diff size, and this plan touches many files while changing nothing a user can see.

- [ ] **Step 4: Regenerate the version history**

```bash
python scripts/dev/build_version_matrix.py
git diff --stat data/version_history.json
```

**This step cannot be skipped.** The local gate runs *before* the bump, so it structurally cannot catch a missing regeneration — the only thing that catches it is doing it here.

- [ ] **Step 5: Commit**

```bash
git add VERSION.json data/version_history.json
git commit -m "chore(v74): bot patch -- injectable scan params, no observable difference"
```

- [ ] **Step 6: Close the plan out**

Move all three plan parts to `docs/superpowers/plans/implemented/`, and append to the plan header: the final `EXEMPT` count from C2, and which branch B4 took. Commit as `docs(v74): close injectable scan params -- all 12 tasks complete`.

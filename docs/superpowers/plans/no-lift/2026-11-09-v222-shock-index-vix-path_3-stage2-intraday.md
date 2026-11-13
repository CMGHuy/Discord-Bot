# v222 — Market-shock detector: index + VIX entry path — Part 3: Stage 2 intraday

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [`docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md`](../specs/2026-11-09-v222-shock-index-vix-path-design.md)
**Index:** [`2026-11-09-v222-shock-index-vix-path_0-index.md`](2026-11-09-v222-shock-index-vix-path_0-index.md) — Goal, Global Constraints, plan-time readings, Parallelisation and the task ledger live there; every task below implicitly includes them.

Tasks V222-6d, V222-7, V222-7b: the derived 2026-11-05 fixture with real
one-minute `^VIX` (built now, read only in Stage 3) and the intraday evaluator
(readings, A1's first `SHOCK` re-derived, the index half, the five gates, the
ramp run). V222-7c (adapter, report, CLI) and V222-8 (the Stage 2 run and gate
2) continue in [`_3b-stage2-run.md`](2026-11-09-v222-shock-index-vix-path_3b-stage2-run.md),
a second file only because of the 1500-line cap. `shock.py` is not edited
here; the index half lives in the evaluator until V222-9.

**Plan-time readings this part fixes (index § plan-time readings, extended here
before any Stage 2 data is read; the controller checks them):**

- **Slot filling.** A slot's candidates are its pick followed by its reserves,
  in ranking order. The first candidate whose fixture status is `ok` fills it;
  `unbuildable`, `synthetic` and `no_vix` candidates are skipped (listed in the
  result). A candidate without a fixture on disk stops the slot: the run is
  `INCOMPLETE` and names the day to build next. A slot whose candidates are all
  skipped is **exhausted** and scores against the cell, like A1's unbuildable
  days: an exhausted counted shock slot neither survives nor leads, an exhausted
  quiet or near-miss slot counts as a fire.
- **Fixture source.** A day on the list that has an A1 fixture (in
  `tests/fixtures/shock_replay/`) reuses it as is; every other day is built into
  `tests/fixtures/shock_replay_v222/`.
- **Drop still ahead.** `(SPY at t − close) / (prior close − close)` with
  `SPY at t` = the reading's `spy_last` at `t`. A day whose close is at or above
  its prior close, or whose reading at `t` has no `spy_last`, has no share and
  does not lead. A1 never firing gives `t_A1` = the fixture's `close_utc` and a
  share of 0.
- **Builder inputs.** The adapter takes each day's SPY and `^VIX` open, close and
  previous close from the Stage 1 files `data/v222/SPY.csv` and `data/v222/^VIX.csv`
  (each series' own previous row, as A1's `day_table` does); it does not call
  `shock_validation_days.day_table`, which keeps only 2023–2025 and needs QQQ.
- **Stage 3 prior.** The 2026-11-04 `^VIX` close is read only once the Stage 2
  day list is committed in Results (2026-11-04 is itself a possible candidate).

**Paths used in every task.**

```bash
M=E:/Documents/Private/Projects/Discord-Bot                                   # main tree
W=$M/.claude/worktrees/2026-11-09-v222-shock-index-vix-path                   # worktree (all code)
D=$M/data/v222                                                                 # stage data (gitignored, main tree)
```

`scripts/dev/testrun.py` resolves test paths against its own checkout, so
`python "$W/scripts/dev/testrun.py" file tests/...` runs the worktree's tests.
Never `cd`; use `git -C "$W"` and absolute paths.

# Phase 3 — Stage 2 intraday confirmation and lead

### Task V222-6d: Derived 2026-11-05 fixture with real one-minute `^VIX` (new path, frozen file untouched)

**Model:** sonnet — a bounded builder extension (CSV reader, last-finished-bar lookup, deep copy) with exact tests; no frozen rule is touched.

**Files:**
- Modify: `scripts/data/build_shock_replay_fixture.py` (imports, constants beside `DEFAULT_OUT`, three functions after `daily_vix_path`, `_parse`, `_main_vix1m`, `main`)
- Modify: `tests/scripts/test_build_shock_replay_fixture.py` (append)
- Create: `tests/fixtures/shock_replay_2026_11_05_vix1m.json` (Step 6, after the Stage 2 day list is committed)
- Modify: `scripts/dev/select_tests.py` (`DATA_READERS`: two exact rows below the 2026-11-05 row)

**Interfaces:**
- Consumes: `tests/fixtures/vix_2026_11_05_1m.csv` (on `main`, `b253ef36`; three yfinance header rows `Price,...` / `Ticker,...` / `Datetime,...`, then `2026-11-05 08:15:00+00:00,<adj>,<close>,...`); `DEFAULT_OUT` (the frozen 11-05 fixture, read only); `data/v222/^VIX.csv` (V222-1) for the prior close; Results § Stage 2 day list committed (V222-5) before Step 6.
- Produces: `VIX_BARS = ROOT / "tests/fixtures/vix_2026_11_05_1m.csv"`, `VIX1M_OUT = ROOT / "tests/fixtures/shock_replay_2026_11_05_vix1m.json"` (the ledger's repo-relative paths, anchored on `ROOT` like `DEFAULT_OUT`), `VIX_BARS_SOURCE = "yfinance_1m"`; `load_vix_bars(path: Path) -> list[tuple[datetime, float]]`; `vix_from_bars(bars, t: datetime, prior: float) -> dict`; `derive_vix1m_fixture(frozen: dict, bars, prior: float) -> dict`; CLI `--vix-bars PATH --vix-prior LEVEL [--out]`; the committed fixture (header keys `source`, `vix_interpolated: false`, `vix_source`, `vix_prior`, `note`, `steps`, `long_entries`), which V222-13 reads.

The derived fixture differs from the frozen one **only** in each step's `vix`
and the header keys `vix_interpolated`, `vix_source`, `vix_prior`. Every other
byte of every step (names, SPY, QQQ, `as_of`, `minutes_since_open`) and
`long_entries` is copied. The frozen file is never written: the CLI refuses an
`--out` that resolves to it. A step reads the close of the last one-minute bar
**finished** by the step (bar start + 1 min ≤ step time), against the prior
close passed in.

- [ ] **Step 1: Write the failing tests**

Append to `tests/scripts/test_build_shock_replay_fixture.py`:

```python
# --- v222 V222-6d: the 2026-11-05 fixture with real one-minute ^VIX ---------

VIX_HEADER = ("Price,Adj Close,Close,High,Low,Open,Volume\n"
              "Ticker,^VIX,^VIX,^VIX,^VIX,^VIX,^VIX\nDatetime,,,,,,\n")


def _vix_csv(tmp_path, rows):
    path = tmp_path / "vix.csv"
    body = "".join(f"{ts},{c},{c},{c},{c},{c},0\n" for ts, c in rows)
    path.write_text(VIX_HEADER + body, encoding="utf-8")
    return path


def test_load_vix_bars_reads_the_yfinance_csv_sorted_in_utc(tmp_path):
    path = _vix_csv(tmp_path, [("2026-11-05 14:45:00+00:00", 19.5),
                               ("2026-11-05 14:44:00+00:00", 19.0)])
    assert bsr.load_vix_bars(path) == [(T(14, 44), 19.0), (T(14, 45), 19.5)]


def test_the_archived_csv_loads_from_its_first_bar():
    bars = bsr.load_vix_bars(bsr.VIX_BARS)
    assert bars[0][0] == T(8, 15) and bars[0][1] == pytest.approx(17.15, abs=1e-6)
    assert [b[0] for b in bars] == sorted(b[0] for b in bars)


def test_a_step_reads_the_last_bar_finished_by_it():
    bars = [(T(14, 43), 18.0), (T(14, 44), 20.0), (T(14, 45), 30.0)]
    assert bsr.vix_from_bars(bars, T(14, 45), 16.0) == {"level": 20.0, "chg_pct": 25.0}
    assert bsr.vix_from_bars(bars, T(14, 44), 16.0) == {"level": 18.0, "chg_pct": 12.5}
    assert bsr.vix_from_bars(bars, T(14, 43), 16.0) == {"level": None, "chg_pct": None}


def _frozen():
    steps = [{"as_of": T(14, 45).isoformat(), "minutes_since_open": 15.0,
              "vix": {"level": 17.0, "chg_pct": 2.0}, "spy": {"last": 1.0}, "qqq": None,
              "names": [{"ticker": "A", "last": 2.0}]},
             {"as_of": T(15, 0).isoformat(), "minutes_since_open": 30.0,
              "vix": {"level": 18.0, "chg_pct": 8.0}, "spy": {"last": 0.5}, "qqq": None,
              "names": [{"ticker": "A", "last": 1.5}]}]
    return {"source": "alpaca", "vix_interpolated": True, "note": "n", "steps": steps,
            "long_entries": [{"ticker": "A", "opened_at": T(14, 50).isoformat()}]}


def _without(d: dict, *keys) -> str:
    return json.dumps({k: v for k, v in d.items() if k not in keys}, sort_keys=True)


def test_the_derived_fixture_changes_only_vix_and_the_header_flags():
    frozen = _frozen()
    before = json.dumps(frozen, sort_keys=True)
    bars = [(T(14, 44), 20.0), (T(14, 59), 24.0)]
    fx = bsr.derive_vix1m_fixture(frozen, bars, 16.0)
    assert json.dumps(frozen, sort_keys=True) == before           # input untouched
    assert (fx["vix_interpolated"], fx["vix_source"], fx["vix_prior"]) == (
        False, "yfinance_1m", 16.0)
    assert [s["vix"] for s in fx["steps"]] == [{"level": 20.0, "chg_pct": 25.0},
                                              {"level": 24.0, "chg_pct": 50.0}]
    assert ([_without(s, "vix") for s in fx["steps"]]
            == [_without(s, "vix") for s in frozen["steps"]])
    header = ("steps", "vix_interpolated", "vix_source", "vix_prior")
    assert _without(fx, *header) == _without(frozen, *header)


def test_the_cli_writes_a_new_path_and_never_the_frozen_file(tmp_path, monkeypatch):
    frozen_path = tmp_path / "frozen.json"
    frozen_path.write_text(json.dumps(_frozen()), encoding="utf-8")
    monkeypatch.setattr(bsr, "DEFAULT_OUT", frozen_path)
    bars = _vix_csv(tmp_path, [("2026-11-05 14:44:00+00:00", 20.0)])
    out = tmp_path / "derived.json"
    args = ["--vix-bars", str(bars), "--vix-prior", "16.0"]
    assert bsr.main([*args, "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["steps"][0]["vix"]["level"] == 20.0
    before = frozen_path.read_bytes()
    assert bsr.main([*args, "--out", str(frozen_path)]) == 2
    assert bsr.main(["--vix-bars", str(bars), "--out", str(out)]) == 2   # no prior
    assert frozen_path.read_bytes() == before
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python "$W/scripts/dev/testrun.py" file tests/scripts/test_build_shock_replay_fixture.py`
Expected: the five new tests FAIL (`AttributeError: ... 'load_vix_bars'`, `'VIX_BARS'`, ...); the existing ones pass.

- [ ] **Step 3: Implement the derivation**

In `scripts/data/build_shock_replay_fixture.py` add `import copy` and `import csv` to the stdlib imports. Below `DEFAULT_CACHE = ...` add:

```python
VIX_BARS = ROOT / "tests/fixtures/vix_2026_11_05_1m.csv"
VIX1M_OUT = ROOT / "tests/fixtures/shock_replay_2026_11_05_vix1m.json"
VIX_BARS_SOURCE = "yfinance_1m"
BAR = timedelta(minutes=1)
```

After `daily_vix_path` add:

```python
def load_vix_bars(path: Path) -> list[tuple[datetime, float]]:
    """yfinance one-minute CSV (three header rows) -> sorted (UTC bar start, close)."""
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    close = rows[0].index("Close")
    bars = [(datetime.fromisoformat(r[0]).astimezone(UTC), float(r[close]))
            for r in rows[3:] if r and r[close]]
    return sorted(bars)


def vix_from_bars(bars, t: datetime, prior: float) -> dict:
    """The close of the last bar finished by `t`, and its change vs `prior` (%)."""
    done = [close for start, close in bars if start + BAR <= t]
    if not done:
        return {"level": None, "chg_pct": None}
    level = done[-1]
    return {"level": round(level, 4), "chg_pct": round((level / prior - 1) * 100, 4)}


def derive_vix1m_fixture(frozen: dict, bars, prior: float) -> dict:
    """The frozen 11-05 fixture with each step's VIX read from real one-minute bars.

    Only `vix` per step and the header flags change; the input is not mutated."""
    out = copy.deepcopy(frozen)
    for step in out["steps"]:
        step["vix"] = vix_from_bars(bars, datetime.fromisoformat(step["as_of"]), prior)
    out.update(vix_interpolated=False, vix_source=VIX_BARS_SOURCE, vix_prior=prior)
    return out
```

- [ ] **Step 4: Wire the CLI**

In `_parse`, change the `--out` default to `None` and add two flags:

```python
    ap.add_argument("--out", default=None)
    # ... existing flags unchanged ...
    ap.add_argument("--vix-bars", default=None)
    ap.add_argument("--vix-prior", type=float, default=None)
```

Add above `main`:

```python
def _main_vix1m(args) -> int:
    out = Path(args.out) if args.out else VIX1M_OUT
    if args.vix_prior is None or args.vix_prior <= 0:
        print("--vix-bars needs --vix-prior LEVEL (the 2026-11-04 ^VIX close)", file=sys.stderr)
        return 2
    if out.resolve() == Path(DEFAULT_OUT).resolve():
        print(f"refusing to write the frozen {Path(DEFAULT_OUT).name}", file=sys.stderr)
        return 2
    frozen = json.loads(Path(DEFAULT_OUT).read_text(encoding="utf-8"))
    fx = derive_vix1m_fixture(frozen, load_vix_bars(Path(args.vix_bars)), args.vix_prior)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fx, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out}: {len(fx['steps'])} steps, VIX from {args.vix_bars}")
    return 0
```

In `main`, dispatch the new mode first and give the 11-05 build its old default
(only these two edits; the rest of `main` stays as is):

```python
def main(argv=None, *, provider=None, limiter=None) -> int:
    args = _parse(argv)
    if args.vix_bars:
        return _main_vix1m(args)
    if args.validation_days:
        return _main_validation(args, provider, limiter)
    # ... unchanged down to the output path, which becomes:
    out = Path(args.out or DEFAULT_OUT)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python "$W/scripts/dev/testrun.py" file tests/scripts/test_build_shock_replay_fixture.py`
Expected: all pass (the existing tests unchanged).

Run: `python "$W/scripts/dev/complexity_gate.py"`
Expected: no new function at or above 15.

```bash
git -C "$W" add scripts/data/build_shock_replay_fixture.py tests/scripts/test_build_shock_replay_fixture.py
git -C "$W" commit -m "feat(v222): derive the 2026-11-05 fixture from real one-minute ^VIX bars"
```

- [ ] **Step 6: Build the derived fixture (only after the Stage 2 day list is committed)**

Precondition: Results § Stage 2 day list is committed on `main` (V222-5) and
gate 1 said go on. On NO-LIFT at gate 1 skip Steps 6 and 7: Stage 3 never runs.
If V222-5 has not run yet, stop after Step 5 and come back for Steps 6 and 7.

```bash
grep -n "^### Stage 2 day list" -A 3 "$M/docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md"
PRIOR=$(python -c "import pandas as pd; f = pd.read_csv(r'$D/^VIX.csv', parse_dates=['Date'], index_col='Date'); print(round(float(f.loc['2026-11-04', 'Close']), 4))")
echo "prior VIX close 2026-11-04: $PRIOR"
python "$W/scripts/data/build_shock_replay_fixture.py" --vix-bars "$W/tests/fixtures/vix_2026_11_05_1m.csv" --vix-prior "$PRIOR"
git -C "$W" status --short tests/fixtures/
```

Expected: the heading is followed by the drawn list (not `Pending V222-5.`); a
prior near 16.6 (the frozen fixture's implied 21.13 / 1.2721); `wrote
.../shock_replay_2026_11_05_vix1m.json: 26 steps`; status shows the new fixture
and **no** change to `shock_replay_2026_11_05.json`. Do not replay the fixture
or look at its readings: V222-13 reports it once.

Append the committed-fixture test to `tests/scripts/test_build_shock_replay_fixture.py`:

```python
def test_the_committed_vix1m_fixture_is_the_frozen_one_with_real_vix():
    fx = json.loads(bsr.VIX1M_OUT.read_text(encoding="utf-8"))
    frozen = json.loads(bsr.DEFAULT_OUT.read_text(encoding="utf-8"))
    assert frozen["vix_interpolated"] is True and fx["vix_interpolated"] is False
    assert fx["vix_source"] == "yfinance_1m" and fx["vix_prior"] > 0
    assert fx == bsr.derive_vix1m_fixture(frozen, bsr.load_vix_bars(bsr.VIX_BARS),
                                          fx["vix_prior"])
    assert all(s["vix"]["level"] is not None for s in fx["steps"])
```

- [ ] **Step 7: Route the two files and commit**

In `scripts/dev/select_tests.py`, directly below the
`("tests/fixtures/shock_replay_2026_11_05.json", ...)` row (keys match exactly,
so the existing 11-05 row never catches the new name), add:

```python
    # v222 V222-6d: the 2026-11-05 fixture with real one-minute ^VIX, and its bars.
    ("tests/fixtures/shock_replay_2026_11_05_vix1m.json",
     ("tests/scripts/test_build_shock_replay_fixture.py",)),
    ("tests/fixtures/vix_2026_11_05_1m.csv",
     ("tests/scripts/test_build_shock_replay_fixture.py",)),
```

V222-13 later appends its own test to the vix1m row.

```bash
python "$W/scripts/dev/testrun.py" file tests/scripts/test_build_shock_replay_fixture.py
python "$W/scripts/dev/testrun.py" file tests/dev/test_select_tests.py
python "$W/scripts/dev/testrun.py" file tests/market/test_shock_acceptance_a1.py
```

Expected: all pass; the A1 test is unedited and its frozen fixture unchanged.

```bash
git -C "$W" add tests/fixtures/shock_replay_2026_11_05_vix1m.json tests/scripts/test_build_shock_replay_fixture.py scripts/dev/select_tests.py
git -C "$W" commit -m "data(v222): 2026-11-05 fixture with real one-minute ^VIX (in-sample, Stage 3 only)"
git -C "$M" status --short
```

Expected: the main tree shows nothing of this task.

### Task V222-7: Intraday evaluator: readings, A1 first-`SHOCK` replica, index half, lead rule

**Model:** opus — gate arithmetic and a state-machine replica whose parity with `shock.step` decides whether Stage 2 can be trusted; an off-by-one here silently changes a pre-registered verdict.

**Files:**
- Create: `scripts/backtest/shock_index_intraday.py`
- Create: `tests/backtest_scripts/test_shock_index_intraday.py` (suite `backtest-scripts`)
- Modify: `scripts/dev/select_tests.py` (append the new test to the `tests/fixtures/shock_replay/` row)

**Interfaces:**
- Consumes: `swingbot.core.market.shock` (`measure`, `entry_condition`, `step`, `ShockState`, `ShockThresholds`, `ShockSnapshot`, `NameRow`, `VixTape`, `ShockReading`, and the private `_settled` / `_meets`, used so the replica applies the detector's own settle and 1e-9 rules); the 26 A1 fixtures `tests/fixtures/shock_replay/*.json.gz` (read only). Fixture shape (A1 `build_day_fixture`): `source`, `session_date`, `class`, `open_utc`, `close_utc`, `vix_interpolated`, `spy_daily{prev_close, open, close}`, `note`, `steps[{as_of, minutes_since_open, vix{level, chg_pct}, spy, qqq, names[]}]`.
- Produces: `FORCE_VIX_BAR = -1e9`; `SURVIVAL_MIN = 6`; `QUIET_MAX = 0`; `NEAR_MISS_MAX = 2`; `LEAD_MIN_MINUTES = 30`; `LEAD_MIN_SHARE = 0.15`; `LEAD_DAYS_MIN = 5`; `A1_RECORDED = {"calm": 0, "rotation": 1, "hard": 0}`; `readings(fx: dict, th: ShockThresholds = ShockThresholds()) -> list[ShockReading]`; `index_half(reading, k: float, vbar: float) -> bool`; `first_shock(rs, th=ShockThresholds(), k: float = 0.0, vbar: float = FORCE_VIX_BAR) -> datetime | None`; `index_first_fire(rs, k: float, vbar: float = FORCE_VIX_BAR, th=ShockThresholds()) -> datetime | None`; `require_vix(rs, th) -> None`; `drop_ahead(rs, t: datetime | None, spy_daily: dict) -> float | None`; `DayLead` (frozen: `day, t_a1, t_idx, ahead_a1, ahead_idx, leads`); `lead_day(fx, k: float, vbar: float = FORCE_VIX_BAR) -> DayLead`; the test file's `_fx(downs, moves, *, vix=0.0, close=470.0, day=..., thin_at=None, source="alpaca")` and `_lead_fx` helpers, which V222-7b and V222-7c reuse.

Rules this module pins (index § plan-time readings, part header):

- `index_half` is the detector's future `_index_path` with the guard: false when
  `k <= 0`, when `spy_atr_move` is None, or when `vix_chg_pct` misses `vbar`
  (`shock._meets`: None never meets). With `vbar = FORCE_VIX_BAR` any non-None
  `vix_chg_pct` meets, which is "VIX half forced true".
- `first_shock` replays `_from_normal`: a settled reading on which A1's
  `entry_condition` **or** the index half holds adds one to a shared streak, any
  other settled or unsettled reading resets it, an insufficient reading holds
  it, and the second consecutive one is the first `SHOCK`. With `k = 0` it must
  equal the first `SHOCK` label of `shock.step` on every A1 fixture.
- `index_first_fire` is the same streak with the index half alone (survival,
  quiet and near-miss count this).

- [ ] **Step 1: Write the failing tests**

Create `tests/backtest_scripts/test_shock_index_intraday.py`:

```python
"""v222 Stage 2: the intraday evaluator (readings, A1 replica, index half, lead)."""
import gzip
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts" / "backtest") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import shock_index_intraday as sii  # noqa: E402

from swingbot.core.market import shock  # noqa: E402

UTC = timezone.utc
A1_DIR = ROOT / "tests" / "fixtures" / "shock_replay"
OPEN = datetime(2025, 7, 15, 13, 30, tzinfo=UTC)
K = 1.5


def at(minutes: int) -> datetime:
    return OPEN + timedelta(minutes=minutes)


def _name(i: int, down: bool) -> dict:
    return {"ticker": f"N{i:02d}", "sector": f"S{i % 3}", "last": 98.0 if down else 100.0,
            "prev_close": 100.0, "atr14": 2.0, "is_equity": True}


def _spy(move: float) -> dict:
    return {"ticker": "SPY", "sector": None, "last": 500.0 + 5.0 * move, "prev_close": 500.0,
            "atr14": 5.0, "is_equity": False}


def _fx(downs, moves, *, vix=0.0, close=470.0, day="2025-07-15", thin_at=None,
        source="alpaca") -> dict:
    """Synthetic day: step k at open + 15(k+1) min; `downs` of 30 names are 1 ATR down;
    SPY sits `moves[k]` ATR (5.0) from a 500 prior close; `vix` is one chg_pct or a list."""
    steps = []
    for k, (down, move) in enumerate(zip(downs, moves)):
        chg = vix[k] if isinstance(vix, list) else vix
        steps.append({"as_of": at(15 * (k + 1)).isoformat(), "minutes_since_open": 15.0 * (k + 1),
                      "vix": {"level": None if chg is None else 20.0, "chg_pct": chg},
                      "spy": _spy(move), "qqq": None,
                      "names": [_name(i, i < down) for i in range(10 if k == thin_at else 30)]})
    return {"source": source, "session_date": day, "class": "shock",
            "open_utc": OPEN.isoformat(), "close_utc": at(390).isoformat(),
            "vix_interpolated": True,
            "spy_daily": {"prev_close": 500.0, "open": 500.0, "close": close}, "steps": steps}


def _lead_fx(day="2025-07-15", **kw) -> dict:
    """Index half from +15 (fires +30, SPY 492); A1 majority from +105 (fires +120, SPY 472)."""
    return _fx([0] * 6 + [18, 18], [-1.6] * 7 + [-5.6], day=day, **kw)


def test_readings_are_one_per_step_with_the_spy_move():
    rs = sii.readings(_fx([0, 0], [-1.6, -0.4]))
    assert [r.as_of for r in rs] == [at(15), at(30)]
    assert [round(r.spy_atr_move, 6) for r in rs] == [-1.6, -0.4]
    assert sii.readings({"source": "unbuildable", "steps": []}) == []


@pytest.mark.parametrize("k, move, chg, vbar, expected", [
    (0.0, -5.0, 50.0, sii.FORCE_VIX_BAR, False),        # off
    (1.5, -1.5, 0.0, sii.FORCE_VIX_BAR, True),          # boundary meets (1e-9)
    (1.5, -1.49, 0.0, sii.FORCE_VIX_BAR, False),
    (1.5, -2.0, None, sii.FORCE_VIX_BAR, False),        # no VIX never meets
    (1.5, -2.0, 19.99, 20.0, False),
    (1.5, -2.0, 20.0, 20.0, True),
])
def test_index_half(k, move, chg, vbar, expected):
    (r,) = sii.readings(_fx([0], [move], vix=chg))
    assert sii.index_half(r, k, vbar) is expected


def test_the_index_half_is_false_without_a_spy_move():
    fx = _fx([0], [-3.0])
    fx["steps"][0]["spy"] = None
    (r,) = sii.readings(fx)
    assert r.spy_atr_move is None and sii.index_half(r, K, sii.FORCE_VIX_BAR) is False


def test_a1_alone_fires_on_the_second_settled_reading():
    rs = sii.readings(_fx([0, 18, 18, 18], [0.0] * 4))
    assert sii.first_shock(rs) == at(45)
    assert sii.index_first_fire(rs, K) is None


def test_the_index_half_and_a1_share_one_streak():
    rs = sii.readings(_fx([0, 18, 18], [-1.6, 0.0, 0.0]))
    assert sii.first_shock(rs, k=K) == at(30)            # index then A1
    assert sii.first_shock(rs) == at(45)                 # A1 alone
    assert sii.index_first_fire(rs, K) is None           # one index reading only


def test_an_insufficient_reading_holds_the_streak_and_an_unsettled_one_never_counts():
    rs = sii.readings(_fx([0, 0, 0], [-1.6, -1.6, -1.6], thin_at=1))
    assert rs[1].insufficient and sii.index_first_fire(rs, K) == at(45)
    fx = _fx([0, 0], [-1.6, -1.6])
    fx["steps"][0]["minutes_since_open"] = 14.0
    assert sii.index_first_fire(sii.readings(fx), K) is None


def test_require_vix_refuses_a_settled_reading_without_vix():
    sii.require_vix(sii.readings(_fx([0, 0], [0.0, 0.0])), shock.ShockThresholds())
    with pytest.raises(ValueError, match="vix_chg_pct"):
        sii.require_vix(sii.readings(_fx([0, 0], [0.0, 0.0], vix=[0.0, None])),
                        shock.ShockThresholds())


def test_drop_ahead():
    fx = _lead_fx()
    rs = sii.readings(fx)
    assert sii.drop_ahead(rs, at(30), fx["spy_daily"]) == pytest.approx(22 / 30)
    assert sii.drop_ahead(rs, None, fx["spy_daily"]) == 0.0          # A1 never fired
    assert sii.drop_ahead(rs, at(31), fx["spy_daily"]) is None       # no reading then
    up = {"prev_close": 500.0, "open": 500.0, "close": 501.0}
    assert sii.drop_ahead(rs, at(30), up) is None                    # no drop to be ahead of


def test_a_day_leads_when_earlier_by_30_minutes_and_15_points():
    d = sii.lead_day(_lead_fx(), K)
    assert (d.t_a1, d.t_idx) == (at(120), at(30))
    assert d.ahead_idx == pytest.approx(22 / 30) and d.ahead_a1 == pytest.approx(2 / 30)
    assert d.leads is True and d.day == "2025-07-15"


def test_earlier_without_more_drop_ahead_does_not_lead():
    d = sii.lead_day(_fx([0] * 6 + [18, 18], [-1.6] * 8, close=490.0), K)
    assert d.t_idx == at(30) and d.ahead_idx == pytest.approx(d.ahead_a1)
    assert d.leads is False


def test_a1_never_firing_counts_the_close_and_a_zero_share():
    d = sii.lead_day(_fx([0] * 8, [-1.6] * 8), K)
    assert d.t_a1 is None and d.ahead_a1 == 0.0 and d.leads is True
    late = sii.lead_day(_fx([0] * 26, [0.0] * 24 + [-1.6, -1.6]), K)   # fires at the close
    assert late.t_idx == at(390) and late.leads is False


def test_neither_firing_does_not_lead_and_an_off_cell_never_leads():
    assert sii.lead_day(_fx([0] * 8, [0.0] * 8), K).leads is False
    off = sii.lead_day(_lead_fx(), 0.0)
    assert off.t_idx == off.t_a1 and off.leads is False


def test_the_frozen_gate_constants():
    assert (sii.SURVIVAL_MIN, sii.QUIET_MAX, sii.NEAR_MISS_MAX) == (6, 0, 2)
    assert (sii.LEAD_MIN_MINUTES, sii.LEAD_MIN_SHARE, sii.LEAD_DAYS_MIN) == (30, 0.15, 5)
    assert sii.A1_RECORDED == {"calm": 0, "rotation": 1, "hard": 0}
    assert sii.FORCE_VIX_BAR == -1e9


# --- parity with the detector on the 26 frozen A1 fixtures ------------------

A1_PATHS = sorted(A1_DIR.glob("*.json.gz"))


def _read(path: Path) -> dict:
    return json.loads(gzip.decompress(path.read_bytes()))


def _first_by_step(fx: dict):
    th, state = shock.ShockThresholds(), shock.ShockState()
    for r in sii.readings(fx, th):
        state = shock.step(state, r, th)
        if state.label == "SHOCK":
            return r.as_of
    return None


def test_all_26_a1_fixtures_are_there():
    assert len(A1_PATHS) == 26


@pytest.mark.parametrize("path", A1_PATHS, ids=lambda p: p.name[:10])
def test_first_shock_matches_shock_step_on_every_a1_fixture(path):
    fx = _read(path)
    assert sii.first_shock(sii.readings(fx)) == _first_by_step(fx)


@pytest.mark.parametrize("day, expected", [
    ("2024-08-05", datetime(2024, 8, 5, 14, 0, tzinfo=UTC)),
    ("2024-12-18", datetime(2024, 12, 18, 21, 0, tzinfo=UTC)),
    ("2025-04-04", datetime(2025, 4, 4, 14, 30, tzinfo=UTC)),
    ("2025-04-21", None),
])
def test_first_shock_reproduces_the_recorded_a1_timings(day, expected):
    """Spec § Premise check, A1 one-shot acceptance table."""
    assert sii.first_shock(sii.readings(_read(A1_DIR / f"{day}.json.gz"))) == expected
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_shock_index_intraday.py`
Expected: collection error `ModuleNotFoundError: No module named 'shock_index_intraday'`.

- [ ] **Step 3: Implement the module**

Create `scripts/backtest/shock_index_intraday.py`:

```python
"""v222 Stage 2: replay intraday fixtures for the Stage 1 winner cell.

Readings come from `shock.measure` with default thresholds over A1-shaped
replay fixtures. A1's first SHOCK is re-derived here (parity-tested against
`shock.step` on all 26 A1 fixtures) so the index half can be added without
touching shock.py. Every gate runs with the VIX half forced true
(FORCE_VIX_BAR: any non-None vix_chg_pct meets); the ramp-VIX run is
descriptive (spec § Frozen "VIX half in Stage 2").
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "scripts" / "backtest"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from swingbot.core.market import shock  # noqa: E402
from swingbot.core.market.shock import ShockReading, ShockThresholds  # noqa: E402

# Frozen before any Stage 2 data is read (spec § Frozen; copied, never re-chosen).
FORCE_VIX_BAR = -1e9
SURVIVAL_MIN = 6                       # of 8 counted shock days
QUIET_MAX = 0                          # of 4 quiet days
NEAR_MISS_MAX = 2                      # of 4 near-miss days
LEAD_MIN_MINUTES = 30
LEAD_MIN_SHARE = 0.15
LEAD_DAYS_MIN = 5                      # of 8 counted shock days
A1_RECORDED = {"calm": 0, "rotation": 1, "hard": 0}   # A1's recorded false fires
EPS = 1e-9


def _row(d):
    return shock.NameRow(**d) if d else None


def _session_date(fx: dict) -> date:
    if fx.get("session_date"):
        return date.fromisoformat(fx["session_date"])
    return datetime.fromisoformat(fx["steps"][0]["as_of"]).date()


def _snapshot(step: dict, session_date: date) -> shock.ShockSnapshot:
    as_of = datetime.fromisoformat(step["as_of"])
    vix = shock.VixTape(step["vix"]["level"], step["vix"]["chg_pct"], as_of)
    return shock.ShockSnapshot(
        as_of=as_of, session_date=session_date, minutes_since_open=step["minutes_since_open"],
        names=tuple(_row(n) for n in step["names"]), spy=_row(step["spy"]),
        qqq=_row(step["qqq"]), vix=vix)


def readings(fx: dict, th: ShockThresholds = ShockThresholds()) -> list[ShockReading]:
    """One `shock.measure` reading per fixture step (none for an unbuildable day)."""
    if not fx.get("steps"):
        return []
    day, prev, out = _session_date(fx), None, []
    for step in fx["steps"]:
        prev = shock.measure(_snapshot(step, day), prev, th)
        out.append(prev)
    return out


def index_half(reading: ShockReading, k: float, vbar: float) -> bool:
    """SPY at least k ATR below the prior close and VIX up at least vbar %; off at k <= 0."""
    if k <= 0 or reading.spy_atr_move is None:
        return False
    return shock._meets(-reading.spy_atr_move, k) and shock._meets(reading.vix_chg_pct, vbar)


def _first_streak(rs, th: ShockThresholds, fires) -> datetime | None:
    """The reading completing two consecutive settled `fires` readings (as _from_normal)."""
    streak = 0
    for r in rs:
        if r.insufficient:
            continue                   # shock.step holds the state
        if shock._settled(r, th) and fires(r):
            streak += 1
            if streak >= 2:
                return r.as_of
        else:
            streak = 0
    return None


def first_shock(rs, th: ShockThresholds = ShockThresholds(), k: float = 0.0,
                vbar: float = FORCE_VIX_BAR) -> datetime | None:
    """First SHOCK of A1 (k = 0) or of A1 plus the index half (shared streak)."""
    return _first_streak(rs, th, lambda r: shock.entry_condition(r, th) or index_half(r, k, vbar))


def index_first_fire(rs, k: float, vbar: float = FORCE_VIX_BAR,
                     th: ShockThresholds = ShockThresholds()) -> datetime | None:
    """First fire of the index half on its own (two consecutive settled readings)."""
    return _first_streak(rs, th, lambda r: index_half(r, k, vbar))


def require_vix(rs, th: ShockThresholds) -> None:
    """The VIX half can only be forced on a reading that carries vix_chg_pct."""
    for r in rs:
        if not r.insufficient and shock._settled(r, th) and r.vix_chg_pct is None:
            raise ValueError(f"{r.as_of.isoformat()}: settled reading without vix_chg_pct")


def drop_ahead(rs, t: datetime | None, spy_daily: dict) -> float | None:
    """Share of the prior-close-to-close SPY drop still ahead at t (A1's lead_share).

    None when SPY did not close lower or no reading at t carries spy_last; t None
    (never fired) is 0.0."""
    drop = spy_daily["prev_close"] - spy_daily["close"]
    if drop <= 0:
        return None
    if t is None:
        return 0.0
    hit = next((r for r in rs if r.as_of == t), None)
    if hit is None or hit.spy_last is None:
        return None
    return (hit.spy_last - spy_daily["close"]) / drop


@dataclass(frozen=True)
class DayLead:
    day: str
    t_a1: datetime | None
    t_idx: datetime | None
    ahead_a1: float | None
    ahead_idx: float | None
    leads: bool


def _close_utc(fx: dict, rs) -> datetime:
    return datetime.fromisoformat(fx["close_utc"]) if fx.get("close_utc") else rs[-1].as_of


def _leads(t_a1_eff: datetime, t_idx, ahead_a1, ahead_idx) -> bool:
    if t_idx is None or ahead_a1 is None or ahead_idx is None:
        return False
    early = t_idx <= t_a1_eff - timedelta(minutes=LEAD_MIN_MINUTES)
    return early and ahead_idx - ahead_a1 + EPS >= LEAD_MIN_SHARE


def lead_day(fx: dict, k: float, vbar: float = FORCE_VIX_BAR) -> DayLead:
    """A1 alone vs A1 plus the index half on one day (spec § Frozen "Lead over A1")."""
    th = ShockThresholds()
    rs = readings(fx, th)
    day = fx.get("session_date") or ""
    if not rs:
        return DayLead(day, None, None, None, None, False)
    t_a1, t_idx = first_shock(rs, th), first_shock(rs, th, k, vbar)
    spy = fx["spy_daily"]
    ahead_a1 = drop_ahead(rs, t_a1, spy)
    ahead_idx = drop_ahead(rs, t_idx, spy) if t_idx is not None else None
    t_eff = t_a1 or _close_utc(fx, rs)
    return DayLead(day, t_a1, t_idx, ahead_a1, ahead_idx,
                   _leads(t_eff, t_idx, ahead_a1, ahead_idx))
```

- [ ] **Step 4: Route the A1 fixtures to the new test**

In `scripts/dev/select_tests.py`, change the existing row

```python
    ("tests/fixtures/shock_replay/", ("tests/market/test_shock_acceptance_a1.py",)),
```

to

```python
    ("tests/fixtures/shock_replay/", ("tests/market/test_shock_acceptance_a1.py",
                                      "tests/backtest_scripts/test_shock_index_intraday.py")),
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_shock_index_intraday.py
python "$W/scripts/dev/testrun.py" file tests/dev/test_select_tests.py
python "$W/scripts/dev/complexity_gate.py"
```

Expected: all pass, the 26 parity cases included; no function at or above 15.
A parity failure means the replica differs from `shock.step`: fix the replica,
never the fixtures or the A1 test. A recorded-timing failure on an otherwise
passing parity run means the readings differ from the A1 run: stop and report.

- [ ] **Step 6: Commit**

```bash
git -C "$W" add scripts/backtest/shock_index_intraday.py tests/backtest_scripts/test_shock_index_intraday.py
git -C "$W" commit -m "feat(v222): intraday evaluator -- readings, A1 first-SHOCK replica, index half, lead"
git -C "$W" add scripts/dev/select_tests.py
git -C "$W" commit -m "chore(v222): route the A1 replay fixtures to the intraday evaluator test"
```

### Task V222-7b: Stage 2 `evaluate`: survival, quiet, near-miss, A1-days false fires, lead, ramp run

**Model:** opus — applies the five pre-registered gates, slot replacement and the A1 sanity check; a wrong count or a lenient tie flips the verdict.

**Files:**
- Modify: `scripts/backtest/shock_index_intraday.py` (imports, then append)
- Modify: `tests/backtest_scripts/test_shock_index_intraday.py` (append)

**Interfaces:**
- Consumes: V222-7 (`readings`, `index_first_fire`, `first_shock`, `require_vix`, `lead_day`, `DayLead`, the frozen constants, test helpers `_fx`, `_lead_fx`, `K`); `shock_index_screen.N_SHOCK = 8`, `N_QUIET = 4`, `N_NEAR = 4`, `NEG_CLASSES = ("calm", "rotation", "hard")` (V222-4); the day-list shape of `data/v222/stage2_days.json` (V222-4c): `cell, alpaca_from, shock, shock_reserve, quiet, quiet_reserve, near_miss, near_miss_reserve, a1_shock, a1_negative{calm, rotation, hard}`, ISO strings (a reserve list may hold fewer than 3).
- Produces: `GATES = ("survival", "quiet", "near_miss", "a1_false_fires", "lead")`; `fixture_status(fx: dict) -> str` (`"ok"`, `"unbuildable"`, `"synthetic"`, `"no_vix"`); `a1_false_fire(fx: dict, rs, first: datetime | None) -> bool`; `load_fixtures(days: dict, v222_dir: Path, a1_dir: Path) -> dict[str, dict]`; `evaluate(days: dict, fixtures: dict[str, dict]) -> dict` with keys `cell, complete, missing, skipped, picked, survival, quiet, near_miss, a1_false_fires, lead, a1_shock_report, ramp, verdict, frozen`. Gate dicts: `survival`/`lead` `{n, of, min, pass, fired | rows}`, `quiet`/`near_miss` `{n, of, max, pass, fired}`, `a1_false_fires` `{rows: {cls: {a1, with_index, recorded, of}}, pass}`; `lead.rows` and `a1_shock_report` items `{day, t_a1, t_idx, ahead_a1, ahead_idx, leads}` (ISO strings; the A1 rows add `index_fire`, `status`); `ramp` has the five gate dicts computed with the cell's real `index_vix_chg` (descriptive); `verdict` ∈ `"PASS"`, `"NO-LIFT"`, `"INCOMPLETE"`; `frozen` = `[k, v]` on PASS else None. JSON-safe throughout. Raises `ValueError` when A1 alone does not reproduce `A1_RECORDED`.

Slot filling, exhausted slots and fixture reuse follow the part header. The
A1 shock fixtures are reported (`a1_shock_report`), never counted. On an
incomplete run no gate is computed (all gate keys None), so nothing of a
Stage 2 day is scored before every slot has its fixture.

- [ ] **Step 1: Write the failing tests**

Append to `tests/backtest_scripts/test_shock_index_intraday.py`:

```python
# --- V222-7b: evaluate -------------------------------------------------------

SHOCK_DAYS = [f"2020-01-{d:02d}" for d in range(1, 9)]


def _quiet(day):
    return _fx([0] * 4, [0.0] * 4, day=day)


def _spy_only(day):
    return _fx([0] * 4, [-1.6] * 4, day=day)        # index half fires, A1 never


def _no_lead(day):
    return _fx([0] * 6 + [18, 18], [-1.6] * 8, close=490.0, day=day)


def _world(**over):
    """A passing Stage 2: 8 leading shock days, silent quiet/near-miss/A1-negative days."""
    days = {"cell": [K, 20.0], "alpaca_from": "2016-01-04",
            "shock": SHOCK_DAYS, "shock_reserve": ["2020-01-20"],
            "quiet": ["2020-02-01", "2020-02-02", "2020-02-03", "2020-02-04"],
            "quiet_reserve": [["2020-02-11"], [], [], []],
            "near_miss": ["2020-03-01", "2020-03-02", "2020-03-03", "2020-03-04"],
            "near_miss_reserve": ["2020-03-11"], "a1_shock": ["2024-08-05"],
            "a1_negative": {"calm": ["2023-05-01"], "rotation": ["2023-06-01"],
                            "hard": ["2023-07-01"]}}
    fixtures = {d: _lead_fx(day=d) for d in [*SHOCK_DAYS, "2020-01-20", "2024-08-05"]}
    for d in [*days["quiet"], "2020-02-11", *days["near_miss"], "2020-03-11",
              "2023-05-01", "2023-07-01"]:
        fixtures[d] = _quiet(d)
    fixtures["2023-06-01"] = _fx([0, 18, 18, 18], [0.0] * 4, day="2023-06-01")  # A1's 1/4
    fixtures.update(over)                            # day -> replacement fixture
    return days, fixtures


def _failed(r):
    return [g for g in sii.GATES if not r[g]["pass"]]


def test_a_passing_world_freezes_the_cell():
    r = sii.evaluate(*_world())
    assert (r["verdict"], r["frozen"], r["complete"], _failed(r)) == ("PASS", [K, 20.0], True, [])
    assert (r["survival"]["n"], r["quiet"]["n"], r["near_miss"]["n"], r["lead"]["n"]) == (8, 0, 0, 8)
    assert r["a1_false_fires"]["rows"]["rotation"] == {"a1": 1, "with_index": 1, "recorded": 1,
                                                       "of": 1}
    assert r["a1_shock_report"][0]["leads"] is True
    assert r["ramp"]["survival"]["n"] == 0          # VIX 0 % never meets the real 20 % bar
    json.dumps(r)                                    # JSON-safe


def test_five_of_eight_survivors_is_no_lift():
    r = sii.evaluate(*_world(**{d: _quiet(d) for d in SHOCK_DAYS[:3]}))
    assert (r["survival"]["n"], r["lead"]["n"]) == (5, 5)
    assert (r["verdict"], r["frozen"], _failed(r)) == ("NO-LIFT", None, ["survival"])


def test_surviving_without_leading_fails_the_lead_gate_alone():
    r = sii.evaluate(*_world(**{d: _no_lead(d) for d in SHOCK_DAYS[:4]}))
    assert (r["survival"]["n"], r["lead"]["n"], _failed(r)) == (8, 4, ["lead"])


def test_near_miss_allows_two_fires_and_quiet_allows_none():
    two = sii.evaluate(*_world(**{d: _spy_only(d) for d in ["2020-03-01", "2020-03-02"]}))
    assert (two["near_miss"]["n"], two["verdict"]) == (2, "PASS")
    three = sii.evaluate(*_world(**{d: _spy_only(d) for d in
                                    ["2020-03-01", "2020-03-02", "2020-03-03"]}))
    assert _failed(three) == ["near_miss"]
    quiet = sii.evaluate(*_world(**{"2020-02-03": _spy_only("2020-02-03")}))
    assert (quiet["quiet"]["n"], _failed(quiet)) == (1, ["quiet"])


def test_an_added_a1_false_fire_fails_the_a1_days_gate():
    r = sii.evaluate(*_world(**{"2023-05-01": _spy_only("2023-05-01")}))
    assert r["a1_false_fires"]["rows"]["calm"]["with_index"] == 1
    assert _failed(r) == ["a1_false_fires"]


def test_a1_alone_must_reproduce_its_recorded_row():
    with pytest.raises(ValueError, match="recorded"):
        sii.evaluate(*_world(**{"2023-06-01": _quiet("2023-06-01")}))


def test_a_missing_fixture_is_incomplete_and_scores_nothing():
    days, fixtures = _world()
    del fixtures["2020-01-03"]
    r = sii.evaluate(days, fixtures)
    assert (r["verdict"], r["complete"], r["missing"], r["frozen"]) == (
        "INCOMPLETE", False, ["2020-01-03"], None)
    assert all(r[g] is None for g in sii.GATES)


def test_an_unbuildable_day_is_replaced_by_the_next_in_its_ranking():
    unbuilt = {"source": "unbuildable", "session_date": "2020-01-03", "steps": []}
    r = sii.evaluate(*_world(**{"2020-01-03": unbuilt}))
    assert r["skipped"] == [["2020-01-03", "unbuildable"]] and r["verdict"] == "PASS"
    assert "2020-01-20" in r["picked"]["shock"]
    days, fixtures = _world(**{"2020-01-03": unbuilt})
    del fixtures["2020-01-20"]
    assert sii.evaluate(days, fixtures)["missing"] == ["2020-01-20"]


def test_an_exhausted_slot_scores_against_the_cell():
    synth = {"source": "synthetic", "steps": []}
    unbuilt = {"source": "unbuildable", "steps": []}
    r = sii.evaluate(*_world(**{"2020-01-03": unbuilt, "2020-01-20": synth}))
    assert len(r["picked"]["shock"]) == 7 and r["survival"]["of"] == 8
    assert (r["survival"]["n"], r["lead"]["n"]) == (7, 7)
    q = sii.evaluate(*_world(**{"2020-02-02": unbuilt}))      # slot 2 has no reserve
    assert (q["quiet"]["n"], _failed(q)) == (1, ["quiet"])


def test_fixture_status_and_a1_false_fire():
    assert sii.fixture_status(_quiet("2020-01-01")) == "ok"
    assert sii.fixture_status({"source": "unbuildable", "steps": []}) == "unbuildable"
    assert sii.fixture_status({"source": "alpaca", "steps": []}) == "unbuildable"
    assert sii.fixture_status({"source": "synthetic", "steps": [{}]}) == "synthetic"
    assert sii.fixture_status(_fx([0, 0], [0.0, 0.0], vix=[0.0, None])) == "no_vix"
    thin = _fx([0, 0], [0.0, 0.0], thin_at=0)
    rs = sii.readings(thin)
    assert sii.a1_false_fire(thin, rs, None) is True
    assert sii.a1_false_fire(_quiet("2020-01-01"), sii.readings(_quiet("2020-01-01")), None) is False


def test_load_fixtures_reuses_an_a1_fixture_first(tmp_path):
    a1, v222 = tmp_path / "a1", tmp_path / "v222"
    a1.mkdir(), v222.mkdir()
    days, _ = _world()
    for base, day, src in [(a1, "2020-02-01", "a1"), (v222, "2020-02-01", "v222"),
                           (v222, "2020-01-01", "v222")]:
        (base / f"{day}.json.gz").write_bytes(gzip.compress(json.dumps({"note": src}).encode()))
    got = sii.load_fixtures(days, v222, a1)
    assert got == {"2020-01-01": {"note": "v222"}, "2020-02-01": {"note": "a1"}}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_shock_index_intraday.py`
Expected: the new tests FAIL with `AttributeError: module 'shock_index_intraday' has no attribute 'evaluate'` (or `GATES`, `fixture_status`, `load_fixtures`); the V222-7 tests pass.

- [ ] **Step 3: Implement**

In `scripts/backtest/shock_index_intraday.py` add `import gzip` and `import json` to
the stdlib imports, and below the `shock` imports:

```python
from shock_index_screen import N_NEAR, N_QUIET, N_SHOCK, NEG_CLASSES  # noqa: E402
```

Append:

```python
GATES = ("survival", "quiet", "near_miss", "a1_false_fires", "lead")


def fixture_status(fx: dict) -> str:
    """ok, or why a fixture cannot be gated (it is then replaced from its ranking)."""
    if fx.get("source") == "synthetic":
        return "synthetic"
    if fx.get("source") != "alpaca" or not fx.get("steps"):
        return "unbuildable"
    try:
        require_vix(readings(fx), ShockThresholds())
    except ValueError:
        return "no_vix"
    return "ok"


def a1_false_fire(fx: dict, rs, first: datetime | None) -> bool:
    """A1's is_false_fire: unbuildable, any insufficient reading, or a first SHOCK."""
    unbuildable = fx.get("source") == "unbuildable" or not fx.get("steps")
    return unbuildable or any(r.insufficient for r in rs) or first is not None


def _listed(days: dict) -> list[str]:
    groups = [days["shock"], days["shock_reserve"], days["quiet"], *days["quiet_reserve"],
              days["near_miss"], days["near_miss_reserve"], days["a1_shock"],
              *days["a1_negative"].values()]
    return list(dict.fromkeys(iso for group in groups for iso in group))


def load_fixtures(days: dict, v222_dir: Path, a1_dir: Path) -> dict[str, dict]:
    """Every listed day's fixture on disk; an A1 fixture is reused as is (A1 dir first)."""
    out = {}
    for iso in _listed(days):
        for base in (Path(a1_dir), Path(v222_dir)):
            path = base / f"{iso}.json.gz"
            if path.exists():
                out[iso] = json.loads(gzip.decompress(path.read_bytes()))
                break
    return out


def _fill(candidates: list[str], fixtures: dict, n: int):
    """First n `ok` candidates in ranking order -> (picked, missing iso | None, skipped)."""
    picked, skipped = [], []
    for iso in candidates:
        if len(picked) == n:
            break
        if iso not in fixtures:
            return picked, iso, skipped
        status = fixture_status(fixtures[iso])
        if status == "ok":
            picked.append(iso)
        else:
            skipped.append([iso, status])
    return picked, None, skipped


def _slots(days: dict, fixtures: dict) -> dict:
    out = {"shock": _fill([*days["shock"], *days["shock_reserve"]], fixtures, N_SHOCK),
           "near_miss": _fill([*days["near_miss"], *days["near_miss_reserve"]], fixtures, N_NEAR)}
    for i, (pick, reserve) in enumerate(zip(days["quiet"], days["quiet_reserve"]), 1):
        out[f"quiet{i}"] = _fill([pick, *reserve], fixtures, 1)
    return out


def _iso(t: datetime | None) -> str | None:
    return t.isoformat() if t else None


def _lead_row(d: DayLead) -> dict:
    return {"day": d.day, "t_a1": _iso(d.t_a1), "t_idx": _iso(d.t_idx),
            "ahead_a1": d.ahead_a1, "ahead_idx": d.ahead_idx, "leads": d.leads}


def _fires(isos, fixtures: dict, k: float, vbar: float) -> list[str]:
    return [iso for iso in isos if index_first_fire(readings(fixtures[iso]), k, vbar)]


def _a1_negatives(days: dict, fixtures: dict, k: float, vbar: float) -> dict:
    rows = {}
    for cls in NEG_CLASSES:
        a1 = with_index = 0
        for iso in days["a1_negative"][cls]:
            fx = fixtures[iso]
            rs = readings(fx)
            a1 += a1_false_fire(fx, rs, first_shock(rs))
            with_index += a1_false_fire(fx, rs, first_shock(rs, k=k, vbar=vbar))
        rows[cls] = {"a1": a1, "with_index": with_index, "recorded": A1_RECORDED[cls],
                     "of": len(days["a1_negative"][cls])}
    return rows


def _gates(slots: dict, fixtures: dict, days: dict, k: float, vbar: float) -> dict:
    shock_days = slots["shock"][0]
    quiet = [slots[f"quiet{i}"][0] for i in range(1, N_QUIET + 1)]
    near_days = slots["near_miss"][0]
    survived = _fires(shock_days, fixtures, k, vbar)
    quiet_fired = _fires([iso for slot in quiet for iso in slot], fixtures, k, vbar)
    near_fired = _fires(near_days, fixtures, k, vbar)
    n_quiet = len(quiet_fired) + sum(1 for slot in quiet if not slot)   # exhausted = fired
    n_near = len(near_fired) + N_NEAR - len(near_days)
    leads = [_lead_row(lead_day(fixtures[iso], k, vbar)) for iso in shock_days]
    n_lead = sum(row["leads"] for row in leads)
    negatives = _a1_negatives(days, fixtures, k, vbar)
    return {
        "survival": {"n": len(survived), "of": N_SHOCK, "min": SURVIVAL_MIN, "fired": survived,
                     "pass": len(survived) >= SURVIVAL_MIN},
        "quiet": {"n": n_quiet, "of": N_QUIET, "max": QUIET_MAX, "fired": quiet_fired,
                  "pass": n_quiet <= QUIET_MAX},
        "near_miss": {"n": n_near, "of": N_NEAR, "max": NEAR_MISS_MAX, "fired": near_fired,
                      "pass": n_near <= NEAR_MISS_MAX},
        "a1_false_fires": {"rows": negatives, "pass": all(
            r["with_index"] <= r["recorded"] for r in negatives.values())},
        "lead": {"n": n_lead, "of": N_SHOCK, "min": LEAD_DAYS_MIN, "rows": leads,
                 "pass": n_lead >= LEAD_DAYS_MIN},
    }


def _a1_shock_report(days: dict, fixtures: dict, k: float) -> list[dict]:
    rows = []
    for iso in days["a1_shock"]:
        fx = fixtures[iso]
        row = _lead_row(lead_day(fx, k))
        row.update(index_fire=_iso(index_first_fire(readings(fx), k)),
                   status=fixture_status(fx))
        rows.append(row)
    return rows


def _check_a1(gates: dict) -> None:
    alone = {cls: row["a1"] for cls, row in gates["a1_false_fires"]["rows"].items()}
    if alone != A1_RECORDED:
        raise ValueError(f"A1 alone gives {alone}, not the recorded {A1_RECORDED}")


def evaluate(days: dict, fixtures: dict[str, dict]) -> dict:
    """The five Stage 2 gates for the winner cell, VIX half forced true; ramp descriptive."""
    k, v = (float(x) for x in days["cell"])
    slots = _slots(days, fixtures)
    a1_isos = [*days["a1_shock"], *(d for ds in days["a1_negative"].values() for d in ds)]
    missing = [s[1] for s in slots.values() if s[1]] + [d for d in a1_isos if d not in fixtures]
    base = {"cell": [k, v], "missing": missing, "picked": {g: s[0] for g, s in slots.items()},
            "skipped": [x for s in slots.values() for x in s[2]]}
    if missing:
        return {**base, "complete": False, **dict.fromkeys(GATES), "a1_shock_report": None,
                "ramp": None, "verdict": "INCOMPLETE", "frozen": None}
    gates = _gates(slots, fixtures, days, k, FORCE_VIX_BAR)
    _check_a1(gates)
    passed = all(gates[g]["pass"] for g in GATES)
    return {**base, "complete": True, **gates,
            "a1_shock_report": _a1_shock_report(days, fixtures, k),
            "ramp": _gates(slots, fixtures, days, k, v),
            "verdict": "PASS" if passed else "NO-LIFT", "frozen": [k, v] if passed else None}
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_shock_index_intraday.py
python "$W/scripts/dev/complexity_gate.py"
```

Expected: all pass; no function at or above 15 (`_gates` is straight-line).

- [ ] **Step 5: Commit**

```bash
git -C "$W" add scripts/backtest/shock_index_intraday.py tests/backtest_scripts/test_shock_index_intraday.py
git -C "$W" commit -m "feat(v222): Stage 2 evaluate -- five gates, slot replacement, A1 check, ramp run"
```


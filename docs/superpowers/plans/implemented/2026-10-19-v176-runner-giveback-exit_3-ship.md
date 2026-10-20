# v176 Runner give-back exit. Part 3: ship tooling, full suite, merge, deploy, measurement, close-out (V176-7..V176-14)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task V176-8:" -A 420 docs/superpowers/plans/2026-10-19-v176-runner-giveback-exit_3-ship.md`.

**Spec:** [`docs/superpowers/specs/2026-10-19-v176-runner-giveback-exit-design.md`](../specs/2026-10-19-v176-runner-giveback-exit-design.md) (this part: § Open trades at deploy, § Measurement, § Live book)
**Index:** [`2026-10-19-v176-runner-giveback-exit_0-index.md`](2026-10-19-v176-runner-giveback-exit_0-index.md) carries the header (`Bump`, `Edge`, `Screen`), `## Global Constraints`, `## Parallelisation` and the task ledger. Every task below implicitly includes the Global Constraints; the ledger's names, signatures and paths are final.

**Paths.** `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree), `$WT` = `$R/.claude/worktrees/2026-10-19-v176-runner-giveback-exit` (branch of the same name, created in V176-1). Never `cd`; use `git -C <tree>` and absolute paths. V176-7..V176-10 run in `$WT` (paths below relative to it); V176-11..V176-14 run in `$R` on `main`. `$SCRATCH` = the session scratchpad directory.

**Controller decisions applied here (2026-10-19):**
- The one full suite is V176-10, in the worktree, before the merge. No full suite after the merge.
- The version bump (bot minor) is done at the merge (V176-11), so the deployed image carries it; `/close-out` in V176-14 skips its bump step (Steps 3-4) because it is already in the log.
- The deploy gate (V176-12) is read-only on production, goes through `scripts/ops/ssh-hetzner.sh` only, and its table is shown to the partner and committed **before** `git push origin main` (the push is the deploy).
- Measurement verdict rule (V176-13), descriptive and reported to the partner, **never** flipping the flag: `PASS` if the paired ΔExpR ticker-cluster bootstrap interval's low end > 0, `FAIL` if its high end < 0, `NO-LIFT` if it contains 0.

**Consumed from parts 1-2 (ledger names only):**
- `swingbot/core/planning/exit_sim.py` (V176-1): `GIVEBACK_PCT_BOUNDS = (0.5, 49.0)`; `giveback_stop(extreme, pct, direction) -> float`; `runner_giveback_pct() -> float`; `giveback_level(extreme, direction) -> float | None`; `tighter_stop(stop, other, is_bull) -> float`; `runner_stop_source(stop, floor, giveback) -> str`; existing `runner_floor(entry, tp1)`, `chandelier_stop(extreme, atr, mult, direction)`.
- `swingbot/config.py` (V176-1): `RUNNER_GIVEBACK_ENABLED: bool` (default `True`), `RUNNER_GIVEBACK_PCT: float` (default `5.0`).
- `exit_sim` (V176-5): `GIVEBACK_EXTREME_BASIS: str = "close"` (`"close"` | `"high_low"`, read at call time by `_giveback_extreme`, so a worker sets `exit_sim.GIVEBACK_EXTREME_BASIS = basis` and both walks follow); `ExitResult.runner_stop_source: str | None` (`"floor"`/`"trail"`/`"giveback"` when the runner closed on its stop, else `None`).
- Live runner leg (V176-2): `"stop_source"` always on a runner stop close; when `"giveback"` also `"giveback_pct"`, `"giveback_extreme"`, `"giveback_stop"`.

**Existing symbols used (verified with `git grep -n` on 2026-10-19):** `swingbot/core/analytics/expectancy_attribution.py:110 net_r(entry, stop_loss, direction, legs)` (friction-net R, slippage both fills + `commission_r()`); `swingbot/core/backtesting/acceptance.py:182 BOOTSTRAP_RESAMPLES`, `:280 bootstrap_delta(...) -> BootstrapResult(point, lo, hi, p, n_resamples, seed)`, `:372 mde_paired(...)`; `swingbot/core/backtesting/arms/strategy_engine.py:230 StrategyEngine.iter_trades(ticker, df, strategy, horizon_key, signal_window, params)` yielding `(date, plan, result)`; `swingbot/core/backtesting/backtest_scenarios.py:255 replay_scenarios(...)`, `_resolve_replay_workers`; `swingbot/core/backtesting/arms/windows.py ALL_HORIZONS`; `swingbot/core/marketdata/training_data.py select/load_daily/available_tickers/write_provenance`; `swingbot/core/planning/plan_store.py:61 PlanStore.open_plans()`, `:43 records()`; `swingbot/core/marketdata/data.py:620 get_current_price(ticker, ..., allow_stale=True)`, `get_daily_data`; `swingbot/core/market/indicators.py:62 atr(df, period=14)`; `swingbot/core/backtesting/instrument/fills.py:33 gap_stop_fill`; `scripts/reports/preregistration_ledger.py` (CLI); `scripts/dev/build_version_matrix.py`.

# Phase 5: Ship tooling (in the worktree)

### Task V176-7: Deploy-gate scripts (prod read-only rows + local gate table)

**Model:** sonnet — two small new scripts with pure arithmetic over V176-1's helpers; nothing touches the live engine.

**Files:**
- Create: `scripts/ops/partial_runner_rows.py`
- Create: `scripts/ops/giveback_deploy_gate.py`
- Create: `tests/scripts/test_giveback_deploy_gate.py` (suite `tooling` = `tests/scripts/`; no manifest edit)

**Interfaces:**
- Consumes (V176-1, `swingbot.core.planning.exit_sim`): `giveback_stop(extreme, pct, direction)`, `tighter_stop(stop, other, is_bull)`, existing `runner_floor(entry, tp1)`.
- Produces (V176-12 runs them):
  - `scripts/ops/partial_runner_rows.py` — piped to `docker compose exec -T bot python -` on the **old** (pre-v176) image, so it imports nothing v176 adds: only `PlanStore().open_plans()` and `get_current_price`. Writes nothing. Prints one JSON line, the list of `{plan_id, ticker, direction, entry_price, stop_loss, tp1, working_stop, runner_high_close, last_price}` for `PARTIAL` plans. Testable core: `partial_rows(plans, price_fn) -> list[dict]`.
  - `scripts/ops/giveback_deploy_gate.py` — `load_rows(text: str) -> list[dict]` (the last line of `text` that starts with `[`, so container log noise above it is ignored); `gate_row(row: dict, pct: float) -> dict` (adds `floor`, `current_stop`, `extreme_used`, `giveback_stop`, `new_stop`, `moves`, `past`); `render_table(rows: list[dict]) -> str` (markdown); `main(argv: list[str] | None = None) -> int` (`--rows <path>`, `--pct 5.0`).

`gate_row` mirrors the first post-deploy tick of V176-2: `_track_extreme` first folds the tick into `E` (so `extreme_used` = the more favourable of the stored `runner_high_close` and `last_price`, or `last_price` when `E` is None), then `_apply_giveback` tightens the current stop (`working_stop`, else the runner floor). `past` is whether that same tick is already at or beyond `new_stop`, meaning the runner closes on its first tick. The chandelier may tighten further on that tick; the table reports the give-back's move only, which is the move the partner's broker stops do not follow.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_giveback_deploy_gate.py`:

```python
"""v176 deploy gate: the per-plan old/new stop table shown before the push.

RKLB-like short (spec § Open trades at deploy): entry 63.0 and TP1 57.165 put
the runner floor at 59.11 (the live working stop), E = 49.94, last 52.30.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ops"))

import giveback_deploy_gate as gate  # noqa: E402
import partial_runner_rows as prr  # noqa: E402

RKLB = {"plan_id": "47f7fd16-38d5-49d4-a917-d0fdb3376c85", "ticker": "RKLB",
        "direction": "bearish", "entry_price": 63.0, "stop_loss": 66.0, "tp1": 57.165,
        "working_stop": 59.11, "runner_high_close": 49.94, "last_price": 52.30}


def test_rklb_moves_to_its_giveback_and_stays_open():
    out = gate.gate_row(dict(RKLB), 5.0)
    assert out["floor"] == pytest.approx(59.11)
    assert out["current_stop"] == pytest.approx(59.11)
    assert out["extreme_used"] == pytest.approx(49.94)
    assert out["giveback_stop"] == pytest.approx(52.437)
    assert out["new_stop"] == pytest.approx(52.437)
    assert out["moves"] is True
    assert out["past"] is False                    # 52.30 < 52.437: no close on tick 1


def test_a_last_price_past_the_new_stop_closes_on_the_first_tick():
    out = gate.gate_row(dict(RKLB, last_price=52.50), 5.0)
    assert out["past"] is True


def test_a_new_extreme_on_the_first_tick_is_folded_in_first():
    out = gate.gate_row(dict(RKLB, last_price=48.0), 5.0)
    assert out["extreme_used"] == pytest.approx(48.0)
    assert out["new_stop"] == pytest.approx(50.4)
    assert out["past"] is False


def test_no_stored_extreme_takes_the_last_price_as_e():
    out = gate.gate_row(dict(RKLB, runner_high_close=None, last_price=55.0), 5.0)
    assert out["extreme_used"] == pytest.approx(55.0)
    assert out["new_stop"] == pytest.approx(57.75)
    assert out["past"] is False


def test_a_looser_giveback_never_moves_the_stop_long():
    row = {"plan_id": "p2", "ticker": "AAPL", "direction": "bullish", "entry_price": 100.0,
           "stop_loss": 95.0, "tp1": 110.0, "working_stop": None,
           "runner_high_close": 111.0, "last_price": 110.0}
    out = gate.gate_row(row, 5.0)
    assert out["current_stop"] == pytest.approx(100.0 + 20.0 / 3.0)
    assert out["giveback_stop"] == pytest.approx(105.45)
    assert out["new_stop"] == pytest.approx(out["current_stop"])
    assert out["moves"] is False


def test_unknown_last_price_leaves_past_unknown():
    out = gate.gate_row(dict(RKLB, last_price=None), 5.0)
    assert out["extreme_used"] == pytest.approx(49.94)
    assert out["past"] is None


def test_render_table_has_one_row_per_plan_and_names_the_columns():
    table = gate.render_table([gate.gate_row(dict(RKLB), 5.0)])
    lines = table.splitlines()
    assert lines[0].startswith("| plan | ticker | dir |")
    assert len(lines) == 3
    assert "47f7fd16" in lines[2] and "52.44" in lines[2] and "59.11" in lines[2]
    assert lines[2].rstrip().endswith("| no |")


def test_render_table_with_no_partial_plans_says_so():
    assert gate.render_table([]) == "No open PARTIAL plans: the give-back moves no stop at deploy."


def test_load_rows_ignores_log_noise_above_the_json_line():
    text = "INFO config loaded\n" + json.dumps([RKLB]) + "\n"
    assert gate.load_rows(text) == [RKLB]


def test_main_prints_the_table(tmp_path, capsys):
    path = tmp_path / "rows.txt"
    path.write_text(json.dumps([RKLB]) + "\n", encoding="utf-8")
    assert gate.main(["--rows", str(path), "--pct", "5.0"]) == 0
    assert "RKLB" in capsys.readouterr().out


def test_partial_rows_keeps_partial_plans_only_and_reads_the_price():
    def plan(pid, status, **kw):
        base = dict(plan_id=pid, ticker="RKLB", direction="bearish", entry_price=63.0,
                    stop_loss=66.0, tp1=57.165, working_stop=59.11,
                    runner_high_close=49.94, status=status)
        base.update(kw)
        return SimpleNamespace(**base)
    plans = [plan("a", "PARTIAL"), plan("b", "ACTIVE"), plan("c", "PENDING")]
    rows = prr.partial_rows(plans, lambda ticker: 52.30)
    assert [r["plan_id"] for r in rows] == ["a"]
    assert rows[0]["last_price"] == 52.30
    assert set(rows[0]) == {"plan_id", "ticker", "direction", "entry_price", "stop_loss",
                            "tp1", "working_stop", "runner_high_close", "last_price"}


def test_partial_rows_survives_a_price_failure():
    plans = [SimpleNamespace(plan_id="a", ticker="RKLB", direction="bearish", entry_price=63.0,
                             stop_loss=66.0, tp1=57.165, working_stop=None,
                             runner_high_close=None, status="PARTIAL")]

    def boom(ticker):
        raise RuntimeError("feed down")
    assert prr.partial_rows(plans, boom)[0]["last_price"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/scripts/test_giveback_deploy_gate.py`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'giveback_deploy_gate'`.

- [ ] **Step 3: Write `scripts/ops/partial_runner_rows.py`**

```python
#!/usr/bin/env python3
"""v176 deploy gate, production half: list every open PARTIAL plan as JSON.

READ-ONLY. Piped into the running (pre-v176) bot container:

    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" \
        < scripts/ops/partial_runner_rows.py > "$SCRATCH/v176-partial-rows.txt"

It imports nothing v176 adds (the old image has none of it), writes no row
and moves no stop. The last stdout line is the JSON list that
scripts/ops/giveback_deploy_gate.py reads.
"""
from __future__ import annotations

import json

FIELDS = ("plan_id", "ticker", "direction", "entry_price", "stop_loss", "tp1",
          "working_stop", "runner_high_close")


def _price(price_fn, ticker):
    try:
        value = price_fn(ticker)
    except Exception:          # a dead feed leaves the price unknown, never stops the list
        return None
    return float(value) if value is not None else None


def partial_rows(plans, price_fn) -> list[dict]:
    """One dict per PARTIAL plan, in the store's order, with its last price."""
    rows = []
    for plan in plans:
        if str(plan.status) != "PARTIAL":
            continue
        row = {name: getattr(plan, name) for name in FIELDS}
        row["plan_id"] = str(row["plan_id"])
        row["last_price"] = _price(price_fn, plan.ticker)
        rows.append(row)
    return rows


def main() -> int:
    from swingbot.core.marketdata.data import get_current_price
    from swingbot.core.planning.plan_store import PlanStore
    plans = PlanStore().open_plans()
    rows = partial_rows(plans, lambda t: get_current_price(t, allow_stale=False))
    print(json.dumps(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`str(plan.status)`: `PlanStatus` members are plain strings (`plan_types.py:6-11`), so `"PARTIAL"` compares directly.

- [ ] **Step 4: Write `scripts/ops/giveback_deploy_gate.py`**

```python
#!/usr/bin/env python3
"""v176 deploy gate, local half: each open runner's stop before and after the
first post-deploy tick, from the rows scripts/ops/partial_runner_rows.py
printed on production.

    python scripts/ops/giveback_deploy_gate.py --rows "$SCRATCH/v176-partial-rows.txt" --pct 5.0

Mirrors PlanManager's first tick (V176-2): the tick is folded into the
extreme first, then the give-back tightens the current stop (working_stop,
else the runner floor). The chandelier may tighten further on the same
tick; this table shows the give-back's move only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot.core.planning.exit_sim import giveback_stop, runner_floor, tighter_stop  # noqa: E402

COLUMNS = ("plan", "ticker", "dir", "entry", "TP1", "floor", "current stop", "E stored",
           "E used", "give-back stop", "new stop", "last", "moves", "closes on tick 1")


def load_rows(text: str) -> list[dict]:
    """The JSON list on the last line that starts with '[' (log noise above is ignored)."""
    lines = [line for line in text.splitlines() if line.lstrip().startswith("[")]
    if not lines:
        raise ValueError("no JSON row list in the rows output")
    return json.loads(lines[-1])


def _extreme_used(stored, last, is_bull):
    if last is None:
        return stored
    if stored is None:
        return float(last)
    return max(stored, last) if is_bull else min(stored, last)


def _past(last, stop, is_bull):
    if last is None:
        return None
    return bool(last <= stop) if is_bull else bool(last >= stop)


def gate_row(row: dict, pct: float) -> dict:
    """``row`` plus floor, current_stop, extreme_used, giveback_stop, new_stop, moves, past."""
    is_bull = row["direction"] == "bullish"
    floor = runner_floor(float(row["entry_price"]), float(row["tp1"]))
    current = float(row["working_stop"]) if row["working_stop"] is not None else floor
    extreme = _extreme_used(row["runner_high_close"], row["last_price"], is_bull)
    giveback = giveback_stop(float(extreme), pct, row["direction"]) if extreme is not None else None
    new_stop = tighter_stop(current, giveback, is_bull)
    return {**row, "floor": floor, "current_stop": current, "extreme_used": extreme,
            "giveback_stop": giveback, "new_stop": new_stop,
            "moves": new_stop != current, "past": _past(row["last_price"], new_stop, is_bull)}


def _fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return f"{value:.2f}"


def _cells(r: dict) -> list[str]:
    return [str(r["plan_id"])[:8], r["ticker"], "long" if r["direction"] == "bullish" else "short",
            *(_fmt(r[k]) for k in ("entry_price", "tp1", "floor", "current_stop",
                                   "runner_high_close", "extreme_used", "giveback_stop",
                                   "new_stop", "last_price", "moves")),
            "unknown" if r["past"] is None else _fmt(r["past"])]


def render_table(rows: list[dict]) -> str:
    if not rows:
        return "No open PARTIAL plans: the give-back moves no stop at deploy."
    out = ["| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    out += ["| " + " | ".join(_cells(r)) + " |" for r in rows]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rows", required=True, type=Path)
    parser.add_argument("--pct", type=float, default=5.0)
    args = parser.parse_args(argv)
    rows = load_rows(args.rows.read_text(encoding="utf-8"))
    print(render_table([gate_row(row, args.pct) for row in rows]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Check against `test_render_table_has_one_row_per_plan_and_names_the_columns`: the header starts `| plan | ticker | dir |`, the RKLB row ends with `| no |` (`past` is False) and `_fmt(52.437)` is `52.44`.

- [ ] **Step 5: Run test to verify it passes**

Run: `python $WT/scripts/dev/testrun.py file tests/scripts/test_giveback_deploy_gate.py`
Expected: PASS, 12 passed, 0 failed.

- [ ] **Step 6: Complexity and syntax**

Run: `python $WT/scripts/dev/complexity_gate.py` (expect no new offender; every function above is C <= 5) and `python -m py_compile $WT/scripts/ops/partial_runner_rows.py $WT/scripts/ops/giveback_deploy_gate.py`.

- [ ] **Step 7: Commit**

```bash
git -C $WT add scripts/ops/partial_runner_rows.py scripts/ops/giveback_deploy_gate.py tests/scripts/test_giveback_deploy_gate.py
git -C $WT commit -m "feat(v176): deploy-gate scripts for open runners' old and new stops

partial_runner_rows.py runs read-only in the pre-v176 bot container and
prints every PARTIAL plan as JSON; giveback_deploy_gate.py folds the first
tick into E and tables each runner's current stop, give-back stop, new stop
and whether tick 1 closes it.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V176-8: TRAIN paired measurement script

**Model:** opus — statistical instrument (paired arms on the same entries, ticker-cluster bootstrap, MDE, frozen window, one-look refusal) where a silent pairing or lookahead error fakes a result.

**Files:**
- Create: `scripts/backtest/measure_runner_giveback.py`
- Create: `tests/backtest_scripts/test_measure_runner_giveback.py` (suite `backtest-scripts` = `tests/backtest_scripts/`; no manifest edit)

**Interfaces:**
- Consumes: V176-1 `config.RUNNER_GIVEBACK_ENABLED` / `config.RUNNER_GIVEBACK_PCT` (set per arm, restored after); V176-5 `exit_sim.GIVEBACK_EXTREME_BASIS` (set once per worker) and `ExitResult.runner_stop_source`; existing `simulate_exit`, `net_r`, `bootstrap_delta`, `mde_paired`, `BOOTSTRAP_RESAMPLES`, `StrategyEngine.iter_trades`, `replay_scenarios`, `ALL_HORIZONS`, `training_data`.
- Produces (V176-13 runs it):
  - CLI `python scripts/backtest/measure_runner_giveback.py --out-dir docs/superpowers/results/v176 [--basis close|high_low] [--tickers T ...] [--workers N] [--resamples N]`; writes `<out-dir>/train-<basis>.json` = `{"frozen": {...}, "summary": {...}}` plus its provenance sidecar; refuses to overwrite it (one look).
  - `paired_trades(ticker: str, df, *, basis: str) -> list[dict]` — one row per TRAIN entry decided in both arms.
  - `summarise(rows: list[dict], *, n_resamples: int = BOOTSTRAP_RESAMPLES) -> dict` — `summary["primary"]` = `{n, exp_r_off, exp_r_on, delta_exp_r, ci_lo, ci_hi, p_le_zero, mde_paired, n_resamples, verdict}`; descriptive blocks `per_horizon`, `runner`, `giveback_exits`, `book`, `changed`, `cells_looked_at`.
  - `verdict(lo: float | None, hi: float | None) -> str` — `PASS` if `lo > 0`, `FAIL` if `hi < 0`, `NO-LIFT` otherwise, `UNMEASURABLE` without an interval.

**Design (frozen before TRAIN is read; spec § Measurement):**
- Entries come from one **flag-off** pass (`_entries`), so earlier give-back exits cannot add entries through `iter_trades`' `open_until`; every entry is then simulated twice through the same `simulate_exit(scale_out=True)` call, off and on at 5%. Same entries, frictions in both arms (`net_r`: slippage on both fills, `commission_r()`); the run refuses zero frictions.
- Every frame is cut at `TRAIN[1]` before anything runs, so no VALIDATION bar is run or read. A late-2023 trade times out on the last TRAIN bar in **both** arms (a stated difference from v123, which walked exits into 2024).
- Data: the 75-ticker `yfinance` backtest cache (`training_data.select("yfinance")`), v123's source.
- Primary reading: pooled paired per-trade ΔR (on minus off, net), which with identical first legs is the runner-leg ΔR and equals ΔExpR; ticker-cluster `bootstrap_delta` interval, `mde_paired` at the observed N. Everything else is descriptive and counted in `cells_looked_at` (2 per horizon + 8 pooled).
- Runner-only context, from the **off** arm's window `[tp1_index, off exit)`: MFE (fixed denominator for capture), best close, and `gb_r = 0.05 × best_close / risk` (5% of price in R). On-arm give-back exits get `days`, `shakeout` (a close beyond the pre-exit best close within 10 bars) and `gap_worse_r` (exit bar opened past the level: the v1 walk fills at the level, a live/broker stop would fill at the open; the R cost of that, × runner fraction; 0.0 when not gapped).
- Win rate is not reported.

- [ ] **Step 1: Write the failing test**

Create `tests/backtest_scripts/test_measure_runner_giveback.py`:

```python
"""v176 TRAIN paired measurement: pairing, frictions, the TRAIN cut, the verdict rule.

Frame: part 2's run-up-and-reversal (tests/planning/test_exit_sim_giveback.py),
dated in TRAIN. Flag off, the runner rides to the floor 106.667 on bar 4; on,
bar 2's close 120 sets a 114 give-back that bar 3 hits.
"""
import json
import sys
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.planning import exit_sim
from tests.helpers import make_ohlcv
from tests.planning.test_exit_sim_single import _plan

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import measure_runner_giveback as mrg  # noqa: E402

FLOOR = 100.0 + (2.0 / 3.0) * 10.0
BARS = [100.0, (100.0, 111.0, 99.5, 110.5), (110.5, 121.0, 110.0, 120.0),
        (120.0, 120.5, 113.0, 113.5), (113.5, 114.0, 106.0, 106.5)]


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", True)
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_PCT", 5.0)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    monkeypatch.setattr(config, "ADAPTIVE_RUNNER_TRAIL_ENABLED", False)
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False)
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 5.0)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0)
    monkeypatch.setattr(config, "COMMISSION_RISK_BASIS", 100.0)
    monkeypatch.setattr(exit_sim, "GIVEBACK_EXTREME_BASIS", "close")   # restored after paired_trades sets it


def _one_entry(monkeypatch, seen=None):
    plan = _plan(direction="bullish", stop_loss=95.0, tp1=110.0, tp2=None, trail_atr_mult=50.0)

    def fake_entries(ticker, df):
        if seen is not None:
            seen.append(df)
        return [("strategy", "2w", 0, plan)]
    monkeypatch.setattr(mrg, "_entries", fake_entries)


def test_the_same_entry_is_simulated_off_and_on_with_frictions(monkeypatch):
    _one_entry(monkeypatch)
    [row] = mrg.paired_trades("AAA", make_ohlcv(BARS, start="2021-01-04"), basis="close")
    assert row["off"]["reason"] == "runner_be" and row["off"]["stop_source"] == "floor"
    assert row["on"]["reason"] == "runner_trail" and row["on"]["stop_source"] == "giveback"
    assert row["off"]["exit_price"] == pytest.approx(FLOOR)
    assert row["on"]["exit_price"] == pytest.approx(114.0)
    assert row["changed"] is True
    # net of 5 bps per fill: the entry fill 100.05 re-bases risk to 5.05; leg 1 cancels
    assert row["on"]["r_net"] - row["off"]["r_net"] == pytest.approx(
        0.5 * (114.0 - FLOOR) * 0.9995 / 5.05)
    assert config.RUNNER_GIVEBACK_ENABLED is True            # each arm restores the flag


def test_runner_context_uses_the_off_arms_window(monkeypatch):
    _one_entry(monkeypatch)
    [row] = mrg.paired_trades("AAA", make_ohlcv(BARS, start="2021-01-04"), basis="close")
    assert row["tp1_index"] == 1
    assert row["mfe_off_r"] == pytest.approx(4.0)            # best close 120 over [1, 4)
    assert row["gb_r"] == pytest.approx(0.05 * 120.0 / 5.0)
    assert (row["days_off"], row["days_on"]) == (3, 2)
    assert row["shakeout"] is False                           # 106.5 after exit < 120
    assert row["gap_worse_r"] == 0.0                          # bar 3 opened at 120 > 114


def test_high_low_basis_takes_e_from_the_bar_high(monkeypatch):
    _one_entry(monkeypatch)
    [row] = mrg.paired_trades("AAA", make_ohlcv(BARS, start="2021-01-04"), basis="high_low")
    assert exit_sim.GIVEBACK_EXTREME_BASIS == "high_low"
    assert row["on"]["exit_price"] == pytest.approx(exit_sim.giveback_stop(121.0, 5.0, "bullish"))


def test_no_bar_after_train_end_reaches_the_entries_or_the_exits(monkeypatch):
    seen = []
    _one_entry(monkeypatch, seen)
    mrg.paired_trades("AAA", make_ohlcv(BARS * 3, start="2023-12-20"), basis="close")
    assert str(seen[0].index[-1].date()) <= "2023-12-31"


def test_an_unknown_basis_is_refused():
    with pytest.raises(ValueError, match="basis"):
        mrg.paired_trades("AAA", make_ohlcv(BARS, start="2021-01-04"), basis="open")


@pytest.mark.parametrize("lo,hi,expected", [(0.01, 0.2, "PASS"), (-0.2, -0.01, "FAIL"),
                                            (-0.1, 0.1, "NO-LIFT"), (0.0, 0.1, "NO-LIFT"),
                                            (None, None, "UNMEASURABLE")])
def test_verdict_rule(lo, hi, expected):
    assert mrg.verdict(lo, hi) == expected


def _row(ticker, off_r, on_r, *, hk="2w", day="2021-03-01"):
    def arm(r, source):
        return {"r_net": r, "runner_r": r, "stop_source": source, "reason": "runner_trail",
                "exit_date": day, "exit_price": 1.0, "exit_index": 5}
    return {"ticker": ticker, "horizon_key": hk, "signal_date": day, "changed": off_r != on_r,
            "off": arm(off_r, "floor"), "on": arm(on_r, "giveback"), "mfe_off_r": 3.0,
            "gb_r": 1.0, "days_off": 6, "days_on": 3, "shakeout": False, "gap_worse_r": 0.0}


def test_summarise_passes_a_uniform_lift():
    rows = [_row(t, 1.0, 1.1) for t in "ABCDEF"]
    s = mrg.summarise(rows, n_resamples=200)
    assert s["primary"]["delta_exp_r"] == pytest.approx(0.1)
    assert s["primary"]["verdict"] == "PASS"
    assert s["changed"] == 6
    assert s["runner"]["off"]["floor_share"] == 1.0
    assert s["runner"]["on"]["capture_fixed_window"] == pytest.approx(1.1 / 3.0)
    assert s["giveback_exits"]["n"] == 6


def test_summarise_calls_a_mixed_result_no_lift():
    rows = [_row(t, 1.0, 1.2) for t in "ABC"] + [_row(t, 1.0, 0.8) for t in "DEF"]
    s = mrg.summarise(rows, n_resamples=200)
    assert s["primary"]["ci_lo"] < 0 < s["primary"]["ci_hi"]
    assert s["primary"]["verdict"] == "NO-LIFT"
    assert s["cells_looked_at"] == 2 * len(s["per_horizon"]) + 8


def test_book_reports_drawdown_in_r_and_dollars():
    rows = [_row("A", 1.0, 1.0, day="2021-01-04"), _row("B", -2.0, -2.0, day="2021-01-05"),
            _row("C", 0.5, 0.5, day="2021-01-06")]
    book = mrg.summarise(rows, n_resamples=50)["book"]["off"]
    assert book["total_r"] == pytest.approx(-0.5)
    assert book["max_drawdown_r"] == pytest.approx(2.0)
    assert book["max_drawdown_dollars"] == pytest.approx(200.0)


def test_main_refuses_a_second_look(tmp_path, capsys):
    (tmp_path / "train-close.json").write_text("{}", encoding="utf-8")
    assert mrg.main(["--out-dir", str(tmp_path), "--basis", "close"]) == 1
    assert "refused:one-look" in capsys.readouterr().err


def test_main_refuses_zero_frictions(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 0.0)
    assert mrg.main(["--out-dir", str(tmp_path)]) == 1
    assert "refused:zero-frictions" in capsys.readouterr().err


def test_main_refuses_a_smoke_run_into_the_committed_directory(capsys):
    assert mrg.main(["--tickers", "AAA"]) == 1
    assert "refused:smoke-run" in capsys.readouterr().err


def test_main_writes_frozen_block_and_summary(tmp_path, monkeypatch):
    rows = [_row(t, 1.0, 1.1) for t in "ABCD"]
    monkeypatch.setattr(mrg, "build_rows", lambda basis, **kw: rows)
    monkeypatch.setattr(mrg.training_data, "select", lambda name=None: name)
    monkeypatch.setattr(mrg.training_data, "write_provenance", lambda path: path)
    assert mrg.main(["--out-dir", str(tmp_path), "--resamples", "50"]) == 0
    blob = json.loads((tmp_path / "train-close.json").read_text(encoding="utf-8"))
    assert blob["frozen"]["window"] == ["2020-01-01", "2023-12-31"]
    assert blob["frozen"]["data_source"] == "yfinance"
    assert blob["frozen"]["basis"] == "close" and blob["frozen"]["pct"] == 5.0
    assert blob["summary"]["primary"]["verdict"] == "PASS"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/backtest_scripts/test_measure_runner_giveback.py`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'measure_runner_giveback'`.

- [ ] **Step 3: Write `scripts/backtest/measure_runner_giveback.py` (pairing half)**

```python
#!/usr/bin/env python3
"""v176: TRAIN-only paired measurement of the runner give-back (flag off vs on at 5%).

Frozen before TRAIN is read (spec § Measurement), v123's instrument:
  window     TRAIN 2020-01-01..2023-12-31 only. Every frame is cut at TRAIN's
             end, so no VALIDATION bar is run or read.
  data       the 75-ticker local backtest cache (training_data "yfinance")
  engines    StrategyEngine.iter_trades + replay_scenarios, all ten horizons
  exits      simulate_exit(scale_out=True), instrument v1
  frictions  net_r: SLIPPAGE_BPS on both fills + commission_r(), both arms;
             zero frictions are refused
  arms       entries from ONE flag-off pass; each re-simulated off, then on at 5%
  basis      close (the spec's rule, the primary reading) | high_low (the
             tick/close sensitivity, descriptive)

One look: refuses to overwrite <out-dir>/train-<basis>.json. Reported, not a
gate; it never changes RUNNER_GIVEBACK_ENABLED.
PROGRESS: a flushed line per ticker plus logs/measure_runner_giveback.<basis>.progress.

Run: python scripts/backtest/measure_runner_giveback.py --out-dir docs/superpowers/results/v176 --basis close
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import json
import sys
from collections import Counter, defaultdict, namedtuple
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "data"), str(ROOT / "scripts" / "backtest")]

from swingbot import config  # noqa: E402
from swingbot.core.analytics.expectancy_attribution import net_r  # noqa: E402
from swingbot.core.backtesting.acceptance import (BOOTSTRAP_RESAMPLES,  # noqa: E402
                                                  bootstrap_delta, mde_paired)
from swingbot.core.marketdata import training_data  # noqa: E402
from swingbot.core.planning import exit_sim  # noqa: E402
from swingbot.core.planning.plan_engine import simulate_exit  # noqa: E402

TRAIN = ("2020-01-01", "2023-12-31")
PCT = 5.0
DATA_SOURCE = "yfinance"
BASES = ("close", "high_low")
ARMS = ("off", "on")
CLOSED = ("win", "loss", "scratch")
SHAKEOUT_BARS = 10
POOLED_DESCRIPTIVE_CELLS = 8   # runner R, floor share, exit mix, capture, days, gaps, shake-outs, book
RESULTS = ROOT / "docs" / "superpowers" / "results" / "v176"
LOG_DIR = ROOT / "logs"
_Arm = namedtuple("_Arm", "ticker r")


@contextlib.contextmanager
def giveback(enabled: bool):
    """The give-back flag (at 5%) for one simulation; the previous values come back after."""
    saved = (config.RUNNER_GIVEBACK_ENABLED, config.RUNNER_GIVEBACK_PCT)
    config.RUNNER_GIVEBACK_ENABLED, config.RUNNER_GIVEBACK_PCT = enabled, PCT
    try:
        yield
    finally:
        config.RUNNER_GIVEBACK_ENABLED, config.RUNNER_GIVEBACK_PCT = saved


def _entries(ticker, df) -> list:
    """(source, horizon_key, signal_index, plan) for every TRAIN entry of the
    flag-OFF pass: the off arm decides the entry set for both arms."""
    from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine
    from swingbot.core.backtesting.arms.windows import ALL_HORIZONS
    from swingbot.core.backtesting.backtest_scenarios import replay_scenarios
    from swingbot.scan_params import ScanParams
    params, engine, out = ScanParams.from_config(), StrategyEngine(), []
    position = {str(ts.date()): i for i, ts in enumerate(df.index)}
    with giveback(False):
        for hk in ALL_HORIZONS:
            for strategy in engine.strategies:
                for date, plan, _result in engine.iter_trades(ticker, df, strategy, hk, TRAIN, params):
                    out.append(("strategy", hk, position[date], plan))
            for index, plan in replay_scenarios(ticker, df, hk, params=params):
                if str(df.index[index].date()) >= TRAIN[0]:
                    out.append(("scenario", hk, index, plan))
    return out


def _arm(df, index, plan, enabled) -> dict | None:
    with giveback(enabled):
        result = simulate_exit(df, index, copy.deepcopy(plan), scale_out=True)
    if result.outcome not in CLOSED or not result.legs:
        return None
    runner = result.outcome == "win" and len(result.legs) == 2
    return {"r_net": net_r(result.entry_price, plan.stop_loss, plan.direction, result.legs),
            "runner_r": float(result.legs[1]["r"]) if runner else None,
            "entry_index": int(result.entry_index), "entry_price": float(result.entry_price),
            "exit_index": int(result.exit_index),
            "exit_date": str(df.index[result.exit_index].date()),
            "exit_price": float(result.legs[-1]["exit_price"]),
            "reason": result.runner_outcome or result.outcome,
            "stop_source": result.runner_stop_source}


def _tp1_index(df, start, stop, plan) -> int:
    high, low = df["High"].values, df["Low"].values
    for j in range(start, stop + 1):
        if (high[j] >= plan.tp1) if plan.direction == "bullish" else (low[j] <= plan.tp1):
            return j
    return stop


def _best_close(closes, lo, hi, is_bull) -> float:
    window = closes[lo:max(hi, lo + 1)]
    return float(window.max() if is_bull else window.min())


def _giveback_extras(df, on, best_on, sign, risk, fraction) -> dict:
    """Shake-out and gap-through-level for an on-arm give-back exit."""
    if on["stop_source"] != "giveback":
        return {"shakeout": None, "gap_worse_r": None}
    j = on["exit_index"]
    later = df["Close"].values[j + 1:j + 1 + SHAKEOUT_BARS]
    gap = (float(df["Open"].values[j]) - on["exit_price"]) * sign / risk
    return {"shakeout": bool(any((float(c) - best_on) * sign > 0 for c in later)),
            "gap_worse_r": min(0.0, gap) * fraction}


def _runner_context(df, off, on, plan, risk) -> dict:
    """Fixed-window (OFF arm) MFE and best close, 5% of price in R, days from TP1."""
    is_bull, closes = plan.direction == "bullish", df["Close"].values
    sign = 1 if is_bull else -1
    tp1 = _tp1_index(df, off["entry_index"], off["exit_index"], plan)
    best_off = _best_close(closes, tp1, off["exit_index"], is_bull)
    best_on = _best_close(closes, tp1, on["exit_index"], is_bull)
    mfe = max((best_off - off["entry_price"]) * sign / risk, off["runner_r"])
    return {"tp1_index": tp1, "mfe_off_r": mfe, "gb_r": PCT / 100.0 * best_off / risk,
            "days_off": off["exit_index"] - tp1, "days_on": on["exit_index"] - tp1,
            **_giveback_extras(df, on, best_on, sign, risk, 1.0 - plan.tp1_fraction)}


def pair_row(ticker, df, source, hk, index, plan) -> dict | None:
    off, on = _arm(df, index, plan, False), _arm(df, index, plan, True)
    if off is None or on is None:
        return None
    risk = abs(off["entry_price"] - plan.stop_loss)
    row = {"ticker": ticker, "source": source, "horizon_key": hk, "direction": plan.direction,
           "signal_date": str(df.index[index].date()), "risk": risk, "off": off, "on": on,
           "changed": (off["exit_index"], off["exit_price"]) != (on["exit_index"], on["exit_price"])}
    if off["runner_r"] is not None and on["runner_r"] is not None:
        row.update(_runner_context(df, off, on, plan, risk))
    return row


def paired_trades(ticker: str, df, *, basis: str) -> list[dict]:
    """Every TRAIN entry of ``ticker``, simulated off and on, on a frame cut at TRAIN's end."""
    if basis not in BASES:
        raise ValueError(f"basis must be one of {BASES}, got {basis!r}")
    exit_sim.GIVEBACK_EXTREME_BASIS = basis
    df = df.loc[:TRAIN[1]]
    rows = (pair_row(ticker, df, *entry) for entry in _entries(ticker, df))
    return [row for row in rows if row is not None]
```

Check the test frame: the market entry fills at bar 1's open (100.0), TP1 is touched on bar 1 (high 111), so `_tp1_index` scanning from `entry_index` (1) returns 1; off window closes `[1, 4)` = 110.5, 120, 113.5 → best 120, MFE `max(20/5, 1.333) = 4.0`; on exits on bar 3, `days_on = 2`; bar 3's open 120 is above the 114 level, so `gap_worse_r = min(0, 6/5) × 0.5 = 0.0`; the only later close is 106.5 → no shake-out. If `entry_index` comes out as 0 on this frame (signal bar), `_tp1_index` still returns 1 (bar 0's high 101 < 110), so the asserted numbers do not depend on it.

- [ ] **Step 4: Append the summary half and the CLI to the same file**

```python
# --- summary -----------------------------------------------------------------

def _mean(values):
    xs = [v for v in values if v is not None]
    return sum(xs) / len(xs) if xs else None


def _delta_mean(baseline, component):
    """Paired statistic: mean R on minus mean R off over one ticker draw."""
    if not baseline or not component:
        return None
    return _mean(t.r for t in component) - _mean(t.r for t in baseline)


def verdict(lo, hi) -> str:
    """Descriptive only (controller rule, 2026-10-19); never flips the flag."""
    if lo is None or hi is None:
        return "UNMEASURABLE"
    if lo > 0:
        return "PASS"
    if hi < 0:
        return "FAIL"
    return "NO-LIFT"


def _primary(rows, n_resamples) -> dict:
    base = [_Arm(r["ticker"], r["off"]["r_net"]) for r in rows]
    comp = [_Arm(r["ticker"], r["on"]["r_net"]) for r in rows]
    boot = bootstrap_delta(base, comp, _delta_mean, n_resamples=n_resamples)
    mde = mde_paired(base, comp, _delta_mean, observed_n=len(rows), target_n=len(rows),
                     n_resamples=n_resamples) if rows else None
    return {"n": len(rows), "exp_r_off": _mean(a.r for a in base),
            "exp_r_on": _mean(a.r for a in comp), "delta_exp_r": boot.point,
            "ci_lo": boot.lo, "ci_hi": boot.hi, "p_le_zero": boot.p_greater_than_zero,
            "mde_paired": mde, "n_resamples": n_resamples, "verdict": verdict(boot.lo, boot.hi)}


def _quantiles(values) -> dict | None:
    xs = np.array([v for v in values if v is not None], dtype=float)
    if xs.size == 0:
        return None
    p10, p25, p50, p75, p90 = (float(q) for q in np.percentile(xs, [10, 25, 50, 75, 90]))
    return {"n": int(xs.size), "mean": float(xs.mean()), "p10": p10, "p25": p25,
            "p50": p50, "p75": p75, "p90": p90}


def _per_horizon(rows) -> dict:
    by = defaultdict(list)
    for row in rows:
        by[row["horizon_key"]].append(row)
    return {hk: {"n": len(v), "changed": sum(r["changed"] for r in v),
                 "delta_r": _mean(r["on"]["r_net"] - r["off"]["r_net"] for r in v),
                 "giveback_pct_in_r": _quantiles(r.get("gb_r") for r in v)}
            for hk, v in sorted(by.items())}


def _runner_arm(runners, arm, mfe_total) -> dict:
    n = len(runners)
    mix = Counter(r[arm]["stop_source"] or r[arm]["reason"] for r in runners)
    return {"runner_r": _quantiles(r[arm]["runner_r"] for r in runners),
            "floor_share": sum(r[arm]["stop_source"] == "floor" for r in runners) / n if n else None,
            "exit_mix": dict(sorted(mix.items())),
            "capture_fixed_window": (sum(r[arm]["runner_r"] for r in runners) / mfe_total
                                     if mfe_total > 0 else None),
            "days_tp1_to_exit": _quantiles(r[f"days_{arm}"] for r in runners)}


def _giveback_block(runners) -> dict:
    gb = [r for r in runners if r["on"]["stop_source"] == "giveback"]
    gapped = [r["gap_worse_r"] for r in gb if r["gap_worse_r"] < 0]
    return {"n": len(gb), "fill_worse_than_level": len(gapped), "mean_gap_cost_r": _mean(gapped),
            "shakeouts_within_10_bars": sum(1 for r in gb if r["shakeout"])}


def _book(rows, arm) -> dict:
    """Fixed risk per trade (COMMISSION_RISK_BASIS dollars), ordered by exit date."""
    ordered = sorted(rows, key=lambda r: (r[arm]["exit_date"], r["ticker"], r["signal_date"]))
    rs = np.array([r[arm]["r_net"] for r in ordered], dtype=float)
    cum = np.cumsum(rs)
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
    dd = float(np.max(peak - cum)) if rs.size else 0.0
    basis = float(config.COMMISSION_RISK_BASIS)
    return {"total_r": float(rs.sum()), "dollars": float(rs.sum()) * basis,
            "max_drawdown_r": dd, "max_drawdown_dollars": dd * basis,
            "risk_per_trade_dollars": basis}


def summarise(rows: list[dict], *, n_resamples: int = BOOTSTRAP_RESAMPLES) -> dict:
    runners = [r for r in rows if "mfe_off_r" in r]
    mfe_total = sum(r["mfe_off_r"] for r in runners)
    per_horizon = _per_horizon(rows)
    return {"primary": _primary(rows, n_resamples),
            "changed": sum(r["changed"] for r in rows),
            "per_horizon": per_horizon,
            "runner": {"n": len(runners),
                       "mean_delta_r": _mean(r["on"]["r_net"] - r["off"]["r_net"] for r in runners),
                       **{arm: _runner_arm(runners, arm, mfe_total) for arm in ARMS}},
            "giveback_exits": _giveback_block(runners),
            "book": {arm: _book(rows, arm) for arm in ARMS},
            "cells_looked_at": 2 * len(per_horizon) + POOLED_DESCRIPTIVE_CELLS}


# --- run ---------------------------------------------------------------------

def _init_worker(basis) -> None:
    training_data.select(DATA_SOURCE)
    exit_sim.GIVEBACK_EXTREME_BASIS = basis


def _ticker_rows(task):
    ticker, basis = task
    df = training_data.load_daily(ticker)
    return ticker, ([] if df is None else paired_trades(ticker, df, basis=basis))


def build_rows(basis, *, tickers=None, workers=None) -> list[dict]:
    """Every cached ticker's rows, in ticker order whatever order the pool finishes in."""
    from swingbot.core.backtesting.backtest_scenarios import _resolve_replay_workers
    universe = list(tickers) if tickers else training_data.available_tickers()
    LOG_DIR.mkdir(exist_ok=True)
    progress = LOG_DIR / f"measure_runner_giveback.{basis}.progress"
    by_ticker = {}

    def record(ticker, rows):
        by_ticker[ticker] = rows
        done = len(by_ticker)
        print(f"  [{basis}] {done}/{len(universe)} {ticker}: {len(rows)} paired", flush=True)
        progress.write_text(f"{done}/{len(universe)} tickers ({done / len(universe) * 100:.0f}%)\n",
                            encoding="utf-8")

    n_workers = _resolve_replay_workers(workers)
    if n_workers <= 1 or len(universe) <= 1:
        _init_worker(basis)
        for ticker in universe:
            record(*_ticker_rows((ticker, basis)))
    else:
        with ProcessPoolExecutor(max_workers=n_workers, initializer=_init_worker,
                                 initargs=(basis,)) as pool:
            for future in as_completed([pool.submit(_ticker_rows, (t, basis)) for t in universe]):
                record(*future.result())
    progress.unlink(missing_ok=True)
    return [row for ticker in sorted(by_ticker) for row in by_ticker[ticker]]


def _frozen(basis) -> dict:
    from swingbot.core.backtesting.arms.windows import ALL_HORIZONS
    return {"window": list(TRAIN), "data_source": DATA_SOURCE, "pct": PCT, "basis": basis,
            "arms": "flag off vs on, same entries (flag-off pass)", "scale_out": True,
            "instrument": "v1", "engines": ["StrategyEngine.iter_trades", "replay_scenarios"],
            "horizons": list(ALL_HORIZONS), "slippage_bps": float(config.SLIPPAGE_BPS),
            "commission_per_side": float(config.COMMISSION_PER_TRADE),
            "commission_risk_basis": float(config.COMMISSION_RISK_BASIS)}


def _refusal(args, target) -> str | None:
    if float(config.SLIPPAGE_BPS) <= 0 or float(config.COMMISSION_PER_TRADE) <= 0:
        return "refused:zero-frictions -- the spec needs non-zero frictions in both arms"
    if args.tickers and args.out_dir.resolve() == RESULTS.resolve():
        return "refused:smoke-run -- --tickers needs a scratch --out-dir"
    if target.exists():
        return f"refused:one-look -- {target} exists; this measurement is one look"
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, default=RESULTS)
    parser.add_argument("--basis", choices=BASES, default="close")
    parser.add_argument("--tickers", nargs="+", default=None)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--resamples", type=int, default=BOOTSTRAP_RESAMPLES)
    args = parser.parse_args(argv)
    target = args.out_dir / f"train-{args.basis}.json"
    refusal = _refusal(args, target)
    if refusal:
        print(refusal, file=sys.stderr)
        return 1
    training_data.select(DATA_SOURCE)
    rows = build_rows(args.basis, tickers=args.tickers, workers=args.workers)
    blob = {"frozen": _frozen(args.basis), "summary": summarise(rows, n_resamples=args.resamples)}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(blob, indent=1), encoding="utf-8")
    training_data.write_provenance(target)
    print(json.dumps(blob["summary"]["primary"], indent=1), f"\n-> {target}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`test_main_writes_frozen_block_and_summary` stubs `build_rows`, so `_frozen` is the only place it touches the engine package (`ALL_HORIZONS`, an import, no data).

- [ ] **Step 5: Run test to verify it passes**

Run: `python $WT/scripts/dev/testrun.py file tests/backtest_scripts/test_measure_runner_giveback.py`
Expected: PASS, 17 passed, 0 failed. If `test_the_same_entry_is_simulated_off_and_on_with_frictions` differs only in the last decimal of the friction arithmetic, re-derive it from `net_r`'s formula (`expectancy_attribution.py:110-128`) rather than loosening the tolerance.

- [ ] **Step 6: Smoke run on two tickers into scratch (no committed output, no VALIDATION)**

Run (backtest cache required: `python scripts/data/fetch_backtest_data.py` once if `data/backtest_cache/` is empty):
`python $WT/scripts/backtest/measure_runner_giveback.py --out-dir "$SCRATCH/v176-smoke" --tickers AAPL MSFT --workers 1 --resamples 200`
Expected: two `[close] n/2` progress lines, a printed `primary` block with `n > 0`, `$SCRATCH/v176-smoke/train-close.json` written. This is a plumbing check on two tickers, **not** the measurement: do not read or quote its numbers. Delete `$SCRATCH/v176-smoke` afterwards.

- [ ] **Step 7: Complexity**

Run: `python $WT/scripts/dev/complexity_gate.py`. Expected: no new offender (the largest new functions, `_entries` and `build_rows`, are C <= 8).

- [ ] **Step 8: Commit**

```bash
git -C $WT add scripts/backtest/measure_runner_giveback.py tests/backtest_scripts/test_measure_runner_giveback.py
git -C $WT commit -m "feat(v176): TRAIN paired give-back measurement script

Entries from one flag-off pass, each simulated off and on at 5% with
frictions; pooled paired dR with a ticker-cluster bootstrap and mde_paired,
descriptive per-horizon and runner blocks; frames cut at TRAIN's end; one
look per basis (close, high_low).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V176-9: Live-book give-back counterfactual script

**Model:** sonnet — a small offline report over existing helpers with a fixed walk rule; no engine change.

**Files:**
- Create: `scripts/reports/giveback_live_counterfactual.py`
- Create: `tests/scripts/test_giveback_live_counterfactual.py` (suite `tooling`; no manifest edit)

**Interfaces:**
- Consumes: V176-2 leg keys `stop_source`, `giveback_pct`, `giveback_extreme`, `giveback_stop` on the runner leg (`legs_realized[-1]`, written by `_close_runner`, `r` = runner R per unit, `closed_at` ISO); V176-1 `tighter_stop`; existing `runner_floor`, `chandelier_stop`, `gap_stop_fill` (`swingbot/core/backtesting/instrument/fills.py:33`, the pure twin of `plan_manager.py:39`, imported so the script never loads the live manager module), `atr` (`swingbot/core/market/indicators.py:62`), `PlanStore().records()` (raw plan dicts), `get_daily_data(ticker, period)`.
- Produces: `giveback_plans(records: list[dict]) -> list[dict]`; `counterfactual_exit(plan: dict, bars) -> dict` (`{plan_id, ticker, direction, exit_date, live_exit, live_r, giveback_stop, cf_start_stop, cf_exit, cf_date, cf_reason, cf_r, delta_r}`; `cf_reason` ∈ `floor` / `trail` / `tp2` / `open` / `no_bars`; `delta_r = live_r − cf_r`, positive means the give-back helped); `main(argv=None) -> int`, printing `"no conclusion below 30 give-back exits"` while `n < 30`.

**Walk rule (stated in the docstring; an approximation, reported as one):** the flag-off stop at the give-back exit is `tighter_stop(floor, chandelier(E, ATR14 of the bar before the exit day, trail_atr_mult))`, with `E` = the leg's `giveback_extreme`. From the exit day (inclusive) each daily bar: stop touched → fill `gap_stop_fill(open, stop)`, labelled `floor` when the stop is the floor, else `trail`; else TP2 touched → TP2; then `E` takes the close and the chandelier ratchets (never loosens). No exit by the last bar → `open`, marked at the last close.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_giveback_live_counterfactual.py`:

```python
"""v176 live-book counterfactual: a live give-back exit vs the flag-off exit from daily bars."""
import sys
from pathlib import Path

import pytest

from tests.helpers import make_ohlcv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))

import giveback_live_counterfactual as glc  # noqa: E402

FLOOR = 100.0 + (2.0 / 3.0) * 10.0
BEAR_FLOOR = 100.0 - (2.0 / 3.0) * 10.0


def _plan(direction="bullish", **leg_kw):
    bull = direction == "bullish"
    leg = {"fraction": 0.5, "exit_price": 114.0 if bull else 86.0, "r": 2.8,
           "reason": "tp1_runner_trail", "closed_at": "2021-01-07T15:00:00+00:00",
           "stop_source": "giveback", "giveback_pct": 5.0,
           "giveback_extreme": 120.0 if bull else 80.0, "giveback_stop": 114.0 if bull else 84.0}
    leg.update(leg_kw)
    return {"plan_id": "p1", "ticker": "AAA", "direction": direction, "status": "CLOSED",
            "entry_price": 100.0, "stop_loss": 95.0 if bull else 105.0,
            "tp1": 110.0 if bull else 90.0, "tp2": None, "trail_atr_mult": 50.0,
            "legs_realized": [{"fraction": 0.5, "exit_price": 110.0, "r": 2.0,
                               "reason": "tp1_partial"}, leg]}


FLAT = [(100.0, 101.0, 99.0, 100.0)] * 3                  # 2021-01-04..06


def test_long_runner_would_have_ridden_to_the_floor():
    bars = make_ohlcv(FLAT + [(115.0, 116.0, 113.0, 113.5),   # exit day 01-07
                              (113.5, 114.0, 108.0, 109.0),
                              (109.0, 110.0, 106.0, 106.5)], start="2021-01-04")
    out = glc.counterfactual_exit(_plan(), bars)
    assert out["exit_date"] == "2021-01-07"
    assert out["cf_start_stop"] == pytest.approx(FLOOR)      # chandelier at mult 50 is far below
    assert out["cf_reason"] == "floor"
    assert out["cf_date"] == "2021-01-11"
    assert out["cf_exit"] == pytest.approx(FLOOR)
    assert out["cf_r"] == pytest.approx((FLOOR - 100.0) / 5.0)
    assert out["delta_r"] == pytest.approx(2.8 - (FLOOR - 100.0) / 5.0)


def test_a_gap_through_the_floor_fills_at_the_open():
    bars = make_ohlcv(FLAT + [(115.0, 116.0, 113.0, 113.5), (104.0, 105.0, 103.0, 104.5)],
                      start="2021-01-04")
    out = glc.counterfactual_exit(_plan(), bars)
    assert out["cf_exit"] == pytest.approx(104.0)


def test_short_runner_never_stopped_is_marked_open_at_the_last_close():
    bars = make_ohlcv(FLAT + [(85.0, 87.0, 84.5, 86.5), (86.5, 90.0, 85.0, 89.0)],
                      start="2021-01-04")
    out = glc.counterfactual_exit(_plan("bearish"), bars)
    assert out["cf_start_stop"] == pytest.approx(BEAR_FLOOR)
    assert out["cf_reason"] == "open"
    assert out["cf_exit"] == pytest.approx(89.0)
    assert out["cf_r"] == pytest.approx((100.0 - 89.0) / 5.0)


def test_no_bars_from_the_exit_day_is_reported_not_guessed():
    bars = make_ohlcv(FLAT, start="2021-01-04")
    assert glc.counterfactual_exit(_plan(), bars)["cf_reason"] == "no_bars"


def test_only_closed_plans_with_a_giveback_runner_leg_are_counted():
    trail = _plan(stop_source="trail")
    still_open = dict(_plan(), status="PARTIAL")
    assert [p["plan_id"] for p in glc.giveback_plans([_plan(), trail, still_open])] == ["p1"]


def test_main_withholds_a_conclusion_below_thirty(monkeypatch, capsys):
    bars = make_ohlcv(FLAT + [(115.0, 116.0, 113.0, 113.5)], start="2021-01-04")
    monkeypatch.setattr(glc, "_records", lambda: [_plan()])
    monkeypatch.setattr(glc, "_bars", lambda ticker: bars)
    assert glc.main([]) == 0
    out = capsys.readouterr().out
    assert "no conclusion below 30 give-back exits" in out
    assert "AAA" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/scripts/test_giveback_live_counterfactual.py`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'giveback_live_counterfactual'`.

- [ ] **Step 3: Write `scripts/reports/giveback_live_counterfactual.py`**

```python
#!/usr/bin/env python3
"""v176 live book: each live give-back exit against its flag-off counterfactual exit.

A closed plan counts when its runner leg carries stop_source == "giveback".
The flag-off stop at that exit is approximated from daily bars as the tighter
of the runner floor and the chandelier on the leg's giveback_extreme with the
ATR(14) of the bar before the exit day; from the exit day on, each bar checks
the stop (gap-aware fill), then TP2, then takes the close into E and
ratchets the chandelier. No exit by the last bar: "open" at the last close.
No conclusion below 30 give-back exits (spec § Live book); changing the 5%
or the flag is the partner's call.

Run where the live book is, read-only:
    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" \
        < scripts/reports/giveback_live_counterfactual.py
or locally after /replicate-prod-db: python scripts/reports/giveback_live_counterfactual.py [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot.core.market.indicators import atr  # noqa: E402
from swingbot.core.planning.exit_sim import chandelier_stop, runner_floor, tighter_stop  # noqa: E402
from swingbot.core.backtesting.instrument.fills import gap_stop_fill  # noqa: E402  (pure; same formula as plan_manager.py:39)

MIN_N = 30
NY = "America/New_York"


def _runner_leg(plan: dict) -> dict | None:
    legs = plan.get("legs_realized") or []
    leg = legs[-1] if legs else None
    return leg if leg and leg.get("stop_source") == "giveback" else None


def giveback_plans(records: list[dict]) -> list[dict]:
    return [r for r in records if r.get("status") == "CLOSED" and _runner_leg(r)]


def _session_date(stamp) -> str:
    ts = pd.Timestamp(stamp)
    return str((ts.tz_convert(NY) if ts.tzinfo is not None else ts).date())


def _trail(extreme, atr_value, plan) -> float | None:
    if atr_value is None or not math.isfinite(float(atr_value)):
        return None
    return chandelier_stop(extreme, float(atr_value), float(plan["trail_atr_mult"]), plan["direction"])


def _hit(bar, stop, tp2, is_bull):
    """(fill, kind) when the bar reaches the stop, else TP2, else None."""
    if (bar.Low <= stop) if is_bull else (bar.High >= stop):
        return gap_stop_fill(float(bar.Open), stop, "bullish" if is_bull else "bearish"), "stop"
    if tp2 is not None and ((bar.High >= tp2) if is_bull else (bar.Low <= tp2)):
        return float(tp2), "tp2"
    return None


def _walk(bars, atr_series, start, stop, extreme, plan, floor):
    is_bull = plan["direction"] == "bullish"
    for i in range(start, len(bars)):
        bar = bars.iloc[i]
        hit = _hit(bar, stop, plan.get("tp2"), is_bull)
        if hit:
            kind = "tp2" if hit[1] == "tp2" else ("floor" if stop == floor else "trail")
            return hit[0], str(bars.index[i].date()), kind
        extreme = max(extreme, float(bar.Close)) if is_bull else min(extreme, float(bar.Close))
        stop = tighter_stop(stop, _trail(extreme, atr_series.iloc[i], plan), is_bull)
    return float(bars["Close"].iloc[-1]), str(bars.index[-1].date()), "open"


def counterfactual_exit(plan: dict, bars) -> dict:
    leg = _runner_leg(plan)
    is_bull = plan["direction"] == "bullish"
    entry, sign = float(plan["entry_price"]), (1 if is_bull else -1)
    risk = abs(entry - float(plan["stop_loss"]))
    floor = runner_floor(entry, float(plan["tp1"]))
    day = _session_date(leg["closed_at"])
    dates = [str(ts.date()) for ts in bars.index]
    start = next((i for i, d in enumerate(dates) if d >= day), None)
    out = {"plan_id": plan["plan_id"], "ticker": plan["ticker"], "direction": plan["direction"],
           "exit_date": day, "live_exit": float(leg["exit_price"]), "live_r": float(leg["r"]),
           "giveback_stop": leg.get("giveback_stop")}
    if start is None:
        return {**out, "cf_start_stop": None, "cf_exit": None, "cf_date": None,
                "cf_reason": "no_bars", "cf_r": None, "delta_r": None}
    atr_series = atr(bars, 14)
    extreme = float(leg["giveback_extreme"])
    stop0 = tighter_stop(floor, _trail(extreme, atr_series.iloc[max(start - 1, 0)], plan), is_bull)
    cf_exit, cf_date, reason = _walk(bars, atr_series, start, stop0, extreme, plan, floor)
    cf_r = (cf_exit - entry) * sign / risk
    return {**out, "cf_start_stop": stop0, "cf_exit": cf_exit, "cf_date": cf_date,
            "cf_reason": reason, "cf_r": cf_r, "delta_r": out["live_r"] - cf_r}


def _records() -> list[dict]:
    from swingbot.core.planning.plan_store import PlanStore
    return PlanStore().records()


def _bars(ticker):
    from swingbot.core.marketdata.data import get_daily_data
    return get_daily_data(ticker, period="5y")


def _summary(results) -> str:
    decided = [r["delta_r"] for r in results if r["delta_r"] is not None]
    if len(decided) < MIN_N:
        return f"n={len(decided)}: no conclusion below {MIN_N} give-back exits"
    s = pd.Series(decided)
    return (f"n={len(decided)}: mean delta_r {s.mean():+.3f}R, median {s.median():+.3f}R "
            "(descriptive; the 5% and the flag are the partner's call)")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)
    results = [counterfactual_exit(p, _bars(p["ticker"])) for p in giveback_plans(_records())]
    for r in results:
        print(f"{r['ticker']:<6} {str(r['plan_id'])[:8]} exit {r['exit_date']} live {r['live_r']:+.2f}R "
              f"cf {r['cf_reason']} {r['cf_r'] if r['cf_r'] is None else round(r['cf_r'], 2)}R")
    print(_summary(results))
    if args.json:
        args.json.write_text(json.dumps(results, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Check the long test: exit day 01-07 (low 113 > 106.667); 01-08 (low 108) holds; 01-11 (Monday, low 106 <= 106.667) fills at `min(109, 106.667)` = the floor. The gap test: 01-08 opens at 104 below the floor, fill 104. The short test: highs 87 and 90 stay under 93.333, so `open` at the last close 89. ATR(14) on 4-6 bars is NaN early, which `_trail` treats as no chandelier term (the floor alone).

- [ ] **Step 4: Run test to verify it passes**

Run: `python $WT/scripts/dev/testrun.py file tests/scripts/test_giveback_live_counterfactual.py`
Expected: PASS, 6 passed, 0 failed. If `atr(bars, 14)` returns finite values on the short frames (an implementation that back-fills), the chandelier at `trail_atr_mult=50` still sits far beyond the floor, so the asserted numbers hold.

- [ ] **Step 5: Complexity and syntax**

Run: `python $WT/scripts/dev/complexity_gate.py` (no new offender) and `python -m py_compile $WT/scripts/reports/giveback_live_counterfactual.py`.

- [ ] **Step 6: Commit**

```bash
git -C $WT add scripts/reports/giveback_live_counterfactual.py tests/scripts/test_giveback_live_counterfactual.py
git -C $WT commit -m "feat(v176): live-book give-back counterfactual report

Each closed plan whose runner leg is tagged stop_source=giveback is walked
forward on daily bars with the flag-off stop (floor/chandelier) to its
counterfactual exit; no conclusion below 30 give-back exits.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V176-10: Full suite (the plan's one full run)

**Model:** haiku — runs one command through the `test-runner` subagent and reports counts; no code.

**Files:** none.

- [ ] **Step 1: Confirm every code task is committed in the worktree**

Run: `git -C $WT log --oneline main..HEAD` (expect the V176-1..V176-9 commits) and `git -C $WT status --short` (expect empty). The Postgres test database must be up (`/replicate-prod-db` has run this session).

- [ ] **Step 2: Run the full suite through the `test-runner` subagent**

Dispatch `test-runner` with: `python $WT/scripts/dev/testrun.py full` (runs `-n 4` and the complexity gate). Expected: `0 failed`, `0 xfailed`; the complexity gate reports no new offender. A changed pass count is not a failure (`testing-cost.md`).

- [ ] **Step 3: On a failure, fix and re-run that test alone**

Each failure is fixed in the task's own files and re-run alone (`python $WT/scripts/dev/testrun.py file <path>` or `python -m pytest <path>::<test> -v`), never by re-running the whole suite. A pinned simulator test that moved and is not in the index's decision table is decided by the same rule (witness/golden → flag-off; engine-behaviour test → re-pin with a hand derivation) and committed as `test(v176): ...` with the decision line in the body.

- [ ] **Step 4: Record the result**

Note the pass/skip counts and the wall time for the V176-11 merge commit body. No commit in this task unless Step 3 changed a file.

# Phase 6: Ship (on `main`, main tree)

### Task V176-11: Merge to `main` + bump bot minor + regenerate version history

**Model:** haiku — a mechanical merge and the two-commit release ritual, following fixed commands.

**Files:**
- Modify: `VERSION.json`
- Modify: `swingbot/admin/version_history.json` (regenerated; the index ledger's `version_history.json`)

- [ ] **Step 1: Check for a concurrent session and a stale checkout**

Run: `git -C $R fetch origin`, `git -C $R status -sb` (on `main`, clean except files another session owns; never stage those), `git -C $R log --oneline -1 origin/main` vs `git -C $R log --oneline -1 main`. If `origin/main` is ahead, `git -C $R pull --ff-only` first. Follow the `worktree-lifecycle` skill before merging.

- [ ] **Step 2: Merge the worktree branch (no full suite after it)**

```bash
git -C $R merge --no-ff 2026-10-19-v176-runner-giveback-exit -m "merge(v176): runner give-back exit

<V176-10 counts: N passed, M skipped, 0 failed, 0 xfailed>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

A conflict is resolved by hand in `$R` and checked with `python $R/scripts/dev/testrun.py changed` only. Do **not** push (the push is the deploy, gated in V176-12).

- [ ] **Step 3: Bump `bot` from disk and commit it alone**

Read `$R/VERSION.json` (never this plan or memory). At writing it is `"bot": "2.11.0"`, so the minor bump gives `2.12.0`; if disk says otherwise, bump the minor of what disk says. Set `bot_updated` to the current UTC time in the existing `YYYY-MM-DD HH-MM-SS` format; leave the `ui` lines untouched.

```bash
git -C $R add VERSION.json
git -C $R commit -m "release(bot): 2.12.0 -- runner give-back exit (5% off the best price since TP1)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Regenerate the version history and commit it as the next commit**

```bash
python $R/scripts/dev/build_version_matrix.py
python $R/scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py
git -C $R add swingbot/admin/version_history.json
git -C $R commit -m "chore(bot): 2.12.0 -- runner give-back exit (5% off the best price since TP1)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Expected: the matrix test passes; the history's newest pair is the bump commit, not `"commit": "uncommitted"`. V176-14's `/close-out` skips its bump steps because this release is already in the log.

### Task V176-12: Deploy gate, deploy, verify RKLB

**Model:** sonnet — production operations with a hard read-only gate and a partner decision before the push; the commands are fixed, the judgement is in reading the table.

**Files:**
- Create: `docs/superpowers/results/2026-10-19-v176-deploy-gate.md`

**Interfaces:** consumes V176-7's `scripts/ops/partial_runner_rows.py` and `scripts/ops/giveback_deploy_gate.py`; production only through `bash scripts/ops/ssh-hetzner.sh` (never raw `ssh`/`scp`). Everything before Step 5 is **read-only** on the VM: no `.env` edit, no restart, no write query.

- [ ] **Step 1: Read the VM's give-back config (read-only)**

Run: `bash $R/scripts/ops/ssh-hetzner.sh "grep -n 'RUNNER_GIVEBACK' /opt/swing-bot/.env || echo 'no RUNNER_GIVEBACK keys: code defaults apply (enabled, 5.0)'"`
Expected: no keys (the defaults ship on). If a key is set, the gate uses that percent in Step 3 (`--pct`), and an `ENABLED=false` means no stop moves: record it and ask the partner before going on.

- [ ] **Step 2: List every open PARTIAL plan from the running (old) image**

```bash
bash $R/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" \
  < $R/scripts/ops/partial_runner_rows.py > "$SCRATCH/v176-partial-rows.txt"
```

Expected: the last line is a JSON list; RKLB `47f7fd16-38d5-49d4-a917-d0fdb3376c85` is in it, `direction` `bearish`, `working_stop` 59.11, `runner_high_close` 49.94 (the spec's numbers on 2026-10-19; record what the VM says, not these).

- [ ] **Step 3: Build the gate table locally**

Run: `python $R/scripts/ops/giveback_deploy_gate.py --rows "$SCRATCH/v176-partial-rows.txt" --pct 5.0`
Expected for RKLB: give-back stop ≈ 52.44, new stop 52.44, "closes on tick 1" `yes` if the last price is at or above 52.44, else `no`.

- [ ] **Step 4: Record the table, show it to the partner, get the go-ahead**

Create `docs/superpowers/results/2026-10-19-v176-deploy-gate.md`:

```markdown
# v176 deploy gate: open runners' stops before and after the first tick

**Plan:** [v176 index](../plans/2026-10-19-v176-runner-giveback-exit_0-index.md) (V176-12)
**Taken:** <UTC timestamp>, read-only, on the pre-v176 image (`<docker image tag from compose ps>`)
**VM config:** <Step 1 output>

<Step 3 table, verbatim>

Plans marked "closes on tick 1 = yes" close on the first tick after the
restart at that tick's price (the paper close does not move broker stops).
Every "moves = yes" row's broker stop sits at the old level until moved by
hand; the `stop_moved` notice follows in the regular session.

## After deploy
(filled in Step 7)
```

Show the table to the partner in the chat (the rows, with the RKLB row called out), then ask with `AskUserQuestion`, one question, recommended option first: "Push `main` and deploy v176 now? (1) Yes, deploy (recommended) (2) Not yet". "Not yet" stops this task here, with the results doc committed and nothing pushed.

```bash
git -C $R add docs/superpowers/results/2026-10-19-v176-deploy-gate.md
git -C $R commit -m "docs(v176): deploy gate -- open runners' old and new stops before the push

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 5: Push (this is the deploy) and watch the workflow**

```bash
git -C $R push origin main
gh run list --workflow deploy.yml --limit 1
gh run watch <run id> --exit-status
```

Expected: every job green, `deploy` last. A red job: stop, read its log (`gh run view <id> --log-failed`), and report; rollback is `SWING_BOT_IMAGE=ghcr.io/<owner>/<repo>:sha-<previous 12> ./deploy/deploy.sh` on the VM, and only on the partner's word (`docs/deploy/DEPLOY_HETZNER.md` § rollback).

- [ ] **Step 6: Verify the deploy and RKLB (read-only)**

```bash
bash $R/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && git log --oneline -1 && docker compose ps"
bash $R/scripts/ops/ssh-hetzner.sh "grep -i 'slash' /opt/swing-bot/logs/*.log | tail -5"
bash $R/scripts/ops/ssh-hetzner.sh "grep -h 'giveback stop' /opt/swing-bot/logs/bot.log | tail -20"
bash $R/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot -X -c \"SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY; SELECT status, doc->>'working_stop' AS working_stop, doc->>'runner_high_close' AS e, doc->'legs_realized'->-1 AS last_leg FROM plans WHERE plan_id = '47f7fd16-38d5-49d4-a917-d0fdb3376c85';\""
```

Expected: HEAD is the merged `main`; containers healthy; slash sync logged; a `Plan giveback stop: RKLB ...` line after the first poll (the manager polls every 60s outside the quiet window, so this may wait for the next session); RKLB either `PARTIAL` with `working_stop` ≈ 52.437, or `CLOSED` with `last_leg.reason = "tp1_runner_trail"` and `last_leg.stop_source = "giveback"` if price was already past the level. Anything else (stop unchanged after a non-quiet poll, a different `stop_source`) is a defect: report it, do not hot-fix on the VM.

- [ ] **Step 7: Record the post-deploy reading and commit (no separate push)**

Replace `(filled in Step 7)` in the results doc with: deploy run id and image tag, the time of the first `giveback stop` line, RKLB's status/`working_stop`/last leg, and every gate row whose observed stop differs from the table's "new stop" (with the reason, e.g. a new extreme since the gate).

```bash
git -C $R add docs/superpowers/results/2026-10-19-v176-deploy-gate.md
git -C $R commit -m "docs(v176): post-deploy reading -- RKLB runner stop and first give-back moves

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

This docs-only commit rides the next push; do not push it on its own (a push redeploys).

# Phase 7: Measure and close

### Task V176-13: TRAIN measurement run + ledger row

**Model:** opus — reading a paired bootstrap result honestly (one primary reading, descriptive cells counted, no re-tuning off the report) is the error-prone part.

**Files:**
- Create: `docs/superpowers/results/v176/train-close.json`, `docs/superpowers/results/v176/train-high_low.json` (+ their provenance sidecars, written by the script)
- Create: `docs/superpowers/results/2026-10-19-v176-giveback-train.md`
- Modify: `docs/superpowers/results/preregistration-ledger.jsonl` (one appended row, id `v176-giveback`)

Frozen before TRAIN is read (the script's `frozen` block): TRAIN 2020-01-01..2023-12-31 only, VALIDATION neither run nor read; 75-ticker `yfinance` cache; `iter_trades` + `replay_scenarios`, all ten horizons, `scale_out=True`, v1; non-zero frictions both arms; flag off vs on at 5% on the same entries. One look, one ledger row. Win rate is not reported.

- [ ] **Step 1: Run both bases through the `backtest-runner` subagent (long run, percent printed)**

Check first: `ls $R/data/backtest_cache/*.csv | wc -l` is 75 (else `python $R/scripts/data/fetch_backtest_data.py --data-source yfinance` once). Then dispatch `backtest-runner` with, in order:

```bash
python $R/scripts/backtest/measure_runner_giveback.py --out-dir $R/docs/superpowers/results/v176 --basis close
python $R/scripts/backtest/measure_runner_giveback.py --out-dir $R/docs/superpowers/results/v176 --basis high_low
```

Progress lives in `$R/logs/measure_runner_giveback.<basis>.progress`. Each run refuses to overwrite its JSON: a crashed run is re-run only if no JSON was written; a written JSON is the look.

- [ ] **Step 2: Write the results doc**

Create `docs/superpowers/results/2026-10-19-v176-giveback-train.md` with, in this order: the frozen block (copied from `train-close.json`); **Primary reading** (close basis): `n`, `exp_r_off`, `exp_r_on`, `delta_exp_r` with `[ci_lo, ci_hi]`, `p_le_zero`, `mde_paired`, `changed`, and the verdict by the rule below; the spec's prior beside it (pooled effect near 0.01R, |Δ ExpR| < 0.05R; v92 and v123 closed near zero); **Descriptive (not effect claims; `cells_looked_at` cells, so one or two horizon "effects" at 5% are expected by chance)**: per-horizon ΔR beside `giveback_pct_in_r` quantiles, runner-R quantiles and floor share off/on, capture against the off arm's fixed MFE window, exit mix by `stop_source`, give-back exits with a fill worse than the level and their mean gap cost, dollars and max drawdown at fixed risk off/on, days TP1→exit, shake-outs within 10 bars; **Tick/close sensitivity**: the `high_low` primary block beside the `close` one, as a bound on the live (tick) vs backtest (close) asymmetry; **What this does not license**: a different percent or an ATR-scaled `p` is a new pre-registration (grid frozen before fold-train, Stage 1 `plateau_report()`, the harvest gate's one-shot VALIDATION); the best cell is not read off this report; changing the 5% or the flag is the partner's call.

Verdict rule (controller, 2026-10-19), on the close basis only: `PASS` if `ci_lo > 0`, `FAIL` if `ci_hi < 0`, `NO-LIFT` if the interval contains 0 (`UNMEASURABLE` if no interval). It is descriptive: it never flips `RUNNER_GIVEBACK_ENABLED`.

- [ ] **Step 3: Append the ledger row**

```bash
python $R/scripts/reports/preregistration_ledger.py --id v176-giveback \
  --hypothesis "RUNNER_GIVEBACK_ENABLED at 5%: runner stop 5% off the best close since TP1, paired off/on on TRAIN (v176)" \
  --instrument v1 --n <primary n> --exp-r null --p <primary p_le_zero> \
  --verdict <PASS|FAIL|NO-LIFT|UNMEASURABLE> \
  --record docs/superpowers/results/2026-10-19-v176-giveback-train.md --data-source yfinance
```

`--exp-r null` like the other paired exit rows (v92, v123, v129); the ΔExpR lives in the record. Expected: the CLI prints the row and its BH q-value (reported, never gating).

- [ ] **Step 4: Report to the partner, then commit**

Give the partner the primary block, the verdict and the tick/close gap in the chat; no recommendation to change the percent or the flag beyond pointing at the new-pre-registration route.

```bash
git -C $R add docs/superpowers/results/v176/ docs/superpowers/results/2026-10-19-v176-giveback-train.md docs/superpowers/results/preregistration-ledger.jsonl
git -C $R commit -m "docs(v176): TRAIN give-back measurement -- <verdict>, dExpR <point> [<lo>, <hi>]

One look, close basis primary, high_low sensitivity; ledger row v176-giveback.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V176-14: `/panel` pre-close-out and `/close-out`

**Model:** sonnet — runs two fixed rituals and resolves their findings; no new code.

**Files:**
- Modify: `docs/superpowers/plans/2026-10-19-v176-runner-giveback-exit_0-index.md` (with parts 1-3 and the spec, moved to `implemented/` by `/close-out`)

- [ ] **Step 1: `/panel` over the merged diff and the results**

Run `/panel risk-manager,veteran-trader,quant-researcher` (the spec's `**Panel:**` line) over `<merge commit>^1...<merge commit>` plus `docs/superpowers/results/2026-10-19-v176-deploy-gate.md` and `docs/superpowers/results/2026-10-19-v176-giveback-train.md`. A `BLOCKING` finding stops here and goes to the partner; others are applied or answered in a `## Panel review` section appended to the index, committed as `docs(v176): panel review at close-out`.

- [ ] **Step 2: `/close-out`, skipping the bump**

Run `/close-out`. Step 3-4 (bump and regeneration) are **already done** in V176-11 (`release(bot): 2.12.0`, then the regenerated history): confirm both commits are in `git -C $R log --oneline -5 -- VERSION.json swingbot/admin/version_history.json` and do not bump again. If the measurement contradicted the header's `Edge: harvest` prediction (spec: |Δ ExpR| < 0.05R), amend the header in one clause in the move commit. Then `git mv` the index, the three parts and the spec into `docs/superpowers/plans/implemented/` / `docs/superpowers/specs/implemented/`, and remove the worktree `$WT` and its branch `2026-10-19-v176-runner-giveback-exit` (`git rev-list --count main..2026-10-19-v176-runner-giveback-exit` must be 0 first; never touch a `backup`/`stable-*` branch).

```bash
git -C $R commit -m "docs(v176): close out -- runner give-back exit implemented

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

No full suite after the merge. The docs commits from V176-12 Step 7 onwards ride the next push; push only when the partner asks (a push redeploys).

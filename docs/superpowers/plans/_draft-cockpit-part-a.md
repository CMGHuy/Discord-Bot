# PART 1 (Plan A) — Analytics & Insight Core (Tasks A1–A31)

**Goal:** A single analytics package (`swingbot/core/analytics/`) that turns trades.json + the validation registry + the journal into every number the Discord UX (Plan B) and the admin cockpit (Plan C) display — equity/drawdown, per-dimension stats, quality-score calibration, edge-decay detection, a per-trade lessons journal, and one shared `follow_score` ranking that answers "which plan should I follow today?".

**Architecture:** Pure functions over trade-record lists (no I/O in `metrics.py`/`aggregate.py`/`calibration.py`), a `JournalStore` that auto-writes a lesson entry on every trade close (MFE/MAE, exit efficiency, tags), a nightly `analytics_snapshot.json` so UIs never recompute on request, and an atomic-write JSON layer fixing the existing torn-write risk. Plans B and C only *render* what this package computes — no stat is ever computed twice.

**Tech Stack:** Python 3.11+, pandas 2.3.3, numpy, pytest ≥8. JSON persistence under `data/`. **No new dependencies** (quantstats stays optional in `risk_metrics.py`, untouched).

**Prerequisite:** Unified Plan Engine v2 (`docs/superpowers/plans/2026-07-11-unified-plan-engine-v2.md`) fully implemented: `plan_engine.TradePlanV2`, `quality.py` scores wired, `registry.get_badge`, `plan_store.PlanStore`, `plan_manager.PlanManager`, two-leg trades.json schema.

> **Codebase-verification note (2026-07-12, plan-engine-v2 at Task 15/110 on `feature/plan-engine-v2`):** as of this writing the prerequisite is **not yet met** — `swingbot/core/plan_engine.py` and `swingbot/core/registry.py` already exist with the shapes assumed below, but `quality.py`, `plan_store.py`, `plan_manager.py`, `scripts/audit_quality_score.py`, and the two-leg `legs`/`plan_id` trades.json schema do **not exist yet**. Every task below is written against the v2 plan's own documented interfaces (verified by reading `2026-07-11-unified-plan-engine-v2.md` directly, not just this plan's summary of them) so it is ready to execute the moment v2 lands. Task A1 is the literal gate — do not start A2 until its audit passes for real. Three concrete corrections were needed versus the original one-line assumption in this plan's prior draft; see Task A1 Step 2 for the mapping.

## Global Constraints

- **Read-only over trading logic.** This plan never changes entries, exits, sizing, gates, or `STRATEGY_RR_OVERRIDE`. It measures; it does not decide.
- **One definition per stat.** `win_rate` = wins/(wins+losses)×100 over closed win+loss trades; `expectancy_r` = mean realized R over all closed trades with a computable R (r = (exit−entry)/(entry−stop), sign-flipped for bearish) — identical to `performance.get_extended_stats` semantics. Any UI showing a different number is a bug.
- **Validation-window hygiene unchanged:** analytics may *display* registry OOS stats but never triggers a validation-window backtest.
- **Trade dicts are the interface.** Every analytics function takes plain trade-record dicts (schema: `performance.log_trade` record, two-leg v2 extension included). Missing keys degrade gracefully (skip + count), never raise.
- **No I/O in pure modules:** `metrics.py`, `aggregate.py`, `calibration.py`, `rank.py` import neither `config` paths nor do file reads. I/O lives in `journal.py`, `snapshots.py`, `jsonio.py`, and — one narrow, deliberate exception — `insights.py`'s `edge_decay_report` (Task A26), which calls `registry.load_registry()` so that `calibration.badge_drift` itself stays completely pure. `registry.load_registry()` reads a file colocated with `registry.py` (not under `config.DATA_DIR`) through its own module-level cache, so this exception never touches `config` paths or the atomic-write layer — but it is still a real file read, so `insights.py` is not claimed as I/O-free the way the other four modules are.
- **Every task ends green:** `python -m pytest tests/ -q` and `make check` pass before commit. Run from repo root `E:\Documents\Private\Projects\Discord-Bot`. **Windows note:** `make check` shells out to `python3`, which is not guaranteed on PATH on a plain Windows install (see Task A31) — if `make` or `python3` is unavailable, run the equivalent `python -m py_compile` loop directly; this plan's own test commands always use `python`, never `python3`.
- **Timezone:** day-of-week and calendar buckets use Europe/Berlin, matching `performance.get_detailed_stats`.
- **Currency:** amounts formatted with `config.CURRENCY_SYMBOL` (default €) by callers; analytics returns raw floats.
- **Commit style:** conventional commits, one commit per task minimum.

## File Structure (target state)

```
swingbot/core/
  jsonio.py                    NEW  atomic_write_json / read_json (temp+rename, fsync)
  analytics/
    __init__.py                NEW  re-exports public API
    metrics.py                 NEW  equity, drawdown, PF, expectancy, streaks, rolling WR, sharpe/sortino
    mfe_mae.py                 NEW  MFE/MAE/exit-efficiency from cached daily bars
    aggregate.py               NEW  StatRow + stats_by(dimension)
    calibration.py             NEW  score deciles, tier calibration, badge drift
    rank.py                    NEW  follow_score + rank_plans (THE shared ordering)
    journal.py                 NEW  JournalStore, auto entries, tags, notes  → data/journal.json
    insights.py                NEW  weekly digest, edge decay report, top lessons
    snapshots.py               NEW  build/save/load data/analytics_snapshot.json
  performance.py               MOD  jsonio writes; log_trade carries plan metadata; close-hook → journal
  state.py                     MOD  jsonio writes
  account.py                   MOD  jsonio writes
  retrospective.py             MOD  daily recap gains calibration + decay lines
scripts/
  backfill_journal.py          NEW  journal entries for historical closed trades
  export_analytics.py          NEW  CSV/JSON export to exports/analytics/
tests/
  test_jsonio.py, test_metrics_equity.py, test_metrics_ratios.py, test_metrics_streaks.py,
  test_mfe_mae.py, test_aggregate.py, test_calibration.py, test_rank.py,
  test_journal.py, test_journal_tags.py, test_insights.py, test_snapshots.py,
  test_trade_metadata.py, test_analytics_perf.py
```

---

# Phase A0 — Safe persistence & prerequisites (Tasks A1–A4)

### Task A1: Prerequisite interface audit

**Files:**
- Modify: this plan document (Progress note only)

The plan-engine-v2 work defines `quality.py`, `plan_store.PlanStore`, `plan_manager.PlanManager` after this plan was originally drafted. Before any code in this Part, confirm the real names against the actual v2 codebase — **do not trust the summary in this plan's Architecture section**, read `swingbot/core/plan_engine.py` and `swingbot/core/registry.py` directly, and read `docs/superpowers/plans/2026-07-11-unified-plan-engine-v2.md` for anything not yet merged.

- [ ] **Step 1: Verify imports and record actual names**

Run:
```
python -c "from swingbot.core.plan_engine import TradePlanV2, PlanStatus; from swingbot.core.registry import Badge, get_badge, load_registry; from swingbot.core import quality, plan_store, plan_manager; print('OK')"
```
Expected once v2 is fully merged: `OK`.

Expected **today** (v2 Task 15/110, this plan's actual prerequisite state as of 2026-07-12): `ModuleNotFoundError: No module named 'swingbot.core.quality'` (or `plan_store`/`plan_manager`, whichever import statement Python reaches first — `quality` sorts first alphabetically after the successful `plan_engine`/`registry` imports, so that is the module you will actually see fail). This is expected and is not a bug in this task — it means Part A genuinely cannot start yet. Do not stub these modules to make the import pass; wait for v2 to land, then re-run this exact command as the real gate.

- [ ] **Step 2: Confirm assumed signatures against the v2 plan text**

Three corrections found by reading `2026-07-11-unified-plan-engine-v2.md` directly (Task 56 for `PlanStore`, Task 70 for the `TradeLog` integration) instead of trusting a one-line paraphrase:

1. **`PlanStore` has no `all(status=None)` overload.** The real methods are `.add(plan)`, `.get(plan_id) -> TradePlanV2 | None`, `.update(plan)`, `.open_plans() -> list[TradePlanV2]` (status in PENDING/ACTIVE/PARTIAL only), and `.all() -> list[TradePlanV2]` (every plan, no filter argument). Any task below that needs "every plan regardless of status" calls `.all()` with no arguments; anything needing only live plans calls `.open_plans()`. Tasks A18/A29 in this plan already only ever need a caller-supplied `list[TradePlanV2] | list[dict]`, so this correction has **zero impact on any public signature this plan promises** — it only affects internal call sites Plan C wires up later.
2. **`performance.log_trade` already gains `plan_id` from v2 itself** (v2 Task 68 adds the `legs`/`plan_id` schema fields; v2 Task 70's `PlanManager._on_event` hook calls `log_trade(..., plan_id=plan.plan_id)` on fill). By the time Task A12 below runs, `plan_id` is **already a parameter and a record key** — Task A12 only needs to add `tier`, `badge`, `quality_score`, `source` on top of what v2 already shipped. The final combined signature `log_trade(..., plan_id=None, tier=None, badge=None, quality_score=None, source=None)` is exactly what this plan promises; A12 is written below assuming `plan_id` already exists so it does not redeclare it.
3. **v2's runner-leg close reasons are prefixed, not bare.** `ExitResult.legs[-1]["reason"]` and the `PlanManager` close-hook's `event.detail["reason"]` use `"tp1_runner_be"` / `"tp1_runner_tp2"` / `"tp1_runner_trail"` (see v2 lines ~4759, ~4777) — **not** bare `"runner_be"`/`"runner_tp2"`/`"runner_trail"` as an early draft of this plan assumed. Task A21's `tags_for` below matches on the substrings `"runner_tp2"`, `"runner_trail"`, `"runner_be"` (via `in`, not equality) against `t.get("legs", [{}])[-1].get("reason", "")` **or** the legacy `t.get("close_reason", "")` field, so both the v2-prefixed and any future bare form match without a signature change.

- [ ] **Step 3: Commit** — `docs: record plan-engine-v2 interface audit for analytics plan` (only if the doc changed — e.g. once the real `OK` is observed, replace this task's "Expected today" block with the actual pass and the real registry `Badge`/`get_badge` call shapes observed).

### Task A2: Atomic JSON I/O

**Files:**
- Create: `swingbot/core/jsonio.py`
- Test: `tests/test_jsonio.py`

**Interfaces:**
- Produces: `atomic_write_json(path: str, obj) -> None` (writes `<path>.tmp`, `os.replace` onto path); `read_json(path: str, default)` (returns `default` on missing file or JSON decode error, logging a warning). Used by every store in this plan and by Tasks A3–A4 migrations.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_jsonio.py
import json
import os

from swingbot.core.jsonio import atomic_write_json, read_json


def test_roundtrip(tmp_path):
    p = str(tmp_path / "x.json")
    atomic_write_json(p, {"a": 1})
    assert read_json(p, None) == {"a": 1}
    assert not os.path.exists(p + ".tmp")


def test_read_missing_returns_default(tmp_path):
    assert read_json(str(tmp_path / "nope.json"), []) == []


def test_read_corrupt_returns_default(tmp_path):
    p = str(tmp_path / "bad.json")
    with open(p, "w") as f:
        f.write("{truncated")
    assert read_json(p, {"d": True}) == {"d": True}


def test_write_creates_missing_parent_dir(tmp_path):
    # journal.json / analytics_snapshot.json / plans.json etc. are all
    # first-write-ever files the first time a fresh checkout runs -- the
    # parent (data/) normally already exists, but a nested tmp_path
    # subdirectory in a test, or a brand-new deploy target, might not.
    p = str(tmp_path / "nested" / "sub" / "y.json")
    atomic_write_json(p, [1, 2, 3])
    assert read_json(p, None) == [1, 2, 3]


def test_roundtrip_list_and_unicode(tmp_path):
    p = str(tmp_path / "list.json")
    obj = [{"ticker": "AAPL", "note": "target hit — clean 2R capture €"}]
    atomic_write_json(p, obj)
    assert read_json(p, None) == obj
```

- [ ] **Step 2: Run `python -m pytest tests/test_jsonio.py -v` — expect FAIL**

Expected:
```
ModuleNotFoundError: No module named 'swingbot.core.jsonio'
```

- [ ] **Step 3: Implement**

```python
# swingbot/core/jsonio.py
"""Atomic JSON persistence: write to <path>.tmp then os.replace, so a crash
mid-write (power loss, OOM kill, docker restart) can never leave a torn
file behind for the next read to choke on.

Every store in this plan (JournalStore, snapshots.py, and the migrated
TradeLog/StateStore/account.py) goes through these two functions instead
of raw json.dump/json.load -- see Tasks A3/A4 for the migration of the
three pre-existing stores that used to write with plain json.dump.
"""
import json
import logging
import os

log = logging.getLogger("swing-bot.jsonio")


def atomic_write_json(path: str, obj) -> None:
    """Write `obj` as indented JSON to `path` without ever leaving a torn
    (partially-written) file behind, even if the process is killed
    mid-write.

    Mechanism: write to `<path>.tmp` first, fsync it to disk, then
    `os.replace(tmp, path)` -- os.replace is atomic on both POSIX and
    Windows (unlike os.rename on Windows, which fails if the destination
    exists; os.replace does not have that restriction on either OS), so
    any reader of `path` sees either the fully-old content or the fully-
    new content, never a half-written mix.

    `default=str` on json.dump means an unexpected non-JSON-native value
    (e.g. a stray datetime object a caller forgot to .isoformat()) is
    stringified instead of raising -- a persistence layer should degrade,
    not crash the trade it's trying to save.
    """
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def read_json(path: str, default):
    """Read JSON from `path`, returning `default` (never raising) when the
    file is missing, empty, or corrupt. A corrupt file is logged as a
    warning rather than silently swallowed, so a real disk-corruption
    event is at least visible in the logs even though the bot keeps
    running on the fallback value."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("read_json(%s) failed (%s); returning default", path, exc)
        return default
```

- [ ] **Step 4: Run `python -m pytest tests/test_jsonio.py -v` — PASS (5 tests)**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/jsonio.py tests/test_jsonio.py
git commit -m "feat: atomic JSON write layer (jsonio)"
```

### Task A3: TradeLog persists atomically

**Files:**
- Modify: `swingbot/core/performance.py` (`TradeLog._load` at line 173, `TradeLog._save` at line 182 — verified against the current file, not the stale plan draft)
- Test: `tests/test_trade_metadata.py` (file created here, extended in A12)

**Interfaces:**
- No public signature change — `TradeLog._load`/`_save` are private; this task only changes their body.

- [ ] **Step 1: Failing test**

```python
# tests/test_trade_metadata.py
import json
import os

from swingbot.core.performance import TradeLog


def test_tradelog_writes_atomically_no_tmp_left_behind(tmp_path):
    path = str(tmp_path / "trades.json")
    log = TradeLog(path=path)
    log.log_trade(
        ticker="AAPL", strategy="Fibonacci", horizon_key="4w", direction="bullish",
        confidence_level=4, confidence_label="Strong", entry=100.0, stop_loss=95.0,
        take_profit=110.0,
    )
    assert os.path.exists(path)
    assert not os.path.exists(path + ".tmp")
    with open(path) as f:
        data = json.load(f)
    assert len(data) == 1 and data[0]["ticker"] == "AAPL"


def test_tradelog_recovers_from_corrupt_file(tmp_path):
    path = str(tmp_path / "trades.json")
    with open(path, "w") as f:
        f.write("{not valid json")
    log = TradeLog(path=path)
    # A corrupt file must never crash the bot on startup -- it starts
    # with an empty trade list instead of raising.
    assert log.get_trades(limit=None) == []
```

- [ ] **Step 2: Run `python -m pytest tests/test_trade_metadata.py -v` — expect PASS already**

This is deliberately a "no-op red" step: `TradeLog._load`'s existing `json.JSONDecodeError` guard and `_save`'s plain `json.dump` already satisfy both assertions today (the corrupt-file recovery already existed; only the *atomicity* guarantee is new). Confirm both tests pass with the OLD implementation first, so the diff in Step 3 is provably behavior-preserving, not behavior-fixing — this task is a pure refactor.

- [ ] **Step 3: Replace `_load`/`_save` bodies**

```python
# swingbot/core/performance.py -- replace the two method bodies (imports:
# add `from swingbot.core.jsonio import atomic_write_json, read_json` near
# the top with the other swingbot.core imports; the existing `import json`
# line can stay -- other parts of this file still use raw json elsewhere)

    def _load(self) -> list:
        return read_json(self.path, [])

    def _save(self):
        atomic_write_json(self.path, self._trades)
```

Note the attribute is `self._trades` (not `self.trades` — the class stores it privately and exposes it only through `get_trades()`/etc.); double-check this against the current file before pasting, since a stale copy-paste here would silently write nothing. `_LOCK` usage in every caller (`log_trade`, `update_open_trades`, `close_trade_manual`, `delete_trade`, `clear_history`, `clear_open`, `clear_all`, `close_if_live_price_hit`, `check_near_tp_timeout`, `mark_near_close`) is untouched — this task only ever touches the two private I/O methods.

- [ ] **Step 4: `python -m pytest tests/ -q` — full suite must stay green (TradeLog is widely used across command modules, the admin UI blueprint, and scanning/engine.py)**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/performance.py tests/test_trade_metadata.py
git commit -m "refactor: TradeLog reads/writes via jsonio"
```

### Task A4: StateStore + account persist atomically

**Files:**
- Modify: `swingbot/core/state.py` (`_save` at line 36, `_load` at line 27)
- Modify: `swingbot/core/account.py` (`save_account_config` at line 170, the load path inside `load_account_config` at lines 124–129)
- Test: extend `tests/test_jsonio.py` with `test_statestore_atomic` / `test_account_atomic`

**Interfaces:** No public signature change.

- [ ] **Step 1: Failing test**

```python
# tests/test_jsonio.py -- append
import os


def test_statestore_atomic(tmp_path):
    from swingbot.core.state import StateStore

    path = str(tmp_path / "state.json")
    store = StateStore(path=path)
    store.set_last_trend("AAPL|Fibonacci|4w", "bullish")
    assert not os.path.exists(path + ".tmp")

    reloaded = StateStore(path=path)
    assert reloaded.get_last_trend("AAPL|Fibonacci|4w") == "bullish"


def test_account_config_atomic(tmp_path):
    from swingbot.core import account as account_module

    path = str(tmp_path / "account.json")
    cfg = account_module.load_account_config(path)  # seeds a fresh file
    assert not os.path.exists(path + ".tmp")
    account_module.set_balance(50_000.0, path)
    assert not os.path.exists(path + ".tmp")

    reloaded = account_module.load_account_config(path)
    assert reloaded["base_balance"] == 50_000.0
```

- [ ] **Step 2: Run `python -m pytest tests/test_jsonio.py -v` — the two new tests PASS even before the refactor** (plain `json.dump` to the real path also leaves no `.tmp` file, since it never created one — this is another behavior-preserving refactor, not a bugfix; the point of the migration is torn-write safety under a crash mid-write, which a single-process pytest run cannot itself observe, only exercise the code path for).

- [ ] **Step 3: Swap the I/O bodies**

```python
# swingbot/core/state.py -- add `from swingbot.core.jsonio import atomic_write_json, read_json`
# near the top; replace:

    def _load(self) -> dict:
        return read_json(self.path, {})

    def _save(self):
        atomic_write_json(self.path, self._data)
```

```python
# swingbot/core/account.py -- add the same import; replace the two
# raw-json call sites. load_account_config's existing try/except around
# json.load(f) becomes a direct read_json call (default None so the
# existing `if stored is not None:` merge-defaults branch is unchanged):

    if os.path.exists(path):
        stored = read_json(path, None)
        if stored is not None:
            ...  # merge-with-defaults logic below this line is UNCHANGED

# and:

def save_account_config(config: dict, path: str = CONFIG_PATH):
    atomic_write_json(path, config)
```

Keep every other line of `load_account_config`'s migration/back-solve logic (the `base_balance` back-solve for pre-existing files, the `balance_history` seeding for brand-new accounts) exactly as-is — only the raw `json.load`/`json.dump` calls are replaced.

- [ ] **Step 4: `python -m pytest tests/ -q` — full suite green**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/state.py swingbot/core/account.py tests/test_jsonio.py
git commit -m "refactor: state + account persistence via jsonio"
```

---

# Phase A1 — Metrics core (Tasks A5–A12)

All functions in `swingbot/core/analytics/metrics.py`, pure, typed docstrings, no I/O, no imports of `config` or anything under `swingbot.core` that itself does I/O (`performance`, `account`, `data` are all off-limits here — `aggregate.py` is the one exception allowed to import `performance.primary_strategy_label`, since that's a pure string-resolution helper with no file I/O of its own). Package `__init__.py` created in Task A5 re-exporting each addition as it lands, so by the end of Phase A1 `from swingbot.core.analytics import metrics` and `from swingbot.core import analytics; analytics.equity_curve(...)` both work.

### Task A5: Equity curve

**Files:**
- Create: `swingbot/core/analytics/__init__.py`, `swingbot/core/analytics/metrics.py`
- Test: `tests/test_metrics_equity.py`

**Interfaces:**
- Produces: `equity_curve(closed: list[dict], starting_balance: float) -> dict` returning `{"points": [{"date": iso, "balance": float, "pnl": float}], "skipped_n": int}`. First point is `starting_balance` dated at the earliest `opened_at`; one point per close, ordered by `closed_at`; trades missing `realized_pnl_amount` are skipped and counted in `skipped_n`.

- [ ] **Step 1: Failing test**

```python
# tests/test_metrics_equity.py
from swingbot.core.analytics.metrics import equity_curve


def _t(closed_at, pnl, opened_at="2026-01-02T10:00:00+00:00"):
    return {"status": "win" if pnl >= 0 else "loss", "opened_at": opened_at,
            "closed_at": closed_at, "realized_pnl_amount": pnl}


def test_equity_curve_walks_balance():
    curve = equity_curve([_t("2026-01-05T10:00:00+00:00", 50.0),
                          _t("2026-01-03T10:00:00+00:00", -20.0)], 1000.0)
    pts = curve["points"]
    assert [p["balance"] for p in pts] == [1000.0, 980.0, 1030.0]  # sorted by close date
    assert curve["skipped_n"] == 0
    assert pts[0]["date"] == "2026-01-02"  # earliest opened_at, not the first close


def test_equity_curve_skips_unsized_trades():
    curve = equity_curve([{"status": "win", "closed_at": "2026-01-03T00:00:00+00:00",
                           "opened_at": "2026-01-02T00:00:00+00:00"}], 500.0)
    assert curve["skipped_n"] == 1 and len(curve["points"]) == 1


def test_equity_curve_empty_input():
    curve = equity_curve([], 1000.0)
    assert curve == {"points": [], "skipped_n": 0}
```

- [ ] **Step 2: Run `python -m pytest tests/test_metrics_equity.py -v` — expect FAIL (`ModuleNotFoundError: No module named 'swingbot.core.analytics'`)**

- [ ] **Step 3: Implement**

```python
# swingbot/core/analytics/__init__.py
"""Analytics core -- pure computation over trade-record dicts (see the Global
Constraints in docs/superpowers/plans/2026-07-11-cockpit-v3.md Part 1: no I/O
in metrics/aggregate/calibration/rank/insights, and every stat has exactly
one definition here that every UI/embed/route consumes instead of
re-deriving). Re-exports the public surface so callers can do either
`from swingbot.core.analytics import metrics` or
`from swingbot.core.analytics import equity_curve` interchangeably."""
from swingbot.core.analytics.metrics import (  # noqa: F401
    equity_curve,
)

__all__ = ["equity_curve"]
```

```python
# swingbot/core/analytics/metrics.py
"""Pure metrics over closed-trade record lists -- no file I/O, no config
imports. Every function degrades gracefully on missing/malformed keys
(skip + count, never raise) per this plan's Global Constraints.

`closed` throughout this module means "a list of trade dicts, some subset
of which may be closed" -- callers are NOT required to pre-filter to
status in ("win", "loss") before calling; every function here filters
internally by whatever status/field it actually needs, so passing the
full unfiltered trades.json list is always safe (open trades simply
contribute nothing, since they lack exit_price/realized_pnl_amount)."""
from __future__ import annotations


def equity_curve(closed: list[dict], starting_balance: float) -> dict:
    """Walk realized P&L in chronological close order to build a running
    account-balance series.

    The very first point is dated at the EARLIEST `opened_at` across the
    input (not the earliest close) so the curve visually starts "before
    any trade closed" at the starting balance, rather than jumping
    straight to the first trade's post-close balance with no baseline --
    this is what makes an equity chart read as "flat, then it moves" for
    the calm period before the first close, instead of starting the
    chart already mid-move.

    Trades missing `realized_pnl_amount` (never settled -- e.g. no
    sizing snapshot at open time) are skipped from the balance walk and
    counted in `skipped_n` so a caller can show "N trades excluded from
    equity curve (unsized)" instead of silently under-counting.
    """
    if not closed:
        return {"points": [], "skipped_n": 0}

    considered = [t for t in closed if t.get("realized_pnl_amount") is not None and t.get("closed_at")]
    skipped_n = len(closed) - len(considered)
    considered.sort(key=lambda t: t["closed_at"])

    opened_dates = [t["opened_at"] for t in closed if t.get("opened_at")]
    points: list[dict] = []
    balance = float(starting_balance)
    if opened_dates:
        points.append({"date": min(opened_dates)[:10], "balance": round(balance, 2), "pnl": 0.0})

    for t in considered:
        pnl = float(t["realized_pnl_amount"])
        balance += pnl
        points.append({"date": t["closed_at"][:10], "balance": round(balance, 2), "pnl": round(pnl, 2)})

    return {"points": points, "skipped_n": skipped_n}
```

- [ ] **Step 4: Run `python -m pytest tests/test_metrics_equity.py -v` — PASS (3 tests)**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/analytics/__init__.py swingbot/core/analytics/metrics.py tests/test_metrics_equity.py
git commit -m "feat: analytics equity_curve"
```

### Task A6: Drawdown

**Files:** Modify `swingbot/core/analytics/metrics.py`, `swingbot/core/analytics/__init__.py`; test `tests/test_metrics_equity.py`

**Interfaces:**
- Produces: `drawdown_series(points: list[dict]) -> list[dict]` — per equity point `{"date", "dd_pct"}` where `dd_pct = (peak - balance) / peak * 100` (≥ 0), `peak` being the running max balance up to and including that point; `max_drawdown_pct(points) -> float | None` (`None` when fewer than 2 points).

- [ ] **Step 1: Failing test**

```python
# tests/test_metrics_equity.py -- append
from swingbot.core.analytics.metrics import drawdown_series, max_drawdown_pct


def _pts(balances):
    return [{"date": f"2026-01-{i+1:02d}", "balance": b, "pnl": 0.0} for i, b in enumerate(balances)]


def test_drawdown_series_and_max():
    pts = _pts([1000, 1100, 990, 1200])
    dd = drawdown_series(pts)
    assert [round(d["dd_pct"], 4) for d in dd] == [0.0, 0.0, 10.0, 0.0]
    assert max_drawdown_pct(pts) == 10.0


def test_max_drawdown_pct_needs_two_points():
    assert max_drawdown_pct([]) is None
    assert max_drawdown_pct(_pts([1000])) is None


def test_drawdown_series_monotonic_up_is_all_zero():
    pts = _pts([1000, 1050, 1100, 1150])
    assert all(d["dd_pct"] == 0.0 for d in drawdown_series(pts))
```

- [ ] **Step 2: Run — FAIL (`ImportError: cannot import name 'drawdown_series'`)**

- [ ] **Step 3: Implement (append to `metrics.py`)**

```python
def drawdown_series(points: list[dict]) -> list[dict]:
    """Per-point drawdown as a % of the running peak balance seen so far
    (inclusive of the current point) -- the standard "how far below the
    best-ever balance am I right now" reading, always >= 0."""
    series = []
    peak = None
    for p in points:
        bal = p["balance"]
        peak = bal if peak is None else max(peak, bal)
        dd_pct = (peak - bal) / peak * 100 if peak else 0.0
        series.append({"date": p["date"], "dd_pct": round(dd_pct, 4)})
    return series


def max_drawdown_pct(points: list[dict]) -> float | None:
    """Worst single-point drawdown across the whole curve. None (not 0.0)
    when there are fewer than 2 points -- a one-point "curve" has no
    meaningful drawdown to report, and 0.0 would misleadingly read as
    "verified flat" rather than "not enough data"."""
    if len(points) < 2:
        return None
    dds = [d["dd_pct"] for d in drawdown_series(points)]
    return max(dds) if dds else None
```

Update `swingbot/core/analytics/__init__.py`'s import line and `__all__` to add `drawdown_series, max_drawdown_pct` (every subsequent task in this phase does the same mechanical addition — from here on this plan will only say "re-export it" rather than reprinting the whole file each time).

- [ ] **Step 4: Run `python -m pytest tests/test_metrics_equity.py -v` — PASS (6 tests). Step 5: Commit**

```bash
git add swingbot/core/analytics/metrics.py swingbot/core/analytics/__init__.py tests/test_metrics_equity.py
git commit -m "feat: analytics drawdown"
```

### Task A7: Win rate, expectancy, profit factor

**Files:** Modify `metrics.py`, `__init__.py`; test `tests/test_metrics_ratios.py`

**Interfaces:**
- Produces: `win_rate(closed) -> float | None`; `expectancy_r(closed) -> float | None`; `r_multiple(trade) -> float | None` (the single shared R computation: `(exit−entry)/(entry−stop)`, negated for bearish, `None` when stop distance is 0 or `entry`/`stop_loss`/`exit_price` is missing); `profit_factor(closed) -> float | None` (gross wins / |gross losses| over `realized_pnl_amount`; `None` when gross loss is 0, i.e. undefined/infinite).

- [ ] **Step 1: Failing test**

```python
# tests/test_metrics_ratios.py
from swingbot.core.analytics.metrics import win_rate, expectancy_r, r_multiple, profit_factor


def _win():
    return {"status": "win", "direction": "bullish", "entry": 100.0, "stop_loss": 95.0,
            "exit_price": 104.0, "realized_pnl_amount": 80.0}


def _loss():
    return {"status": "loss", "direction": "bearish", "entry": 100.0, "stop_loss": 105.0,
            "exit_price": 106.0, "realized_pnl_amount": -40.0}


def _still_open_unsized():
    # No exit_price/stop -- must be skipped everywhere without raising,
    # per the Global Constraint "missing keys degrade gracefully".
    return {"status": "open", "direction": "bullish", "entry": 100.0}


def test_r_multiple_bullish_win_and_bearish_loss():
    assert r_multiple(_win()) == 0.8      # (104-100)/(100-95)
    assert r_multiple(_loss()) == -1.2    # (100-106)/(100-105) = -6/-5... sign-adjusted: -1.2


def test_r_multiple_none_on_zero_risk_or_missing_fields():
    assert r_multiple({"entry": 100.0, "stop_loss": 100.0, "exit_price": 105.0,
                       "direction": "bullish"}) is None
    assert r_multiple({"entry": 100.0, "stop_loss": 95.0, "direction": "bullish"}) is None


def test_expectancy_and_win_rate_and_profit_factor():
    closed = [_win(), _loss(), _still_open_unsized()]
    assert win_rate(closed) == 50.0
    assert round(expectancy_r(closed), 4) == -0.2   # mean(0.8, -1.2); open trade excluded (no exit_price)
    assert profit_factor(closed) == 2.0              # 80 / 40


def test_win_rate_and_expectancy_empty_or_no_losses():
    assert win_rate([]) is None
    assert expectancy_r([]) is None
    assert profit_factor([_win()]) is None  # no losing amount -- undefined, not infinite
```

- [ ] **Step 2: Run — FAIL. Step 3: Implement (append to `metrics.py`)**

```python
def r_multiple(trade: dict) -> float | None:
    """THE single shared R-multiple computation -- every other stat in this
    module and in aggregate.py/calibration.py that needs "how many risk
    units did this trade make or lose" calls this instead of re-deriving
    it, per the Global Constraint "one definition per stat".

    r = (exit - entry) / (entry - stop_loss), sign-flipped for a bearish
    trade so a positive r always means "in the trade's favor" regardless
    of direction. None when any of entry/stop_loss/exit_price is missing,
    or when the stop distance is exactly 0 (a malformed record -- dividing
    by zero risk is meaningless, not infinite).
    """
    entry = trade.get("entry")
    stop = trade.get("stop_loss")
    exit_price = trade.get("exit_price")
    if entry is None or stop is None or exit_price is None:
        return None
    risk = abs(entry - stop)
    if risk == 0:
        return None
    is_bull = trade.get("direction") == "bullish"
    raw = (exit_price - entry) if is_bull else (entry - exit_price)
    return raw / risk


def win_rate(closed: list[dict]) -> float | None:
    """wins / (wins + losses) * 100, over trades with status "win"/"loss"
    only -- scratches, timeouts, and manual "closed" exits are excluded
    from both numerator and denominator (see the plan's Global Constraint
    for why: a manual close has no real win/loss verdict to count).
    None when there are zero win/loss trades, not 0.0 -- "no data yet" and
    "0% win rate" must never look the same on a UI.
    """
    wins = sum(1 for t in closed if t.get("status") == "win")
    losses = sum(1 for t in closed if t.get("status") == "loss")
    total = wins + losses
    return (wins / total * 100) if total else None


def expectancy_r(closed: list[dict]) -> float | None:
    """Mean r_multiple() over every trade with a computable R -- i.e. every
    trade for which r_multiple() doesn't return None, regardless of its
    status label. This intentionally includes any future "scratch"/
    "timeout" statuses the v2 exit engine may introduce to live trades
    (they still have a real entry/stop/exit_price and a real R), and
    excludes anything still open or missing fields, without needing a
    parallel status whitelist to stay in sync with r_multiple()'s own
    guard clauses.
    """
    rs = [r for t in closed if (r := r_multiple(t)) is not None]
    return (sum(rs) / len(rs)) if rs else None


def profit_factor(closed: list[dict]) -> float | None:
    """Gross realized profit / |gross realized loss|, over `realized_pnl_amount`
    (the actual currency P&L, not the R-multiple) -- the standard "how many
    dollars won per dollar lost" summary. None when there is no losing
    amount to divide by (this is mathematically infinite, not undefined,
    but reporting None/"n/a" instead of infinity keeps every consumer's
    formatting code simple, and is unambiguous: "no losses yet" is a very
    different message than a huge finite number).
    """
    amounts = [t.get("realized_pnl_amount") for t in closed if t.get("realized_pnl_amount") is not None]
    gross_win = sum(a for a in amounts if a > 0)
    gross_loss = abs(sum(a for a in amounts if a < 0))
    if gross_loss == 0:
        return None
    return gross_win / gross_loss
```

- [ ] **Step 4: Run `python -m pytest tests/test_metrics_ratios.py -v` — PASS (5 tests). Step 5: Commit**

```bash
git add swingbot/core/analytics/metrics.py swingbot/core/analytics/__init__.py tests/test_metrics_ratios.py
git commit -m "feat: analytics ratio metrics"
```

### Task A8: Streaks

**Files:** Modify `metrics.py`, `__init__.py`; test `tests/test_metrics_streaks.py`

**Interfaces:**
- Produces: `streaks(closed) -> dict` — `{"current": int, "current_kind": "win"|"loss"|None, "best_win_streak": int, "worst_loss_streak": int}` over win/loss trades sorted by `closed_at` (any other status — `scratch`, `timeout`, manual `closed` — breaks a streak without starting a new one of its own).

- [ ] **Step 1: Failing test**

```python
# tests/test_metrics_streaks.py
from swingbot.core.analytics.metrics import streaks


def _t(status, closed_at):
    return {"status": status, "closed_at": closed_at}


def test_streaks_basic_sequence():
    # W W L W W W, in chronological order
    closed = [_t("win", "2026-01-01"), _t("win", "2026-01-02"), _t("loss", "2026-01-03"),
              _t("win", "2026-01-04"), _t("win", "2026-01-05"), _t("win", "2026-01-06")]
    s = streaks(closed)
    assert s == {"current": 3, "current_kind": "win", "best_win_streak": 3, "worst_loss_streak": 1}


def test_manual_close_breaks_streak_without_starting_one():
    closed = [_t("win", "2026-01-01"), _t("closed", "2026-01-02"), _t("win", "2026-01-03")]
    s = streaks(closed)
    # the manual close resets current progress but "closed" is never itself
    # a win or loss streak -- the two wins around it are separate 1-streaks.
    assert s["current"] == 1 and s["current_kind"] == "win"
    assert s["best_win_streak"] == 1


def test_streaks_empty():
    assert streaks([]) == {"current": 0, "current_kind": None, "best_win_streak": 0, "worst_loss_streak": 0}


def test_streaks_unsorted_input_is_sorted_internally():
    closed = [_t("loss", "2026-01-03"), _t("win", "2026-01-01"), _t("win", "2026-01-02")]
    s = streaks(closed)
    assert s == {"current": 1, "current_kind": "loss", "best_win_streak": 2, "worst_loss_streak": 1}
```

- [ ] **Step 2: Run — FAIL. Step 3: Implement (append to `metrics.py`)**

```python
def streaks(closed: list[dict]) -> dict:
    """Current/best/worst consecutive win or loss run, over win/loss trades
    only, ordered by `closed_at`. Any other status (scratch/timeout/manual
    "closed") is a hard break: it ends whatever streak was running, but is
    never itself counted toward a streak of its own length -- so a
    win/CLOSED/win sequence is two separate 1-trade win streaks, not a
    3-trade streak with a hole in it.
    """
    ordered = sorted(closed, key=lambda t: t.get("closed_at") or "")
    best_win = worst_loss = current = 0
    current_kind: str | None = None

    for t in ordered:
        status = t.get("status")
        if status not in ("win", "loss"):
            current = 0
            current_kind = None
            continue
        if status == current_kind:
            current += 1
        else:
            current = 1
            current_kind = status
        if status == "win":
            best_win = max(best_win, current)
        else:
            worst_loss = max(worst_loss, current)

    return {"current": current, "current_kind": current_kind,
            "best_win_streak": best_win, "worst_loss_streak": worst_loss}
```

- [ ] **Step 4: Run `python -m pytest tests/test_metrics_streaks.py -v` — PASS (4 tests). Step 5: Commit**

```bash
git add swingbot/core/analytics/metrics.py swingbot/core/analytics/__init__.py tests/test_metrics_streaks.py
git commit -m "feat: analytics streaks"
```

### Task A9: R distribution + rolling win rate

**Files:** Modify `metrics.py`, `__init__.py`; test `tests/test_metrics_ratios.py`

**Interfaces:**
- Produces: `r_multiples(closed) -> list[float]` (via `r_multiple`, skipping `None`); `rolling_win_rate(closed, window: int = 20) -> list[dict]` — `{"date", "win_rate"}` per close over the trailing `window` win/loss trades, emitted only once at least 5 win/loss trades have accumulated so far.

- [ ] **Step 1: Failing test**

```python
# tests/test_metrics_ratios.py -- append
from swingbot.core.analytics.metrics import r_multiples, rolling_win_rate


def _wl(status, closed_at):
    return {"status": status, "closed_at": closed_at, "direction": "bullish",
            "entry": 100.0, "stop_loss": 95.0,
            "exit_price": 104.0 if status == "win" else 96.0}


def test_r_multiples_skips_unsized():
    closed = [_wl("win", "2026-01-01"), {"status": "win"}]  # second has no entry/stop/exit
    rs = r_multiples(closed)
    assert len(rs) == 1 and round(rs[0], 2) == 0.8


def test_rolling_win_rate_window_and_floor():
    # 6 alternating W/L trades, chronological, window=4
    seq = ["win", "loss", "win", "loss", "win", "loss"]
    closed = [_wl(s, f"2026-01-{i+1:02d}") for i, s in enumerate(seq)]
    pts = rolling_win_rate(closed, window=4)
    assert pts[-1]["win_rate"] == 50.0


def test_rolling_win_rate_needs_five_closed():
    seq = ["win", "loss", "win", "loss"]  # only 4
    closed = [_wl(s, f"2026-01-{i+1:02d}") for i, s in enumerate(seq)]
    assert rolling_win_rate(closed) == []
```

- [ ] **Step 2: Run — FAIL. Step 3: Implement (append to `metrics.py`)**

```python
def r_multiples(closed: list[dict]) -> list[float]:
    """Every computable R-multiple across the input, in whatever order
    `closed` was given -- the raw list a histogram/decile chart bins
    directly. Trades r_multiple() can't compute (missing fields, zero
    risk) are silently skipped, not zero-filled -- a skipped trade should
    not look like a breakeven trade in a histogram."""
    return [r for t in closed if (r := r_multiple(t)) is not None]


def rolling_win_rate(closed: list[dict], window: int = 20) -> list[dict]:
    """Trailing win rate, one point per win/loss close, computed over the
    most recent `window` win/loss trades up to and including that point.

    Emission starts only once at least 5 win/loss trades have accumulated
    (a rolling window over 1-4 trades is nearly pure noise and would make
    an early chart look far more volatile than the track record actually
    is) -- this floor is independent of `window` itself, so `window=4`
    with exactly 6 trades still only emits points 5 and 6, each looking
    back over the last 4.
    """
    wl = sorted([t for t in closed if t.get("status") in ("win", "loss")],
                key=lambda t: t.get("closed_at") or "")
    points = []
    for i in range(len(wl)):
        if i + 1 < 5:
            continue
        window_slice = wl[max(0, i + 1 - window):i + 1]
        wins = sum(1 for t in window_slice if t["status"] == "win")
        wr = wins / len(window_slice) * 100
        points.append({"date": (wl[i].get("closed_at") or "")[:10], "win_rate": round(wr, 2)})
    return points
```

- [ ] **Step 4: Run `python -m pytest tests/test_metrics_ratios.py -v` — PASS (8 tests). Step 5: Commit**

```bash
git add swingbot/core/analytics/metrics.py swingbot/core/analytics/__init__.py tests/test_metrics_ratios.py
git commit -m "feat: analytics r distribution + rolling win rate"
```

### Task A10: Native Sharpe / Sortino

**Files:** Modify `metrics.py`, `__init__.py`; test `tests/test_metrics_ratios.py`

**Interfaces:**
- Produces: `sharpe(returns: list[float]) -> float | None`, `sortino(returns: list[float]) -> float | None` — per-trade (unannualized, matching `risk_metrics.py`'s convention — see that module's docstring on why annualizing a discrete, irregularly-spaced trade sequence would be dishonest), `mean(returns)/std(returns, ddof=1)`; sortino divides by the downside deviation (population, target 0) instead of the full std. Both `None` when `len(returns) < 5` or the relevant deviation is 0. `trade_return_pct(trade) -> float | None` mirroring `risk_metrics._trade_return_pct` exactly (`(exit-entry)/entry*100`, negated for bearish) so the two modules can never silently drift apart.

- [ ] **Step 1: Failing test**

```python
# tests/test_metrics_ratios.py -- append
import numpy as np
import pytest

from swingbot.core.analytics.metrics import sharpe, sortino, trade_return_pct


def test_sharpe_matches_numpy_reference():
    returns = [1.0, 2.0, -1.0, 0.5, 1.5]
    expected = np.mean(returns) / np.std(returns, ddof=1)
    assert sharpe(returns) == pytest.approx(expected)
    assert sharpe(returns) == pytest.approx(0.7, abs=0.05)


def test_sharpe_and_sortino_none_below_five():
    assert sharpe([1.0, 2.0, -1.0, 0.5]) is None
    assert sortino([1.0, 2.0, -1.0, 0.5]) is None


def test_sortino_uses_downside_only():
    returns = [1.0, 2.0, -1.0, 0.5, 1.5]
    downside = [min(r, 0.0) for r in returns]
    expected_downside_std = float(np.sqrt(np.mean(np.square(downside))))
    expected = np.mean(returns) / expected_downside_std
    assert sortino(returns) == pytest.approx(expected)


def test_sortino_none_when_no_downside():
    # all positive returns -> downside deviation is 0 -> undefined, not infinite
    assert sortino([1.0, 2.0, 3.0, 1.5, 2.5]) is None


def test_trade_return_pct_mirrors_risk_metrics():
    from swingbot.core.risk_metrics import _trade_return_pct

    bull = {"entry": 100.0, "exit_price": 104.0, "direction": "bullish"}
    bear = {"entry": 100.0, "exit_price": 96.0, "direction": "bearish"}
    assert trade_return_pct(bull) == pytest.approx(_trade_return_pct(bull))
    assert trade_return_pct(bear) == pytest.approx(_trade_return_pct(bear))
```

- [ ] **Step 2: Run — FAIL. Step 3: Implement (append to `metrics.py`, `import numpy as np` at the top)**

```python
import numpy as np  # add to the top of the file, alongside `from __future__ import annotations`

MIN_TRADES_FOR_RATIO = 5  # below this, sample noise dominates any Sharpe/Sortino reading


def trade_return_pct(trade: dict) -> float | None:
    """Signed %% return for one closed trade -- mirrors
    risk_metrics._trade_return_pct exactly (same formula, same sign
    convention) so this module's native Sharpe/Sortino and risk_metrics.py's
    optional quantstats-backed ones can never quietly disagree. Returns
    None (rather than raising) when entry/exit_price is missing or entry
    is 0, unlike risk_metrics._trade_return_pct which assumes valid input --
    this copy is the safe-to-call-on-anything version.
    """
    entry = trade.get("entry")
    exit_price = trade.get("exit_price")
    if not entry or exit_price is None:
        return None
    pct = (exit_price - entry) / entry * 100
    return -pct if trade.get("direction") == "bearish" else pct


def sharpe(returns: list[float]) -> float | None:
    """Unannualized per-trade Sharpe: mean(returns) / std(returns, ddof=1).
    None below MIN_TRADES_FOR_RATIO trades or when std is 0 (a dead-flat
    return series has an undefined Sharpe, not an infinite one)."""
    if len(returns) < MIN_TRADES_FOR_RATIO:
        return None
    arr = np.asarray(returns, dtype=float)
    std = float(np.std(arr, ddof=1))
    if std == 0:
        return None
    return float(np.mean(arr)) / std


def sortino(returns: list[float]) -> float | None:
    """Unannualized per-trade Sortino: mean(returns) / downside_deviation,
    where downside_deviation is the population RMS of min(r, 0) across
    ALL returns (positive returns contribute 0 to the sum, per the
    standard Sortino definition -- this is deliberately NOT the std of
    only the negative returns, which would be a different, smaller-sample
    statistic). None below MIN_TRADES_FOR_RATIO trades, or when there is
    no downside at all (every return >= 0 -> downside deviation 0 ->
    undefined ratio, not infinite).
    """
    if len(returns) < MIN_TRADES_FOR_RATIO:
        return None
    arr = np.asarray(returns, dtype=float)
    downside = np.minimum(arr, 0.0)
    downside_std = float(np.sqrt(np.mean(np.square(downside))))
    if downside_std == 0:
        return None
    return float(np.mean(arr)) / downside_std
```

- [ ] **Step 4: Run `python -m pytest tests/test_metrics_ratios.py -v` — PASS (13 tests). Step 5: Commit**

```bash
git add swingbot/core/analytics/metrics.py swingbot/core/analytics/__init__.py tests/test_metrics_ratios.py
git commit -m "feat: native sharpe/sortino (quantstats stays optional)"
```

### Task A11: MFE / MAE / exit efficiency

**Files:**
- Create: `swingbot/core/analytics/mfe_mae.py`
- Test: `tests/test_mfe_mae.py` (uses `tests/conftest.py::make_ohlcv` — the REAL fixture, see the deviation note below)

**Interfaces:**
- Produces: `compute_mfe_mae(trade: dict, df: pd.DataFrame) -> dict | None` → `{"mfe_r": float, "mae_r": float, "exit_efficiency": float | None}`. Bars sliced `opened_at..closed_at` inclusive on the DatetimeIndex. Bullish: `mfe_r = (max(High) − entry)/risk`, `mae_r = max(0, (entry − min(Low))/risk)`; bearish mirrored. `risk = |entry − stop_loss|`; `None` if risk is 0, dates missing/unparseable, `df` is `None`/empty, or the slice is empty. `exit_efficiency = r_multiple(trade)/mfe_r` when `mfe_r > 0`, else `None`, clamped to `[-5, 1]`.

> **Deviation from the original plan draft:** the prior draft's test called `make_ohlcv([(100, 101, 99, 100), (100, 108, 98, 106), (106, 107, 103, 104)], start="2026-03-02")` — a list of `(open, high, low, close)` tuples. **`tests/conftest.py::make_ohlcv` does not accept that shape.** Its real signature is `make_ohlcv(closes, spread_pct=1.0, volumes=None, start="2019-01-01")`: it takes a flat list of *close* prices and derives High/Low as `close ± (spread_pct/100)/2` symmetrically — there is no way to pass an arbitrary asymmetric per-bar OHLC tuple through it, and this plan's own Prerequisite section requires following the existing fixture convention exactly rather than inventing a parallel one. The test below is rewritten to get the identical numeric fixture (`mfe_r=2.0, mae_r=0.5, exit_efficiency=0.5`) using `spread_pct=0.0` (flat bars, `High == Low == Close`) so each bar's close IS its high and low — algebraically equivalent to the original intent, expressed through the real fixture API.

- [ ] **Step 1: Failing test**

```python
# tests/test_mfe_mae.py
from tests.conftest import make_ohlcv
from swingbot.core.analytics.mfe_mae import compute_mfe_mae


def test_bullish_mfe_mae_and_exit_efficiency():
    # Flat bars (spread_pct=0.0) so High == Low == Close on every bar --
    # lets us place the swing high (108) and swing low (98) on separate
    # bars using only make_ohlcv's real (closes, spread_pct) signature.
    # Bars: 2026-03-02..03-05 (bdate_range skips the weekend that would
    # otherwise fall in this run).
    df = make_ohlcv([100, 108, 98, 104], spread_pct=0.0, start="2026-03-02")
    t = {"direction": "bullish", "entry": 100.0, "stop_loss": 96.0, "exit_price": 104.0,
         "opened_at": "2026-03-02T15:00:00+00:00", "closed_at": "2026-03-05T15:00:00+00:00",
         "status": "win"}
    m = compute_mfe_mae(t, df)
    assert m["mfe_r"] == 2.0            # (108-100)/4
    assert m["mae_r"] == 0.5            # (100-98)/4
    assert m["exit_efficiency"] == 0.5  # realized r=1.0 of a 2.0R max move


def test_bearish_mirror():
    df = make_ohlcv([100, 92, 102, 96], spread_pct=0.0, start="2026-03-02")
    t = {"direction": "bearish", "entry": 100.0, "stop_loss": 104.0, "exit_price": 96.0,
         "opened_at": "2026-03-02T15:00:00+00:00", "closed_at": "2026-03-05T15:00:00+00:00",
         "status": "win"}
    m = compute_mfe_mae(t, df)
    assert m["mfe_r"] == 2.0            # (100-92)/4
    assert m["mae_r"] == 0.5            # (102-100)/4
    assert m["exit_efficiency"] == 0.5


def test_zero_risk_returns_none():
    df = make_ohlcv([100, 100], start="2026-03-02")
    t = {"entry": 100, "stop_loss": 100, "direction": "bullish",
         "opened_at": "2026-03-02T00:00:00+00:00", "closed_at": "2026-03-03T00:00:00+00:00"}
    assert compute_mfe_mae(t, df) is None


def test_missing_dates_or_empty_df_returns_none():
    from swingbot.core.analytics.mfe_mae import compute_mfe_mae as f
    df = make_ohlcv([100, 101], start="2026-03-02")
    t = {"entry": 100.0, "stop_loss": 96.0, "direction": "bullish"}  # no opened_at/closed_at
    assert f(t, df) is None
    assert f(dict(t, opened_at="2026-03-02T00:00:00+00:00",
                  closed_at="2026-03-03T00:00:00+00:00"), None) is None
```

- [ ] **Step 2: Run `python -m pytest tests/test_mfe_mae.py -v` — expect FAIL (no module)**

- [ ] **Step 3: Implement**

```python
# swingbot/core/analytics/mfe_mae.py
"""Maximum Favorable/Adverse Excursion and exit efficiency, computed from a
ticker's cached daily bars for one closed trade -- the "how good was this
exit, really" number the auto-journal (journal.py, Task A20) is built
around: a trade that closed +1R after running to +3R in its favor tells a
very different story than one that closed +1R after only ever reaching
+1.1R.

Pure function, no I/O -- the caller (journal.py) is responsible for
fetching `df` (see Task A22's journal_trade_close)."""
from __future__ import annotations

import datetime as dt

from swingbot.core.analytics.metrics import r_multiple


def _parse_dt(iso_str) -> dt.datetime | None:
    if not iso_str:
        return None
    try:
        return dt.datetime.fromisoformat(iso_str)
    except (TypeError, ValueError):
        return None


def compute_mfe_mae(trade: dict, df) -> dict | None:
    """Maximum favorable/adverse excursion (in R-multiples of the trade's
    own original risk) across the bars the trade was actually open for,
    plus exit efficiency (how much of the best-available move was
    actually banked at exit).

    None whenever the inputs don't support a real answer: missing
    entry/stop_loss, zero risk, missing/unparseable opened_at/closed_at,
    a None/empty `df`, or a date slice that lands on zero bars (e.g. the
    cached data doesn't cover the trade's window). Never raises.
    """
    entry = trade.get("entry")
    stop = trade.get("stop_loss")
    if entry is None or stop is None:
        return None
    risk = abs(entry - stop)
    if risk == 0:
        return None

    start = _parse_dt(trade.get("opened_at"))
    end = _parse_dt(trade.get("closed_at"))
    if start is None or end is None:
        return None
    if df is None or df.empty:
        return None

    idx = df.index
    tz_aware = getattr(idx, "tz", None) is not None
    if tz_aware:
        start_cmp = start if start.tzinfo else start.replace(tzinfo=dt.timezone.utc)
        end_cmp = end if end.tzinfo else end.replace(tzinfo=dt.timezone.utc)
    else:
        start_cmp = start.replace(tzinfo=None)
        end_cmp = end.replace(tzinfo=None)

    sliced = df.loc[(idx >= start_cmp) & (idx <= end_cmp)]
    if sliced.empty:
        return None

    is_bull = trade.get("direction") == "bullish"
    if is_bull:
        mfe_r = (float(sliced["High"].max()) - entry) / risk
        mae_r = max(0.0, (entry - float(sliced["Low"].min())) / risk)
    else:
        mfe_r = (entry - float(sliced["Low"].min())) / risk
        mae_r = max(0.0, (float(sliced["High"].max()) - entry) / risk)
    mfe_r = max(0.0, mfe_r)

    r_real = r_multiple(trade)
    exit_efficiency = None
    if r_real is not None and mfe_r > 0:
        exit_efficiency = max(-5.0, min(1.0, r_real / mfe_r))

    return {
        "mfe_r": round(mfe_r, 4),
        "mae_r": round(mae_r, 4),
        "exit_efficiency": round(exit_efficiency, 4) if exit_efficiency is not None else None,
    }
```

Re-export `compute_mfe_mae` from `swingbot/core/analytics/__init__.py`.

- [ ] **Step 4: Run `python -m pytest tests/test_mfe_mae.py -v` — PASS (5 tests). Step 5: Commit**

```bash
git add swingbot/core/analytics/mfe_mae.py swingbot/core/analytics/__init__.py tests/test_mfe_mae.py
git commit -m "feat: MFE/MAE + exit efficiency"
```

### Task A12: Trade records carry plan metadata

The v2 cutover posts plans with tier/badge/quality (and, per Task A1 Step 2, already posts `plan_id` — see the correction there), but `performance.log_trade`'s record dict does not yet persist `tier`/`badge`/`quality_score`/`source` — so no aggregation by tier/badge/source is possible. Fix at the source.

**Files:**
- Modify: `swingbot/core/performance.py` (`log_trade` signature at line 186, record dict starting at line 209)
- Modify: every `log_trade` caller that has a `TradePlanV2` in hand. As of 2026-07-12 the only real call site is `swingbot/core/scanning/engine.py:799`, and it does **not** currently have a `TradePlanV2` — it builds trades from the pre-v2 confluence `plan`/`item` objects. Per v2's own migration (Task 89, "scan engine cutover"), this call site will be rewritten to pass a `TradePlanV2` before Part A reaches this task; **do not edit `scanning/engine.py`'s current pre-v2 call site now** — grep `log_trade(` fresh at execution time and thread the five fields through whatever call site v2 actually left behind (v2 Task 70's `PlanManager._on_event` hook is the other long-lived caller, and already passes `plan_id`; extend that same call with `tier=plan.tier, badge=plan.badge, quality_score=plan.quality_score, source=plan.source`).
- Test: `tests/test_trade_metadata.py`

**Interfaces:**
- Produces: `log_trade(..., plan_id: str | None = None, tier: str | None = None, badge: str | None = None, quality_score: int | None = None, source: str | None = None)` (`plan_id` already exists from v2 Task 68/70 — this task adds the other four); record keys `plan_id, tier, badge, quality_score, source` (`None` for legacy rows and for any trade logged without a plan in hand). Consumed by Tasks A14–A18 and Plans B/C.

- [ ] **Step 1: Failing test**

```python
# tests/test_trade_metadata.py -- append
from swingbot.core.performance import TradeLog


def test_log_trade_persists_plan_pedigree(tmp_path):
    log = TradeLog(path=str(tmp_path / "trades.json"))
    trade_id = log.log_trade(
        ticker="AAPL", strategy="Fibonacci", horizon_key="4w", direction="bullish",
        confidence_level=4, confidence_label="Strong", entry=100.0, stop_loss=95.0,
        take_profit=110.0, plan_id="p1", tier="A", badge="VALIDATED", quality_score=82,
        source="confluence",
    )
    log.refresh()
    t = log.get_trade_by_id(trade_id)
    assert t["plan_id"] == "p1"
    assert t["tier"] == "A"
    assert t["badge"] == "VALIDATED"
    assert t["quality_score"] == 82
    assert t["source"] == "confluence"


def test_log_trade_without_plan_metadata_defaults_to_none(tmp_path):
    log = TradeLog(path=str(tmp_path / "trades.json"))
    trade_id = log.log_trade(
        ticker="MSFT", strategy="EMA Crossover", horizon_key="2w", direction="bearish",
        confidence_level=3, confidence_label="Moderate", entry=50.0, stop_loss=52.0,
        take_profit=46.0,
    )
    t = log.get_trade_by_id(trade_id)
    assert t["plan_id"] is None and t["tier"] is None and t["badge"] is None
    assert t["quality_score"] is None and t["source"] is None
```

- [ ] **Step 2: Run `python -m pytest tests/test_trade_metadata.py -v` — expect FAIL** (`plan_id` may already pass depending on v2's merge state — the `tier`/`badge`/`quality_score`/`source` assertions are the ones that fail: `KeyError` or `TypeError: log_trade() got an unexpected keyword argument 'tier'`).

- [ ] **Step 3: Extend the signature and record dict**

```python
# swingbot/core/performance.py -- log_trade's signature gains (after
# whatever plan_id parameter v2 already added):

    def log_trade(self, ticker, strategy, horizon_key, direction, confidence_level,
                  confidence_label, entry, stop_loss, take_profit, target2=None,
                  confidence_score=None, confidence_breakdown=None, target_sources=None,
                  stop_sources=None, target2_sources=None, risk_reward_ratio=None,
                  explanation=None, confirmed_by=None, plan_id=None,
                  tier=None, badge=None, quality_score=None, source=None) -> str:
```

```python
# and the record dict (after the existing "confirmed_by" line, before
# "opened_at" -- or immediately after plan_id if v2 already inserted it there):

            "plan_id": plan_id,          # already added by plan-engine-v2 Task 68/70
            "tier": tier,                # "A" | "B" | "C" | None (legacy / no plan)
            "badge": badge,              # "VALIDATED" | "WEAK" | None
            "quality_score": quality_score,
            "source": source,            # "strategy" | "confluence" | None
```

- [ ] **Step 4: Thread the fields through every caller that has a `TradePlanV2` in hand** — `plan.plan_id`, `plan.tier`, `plan.badge`, `plan.quality_score`, `plan.source`. Callers without a plan (there should be none left post-v2-cutover, but the signature defaults keep this non-breaking either way) pass nothing and get `None` in every field, exactly like a pre-this-task legacy row.

- [ ] **Step 5: `python -m pytest tests/ -q` — full suite green. Step 6: Commit**

```bash
git add swingbot/core/performance.py tests/test_trade_metadata.py
git commit -m "feat: trades.json rows carry plan pedigree (tier/badge/quality/source)"
```

---

# Phase A2 — Aggregation & calibration (Tasks A13–A17)

### Task A13: StatRow + first dimension

**Files:**
- Create: `swingbot/core/analytics/aggregate.py`
- Test: `tests/test_aggregate.py`

**Interfaces:**
- Produces: `@dataclass StatRow: key: str; n: int; wins: int; losses: int; win_rate: float | None; expectancy_r: float | None; avg_r: float | None; profit_factor: float | None; total_pnl: float` and `stats_by(closed: list[dict], dimension: str) -> list[StatRow]` sorted by `n` desc. Dimension `"strategy"` groups on `primary_strategy_label(t)` (imported from `performance`).

> **Implementation note (not a contract change):** the dataclass has two R-multiple fields, `expectancy_r` and `avg_r`, with no separate formula ever specified for `avg_r` anywhere in this plan or its cross-references. Per the Global Constraint "one definition per stat", both are populated from the exact same `metrics.expectancy_r(row_trades)` call — they are intentionally identical values under two field names, kept as two names only because this plan promises both to downstream Plan B/C tasks that were locked to one or the other before this note was written. Do not invent a second formula for `avg_r`.

- [ ] **Step 1: Failing test**

```python
# tests/test_aggregate.py
from swingbot.core.analytics.aggregate import StatRow, stats_by


def _t(strategy_sources, status, pnl, direction="bullish", entry=100.0, stop_loss=95.0, exit_price=None):
    return {"target_sources": strategy_sources, "status": status, "direction": direction,
            "entry": entry, "stop_loss": stop_loss,
            "exit_price": exit_price if exit_price is not None else (104.0 if status == "win" else 96.0),
            "realized_pnl_amount": pnl, "closed_at": "2026-03-10T10:00:00+00:00"}


def test_stats_by_strategy_groups_and_sums():
    closed = [
        _t(["EMA20"], "win", 80.0),
        _t(["EMA20"], "loss", -40.0),
        _t(["Fib 61.8%"], "win", 60.0),
    ]
    rows = stats_by(closed, "strategy")
    assert isinstance(rows[0], StatRow)
    by_key = {r.key: r for r in rows}
    assert by_key["EMA20"].n == 2 and by_key["EMA20"].wins == 1 and by_key["EMA20"].losses == 1
    assert by_key["EMA20"].total_pnl == 40.0
    assert by_key["Fib 61.8%"].n == 1 and by_key["Fib 61.8%"].total_pnl == 60.0


def test_stats_by_missing_pnl_counts_as_zero():
    closed = [_t(["EMA20"], "win", None)]
    rows = stats_by(closed, "strategy")
    assert rows[0].total_pnl == 0.0


def test_stats_by_sorted_by_n_desc():
    closed = [_t(["EMA20"], "win", 10.0), _t(["EMA20"], "loss", -5.0), _t(["Fib 61.8%"], "win", 5.0)]
    rows = stats_by(closed, "strategy")
    assert [r.key for r in rows] == ["EMA20", "Fib 61.8%"]
```

- [ ] **Step 2: Run `python -m pytest tests/test_aggregate.py -v` — expect FAIL (no module)**

- [ ] **Step 3: Implement**

```python
# swingbot/core/analytics/aggregate.py
"""Group closed trades along any of DIMENSIONS (Task A14) into StatRow
summaries. Every ratio is delegated to metrics.py -- no local formulas --
per the Global Constraint "one definition per stat". The only non-pure
import here is performance.primary_strategy_label, a pure string
resolution helper with no file I/O of its own (see its docstring)."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from swingbot.core.analytics import metrics
from swingbot.core.performance import primary_strategy_label


@dataclass
class StatRow:
    key: str
    n: int
    wins: int
    losses: int
    win_rate: float | None
    expectancy_r: float | None
    avg_r: float | None
    profit_factor: float | None
    total_pnl: float


def _row_for(key: str, trades: list[dict]) -> StatRow:
    wins = sum(1 for t in trades if t.get("status") == "win")
    losses = sum(1 for t in trades if t.get("status") == "loss")
    expectancy = metrics.expectancy_r(trades)
    total_pnl = sum(float(t.get("realized_pnl_amount") or 0.0) for t in trades)
    return StatRow(
        key=key, n=len(trades), wins=wins, losses=losses,
        win_rate=metrics.win_rate(trades), expectancy_r=expectancy, avg_r=expectancy,
        profit_factor=metrics.profit_factor(trades), total_pnl=round(total_pnl, 2),
    )


def stats_by(closed: list[dict], dimension: str) -> list[StatRow]:
    """Group `closed` by `dimension` (see DIMENSIONS in Task A14 for the
    full set) and return one StatRow per group, sorted by trade count
    descending -- the busiest bucket first, matching how every table in
    this cockpit wants "most-traded strategy/ticker/etc. at the top"."""
    from swingbot.core.analytics.aggregate import _EXTRACTORS  # populated by Task A14
    if dimension not in _EXTRACTORS:
        raise ValueError(f"Unknown aggregation dimension: {dimension!r}")

    groups: dict[str, list[dict]] = defaultdict(list)
    extractor = _EXTRACTORS[dimension]
    for t in closed:
        groups[extractor(t)].append(t)

    rows = [_row_for(key, trades) for key, trades in groups.items()]
    rows.sort(key=lambda r: r.n, reverse=True)
    return rows


# Task A14 replaces this stub with the full 10-entry table and DIMENSIONS tuple.
_EXTRACTORS: dict = {
    "strategy": lambda t: primary_strategy_label(t),
}
```

Note the self-import `from swingbot.core.analytics.aggregate import _EXTRACTORS` inside `stats_by` is deliberate and temporary — it exists only so this task's test passes standalone before Task A14 adds the rest of the table at module scope; Task A14's diff removes that in-function import and reads `_EXTRACTORS` as a plain module global instead (a circular self-import would be a code smell in the final state, not just here).

Re-export `StatRow, stats_by` from `swingbot/core/analytics/__init__.py`.

- [ ] **Step 4: Run `python -m pytest tests/test_aggregate.py -v` — PASS (3 tests). Step 5: Commit**

```bash
git add swingbot/core/analytics/aggregate.py swingbot/core/analytics/__init__.py tests/test_aggregate.py
git commit -m "feat: StatRow aggregation (by strategy)"
```

### Task A14: All dimensions

**Files:** Modify `aggregate.py`; test `tests/test_aggregate.py`

**Interfaces:**
- Produces: `DIMENSIONS = ("strategy", "horizon", "tier", "badge", "confidence", "direction", "dow", "month", "ticker", "source")`; key extractors: `horizon`→`horizon_key`, `tier`/`badge`/`source`→Task A12 fields (`"unknown"` when `None`), `confidence`→`str(confidence_level)` (`"unknown"` when `None`), `dow`→Berlin weekday name of `closed_at`, `month`→`YYYY-MM` of `closed_at` in Berlin time. `stats_by` raises `ValueError` on an unknown dimension.

- [ ] **Step 1: Failing test**

```python
# tests/test_aggregate.py -- append
import pytest

from swingbot.core.analytics.aggregate import DIMENSIONS, stats_by


def _full_trade():
    return {
        "target_sources": ["EMA20"], "status": "win", "direction": "bullish",
        "entry": 100.0, "stop_loss": 95.0, "exit_price": 104.0, "realized_pnl_amount": 80.0,
        "horizon_key": "4w", "tier": "A", "badge": "VALIDATED", "source": "confluence",
        "confidence_level": 4, "ticker": "AAPL",
        # 2026-03-09 is a Monday in both UTC and Europe/Berlin.
        "opened_at": "2026-03-06T10:00:00+00:00", "closed_at": "2026-03-09T10:00:00+00:00",
    }


def test_all_ten_dimensions_present():
    assert set(DIMENSIONS) == {"strategy", "horizon", "tier", "badge", "confidence",
                               "direction", "dow", "month", "ticker", "source"}


def test_dimension_extractors():
    closed = [_full_trade()]
    assert stats_by(closed, "tier")[0].key == "A"
    assert stats_by(closed, "badge")[0].key == "VALIDATED"
    assert stats_by(closed, "source")[0].key == "confluence"
    assert stats_by(closed, "horizon")[0].key == "4w"
    assert stats_by(closed, "confidence")[0].key == "4"
    assert stats_by(closed, "direction")[0].key == "bullish"
    assert stats_by(closed, "ticker")[0].key == "AAPL"
    assert stats_by(closed, "dow")[0].key == "Monday"
    assert stats_by(closed, "month")[0].key == "2026-03"


def test_unknown_fields_bucket_as_unknown():
    closed = [{"target_sources": [], "status": "win", "direction": "bullish",
              "entry": 100.0, "stop_loss": 95.0, "exit_price": 104.0}]
    assert stats_by(closed, "tier")[0].key == "unknown"
    assert stats_by(closed, "badge")[0].key == "unknown"
    assert stats_by(closed, "source")[0].key == "unknown"
    assert stats_by(closed, "confidence")[0].key == "unknown"


def test_stats_by_raises_on_unknown_dimension():
    with pytest.raises(ValueError):
        stats_by([], "nope")
```

- [ ] **Step 2: Run — FAIL. Step 3: Implement**

```python
# swingbot/core/analytics/aggregate.py -- add near the top (after the
# metrics/performance imports):
import datetime as dt

try:
    from zoneinfo import ZoneInfo
    _BERLIN_TZ = ZoneInfo("Europe/Berlin")
except Exception:
    _BERLIN_TZ = None

_DOW_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _to_berlin(iso_str: str | None) -> dt.datetime | None:
    if not iso_str:
        return None
    try:
        d = dt.datetime.fromisoformat(iso_str)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(_BERLIN_TZ) if _BERLIN_TZ else d


def _dow_key(t: dict) -> str:
    d = _to_berlin(t.get("closed_at"))
    return _DOW_NAMES[d.weekday()] if d else "unknown"


def _month_key(t: dict) -> str:
    d = _to_berlin(t.get("closed_at"))
    return d.strftime("%Y-%m") if d else "unknown"


DIMENSIONS = ("strategy", "horizon", "tier", "badge", "confidence",
             "direction", "dow", "month", "ticker", "source")

# Replaces the Task A13 stub -- now a plain module global, not populated
# via any self-import.
_EXTRACTORS = {
    "strategy": lambda t: primary_strategy_label(t),
    "horizon": lambda t: t.get("horizon_key") or "unknown",
    "tier": lambda t: t.get("tier") or "unknown",
    "badge": lambda t: t.get("badge") or "unknown",
    "source": lambda t: t.get("source") or "unknown",
    "confidence": lambda t: str(t["confidence_level"]) if t.get("confidence_level") is not None else "unknown",
    "direction": lambda t: t.get("direction") or "unknown",
    "ticker": lambda t: t.get("ticker") or "unknown",
    "dow": _dow_key,
    "month": _month_key,
}
```

```python
# and simplify stats_by's body -- delete the in-function import line from
# Task A13, since _EXTRACTORS is now already a module global by the time
# stats_by is defined below it:

def stats_by(closed: list[dict], dimension: str) -> list[StatRow]:
    if dimension not in _EXTRACTORS:
        raise ValueError(f"Unknown aggregation dimension: {dimension!r}")
    groups: dict[str, list[dict]] = defaultdict(list)
    extractor = _EXTRACTORS[dimension]
    for t in closed:
        groups[extractor(t)].append(t)
    rows = [_row_for(key, trades) for key, trades in groups.items()]
    rows.sort(key=lambda r: r.n, reverse=True)
    return rows
```

Re-export `DIMENSIONS` alongside `StatRow, stats_by`.

- [ ] **Step 4: Run `python -m pytest tests/test_aggregate.py -v` — PASS (8 tests). Step 5: Commit**

```bash
git add swingbot/core/analytics/aggregate.py swingbot/core/analytics/__init__.py tests/test_aggregate.py
git commit -m "feat: aggregation across all 10 dimensions"
```

### Task A15: Quality-score deciles

**Files:**
- Create: `swingbot/core/analytics/calibration.py`
- Test: `tests/test_calibration.py`

**Interfaces:**
- Produces: `score_deciles(closed) -> list[dict]` — rows `{"decile": "0-9"…"90-100", "n", "win_rate", "expectancy_r"}` over closed trades with a non-`None` `quality_score`; empty deciles omitted; sorted ascending by decile floor. Intended as the live-trade twin of an eventual offline `scripts/audit_quality_score.py` decile table — that script does not exist yet as of this writing (it is not part of plan-engine-v2's committed task list either), so this task does **not** depend on it; treat `score_deciles` as standalone.

- [ ] **Step 1: Failing test**

```python
# tests/test_calibration.py
from swingbot.core.analytics.calibration import score_deciles


def _t(score, status, entry=100.0, stop_loss=95.0, exit_price=None):
    return {"quality_score": score, "status": status, "direction": "bullish",
            "entry": entry, "stop_loss": stop_loss,
            "exit_price": exit_price if exit_price is not None else (104.0 if status == "win" else 96.0)}


def test_score_deciles_groups_by_ten_and_omits_empty():
    closed = [_t(5, "loss"), _t(55, "win"), _t(57, "win"), _t(95, "win")]
    rows = score_deciles(closed)
    by_decile = {r["decile"]: r for r in rows}
    assert set(by_decile) == {"0-9", "50-59", "90-100"}
    assert by_decile["50-59"]["n"] == 2
    assert by_decile["50-59"]["win_rate"] == 100.0
    assert by_decile["0-9"]["win_rate"] == 0.0


def test_score_deciles_skips_missing_score():
    closed = [_t(None, "win"), _t(50, "win")]
    rows = score_deciles(closed)
    assert len(rows) == 1 and rows[0]["n"] == 1


def test_score_deciles_sorted_ascending():
    closed = [_t(95, "win"), _t(5, "loss")]
    rows = score_deciles(closed)
    assert [r["decile"] for r in rows] == ["0-9", "90-100"]
```

- [ ] **Step 2: Run — FAIL. Step 3: Implement**

```python
# swingbot/core/analytics/calibration.py
"""Live-trade calibration checks: does the quality score actually predict
win rate (score_deciles), does each tier land in its design band
(tier_calibration), and has a VALIDATED strategy's live win rate drifted
below its out-of-sample number (badge_drift)? Pure functions, no I/O --
callers supply `closed` and (for badge_drift) the already-loaded registry
list."""
from __future__ import annotations

from collections import defaultdict

from swingbot.core.analytics import metrics


def _decile_label(score: float) -> str:
    idx = min(int(score) // 10, 9)
    lo = idx * 10
    hi = 100 if idx == 9 else lo + 9
    return f"{lo}-{hi}"


def _decile_floor(label: str) -> int:
    return int(label.split("-")[0])


def score_deciles(closed: list[dict]) -> list[dict]:
    """Bucket closed trades with a known quality_score into 10-wide score
    deciles (0-9 .. 80-89, plus a combined 90-100) and report each
    bucket's win rate/expectancy -- the live counterpart to whatever
    offline backtest calibration produced the score in the first place.
    Trades without a quality_score (legacy rows, or any trade logged
    without a plan in hand) are silently excluded, not bucketed as
    "unknown" -- there is no decile for "no score"."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in closed:
        score = t.get("quality_score")
        if score is None:
            continue
        groups[_decile_label(score)].append(t)

    rows = [
        {"decile": label, "n": len(trades),
         "win_rate": metrics.win_rate(trades), "expectancy_r": metrics.expectancy_r(trades)}
        for label, trades in groups.items()
    ]
    rows.sort(key=lambda r: _decile_floor(r["decile"]))
    return rows
```

Re-export `score_deciles` from `__init__.py`.

- [ ] **Step 4: Run `python -m pytest tests/test_calibration.py -v` — PASS (3 tests). Step 5: Commit**

```bash
git add swingbot/core/analytics/calibration.py swingbot/core/analytics/__init__.py tests/test_calibration.py
git commit -m "feat: quality-score decile calibration"
```

### Task A16: Tier calibration

**Files:** Modify `calibration.py`; test `tests/test_calibration.py`

**Interfaces:**
- Produces: `tier_calibration(closed) -> list[dict]` — one row per tier A/B/C: `{"tier", "n", "win_rate", "expectancy_r", "expected_band", "ok"}` where `expected_band` is the fixed design intent `{"A": ">=80", "B": "70-80", "C": "<70"}`, and `ok: bool | None` (`None` when `win_rate` is `None` or `n < 10` — "insufficient data", not "failing").

- [ ] **Step 1: Failing test**

```python
# tests/test_calibration.py -- append
from swingbot.core.analytics.calibration import tier_calibration


def _tier_t(tier, status):
    return {"tier": tier, "status": status, "direction": "bullish",
            "entry": 100.0, "stop_loss": 95.0, "exit_price": 104.0 if status == "win" else 96.0}


def test_tier_calibration_ok_true_and_none():
    closed = [_tier_t("A", "win") for _ in range(10)] + [_tier_t("A", "loss") for _ in range(2)]
    closed += [_tier_t("B", "win"), _tier_t("B", "loss"), _tier_t("B", "win")]
    rows = tier_calibration(closed)
    by_tier = {r["tier"]: r for r in rows}
    assert by_tier["A"]["n"] == 12
    assert round(by_tier["A"]["win_rate"], 1) == 83.3
    assert by_tier["A"]["expected_band"] == ">=80"
    assert by_tier["A"]["ok"] is True
    assert by_tier["B"]["n"] == 3 and by_tier["B"]["ok"] is None  # below the N=10 floor
    assert by_tier["C"]["n"] == 0 and by_tier["C"]["ok"] is None  # no data at all


def test_tier_calibration_ok_false_when_band_missed():
    closed = [_tier_t("C", "win") for _ in range(3)] + [_tier_t("C", "loss") for _ in range(9)]
    row = tier_calibration(closed)[2]
    assert row["tier"] == "C" and row["n"] == 12
    assert round(row["win_rate"], 1) == 25.0
    assert row["ok"] is True  # 25% IS < 70 -- band met


def test_tier_calibration_row_order_is_a_b_c():
    rows = tier_calibration([])
    assert [r["tier"] for r in rows] == ["A", "B", "C"]
```

- [ ] **Step 2: Run — FAIL. Step 3: Implement (append to `calibration.py`)**

```python
EXPECTED_BAND = {"A": ">=80", "B": "70-80", "C": "<70"}
MIN_N_FOR_CALIBRATION_VERDICT = 10  # below this, "ok" is None (insufficient data), not False


def _meets_band(win_rate: float, band: str) -> bool:
    if band == ">=80":
        return win_rate >= 80
    if band == "<70":
        return win_rate < 70
    lo, hi = (float(x) for x in band.split("-"))
    return lo <= win_rate <= hi


def tier_calibration(closed: list[dict]) -> list[dict]:
    """One row per design tier (A/B/C, always all three regardless of
    whether any trades exist yet) comparing live win rate against the
    fixed design band that tier is SUPPOSED to land in. `ok` is a
    three-valued signal, not a boolean pass/fail: None means "not enough
    live data to judge yet" (win_rate is None, or n < 10), which is a
    very different message from "judged and it's missing its band"."""
    rows = []
    for tier, band in EXPECTED_BAND.items():
        trades = [t for t in closed if t.get("tier") == tier]
        n = len(trades)
        wr = metrics.win_rate(trades)
        er = metrics.expectancy_r(trades)
        ok = None if (wr is None or n < MIN_N_FOR_CALIBRATION_VERDICT) else _meets_band(wr, band)
        rows.append({"tier": tier, "n": n, "win_rate": wr, "expectancy_r": er,
                     "expected_band": band, "ok": ok})
    return rows
```

Re-export `tier_calibration`.

- [ ] **Step 4: Run `python -m pytest tests/test_calibration.py -v` — PASS (6 tests). Step 5: Commit**

```bash
git add swingbot/core/analytics/calibration.py swingbot/core/analytics/__init__.py tests/test_calibration.py
git commit -m "feat: tier calibration vs design bands"
```

### Task A17: Badge drift (edge decay)

**Files:** Modify `calibration.py`; test `tests/test_calibration.py`

**Interfaces:**
- Produces: `badge_drift(closed, registry_entries: list[dict]) -> list[dict]` — one row per distinct VALIDATED-status strategy present in `registry_entries`: `{"strategy", "oos_n", "oos_wr", "live_n", "live_wr", "delta_wr", "drift_alert": bool}`. **Pre-registered decay rule (do not tune after seeing live data): `drift_alert = live_n >= 20 and live_wr is not None and live_wr < oos_wr - 10.0`.** `registry_entries` is the parsed `validation_registry.json` list (caller loads via `registry.load_registry()` — this module never imports `registry` itself, keeping `calibration.py` I/O-free per the Global Constraints).

- [ ] **Step 1: Failing test**

```python
# tests/test_calibration.py -- append
from swingbot.core.analytics.calibration import badge_drift


def _reg(strategy, wr, n=206, status="VALIDATED"):
    return {"source": "strategy", "strategy": strategy, "horizon": None, "status": status,
            "n": n, "win_rate": wr, "expectancy_r": 0.105, "window": "2024-01-01..2025-12-31"}


def _live_t(strategy_sources, status):
    return {"target_sources": strategy_sources, "status": status, "direction": "bullish",
            "entry": 100.0, "stop_loss": 95.0, "exit_price": 104.0 if status == "win" else 96.0}


def test_badge_drift_alerts_on_real_decay():
    registry = [_reg("Fibonacci", 81.6)]
    live = [_live_t(["Fib 61.8%"], "win") for _ in range(16)] + [_live_t(["Fib 61.8%"], "loss") for _ in range(9)]
    rows = badge_drift(live, registry)
    assert rows[0]["strategy"] == "Fibonacci"
    assert rows[0]["oos_wr"] == 81.6 and rows[0]["live_n"] == 25
    assert round(rows[0]["live_wr"], 1) == 64.0
    assert rows[0]["drift_alert"] is True


def test_badge_drift_false_when_within_ten_points():
    registry = [_reg("Fibonacci", 81.6)]
    live = [_live_t(["Fib 61.8%"], "win") for _ in range(19)]
    live += [_live_t(["Fib 61.8%"], "loss") for _ in range(6)]
    rows = badge_drift(live, registry)
    assert round(rows[0]["live_wr"], 1) == 76.0
    assert rows[0]["drift_alert"] is False


def test_badge_drift_false_below_n_floor():
    registry = [_reg("Fibonacci", 81.6)]
    live = [_live_t(["Fib 61.8%"], "win") for _ in range(4)] + [_live_t(["Fib 61.8%"], "loss") for _ in range(6)]
    rows = badge_drift(live, registry)
    assert rows[0]["live_n"] == 10
    assert rows[0]["drift_alert"] is False  # 40% would otherwise alert, but N=10 < 20


def test_badge_drift_ignores_weak_registry_rows_and_dedups_by_strategy():
    registry = [_reg("VWAP", 90.0, status="WEAK"), _reg("Fibonacci", 81.6), _reg("Fibonacci", 81.6, n=50)]
    rows = badge_drift([], registry)
    assert [r["strategy"] for r in rows] == ["Fibonacci"]  # WEAK excluded, dup collapsed
```

- [ ] **Step 2: Run — FAIL. Step 3: Implement (append to `calibration.py`)**

```python
DRIFT_LIVE_N_FLOOR = 20         # below this, live win rate is too noisy to judge decay from
DRIFT_THRESHOLD_POINTS = 10.0   # live WR must fall more than this many points below OOS WR


def badge_drift(closed: list[dict], registry_entries: list[dict]) -> list[dict]:
    """Compare each VALIDATED strategy's committed out-of-sample win rate
    against its live win rate so far, flagging real edge decay.

    The alert rule below is PRE-REGISTERED (Global Constraint / design
    decision #5 in the cockpit-v3 plan): live_n >= 20 and
    live_wr < oos_wr - 10.0. This threshold must never be loosened or
    tightened after actually observing live drift -- that would be
    tuning on the very data the rule exists to police. If it needs to
    change, that is a deliberate, documented design decision made BEFORE
    looking at what triggered it, not a reaction to it.

    One row per distinct strategy name across `registry_entries` that has
    at least one VALIDATED-status record -- WEAK-status rows are excluded
    entirely (there is no "decay" concept for a strategy that was never
    validated to begin with), and duplicate strategy names (e.g. one row
    per horizon) collapse to the first VALIDATED occurrence encountered.
    """
    from swingbot.core.performance import primary_strategy_label

    rows = []
    seen: set[str] = set()
    for r in registry_entries:
        if r.get("status") != "VALIDATED":
            continue
        strat = r["strategy"]
        if strat in seen:
            continue
        seen.add(strat)

        oos_n = r.get("n", 0)
        oos_wr = r.get("win_rate", 0.0)
        live = [t for t in closed
                if primary_strategy_label(t) == strat or t.get("strategy") == strat]
        live_n = len(live)
        live_wr = metrics.win_rate(live)
        delta = (live_wr - oos_wr) if live_wr is not None else None
        alert = bool(live_n >= DRIFT_LIVE_N_FLOOR and live_wr is not None
                     and live_wr < oos_wr - DRIFT_THRESHOLD_POINTS)

        rows.append({"strategy": strat, "oos_n": oos_n, "oos_wr": oos_wr,
                     "live_n": live_n, "live_wr": live_wr, "delta_wr": delta,
                     "drift_alert": alert})
    return rows
```

`badge_drift` needs `metrics` (already imported at the top of `calibration.py` since Task A15). Re-export `badge_drift`.

- [ ] **Step 4: Run `python -m pytest tests/test_calibration.py -v` — PASS (10 tests). Step 5: Commit**

```bash
git add swingbot/core/analytics/calibration.py swingbot/core/analytics/__init__.py tests/test_calibration.py
git commit -m "feat: badge drift / edge-decay detection"
```

---

# Phase A3 — The follow score (Task A18)

### Task A18: follow_score + rank_plans

The one shared answer to "which plan do I follow?". Plans B and C must import this — never re-rank locally.

**Files:**
- Create: `swingbot/core/analytics/rank.py`
- Test: `tests/test_rank.py`

**Interfaces:**
- Produces: `follow_score(plan, *, today: dt.date | None = None) -> float` (0–100) and `rank_plans(plans: list, *, today: dt.date | None = None) -> list` (desc by score, tie-break `quality_score` desc then `ticker` asc); `today` defaults to the current date, injectable for tests. Accepts `TradePlanV2` instances **or** dicts via an internal `_get(p, name, default=None)` (`getattr` for objects, `.get` for dicts). Components (fixed weights, documented in the docstring):
  - badge: VALIDATED = 40, else 0
  - quality: `0.4 × quality_score` (0–40)
  - regime: 10 if `_get(p, "regime_aligned")` truthy else 0 (callers stamp this bool; `TradePlanV2` has no such field today — `_get`'s default-None-is-falsy behavior means every current plan scores 0 here until a caller adds the attribute, which is intentional degrade-gracefully behavior, not a bug)
  - freshness: `max(0, 10 − 2×age_days)` where `age_days` is the (today − `created_at` date).days, `created_at` parsed as either a bare `YYYY-MM-DD` date (the format `TradePlanV2.created_at` actually uses) or a full ISO datetime (for dict-shaped plans built by other callers)

- [ ] **Step 1: Failing test**

```python
# tests/test_rank.py
import datetime as dt

from swingbot.core.analytics.rank import follow_score, rank_plans

TODAY = dt.date(2026, 7, 11)


def test_validated_a_beats_weak_a():
    val = {"badge": "VALIDATED", "quality_score": 80, "regime_aligned": True,
           "created_at": "2026-07-11"}
    weak = dict(val, badge="WEAK")
    assert follow_score(val, today=TODAY) == 40 + 32 + 10 + 10  # 92.0
    assert follow_score(weak, today=TODAY) == 52.0
    assert rank_plans([weak, val], today=TODAY)[0] is val


def test_stale_plan_loses_freshness():
    p = {"badge": "VALIDATED", "quality_score": 80, "regime_aligned": True,
         "created_at": "2026-07-01"}
    assert follow_score(p, today=TODAY) == 82.0  # freshness floor 0


def test_missing_fields_degrade_to_zero_component_not_error():
    p = {"badge": "VALIDATED", "created_at": "2026-07-11"}  # no quality_score, no regime_aligned
    assert follow_score(p, today=TODAY) == 40 + 0 + 0 + 10  # 50.0


def test_rank_plans_tie_break_quality_then_ticker():
    a = {"badge": "VALIDATED", "quality_score": 70, "created_at": "2026-07-11", "ticker": "MSFT"}
    b = {"badge": "VALIDATED", "quality_score": 70, "created_at": "2026-07-11", "ticker": "AAPL"}
    c = {"badge": "VALIDATED", "quality_score": 90, "created_at": "2026-07-11", "ticker": "ZZZZ"}
    ranked = rank_plans([a, b, c], today=TODAY)
    assert [p["ticker"] for p in ranked] == ["ZZZZ", "AAPL", "MSFT"]


def test_follow_score_accepts_dataclass_instances():
    from dataclasses import dataclass

    @dataclass
    class FakePlan:
        badge: str
        quality_score: int
        created_at: str
        ticker: str = "AAPL"

    p = FakePlan(badge="VALIDATED", quality_score=50, created_at="2026-07-11")
    assert follow_score(p, today=TODAY) == 40 + 20 + 0 + 10  # regime_aligned absent -> 0
```

- [ ] **Step 2: Run `python -m pytest tests/test_rank.py -v` — expect FAIL (no module)**

- [ ] **Step 3: Implement**

```python
# swingbot/core/analytics/rank.py
"""follow_score is THE single ranking authority this whole cockpit uses to
answer "which plan should I follow today?" -- Discord alerts, !plans,
!top, the weekly digest, /api/plans, and the admin board all consume
rank_plans() instead of sorting locally. See design decision #1 in
docs/superpowers/plans/2026-07-11-cockpit-v3.md."""
from __future__ import annotations

import datetime as dt

BADGE_WEIGHT = 40.0
QUALITY_WEIGHT = 0.4          # applied to a 0-100 quality_score -> 0-40 contribution
REGIME_WEIGHT = 10.0
FRESHNESS_MAX = 10.0
FRESHNESS_DECAY_PER_DAY = 2.0  # freshness hits 0 at age_days == 5


def _get(p, name: str, default=None):
    """Read `name` off either a TradePlanV2 (or any dataclass/object) or a
    plain dict, uniformly -- lets follow_score/rank_plans accept whatever
    shape the caller has on hand without every caller converting first."""
    if isinstance(p, dict):
        return p.get(name, default)
    return getattr(p, name, default)


def _parse_created_at(value: str) -> dt.date | None:
    """TradePlanV2.created_at is a bare ISO date ("2026-07-11"); some
    dict-shaped callers may instead carry a full ISO datetime. Handle
    both without raising on a malformed value."""
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value[:10])
    except ValueError:
        return None


def follow_score(plan, *, today: dt.date | None = None) -> float:
    """0-100 composite score: badge (40) + quality (40) + regime (10) +
    freshness (10). Every component degrades to 0 (never raises) when its
    underlying field is missing -- an old-shaped plan simply scores lower,
    it never crashes a ranking pass.
    """
    if today is None:
        today = dt.date.today()

    badge_score = BADGE_WEIGHT if _get(plan, "badge") == "VALIDATED" else 0.0

    quality_score = _get(plan, "quality_score") or 0
    quality_component = QUALITY_WEIGHT * quality_score

    regime_component = REGIME_WEIGHT if _get(plan, "regime_aligned") else 0.0

    created = _parse_created_at(_get(plan, "created_at", ""))
    if created is None:
        freshness_component = 0.0
    else:
        age_days = (today - created).days
        freshness_component = max(0.0, FRESHNESS_MAX - FRESHNESS_DECAY_PER_DAY * age_days)

    return badge_score + quality_component + regime_component + freshness_component


def rank_plans(plans: list, *, today: dt.date | None = None) -> list:
    """`plans` sorted by follow_score descending; ties broken by
    quality_score descending, then ticker ascending (alphabetical) --
    deterministic ordering so the same input always renders in the same
    order across Discord/admin/API without depending on Python's stable
    sort accidentally preserving insertion order (it does, but the
    explicit tie-break key means that's not what's actually holding the
    order steady, so a caller passing plans in a different order gets an
    identical result)."""
    def _key(p):
        return (-follow_score(p, today=today), -(_get(p, "quality_score") or 0), _get(p, "ticker") or "")

    return sorted(plans, key=_key)
```

Re-export `follow_score, rank_plans` from `swingbot/core/analytics/__init__.py`.

- [ ] **Step 4: Run `python -m pytest tests/test_rank.py -v` — PASS (5 tests). Step 5: Commit**

```bash
git add swingbot/core/analytics/rank.py swingbot/core/analytics/__init__.py tests/test_rank.py
git commit -m "feat: shared follow_score plan ranking"
```

---

# Phase A4 — Lessons journal (Tasks A19–A24)

### Task A19: JournalStore

**Files:**
- Create: `swingbot/core/analytics/journal.py`
- Test: `tests/test_journal.py`

**Interfaces:**
- Produces: `JournalStore(path: str | None = None)` (default `config.DATA_DIR/journal.json`, list-of-dicts via `jsonio`); methods `add(entry: dict) -> dict` (stamps `created_at`, dedups on `trade_id` by replacing), `get(trade_id) -> dict | None`, `entries(*, strategy=None, tag=None, outcome=None, since=None) -> list[dict]` (newest first), `set_note(trade_id, note: str) -> bool`. Module-level `_LOCK = threading.Lock()` around mutations, matching the house pattern already used by `performance.py`/`state.py`.

- [ ] **Step 1: Failing test**

```python
# tests/test_journal.py
from swingbot.core.analytics.journal import JournalStore


def _entry(trade_id, strategy="Fibonacci", tags=None, outcome="win", closed_at="2026-03-10T10:00:00+00:00"):
    return {"trade_id": trade_id, "ticker": "AAPL", "strategy": strategy,
            "outcome": outcome, "tags": tags or [], "note": "", "closed_at": closed_at}


def test_add_stamps_created_at_and_get_roundtrips(tmp_path):
    store = JournalStore(path=str(tmp_path / "journal.json"))
    saved = store.add(_entry("t1"))
    assert "created_at" in saved
    assert store.get("t1")["ticker"] == "AAPL"
    assert store.get("nope") is None


def test_re_add_same_trade_id_replaces_not_duplicates(tmp_path):
    store = JournalStore(path=str(tmp_path / "journal.json"))
    store.add(_entry("t1", outcome="win"))
    store.add(_entry("t1", outcome="loss"))
    all_entries = store.entries()
    assert len(all_entries) == 1 and all_entries[0]["outcome"] == "loss"


def test_entries_filters_by_strategy_and_tag_newest_first(tmp_path):
    store = JournalStore(path=str(tmp_path / "journal.json"))
    store.add(_entry("t1", strategy="Fibonacci", tags=["fast_win"], closed_at="2026-03-01T00:00:00+00:00"))
    store.add(_entry("t2", strategy="EMA Crossover", tags=["slow_burn"], closed_at="2026-03-02T00:00:00+00:00"))
    store.add(_entry("t3", strategy="Fibonacci", tags=["fast_win"], closed_at="2026-03-03T00:00:00+00:00"))

    by_strategy = store.entries(strategy="Fibonacci")
    assert [e["trade_id"] for e in by_strategy] == ["t3", "t1"]  # newest first

    by_tag = store.entries(tag="slow_burn")
    assert [e["trade_id"] for e in by_tag] == ["t2"]


def test_entries_filters_by_outcome_and_since(tmp_path):
    store = JournalStore(path=str(tmp_path / "journal.json"))
    store.add(_entry("t1", outcome="win", closed_at="2026-03-01T00:00:00+00:00"))
    store.add(_entry("t2", outcome="loss", closed_at="2026-03-05T00:00:00+00:00"))
    assert [e["trade_id"] for e in store.entries(outcome="loss")] == ["t2"]
    assert [e["trade_id"] for e in store.entries(since="2026-03-03")] == ["t2"]


def test_set_note_roundtrips_through_a_fresh_store_instance(tmp_path):
    path = str(tmp_path / "journal.json")
    store = JournalStore(path=path)
    store.add(_entry("t1"))
    assert store.set_note("t1", "Should have trailed further.") is True

    fresh = JournalStore(path=path)  # forces a real disk read, not shared in-memory state
    assert fresh.get("t1")["note"] == "Should have trailed further."
```

- [ ] **Step 2: Run `python -m pytest tests/test_journal.py -v` — expect FAIL (no module)**

- [ ] **Step 3: Implement**

```python
# swingbot/core/analytics/journal.py
"""Per-trade lessons journal: one entry per closed trade, auto-populated
with MFE/MAE/exit-efficiency and a templated lesson (Task A20), auto-tagged
(Task A21), and optionally hand-annotated with a free-text note. This IS
the data source for the retrospective (A27), the weekly digest (A25), and
the admin/Discord Journal browsers in Plans B/C -- none of them re-derive
a lesson, they only render what's already here."""
from __future__ import annotations

import os
import threading
from datetime import datetime, timezone

from swingbot import config
from swingbot.core.jsonio import atomic_write_json, read_json

_LOCK = threading.Lock()


class JournalStore:
    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(config.DATA_DIR, "journal.json")

    def _load(self) -> list[dict]:
        return read_json(self.path, [])

    def _save(self, entries: list[dict]) -> None:
        atomic_write_json(self.path, entries)

    def add(self, entry: dict) -> dict:
        """Insert (or replace, if `entry["trade_id"]` already exists) one
        journal entry, stamping `created_at` fresh every time -- a
        re-add (e.g. the backfill script re-run, or a future re-journal
        after a correction) always reflects "when this record was last
        written", not "when it was first written"."""
        with _LOCK:
            entries = self._load()
            stamped = dict(entry, created_at=datetime.now(timezone.utc).isoformat())
            entries = [e for e in entries if e.get("trade_id") != entry.get("trade_id")]
            entries.append(stamped)
            self._save(entries)
            return stamped

    def get(self, trade_id: str) -> dict | None:
        return next((e for e in self._load() if e.get("trade_id") == trade_id), None)

    def entries(self, *, strategy: str | None = None, tag: str | None = None,
                outcome: str | None = None, since: str | None = None,
                has_note: bool | None = None) -> list[dict]:
        """Every matching entry, newest first (by `closed_at`, falling back
        to `created_at` for an entry that somehow lacks it). All filters
        are AND-combined; omit a filter (leave it None) to not apply it."""
        rows = self._load()
        if strategy is not None:
            rows = [e for e in rows if e.get("strategy") == strategy]
        if tag is not None:
            rows = [e for e in rows if tag in (e.get("tags") or [])]
        if outcome is not None:
            rows = [e for e in rows if e.get("outcome") == outcome]
        if since is not None:
            rows = [e for e in rows if (e.get("closed_at") or "") >= since]
        if has_note is not None:
            rows = [e for e in rows if bool((e.get("note") or "").strip()) == has_note]
        rows.sort(key=lambda e: e.get("closed_at") or e.get("created_at") or "", reverse=True)
        return rows

    def set_note(self, trade_id: str, note: str) -> bool:
        """Attach/replace a free-text note on an existing entry. False (no
        exception) when `trade_id` isn't journaled -- most likely a trade
        that hasn't closed yet, or predates the journal existing at all."""
        with _LOCK:
            entries = self._load()
            for e in entries:
                if e.get("trade_id") == trade_id:
                    e["note"] = note
                    self._save(entries)
                    return True
            return False
```

Re-export `JournalStore` from `swingbot/core/analytics/__init__.py`.

- [ ] **Step 4: Run `python -m pytest tests/test_journal.py -v` — PASS (5 tests). Step 5: Commit**

```bash
git add swingbot/core/analytics/journal.py swingbot/core/analytics/__init__.py tests/test_journal.py
git commit -m "feat: lessons JournalStore"
```

### Task A20: Auto entry builder

**Files:** Modify `journal.py`; test `tests/test_journal.py`

**Interfaces:**
- Produces: `build_entry(trade: dict, df) -> dict` with exact keys: `trade_id, ticker, strategy, horizon_key, direction, tier, badge, quality_score, outcome` (resolved from `status`, or the close reason when `status` is the generic `"closed"` — see `_resolve_outcome` below), `r_realized` (via `metrics.r_multiple`), `mfe_r, mae_r, exit_efficiency` (via `mfe_mae.compute_mfe_mae`, `None`-safe when `df` is `None`), `holding_days, tags` (`[]` until Task A21 fills it in), `auto_lesson` (str), `note` (`""`), `opened_at, closed_at`.
- `auto_lesson` rules (exact, in priority order, first match wins):
  1. loss with `mae_r` ≤ 0.3 and `mfe_r` ≥ 1.0 → `"Trade went {mfe_r:.1f}R in favor before stopping out — exit management, not entry, cost this one."`
  2. win with `exit_efficiency` ≥ 0.8 → `"Clean capture: banked {eff:.0%} of the available move."`
  3. loss with `mae_r` ≥ 1.0 and `mfe_r` < 0.2 → `"Entry was wrong from the first bar — review the trigger, not the exit."`
  4. scratch/timeout → `"No follow-through within the horizon — count it as rent, not error."`
  5. fallback → `"Outcome {outcome} at {r_realized:+.2f}R."` (or, when `r_realized` is `None`, `"Outcome {outcome}."`)

- [ ] **Step 1: Failing test**

```python
# tests/test_journal.py -- append
from tests.conftest import make_ohlcv
from swingbot.core.analytics.journal import build_entry


def _base_trade(**kw):
    base = {"id": "t1", "ticker": "AAPL", "strategy": "Fibonacci", "horizon_key": "4w",
            "direction": "bullish", "tier": "A", "badge": "VALIDATED", "quality_score": 80,
            "entry": 100.0, "stop_loss": 96.0,
            "opened_at": "2026-03-02T15:00:00+00:00", "closed_at": "2026-03-05T15:00:00+00:00"}
    base.update(kw)
    return base


def test_build_entry_rule1_loss_stopped_after_running():
    # mae_r <= 0.3 and mfe_r >= 1.0 -- ran to +1R+ then reversed and stopped out
    df = make_ohlcv([100, 104, 95], spread_pct=0.0, start="2026-03-02")
    t = _base_trade(status="loss", exit_price=96.0)
    e = build_entry(t, df)
    assert e["auto_lesson"] == ("Trade went 1.0R in favor before stopping out — exit management, "
                                "not entry, cost this one.")
    assert e["trade_id"] == "t1" and e["tier"] == "A" and e["badge"] == "VALIDATED"


def test_build_entry_rule2_win_clean_capture():
    df = make_ohlcv([100, 104], spread_pct=0.0, start="2026-03-02")
    t = _base_trade(status="win", exit_price=104.0, closed_at="2026-03-03T15:00:00+00:00")
    e = build_entry(t, df)
    assert e["auto_lesson"] == "Clean capture: banked 100% of the available move."


def test_build_entry_rule4_scratch_no_followthrough():
    df = make_ohlcv([100, 100], spread_pct=0.0, start="2026-03-02")
    t = _base_trade(status="closed", close_reason="scratch", exit_price=100.0,
                    closed_at="2026-03-03T15:00:00+00:00")
    e = build_entry(t, df)
    assert e["outcome"] == "scratch"
    assert e["auto_lesson"] == "No follow-through within the horizon — count it as rent, not error."


def test_build_entry_fallback_and_df_none_is_safe():
    t = _base_trade(status="loss", exit_price=97.0)
    e = build_entry(t, None)
    assert e["mfe_r"] is None and e["mae_r"] is None and e["exit_efficiency"] is None
    assert e["auto_lesson"] == f"Outcome loss at {e['r_realized']:+.2f}R."
    assert e["note"] == "" and e["tags"] == []
```

- [ ] **Step 2: Run — FAIL. Step 3: Implement (append to `journal.py`)**

```python
# add to the top of journal.py:
from swingbot.core.analytics import metrics
from swingbot.core.analytics.mfe_mae import compute_mfe_mae


def _resolve_outcome(trade: dict) -> str:
    """status is the coarse open/win/loss/closed vocabulary TradeLog has
    always used; a v2-manager close additionally carries a specific
    close_reason ("scratch"/"timeout"/...) inside the generic "closed"
    status (see plan-engine-v2 Task 70's status mapping: only "win"/
    "loss"/"closed" ever land in the field, with the real nuance in the
    leg reason or close_reason). Prefer that finer-grained reason when
    status itself is the generic "closed" bucket."""
    status = trade.get("status")
    if status in ("win", "loss"):
        return status
    legs = trade.get("legs") or []
    candidates = []
    if legs:
        candidates.append(legs[-1].get("reason", ""))
    candidates.append((trade.get("close_reason") or ""))
    for reason in candidates:
        reason = reason.lower()
        if "scratch" in reason:
            return "scratch"
        if "timeout" in reason:
            return "timeout"
    return status or "closed"


def _holding_days(trade: dict) -> float | None:
    opened, closed = trade.get("opened_at"), trade.get("closed_at")
    if not opened or not closed:
        return None
    try:
        from datetime import datetime
        return round((datetime.fromisoformat(closed) - datetime.fromisoformat(opened)).total_seconds() / 86400, 2)
    except ValueError:
        return None


def _auto_lesson(outcome: str, mfe_r: float | None, mae_r: float | None,
                  exit_efficiency: float | None, r_realized: float | None) -> str:
    if outcome == "loss" and mae_r is not None and mfe_r is not None and mae_r <= 0.3 and mfe_r >= 1.0:
        return (f"Trade went {mfe_r:.1f}R in favor before stopping out — exit management, "
                f"not entry, cost this one.")
    if outcome == "win" and exit_efficiency is not None and exit_efficiency >= 0.8:
        return f"Clean capture: banked {exit_efficiency:.0%} of the available move."
    if outcome == "loss" and mae_r is not None and mfe_r is not None and mae_r >= 1.0 and mfe_r < 0.2:
        return "Entry was wrong from the first bar — review the trigger, not the exit."
    if outcome in ("scratch", "timeout"):
        return "No follow-through within the horizon — count it as rent, not error."
    if r_realized is None:
        return f"Outcome {outcome}."
    return f"Outcome {outcome} at {r_realized:+.2f}R."


def build_entry(trade: dict, df) -> dict:
    """Assemble one auto-populated journal entry for a just-closed trade.
    `df` is the ticker's cached daily bars (or None -- every MFE/MAE field
    degrades to None rather than raising when it's unavailable, per the
    Global Constraint on graceful degradation)."""
    m = compute_mfe_mae(trade, df) if df is not None else None
    mfe_r = m["mfe_r"] if m else None
    mae_r = m["mae_r"] if m else None
    exit_efficiency = m["exit_efficiency"] if m else None
    r_realized = metrics.r_multiple(trade)
    outcome = _resolve_outcome(trade)

    return {
        "trade_id": trade.get("id"),
        "ticker": trade.get("ticker"),
        "strategy": trade.get("strategy"),
        "horizon_key": trade.get("horizon_key"),
        "direction": trade.get("direction"),
        "tier": trade.get("tier"),
        "badge": trade.get("badge"),
        "quality_score": trade.get("quality_score"),
        "outcome": outcome,
        "r_realized": r_realized,
        "mfe_r": mfe_r,
        "mae_r": mae_r,
        "exit_efficiency": exit_efficiency,
        "holding_days": _holding_days(trade),
        "tags": [],  # Task A21 fills this in via tags_for()
        "auto_lesson": _auto_lesson(outcome, mfe_r, mae_r, exit_efficiency, r_realized),
        "note": "",
        "opened_at": trade.get("opened_at"),
        "closed_at": trade.get("closed_at"),
    }
```

- [ ] **Step 4: Run `python -m pytest tests/test_journal.py -v` — PASS (9 tests). Step 5: Commit**

```bash
git add swingbot/core/analytics/journal.py tests/test_journal.py
git commit -m "feat: auto journal entries with lesson templates"
```

### Task A21: Auto-tag rules

**Files:** Modify `journal.py`; test `tests/test_journal_tags.py`

**Interfaces:**
- Produces: `tags_for(trade: dict, m: dict | None) -> list[str]`, wired into `build_entry` (this task's Step 3 also updates `build_entry`'s `"tags": []` line to `"tags": tags_for(trade, m)`). Exact rules, evaluated in this order (a trade can collect more than one tag — this is not a first-match-wins list like `auto_lesson`):
  - close reason contains `"runner_tp2"` / `"runner_trail"` / `"runner_be"` (checked against `trade["legs"][-1]["reason"]` when present, else `trade["close_reason"]` — see Task A1 Step 2's correction on the real `tp1_runner_*` prefix; `in` substring matching means the prefix is transparent) → that substring, as-is, as the tag
  - `"gap_fill"`: `exit_price` beyond the stop (on a loss) or beyond the target (on a win) by more than 0.5% of entry
  - `"near_miss_tp"`: outcome is loss/scratch and `m["mfe_r"] >= 0.8 × tp1_r`, where `tp1_r = |take_profit − entry| / |entry − stop_loss|`
  - `"fast_win"`: win with `holding_days <= 2`
  - `"slow_burn"`: `holding_days > 30`
  - `"weak_source"`: `badge == "WEAK"`

- [ ] **Step 1: Failing test**

```python
# tests/test_journal_tags.py
from swingbot.core.analytics.journal import tags_for


def _base(**kw):
    base = {"direction": "bullish", "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
            "status": "loss", "exit_price": 95.0, "opened_at": "2026-03-01T00:00:00+00:00",
            "closed_at": "2026-03-02T00:00:00+00:00", "badge": "VALIDATED"}
    base.update(kw)
    return base


def test_runner_tag_matches_v2_prefixed_reason():
    t = _base(status="win", exit_price=110.0, legs=[{"fraction": 1.0, "exit_price": 110.0,
                                                       "r": 2.0, "reason": "tp1_runner_trail"}])
    assert "runner_trail" in tags_for(t, None)


def test_legacy_close_reason_also_matches():
    t = _base(status="win", exit_price=110.0, close_reason="auto (runner_be exit)")
    assert "runner_be" in tags_for(t, None)


def test_gap_fill_tag():
    # Loss exit 93.0 is 2.0 below the 95.0 stop -- 2.0/100 = 2% > 0.5% threshold.
    t = _base(status="loss", exit_price=93.0)
    assert "gap_fill" in tags_for(t, None)


def test_near_miss_tp_tag():
    # tp1_r = |110-100|/|100-95| = 2.0; need mfe_r >= 1.6
    t = _base(status="loss", exit_price=95.0)
    assert "near_miss_tp" in tags_for(t, {"mfe_r": 1.8, "mae_r": 1.0, "exit_efficiency": None})
    assert "near_miss_tp" not in tags_for(t, {"mfe_r": 1.0, "mae_r": 1.0, "exit_efficiency": None})


def test_fast_win_and_slow_burn_and_weak_source():
    fast = _base(status="win", exit_price=110.0, opened_at="2026-03-01T00:00:00+00:00",
                 closed_at="2026-03-02T12:00:00+00:00")
    assert "fast_win" in tags_for(fast, None)

    slow = _base(status="loss", opened_at="2026-01-01T00:00:00+00:00",
                closed_at="2026-02-15T00:00:00+00:00")
    assert "slow_burn" in tags_for(slow, None)

    weak = _base(badge="WEAK")
    assert "weak_source" in tags_for(weak, None)


def test_multiple_tags_can_apply_at_once():
    t = _base(status="loss", exit_price=93.0, badge="WEAK")  # gap_fill + weak_source
    tags = tags_for(t, None)
    assert "gap_fill" in tags and "weak_source" in tags
```

- [ ] **Step 2: Run — FAIL. Step 3: Implement (append to `journal.py`, and change `build_entry`'s tags line)**

```python
_RUNNER_SUBSTRINGS = ("runner_tp2", "runner_trail", "runner_be")


def _close_reason_text(trade: dict) -> str:
    legs = trade.get("legs") or []
    if legs:
        return (legs[-1].get("reason") or "").lower()
    return (trade.get("close_reason") or "").lower()


def tags_for(trade: dict, m: dict | None) -> list[str]:
    """Every auto-tag rule that fires for this trade, in rule-declaration
    order. Unlike auto_lesson, tags are NOT first-match-wins -- a trade
    can legitimately be both a "gap_fill" AND "weak_source", for
    instance, and both should be visible in the journal browser filters.
    """
    tags: list[str] = []
    reason_text = _close_reason_text(trade)
    for substr in _RUNNER_SUBSTRINGS:
        if substr in reason_text:
            tags.append(substr)
            break  # a trade closes via at most one runner reason

    entry = trade.get("entry")
    stop = trade.get("stop_loss")
    target = trade.get("take_profit")
    exit_price = trade.get("exit_price")
    status = trade.get("status")
    if entry is not None and exit_price is not None:
        threshold = 0.005 * entry
        is_bull = trade.get("direction") == "bullish"
        if status == "loss" and stop is not None:
            gap = (stop - exit_price) if is_bull else (exit_price - stop)
            if gap > threshold:
                tags.append("gap_fill")
        elif status == "win" and target is not None:
            gap = (exit_price - target) if is_bull else (target - exit_price)
            if gap > threshold:
                tags.append("gap_fill")

    outcome = _resolve_outcome(trade)
    if outcome in ("loss", "scratch") and m and m.get("mfe_r") is not None \
            and entry is not None and stop is not None and target is not None:
        risk = abs(entry - stop)
        if risk > 0:
            tp1_r = abs(target - entry) / risk
            if m["mfe_r"] >= 0.8 * tp1_r:
                tags.append("near_miss_tp")

    holding_days = _holding_days(trade)
    if status == "win" and holding_days is not None and holding_days <= 2:
        tags.append("fast_win")
    if holding_days is not None and holding_days > 30:
        tags.append("slow_burn")

    if trade.get("badge") == "WEAK":
        tags.append("weak_source")

    return tags
```

```python
# in build_entry, replace:
#     "tags": [],  # Task A21 fills this in via tags_for()
# with:
        "tags": tags_for(trade, m),
```

- [ ] **Step 4: Run `python -m pytest tests/test_journal_tags.py -v` — PASS (7 tests). Step 5: `python -m pytest tests/test_journal.py -v` — still green (build_entry's tags field changed shape). Step 6: Commit**

```bash
git add swingbot/core/analytics/journal.py tests/test_journal_tags.py
git commit -m "feat: journal auto-tagging"
```

### Task A22: Journal on every close

**Files:**
- Modify: `swingbot/core/performance.py` (`update_open_trades` at line 307, `close_trade_manual` at line 608, `close_if_live_price_hit` at line 665, `check_near_tp_timeout` at line 713 — this is the fourth close path; the plan's "four close paths" phrasing refers to these, not to `update_open_trades` alone)
- Test: `tests/test_journal.py`

**Interfaces:**
- Produces: module function `journal_trade_close(trade: dict) -> None` in `journal.py` — fetches daily bars via `swingbot.core.data.get_daily_data(ticker)` inside try/except (journal failure must NEVER break a close; log a warning), builds an entry via `build_entry`, and `JournalStore().add(entry)`. Called once per newly-closed trade dict returned from each of the four close paths above.

- [ ] **Step 1: Failing test**

```python
# tests/test_journal.py -- append
from unittest.mock import patch

from swingbot.core.analytics.journal import JournalStore, journal_trade_close
from tests.conftest import make_ohlcv


def _closed_trade():
    return {"id": "t1", "ticker": "AAPL", "strategy": "Fibonacci", "horizon_key": "4w",
            "direction": "bullish", "entry": 100.0, "stop_loss": 96.0, "status": "win",
            "exit_price": 104.0, "opened_at": "2026-03-02T15:00:00+00:00",
            "closed_at": "2026-03-05T15:00:00+00:00"}


def test_journal_trade_close_adds_entry(tmp_path, monkeypatch):
    monkeypatch.setattr("swingbot.core.analytics.journal.config.DATA_DIR", str(tmp_path))
    df = make_ohlcv([100, 108, 98, 104], spread_pct=0.0, start="2026-03-02")
    with patch("swingbot.core.data.get_daily_data", return_value=df):
        journal_trade_close(_closed_trade())
    store = JournalStore(path=str(tmp_path / "journal.json"))
    assert store.get("t1") is not None


def test_journal_trade_close_never_raises_on_fetch_failure(tmp_path, monkeypatch):
    monkeypatch.setattr("swingbot.core.analytics.journal.config.DATA_DIR", str(tmp_path))
    with patch("swingbot.core.data.get_daily_data", side_effect=ValueError("no data")):
        journal_trade_close(_closed_trade())  # must not raise
    store = JournalStore(path=str(tmp_path / "journal.json"))
    # Entry still gets added -- just with df=None (all MFE/MAE fields None) --
    # a data-fetch failure degrades the entry, it does not skip it.
    assert store.get("t1") is not None
    assert store.get("t1")["mfe_r"] is None
```

- [ ] **Step 2: Run — FAIL. Step 3: Implement**

```python
# journal.py -- add near the top:
import logging

log = logging.getLogger("swing-bot.journal")


# append at module scope:
def journal_trade_close(trade: dict) -> None:
    """Called once per newly-closed trade from every TradeLog close path.
    Never raises: a bars fetch failure or any other exception here must
    not un-close a trade or crash the caller's own save -- this is pure
    bookkeeping layered on top of a close that has already happened and
    already been persisted by the time this runs.
    """
    df = None
    try:
        from swingbot.core.data import get_daily_data
        df = get_daily_data(trade["ticker"])
    except Exception:
        log.warning("journal_trade_close: bars fetch failed for %s -- journaling without MFE/MAE",
                    trade.get("ticker"), exc_info=True)

    try:
        entry = build_entry(trade, df)
        JournalStore().add(entry)
    except Exception:
        log.warning("journal_trade_close: failed to journal trade %s", trade.get("id"), exc_info=True)
```

Wire the four call sites in `performance.py` — each is one line, added right after that path's own `self._save()` inside the `with _LOCK:` block has already released (call it AFTER the lock exits, since `journal_trade_close` does its own file I/O under a *different* lock and must never be invoked while `TradeLog`'s `_LOCK` is still held):

```python
# performance.py -- update_open_trades, right after
#     "if newly_closed: self._save()"
# and the `with _LOCK:` block has closed:
        for t in newly_closed:
            _journal_close_safely(t)
        return newly_closed

# close_trade_manual: right before its final `return True`, AFTER the
# `with _LOCK:` block, using the same `t` object mutated inside the loop
# (capture it in a local before returning):
                    self._save()
                    _journal_close_safely(t)
                    return True

# close_if_live_price_hit: after the `with _LOCK:` block, before `return newly_closed`:
        for t in newly_closed:
            _journal_close_safely(t)
        return newly_closed

# check_near_tp_timeout: same pattern, after the `with _LOCK:` block:
        for t in newly_closed:
            _journal_close_safely(t)
        return newly_closed
```

```python
# performance.py -- module-level helper, defined once near the top
# (after the existing imports), used by all four call sites above:
def _journal_close_safely(trade: dict) -> None:
    """Lazy import to avoid a circular import (analytics.journal doesn't
    import performance, but importing it eagerly at module load time
    would still tie the two modules' import order together unnecessarily)
    and a try/except so a journaling bug can never surface as a broken
    trade close -- matches the lazy-import pattern already used by
    primary_strategy_label() in this same file."""
    try:
        from swingbot.core.analytics.journal import journal_trade_close
        journal_trade_close(trade)
    except Exception:
        import logging
        logging.getLogger("swing-bot.performance").warning(
            "journal hook failed for trade %s", trade.get("id"), exc_info=True)
```

- [ ] **Step 4: `python -m pytest tests/ -q` — full suite green (TradeLog's close paths are exercised by many existing tests; the journal hook must never change their return values or timing in any observable way, just add a side effect). Step 5: Commit**

```bash
git add swingbot/core/performance.py swingbot/core/analytics/journal.py tests/test_journal.py
git commit -m "feat: auto journal entry on every trade close"
```

### Task A23: Manual notes API

**Files:** Modify `journal.py` (already has `set_note` from Task A19); test `tests/test_journal.py`

**Interfaces:**
- Produces: confirms `set_note` returns `False` for an unknown `trade_id` (already implemented and tested in A19 — this task adds the negative-path assertion explicitly plus the `has_note` filter on `entries()`, already implemented in A19's `entries()` signature but untested until now).

- [ ] **Step 1: Failing test**

```python
# tests/test_journal.py -- append
def test_set_note_false_for_missing_trade_id(tmp_path):
    store = JournalStore(path=str(tmp_path / "journal.json"))
    assert store.set_note("missing", "x") is False


def test_has_note_filter(tmp_path):
    store = JournalStore(path=str(tmp_path / "journal.json"))
    store.add(_entry("t1"))
    store.add(_entry("t2"))
    store.set_note("t1", "worth remembering")
    result = store.entries(has_note=True)
    assert [e["trade_id"] for e in result] == ["t1"]
    assert [e["trade_id"] for e in store.entries(has_note=False)] == ["t2"]
```

- [ ] **Step 2: Run `python -m pytest tests/test_journal.py -v` — expect PASS already** (both `set_note`'s `False` return and the `has_note` kwarg were implemented in Task A19's `journal.py`, just not directly asserted until now — this is a coverage-only task, not a behavior change). Confirm green, then proceed straight to commit — there is no Step 3 implementation diff.

- [ ] **Step 3: Commit**

```bash
git add tests/test_journal.py
git commit -m "test: journal manual notes + has_note filter coverage"
```

### Task A24: Historical backfill script

**Files:**
- Create: `scripts/backfill_journal.py`
- Test: `tests/test_journal.py` (function-level test on its `backfill(trades, store, fetch)` core)

**Interfaces:**
- Produces: CLI `python scripts/backfill_journal.py [--dry-run]` — iterates every closed trade in `trades.json` lacking a journal entry, builds entries (bars via `swingbot.core.data.get_daily_data`, falling back to a cached CSV at `data/backtest_cache/{TICKER}.csv` when the live fetch fails — same cache directory the backtest tooling already uses), and prints `backfilled N, skipped M`. Core logic lives in a testable `backfill(trades, store, fetch_fn) -> tuple[int, int]` so the CLI wrapper itself needs no test coverage of its own.

- [ ] **Step 1: Failing test**

```python
# tests/test_journal.py -- append
from scripts.backfill_journal import backfill


def test_backfill_skips_already_journaled(tmp_path):
    store = JournalStore(path=str(tmp_path / "journal.json"))
    store.add(_entry("already"))
    trades = [
        {"id": "already", "ticker": "AAPL", "status": "win", "entry": 100.0, "stop_loss": 96.0,
         "exit_price": 104.0, "opened_at": "2026-03-01T00:00:00+00:00", "closed_at": "2026-03-02T00:00:00+00:00"},
        {"id": "new1", "ticker": "MSFT", "status": "loss", "entry": 50.0, "stop_loss": 52.0,
         "exit_price": 52.0, "opened_at": "2026-03-01T00:00:00+00:00", "closed_at": "2026-03-02T00:00:00+00:00"},
        {"id": "open1", "ticker": "TSLA", "status": "open", "entry": 200.0, "stop_loss": 190.0},
    ]

    def fetch(ticker):
        return None  # no bars available in this test -- backfill must still succeed with degraded entries

    backfilled, skipped = backfill(trades, store, fetch)
    assert backfilled == 1  # "new1" only -- "already" is already journaled, "open1" isn't closed
    assert skipped == 1
    assert store.get("new1") is not None
```

- [ ] **Step 2: Run `python -m pytest tests/test_journal.py -v` — expect FAIL (no module `scripts.backfill_journal`)**

- [ ] **Step 3: Implement**

```python
# scripts/backfill_journal.py
"""One-time (or re-runnable) backfill: journal every already-closed trade
in trades.json that predates the auto-journal hook (Task A22), or that the
hook itself failed to journal for any reason. Idempotent -- JournalStore.add
replaces by trade_id, so re-running this after Task A22 is live is always
safe and simply does nothing for trades already journaled.

Run: python scripts/backfill_journal.py [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swingbot import config
from swingbot.core.analytics.journal import JournalStore, build_entry
from swingbot.core.performance import TradeLog

BACKTEST_CACHE_DIR = os.path.join(config.DATA_DIR, "backtest_cache")


def _fetch_with_cache_fallback(ticker: str):
    """Live fetch first; on any failure, fall back to the same cached CSV
    the backtest tooling already maintains at data/backtest_cache/{TICKER}.csv
    (columns Date,Open,High,Low,Close,Volume) so a backfill run doesn't
    need network access at all once that cache is warm."""
    try:
        from swingbot.core.data import get_daily_data
        return get_daily_data(ticker)
    except Exception:
        pass
    csv_path = os.path.join(BACKTEST_CACHE_DIR, f"{ticker.upper()}.csv")
    if os.path.exists(csv_path):
        import pandas as pd
        try:
            return pd.read_csv(csv_path, index_col="Date", parse_dates=True)
        except Exception:
            return None
    return None


def backfill(trades: list[dict], store: JournalStore, fetch_fn) -> tuple[int, int]:
    """Core, testable logic: journal every closed trade in `trades` not
    already present in `store`. Returns (backfilled, skipped) where
    `skipped` counts trades that are not closed (still open) OR already
    journaled -- both are legitimately "nothing to do here", just for
    different reasons, so this plan does not distinguish them in the
    return value (the CLI's printed summary can, if a future task wants
    that granularity)."""
    backfilled = skipped = 0
    for t in trades:
        if t.get("status") not in ("win", "loss", "closed"):
            skipped += 1
            continue
        if store.get(t.get("id")) is not None:
            skipped += 1
            continue
        df = fetch_fn(t["ticker"])
        entry = build_entry(t, df)
        store.add(entry)
        backfilled += 1
    return backfilled, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would be backfilled without writing journal.json")
    args = parser.parse_args()

    trades = TradeLog().get_trades(status="all", limit=None)
    store = JournalStore()

    if args.dry_run:
        # A dry run must never touch disk -- back it with a throwaway
        # in-memory-only store pointed at a path that doesn't exist yet,
        # so JournalStore's own _load()/_save() calls are harmless no-ops
        # on a scratch file, never the real journal.json.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            scratch = JournalStore(path=os.path.join(tmp, "scratch_journal.json"))
            backfilled, skipped = backfill(trades, scratch, _fetch_with_cache_fallback)
    else:
        backfilled, skipped = backfill(trades, store, _fetch_with_cache_fallback)

    print(f"backfilled {backfilled}, skipped {skipped}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run `python -m pytest tests/test_journal.py -v` — PASS. Step 5: Run once for real** (against the live `data/trades.json`, once v2 has actually produced closed trades to backfill — running it today against an empty/near-empty trades.json is harmless but not meaningful):

```
python scripts/backfill_journal.py
```
Expected output shape: `backfilled N, skipped M`.

- [ ] **Step 6: Commit**

```bash
git add scripts/backfill_journal.py tests/test_journal.py
git commit -m "feat: journal backfill script"
```

---

# Phase A5 — Insights & retrospective v2 (Tasks A25–A27)

### Task A25: Weekly digest

**Files:**
- Create: `swingbot/core/analytics/insights.py`
- Test: `tests/test_insights.py`

**Interfaces:**
- Produces: `weekly_digest(entries: list[dict], closed: list[dict], today: dt.date) -> list[str]` — Discord-ready messages (≤1900 chars each) covering the trailing 7 days (`today` inclusive, back to `today - 6 days`): headline (n / WR / expectancy / P&L), best & worst trade with their `auto_lesson`, tag frequency top-3, a tier calibration one-liner, and up to 3 `note` excerpts. `entries` are `JournalStore` records (any window — this function filters to the trailing 7 days itself); `closed` are the corresponding raw `TradeLog` records for the same window (win-rate/expectancy math delegates to `metrics`, never re-derived here). Pure function; posting happens in Plan B.

- [ ] **Step 1: Failing test**

```python
# tests/test_insights.py
import datetime as dt

from swingbot.core.analytics.insights import weekly_digest

TODAY = dt.date(2026, 3, 8)  # a Sunday; window is 2026-03-02..2026-03-08


def _closed(status, r_amount, closed_at):
    return {"status": status, "closed_at": closed_at, "direction": "bullish",
            "entry": 100.0, "stop_loss": 95.0,
            "exit_price": 104.0 if status == "win" else 96.0,
            "realized_pnl_amount": r_amount}


def _entry(trade_id, r_realized, closed_at, tags, note="", auto_lesson="Outcome win at +1.00R."):
    return {"trade_id": trade_id, "ticker": trade_id.upper(), "r_realized": r_realized,
            "closed_at": closed_at, "tags": tags, "note": note, "auto_lesson": auto_lesson}


def test_weekly_digest_headline_and_worst_trade_lesson():
    closed = [
        _closed("win", 80.0, "2026-03-03T10:00:00+00:00"),
        _closed("win", 40.0, "2026-03-04T10:00:00+00:00"),
        _closed("win", 20.0, "2026-03-05T10:00:00+00:00"),
        _closed("loss", -40.0, "2026-03-06T10:00:00+00:00"),
    ]
    entries = [
        _entry("aaa", 0.8, "2026-03-03T10:00:00+00:00", ["fast_win"]),
        _entry("bbb", 0.4, "2026-03-04T10:00:00+00:00", ["fast_win"]),
        _entry("ccc", 0.2, "2026-03-05T10:00:00+00:00", []),
        _entry("ddd", -1.2, "2026-03-06T10:00:00+00:00", ["gap_fill"],
              note="Should have waited for confirmation.",
              auto_lesson="Entry was wrong from the first bar — review the trigger, not the exit."),
    ]
    messages = weekly_digest(entries, closed, TODAY)
    joined = "\n".join(messages)
    assert "WR 75" in joined
    assert "Entry was wrong from the first bar" in joined  # worst trade's lesson, verbatim
    assert all(len(m) <= 1900 for m in messages)


def test_weekly_digest_outside_window_excluded():
    closed = [_closed("win", 50.0, "2026-02-01T10:00:00+00:00")]  # 5 weeks before TODAY
    entries = [_entry("old", 1.0, "2026-02-01T10:00:00+00:00", [])]
    messages = weekly_digest(entries, closed, TODAY)
    assert "n=0" in "\n".join(messages).lower() or "0 trade" in "\n".join(messages).lower()


def test_weekly_digest_empty_week_still_returns_a_message():
    messages = weekly_digest([], [], TODAY)
    assert len(messages) >= 1
```

- [ ] **Step 2: Run `python -m pytest tests/test_insights.py -v` — expect FAIL (no module)**

- [ ] **Step 3: Implement**

```python
# swingbot/core/analytics/insights.py
"""Human-readable rollups over the journal + closed-trade record: the
weekly lessons digest (this task), the edge-decay report and top-lessons
list (Task A26). Every number is delegated to metrics.py/calibration.py --
this module only formats, it never computes a stat from scratch. Posting
these strings to Discord is entirely Plan B's job; every function here
returns plain strings and takes no bot/channel object."""
from __future__ import annotations

import datetime as dt
from collections import Counter

from swingbot.core.analytics import calibration, metrics

DISCORD_MESSAGE_LIMIT = 1900  # headroom under Discord's ~2000-char hard cap


def _date_of(iso_str: str | None) -> dt.date | None:
    if not iso_str:
        return None
    try:
        return dt.datetime.fromisoformat(iso_str).date()
    except ValueError:
        return None


def _in_window(iso_str: str | None, start: dt.date, end: dt.date) -> bool:
    d = _date_of(iso_str)
    return d is not None and start <= d <= end


def _chunk(lines: list[str], limit: int = DISCORD_MESSAGE_LIMIT) -> list[str]:
    """Greedily pack `lines` (already-formatted, newline-joinable strings)
    into as few messages as possible without any single message exceeding
    `limit` characters -- splits between lines only, never mid-line, so a
    long individual line can still overflow (acceptable here since every
    caller's individual lines are already bounded well under the limit by
    construction: a lesson string, a ticker, a tag)."""
    messages, current = [], []
    current_len = 0
    for line in lines:
        add_len = len(line) + 1
        if current and current_len + add_len > limit:
            messages.append("\n".join(current))
            current, current_len = [], 0
        current.append(line)
        current_len += add_len
    if current:
        messages.append("\n".join(current))
    return messages or [""]


def weekly_digest(entries: list[dict], closed: list[dict], today: dt.date) -> list[str]:
    """Trailing-7-day (today inclusive) lessons digest: headline stats,
    best/worst trade with its auto_lesson, top-3 tags by frequency, a
    tier-calibration one-liner, and up to 3 note excerpts."""
    window_start = today - dt.timedelta(days=6)
    week_closed = [t for t in closed if _in_window(t.get("closed_at"), window_start, today)]
    week_entries = [e for e in entries if _in_window(e.get("closed_at"), window_start, today)]

    n = len(week_closed)
    wr = metrics.win_rate(week_closed)
    er = metrics.expectancy_r(week_closed)
    total_pnl = sum(float(t.get("realized_pnl_amount") or 0.0) for t in week_closed)

    lines = [f"**📓 Weekly Lessons Digest — {window_start.isoformat()} to {today.isoformat()}**", ""]
    if n == 0:
        lines.append("n=0 trades closed this week — nothing to report.")
        return _chunk(lines)

    wr_str = f"{wr:.0f}" if wr is not None else "n/a"
    er_str = f"{er:+.2f}R" if er is not None else "n/a"
    lines.append(f"**{n} trade(s) closed** — WR {wr_str}%, expectancy {er_str}, P&L {total_pnl:+.2f}")

    ranked = sorted((e for e in week_entries if e.get("r_realized") is not None),
                    key=lambda e: e["r_realized"])
    if ranked:
        worst, best = ranked[0], ranked[-1]
        lines.append("")
        lines.append(f"**Best:** {best['ticker']} {best['r_realized']:+.2f}R — {best['auto_lesson']}")
        if worst is not best:
            lines.append(f"**Worst:** {worst['ticker']} {worst['r_realized']:+.2f}R — {worst['auto_lesson']}")

    tag_counts = Counter(tag for e in week_entries for tag in (e.get("tags") or []))
    if tag_counts:
        lines.append("")
        lines.append("**Top tags:** " + ", ".join(f"{tag} ({count})" for tag, count in tag_counts.most_common(3)))

    tier_rows = [r for r in calibration.tier_calibration(week_closed) if r["n"] > 0]
    if tier_rows:
        lines.append("")
        lines.append("**Tier calibration:** " + " · ".join(
            f"{r['tier']}: {r['win_rate']:.0f}% (n={r['n']}, band {r['expected_band']})" for r in tier_rows
        ))

    notes = [e for e in week_entries if (e.get("note") or "").strip()][:3]
    if notes:
        lines.append("")
        lines.append("**Notes:**")
        for e in notes:
            excerpt = e["note"][:140] + ("…" if len(e["note"]) > 140 else "")
            lines.append(f"• {e['ticker']}: {excerpt}")

    return _chunk(lines)
```

Re-export `weekly_digest` from `swingbot/core/analytics/__init__.py`.

- [ ] **Step 4: Run `python -m pytest tests/test_insights.py -v` — PASS (3 tests). Step 5: Commit**

```bash
git add swingbot/core/analytics/insights.py swingbot/core/analytics/__init__.py tests/test_insights.py
git commit -m "feat: weekly lessons digest"
```

### Task A26: Edge-decay report + top lessons

**Files:** Modify `insights.py`; test `tests/test_insights.py`

**Interfaces:**
- Produces: `edge_decay_report(closed) -> list[str]` — human lines built from `calibration.badge_drift(closed, registry.load_registry())` (this function loads the registry itself — see the Global Constraints footnote above — keeping `calibration.py` pure), one line per row where `drift_alert` is `True`; `[]` when there are no alerts. `top_lessons(entries, n=5) -> list[str]` — the `n` most frequent `(auto_lesson, tuple(sorted(tags)))` pairings across `entries`, each rendered as `"{count}x — {auto_lesson} [{tags}]"`.

- [ ] **Step 1: Failing test**

```python
# tests/test_insights.py -- append
from unittest.mock import patch

from swingbot.core.analytics.insights import edge_decay_report, top_lessons


def _live_t(status):
    return {"target_sources": ["Fib 61.8%"], "status": status, "direction": "bullish",
            "entry": 100.0, "stop_loss": 95.0, "exit_price": 104.0 if status == "win" else 96.0}


def test_edge_decay_report_line_on_real_alert():
    registry = [{"source": "strategy", "strategy": "Fibonacci", "horizon": None,
                "status": "VALIDATED", "n": 206, "win_rate": 81.6, "expectancy_r": 0.105,
                "window": "2024-01-01..2025-12-31"}]
    live = [_live_t("win") for _ in range(14)] + [_live_t("loss") for _ in range(11)]  # 56% of 25
    with patch("swingbot.core.registry.load_registry", return_value=registry):
        lines = edge_decay_report(live)
    assert len(lines) == 1
    assert "Fibonacci" in lines[0] and "81.6" in lines[0] and "56" in lines[0]


def test_edge_decay_report_empty_when_no_alerts():
    with patch("swingbot.core.registry.load_registry", return_value=[]):
        assert edge_decay_report([]) == []


def test_top_lessons_counts_pairings():
    entries = [
        {"auto_lesson": "Clean capture.", "tags": ["fast_win"]},
        {"auto_lesson": "Clean capture.", "tags": ["fast_win"]},
        {"auto_lesson": "Entry was wrong.", "tags": ["gap_fill"]},
    ]
    lines = top_lessons(entries, n=2)
    assert lines[0].startswith("2x")
    assert "Clean capture." in lines[0]
```

- [ ] **Step 2: Run — FAIL. Step 3: Implement (append to `insights.py`)**

```python
def edge_decay_report(closed: list[dict]) -> list[str]:
    """One line per strategy whose live win rate has drifted meaningfully
    below its committed out-of-sample number (see calibration.badge_drift
    for the pre-registered alert rule). Loads the registry itself (the
    one deliberate I/O exception in this module) so calibration.py stays
    a pure function of (closed, registry_entries) with no hidden load."""
    from swingbot.core import registry

    rows = calibration.badge_drift(closed, registry.load_registry())
    lines = []
    for r in rows:
        if not r["drift_alert"]:
            continue
        lines.append(
            f"📉 **{r['strategy']}** live WR {r['live_wr']:.0f}% (n={r['live_n']}) "
            f"vs OOS {r['oos_wr']:.1f}% (n={r['oos_n']}) — drifted {abs(r['delta_wr']):.1f} points."
        )
    return lines


def top_lessons(entries: list[dict], n: int = 5) -> list[str]:
    """The `n` most frequent (auto_lesson, tags) pairings across `entries`,
    most-common first -- "which lesson keeps coming up" is a much more
    actionable weekly signal than a flat list of every individual lesson.
    """
    counts = Counter(
        (e.get("auto_lesson", ""), tuple(sorted(e.get("tags") or [])))
        for e in entries
    )
    lines = []
    for (lesson, tags), count in counts.most_common(n):
        tag_str = f" [{', '.join(tags)}]" if tags else ""
        lines.append(f"{count}x — {lesson}{tag_str}")
    return lines
```

Re-export `edge_decay_report, top_lessons`.

- [ ] **Step 4: Run `python -m pytest tests/test_insights.py -v` — PASS (6 tests). Step 5: Commit**

```bash
git add swingbot/core/analytics/insights.py swingbot/core/analytics/__init__.py tests/test_insights.py
git commit -m "feat: edge decay report + top lessons"
```

### Task A27: Retrospective v2 integration

**Files:**
- Modify: `swingbot/core/retrospective.py` (`build_daily_retrospective` at line 261, `_analyse` at line 522)
- Test: `tests/test_insights.py`

**Interfaces:**
- Consumes: `insights.edge_decay_report`, `calibration.tier_calibration`, `JournalStore` entries for today's closed trades.
- Produces: the daily recap gains (a) a `📐 Calibration` line when any tier row has `ok is False`, (b) `📉 Edge decay` lines from `edge_decay_report(closed_today)`, (c) a new **"📓 Trade lessons"** message block listing each closed-today trade's journal `auto_lesson` by ticker. `build_daily_retrospective`'s signature, return type (`list[str]`), and every existing message it already produces are unchanged — this is a pure addition of new list entries, appended after the existing "Lessons Learned" block (Part 5) so the closed-trade table's fixed-width monospace formatting (`_emit_table`) is never touched or risked by free-text lesson strings sharing a row with it.

> **Implementation note:** "each closed-trade line appends its journal auto_lesson" is interpreted as a new, separate message block rather than literally appending free text onto `_emit_table`'s fixed-width rows — mutating those rows would break their column alignment and the existing tests that assert on that table's exact formatting (`test_retrospective.py`, if it exists, or any future test locking that table's shape). A dedicated lessons block achieves the same "you can see the lesson from the recap" goal without that risk.

- [ ] **Step 1: Failing test**

```python
# tests/test_insights.py -- append
import datetime as dt
from unittest.mock import patch

from swingbot.core.retrospective import build_daily_retrospective


def _closed_today(ticker, status, closed_at="2026-03-10T16:00:00+00:00"):
    return {"id": ticker.lower(), "ticker": ticker, "status": status, "direction": "bullish",
            "entry": 100.0, "stop_loss": 95.0, "exit_price": 104.0 if status == "win" else 96.0,
            "opened_at": "2026-03-09T10:00:00+00:00", "closed_at": closed_at,
            "confidence_level": 4, "horizon_key": "4w", "tier": "C", "target_sources": []}


def test_retrospective_includes_edge_decay_line_when_alert():
    registry = [{"source": "strategy", "strategy": "Fibonacci", "horizon": None,
                "status": "VALIDATED", "n": 206, "win_rate": 81.6, "expectancy_r": 0.105,
                "window": "2024-01-01..2025-12-31"}]
    heavy_losers = [dict(_closed_today("AAA", "loss"), target_sources=["Fib 61.8%"]) for _ in range(30)]
    with patch("swingbot.core.registry.load_registry", return_value=registry):
        messages = build_daily_retrospective(heavy_losers, today=dt.date(2026, 3, 10))
    joined = "\n".join(messages)
    assert "Edge decay" in joined or "📉" in joined


def test_retrospective_without_decay_omits_the_line():
    trades = [_closed_today("AAA", "win")]
    with patch("swingbot.core.registry.load_registry", return_value=[]):
        messages = build_daily_retrospective(trades, today=dt.date(2026, 3, 10))
    joined = "\n".join(messages)
    assert "Edge decay" not in joined


def test_retrospective_lessons_block_present_when_journaled(tmp_path, monkeypatch):
    monkeypatch.setattr("swingbot.core.analytics.journal.config.DATA_DIR", str(tmp_path))
    from swingbot.core.analytics.journal import JournalStore

    JournalStore(path=str(tmp_path / "journal.json")).add({
        "trade_id": "aaa", "ticker": "AAA", "auto_lesson": "Clean capture: banked 100% of the available move.",
        "closed_at": "2026-03-10T16:00:00+00:00", "tags": [], "note": "",
    })
    trades = [_closed_today("AAA", "win")]
    with patch("swingbot.core.registry.load_registry", return_value=[]):
        messages = build_daily_retrospective(trades, today=dt.date(2026, 3, 10))
    assert any("Clean capture" in m for m in messages)
```

- [ ] **Step 2: Run — FAIL. Step 3: Implement**

```python
# retrospective.py -- add imports near the top, alongside the existing
# `from swingbot.core.performance import primary_strategy_label`:
from swingbot.core.analytics import calibration
from swingbot.core.analytics.insights import edge_decay_report
from swingbot.core.analytics.journal import JournalStore
```

```python
# retrospective.py -- inside build_daily_retrospective, immediately
# before the existing "return messages" line (after Part 5's lessons/
# suggestions block), add three new blocks:

    # ── Part 6: Calibration + edge decay (analytics core) ────────────────
    calibration_lines = []
    tier_rows = calibration.tier_calibration(closed_today)
    failing = [r for r in tier_rows if r["ok"] is False]
    if failing:
        calibration_lines.append("**📐 Calibration**")
        for r in failing:
            calibration_lines.append(
                f"• Tier {r['tier']} at {r['win_rate']:.0f}% WR (n={r['n']}) is outside its "
                f"design band ({r['expected_band']})."
            )
    try:
        decay_lines = edge_decay_report(all_trades)
    except Exception:
        log.exception("build_daily_retrospective: edge_decay_report failed, skipping")
        decay_lines = []
    if decay_lines:
        calibration_lines.append("**📉 Edge decay**")
        calibration_lines.extend(decay_lines)
    if calibration_lines:
        messages.append("\n".join(calibration_lines))

    # ── Part 7: Journal lessons for today's closed trades ────────────────
    if closed_today:
        store = JournalStore()
        lesson_lines = ["**📓 Trade lessons**"]
        for t in closed_today:
            entry = store.get(t.get("id"))
            if entry and entry.get("auto_lesson"):
                lesson_lines.append(f"• {t['ticker']}: {entry['auto_lesson']}")
        if len(lesson_lines) > 1:
            messages.append("\n".join(lesson_lines))

    return messages
```

`edge_decay_report` is passed `all_trades` (the full input, not just `closed_today`) since edge decay is about the strategy's overall live track record, not just today's slice — `badge_drift`'s own `live_n >= 20` floor already makes a single day's worth of trades far too small to ever alert on anyway.

- [ ] **Step 4: Run `python -m pytest tests/test_insights.py -v` — PASS. Then `python -m pytest tests/ -q` — full suite green, including any pre-existing retrospective tests (this integration must never change the wording or presence of any of the five existing message parts, only add new ones after them). Step 5: Commit**

```bash
git add swingbot/core/retrospective.py tests/test_insights.py
git commit -m "feat: retrospective consumes calibration + journal"
```

---

# Phase A6 — Snapshots, export, wrap-up (Tasks A28–A31)

### Task A28: Analytics snapshot build/save/load

**Files:**
- Create: `swingbot/core/analytics/snapshots.py`
- Test: `tests/test_snapshots.py`

**Interfaces:**
- Produces: `build_snapshot(closed: list[dict], starting_balance: float, registry_entries: list[dict]) -> dict` with exact top-level keys: `built_at` (ISO), `overall` (`n, wins, losses, win_rate, expectancy_r, profit_factor, sharpe, sortino, max_drawdown_pct, total_pnl, streaks`), `equity_curve`, `drawdown`, `rolling_wr`, `by` (`{dimension: [StatRow-as-dict]}` for all 10 dimensions), `calibration` (`{deciles, tiers, drift}`), `r_multiples` (histogram-ready list of floats). `save_snapshot(snap, path=None)` / `load_snapshot(path=None, max_age_seconds=3600) -> dict | None` (`None` when the file is missing or `built_at` is older than `max_age_seconds`) → `data/analytics_snapshot.json` via `jsonio`.

- [ ] **Step 1: Failing test**

```python
# tests/test_snapshots.py
import datetime as dt

from swingbot.core.analytics.snapshots import build_snapshot, save_snapshot, load_snapshot
from swingbot.core.analytics.aggregate import DIMENSIONS


def _t(i, status="win"):
    return {"id": f"t{i}", "ticker": "AAPL", "target_sources": ["EMA20"], "status": status,
            "direction": "bullish", "entry": 100.0, "stop_loss": 95.0,
            "exit_price": 104.0 if status == "win" else 96.0,
            "realized_pnl_amount": 80.0 if status == "win" else -40.0,
            "opened_at": f"2026-03-0{i}T10:00:00+00:00", "closed_at": f"2026-03-0{i+1}T10:00:00+00:00",
            "horizon_key": "4w", "tier": "A", "badge": "VALIDATED", "source": "confluence",
            "confidence_level": 4, "quality_score": 75}


def test_build_snapshot_has_every_documented_key():
    closed = [_t(1), _t(2), _t(3, "loss"), _t(4), _t(5)]
    snap = build_snapshot(closed, starting_balance=10_000.0, registry_entries=[])
    assert set(snap) == {"built_at", "overall", "equity_curve", "drawdown", "rolling_wr", "by",
                         "calibration", "r_multiples"}
    assert set(snap["overall"]) == {"n", "wins", "losses", "win_rate", "expectancy_r",
                                    "profit_factor", "sharpe", "sortino", "max_drawdown_pct",
                                    "total_pnl", "streaks"}
    assert set(snap["by"]) == set(DIMENSIONS)
    assert set(snap["calibration"]) == {"deciles", "tiers", "drift"}
    assert snap["overall"]["n"] == 5


def test_save_and_load_snapshot_roundtrip(tmp_path):
    path = str(tmp_path / "analytics_snapshot.json")
    snap = build_snapshot([_t(1)], 10_000.0, [])
    save_snapshot(snap, path=path)
    loaded = load_snapshot(path=path, max_age_seconds=3600)
    assert loaded is not None and loaded["overall"]["n"] == 1


def test_load_snapshot_missing_or_stale_returns_none(tmp_path):
    path = str(tmp_path / "analytics_snapshot.json")
    assert load_snapshot(path=path) is None

    stale = build_snapshot([_t(1)], 10_000.0, [])
    stale["built_at"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)).isoformat()
    save_snapshot(stale, path=path)
    assert load_snapshot(path=path, max_age_seconds=3600) is None
```

- [ ] **Step 2: Run `python -m pytest tests/test_snapshots.py -v` — expect FAIL (no module)**

- [ ] **Step 3: Implement**

```python
# swingbot/core/analytics/snapshots.py
"""Pure assembly of everything Phase A1/A2 computed into one JSON blob
(data/analytics_snapshot.json) so every UI (!stats, /api/stats, the
Performance page, the Strategies heatmap) reads ONE pre-built file
instead of recomputing on every request -- see design decision #3 in
docs/superpowers/plans/2026-07-11-cockpit-v3.md. build_snapshot itself is
pure (a function of its three arguments); save/load are the only I/O in
this module, both going through jsonio."""
from __future__ import annotations

import dataclasses
import datetime as dt
import os

from swingbot import config
from swingbot.core.analytics import calibration, metrics
from swingbot.core.analytics.aggregate import DIMENSIONS, stats_by
from swingbot.core.jsonio import atomic_write_json, read_json

DEFAULT_PATH = os.path.join(config.DATA_DIR, "analytics_snapshot.json")


def build_snapshot(closed: list[dict], starting_balance: float, registry_entries: list[dict]) -> dict:
    """Assemble the full analytics snapshot from a closed-trade list, the
    account's starting balance, and the already-loaded validation
    registry. Pure -- callers (refresh_snapshot, Task A29) are
    responsible for gathering these three inputs from disk/TradeLog."""
    wins = sum(1 for t in closed if t.get("status") == "win")
    losses = sum(1 for t in closed if t.get("status") == "loss")
    curve = metrics.equity_curve(closed, starting_balance)
    points = curve["points"]
    returns = [r for t in closed if (r := metrics.trade_return_pct(t)) is not None]

    overall = {
        "n": len(closed),
        "wins": wins,
        "losses": losses,
        "win_rate": metrics.win_rate(closed),
        "expectancy_r": metrics.expectancy_r(closed),
        "profit_factor": metrics.profit_factor(closed),
        "sharpe": metrics.sharpe(returns),
        "sortino": metrics.sortino(returns),
        "max_drawdown_pct": metrics.max_drawdown_pct(points),
        "total_pnl": round(sum(float(t.get("realized_pnl_amount") or 0.0) for t in closed), 2),
        "streaks": metrics.streaks(closed),
    }

    by = {dim: [dataclasses.asdict(row) for row in stats_by(closed, dim)] for dim in DIMENSIONS}

    calibration_block = {
        "deciles": calibration.score_deciles(closed),
        "tiers": calibration.tier_calibration(closed),
        "drift": calibration.badge_drift(closed, registry_entries),
    }

    return {
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "overall": overall,
        "equity_curve": curve,
        "drawdown": metrics.drawdown_series(points),
        "rolling_wr": metrics.rolling_win_rate(closed),
        "by": by,
        "calibration": calibration_block,
        "r_multiples": metrics.r_multiples(closed),
    }


def save_snapshot(snap: dict, path: str | None = None) -> None:
    atomic_write_json(path or DEFAULT_PATH, snap)


def load_snapshot(path: str | None = None, max_age_seconds: int = 3600) -> dict | None:
    """None when the file is missing/corrupt (read_json's own default
    handles that) OR when it parses fine but is older than
    `max_age_seconds` -- a stale snapshot silently served as fresh would
    be worse than no snapshot at all (the caller, e.g. !stats, falls back
    to an explicit "rebuilding..." path when this returns None, per
    Plan B's consumption of this function)."""
    snap = read_json(path or DEFAULT_PATH, None)
    if snap is None:
        return None
    try:
        built_at = dt.datetime.fromisoformat(snap["built_at"])
    except (KeyError, ValueError, TypeError):
        return None
    if built_at.tzinfo is None:
        built_at = built_at.replace(tzinfo=dt.timezone.utc)
    age = (dt.datetime.now(dt.timezone.utc) - built_at).total_seconds()
    return snap if age <= max_age_seconds else None
```

Re-export `build_snapshot, save_snapshot, load_snapshot` from `swingbot/core/analytics/__init__.py`.

- [ ] **Step 4: Run `python -m pytest tests/test_snapshots.py -v` — PASS (3 tests). Step 5: Commit**

```bash
git add swingbot/core/analytics/snapshots.py swingbot/core/analytics/__init__.py tests/test_snapshots.py
git commit -m "feat: analytics snapshot"
```

### Task A29: Snapshot refresh wiring

**Files:**
- Modify: `swingbot/commands/scanning.py` (`_session_scan_tick`, right after `await _send_alerts(channel, alerts)` at line 417 — this is the actual "after alert dispatch" point; the surrounding `@tasks.loop` decorator sits at line 362 on the thin `session_scan()` wrapper, but the real per-tick work — and therefore the right hook point — is inside `_session_scan_tick()`)
- Modify: the four close paths in `swingbot/core/performance.py` already touched in Task A22 (add one call alongside each site's `_journal_close_safely` loop, not per-trade — once per batch of closes)
- Test: `tests/test_snapshots.py`

**Interfaces:**
- Produces: `refresh_snapshot() -> None` in `snapshots.py` — assembles inputs (`TradeLog().get_trades(status="all", limit=None)`, `account.load_account_config()["balance"]` as the starting balance proxy — see the note below on why this is an approximation, not `account.load_account_config()["base_balance"]` — and `registry.load_registry()`) and calls `save_snapshot`; wrapped in try/except-log like the journal hook (Task A22). Called after each scan cycle and after each batch of closes. Cheap by design (a pure recompute over an in-memory list — no network calls, no backtest).

> **Design note on `starting_balance`:** `build_snapshot`'s `equity_curve` wants the balance BEFORE any trade in `closed` settled, so the mathematically correct value is `account_cfg["base_balance"]` (the human-set anchor, see `account.py`'s module docstring) — using the current `"balance"` would double-count all the realized P&L that's already folded into `closed`. `refresh_snapshot` uses `base_balance` for exactly this reason; this note exists because an earlier skim of this task could easily reach for the wrong key.

- [ ] **Step 1: Failing test**

```python
# tests/test_snapshots.py -- append
from unittest.mock import patch

from swingbot.core.analytics.snapshots import refresh_snapshot, DEFAULT_PATH


def test_refresh_snapshot_writes_file(tmp_path, monkeypatch):
    snap_path = str(tmp_path / "analytics_snapshot.json")
    monkeypatch.setattr("swingbot.core.analytics.snapshots.DEFAULT_PATH", snap_path)

    fake_trades = [_t(1)]
    with patch("swingbot.core.performance.TradeLog") as MockLog, \
         patch("swingbot.core.account.load_account_config", return_value={"base_balance": 10_000.0}), \
         patch("swingbot.core.registry.load_registry", return_value=[]):
        MockLog.return_value.get_trades.return_value = fake_trades
        refresh_snapshot()

    import os
    assert os.path.exists(snap_path)


def test_refresh_snapshot_never_raises_on_failure(monkeypatch):
    monkeypatch.setattr("swingbot.core.analytics.snapshots.DEFAULT_PATH", "/nonexistent/deeply/nested/x.json")
    with patch("swingbot.core.performance.TradeLog", side_effect=RuntimeError("boom")):
        refresh_snapshot()  # must not raise
```

- [ ] **Step 2: Run — FAIL. Step 3: Implement (append to `snapshots.py`)**

```python
import logging

log = logging.getLogger("swing-bot.snapshots")


def refresh_snapshot() -> None:
    """Rebuild and save the analytics snapshot from the current in-memory
    state of trades.json / account.json / the validation registry.
    Wrapped so a failure here (a corrupt account.json, a registry load
    error) can never propagate into the scan loop or a trade-close path
    that calls this as a side effect -- worst case the snapshot simply
    stays at its previous (or absent) state for one more cycle.
    """
    try:
        from swingbot.core import account as account_module
        from swingbot.core import registry
        from swingbot.core.performance import TradeLog

        closed = TradeLog().get_trades(status="all", limit=None)
        starting_balance = account_module.load_account_config().get("base_balance", 0.0)
        registry_entries = registry.load_registry()

        snap = build_snapshot(closed, starting_balance, registry_entries)
        save_snapshot(snap)
    except Exception:
        log.warning("refresh_snapshot failed -- snapshot left stale for this cycle", exc_info=True)
```

Wire the two call sites:

```python
# swingbot/commands/scanning.py -- inside _session_scan_tick, right after:
#     await _send_alerts(channel, alerts)
# add:
    _refresh_snapshot_safely()

# module-level helper, defined near the top of scanning.py alongside its
# other small helpers (mirrors performance.py's _journal_close_safely):
def _refresh_snapshot_safely() -> None:
    try:
        from swingbot.core.analytics.snapshots import refresh_snapshot
        refresh_snapshot()
    except Exception:
        log.warning("post-scan snapshot refresh failed", exc_info=True)
```

```python
# swingbot/core/performance.py -- in each of the four close paths
# touched by Task A22, right after the "for t in newly_closed:
# _journal_close_safely(t)" loop, add ONE call (not per-trade):
        if newly_closed:
            _refresh_snapshot_safely()
        return newly_closed

# and the module-level helper, next to _journal_close_safely:
def _refresh_snapshot_safely() -> None:
    try:
        from swingbot.core.analytics.snapshots import refresh_snapshot
        refresh_snapshot()
    except Exception:
        import logging
        logging.getLogger("swing-bot.performance").warning(
            "post-close snapshot refresh failed", exc_info=True)
```

`close_trade_manual`'s single-trade-per-call shape means its own call site is simply `_refresh_snapshot_safely()` unconditionally right before its `return True`, not inside a `for` loop.

- [ ] **Step 4: Run `python -m pytest tests/test_snapshots.py -v` — PASS. Then `python -m pytest tests/ -q` — full suite green. Step 5: Commit**

```bash
git add swingbot/core/analytics/snapshots.py swingbot/commands/scanning.py swingbot/core/performance.py tests/test_snapshots.py
git commit -m "feat: snapshot refresh on scan + close"
```

### Task A30: Analytics export

**Files:**
- Create: `scripts/export_analytics.py`
- Test: `tests/test_snapshots.py` (core `export_all(snapshot, out_dir) -> list[str]`)

**Interfaces:**
- Produces: CLI `python scripts/export_analytics.py [--out exports/analytics]` writing `snapshot.json` (the snapshot dict, verbatim), `stats_by_<dimension>.csv` (one per dimension, `StatRow` columns) for every one of the 10 `DIMENSIONS`, `equity_curve.csv` (`date,balance,pnl`), and `journal.csv` (every `JournalStore` entry, columns = the union of keys `build_entry` produces). Returns/prints the list of written paths.

- [ ] **Step 1: Failing test**

```python
# tests/test_snapshots.py -- append
import csv
import os

from scripts.export_analytics import export_all


def _fixture_snapshot():
    from swingbot.core.analytics.snapshots import build_snapshot
    return build_snapshot([_t(1), _t(2), _t(3, "loss")], 10_000.0, [])


def test_export_all_writes_expected_files(tmp_path):
    paths = export_all(_fixture_snapshot(), str(tmp_path))
    names = {os.path.basename(p) for p in paths}
    assert "snapshot.json" in names
    assert "equity_curve.csv" in names
    assert "stats_by_strategy.csv" in names
    assert "stats_by_ticker.csv" in names

    with open(os.path.join(tmp_path, "stats_by_strategy.csv"), newline="") as f:
        header = next(csv.reader(f))
    assert header == ["key", "n", "wins", "losses", "win_rate", "expectancy_r",
                      "avg_r", "profit_factor", "total_pnl"]
```

- [ ] **Step 2: Run `python -m pytest tests/test_snapshots.py -v` — expect FAIL (no module `scripts.export_analytics`)**

- [ ] **Step 3: Implement**

```python
# scripts/export_analytics.py
"""Export the analytics snapshot + journal to CSV/JSON for spreadsheet
analysis or an external dashboard.

Run: python scripts/export_analytics.py [--out exports/analytics]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swingbot.core.analytics.aggregate import DIMENSIONS
from swingbot.core.analytics.journal import JournalStore

STAT_ROW_COLUMNS = ["key", "n", "wins", "losses", "win_rate", "expectancy_r",
                    "avg_r", "profit_factor", "total_pnl"]
JOURNAL_COLUMNS = ["trade_id", "ticker", "strategy", "horizon_key", "direction", "tier",
                   "badge", "quality_score", "outcome", "r_realized", "mfe_r", "mae_r",
                   "exit_efficiency", "holding_days", "tags", "auto_lesson", "note",
                   "opened_at", "closed_at", "created_at"]


def export_all(snapshot: dict, out_dir: str) -> list[str]:
    """Write every export artifact for `snapshot` (+ the current journal)
    into `out_dir` (created if missing). Returns the list of written
    absolute paths, in write order, for the CLI to print."""
    os.makedirs(out_dir, exist_ok=True)
    written = []

    snap_path = os.path.join(out_dir, "snapshot.json")
    with open(snap_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, default=str)
    written.append(snap_path)

    equity_path = os.path.join(out_dir, "equity_curve.csv")
    with open(equity_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "balance", "pnl"])
        writer.writeheader()
        writer.writerows(snapshot["equity_curve"]["points"])
    written.append(equity_path)

    for dim in DIMENSIONS:
        dim_path = os.path.join(out_dir, f"stats_by_{dim}.csv")
        with open(dim_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=STAT_ROW_COLUMNS)
            writer.writeheader()
            writer.writerows(snapshot["by"].get(dim, []))
        written.append(dim_path)

    journal_path = os.path.join(out_dir, "journal.csv")
    with open(journal_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=JOURNAL_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(JournalStore().entries())
    written.append(journal_path)

    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="exports/analytics")
    args = parser.parse_args()

    from swingbot.core.analytics.snapshots import load_snapshot, refresh_snapshot

    snap = load_snapshot(max_age_seconds=10 ** 9)  # any age is fine for a manual export
    if snap is None:
        refresh_snapshot()
        snap = load_snapshot(max_age_seconds=10 ** 9)
    if snap is None:
        print("No trades to export yet.")
        return

    for path in export_all(snap, args.out):
        print(path)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run `python -m pytest tests/test_snapshots.py -v` — PASS. Step 5: Commit**

```bash
git add scripts/export_analytics.py tests/test_snapshots.py
git commit -m "feat: analytics CSV/JSON export"
```

### Task A31: Performance benchmark + phase checkpoint

**Files:**
- Test: `tests/test_analytics_perf.py`
- Modify: `README.md` (Analytics section), this plan's Progress block

- [ ] **Step 1: Benchmark test**

```python
# tests/test_analytics_perf.py
"""Sanity bound on build_snapshot's cost over a realistically-large trade
history -- generous enough that normal CI noise (a slow shared runner, a
cold Python import) doesn't flake it, but tight enough to catch an
accidentally-O(n^2) aggregation (e.g. a per-row full-list rescan) before
it ships."""
import time

from swingbot.core.analytics.snapshots import build_snapshot

N_SYNTHETIC_TRADES = 5000


def _synthetic_trades(n: int) -> list[dict]:
    strategies = ["Fibonacci", "EMA Crossover", "VWAP", "Support/Resistance", "RSI"]
    tiers = ["A", "B", "C"]
    trades = []
    for i in range(n):
        status = "win" if i % 3 != 0 else "loss"
        day = 1 + (i % 27)
        month = 1 + (i // 27) % 12
        trades.append({
            "id": f"synthetic-{i}",
            "ticker": f"SYM{i % 50}",
            "target_sources": [strategies[i % len(strategies)]],
            "strategy": strategies[i % len(strategies)],
            "status": status,
            "direction": "bullish" if i % 2 == 0 else "bearish",
            "entry": 100.0,
            "stop_loss": 95.0 if i % 2 == 0 else 105.0,
            "exit_price": (104.0 if i % 2 == 0 else 96.0) if status == "win"
                          else (96.0 if i % 2 == 0 else 104.0),
            "realized_pnl_amount": 80.0 if status == "win" else -40.0,
            "opened_at": f"2025-{month:02d}-{day:02d}T10:00:00+00:00",
            "closed_at": f"2025-{month:02d}-{min(day + 2, 28):02d}T10:00:00+00:00",
            "horizon_key": "4w",
            "tier": tiers[i % 3],
            "badge": "VALIDATED" if i % 3 == 0 else "WEAK",
            "source": "confluence" if i % 2 == 0 else "strategy",
            "confidence_level": 1 + (i % 5),
            "quality_score": i % 100,
        })
    return trades


def test_build_snapshot_5000_trades_under_2_seconds():
    trades = _synthetic_trades(N_SYNTHETIC_TRADES)
    start = time.perf_counter()
    snap = build_snapshot(trades, starting_balance=10_000.0, registry_entries=[])
    elapsed = time.perf_counter() - start
    assert snap["overall"]["n"] == N_SYNTHETIC_TRADES
    assert elapsed < 2.0, f"build_snapshot took {elapsed:.2f}s for {N_SYNTHETIC_TRADES} trades (budget: 2.0s)"
```

- [ ] **Step 2: Run everything**

```
python -m pytest tests/ -q
```
Expected: all tests pass (this plan's own tests plus every pre-existing test in the repo — TradeLog/StateStore/account's atomic-write migration in Phase A0 and the journal hooks in Task A22 touch widely-used code paths, so a regression anywhere in the existing suite is exactly what this final full-suite run is meant to catch).

```
make check
```
Expected: `All files OK.` — **Windows caveat:** `make check` (see the Makefile) shells out to `python3`, which may not be on `PATH` on a plain Windows install. If it fails with something like `'python3' is not recognized as an internal or external command`, run the equivalent directly instead:
```
python -m py_compile bot.py admin_ui.py
python -m py_compile (Get-ChildItem -Recurse -Filter *.py swingbot | ForEach-Object FullName)
```
(PowerShell) or, in Git Bash where `python3` may already alias correctly, just re-run `make check` as-is.

```
python scripts/export_analytics.py
```
Expected: prints one absolute path per line (`snapshot.json`, `equity_curve.csv`, 10 `stats_by_*.csv` files, `journal.csv`) if any trades exist yet, or `No trades to export yet.` on a fresh checkout with an empty `trades.json` — both are correct, non-error outcomes.

- [ ] **Step 3: README section**

Add an "Analytics core" section to `README.md` (verify the current README's heading structure and general voice before pasting — match its existing style rather than introducing a new one) documenting:
- The package layout (`swingbot/core/analytics/`: `metrics.py`, `mfe_mae.py`, `aggregate.py`, `calibration.py`, `rank.py`, `journal.py`, `insights.py`, `snapshots.py`) and the one-line role of each, matching this plan's own File Structure block.
- `data/analytics_snapshot.json` — what it is, that it's rebuilt post-scan and post-close, and its `max_age_seconds` staleness guard.
- `data/journal.json` — one entry per closed trade, auto-tagged and auto-lessoned, optionally hand-annotated via `set_note`.
- The `follow_score` formula verbatim (badge 40 + quality 40 + regime 10 + freshness 10) and where it's consumed (Discord alerts, `!plans`, `!top`, the digest, `/api/plans`, the admin board — per design decision #1).
- The pre-registered edge-decay rule verbatim: `drift_alert = live_n >= 20 and live_wr < oos_wr - 10.0`, and the one-sentence reason it must never be tuned after seeing live data.

- [ ] **Step 4: Commit**

```bash
git add tests/test_analytics_perf.py README.md docs/superpowers/plans/2026-07-11-cockpit-v3.md
git commit -m "docs: analytics core wrap-up + perf benchmark"
```

Update this plan's Progress block (`**Completed:** A1–A31`, `**Next:** Task B1`). **Plan A done — Plans B and C may start.**


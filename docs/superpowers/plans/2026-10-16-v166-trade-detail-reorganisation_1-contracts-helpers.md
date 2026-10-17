# v166 Trade detail reorganisation. Part 1: contracts and helpers (TD1..TD4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task TD3:" -A 300 docs/superpowers/plans/2026-10-16-v166-trade-detail-reorganisation_1-contracts-helpers.md`.

**Spec:** [`docs/superpowers/specs/2026-10-16-v166-trade-detail-reorganisation-design.md`](../specs/2026-10-16-v166-trade-detail-reorganisation-design.md) (this part: § 1 exit-reason labels, average exit, status groups, drift check; § 3 API addition and the Plan/Position figures; Edge cases; Amendments 2, 5, 6)
**Index:** [`2026-10-16-v166-trade-detail-reorganisation_0-index.md`](2026-10-16-v166-trade-detail-reorganisation_0-index.md) carries the header, `## Global Constraints`, `## Review Focus`, `## Parallelisation` and the task ledger. Every task below implicitly includes the Global Constraints.

**Paths.** `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree), `$WT` = `$R/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation` (created in TD1 Step 1). Never `cd`; use `git -C $WT`, `python $WT/scripts/dev/testrun.py file <test>` and `npm --prefix $WT/frontend exec -- ng test --watch=false --include <spec>`. All file paths below are relative to `$WT` unless they say `$R`.

**`GATES`** (from the index) = `--include src/app/ui/primitives.spec.ts --include src/app/ui/async-coverage.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/contrast.spec.ts`.

**Order.** TD1, TD2 and TD3 touch disjoint files and may run in parallel once TD1 Step 1 has created the worktree. TD4 runs after TD1 (it reads `TradeRow.risk_stop`).

---

# Phase 1 — Contracts and pure helpers

### Task TD1: Worktree; publish `risk_stop` on trade rows; API contract and PARTIAL tests; TS field

**Model:** sonnet — one backend module plus one TS type, behaviour fixed by the spec

**Files:**
- Modify: `swingbot/admin/api_v1/trades.py` (`_row_from_plan` :313-316, `_row_from_trade` :515-518, `_attach_unrealized_pnl` docstring :991-997 and read :1010, `_strip_internal_fields` :1019-1035)
- Modify: `tests/admin/test_api_v1_trades.py` (`TRADE_ROW` :61, the leak test docstring :1227-1228, new tests appended after the leak test)
- Modify: `tests/admin/test_trades_partial_row.py` (one test appended)
- Modify: `frontend/src/app/api/models.ts` (`TradeRow`, after `stop_loss` at :101)

**Interfaces:**
- Consumes: nothing from this plan. From `main`: `_row_from_plan(plan, trade, noted) -> dict`, `_row_from_trade(t, noted) -> dict`, `_attach_unrealized_pnl(rows)`, `_strip_internal_fields(rows)`, `dash.unrealized_r(entry, stop, direction, price)`; test helpers `_plan`, `_trade`, `seed`, `logged_in`, `priced`, `assert_collection`, `NULLABLE_NUMBER` (in `tests/admin/test_api_v1_trades.py` / `tests/admin/api_v1_contract.py`); `partial_plan(**kw)` in `tests/admin/test_trades_partial_row.py`.
- Produces (consumed by TD4 and, through it, TD5/TD7):
  - Wire: every `/api/v1/trades` list row, every leg row (`_row_from_leg` / `_expand_plan_row` inherit it from `_row_from_plan`) and the `/api/v1/trades/<id>` row carries `risk_stop: float | None` — the plan's `stop_loss` (the original risk stop) for plan rows, the trade's `stop_loss` for legacy rows. No code in `swingbot/` reads or writes `_risk_stop` any more.
  - TS: `TradeRow.risk_stop?: number | null`, declared directly after `stop_loss`.

**Why a rename and nothing else.** `_row_from_plan` is radon C(15); a dict-literal key adds no branch, and the rename keeps the existing value (`plan.get("stop_loss")`, which on PARTIAL is the original stop while the row's `stop_loss` is `view.stop`, the working stop). `_attach_unrealized_pnl` keeps reading it with `.get` (it can run twice per request). `_strip_internal_fields` stops popping it, because it is now a declared public key. `trade_commands._plan_row` / `_trade_row` (close and cancel responses) never called `_strip_internal_fields`, so they used to leak `_risk_stop`; they now carry the public `risk_stop`, which is the declared shape.

- [ ] **Step 1: Create the worktree**

Invoke the `worktree-lifecycle` skill. Reuse the worktree if `git -C E:/Documents/Private/Projects/Discord-Bot worktree list` already shows `2026-10-16-v166-trade-detail-reorganisation`; otherwise:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot fetch --quiet origin
git -C E:/Documents/Private/Projects/Discord-Bot worktree add .claude/worktrees/2026-10-16-v166-trade-detail-reorganisation -b 2026-10-16-v166-trade-detail-reorganisation main
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation log --oneline -1
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation/frontend ci
```

Expected: the log line is the current `main` HEAD (the commit that carries this plan); `npm ci` ends without `ERR!`. Every later step runs in `$WT`.

- [ ] **Step 2: Declare `risk_stop` in the row contract**

In `tests/admin/test_api_v1_trades.py`, inside `TRADE_ROW`, directly after `"stop_loss": NULLABLE_NUMBER,` (line 61), add:

```python
    # v166 -- the plan's ORIGINAL risk stop. On PARTIAL, `stop_loss` is the
    # working (trailing) stop; the trade page needs both to say "move your
    # resting stop to X (was Y)" and to size risk per share from the
    # original stop.
    "risk_stop": NULLABLE_NUMBER,
```

Replace the docstring of `test_no_internal_bookkeeping_fields_leak_onto_the_wire` (lines 1227-1228) with:

```python
    """No transient bookkeeping key (`_display_shares`) reaches the wire,
    and `risk_stop` -- transient as `_risk_stop` until v166 -- is now a
    declared field: the contract check below fails loudly on any
    undeclared or missing key."""
```

- [ ] **Step 3: Write the failing tests**

Append to `tests/admin/test_api_v1_trades.py`, directly after `test_no_internal_bookkeeping_fields_leak_onto_the_wire`:

```python
# --- v166: risk_stop, the plan's original stop -----------------------------

def _partial_pair(working_stop=104.0):
    plan = _plan("11111111-1111-4111-8111-111111111111", status="PARTIAL")
    plan["working_stop"] = working_stop
    plan["legs_realized"] = [{"fraction": 0.5, "exit_price": 110.0, "r": 1.5,
                              "reason": "tp1"}]
    trade = _trade("aaaaaaaaaaaaaaaa", plan_id=plan["plan_id"], status="open")
    return plan, trade


def test_partial_rows_publish_the_original_stop_as_risk_stop(seed, logged_in, priced):
    """On PARTIAL the row's `stop_loss` is the working stop; `risk_stop`
    is the plan's original stop (95.0), on the runner row and every leg row."""
    plan, trade = _partial_pair()
    seed(plans=[plan], trades=[trade])
    priced(115.0)

    items = logged_in.get("/api/v1/trades").get_json()["items"]
    assert items, "the PARTIAL plan produced no rows"
    assert {row["risk_stop"] for row in items} == {95.0}
    runner = next(r for r in items if r["status"] == "PARTIAL")
    assert runner["stop_loss"] != 95.0


def test_partial_r_multiple_is_still_measured_against_the_original_stop(
        seed, logged_in, priced):
    """The rename must not change `_attach_unrealized_pnl`'s input."""
    plan, trade = _partial_pair()
    seed(plans=[plan], trades=[trade])
    priced(115.0)

    items = logged_in.get("/api/v1/trades").get_json()["items"]
    runner = next(r for r in items if r["status"] == "PARTIAL")
    assert runner["r_multiple"] == pytest.approx((115.0 - 101.0) / (101.0 - 95.0), abs=0.01)


def test_trade_detail_row_carries_risk_stop(seed, logged_in, priced):
    plan, trade = _partial_pair()
    seed(plans=[plan], trades=[trade])
    priced(115.0)

    body = logged_in.get(f"/api/v1/trades/{plan['plan_id']}").get_json()
    assert body["risk_stop"] == 95.0
    assert body["stop_loss"] != 95.0


def test_legacy_row_risk_stop_is_its_own_stop(seed, logged_in):
    seed(trades=[_trade("cccccccccccccccc", plan_id=None)])
    row = logged_in.get("/api/v1/trades").get_json()["items"][0]
    assert row["risk_stop"] == row["stop_loss"] == 95.0


def test_pending_plan_row_carries_its_planned_stop(seed, logged_in):
    seed(plans=[_plan("22222222-2222-4222-8222-222222222222", status="PENDING")])
    row = logged_in.get("/api/v1/trades").get_json()["items"][0]
    assert row["risk_stop"] == 95.0
```

Append to `tests/admin/test_trades_partial_row.py`:

```python
def test_risk_stop_is_the_plan_stop_while_stop_loss_is_the_working_stop():
    """v166: the row publishes the original stop beside the working one."""
    row = _row_from_plan(partial_plan(), None, set())
    assert row["risk_stop"] == 90.0
    assert round(row["stop_loss"], 4) == 113.3333
    assert "_risk_stop" not in row
```

- [ ] **Step 4: Run them to verify they fail**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation/scripts/dev/testrun.py file tests/admin/test_api_v1_trades.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation/scripts/dev/testrun.py file tests/admin/test_trades_partial_row.py
```

Expected: FAIL. In `test_api_v1_trades.py` every `assert_shape` / `assert_collection` case fails on the missing `risk_stop` key and the new cases fail with `KeyError: 'risk_stop'`; `test_partial_r_multiple_is_still_measured_against_the_original_stop` already PASSES (it pins today's behaviour across the rename). In `test_trades_partial_row.py` the new case fails with `KeyError: 'risk_stop'`.

- [ ] **Step 5: Rename the key in `trades.py`**

In `_row_from_plan`, replace lines 313-316:

```python
        # Transient -- consumed and stripped by `_attach_unrealized_pnl`
        # once a live price exists to compute pnl_pct/r_multiple/
        # realized_pnl_amount for a row that hasn't closed yet.
        "_risk_stop": plan.get("stop_loss"),
```

with:

```python
        # The plan's ORIGINAL risk stop (v166, public). `stop_loss` above is
        # `view.stop` -- the working/trailing stop once PARTIAL -- so this is
        # the only place the original survives on the row. Also read by
        # `_attach_unrealized_pnl` to measure live R against original risk.
        "risk_stop": plan.get("stop_loss"),
```

In `_row_from_trade`, replace lines 515-518:

```python
        # Transient -- see `_row_from_plan`'s matching field. Legacy v1
        # trades never scale out, so `_risk_stop` is always the same value
        # already shown as `stop_loss`.
        "_risk_stop": t.get("stop_loss"),
```

with:

```python
        # See `_row_from_plan`'s matching field. Legacy v1 trades never scale
        # out, so `risk_stop` is always the same value shown as `stop_loss`.
        "risk_stop": t.get("stop_loss"),
```

In `_attach_unrealized_pnl`, replace the docstring paragraph (lines 991-997):

```python
    Reads `_risk_stop` (transient, set by the two row builders) with
    `.get`, not `.pop`: like `_attach_status_fields`, this may run twice on
    the same row objects when a request sorts by a field that needs a price
    for every row, not just the page (see the `_SORT_ALIASES` branch in
    `list_trades`) -- popping here would make the second pass recompute from
    an empty/missing fallback and silently overwrite the first pass's real
    numbers. `_strip_internal_fields` removes it once, at the very end.
```

with:

```python
    Reads `risk_stop` (the original stop, set by the two row builders and
    published on the wire since v166). Like `_attach_status_fields`, this
    may run twice on the same row objects when a request sorts by a field
    that needs a price for every row, not just the page (see the
    `_SORT_ALIASES` branch in `list_trades`), so it only ever reads it.
```

and the read at line 1010:

```python
            row["r_multiple"] = dash.unrealized_r(entry, row.get("_risk_stop"), direction, price)
```

with:

```python
            row["r_multiple"] = dash.unrealized_r(entry, row.get("risk_stop"), direction, price)
```

Replace the whole of `_strip_internal_fields` (lines 1019-1035) with:

```python
def _strip_internal_fields(rows: list[dict]) -> None:
    """Drop the transient `_display_shares` key -- must run exactly once,
    after every other row transform, so it never leaks onto the wire and
    breaks the row's declared shape.

    Applies `_display_shares` to the public `shares` field for partially-realized
    rows (v79), showing the true remaining share count instead of the original
    size. This override happens exactly once here, after all possible passes of
    `_attach_unrealized_pnl` are complete, so the original `shares` value is
    preserved for each P&L calculation pass. (`risk_stop`, transient as
    `_risk_stop` until v166, is a public field now and is kept.)
    """
    for row in rows:
        if "_display_shares" in row:
            row["shares"] = row.pop("_display_shares")
        else:
            row.pop("_display_shares", None)
```

Confirm no code still names the old key:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation grep -nw "_risk_stop" -- swingbot tests
```

Expected (`-w`, so test names like `..._break_even_risk_stop` do not match): exactly three hits, none of them code that reads or writes the key: the `_strip_internal_fields` docstring in `trades.py`, the leak-test docstring in `tests/admin/test_api_v1_trades.py`, and the `"_risk_stop" not in row` assertion in `tests/admin/test_trades_partial_row.py`. No `row.get("_risk_stop")`, no `"_risk_stop":` key, no `pop("_risk_stop"`.

- [ ] **Step 6: Run the tests to verify they pass, plus the neighbours that build trade rows**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation/scripts/dev/testrun.py file tests/admin/test_api_v1_trades.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation/scripts/dev/testrun.py file tests/admin/test_trades_partial_row.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation/scripts/dev/testrun.py file tests/admin/test_api_v1_trade_detail.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation/scripts/dev/testrun.py file tests/presentation/test_surface_agreement.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation/scripts/dev/testrun.py file tests/admin/test_cohort_api.py
```

Expected: each ends `0 failed` and `0 xfailed`. If `test_partial_rows_publish_the_original_stop_as_risk_stop` fails only on `runner["stop_loss"] != 95.0`, print the runner row and read `plan_view`'s PARTIAL stop before touching the assertion: the spec's premise is that `stop_loss` is the working stop on PARTIAL (`tests/presentation/test_surface_agreement.py::test_no_surface_shows_original_risk_stop` pins it).

- [ ] **Step 7: Complexity did not get worse**

```bash
python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation/swingbot/admin/api_v1/trades.py
```

Expected: `_row_from_plan` still prints `C (15)` (as on `main`) and no other function in the file is newly listed.

- [ ] **Step 8: Add the TypeScript field**

In `frontend/src/app/api/models.ts`, inside `TradeRow`, directly after `stop_loss: number | null;` (line 101), add:

```ts
  /** v166 -- the plan's ORIGINAL risk stop. `stop_loss` is the working
   *  (trailing) stop once a plan is PARTIAL; this is the stop the position
   *  was sized against, so risk per share and "$ at risk" read it first.
   *  The API always sends it (null on a row with no stop). Optional here,
   *  like `cohort_label`, so a typed fixture written before this field
   *  existed is not forced to grow it. */
  risk_stop?: number | null;
```

Type-check through the existing store spec (it compiles `models.ts` and the store) plus the UI gates:

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation/frontend exec -- ng test --watch=false --include src/app/stores/trade-detail.store.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/async-coverage.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/contrast.spec.ts
```

Expected: all pass, no TypeScript error. A 60 s `Timeout waiting for worker ... no tests` is machine load: re-run once.

- [ ] **Step 9: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation add swingbot/admin/api_v1/trades.py tests/admin/test_api_v1_trades.py tests/admin/test_trades_partial_row.py frontend/src/app/api/models.ts
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation commit -m "feat(api): publish the plan's original stop as risk_stop on trade rows"
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation status --short
```

Expected: the status command prints nothing.

### Task TD2: `exit-reasons.ts` label table, `reasonLabel`, `exitReasonLabel`; pytest drift check

**Model:** sonnet — a pure table plus a cross-language drift test, rules fixed by the spec

**Files:**
- Create: `frontend/src/app/workspaces/trades/exit-reasons.ts`
- Create: `frontend/src/app/workspaces/trades/exit-reasons.spec.ts`
- Create: `tests/admin/test_exit_reason_labels.py`

**Interfaces:**
- Consumes: from `main`, `Leg {fraction: number | null; exitPrice: number | null; r: number | null; reason: string | null}` and `StatusEvent {status: string; reason: string | null; at: string | null}` (both exported by `frontend/src/app/stores/trade-detail.store.ts:44-57`, imported as types only); `ABSENT = '—'` (`frontend/src/app/ui/format.ts:10`); `metrics.EXIT_REASONS` and `metrics._EXIT_REASON_ALIASES` (`swingbot/core/analytics/metrics.py:27-33`, `:41-49`).
- Produces (consumed by TD5 and TD7):
  - `EXIT_REASON_LABELS: Readonly<Record<string, string>>` — one `'key': 'Label',` entry per line, single-quoted lower-case keys; the object literal ends with `};`. The drift test parses `^\s*'([^']+)'\s*:\s*'` between `export const EXIT_REASON_LABELS` and the first `};` after it.
  - `GAPPED_R = -1.05`
  - `reasonLabel(reason: string | null | undefined): string | null` — trims; empty or null -> `null`; lower-cased lookup; unknown -> the trimmed raw text.
  - `exitReasonLabel(legs: readonly Leg[], history: readonly StatusEvent[], r: number | null): string` — labels of the legs that carry a reason, in leg order, joined `' + '`; with no such leg, the label of the last `status_history` event whose reason is non-empty; with neither, `'—'`. `' (gapped)'` is appended when the last label is `'Stop'` and `r !== null && r < GAPPED_R`.

**Rules from the spec.** The table is § 1's "Exit-reason label" table, plus `stall_exit` (panel finding). The backend vocabulary owns the keys and the frontend owns only the wording (amendment 6): the drift test compares the table against `EXIT_REASONS` minus `"other"` (a bucket, not a reason text) plus every `_EXIT_REASON_ALIASES` key, and asserts `stall_exit` separately because the backend lists it in neither. Lookup lower-cases and trims, since fixtures use `'TP1'`.

- [ ] **Step 1: Write the failing drift test**

Create `tests/admin/test_exit_reason_labels.py`:

```python
"""v166 -- the trade page's exit-reason wording covers every backend reason.

`frontend/src/app/workspaces/trades/exit-reasons.ts` maps the reason text a
leg or a status_history entry carries to the words the trade page shows
("TP1 + Runner at breakeven"). The backend vocabulary in
`swingbot/core/analytics/metrics.py` owns the keys; the frontend owns only
the wording. A reason added to the backend without a label would render as
raw text on the page -- this test makes that a red build instead.

Read-a-file style: no Flask client, no store.
"""
import re
from pathlib import Path

from swingbot.core.analytics import metrics

_TS = (Path(__file__).resolve().parents[2]
       / "frontend" / "src" / "app" / "workspaces" / "trades" / "exit-reasons.ts")
_KEY = re.compile(r"^\s*'([^']+)'\s*:\s*'", re.M)

# `other` is the metrics bucket for "none of the above", never a reason
# text written onto a leg or a status_history entry.
_NOT_A_REASON = {"other"}


def _table_keys() -> set[str]:
    source = _TS.read_text(encoding="utf-8")
    start = source.index("export const EXIT_REASON_LABELS")
    end = source.index("};", start)
    return set(_KEY.findall(source[start:end]))


def test_the_label_table_parses():
    """Guards the parser itself: an empty set would make every check below pass."""
    assert len(_table_keys()) >= 10


def test_every_exit_reason_has_a_label():
    missing = set(metrics.EXIT_REASONS) - _NOT_A_REASON - _table_keys()
    assert not missing, f"exit-reasons.ts has no label for {sorted(missing)}"


def test_every_exit_reason_alias_has_a_label():
    missing = set(metrics._EXIT_REASON_ALIASES) - _table_keys()
    assert not missing, f"exit-reasons.ts has no label for {sorted(missing)}"


def test_stall_exit_has_a_label():
    """plan_manager writes `stall_exit`, but metrics lists it in neither
    EXIT_REASONS nor the aliases, so the two checks above never see it."""
    assert "stall_exit" in _table_keys()


def test_keys_are_stored_the_way_the_lookup_reads_them():
    """`reasonLabel` trims and lower-cases before the lookup."""
    assert all(key == key.strip().lower() for key in _table_keys())
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation/scripts/dev/testrun.py file tests/admin/test_exit_reason_labels.py
```

Expected: FAIL, every case with `FileNotFoundError` on `exit-reasons.ts`.

- [ ] **Step 3: Write the failing frontend spec**

Create `frontend/src/app/workspaces/trades/exit-reasons.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import type { Leg, StatusEvent } from '../../stores/trade-detail.store';
import { EXIT_REASON_LABELS, GAPPED_R, exitReasonLabel, reasonLabel } from './exit-reasons';

/* v166 — the exit-reason label on the trade page's Result strip and the
 * Outcome card's leg rows. SPCX (production trade f48c80e2) closed in two
 * legs, `tp1` then `tp1_runner_be`, for a blended +1.83R. */

const leg = (reason: string | null, r: number | null = null): Leg => ({
  fraction: 0.5, exitPrice: 100, r, reason,
});
const event = (status: string, reason: string | null): StatusEvent => ({
  status, reason, at: '2026-10-01T14:00:00Z',
});

describe('reasonLabel', () => {
  it('maps every spec row to its label', () => {
    const cases: Array<[string, string]> = [
      ['tp1', 'TP1'],
      ['tp1_runner_be', 'Runner at breakeven'], ['runner_be', 'Runner at breakeven'],
      ['tp1_runner_tp2', 'Runner at T2'], ['runner_tp2', 'Runner at T2'],
      ['runner_trail', 'Runner trailed'],
      ['stop', 'Stop'], ['loss', 'Stop'],
      ['scratch', 'Scratch'],
      ['timeout', 'Time exit'], ['time_exit', 'Time exit'],
      ['auto (near-tp stall)', 'Stall exit'], ['stall_exit', 'Stall exit'],
      ['reversed', 'Reversed'],
    ];
    for (const [reason, label] of cases) expect(reasonLabel(reason)).toBe(label);
  });

  it('keeps stall exits apart from time exits', () => {
    expect(reasonLabel('stall_exit')).not.toBe(reasonLabel('time_exit'));
  });

  it('trims and lower-cases before the lookup', () => {
    expect(reasonLabel('TP1')).toBe('TP1');
    expect(reasonLabel('  Runner_TRAIL ')).toBe('Runner trailed');
  });

  it('shows unknown text as written, trimmed', () => {
    expect(reasonLabel(' manual close ')).toBe('manual close');
  });

  it('returns null for no reason at all', () => {
    expect(reasonLabel(null)).toBeNull();
    expect(reasonLabel(undefined)).toBeNull();
    expect(reasonLabel('   ')).toBeNull();
  });

  it('stores only lower-case, trimmed keys', () => {
    for (const key of Object.keys(EXIT_REASON_LABELS)) expect(key).toBe(key.trim().toLowerCase());
  });
});

describe('exitReasonLabel', () => {
  it('joins a two-leg close in leg order (SPCX)', () => {
    const legs = [leg('tp1', 2.23), leg('tp1_runner_be', 1.43)];
    expect(exitReasonLabel(legs, [], 1.83)).toBe('TP1 + Runner at breakeven');
  });

  it('has no "+" for a single leg', () => {
    expect(exitReasonLabel([leg('runner_trail', 0.8)], [], 0.8)).toBe('Runner trailed');
  });

  it('skips a leg with no reason (the open runner)', () => {
    expect(exitReasonLabel([leg('TP1', 1.2), leg(null)], [], 0.6)).toBe('TP1');
  });

  it('labels a stall exit', () => {
    expect(exitReasonLabel([leg('stall_exit', 0.4)], [], 0.4)).toBe('Stall exit');
  });

  it('falls back to the last status_history reason when no leg has one', () => {
    const history = [event('ACTIVE', 'trigger filled'), event('CLOSED', 'time_exit'), event('CLOSED', null)];
    expect(exitReasonLabel([], history, -0.2)).toBe('Time exit');
  });

  it('says "—" with neither legs nor a history reason', () => {
    expect(exitReasonLabel([], [], null)).toBe('—');
    expect(exitReasonLabel([leg(null)], [event('CLOSED', null)], null)).toBe('—');
  });

  it('marks a stop that gapped past -1.05R', () => {
    expect(GAPPED_R).toBe(-1.05);
    expect(exitReasonLabel([leg('stop', -1.4)], [], -1.4)).toBe('Stop (gapped)');
    expect(exitReasonLabel([leg('loss', -1.2)], [], -1.2)).toBe('Stop (gapped)');
  });

  it('does not mark an ordinary stop, or one with no R', () => {
    expect(exitReasonLabel([leg('stop', -1.0)], [], -1.0)).toBe('Stop');
    expect(exitReasonLabel([leg('stop', -1.05)], [], -1.05)).toBe('Stop');
    expect(exitReasonLabel([leg('stop')], [], null)).toBe('Stop');
  });

  it('only marks the last label, and only when it is a stop', () => {
    expect(exitReasonLabel([leg('tp1', 2), leg('stop', -1.3)], [], -1.2)).toBe('TP1 + Stop (gapped)');
    expect(exitReasonLabel([leg('stop', -1.3), leg('scratch', 0)], [], -1.2)).toBe('Stop + Scratch');
  });

  it('marks a history-derived stop too', () => {
    expect(exitReasonLabel([], [event('CLOSED', 'stop')], -1.5)).toBe('Stop (gapped)');
  });
});
```

- [ ] **Step 4: Run it to verify it fails**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/exit-reasons.spec.ts
```

Expected: FAIL — the build reports it cannot resolve `./exit-reasons`.

- [ ] **Step 5: Write `exit-reasons.ts`**

Create `frontend/src/app/workspaces/trades/exit-reasons.ts`:

```ts
import type { Leg, StatusEvent } from '../../stores/trade-detail.store';
import { ABSENT } from '../../ui/format';

/**
 * v166 — the words the trade page uses for why a position closed.
 *
 * The KEYS are the backend's reason texts (`metrics.EXIT_REASONS` minus the
 * `other` bucket, every `_EXIT_REASON_ALIASES` key, and `stall_exit`, which
 * plan_manager writes but metrics lists nowhere). The frontend owns only the
 * wording. `tests/admin/test_exit_reason_labels.py` reads this object
 * literal and fails when a backend reason has no entry, so keep exactly one
 * `'key': 'Label',` entry per line, keys single-quoted and lower-case, and
 * close the literal with `};`.
 */
export const EXIT_REASON_LABELS: Readonly<Record<string, string>> = {
  'tp1': 'TP1',
  'tp1_runner_be': 'Runner at breakeven',
  'runner_be': 'Runner at breakeven',
  'tp1_runner_tp2': 'Runner at T2',
  'runner_tp2': 'Runner at T2',
  'runner_trail': 'Runner trailed',
  'stop': 'Stop',
  'loss': 'Stop',
  'scratch': 'Scratch',
  'timeout': 'Time exit',
  'time_exit': 'Time exit',
  'auto (near-tp stall)': 'Stall exit',
  'stall_exit': 'Stall exit',
  'reversed': 'Reversed',
};

/** A stop exit worse than this R went through the stop on a gap: the label
 *  says so, because "Stop" alone reads as "filled at the stop". */
export const GAPPED_R = -1.05;

const STOP_LABEL = 'Stop';
const GAPPED_SUFFIX = ' (gapped)';

/** The label for one reason text. Unknown text is shown as written, so a
 *  new backend reason degrades to its raw name rather than to nothing. */
export function reasonLabel(reason: string | null | undefined): string | null {
  const raw = (reason ?? '').trim();
  if (raw === '') return null;
  const key = raw.toLowerCase();
  return Object.hasOwn(EXIT_REASON_LABELS, key) ? EXIT_REASON_LABELS[key] : raw;
}

function legLabels(legs: readonly Leg[]): string[] {
  return legs.flatMap((leg) => {
    const label = reasonLabel(leg.reason);
    return label === null ? [] : [label];
  });
}

function lastHistoryLabel(history: readonly StatusEvent[]): string | null {
  for (let i = history.length - 1; i >= 0; i--) {
    const label = reasonLabel(history[i].reason);
    if (label !== null) return label;
  }
  return null;
}

/**
 * Why a closed position closed, in one line: "TP1 + Runner at breakeven".
 *
 * The legs' own reasons first (in leg order); with none, the last
 * status_history reason; with neither, "—". `r` is the trade's blended R as
 * the API sent it — only used to mark a final stop that gapped.
 */
export function exitReasonLabel(
  legs: readonly Leg[],
  history: readonly StatusEvent[],
  r: number | null,
): string {
  const labels = legLabels(legs);
  if (labels.length === 0) {
    const fallback = lastHistoryLabel(history);
    if (fallback === null) return ABSENT;
    labels.push(fallback);
  }
  const last = labels.length - 1;
  if (labels[last] === STOP_LABEL && r !== null && r < GAPPED_R) labels[last] += GAPPED_SUFFIX;
  return labels.join(' + ');
}
```

- [ ] **Step 6: Run both tests and the UI gates to verify they pass**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation/scripts/dev/testrun.py file tests/admin/test_exit_reason_labels.py
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/exit-reasons.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/async-coverage.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/contrast.spec.ts
```

Expected: pytest `0 failed`, `0 xfailed` (5 passed); vitest all green. A 60 s `Timeout waiting for worker ... no tests` is machine load: re-run once.

Prove the drift test bites: temporarily delete the `'reversed': 'Reversed',` line, re-run the pytest file, and confirm `test_every_exit_reason_has_a_label` fails naming `['reversed']`; restore the line and re-run until green.

- [ ] **Step 7: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation add frontend/src/app/workspaces/trades/exit-reasons.ts frontend/src/app/workspaces/trades/exit-reasons.spec.ts tests/admin/test_exit_reason_labels.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation commit -m "feat(ui): exit-reason labels for the trade page, with a backend drift check"
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation status --short
```

Expected: the status command lists no file this task touched.

### Task TD3: Pure trade figures: average exit, status group, order wording, side, % from, leg Rs, neutral tint

**Model:** sonnet — pure helpers with a spec, rules fixed by the spec

**Files:**
- Create: `frontend/src/app/workspaces/trades/trade-figures.ts`
- Create: `frontend/src/app/workspaces/trades/trade-figures.spec.ts`

**Interfaces:**
- Consumes: from `main`, the types `Leg` and `StatusEvent` (`frontend/src/app/stores/trade-detail.store.ts:44-57`, type-only import); `ABSENT`, `num(value, decimals = 2)` and `rMultiple(value)` from `frontend/src/app/ui/format.ts` (`num(142.2)` -> `'142.20'`, `rMultiple(2.23)` -> `'+2.23R'`, `rMultiple(-0.4)` -> `'-0.40R'`).
- Produces (consumed by TD5, TD6, TD7):
  - `NEUTRAL_R_BAND = 0.1`
  - `type Tone = 'pos' | 'neg' | null`
  - `outcomeTone(r: number | null): Tone` — `null` when `r` is null or `|r| < NEUTRAL_R_BAND`; else `'pos'` for `r > 0`, `'neg'` for `r < 0`.
  - `averageExit(legs: readonly Leg[], exitPrice: number | null): number | null` — `sum(fraction x exitPrice) / sum(fraction)` over legs with a non-null `exitPrice` and a positive non-null `fraction`; no usable leg -> `exitPrice`.
  - `type StatusGroup = 'closed' | 'open' | 'pending' | 'unfilled'`
  - `statusGroup(status: string, exitPrice: number | null): StatusGroup` — status decides first (trimmed, upper-cased): `CLOSED` -> closed, `ACTIVE`/`PARTIAL` -> open, `PENDING` -> pending; any other status -> `closed` when `exitPrice !== null`, else `unfilled`.
  - `sideLabel(direction: string | null): 'Long' | 'Short' | null` — `bullish`/`long` -> Long, `bearish`/`short` -> Short (trimmed, lower-cased), else null.
  - `orderWording(entryType: string | null, direction: string | null, price: number | null): string` — null `entryType` -> `'—'`; `market` -> `'Market (long)'` / `'Market (short)'` (`'Market'` with no known side); `stop_entry` -> `'Buy stop <num>'` / `'Sell stop <num>'` (`'Stop entry <num>'` with no known side); `limit` -> `'Buy limit <num>'` / `'Sell limit <num>'` (`'Limit entry <num>'`); any other value -> `'<raw> <num>'`. `<num>` is `num(price)` (`'—'` when null). The no-side fallbacks mirror `entryTypeWord` in `why/levels-block.ts`.
  - `pctFrom(from: number | null, to: number | null): number | null` — `(to - from) / from * 100`; null when either is null or `from === 0`.
  - `legRsLine(legs: readonly Leg[]): string | null` — with two or more legs carrying a non-null `r`, their `rMultiple` values joined `' / '`; else null.
  - `lastHistoryReason(history: readonly StatusEvent[]): string | null` — the trimmed reason of the last event whose reason is non-empty; else null.
  - `daysUntil(iso: string | null, now: Date): number | null` — whole days from `now` to `iso`, rounded up, never negative; null for a null or unparseable `iso`.

**Rules from the spec.** § 1 Average exit (SPCX: 0.5 x 147.54 + 0.5 x 145.56 = 146.55; a null-exit leg is skipped and the rest renormalised; no usable leg -> `exit_price`); § 1 Tint (neutral band `|R| < 0.1`); § 1 status table ("status decides the group first"; `exit_price` only for a terminal status that is not `CLOSED`); § 3 Order wording ("Buy stop 142.20", "Sell limit …", "Market (long)"); § 1 Result subline leg Rs ("+2.23R / +1.43R", only with two or more legs); § 1 pending/unfilled sublines (last `status_history` reason, "time exit in Nd").

- [ ] **Step 1: Write the failing spec**

Create `frontend/src/app/workspaces/trades/trade-figures.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import type { Leg, StatusEvent } from '../../stores/trade-detail.store';
import {
  NEUTRAL_R_BAND,
  averageExit,
  daysUntil,
  lastHistoryReason,
  legRsLine,
  orderWording,
  outcomeTone,
  pctFrom,
  sideLabel,
  statusGroup,
} from './trade-figures';

/* v166 — the figures the trade page's strip and cards print, as pure
 * functions. SPCX (production trade f48c80e2) is the worked example: two
 * legs of 0.5 at 147.54 (+2.23R) and 145.56 (+1.43R), blended +1.83R. */

const leg = (fraction: number | null, exitPrice: number | null, r: number | null = null): Leg => ({
  fraction, exitPrice, r, reason: null,
});
const event = (reason: string | null): StatusEvent => ({ status: 'CLOSED', reason, at: null });

describe('outcomeTone', () => {
  it('tints outside the neutral band', () => {
    expect(NEUTRAL_R_BAND).toBe(0.1);
    expect(outcomeTone(1.83)).toBe('pos');
    expect(outcomeTone(-0.4)).toBe('neg');
    expect(outcomeTone(0.1)).toBe('pos');
    expect(outcomeTone(-0.1)).toBe('neg');
  });

  it('leaves near-zero and unknown results untinted', () => {
    expect(outcomeTone(0.09)).toBeNull();
    expect(outcomeTone(-0.05)).toBeNull();
    expect(outcomeTone(0)).toBeNull();
    expect(outcomeTone(null)).toBeNull();
  });
});

describe('averageExit', () => {
  it('weights each leg by its fraction (SPCX: 146.55)', () => {
    expect(averageExit([leg(0.5, 147.54), leg(0.5, 145.56)], 145.56)).toBeCloseTo(146.55, 10);
  });

  it('skips a leg with no exit price and renormalises the rest', () => {
    expect(averageExit([leg(0.5, 147.54), leg(0.5, null)], null)).toBeCloseTo(147.54, 10);
    expect(averageExit([leg(0.25, 110), leg(0.25, 120), leg(0.5, null)], null)).toBeCloseTo(115, 10);
  });

  it('skips a leg with no fraction', () => {
    expect(averageExit([leg(null, 200), leg(1, 100)], 999)).toBe(100);
  });

  it('falls back to exit_price with no usable leg', () => {
    expect(averageExit([], 108)).toBe(108);
    expect(averageExit([leg(0.5, null)], 108)).toBe(108);
    expect(averageExit([], null)).toBeNull();
  });
});

describe('statusGroup', () => {
  it('lets the status decide before exit_price', () => {
    expect(statusGroup('CLOSED', null)).toBe('closed');
    expect(statusGroup('CLOSED', 108)).toBe('closed');
    expect(statusGroup('ACTIVE', 108)).toBe('open');
    expect(statusGroup('PARTIAL', null)).toBe('open');
    expect(statusGroup('PENDING', 108)).toBe('pending');
  });

  it('consults exit_price only for another terminal status', () => {
    expect(statusGroup('CANCELLED', 108)).toBe('closed');
    expect(statusGroup('EXPIRED', 108)).toBe('closed');
    expect(statusGroup('CANCELLED', null)).toBe('unfilled');
    expect(statusGroup('EXPIRED', null)).toBe('unfilled');
  });

  it('reads the status case-insensitively', () => {
    expect(statusGroup(' partial ', null)).toBe('open');
  });
});

describe('sideLabel', () => {
  it('names the side in words', () => {
    expect(sideLabel('bullish')).toBe('Long');
    expect(sideLabel('LONG')).toBe('Long');
    expect(sideLabel('bearish')).toBe('Short');
    expect(sideLabel('short')).toBe('Short');
  });

  it('has no side for anything else', () => {
    expect(sideLabel(null)).toBeNull();
    expect(sideLabel('neutral')).toBeNull();
  });
});

describe('orderWording', () => {
  it('names side, type and price so the order can be entered as written', () => {
    expect(orderWording('stop_entry', 'bullish', 142.2)).toBe('Buy stop 142.20');
    expect(orderWording('stop_entry', 'bearish', 98.5)).toBe('Sell stop 98.50');
    expect(orderWording('limit', 'bullish', 100)).toBe('Buy limit 100.00');
    expect(orderWording('limit', 'bearish', 1234.5)).toBe('Sell limit 1,234.50');
  });

  it('names a market order by side, with no price', () => {
    expect(orderWording('market', 'bullish', 142.2)).toBe('Market (long)');
    expect(orderWording('market', 'bearish', null)).toBe('Market (short)');
    expect(orderWording('market', null, null)).toBe('Market');
  });

  it('falls back like entryTypeWord when the side is unknown', () => {
    expect(orderWording('stop_entry', null, 50)).toBe('Stop entry 50.00');
    expect(orderWording('limit', 'sideways', 50)).toBe('Limit entry 50.00');
  });

  it('shows an unknown entry type as written, and "—" for none', () => {
    expect(orderWording('stop', 'bullish', 101.5)).toBe('stop 101.50');
    expect(orderWording(null, 'bullish', 101.5)).toBe('—');
    expect(orderWording('stop_entry', 'bullish', null)).toBe('Buy stop —');
  });
});

describe('pctFrom', () => {
  it('is the signed move from one price to another', () => {
    expect(pctFrom(100, 110)).toBeCloseTo(10, 10);
    expect(pctFrom(100, 95)).toBeCloseTo(-5, 10);
  });

  it('is null when either price is missing or the base is zero', () => {
    expect(pctFrom(null, 110)).toBeNull();
    expect(pctFrom(100, null)).toBeNull();
    expect(pctFrom(0, 110)).toBeNull();
  });
});

describe('legRsLine', () => {
  it('lists each leg R with two or more closed legs (SPCX)', () => {
    expect(legRsLine([leg(0.5, 147.54, 2.23), leg(0.5, 145.56, 1.43)])).toBe('+2.23R / +1.43R');
    expect(legRsLine([leg(0.5, 110, 1.2), leg(0.5, 90, -0.4)])).toBe('+1.20R / -0.40R');
  });

  it('is null for a single leg or legs without R', () => {
    expect(legRsLine([leg(1, 110, 1.2)])).toBeNull();
    expect(legRsLine([leg(0.5, 110, 1.2), leg(0.5, null, null)])).toBeNull();
    expect(legRsLine([])).toBeNull();
  });
});

describe('lastHistoryReason', () => {
  it('is the last non-empty reason, trimmed', () => {
    const history = [event('trigger filled'), event(' invalidated before trigger '), event(null), event('  ')];
    expect(lastHistoryReason(history)).toBe('invalidated before trigger');
  });

  it('is null with no reason anywhere', () => {
    expect(lastHistoryReason([])).toBeNull();
    expect(lastHistoryReason([event(null)])).toBeNull();
  });
});

describe('daysUntil', () => {
  const now = new Date('2026-10-16T00:00:00Z');

  it('counts whole days ahead, rounding up', () => {
    expect(daysUntil('2026-10-20', now)).toBe(4);
    expect(daysUntil('2026-10-20T06:00:00Z', now)).toBe(5);
    expect(daysUntil('2026-10-16', now)).toBe(0);
  });

  it('never goes negative', () => {
    expect(daysUntil('2026-10-01', now)).toBe(0);
  });

  it('is null for no date or an unreadable one', () => {
    expect(daysUntil(null, now)).toBeNull();
    expect(daysUntil('not a date', now)).toBeNull();
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/trade-figures.spec.ts
```

Expected: FAIL — the build reports it cannot resolve `./trade-figures`.

- [ ] **Step 3: Write `trade-figures.ts`**

Create `frontend/src/app/workspaces/trades/trade-figures.ts`:

```ts
import type { Leg, StatusEvent } from '../../stores/trade-detail.store';
import { ABSENT, num, rMultiple } from '../../ui/format';

/* v166 — the figures the trade page's outcome strip and cards print.
 *
 * Pure and separately tested so the components stay presentational: every
 * rule the spec fixes (status precedence, the average-exit weighting, the
 * neutral tint band, the order wording) lives here once. */

/** A result inside ±0.1R is not tinted: colour would overstate a scratch.
 *  The sign and the text still carry the meaning. */
export const NEUTRAL_R_BAND = 0.1;

export type Tone = 'pos' | 'neg' | null;

export function outcomeTone(r: number | null): Tone {
  if (r === null || Math.abs(r) < NEUTRAL_R_BAND) return null;
  return r > 0 ? 'pos' : 'neg';
}

/**
 * The fraction-weighted exit price over the legs that have one.
 *
 * A leg with no exit price (the runner still open, or a record that never
 * stored it) is skipped and the remaining fractions renormalised. With no
 * usable leg the trade's own `exit_price` stands.
 */
export function averageExit(legs: readonly Leg[], exitPrice: number | null): number | null {
  let weight = 0;
  let total = 0;
  for (const leg of legs) {
    if (leg.exitPrice === null || leg.fraction === null || leg.fraction <= 0) continue;
    weight += leg.fraction;
    total += leg.fraction * leg.exitPrice;
  }
  return weight > 0 ? total / weight : exitPrice;
}

export type StatusGroup = 'closed' | 'open' | 'pending' | 'unfilled';

const GROUP_BY_STATUS: Readonly<Record<string, StatusGroup>> = {
  CLOSED: 'closed',
  ACTIVE: 'open',
  PARTIAL: 'open',
  PENDING: 'pending',
};

/** Which outcome strip a trade gets. The status decides first; `exitPrice`
 *  is consulted only for a terminal status that is not CLOSED (a cancelled
 *  or expired row that still carries a fill is shown as closed). Never
 *  decided by `closed_at`. */
export function statusGroup(status: string, exitPrice: number | null): StatusGroup {
  const key = status.trim().toUpperCase();
  if (Object.hasOwn(GROUP_BY_STATUS, key)) return GROUP_BY_STATUS[key];
  return exitPrice !== null ? 'closed' : 'unfilled';
}

type Side = 'Long' | 'Short';

const SIDE_BY_DIRECTION: Readonly<Record<string, Side>> = {
  bullish: 'Long',
  long: 'Long',
  bearish: 'Short',
  short: 'Short',
};

export function sideLabel(direction: string | null): Side | null {
  if (direction === null) return null;
  const key = direction.trim().toLowerCase();
  return Object.hasOwn(SIDE_BY_DIRECTION, key) ? SIDE_BY_DIRECTION[key] : null;
}

const ORDER_WORDS: Readonly<Record<string, Readonly<Record<Side | 'none', string>>>> = {
  stop_entry: { Long: 'Buy stop', Short: 'Sell stop', none: 'Stop entry' },
  limit: { Long: 'Buy limit', Short: 'Sell limit', none: 'Limit entry' },
};

/** The order as it would be entered: "Buy stop 142.20", "Market (long)".
 *  `entryTypeWord` (why/levels-block.ts) says "At market" and carries no
 *  price, which is why the trade page has its own wording. */
export function orderWording(
  entryType: string | null,
  direction: string | null,
  price: number | null,
): string {
  if (entryType === null) return ABSENT;
  const side = sideLabel(direction);
  if (entryType === 'market') return side === null ? 'Market' : `Market (${side.toLowerCase()})`;
  const words = Object.hasOwn(ORDER_WORDS, entryType)
    ? ORDER_WORDS[entryType][side ?? 'none']
    : entryType;
  return `${words} ${num(price)}`;
}

/** The signed percentage move from `from` to `to`. */
export function pctFrom(from: number | null, to: number | null): number | null {
  if (from === null || to === null || from === 0) return null;
  return ((to - from) / from) * 100;
}

/** "+2.23R / +1.43R" — each closed leg's R, so a blended R cannot hide a
 *  losing leg. Null with fewer than two legs that carry an R. */
export function legRsLine(legs: readonly Leg[]): string | null {
  const rs = legs.flatMap((leg) => (leg.r === null ? [] : [leg.r]));
  return rs.length >= 2 ? rs.map((r) => rMultiple(r)).join(' / ') : null;
}

/** The most recent reason the status history recorded, e.g. why a plan
 *  was cancelled before it ever filled. */
export function lastHistoryReason(history: readonly StatusEvent[]): string | null {
  for (let i = history.length - 1; i >= 0; i--) {
    const reason = (history[i].reason ?? '').trim();
    if (reason !== '') return reason;
  }
  return null;
}

const DAY_MS = 86_400_000;

/** Whole days from `now` until `iso`, rounded up; 0 once it has passed. */
export function daysUntil(iso: string | null, now: Date): number | null {
  if (iso === null) return null;
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return null;
  return Math.max(0, Math.ceil((at - now.getTime()) / DAY_MS));
}
```

- [ ] **Step 4: Run the spec and the UI gates to verify they pass**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation/frontend exec -- ng test --watch=false --include src/app/workspaces/trades/trade-figures.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/async-coverage.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/contrast.spec.ts
```

Expected: all green. A 60 s `Timeout waiting for worker ... no tests` is machine load: re-run once. If `daysUntil('2026-10-16', now)` is not 0 on this machine, the date-only string was parsed as local time: Angular's test runner uses the host timezone, and ECMAScript parses a date-only ISO string as UTC — re-check that `now` in the spec is the UTC literal `'2026-10-16T00:00:00Z'` before changing the function.

- [ ] **Step 5: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation add frontend/src/app/workspaces/trades/trade-figures.ts frontend/src/app/workspaces/trades/trade-figures.spec.ts
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation commit -m "feat(ui): pure trade figures -- average exit, status group, order wording, neutral tint"
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation status --short
```

Expected: the status command lists no file this task touched.

### Task TD4: Store: `riskStop`, risk per share from `risk_stop`, `$ at risk`, working stop, trail, sizing, entry type, earnings days

**Model:** sonnet — a few computeds in one store, rules fixed by amendment 2

**Files:**
- Modify: `frontend/src/app/stores/trade-detail.store.ts` (three module helpers inserted directly above `interface TradeDetailSlice` at :225; `riskPerShare` replaced at :325-331; seven computeds added directly after `rewardPerShare` at :332-336)
- Modify: `frontend/src/app/stores/trade-detail.store.spec.ts` (one new `describe` appended at the end of the file)

**Interfaces:**
- Consumes: `TradeRow.risk_stop?: number | null` (TD1). From `main`: the store's private helpers `asNumber(value: unknown): number | null`, `asText(value: unknown): string | null` (blank string -> null), `toGates(raw: unknown): GateRow[]` (all in `trade-detail.store.ts`), the types `TradeDetail` and `GateRow` (already imported from `../api/models`), and `TradeDetailFields.working_stop`, `trail_atr_mult`, `sizing_mode`, `entry_type`, `gates` (`frontend/src/app/api/models.ts:197-248`).
- Produces (consumed by TD5, TD6, TD7) — new or changed `TradeDetailStore` computeds:
  - `riskStop: Signal<number | null>` — `trade.risk_stop`, null when absent or not a finite number.
  - `riskPerShare: Signal<number | null>` — CHANGED: `|entry - (risk_stop ?? stop_loss)|`; null when `entry` is null or both stops are null.
  - `dollarAtRisk: Signal<number | null>` — `shares x riskPerShare`; null when either is null. On PARTIAL `shares` is the open (remaining) count, so this is "open shares, at original stop".
  - `workingStop: Signal<number | null>` — `detail.working_stop`.
  - `trailAtrMult: Signal<number | null>` — `detail.trail_atr_mult`.
  - `sizingMode: Signal<string | null>` — `detail.sizing_mode` (blank -> null).
  - `entryType: Signal<string | null>` — `detail.entry_type` (blank -> null).
  - `earningsDays: Signal<number | null>` — the `value` of the `gates()` row whose key is `earnings`, when it is a number; else null (the "not recorded" row carries `value: null`).
  - `rewardPerShare` is unchanged.

**Rules from the spec.** Amendment 2: on PARTIAL, `stop_loss` is the working (trailing) stop and `shares` is the open count, so risk per share everywhere uses `risk_stop` when present, else `stop_loss`; "$ at risk" is `shares x |entry - risk_stop|`. Edge case "`risk_stop` null": only `stop_loss` is available, so it is the fallback. § 1: the earnings chip reads the earnings gate's numeric days-to-earnings and shows nothing when it is "not recorded". The existing Per-share card in `trade-detail.ts` reads `riskPerShare()` until TD10 removes it; its value changes only on a PARTIAL row whose `risk_stop` differs from `stop_loss`, which is the intended correction.

- [ ] **Step 1: Write the failing spec**

Append to the end of `frontend/src/app/stores/trade-detail.store.spec.ts` (after the closing `});` of `describe('TradeDetailStore — notes and strategy', ...)`):

```ts
/* v166 — the figures the reorganised trade page reads from the store.
 *
 * On PARTIAL the row's `stop_loss` is the working (trailing) stop and
 * `shares` is the open count (`_display_shares`, v79). Risk per share must
 * come from `risk_stop`, the stop the position was sized against, or a
 * runner trailed above entry reads as "risk 4.00" on a trade that risked 5. */

function figuresResponse(row: object = {}, detail: object = {}) {
  return {
    id: ID,
    ticker: 'AAPL',
    strategy: 'RSI Divergence',
    status: 'ACTIVE',
    entry: 100,
    stop_loss: 95,
    target: 110,
    shares: 10,
    has_note: false,
    ...row,
    detail: { trade_id: ID, note: null, ...detail },
  };
}

const EARNINGS_GATE = {
  key: 'earnings', label: 'Earnings', value: 19, threshold: null, margin: null,
  applies: true, parts: [], note: null,
};

describe('TradeDetailStore — plan figures (v166)', () => {
  let store: InstanceType<typeof TradeDetailStore>;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: new FakeEventStream() },
        TradeDetailStore,
      ],
    });
    store = TestBed.inject(TradeDetailStore);
    backend = TestBed.inject(HttpTestingController);
  });

  const load = (row: object = {}, detail: object = {}) => {
    store.setId(ID);
    TestBed.inject(ApplicationRef).tick();
    backend.expectOne(`/api/v1/trades/${ID}`).flush(figuresResponse(row, detail));
    backend.expectOne(`/api/v1/trades/${ID}/journal`).flush({ journaled: false, entry: null });
  };

  it('reads the original stop the API publishes', () => {
    load({ risk_stop: 90 });
    expect(store.riskStop()).toBe(90);
  });

  it('has no original stop on a row that predates the field', () => {
    load();
    expect(store.riskStop()).toBeNull();
  });

  it('measures risk per share from the original stop on PARTIAL', () => {
    load({ status: 'PARTIAL', stop_loss: 104, risk_stop: 95, shares: 5 });
    expect(store.riskPerShare()).toBe(5);
  });

  it('falls back to stop_loss when there is no original stop', () => {
    load({ risk_stop: null });
    expect(store.riskPerShare()).toBe(5);
  });

  it('has no risk per share without an entry or any stop', () => {
    load({ entry: null, risk_stop: 95 });
    expect(store.riskPerShare()).toBeNull();
  });

  it('has no risk per share when both stops are missing', () => {
    load({ stop_loss: null, risk_stop: null });
    expect(store.riskPerShare()).toBeNull();
  });

  it('leaves reward per share as it was', () => {
    load({ status: 'PARTIAL', stop_loss: 104, risk_stop: 95 });
    expect(store.rewardPerShare()).toBe(10);
  });

  it('prices the dollars at risk on the shares the row carries', () => {
    load({ risk_stop: 95 });
    expect(store.dollarAtRisk()).toBe(50);
  });

  it('prices a PARTIAL runner on its open shares at the original stop', () => {
    load({ status: 'PARTIAL', stop_loss: 104, risk_stop: 95, shares: 5 });
    expect(store.dollarAtRisk()).toBe(25);
  });

  it('has no dollars at risk without a share count', () => {
    load({ shares: null, risk_stop: 95 });
    expect(store.dollarAtRisk()).toBeNull();
  });

  it('reads the working stop, trail, sizing mode and entry type from the detail', () => {
    load({}, {
      working_stop: 101.33, trail_atr_mult: 1.5, sizing_mode: 'risk_pct', entry_type: 'stop_entry',
    });
    expect(store.workingStop()).toBe(101.33);
    expect(store.trailAtrMult()).toBe(1.5);
    expect(store.sizingMode()).toBe('risk_pct');
    expect(store.entryType()).toBe('stop_entry');
  });

  it('reads them as unknown on a record that lacks them', () => {
    load({}, { sizing_mode: '', entry_type: null });
    expect(store.workingStop()).toBeNull();
    expect(store.trailAtrMult()).toBeNull();
    expect(store.sizingMode()).toBeNull();
    expect(store.entryType()).toBeNull();
  });

  it('reads the days to earnings from the earnings gate', () => {
    load({}, { gates: [EARNINGS_GATE] });
    expect(store.earningsDays()).toBe(19);
  });

  it('has no earnings days when the gate did not record them', () => {
    load({}, {
      gates: [{ ...EARNINGS_GATE, value: null, applies: false, note: 'not recorded' }],
    });
    expect(store.earningsDays()).toBeNull();
  });

  it('has no earnings days without an earnings gate', () => {
    load({}, {
      gates: [{ ...EARNINGS_GATE, key: 'rs', label: 'Relative strength', value: 1.2 }],
    });
    expect(store.earningsDays()).toBeNull();
  });

  it('has no earnings days before any detail arrives', () => {
    expect(store.earningsDays()).toBeNull();
    expect(store.dollarAtRisk()).toBeNull();
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation/frontend exec -- ng test --watch=false --include src/app/stores/trade-detail.store.spec.ts
```

Expected: FAIL — TypeScript errors such as `Property 'riskStop' does not exist` (and likewise `dollarAtRisk`, `workingStop`, `trailAtrMult`, `sizingMode`, `entryType`, `earningsDays`).

- [ ] **Step 3: Add the module helpers**

In `frontend/src/app/stores/trade-detail.store.ts`, directly above `interface TradeDetailSlice {` (line 225), insert:

```ts
/* -- v166: the stop a position was sized against ---------------------------
 *
 * `stop_loss` on the row is the WORKING stop: once a plan is PARTIAL it is
 * the trailing stop, above entry for a long. Risk per share, and the dollars
 * at risk built on it, must use the original stop (`risk_stop`, published by
 * the API since v166); a row from before that field falls back to
 * `stop_loss`, which is all it has. */

function riskPerShareOf(trade: TradeDetail | null): number | null {
  if (!trade || trade.entry === null) return null;
  const stop = asNumber(trade.risk_stop ?? null) ?? trade.stop_loss;
  return stop === null ? null : Math.abs(trade.entry - stop);
}

function dollarAtRiskOf(trade: TradeDetail | null): number | null {
  const risk = riskPerShareOf(trade);
  const shares = trade?.shares ?? null;
  return risk === null || shares === null ? null : shares * risk;
}

/** Days to the next earnings date, as the earnings gate recorded it. The
 *  gate's "not recorded" row carries `value: null`. */
function earningsDaysOf(gates: GateRow[]): number | null {
  const value = gates.find((gate) => gate.key === 'earnings')?.value;
  return typeof value === 'number' ? value : null;
}

```

- [ ] **Step 4: Replace `riskPerShare` and add the new computeds**

Replace the `riskPerShare` computed and its doc comment (lines 325-331):

```ts
    /** Risk and reward per share, from the plan's own levels. Null unless
     *  both sides are known — half an R:R is not an R:R. */
    riskPerShare: computed(() => {
      const trade = data();
      if (!trade || trade.entry === null || trade.stop_loss === null) return null;
      return Math.abs(trade.entry - trade.stop_loss);
    }),
```

with:

```ts
    /** Risk and reward per share, from the plan's own levels. Null unless
     *  both sides are known — half an R:R is not an R:R. Risk is measured
     *  to the ORIGINAL stop (`risk_stop`), not the working one (v166). */
    riskPerShare: computed(() => riskPerShareOf(data())),
```

Then, directly after the closing `}),` of `rewardPerShare` (which stays as it is), insert:

```ts

    /* -- v166: the reorganised page's plan and position figures ----------- */

    /** The plan's original stop; null on a row from before v166. */
    riskStop: computed(() => asNumber(data()?.risk_stop ?? null)),
    /** Shares x risk per share. On PARTIAL `shares` is the open count, so
     *  this is the runner's risk at the original stop. */
    dollarAtRisk: computed(() => dollarAtRiskOf(data())),
    workingStop: computed(() => asNumber(data()?.detail?.working_stop ?? null)),
    trailAtrMult: computed(() => asNumber(data()?.detail?.trail_atr_mult ?? null)),
    sizingMode: computed(() => asText(data()?.detail?.sizing_mode ?? null)),
    entryType: computed(() => asText(data()?.detail?.entry_type ?? null)),
    earningsDays: computed(() => earningsDaysOf(toGates(data()?.detail?.gates))),
```

- [ ] **Step 5: Run the store spec, the page spec that reads `riskPerShare`, and the UI gates**

```bash
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation/frontend exec -- ng test --watch=false --include src/app/stores/trade-detail.store.spec.ts --include src/app/workspaces/trades/trade-detail.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/async-coverage.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/contrast.spec.ts
```

Expected: all green — the 16 new store cases pass, and `trade-detail.spec.ts` is unchanged and still passes (its fixture has no `risk_stop`, so `riskPerShare` falls back to `stop_loss` exactly as before). A 60 s `Timeout waiting for worker ... no tests` is machine load: re-run once.

- [ ] **Step 6: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation add frontend/src/app/stores/trade-detail.store.ts frontend/src/app/stores/trade-detail.store.spec.ts
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation commit -m "feat(ui): trade store measures risk from the original stop; adds plan and position figures"
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v166-trade-detail-reorganisation status --short
```

Expected: the status command lists no file this task touched.


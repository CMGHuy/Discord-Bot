# v165 P&L calendar day page. Part 1: rows, context, breakdown, day route (CD1..CD5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task CD3:" -A 300 docs/superpowers/plans/2026-10-15-v165-calendar-day-page_1-rows-context-route.md`.

**Spec:** [`docs/superpowers/specs/2026-10-15-v165-calendar-day-page-design.md`](../specs/2026-10-15-v165-calendar-day-page-design.md) (this part: Facts, D1, D2, D3, the day-route half of D4, Testing)
**Index:** [`2026-10-15-v165-calendar-day-page_0-index.md`](2026-10-15-v165-calendar-day-page_0-index.md) carries the header, `## Global Constraints`, `## Review Focus`, `## Parallelisation` and the task ledger. Every task below implicitly includes the Global Constraints.

**Paths.** `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree), `$WT` = `$R/.claude/worktrees/2026-10-15-v165-calendar-day-page` (created in CD1 Step 2). Never `cd`; use `git -C $WT`, and `python $WT/scripts/dev/testrun.py file <test>` (test paths resolve against `$WT`). All file paths below are relative to `$WT` unless they say `$R`.

**Chain.** CD1 → CD2 → CD3 → CD4 → CD5, strictly sequential (shared files `pnl_calendar.py`, `tests/analytics/test_pnl_calendar.py`, `tests/admin/test_api_v1_calendar.py`).

**One deviation from the ledger's file column, no contract change:** CD2 also modifies `tests/admin/test_api_v1_calendar.py` (adds the nine new keys to the existing trade-row `assert_shape`, which rejects undeclared keys — without it the admin suite goes red the moment `ROW_KEYS` grows). The Python chain is sequential, so this collides with nothing.

---

# Phase 1 — Backend: rows, context, breakdown, day route

### Task CD1: Prerequisite gate, worktree, `exit_reason_bucket` rename and text split

**Model:** sonnet — a gate check plus a rename and split inside one module

**Files:**
- Modify: `swingbot/core/analytics/metrics.py` (`_exit_reason_bucket` at ~:819 and its two callers at ~:865, ~:887)
- Modify: `tests/analytics/test_metrics_exit_reasons.py` (references at :103, :107 comment, :111, :130; new tests appended)

**Interfaces:**
- Consumes: nothing from this plan. From `main`: the prerequisite `performance.expand_realized_legs(trade: dict) -> list[dict]` and `pnl_calendar._row_for(part: dict, entry: dict) -> dict | None` (gate only, not edited here).
- Produces:
  - `metrics.exit_reason_bucket(trade: dict) -> str` — the renamed `_exit_reason_bucket`, output byte-identical for every input.
  - `metrics.exit_reason_bucket_text(text: str | None) -> str | None` — `(text or "").strip().lower()`; the exact `EXIT_REASONS` name if it is one, else the `_EXIT_REASON_ALIASES` value, else `None`. No `resolve_outcome` fallback (a leg has no status of its own to fall back on). CD2 calls it.
  - No alias: after this task `hasattr(metrics, "_exit_reason_bucket")` is `False`.

**Why the private `_bucket_for_text`.** `exit_reason_bucket_text` strips whitespace; the trade-level path never did (`close_reason_text` only lowercases). Routing the trade path through the stripping function would move a padded text like `" loss "` from `other` to `stop` — a behaviour change the spec forbids ("its trade-level output is unchanged"). So both public functions share one un-normalising lookup, and only the text half normalises.

- [ ] **Step 1: Prerequisite gate (on `$R`, before anything else)**

The per-leg split is another session's work. It must be committed on `main` in the shape the spec's Facts describe. Run each command on the main tree:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot grep -n -F "def expand_realized_legs(trade: dict) -> list[dict]:" main -- swingbot/core/tracking/performance.py
git -C E:/Documents/Private/Projects/Discord-Bot grep -n -F "def _row_for(part: dict, entry: dict) -> dict | None:" main -- swingbot/core/analytics/pnl_calendar.py
git -C E:/Documents/Private/Projects/Discord-Bot grep -n -F "for part in expand_realized_legs(t):" main -- swingbot/core/analytics/pnl_calendar.py
git -C E:/Documents/Private/Projects/Discord-Bot grep -n -F '"exit_efficiency", "tags", "auto_lesson", "leg_index", "leg_total",' main -- swingbot/core/analytics/pnl_calendar.py
git -C E:/Documents/Private/Projects/Discord-Bot grep -n -F "leg_total: number;" main -- frontend/src/app/api/models.ts
git -C E:/Documents/Private/Projects/Discord-Bot status --short -- swingbot/core/tracking/performance.py swingbot/core/analytics/pnl_calendar.py swingbot/core/analytics/metrics.py swingbot/admin/api_v1/calendar.py frontend/src/app/api/models.ts frontend/src/app/workspaces/calendar/
python E:/Documents/Private/Projects/Discord-Bot/scripts/dev/testrun.py file tests/analytics/test_pnl_calendar.py
```

Expected: each of the five `git grep` commands prints a hit (as of 2026-10-16: `performance.py:484`, `pnl_calendar.py:70`, `pnl_calendar.py:~139`, `pnl_calendar.py:37`, `models.ts:1718` — `models.ts:165` may also hit, that is the Trades row type); `git status --short` prints **nothing** (no uncommitted edits by another session in this plan's files); the test run ends `0 failed`.

Also confirm the part shape by eye: `git -C E:/Documents/Private/Projects/Discord-Bot show main:swingbot/core/tracking/performance.py | sed -n 408,520p` — `expand_trade_legs` builds each leg row as `{**trade, "legs": None, "shares": ..., "exit_price": leg exit, "closed_at": ..., "status": ..., "entry", "direction", "stop_loss"}` (so `take_profit`, `target2`, `opened_at` ride through from the trade), and `expand_realized_legs` adds `leg_index`/`leg_total` and keeps only `win`/`loss`/`closed` rows, in `legs` order.

**On any mismatch — a grep with no hit, a non-empty status, a red test, or a different part shape — STOP and ask the partner (`AskUserQuestion`).** Do not start Step 2; do not edit, stage or commit the other session's files.

- [ ] **Step 2: Create the worktree**

Invoke the `worktree-lifecycle` skill, then (reuse the worktree instead if `git -C E:/Documents/Private/Projects/Discord-Bot worktree list` already shows `2026-10-15-v165-calendar-day-page`):

```bash
git -C E:/Documents/Private/Projects/Discord-Bot worktree add .claude/worktrees/2026-10-15-v165-calendar-day-page -b 2026-10-15-v165-calendar-day-page main
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page log --oneline -1
```

Expected: the log line is the current `main` HEAD (the commit that carries this plan). Every later step runs in `$WT`.

- [ ] **Step 3: Rename the test references and write the failing tests**

In `tests/analytics/test_metrics_exit_reasons.py`, replace every `metrics._exit_reason_bucket(` with `metrics.exit_reason_bucket(` (lines 103, 111, 130) and the comment at line 107 with:

```python
    # Exact match only (metrics.exit_reason_bucket docstring): a substring
```

Then append at the end of the file:

```python
# --- v165: public name, and the text-only half for scale-out legs ----------
#
# The P&L calendar's day page buckets each realized LEG by the leg's own
# reason (`trade["legs"][i]["reason"]`), while a whole trade keeps the
# trade-level bucket. The text half is split out so the leg path and the
# trade path cannot drift apart on what an exact name or an alias means.


def test_the_private_name_is_gone_with_no_alias():
    assert not hasattr(metrics, "_exit_reason_bucket")


@pytest.mark.parametrize("name", list(metrics.EXIT_REASONS))
def test_every_exit_reason_name_buckets_to_itself_from_text(name):
    assert metrics.exit_reason_bucket_text(name) == name


@pytest.mark.parametrize(("text", "bucket"), [
    pytest.param("loss", "stop", id="alias-loss"),
    pytest.param("tp1_runner_be", "runner_be", id="alias-runner-be"),
    pytest.param("tp1_runner_tp2", "runner_tp2", id="alias-runner-tp2"),
    pytest.param("auto (near-tp stall)", "timeout", id="alias-near-tp-stall"),
    pytest.param("time_exit", "timeout", id="alias-time-exit"),
])
def test_text_aliases_resolve_like_the_trade_level_bucket(text, bucket):
    assert metrics.exit_reason_bucket_text(text) == bucket


def test_text_is_stripped_and_lowercased_before_the_lookup():
    assert metrics.exit_reason_bucket_text("  TP1 ") == "tp1"
    assert metrics.exit_reason_bucket_text("Runner_Trail") == "runner_trail"


@pytest.mark.parametrize("text", [
    pytest.param(None, id="none"),
    pytest.param("", id="empty"),
    pytest.param("   ", id="blank"),
    pytest.param("not a stop at all", id="substring-only"),
    pytest.param("auto (price monitor)", id="ambiguous-text"),
    pytest.param("scratch exit", id="prose-needs-status"),
])
def test_text_with_no_exact_name_or_alias_is_none_not_a_guess(text):
    # None, not "other": the caller decides what an unmatched leg means.
    # "scratch exit" is resolve_outcome's job on a whole trade, and a leg
    # has no status of its own to resolve against.
    assert metrics.exit_reason_bucket_text(text) is None


def test_the_trade_level_bucket_does_not_gain_the_texts_stripping():
    # Pins "output unchanged": close_reason_text only lowercases, so a
    # padded reason on a whole trade stayed "other" before v165 and must
    # stay "other" after it. Only the leg path normalises whitespace.
    trade = {"status": "loss", "close_reason": " loss ", "entry": 100.0,
             "stop_loss": 99.0, "direction": "bullish", "exit_price": 99.0}
    assert metrics.exit_reason_bucket(trade) == "other"


def test_the_trade_level_bucket_still_falls_back_to_resolve_outcome():
    trade = {"status": "closed", "close_reason": "scratch exit", "entry": 100.0,
             "stop_loss": 99.0, "direction": "bullish", "exit_price": 100.0}
    assert metrics.exit_reason_bucket(trade) == "scratch"
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page/scripts/dev/testrun.py file tests/analytics/test_metrics_exit_reasons.py`
Expected: FAIL — `AttributeError: module 'swingbot.core.analytics.metrics' has no attribute 'exit_reason_bucket'` (and `exit_reason_bucket_text`), and `test_the_private_name_is_gone_with_no_alias` fails.

- [ ] **Step 5: Rename and split in `metrics.py`**

Replace the whole `_exit_reason_bucket` function (~:819-840) with:

```python
def _bucket_for_text(text: str) -> str | None:
    """The EXIT_REASONS bucket an already-normalised reason text names
    exactly -- the name itself, else its `_EXIT_REASON_ALIASES` entry --
    or None. No substring rule, ever (see `exit_reason_bucket`)."""
    if text in _EXIT_REASON_SET:
        return text
    return _EXIT_REASON_ALIASES.get(text)


def exit_reason_bucket_text(text: str | None) -> str | None:
    """Which EXIT_REASONS bucket a bare reason text names, or None.

    The text-only half of `exit_reason_bucket`, for a reason that has no
    trade around it -- one realized leg's `reason` (v165's calendar rows).
    Stripped and lowercased, then exact name or alias. None, never "other",
    when nothing matches: there is no status to fall back on, and the caller
    decides what an unmatched text means.
    """
    return _bucket_for_text((text or "").strip().lower())


def exit_reason_bucket(trade: dict) -> str:
    """Which EXIT_REASONS bucket a closed trade belongs to.

    Exact match on the raw reason text first, so "runner_tp2" cannot be
    swallowed by a looser substring rule that would also match "tp2" inside it;
    then resolve_outcome, which is the one place that knows prose like
    "scratch exit" means scratch; then "other". Never a fuzzy fallback beyond
    those two -- absorbing an unknown string into whichever bucket it happens to
    share letters with is how a table like this starts lying.

    The text is `close_reason_text` as-is (lowercased, NOT stripped): that is
    this function's output since v89, and v165 keeps it byte-identical.
    """
    bucket = _bucket_for_text(close_reason_text(trade))
    if bucket is not None:
        return bucket
    outcome = resolve_outcome(trade)
    if outcome in _EXIT_REASON_SET:
        return outcome
    return "other"
```

Then rename the two callers — in `exit_reason_split` (~:865):

```python
        buckets[exit_reason_bucket(trade)].append(trade)
```

and in `unmapped_exit_reasons` (~:887):

```python
        if exit_reason_bucket(trade) != "other":
```

Confirm nothing else references the old name:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page grep -n "_exit_reason_bucket" -- "*.py"
```

Expected: no output.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page/scripts/dev/testrun.py file tests/analytics/test_metrics_exit_reasons.py`
Expected: `0 failed`.

The exit-quality outputs are the guard for "unchanged": list the other test files that exercise `exit_reason_split` / `unmapped_exit_reasons`

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page grep -l -e exit_reason_split -e unmapped_exit_reasons -- tests
```

and run each listed file with `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page/scripts/dev/testrun.py file <file>`. Expected: `0 failed` each.

- [ ] **Step 7: Complexity**

Run: `python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page/swingbot/core/analytics/metrics.py`
Expected: the same four lines as before this task (`hold_by_outcome C (14)`, `r_multiple C (12)`, `equity_curve C (11)`, `pct_in_market C (11)`) — none of the three functions written here.

- [ ] **Step 8: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page add swingbot/core/analytics/metrics.py tests/analytics/test_metrics_exit_reasons.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page commit -m "refactor(metrics): public exit_reason_bucket plus its text-only half for legs"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the last command lists no file this plan touches (only files another session owns, if any).

### Task CD2: D1 fuller rows: prices, shares, held hours, % return, exit reason per row

**Model:** sonnet — pure fields inside `analytics`, behaviour fixed by D1

**Files:**
- Modify: `swingbot/core/analytics/pnl_calendar.py` (`ROW_KEYS` :34-38, `_row_for` :70-113, `joined_rows` :116-141; new helpers between `_float_or_none` and `_row_for`)
- Modify: `tests/analytics/test_pnl_calendar.py` (append a D1 section at the end)
- Modify: `tests/admin/test_api_v1_calendar.py` (`test_day_trade_shape_carries_the_journal_join`, ~:174-196 — the trade-row `assert_shape` gains the nine keys; see the part header for why this file is here)

**Interfaces:**
- Consumes: `metrics.exit_reason_bucket(trade: dict) -> str` and `metrics.exit_reason_bucket_text(text: str | None) -> str | None` (CD1). From `main`: `performance.expand_realized_legs` (parts carry `entry`, `exit_price`, `stop_loss`, `take_profit`, `target2`, `shares`, `opened_at`, `closed_at`, `direction`, `leg_index`, `leg_total`, `legs: None` on a leg part).
- Produces (consumed by CD4, CD5, CD6 and the frontend `CalendarTrade` in CD7):
  - `ROW_KEYS` gains, appended after `"leg_total"` in exactly this order: `"entry_price", "exit_price", "stop_price", "tp1", "tp2", "shares", "held_hours", "return_pct", "exit_reason"`. Every one is `float | None` except `exit_reason: str` (an `EXIT_REASONS` name, never `None`).
  - `held_hours(opened_at: str | None, closed_at: str | None) -> float | None` — hours, 2 dp; `None` when either stamp is missing or unparseable, or `closed_at < opened_at`; a naive stamp is read as UTC.
  - `return_pct(entry: float | None, exit_price: float | None, direction: str | None) -> float | None` — `(exit − entry) / entry × 100`, sign flipped for `"bearish"`, 2 dp; `None` when `entry` is missing or `0`, `exit_price` is missing, or `direction` is neither `"bullish"` nor `"bearish"` (the same rule `metrics.r_multiple` applies).
  - `row_exit_reason(part: dict, trade: dict) -> str` — `leg_total == 1`: `metrics.exit_reason_bucket(trade)`; otherwise `metrics.exit_reason_bucket_text(trade["legs"][leg_index]["reason"])`, `"other"` when that is `None`, when the trade has no `legs`, or when `leg_index` is not a valid index into them.
  - `_row_for(part: dict, entry: dict, trade: dict) -> dict | None` — `joined_rows` passes the parent trade `t`.

**Why `trade` and not the part.** A leg part has `legs: None` (`expand_trade_legs`), so `exit_reason_bucket(part)` would fall back to the trade's coarse `close_reason` and every TP1 leg would read like its runner. The leg's own reason only lives on the parent trade, at `trade["legs"][leg_index]` — `leg_index` is the leg's position in `legs` because `expand_trade_legs` emits legs in order and puts the open remainder (dropped by `expand_realized_legs`) last. A trade with exactly one leg yields one part with `leg_total == 1`; `exit_reason_bucket(trade)` reads `legs[-1]["reason"]` for it, which is that one leg.

- [ ] **Step 1: Write the failing tests**

Append to `tests/analytics/test_pnl_calendar.py`:

```python
# --- v165 D1: fuller rows -------------------------------------------------
#
# Every figure is read from the part `expand_realized_legs` produced (leg
# prices, leg shares, leg close) -- never re-derived from the plan, never a
# third copy of the leg pricing in `expand_trade_legs` / `_row_from_leg`.

from swingbot.core.analytics.pnl_calendar import (ROW_KEYS, held_hours,
                                                  return_pct, row_exit_reason)

_D1_KEYS = ("entry_price", "exit_price", "stop_price", "tp1", "tp2", "shares",
            "held_hours", "return_pct", "exit_reason")


def test_the_d1_keys_are_appended_after_leg_total_in_order():
    assert ROW_KEYS[-10:] == ("leg_total", *_D1_KEYS)


def test_a_whole_trade_row_carries_every_d1_field():
    trade = _trade("a" * 16)
    trade.update(take_profit=120.0, target2=130.0, close_reason="time_exit")
    row = joined_rows([trade], [])[0]
    assert {k: row[k] for k in _D1_KEYS} == {
        "entry_price": 100.0, "exit_price": 110.0, "stop_price": 95.0,
        "tp1": 120.0, "tp2": 130.0, "shares": 10.0,
        # 2026-08-01T14:00Z -> 2026-08-03T20:00Z = 2 days 6 hours.
        "held_hours": 54.0,
        # (110 - 100) / 100 * 100.
        "return_pct": 10.0,
        # Whole trade: metrics.exit_reason_bucket(trade), alias time_exit.
        "exit_reason": "timeout",
    }


def test_a_short_whole_trade_return_is_sign_flipped():
    trade = _trade("a" * 16, direction="bearish", exit_price=90.0, stop=105.0)
    row = joined_rows([trade], [])[0]
    # (100 - 90) / 100 * 100: a short that fell 10% made +10%.
    assert row["return_pct"] == 10.0


def _reasoned_scaled_trade():
    """TP1 half at 110 on 08-03 15:00Z, runner half at 105 on 08-05 19:00Z,
    each leg carrying the reason the v2 manager writes."""
    trade = _scaled_trade("a" * 16, legs=({**_TP1, "reason": "tp1"},
                                          {**_RUNNER, "reason": "runner_trail"}))
    trade.update(take_profit=110.0, target2=120.0)
    return trade


def test_a_tp1_leg_reads_its_own_prices_shares_hold_and_reason():
    leg = joined_rows([_reasoned_scaled_trade()], [])[0]
    assert {k: leg[k] for k in _D1_KEYS} == {
        "entry_price": 100.0, "exit_price": 110.0, "stop_price": 95.0,
        "tp1": 110.0, "tp2": 120.0,
        # 10 shares x fraction 0.5, already scaled by expand_trade_legs.
        "shares": 5.0,
        # 2026-08-01T14:00Z -> the LEG's close 2026-08-03T15:00Z = 49 h.
        "held_hours": 49.0,
        "return_pct": 10.0,
        "exit_reason": "tp1",
    }


def test_the_closing_leg_of_a_finished_scale_out_reads_its_own_figures():
    closing = joined_rows([_reasoned_scaled_trade()], [])[1]
    assert {k: closing[k] for k in _D1_KEYS} == {
        "entry_price": 100.0, "exit_price": 105.0, "stop_price": 95.0,
        "tp1": 110.0, "tp2": 120.0, "shares": 5.0,
        # 2026-08-01T14:00Z -> 2026-08-05T19:00Z = 4 days 5 hours.
        "held_hours": 101.0,
        "return_pct": 5.0,
        "exit_reason": "runner_trail",
    }


def test_leg_dollars_still_sum_to_the_trades_realized_total():
    # The one leg invariant v165 claims (D1). Leg R is NOT additive and is
    # deliberately not asserted to sum to anything.
    trade = _reasoned_scaled_trade()
    rows = joined_rows([trade], [])
    assert sum(r["pnl_amount"] for r in rows) == pytest.approx(trade["realized_pnl_amount"])


def test_a_single_leg_trade_is_whole_and_uses_the_trade_level_bucket():
    only = {"fraction": 1.0, "exit_price": 105.0, "reason": "tp1_runner_be",
            "closed_at": "2026-08-05T19:00:00+00:00"}
    row = joined_rows([_scaled_trade("a" * 16, legs=(only,), pnl=50.0)], [])[0]
    assert (row["leg_index"], row["leg_total"]) == (0, 1)
    # legs[-1].reason through the alias table.
    assert row["exit_reason"] == "runner_be"


def test_a_banked_leg_of_an_open_runner_buckets_by_the_legs_reason():
    trade = _scaled_trade("a" * 16, status="open", closed_at=None, pnl=None,
                          legs=({**_TP1, "reason": "tp1"},))
    row = joined_rows([trade], [])[0]
    assert (row["leg_total"], row["exit_reason"]) == (2, "tp1")


def test_a_leg_with_no_or_unknown_reason_buckets_other():
    # _TP1/_RUNNER carry no "reason" key at all.
    rows = joined_rows([_scaled_trade("a" * 16)], [])
    assert [r["exit_reason"] for r in rows] == ["other", "other"]
    odd = _scaled_trade("b" * 16, legs=({**_TP1, "reason": "operator felt like it"},
                                        {**_RUNNER, "reason": None}))
    assert [r["exit_reason"] for r in joined_rows([odd], [])] == ["other", "other"]


@pytest.mark.parametrize(("part", "trade"), [
    pytest.param({"leg_index": 3, "leg_total": 4}, {"legs": [{"reason": "tp1"}]},
                 id="index-overruns-legs"),
    pytest.param({"leg_index": 0, "leg_total": 2}, {"legs": None}, id="no-legs"),
    pytest.param({"leg_index": None, "leg_total": 2}, {"legs": [{"reason": "tp1"}]},
                 id="no-index"),
    pytest.param({"leg_index": -1, "leg_total": 2}, {"legs": [{"reason": "tp1"}]},
                 id="negative-index"),
])
def test_row_exit_reason_never_raises_on_a_malformed_leg(part, trade):
    assert row_exit_reason(part, trade) == "other"


def test_missing_prices_and_stamps_are_none_never_zero():
    trade = _trade("a" * 16, exit_price=None)
    trade.update(opened_at=None, shares=None)
    row = joined_rows([trade], [])[0]
    assert row["exit_price"] is None
    assert row["return_pct"] is None
    assert row["held_hours"] is None
    assert row["shares"] is None
    # _trade sets no take_profit / target2 at all.
    assert (row["tp1"], row["tp2"]) == (None, None)


@pytest.mark.parametrize(("opened", "closed", "hours"), [
    pytest.param("2026-08-01T14:00:00+00:00", "2026-08-03T20:00:00+00:00", 54.0, id="offset"),
    pytest.param("2026-08-01T14:00:00Z", "2026-08-01T16:00:00Z", 2.0, id="zulu"),
    pytest.param("2026-08-01T14:00:00", "2026-08-01T15:30:00+00:00", 1.5, id="naive-is-utc"),
    pytest.param("2026-08-01T14:00:00+00:00", "2026-08-01T14:20:00+00:00", 0.33, id="two-dp"),
    pytest.param("2026-08-01T14:00:00+00:00", "2026-08-01T14:00:00+00:00", 0.0, id="same-instant"),
])
def test_held_hours(opened, closed, hours):
    assert held_hours(opened, closed) == hours


@pytest.mark.parametrize(("opened", "closed"), [
    pytest.param(None, "2026-08-03T20:00:00+00:00", id="no-open"),
    pytest.param("2026-08-01T14:00:00+00:00", None, id="no-close"),
    pytest.param("2026-08-01T14:00:00+00:00", "", id="empty-close"),
    pytest.param("yesterday", "2026-08-03T20:00:00+00:00", id="unparseable"),
    pytest.param("2026-08-03T20:00:00+00:00", "2026-08-01T14:00:00+00:00", id="reversed"),
])
def test_held_hours_is_none_when_it_cannot_be_measured(opened, closed):
    assert held_hours(opened, closed) is None


@pytest.mark.parametrize(("entry", "exit_price", "direction", "pct"), [
    pytest.param(100.0, 110.0, "bullish", 10.0, id="long-up"),
    pytest.param(100.0, 90.0, "bullish", -10.0, id="long-down"),
    pytest.param(100.0, 90.0, "bearish", 10.0, id="short-down"),
    pytest.param(100.0, 110.0, "bearish", -10.0, id="short-up"),
    pytest.param(3.0, 3.1, "bullish", 3.33, id="two-dp"),
])
def test_return_pct(entry, exit_price, direction, pct):
    assert return_pct(entry, exit_price, direction) == pct


@pytest.mark.parametrize(("entry", "exit_price", "direction"), [
    pytest.param(None, 110.0, "bullish", id="no-entry"),
    pytest.param(0.0, 110.0, "bullish", id="zero-entry"),
    pytest.param(100.0, None, "bullish", id="no-exit"),
    pytest.param(100.0, 110.0, None, id="no-direction"),
    pytest.param(100.0, 110.0, "sideways", id="unknown-direction"),
])
def test_return_pct_is_none_when_it_cannot_be_signed(entry, exit_price, direction):
    assert return_pct(entry, exit_price, direction) is None
```

In `tests/admin/test_api_v1_calendar.py`, inside `test_day_trade_shape_carries_the_journal_join`, replace the `assert_shape(body["trades"][0], {...}, where="trades[0]")` call with:

```python
    assert_shape(body["trades"][0], {
        "trade_id": str, "ticker": str, "strategy": str,
        "plan_id": NULLABLE_STR, "opened_at": NULLABLE_STR,
        "horizon": NULLABLE_STR, "direction": NULLABLE_STR, "day": str,
        "closed_at": NULLABLE_STR, "outcome": NULLABLE_STR,
        "pnl_amount": NULLABLE_NUMBER, "r_multiple": NULLABLE_NUMBER,
        "mfe_r": NULLABLE_NUMBER, "mae_r": NULLABLE_NUMBER,
        "exit_efficiency": NULLABLE_NUMBER, "tags": list,
        "auto_lesson": NULLABLE_STR, "leg_index": int, "leg_total": int,
        # v165 D1.
        "entry_price": NULLABLE_NUMBER, "exit_price": NULLABLE_NUMBER,
        "stop_price": NULLABLE_NUMBER, "tp1": NULLABLE_NUMBER, "tp2": NULLABLE_NUMBER,
        "shares": NULLABLE_NUMBER, "held_hours": NULLABLE_NUMBER,
        "return_pct": NULLABLE_NUMBER, "exit_reason": str,
    }, where="trades[0]")
```

(Leave the outer body `assert_shape` alone here — CD5 extends it with `context` and `breakdown`.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page/scripts/dev/testrun.py file tests/analytics/test_pnl_calendar.py`
Expected: FAIL at collection — `ImportError: cannot import name 'held_hours' from 'swingbot.core.analytics.pnl_calendar'`.

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page/scripts/dev/testrun.py file tests/admin/test_api_v1_calendar.py`
Expected: `test_day_trade_shape_carries_the_journal_join` FAILS with `trades[0]: missing key(s) ['entry_price', ...]`.

- [ ] **Step 3: Implement**

In `swingbot/core/analytics/pnl_calendar.py`, replace `ROW_KEYS` with:

```python
ROW_KEYS = (
    "trade_id", "plan_id", "ticker", "strategy", "horizon", "direction", "day",
    "opened_at", "closed_at", "outcome", "pnl_amount", "r_multiple", "mfe_r", "mae_r",
    "exit_efficiency", "tags", "auto_lesson", "leg_index", "leg_total",
    # v165 D1 -- read from the part, never re-derived (see `_detail_fields`).
    "entry_price", "exit_price", "stop_price", "tp1", "tp2", "shares",
    "held_hours", "return_pct", "exit_reason",
)
```

Insert these helpers directly after `_float_or_none` (before `_row_for`):

```python
def _utc_stamp(value) -> _dt.datetime | None:
    """An ISO timestamp as an aware datetime, a naive one read as UTC.

    Every close the tracker writes is UTC ISO (`day_of`'s premise), so a
    naive stamp is an older record missing its offset, not local time.
    """
    if not value:
        return None
    try:
        stamp = _dt.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=_dt.timezone.utc)


def held_hours(opened_at: str | None, closed_at: str | None) -> float | None:
    """Hours from open to close, 2 dp -- or None when it cannot be measured.

    None, never 0, when either stamp is missing or unparseable, and when the
    close precedes the open (a hand-edited record): a 0h hold is a real
    answer that a broken record must not be able to fake. Deliberately not
    `api_v1/trades._held_hours` -- core never imports admin.
    """
    opened, closed = _utc_stamp(opened_at), _utc_stamp(closed_at)
    if opened is None or closed is None or closed < opened:
        return None
    return round((closed - opened).total_seconds() / 3600, 2)


# The only two directions a return can be signed for -- the same rule
# `metrics.r_multiple` applies; anything else is None, not a guessed long.
_DIRECTION_SIGN = {"bullish": 1, "bearish": -1}


def return_pct(entry: float | None, exit_price: float | None,
               direction: str | None) -> float | None:
    """Signed % move from entry to exit in the trade's favour, 2 dp.

    A short that fell 10% returns +10. None when entry is missing or 0, the
    exit is missing, or the direction is unknown.
    """
    sign = _DIRECTION_SIGN.get(direction)
    if not entry or exit_price is None or sign is None:
        return None
    return round((exit_price - entry) / entry * 100 * sign, 2)


def _leg_reason(part: dict, trade: dict) -> str | None:
    """The parent trade's recorded reason for this part's leg, or None.

    A leg part carries `legs: None`, so the reason only lives on the parent,
    at the part's own `leg_index` (`expand_trade_legs` emits legs in order).
    """
    legs = trade.get("legs") or []
    index = part.get("leg_index")
    if not isinstance(index, int) or not 0 <= index < len(legs):
        return None
    return legs[index].get("reason")


def row_exit_reason(part: dict, trade: dict) -> str:
    """The EXIT_REASONS bucket of one calendar row.

    A whole trade (`leg_total == 1`) is bucketed like every other exit-quality
    table: `metrics.exit_reason_bucket` on the trade. A leg is bucketed by
    its own recorded reason, text only -- "other" when that names nothing.
    """
    if part.get("leg_total") == 1:
        return metrics.exit_reason_bucket(trade)
    return metrics.exit_reason_bucket_text(_leg_reason(part, trade)) or "other"


def _detail_fields(part: dict, trade: dict) -> dict:
    """The D1 fields, read from the part `expand_realized_legs` built.

    Leg prices, leg shares and the leg's close are already on the part, so
    nothing here re-prices a leg -- a third copy of that maths beside
    `expand_trade_legs` and `api_v1/trades._row_from_leg` is how the three
    start to disagree. Every missing input stays None.
    """
    entry_price = _float_or_none(part.get("entry"))
    exit_price = _float_or_none(part.get("exit_price"))
    return {
        "entry_price": entry_price,
        "exit_price": exit_price,
        "stop_price": _float_or_none(part.get("stop_loss")),
        "tp1": _float_or_none(part.get("take_profit")),
        "tp2": _float_or_none(part.get("target2")),
        "shares": _float_or_none(part.get("shares")),
        "held_hours": held_hours(part.get("opened_at"), part.get("closed_at")),
        "return_pct": return_pct(entry_price, exit_price, part.get("direction")),
        "exit_reason": row_exit_reason(part, trade),
    }
```

Change `_row_for`'s signature and its last two dict lines (body otherwise unchanged; add one sentence to the docstring):

```python
def _row_for(part: dict, entry: dict, trade: dict) -> dict | None:
```

docstring, appended as a final paragraph:

```python
    `trade` is the part's parent record: a leg part has `legs: None`, and its
    exit reason only lives in `trade["legs"]` (see `row_exit_reason`).
```

and the end of the returned dict becomes:

```python
        "leg_index": part["leg_index"],
        "leg_total": part["leg_total"],
        **_detail_fields(part, trade),
    }
```

In `joined_rows`, pass the parent trade:

```python
        for part in expand_realized_legs(t):
            if (row := _row_for(part, entry, t)) is not None:
                rows.append(row)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page/scripts/dev/testrun.py file tests/analytics/test_pnl_calendar.py`
Expected: `0 failed` (the pre-existing `test_a_row_carries_exactly_the_declared_keys` passes too).

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page/scripts/dev/testrun.py file tests/admin/test_api_v1_calendar.py`
Expected: `0 failed`.

Check for any other caller of `_row_for` (there should be none outside `joined_rows`):

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page grep -n "_row_for(" -- "*.py"
```

Expected: the definition and the one call in `joined_rows` only.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page/swingbot/core/analytics/pnl_calendar.py`
Expected: no output (every function in the module stays below C; `_row_for` stays B 8).

- [ ] **Step 6: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page add swingbot/core/analytics/pnl_calendar.py tests/analytics/test_pnl_calendar.py tests/admin/test_api_v1_calendar.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page commit -m "feat(calendar): rows carry prices, shares, hold time, % return and exit reason"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the last command lists no file this plan touches.

### Task CD3: D2 day context: percentile among other trading days, vs-average-day and vs-weekday deltas

**Model:** sonnet — pure aggregation in one module, rules fixed by D2

**Files:**
- Modify: `swingbot/core/analytics/pnl_calendar.py` (new section after `day_streak`, at the end of the module)
- Modify: `tests/analytics/test_pnl_calendar.py` (append a D2 section)

**Interfaces:**
- Consumes: `bucket_by_day(rows) -> dict[str, list[dict]]` and `day_summary(day, rows) -> {"date", "net_pnl_amount", "net_r", "trade_count", "win_rate"}` (both on `main`) — the calendar cell's day-net rule; no second definition.
- Produces (consumed by CD5's route and the frontend `DayContext` in CD7):
  - `PERCENTILE_MIN_DAYS = 20`
  - `day_context(rows: list[dict], date: str) -> dict` returning exactly
    `{"percentile": float | None, "history_days": int, "vs_avg_day": {"pnl_amount": float | None, "r": float | None}, "vs_weekday_avg": {"pnl_amount": float | None, "r": float | None}}`.
    `rows` is the **filtered, all-history** row set (the same scope `day_of_week_breakdown` gets); `date` is `YYYY-MM-DD`.

**Rules, fixed by D2 and the Global Constraints:**
- A day's net P&L / net R = `day_summary(day, rows)["net_pnl_amount" | "net_r"]` (sum of non-null rows; `None` when all are null).
- **Reference set** = the *other* trading days (this day excluded) whose net P&L is non-null. `history_days` = its size. Null-net-P&L days are out of the percentile and out of *both* averages; within the reference set, a day whose net R is null is additionally out of the R means only.
- `percentile = (strictly below + 0.5 × ties) / history_days × 100`, 1 dp; `None` when `history_days < PERCENTILE_MIN_DAYS` or this day's own net P&L is `None`.
- `vs_avg_day` = this day's net minus the mean over the reference set; `vs_weekday_avg` = the same against the reference days on the same weekday (`date.weekday()`; a per-*day* mean, unlike `day_of_week_breakdown`, which averages per trade). 2 dp. A side with no reference values is `None`.
- When this day's own net P&L is `None`, the whole context is null (percentile and all four deltas), whatever its net R — Review Focus 1: the page renders `—`, never a figure built on a day whose dollars are unknown.
- The page-side band (< 60 days) and hide (< 20 days) are frontend work (CD8); this function only ever returns the exact percentile or `None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/analytics/test_pnl_calendar.py`:

```python
# --- v165 D2: day context -------------------------------------------------
#
# Rows are built directly: day_context reads only day / pnl_amount /
# r_multiple / outcome, exactly what day_summary (the cell rule) reads.

import datetime as _dt

from swingbot.core.analytics.pnl_calendar import PERCENTILE_MIN_DAYS, day_context

_NULL_CONTEXT_DELTAS = {"pnl_amount": None, "r": None}


def _net_row(day, pnl, r=None):
    return {"day": day, "pnl_amount": pnl, "r_multiple": r,
            "outcome": "win" if (pnl or 0) > 0 else "loss"}


def _other_days(values, start="2026-05-01"):
    """One single-row day per value, on consecutive calendar dates from
    `start` -- weekday is irrelevant to the percentile."""
    first = _dt.date.fromisoformat(start)
    return [_net_row((first + _dt.timedelta(days=i)).isoformat(), value)
            for i, value in enumerate(values)]


def test_the_percentile_floor_is_twenty_other_days():
    assert PERCENTILE_MIN_DAYS == 20


def test_percentile_counts_ties_half_against_the_other_days_only():
    # 20 other days: 10 at -10, 5 at +5, 5 at +20. This day: +5.
    # Below: 10, ties: 5 -> (10 + 2.5) / 20 * 100 = 62.5.
    # Were the day in its own set it would be (10 + 3) / 21 * 100 = 61.9.
    others = _other_days([-10.0] * 10 + [5.0] * 5 + [20.0] * 5)
    context = day_context(others + [_net_row("2026-08-10", 5.0)], "2026-08-10")
    assert context["percentile"] == 62.5
    assert context["history_days"] == 20


def test_percentile_is_null_below_twenty_other_days():
    nineteen = _other_days([1.0] * 19)
    context = day_context(nineteen + [_net_row("2026-08-10", 5.0)], "2026-08-10")
    assert context["percentile"] is None
    assert context["history_days"] == 19

    twenty = _other_days([1.0] * 20)
    context = day_context(twenty + [_net_row("2026-08-10", 5.0)], "2026-08-10")
    assert context["percentile"] == 100.0


def test_null_net_days_are_left_out_of_the_reference_set():
    others = _other_days([-10.0] * 10 + [5.0] * 5 + [20.0] * 5)
    unknown = [_net_row("2026-07-01", None, 3.0), _net_row("2026-07-02", None),
               _net_row("2026-07-03", None)]
    context = day_context(others + unknown + [_net_row("2026-08-10", 5.0)], "2026-08-10")
    # Same as without them: never counted as a $0 day.
    assert context["percentile"] == 62.5
    assert context["history_days"] == 20


def test_vs_average_day_and_vs_same_weekday_compare_day_nets():
    # 2026-08-10 and 2026-08-03 and 2026-07-27 are Mondays, 08-04 a Tuesday,
    # 08-05 a Wednesday.
    rows = [
        _net_row("2026-08-10", 40.0, 2.0),            # this day
        _net_row("2026-08-03", 10.0, 1.0),
        _net_row("2026-07-27", 30.0, None),           # null R: out of R means only
        _net_row("2026-08-04", -100.0, -5.0),
        _net_row("2026-08-05", None, 9.0),            # null P&L: out of everything
    ]
    context = day_context(rows, "2026-08-10")
    assert context["history_days"] == 3
    assert context["percentile"] is None              # 3 < 20
    # P&L mean of the 3 reference days: (10 + 30 - 100) / 3 = -20 -> 40 - -20.
    # R mean of the 2 with an R: (1 - 5) / 2 = -2 -> 2 - -2.
    assert context["vs_avg_day"] == {"pnl_amount": 60.0, "r": 4.0}
    # Mondays: P&L mean (10 + 30) / 2 = 20; R mean over 08-03 only = 1.
    assert context["vs_weekday_avg"] == {"pnl_amount": 20.0, "r": 1.0}


def test_the_day_net_is_the_calendar_cells_rule():
    # Partial-null day: the cell sums the computable rows (50, 1.0).
    rows = [_net_row("2026-08-10", 50.0, 1.0), _net_row("2026-08-10", None, None),
            _net_row("2026-08-03", 10.0, 0.5)]
    context = day_context(rows, "2026-08-10")
    assert context["vs_avg_day"] == {"pnl_amount": 40.0, "r": 0.5}
    assert context["vs_weekday_avg"] == {"pnl_amount": 40.0, "r": 0.5}


def test_deltas_are_rounded_to_two_places():
    rows = [_net_row("2026-08-10", 10.0, 1.0), _net_row("2026-08-03", 1.0, 0.1),
            _net_row("2026-08-04", 2.0, 0.2), _net_row("2026-08-05", 2.0, 0.2)]
    context = day_context(rows, "2026-08-10")
    # mean P&L 5/3 = 1.6667 -> 10 - 1.6667 = 8.3333; mean R 0.5/3 -> 0.8333.
    assert context["vs_avg_day"] == {"pnl_amount": 8.33, "r": 0.83}


def test_a_day_with_a_null_net_gets_null_context():
    others = _other_days([10.0] * 25)
    context = day_context(others + [_net_row("2026-08-10", None, 1.0)], "2026-08-10")
    assert context == {
        "percentile": None, "history_days": 25,
        "vs_avg_day": _NULL_CONTEXT_DELTAS, "vs_weekday_avg": _NULL_CONTEXT_DELTAS,
    }


def test_a_date_with_no_rows_and_an_empty_book_are_null_not_errors():
    assert day_context([], "2026-08-03") == {
        "percentile": None, "history_days": 0,
        "vs_avg_day": _NULL_CONTEXT_DELTAS, "vs_weekday_avg": _NULL_CONTEXT_DELTAS,
    }
    only_others = _other_days([10.0] * 3)
    assert day_context(only_others, "2026-08-03")["vs_avg_day"] == _NULL_CONTEXT_DELTAS


def test_a_weekday_with_no_other_days_has_a_null_weekday_delta():
    rows = [_net_row("2026-08-10", 40.0, 2.0), _net_row("2026-08-04", 10.0, 1.0)]
    context = day_context(rows, "2026-08-10")
    assert context["vs_avg_day"] == {"pnl_amount": 30.0, "r": 1.0}
    assert context["vs_weekday_avg"] == _NULL_CONTEXT_DELTAS
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page/scripts/dev/testrun.py file tests/analytics/test_pnl_calendar.py`
Expected: FAIL at collection — `ImportError: cannot import name 'PERCENTILE_MIN_DAYS'`.

- [ ] **Step 3: Implement**

Append to the end of `swingbot/core/analytics/pnl_calendar.py`:

```python
# --- v165 D2: how one day compares with the rest of the book ---------------

# Below this many other trading days a percentile is not shown at all: one
# step of a 10-day percentile is 10 points, which reads as precision it is
# not. The page bands it below 60 (CD8); the server only ever returns the
# exact figure or None.
PERCENTILE_MIN_DAYS = 20


def _weekday_of(day: str) -> int | None:
    try:
        return _dt.date.fromisoformat(day).weekday()
    except (TypeError, ValueError):
        return None


def _percentile(value: float, others: list[float]) -> float | None:
    """Share of `others` strictly below `value`, ties counting half, x 100."""
    if len(others) < PERCENTILE_MIN_DAYS:
        return None
    below = sum(1 for other in others if other < value)
    ties = sum(1 for other in others if other == value)
    return round((below + 0.5 * ties) / len(others) * 100, 1)


def _delta(value: float | None, others: list[float]) -> float | None:
    if value is None or not others:
        return None
    return round(value - sum(others) / len(others), 2)


def _deltas(own: dict, reference: list[dict]) -> dict:
    """This day's net minus the reference days' mean, P&L and R apiece.

    `reference` already excludes null-P&L days; a day with a null net R is
    dropped from the R mean only.
    """
    pnl = [s["net_pnl_amount"] for s in reference]
    r = [s["net_r"] for s in reference if s["net_r"] is not None]
    return {"pnl_amount": _delta(own["net_pnl_amount"], pnl),
            "r": _delta(own["net_r"], r)}


def day_context(rows: list[dict], date: str) -> dict:
    """How `date` sits against every other trading day under the filter.

    `rows` is the filtered ALL-HISTORY row set -- the same scope the weekday
    table uses -- and each day's net is `day_summary`'s, the calendar cell's
    own rule, so this can never disagree with the grid.

    The reference set is the OTHER trading days with a known net P&L: a day
    in its own reference set inflates its percentile, and a null-dollar day
    counted as $0 drags every mean toward flat. When this day's own dollars
    are unknown the whole context is None -- there is nothing to compare.
    """
    buckets = bucket_by_day(rows)
    own = day_summary(date, buckets.get(date, []))
    reference = [day_summary(day, group) for day, group in buckets.items()
                 if day != date]
    reference = [s for s in reference if s["net_pnl_amount"] is not None]
    weekday = _weekday_of(date)
    same_weekday = [s for s in reference
                    if weekday is not None and _weekday_of(s["date"]) == weekday]
    if own["net_pnl_amount"] is None:
        nothing = {"pnl_amount": None, "r": None}
        return {"percentile": None, "history_days": len(reference),
                "vs_avg_day": dict(nothing), "vs_weekday_avg": dict(nothing)}
    return {
        "percentile": _percentile(own["net_pnl_amount"],
                                  [s["net_pnl_amount"] for s in reference]),
        "history_days": len(reference),
        "vs_avg_day": _deltas(own, reference),
        "vs_weekday_avg": _deltas(own, same_weekday),
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page/scripts/dev/testrun.py file tests/analytics/test_pnl_calendar.py`
Expected: `0 failed`.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page/swingbot/core/analytics/pnl_calendar.py`
Expected: no output (`day_context` is A/B; every new helper is A).

- [ ] **Step 6: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page add swingbot/core/analytics/pnl_calendar.py tests/analytics/test_pnl_calendar.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page commit -m "feat(calendar): day_context -- percentile and deltas against the other trading days"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the last command lists no file this plan touches.

### Task CD4: D3 day breakdown by strategy, horizon, direction, exit reason

**Model:** sonnet — pure grouping in one module

**Files:**
- Modify: `swingbot/core/analytics/pnl_calendar.py` (new section at the end of the module, after CD3's `day_context`)
- Modify: `tests/analytics/test_pnl_calendar.py` (append a D3 section)

**Interfaces:**
- Consumes: the row keys `strategy`, `horizon`, `direction`, `exit_reason` (CD2), `pnl_amount`, `r_multiple`, `outcome`; `_sum_or_none` (on `main`); `metrics.win_rate(closed: list[dict]) -> float | None` (0-100 scale, `None` when no win/loss rows).
- Produces (consumed by CD5's route and the frontend `DayBreakdown` in CD7):
  - `BREAKDOWN_DIMENSIONS = ("strategy", "horizon", "direction", "exit_reason")`
  - `day_breakdown(rows: list[dict]) -> dict[str, list[dict]]` — exactly one key per dimension (in `BREAKDOWN_DIMENSIONS` order), each a list of `{"key": str, "n": int, "pnl_amount": float | None, "r": float | None, "win_rate": float | None}`.

**Rules, fixed by D3:**
- `rows` are exactly the day's `trades` (the route passes `day_rows`), so every dimension's `n` sums to `trade_count` and its non-null `pnl_amount` / `r` sum to the tiles' `total_ccy` / `total_r`.
- A null or empty key becomes `"unknown"`.
- `pnl_amount` / `r` per group use `_sum_or_none` (the cell rule: `None` when every row is null, never 0).
- `win_rate` = `metrics.win_rate([{"status": row["outcome"]} ...])`, the day route's own rule; `None` for a group with no decided (win/loss) rows, never 0. Unrounded, like `day_summary`'s.
- Sort: `pnl_amount` descending, `None` last; ties broken by `key` ascending so the order is deterministic.
- The `n < 5` win% suppression is page-side (CD12); the server always returns the figure.

- [ ] **Step 1: Write the failing tests**

Append to `tests/analytics/test_pnl_calendar.py`:

```python
# --- v165 D3: what drove the day ------------------------------------------

from swingbot.core.analytics.pnl_calendar import (BREAKDOWN_DIMENSIONS,
                                                  _sum_or_none, day_breakdown)


def _drove_row(strategy, horizon, direction, exit_reason, pnl, r, outcome):
    return {"strategy": strategy, "horizon": horizon, "direction": direction,
            "exit_reason": exit_reason, "pnl_amount": pnl, "r_multiple": r,
            "outcome": outcome}


def _drove_rows():
    """Four rows on one day. Hand-computed groups are in the tests below."""
    return [
        _drove_row("EMA20", "4w", "bullish", "tp1", 50.0, 2.0, "win"),
        _drove_row("EMA20", "3m", "bullish", "stop", -20.0, -0.8, "loss"),
        _drove_row("VWAP", "4w", "bearish", "tp1", 30.0, 1.0, "win"),
        # A manual close with no dollar figure and no R: counted, not $0.
        _drove_row("VWAP", None, "bearish", "other", None, None, "closed"),
    ]


def test_breakdown_has_exactly_the_four_dimensions():
    assert BREAKDOWN_DIMENSIONS == ("strategy", "horizon", "direction", "exit_reason")
    assert tuple(day_breakdown(_drove_rows())) == BREAKDOWN_DIMENSIONS


def test_breakdown_groups_sum_and_rate_each_dimension():
    breakdown = day_breakdown(_drove_rows())
    # EMA20: +50 -20 = +30, R 2.0 - 0.8 = 1.2, 1 win of 2 decided.
    # VWAP: +30 (the null row adds nothing), R 1.0, 1 win of 1 decided.
    # Equal P&L -> key order.
    assert breakdown["strategy"] == [
        {"key": "EMA20", "n": 2, "pnl_amount": 30.0, "r": 1.2, "win_rate": 50.0},
        {"key": "VWAP", "n": 2, "pnl_amount": 30.0, "r": 1.0, "win_rate": 100.0},
    ]
    assert breakdown["direction"] == [
        {"key": "bearish", "n": 2, "pnl_amount": 30.0, "r": 1.0, "win_rate": 100.0},
        {"key": "bullish", "n": 2, "pnl_amount": 30.0, "r": 1.2, "win_rate": 50.0},
    ]


def test_a_null_key_is_unknown_and_an_all_null_group_sorts_last():
    breakdown = day_breakdown(_drove_rows())
    assert breakdown["horizon"] == [
        {"key": "4w", "n": 2, "pnl_amount": 80.0, "r": 3.0, "win_rate": 100.0},
        {"key": "3m", "n": 1, "pnl_amount": -20.0, "r": -0.8, "win_rate": 0.0},
        # No decided row -> win_rate None, not 0; no dollars -> None, not 0.
        {"key": "unknown", "n": 1, "pnl_amount": None, "r": None, "win_rate": None},
    ]
    assert breakdown["exit_reason"] == [
        {"key": "tp1", "n": 2, "pnl_amount": 80.0, "r": 3.0, "win_rate": 100.0},
        {"key": "stop", "n": 1, "pnl_amount": -20.0, "r": -0.8, "win_rate": 0.0},
        {"key": "other", "n": 1, "pnl_amount": None, "r": None, "win_rate": None},
    ]


def test_every_dimension_sums_back_to_the_days_totals():
    rows = _drove_rows()
    total_pnl = _sum_or_none([r["pnl_amount"] for r in rows])
    total_r = _sum_or_none([r["r_multiple"] for r in rows])
    for dimension, groups in day_breakdown(rows).items():
        assert sum(g["n"] for g in groups) == len(rows), dimension
        assert sum(g["pnl_amount"] for g in groups
                   if g["pnl_amount"] is not None) == pytest.approx(total_pnl), dimension
        assert sum(g["r"] for g in groups if g["r"] is not None) == pytest.approx(total_r), dimension


def test_an_empty_key_string_is_unknown_too():
    rows = [_drove_row("", "4w", "bullish", "tp1", 10.0, 1.0, "win")]
    assert day_breakdown(rows)["strategy"][0]["key"] == "unknown"


def test_an_empty_day_breaks_down_into_empty_lists():
    assert day_breakdown([]) == {d: [] for d in BREAKDOWN_DIMENSIONS}


def test_breakdown_reads_the_d1_exit_reason_of_joined_rows():
    trade = _scaled_trade("a" * 16, legs=({**_TP1, "reason": "tp1"},
                                          {**_RUNNER, "reason": "runner_trail"}))
    keys = {g["key"] for g in day_breakdown(joined_rows([trade], []))["exit_reason"]}
    assert keys == {"tp1", "runner_trail"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page/scripts/dev/testrun.py file tests/analytics/test_pnl_calendar.py`
Expected: FAIL at collection — `ImportError: cannot import name 'BREAKDOWN_DIMENSIONS'`.

- [ ] **Step 3: Implement**

Append to the end of `swingbot/core/analytics/pnl_calendar.py`:

```python
# --- v165 D3: what drove one day --------------------------------------------

# The four ways the day page splits a day. Order is the page's tab order.
BREAKDOWN_DIMENSIONS = ("strategy", "horizon", "direction", "exit_reason")


def _breakdown_group(key: str, group: list[dict]) -> dict:
    """One breakdown row: count, summed dollars and R, win rate.

    Same rules as the day's tiles -- `_sum_or_none` (all-null is None, not
    $0) and `metrics.win_rate` over outcomes (no decided row is None, not
    0%) -- so the rows of a dimension add back up to the tiles.
    """
    return {
        "key": key,
        "n": len(group),
        "pnl_amount": _sum_or_none([r["pnl_amount"] for r in group]),
        "r": _sum_or_none([r["r_multiple"] for r in group]),
        "win_rate": metrics.win_rate([{"status": r["outcome"]} for r in group]),
    }


def _breakdown_order(group: dict) -> tuple:
    """P&L descending, unknown P&L last, then key -- deterministic on ties."""
    pnl = group["pnl_amount"]
    return (pnl is None, -(pnl or 0.0), group["key"])


def day_breakdown(rows: list[dict]) -> dict[str, list[dict]]:
    """The day split by strategy, horizon, direction and exit reason.

    `rows` must be exactly the day's `trades` list, so each dimension's `n`
    sums to `trade_count` and its non-null P&L / R to the tiles' totals. Not
    `/analytics/by-dimension`: that scopes by trade, and on a scale-out day
    it would disagree with these per-leg rows. A missing key is "unknown".
    """
    out: dict[str, list[dict]] = {}
    for dimension in BREAKDOWN_DIMENSIONS:
        groups: dict[str, list[dict]] = {}
        for row in rows:
            groups.setdefault(row.get(dimension) or "unknown", []).append(row)
        out[dimension] = sorted(
            (_breakdown_group(key, group) for key, group in groups.items()),
            key=_breakdown_order,
        )
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page/scripts/dev/testrun.py file tests/analytics/test_pnl_calendar.py`
Expected: `0 failed`.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page/swingbot/core/analytics/pnl_calendar.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page add swingbot/core/analytics/pnl_calendar.py tests/analytics/test_pnl_calendar.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page commit -m "feat(calendar): day_breakdown by strategy, horizon, direction and exit reason"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the last command lists no file this plan touches.

### Task CD5: D4 day route: `day_totals` lifted out of `calendar_pnl_day`, response gains `context` and `breakdown`

**Model:** opus — splits a legacy function at complexity D(22)

**Files:**
- Modify: `swingbot/core/analytics/pnl_calendar.py` (new section at the end, after CD4's `day_breakdown`)
- Modify: `swingbot/admin/api_v1/calendar.py` (`calendar_pnl_day`, ~:121-190)
- Modify: `tests/analytics/test_pnl_calendar.py` (append a `day_totals` section)
- Modify: `tests/admin/test_api_v1_calendar.py` (outer shape in `test_day_trade_shape_carries_the_journal_join`; new tests appended)

**Interfaces:**
- Consumes: `day_context(rows, date)` (CD3), `day_breakdown(rows)` (CD4), the D1 row fields (CD2); `_sum_or_none`, `_avg_or_none` (on `main`), `metrics.win_rate`.
- Produces (consumed by CD6, which edits the same route file, and the frontend `CalendarDayTrades` in CD7):
  - `pnl_calendar.day_totals(day_rows: list[dict]) -> dict` with exactly the keys `trade_count, winners, losers, total_r, total_ccy, win_rate, avg_trade_r, worst_drawdown_r, contributors, detractors` (in that order), every value identical to what the route computes today.
  - `GET /api/v1/calendar/pnl/day` response = `{as_of, date, trades, **day_totals, context, breakdown}`. `context` = `pc.day_context(rows, date)` over the **filtered all-history** rows; `breakdown` = `pc.day_breakdown(day_rows)` over exactly the day's `trades`. 404 on a day with no rows and every existing field unchanged.

**What must not change.** This is a refactor of the summary plus two new keys. The existing route tests (`test_day_detail_summarises_its_existing_trade_rows`, `..._orders_leaders_by_r_magnitude_...`, `..._404_...`, `..._400`, the TP1-partial test) are the behaviour guard and stay untouched. Equivalences used in the lift, each exact:
- `total_r`: `round(sum(measured), 2) if measured else None` ≡ `_sum_or_none(measured)` (`measured` already excludes `None`).
- `total_ccy`: `round(sum(non-null pnl), 2) if any non-null else None` ≡ `_sum_or_none(pnl values)`.
- `avg_trade_r`: `round(sum(measured) / len(measured), 2) if measured else None` ≡ `_avg_or_none(measured)`.
- `winners` / `losers` / leaders / drawdown: moved verbatim (`sorted` is stable, so tie order is unchanged).

- [ ] **Step 1: Write the failing tests**

Append to `tests/analytics/test_pnl_calendar.py`:

```python
# --- v165 D4: the day route's summary, lifted out of the view --------------

from swingbot.core.analytics.pnl_calendar import day_totals


def _tile_row(ticker, r, pnl, outcome):
    return {"ticker": ticker, "r_multiple": r, "pnl_amount": pnl, "outcome": outcome}


def test_day_totals_has_exactly_the_routes_summary_keys_in_order():
    assert list(day_totals([_tile_row("AAPL", 1.0, 10.0, "win")])) == [
        "trade_count", "winners", "losers", "total_r", "total_ccy", "win_rate",
        "avg_trade_r", "worst_drawdown_r", "contributors", "detractors"]


def test_day_totals_values():
    rows = [_tile_row("AAPL", 2.0, 50.0, "win"),
            _tile_row("MSFT", -1.0, -25.0, "loss"),
            _tile_row("NVDA", None, None, "closed")]
    assert day_totals(rows) == {
        "trade_count": 3, "winners": 1, "losers": 1,
        "total_r": 1.0, "total_ccy": 25.0,
        # NVDA's "closed" is neither a win nor a loss.
        "win_rate": 50.0,
        "avg_trade_r": 0.5,
        # Running R: 2.0 (peak) then 1.0 -> drawdown 1.0.
        "worst_drawdown_r": 1.0,
        "contributors": [{"ticker": "AAPL", "r": 2.0}],
        "detractors": [{"ticker": "MSFT", "r": -1.0}],
    }


def test_day_totals_with_no_measurable_r_is_none_not_zero():
    totals = day_totals([_tile_row("AAPL", None, None, "closed")])
    assert (totals["total_r"], totals["total_ccy"], totals["avg_trade_r"],
            totals["worst_drawdown_r"], totals["win_rate"]) == (None, None, None, None, None)
    assert (totals["winners"], totals["losers"]) == (0, 0)
    assert totals["contributors"] == [] and totals["detractors"] == []


def test_day_totals_leaders_are_the_five_largest_by_magnitude():
    rows = [_tile_row(f"T{i}", float(i), 1.0, "win") for i in range(1, 8)]
    assert [x["r"] for x in day_totals(rows)["contributors"]] == [7.0, 6.0, 5.0, 4.0, 3.0]


def test_day_totals_drawdown_walks_the_rows_in_the_order_given():
    # Close order +1, -2, +3, -1: peak 1 -> -1 (dd 2), peak 2 -> 1 (dd 1).
    rows = [_tile_row("A", 1.0, 1.0, "win"), _tile_row("B", -2.0, -1.0, "loss"),
            _tile_row("C", 3.0, 1.0, "win"), _tile_row("D", -1.0, -1.0, "loss")]
    assert day_totals(rows)["worst_drawdown_r"] == 2.0
```

In `tests/admin/test_api_v1_calendar.py`, inside `test_day_trade_shape_carries_the_journal_join`, replace the outer `assert_shape(body, {...})` (the one on `body`, not `trades[0]`) with:

```python
    assert_shape(body, {
        "as_of": str, "date": str, "trades": list, "trade_count": int, "winners": int,
        "losers": int, "total_r": NULLABLE_NUMBER,
        "total_ccy": NULLABLE_NUMBER, "win_rate": NULLABLE_NUMBER,
        "avg_trade_r": NULLABLE_NUMBER,
        "worst_drawdown_r": NULLABLE_NUMBER, "contributors": list,
        "detractors": list,
        # v165 D2 / D3.
        "context": dict, "breakdown": dict,
    })
    assert_shape(body["context"], {
        "percentile": NULLABLE_NUMBER, "history_days": int,
        "vs_avg_day": dict, "vs_weekday_avg": dict,
    }, where="context")
    for side in ("vs_avg_day", "vs_weekday_avg"):
        assert_shape(body["context"][side], {"pnl_amount": NULLABLE_NUMBER, "r": NULLABLE_NUMBER},
                     where=f"context.{side}")
    assert list(body["breakdown"]) == ["strategy", "horizon", "direction", "exit_reason"]
    assert_shape(body["breakdown"]["strategy"][0], {
        "key": str, "n": int, "pnl_amount": NULLABLE_NUMBER,
        "r": NULLABLE_NUMBER, "win_rate": NULLABLE_NUMBER,
    }, where="breakdown.strategy[0]")
```

Then append to the end of `tests/admin/test_api_v1_calendar.py`:

```python
# --- v165: day context and breakdown on the day route ----------------------


def _context_book():
    """08-03 (Mon): EMA20 +50 (r +2.0), VWAP -20.  08-04 (Tue): EMA20 +30
    (r +1.2).  08-05 (Wed): EMA20 -10 (r -0.4), VWAP +100. No journal, so
    every R is metrics.r_multiple off entry 100 / stop 95."""
    return [
        _trade("a" * 16, closed_at="2026-08-03T20:00:00+00:00", pnl=50.0,
               exit_price=110.0, sources=("EMA20",)),
        _trade("b" * 16, closed_at="2026-08-03T21:00:00+00:00", pnl=-20.0,
               exit_price=96.0, status="loss", sources=("VWAP",)),
        _trade("c" * 16, closed_at="2026-08-04T20:00:00+00:00", pnl=30.0,
               exit_price=106.0, sources=("EMA20",)),
        _trade("d" * 16, closed_at="2026-08-05T20:00:00+00:00", pnl=-10.0,
               exit_price=98.0, status="loss", sources=("EMA20",)),
        _trade("e" * 16, closed_at="2026-08-05T21:00:00+00:00", pnl=100.0,
               exit_price=120.0, sources=("VWAP",)),
    ]


def test_day_context_compares_against_the_other_days_under_the_filter(seed, logged_in):
    seed(trades=_context_book())
    body = logged_in.get(
        "/api/v1/calendar/pnl/day?date=2026-08-03&strategy=EMA20").get_json()
    # Other EMA20 days: 08-04 (+30, 1.2R) and 08-05 (-10, -0.4R).
    # Means +10 and 0.4R -> deltas +40 and 2.0 - 0.4 = 1.6R. No other Monday.
    assert body["context"] == {
        "percentile": None, "history_days": 2,
        "vs_avg_day": {"pnl_amount": 40.0, "r": 1.6},
        "vs_weekday_avg": {"pnl_amount": None, "r": None},
    }


def test_day_net_equals_the_grid_cell_and_the_breakdown_sums_to_the_tiles(seed, logged_in):
    seed(trades=_context_book())
    for query in ("", "&strategy=EMA20", "&strategy=VWAP"):
        grid = logged_in.get(f"/api/v1/calendar/pnl?month=2026-08{query}").get_json()
        cell = next(d for d in grid["days"] if d["date"] == "2026-08-03")
        body = logged_in.get(f"/api/v1/calendar/pnl/day?date=2026-08-03{query}").get_json()
        assert body["total_ccy"] == cell["net_pnl_amount"], query
        assert body["trade_count"] == cell["trade_count"], query
        for dimension, groups in body["breakdown"].items():
            assert sum(g["n"] for g in groups) == body["trade_count"], (query, dimension)
            assert sum(g["pnl_amount"] for g in groups if g["pnl_amount"] is not None) \
                == pytest.approx(body["total_ccy"]), (query, dimension)
            assert sum(g["r"] for g in groups if g["r"] is not None) \
                == pytest.approx(body["total_r"]), (query, dimension)


def test_day_breakdown_is_built_from_exactly_the_days_trades(seed, logged_in):
    seed(trades=_context_book())
    body = logged_in.get("/api/v1/calendar/pnl/day?date=2026-08-03").get_json()
    # R: (110-100)/5 = 2.0 and (96-100)/5 = -0.8.
    assert body["breakdown"]["strategy"] == [
        {"key": "EMA20", "n": 1, "pnl_amount": 50.0, "r": 2.0, "win_rate": 100.0},
        {"key": "VWAP", "n": 1, "pnl_amount": -20.0, "r": -0.8, "win_rate": 0.0},
    ]
    # Unfiltered: this day nets 50 - 20 = +30; the other days are 08-04 (+30)
    # and 08-05 (-10 + 100 = +90), mean +60 -> delta -30.
    assert body["context"]["history_days"] == 2
    assert body["context"]["vs_avg_day"]["pnl_amount"] == -30.0


def test_a_leg_row_on_the_day_route_carries_its_own_d1_fields(seed, logged_in):
    runner = {**_trade("m" * 16, status="open", closed_at=None, exit_price=None, pnl=None),
              "legs": [{"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1",
                        "closed_at": "2026-08-03T15:00:00+00:00"}]}
    seed(trades=[runner])
    body = logged_in.get("/api/v1/calendar/pnl/day?date=2026-08-03").get_json()
    leg = body["trades"][0]
    assert (leg["exit_reason"], leg["shares"], leg["exit_price"], leg["return_pct"]) == (
        "tp1", 5.0, 110.0, 10.0)
    # 2026-08-01T14:00Z -> 2026-08-03T15:00Z.
    assert leg["held_hours"] == 49.0
    assert body["breakdown"]["exit_reason"] == [
        {"key": "tp1", "n": 1, "pnl_amount": 50.0, "r": 2.0, "win_rate": 100.0}]


def test_the_day_route_still_404s_before_computing_context(seed, logged_in):
    seed(trades=_context_book())
    assert_error(logged_in.get("/api/v1/calendar/pnl/day?date=2026-08-09&strategy=EMA20"),
                 "not_found", 404)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page/scripts/dev/testrun.py file tests/analytics/test_pnl_calendar.py`
Expected: FAIL at collection — `ImportError: cannot import name 'day_totals'`.

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page/scripts/dev/testrun.py file tests/admin/test_api_v1_calendar.py`
Expected: FAIL — `body: missing key(s) ['breakdown', 'context']` and `KeyError: 'context'` / `'breakdown'` in the new tests; every pre-existing test still passes.

- [ ] **Step 3: Implement `day_totals`**

Append to the end of `swingbot/core/analytics/pnl_calendar.py`:

```python
# --- v165 D4: the day drawer's / day page's summary tiles -------------------


def _leaders(rows: list[dict]) -> list[dict]:
    """The five rows with the largest |R|, as `{ticker, r}`."""
    return [
        {"ticker": row["ticker"], "r": row["r_multiple"]}
        for row in sorted(rows, key=lambda row: abs(row["r_multiple"]), reverse=True)[:5]
    ]


def _worst_drawdown_r(measured: list[float]) -> float | None:
    """Deepest peak-to-trough fall of the running R, walked in close order."""
    if not measured:
        return None
    running = peak = worst = 0.0
    for value in measured:
        running += value
        peak = max(peak, running)
        worst = max(worst, peak - running)
    return round(worst, 2)


def day_totals(day_rows: list[dict]) -> dict:
    """The day's summary tiles, over exactly the rows the day lists.

    Lifted verbatim from `api_v1/calendar.calendar_pnl_day` (v165) so the
    route stays below complexity 15 and this module stays the one place the
    calendar's arithmetic lives. `day_rows` must be in close order -- the
    drawdown walks them as the day happened.
    """
    measured = [r["r_multiple"] for r in day_rows if r["r_multiple"] is not None]
    winners = [r for r in day_rows if r["r_multiple"] is not None and r["r_multiple"] > 0]
    losers = [r for r in day_rows if r["r_multiple"] is not None and r["r_multiple"] < 0]
    return {
        # `trades` stays the route's list contract; this is its numeric
        # companion for the tiles.
        "trade_count": len(day_rows),
        "winners": len(winners),
        "losers": len(losers),
        "total_r": _sum_or_none(measured),
        "total_ccy": _sum_or_none([r["pnl_amount"] for r in day_rows]),
        "win_rate": metrics.win_rate([{"status": r["outcome"]} for r in day_rows]),
        "avg_trade_r": _avg_or_none(measured),
        "worst_drawdown_r": _worst_drawdown_r(measured),
        "contributors": _leaders(winners),
        "detractors": _leaders(losers),
    }
```

- [ ] **Step 4: Rewrite the route**

In `swingbot/admin/api_v1/calendar.py`, replace `calendar_pnl_day` (decorators kept) with:

```python
@api_v1.route("/calendar/pnl/day", methods=["GET"])
@require_auth
def calendar_pnl_day():
    """Every trade closed on one day -- the drawer and the `/calendar/:date`
    page.

    404 rather than an empty 200 when the day holds nothing: every date the
    grid emits has at least one close (days with none are omitted), so an
    empty result means the client asked for a day that is not in the book,
    which is a different answer from "that day was flat".

    Ordered by close time so the list -- and the tiles' running-R drawdown
    -- read as the day happened. The tiles and `breakdown` are computed from
    exactly `trades`, so a filtered grid cannot open a day that tells a
    different story; `context` compares the day against every OTHER trading
    day under the same filter (all history, like the grid's weekday table).
    """
    from swingbot.core.analytics import pnl_calendar as pc

    _reject_unknown_params()
    date = _date_param()
    strategy, horizon = _filter_args()

    rows = pc.filter_rows(pc.load_rows(), strategy=strategy, horizon=horizon)
    day_rows = sorted(
        (r for r in rows if r["day"] == date),
        key=lambda r: r["closed_at"] or "",
    )
    if not day_rows:
        raise ApiError("not_found", f"no closed trades on {date}", 404)

    return jsonify({
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
        "date": date,
        "trades": day_rows,
        **pc.day_totals(day_rows),
        "context": pc.day_context(rows, date),
        "breakdown": pc.day_breakdown(day_rows),
    })
```

The view no longer imports `metrics`; nothing else in the module used that local import. Flask's `jsonify` keeps dict insertion order, so the existing keys still arrive in the same order.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page/scripts/dev/testrun.py file tests/analytics/test_pnl_calendar.py`
Expected: `0 failed`.

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page/scripts/dev/testrun.py file tests/admin/test_api_v1_calendar.py`
Expected: `0 failed` — including every pre-existing day test, unchanged.

Then the two suites these files belong to, narrow but complete:

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page/scripts/dev/testrun.py changed
```

Expected: `0 failed`, `0 xfailed`.

- [ ] **Step 6: Complexity**

Run: `python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page/swingbot/admin/api_v1/calendar.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page/swingbot/core/analytics/pnl_calendar.py`
Expected: **no output** — `calendar_pnl_day` was `D (22)` before this task and is now below C; `day_totals` is below C.

Also print the route's exact score for the commit message check: `python -m radon cc -s E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page/swingbot/admin/api_v1/calendar.py`
Expected: `calendar_pnl_day - A` (single digit).

- [ ] **Step 7: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page add swingbot/core/analytics/pnl_calendar.py swingbot/admin/api_v1/calendar.py tests/analytics/test_pnl_calendar.py tests/admin/test_api_v1_calendar.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v165-calendar-day-page commit -m "feat(calendar): day route serves context and breakdown; summary lifted into day_totals (D22 -> A)"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the last command lists no file this plan touches.


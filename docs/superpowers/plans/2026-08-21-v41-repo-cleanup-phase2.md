# Repo Cleanup Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the one confirmed bug and apply a curated, individually-verified
subset of the dead-code/simplification candidates found by the Phase 1 audit
(`docs/superpowers/results/2026-08-21-repo-cleanup-audit.md`), with zero
speculative changes.

**Architecture:** No new modules, no restructuring. Every task is a small,
targeted edit to an existing file (or a deletion of a completed one-shot
script), each independently testable and independently committable.

**Tech Stack:** Python 3.11+, pytest, yfinance/pandas (Task 1), matplotlib
(Tasks 7-9), TypeScript/Angular (Task 11, edited directly — no build step
run, per the audit's own scope note that Angular tooling wasn't exercised).

Bump: bot patch

## Global Constraints

- This plan assumes plan v36 (`docs/superpowers/plans/2026-08-16-v36-level-touch-strength.md`)
  has already merged to `main`. Every file/line reference below was verified
  against `main` at commit `5235fd4` (pre-v36). The one file v36 also
  touches, `swingbot/core/scanning/engine.py` (Task 6), is safe: v36's edits
  are inside `_scan_one` (lines ~982-1120), Task 6's are in the top-of-file
  import block (lines 45-105) — confirmed disjoint via
  `git diff main...worktree-2026-08-16-v36-level-touch-strength -- swingbot/core/scanning/engine.py`.
  If v36 landed with different line numbers than assumed here, re-verify
  Task 6's context before editing rather than trusting the line numbers
  blindly.
- Verify every task with `python scripts/dev/testrun.py file <the test file
  the task touches>` before committing it (~7s per file — this repo's
  documented fast path; never re-run the full suite per task).
- Task 18 (the version bump) is the LAST task, and only runs after
  `python scripts/dev/testrun.py full` shows `0 failed, 0 xfailed` with
  Tasks 1-17 all committed.
- No new dependencies. Nothing under `.claude/worktrees/` is touched by this
  plan.
- Source of Tasks 1-13, 18: `docs/superpowers/results/2026-08-21-repo-cleanup-audit.md`.
  Tasks 14-17 were added 2026-08-22 from a follow-up pyflakes sweep run
  during this plan's own brainstorming pass — same rigor (pyflakes hit,
  hand-verified against real call sites for re-export/side-effect false
  positives before being added), different source, not in the audit doc.

## Not in this plan (and why)

The audit found more than what's below; these are deliberately excluded,
not forgotten:

- **`core/charts/trade_chart.py`** — the audit listed this as missing a
  try/finally guard around `savefig`. It isn't: `ast`-parsing the function
  confirms the `try` opening at line 469 already has a `finally: plt.close(fig)`
  that covers the `savefig` call at line 1110. The audit was wrong here —
  no task, no change.
- **`core/marketdata/ensure_cached_background`'s no-op Thread** — audit's own
  words were "not urgent, cosmetic." Fixing it would add code, not remove
  it (need a real sentinel/dummy-thread abstraction to avoid spawning a
  literal OS thread for a no-op). Not worth it.
- **9 test files possibly duplicating `make_ohlcv`/`make_trend_df` by hand**
  — the audit verified only 1 of the 10 flagged files; the other 9 need
  individual verification (some may need shapes the shared fixtures don't
  support) before any fix is safe. Needs its own follow-up pass, not a
  blind batch edit here.
- **Duplicated `candidate_symbols` retry-loop shape and `MultiIndex`-flatten
  copy-paste across 4-5 marketdata files** — the audit explicitly flagged
  these as NOT safe for mechanical extraction (retry/exception semantics
  differ subtly per site); consolidating needs a design decision, not a
  cleanup task.
- **`core/marketdata/fmp_client.py`'s standalone-tool-or-should-it-wire-in
  question**, **`core/scanning/engine.py:293`'s deliberately-unwired sizing
  chain**, and **`engine.py`/`commands/scanning.py` size** — all three are
  either a product/feature decision or already-confirmed-not-a-problem, not
  cleanup work.
- **`core/planning/plan_engine.py`'s three near-identical `_resolve_*`
  helpers** — legitimate small consolidation candidate, but `plan_engine.py`
  is v36's most heavily edited file (135 lines changed); deferred to avoid
  editing a file this close to a just-landed feature merge in the same pass.

## Parallelisation

Tasks 1, 2, 3, 6, 8, 9, 10, 11, 12, 14, 15, 16 touch disjoint files and may
run concurrently. **Tasks 4 and 5 both edit `core/tracking/retrospective.py`
and must run sequentially** (either order — they touch different line
ranges, but it's one file, one working tree). **Tasks 7 and 17 both edit
`core/charts/analytics_charts.py` and must run sequentially** for the same
reason (Task 7 touches `_save`, lines 20-48; Task 17 touches
`render_equity_curve`, line 86 — disjoint ranges, same file). Task 18 must
run last, after every other task is committed and the full suite is green.

---

### Task 1: Fix `backtest_cache.fetch()` to try alias candidates

**Files:**
- Modify: `swingbot/core/marketdata/backtest_cache.py:65-73`
- Test: `tests/marketdata/test_backtest_cache.py`

**Interfaces:**
- Consumes: `swingbot.core.marketdata.ticker_utils.candidate_symbols(ticker: str) -> list[str]`
  (already exists, used by `data.py`/`data_store.py`/`export_data.py`).
- Produces: no signature change — `fetch(ticker: str) -> pd.DataFrame | None`
  still returns the same shape, just resolves more tickers successfully.

- [ ] **Step 1: Write the failing test**

Add to `tests/marketdata/test_backtest_cache.py`:

```python
def test_fetch_tries_alias_candidates(monkeypatch):
    """SPX has no direct Yahoo symbol -- ticker_utils.ALIASES maps it to
    ^GSPC. fetch() must try candidates in the same order data.get_daily_data
    does, or alias tickers silently never get cached (the v40 audit bug)."""
    import yfinance as yf

    calls = []

    def fake_download(symbol, **kwargs):
        calls.append(symbol)
        if symbol == "^GSPC":
            return _make_df(500)
        return pd.DataFrame()

    monkeypatch.setattr(yf, "download", fake_download)
    df = bc.fetch("SPX")
    assert calls == ["SPX", "^GSPC"]
    assert df is not None
    assert len(df) == 500
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/marketdata/test_backtest_cache.py::test_fetch_tries_alias_candidates -v`
Expected: FAIL — `assert calls == ["SPX", "^GSPC"]` fails because `calls == ["SPX"]`
(current `fetch()` only tries the raw ticker).

- [ ] **Step 3: Write minimal implementation**

In `swingbot/core/marketdata/backtest_cache.py`, add the import near the top
(alongside the existing `from swingbot import config`):

```python
from swingbot.core.marketdata.ticker_utils import candidate_symbols
```

Replace `fetch()`:

```python
def fetch(ticker: str) -> pd.DataFrame | None:
    """Full available daily history (IPO -> now), split/dividend adjusted,
    normalized to the cache's canonical shape. Tries each of
    ticker_utils.candidate_symbols(ticker) in order (same resolution every
    sibling fetch path in this package uses), returning the first non-empty
    result. Returns None if none resolve."""
    import yfinance as yf  # local import: keeps module import cheap + test-safe

    for candidate in candidate_symbols(ticker):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            df = yf.download(candidate, period="max", auto_adjust=True, progress=False)
        normalized = normalize_ohlcv(df)
        if normalized is not None:
            return normalized
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/marketdata/test_backtest_cache.py -v`
Expected: PASS, all tests in the file (this confirms the fix doesn't break
the 11 existing tests that monkeypatch `bc.fetch` wholesale — they're
unaffected since they replace `fetch` entirely).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/marketdata/backtest_cache.py tests/marketdata/test_backtest_cache.py
git commit -m "fix(v41): backtest_cache.fetch() tries alias candidates like every sibling fetch path

Alias tickers (SPX, XAUUSD, WTI, VIX, NDX, DJI, etc.) never got their
data/backtest_cache/{TICKER}.csv populated because fetch() only tried
the raw ticker string, unlike data.py/data_store.py/export_data.py
which all loop ticker_utils.candidate_symbols(). Found by the v40 audit."
```

---

### Task 2: Remove `StateStore.get_last_trend`/`set_last_trend` dead code

**Files:**
- Modify: `swingbot/core/infra/state.py:33-40`
- Modify: `tests/infra/test_jsonio.py:67-76`

**Interfaces:**
- Consumes: `StateStore.confirm_or_update(key, new_value, required_confirmations=2) -> bool`
  (already exists — the sole production entry point after this task).
- Produces: nothing new. `get_last_trend`/`set_last_trend` no longer exist;
  no other file in `swingbot/`, `commands/`, `admin/`, `scripts/` calls them
  (verified — only their own test did).

- [ ] **Step 1: Update the test to exercise the real (non-dead) API**

`get_last_trend`/`set_last_trend` exist only so `test_statestore_atomic` has
something simple to call — replace it with a call through
`confirm_or_update` (`required_confirmations=1` makes the first call
immediately confirm, so the test still validates "no `.tmp` file left
behind after a real write" and "value persists across a fresh `StateStore`
instance pointed at the same path"):

```python
def test_statestore_atomic(tmp_path):
    from swingbot.core.infra.state import StateStore

    path = str(tmp_path / "state.json")
    store = StateStore(path=path)
    assert store.confirm_or_update("AAPL|Fibonacci|4w", "bullish", required_confirmations=1) is True
    assert not os.path.exists(path + ".tmp")

    reloaded = StateStore(path=path)
    # Matches the already-confirmed value -> no pending flip -> False.
    # If persistence were broken, `confirmed` would reload as None, the
    # first-confirmation branch would fire again, and this would wrongly
    # return True -- so this assertion still proves the reload worked.
    assert reloaded.confirm_or_update("AAPL|Fibonacci|4w", "bullish", required_confirmations=1) is False
```

- [ ] **Step 2: Run test to verify it passes against current code**

Run: `python -m pytest tests/infra/test_jsonio.py::test_statestore_atomic -v`
Expected: PASS (this only changes which public method the test calls;
`get_last_trend`/`set_last_trend` still exist at this point).

- [ ] **Step 3: Delete the dead methods**

In `swingbot/core/infra/state.py`, remove:

```python
    def get_last_trend(self, key: str) -> str | None:
        """`key` is typically `SignalResult.state_key` (ticker|strategy|horizon)."""
        return self._data.get(key, {}).get("trend")

    def set_last_trend(self, key: str, trend: str):
        with _LOCK:
            self._data.setdefault(key, {})["trend"] = trend
            self._save()

```

(the blank line before `confirm_or_update` stays — just this block goes).

- [ ] **Step 4: Run test to verify it still passes**

Run: `python -m pytest tests/infra/test_jsonio.py -v`
Expected: PASS, all tests in the file.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/infra/state.py tests/infra/test_jsonio.py
git commit -m "refactor(v41): remove StateStore.get_last_trend/set_last_trend

No production caller -- confirm_or_update is the real entry point per
this module's own docstring. Only their own test used them; that test
now exercises confirm_or_update instead. Found by the v40 audit."
```

---

### Task 3: Remove unused locals in `explain.py`

**Files:**
- Modify: `swingbot/core/market/explain.py:41-69`
- Test: `tests/market/test_levels_avwap.py`, `tests/scanning/test_embeds_v3.py` (existing — no new test needed, this changes zero output)

**Interfaces:**
- Consumes: nothing new.
- Produces: no signature change — `build_explanation(...)` returns the
  exact same string as before; `opp_word` and `s_count` were computed and
  never read, so removing them cannot change output.

- [ ] **Step 1: Confirm neither variable is read anywhere in the function**

Run: `python -m pyflakes swingbot/core/market/explain.py`
Expected output includes:
```
swingbot/core/market/explain.py:49:5 local variable 'opp_word' is assigned to but never used
swingbot/core/market/explain.py:66:9 local variable 's_count' is assigned to but never used
```

- [ ] **Step 2: Remove `opp_word`**

Delete this line from `build_explanation`:

```python
    opp_word = "support" if is_bull else "resistance"
```

- [ ] **Step 3: Remove `s_count`**

Change:

```python
    # Stop strategies
    if stop_confluence:
        s_count, s_families = stop_confluence
    else:
        s_families = list(dict.fromkeys(strategy_family(s) for s in scenario.stop_sources))
        s_count = len(s_families)
```

to:

```python
    # Stop strategies
    if stop_confluence:
        _, s_families = stop_confluence
    else:
        s_families = list(dict.fromkeys(strategy_family(s) for s in scenario.stop_sources))
```

- [ ] **Step 4: Verify pyflakes is clean and existing tests still pass**

Run: `python -m pyflakes swingbot/core/market/explain.py`
Expected: no output (no warnings).

Run: `python scripts/dev/testrun.py file tests/market/test_levels_avwap.py`
Run: `python scripts/dev/testrun.py file tests/scanning/test_embeds_v3.py`
Expected: both PASS, same pass count as before this change (output text is
byte-identical — these locals were never read).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/explain.py
git commit -m "refactor(v41): remove two unused locals in explain.py

opp_word and s_count are computed and never read in build_explanation()
-- the stop-side message never names a count or a support/resistance
word the way the target-side message does. No output change. Found by
the v40 audit."
```

---

### Task 4: Drop no-op `f`-string prefixes in `growth.py` and `retrospective.py`

**Files:**
- Modify: `swingbot/core/edge/growth.py:122-124`
- Modify: `swingbot/core/tracking/retrospective.py:703,708,713`

**Interfaces:**
- Consumes: nothing new.
- Produces: no signature or output change — these are string literals with
  no `{}` placeholders, so the leading `f` was always a no-op.

- [ ] **Step 1: Confirm both files' no-op f-strings via pyflakes**

Run: `python -m pyflakes swingbot/core/edge/growth.py swingbot/core/tracking/retrospective.py`
Expected output includes six `F541 f-string is missing placeholders` hits:
three at `growth.py:122-124`, three at `retrospective.py:703,708,713`.

- [ ] **Step 2: Fix `growth.py`**

Change:

```python
        for label, e2, tpm2 in ((f"expectancy +0.05R", e + 0.05, tpm),
                                (f"frequency +20/mo", e, tpm + 20),
                                (f"both", e + 0.05, tpm + 20)):
```

to:

```python
        for label, e2, tpm2 in (("expectancy +0.05R", e + 0.05, tpm),
                                ("frequency +20/mo", e, tpm + 20),
                                ("both", e + 0.05, tpm + 20)):
```

- [ ] **Step 3: Fix `retrospective.py`**

Change each of the three lines:

```python
        lines += [f"  BY STRATEGY", hdr, sep]
```
```python
        lines += ["", f"  BY HORIZON", hdr, sep]
```
```python
        lines += ["", f"  BY CONFIDENCE LEVEL", hdr, sep]
```

to:

```python
        lines += ["  BY STRATEGY", hdr, sep]
```
```python
        lines += ["", "  BY HORIZON", hdr, sep]
```
```python
        lines += ["", "  BY CONFIDENCE LEVEL", hdr, sep]
```

- [ ] **Step 4: Verify pyflakes is clean and existing tests still pass**

Run: `python -m pyflakes swingbot/core/edge/growth.py swingbot/core/tracking/retrospective.py`
Expected: no `F541` hits remain.

Run: `python scripts/dev/testrun.py file tests/tracking/test_retrospective_v2.py`
Run: `python scripts/dev/testrun.py file tests/edge/test_edge_heat.py`
Expected: both PASS (output text is byte-identical to before).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/edge/growth.py swingbot/core/tracking/retrospective.py
git commit -m "style(v41): drop no-op f-string prefixes with no placeholders

Six f-strings across growth.py and retrospective.py had no {} in them
-- the f prefix did nothing. No output change. Found by the v40 audit."
```

---

### Task 5: Log the two silent bare excepts in `retrospective.py`

**Files:**
- Modify: `swingbot/core/tracking/retrospective.py:66-71` (`_load_history`), `:126-138` (`_to_berlin`)
- Test: `tests/tracking/test_retrospective_v2.py`

**Interfaces:**
- Consumes: `log = logging.getLogger("swing-bot.retrospective")` (already
  module-level in this file).
- Produces: no signature change. `_load_history() -> list[dict]` still
  returns `[]` on any failure; `_to_berlin(iso_str) -> dt.datetime | None`
  still returns `None` on any failure. Only the "silent" part changes —
  both now log, matching the file's dominant pattern (e.g. `_save_history`'s
  `except Exception: log.exception(...)`).

- [ ] **Step 1: Write the failing test**

Add to `tests/tracking/test_retrospective_v2.py`:

```python
def test_load_history_logs_on_corrupt_file(tmp_path, monkeypatch, caplog):
    from swingbot.core.tracking import retrospective as retro

    bad_path = tmp_path / "history.json"
    bad_path.write_text("{not valid json")
    monkeypatch.setattr(retro, "_HISTORY_PATH", str(bad_path))

    with caplog.at_level("WARNING", logger="swing-bot.retrospective"):
        result = retro._load_history()

    assert result == []
    assert any("history" in r.message.lower() for r in caplog.records)


def test_to_berlin_logs_on_unparseable_timestamp(caplog):
    from swingbot.core.tracking import retrospective as retro

    with caplog.at_level("WARNING", logger="swing-bot.retrospective"):
        result = retro._to_berlin("not-a-timestamp")

    assert result is None
    assert any("timestamp" in r.message.lower() or "berlin" in r.message.lower()
               for r in caplog.records)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/tracking/test_retrospective_v2.py::test_load_history_logs_on_corrupt_file tests/tracking/test_retrospective_v2.py::test_to_berlin_logs_on_unparseable_timestamp -v`
Expected: FAIL — `assert any(...)` fails on both since `caplog.records` is empty
(nothing is logged today).

- [ ] **Step 3: Add logging to `_load_history`**

Change:

```python
def _load_history() -> list[dict]:
    try:
        with open(_HISTORY_PATH) as f:
            return json.load(f)
    except Exception:
        return []
```

to:

```python
def _load_history() -> list[dict]:
    try:
        with open(_HISTORY_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except Exception:
        log.warning("retrospective: failed to load history from %s", _HISTORY_PATH, exc_info=True)
        return []
```

(splitting out `FileNotFoundError` keeps the expected first-run case silent
— matches the module's own "presumably caused it" framing elsewhere — while
a genuinely corrupt/unreadable file now logs.)

- [ ] **Step 4: Add logging to `_to_berlin`**

Change:

```python
def _to_berlin(iso_str: str) -> dt.datetime | None:
    if not iso_str:
        return None
    try:
        d = dt.datetime.fromisoformat(iso_str)
        if d.tzinfo is None:
            import datetime as _dt
            d = d.replace(tzinfo=_dt.timezone.utc)
        if _BERLIN_TZ:
            d = d.astimezone(_BERLIN_TZ)
        return d
    except Exception:
        return None
```

to:

```python
def _to_berlin(iso_str: str) -> dt.datetime | None:
    if not iso_str:
        return None
    try:
        d = dt.datetime.fromisoformat(iso_str)
        if d.tzinfo is None:
            import datetime as _dt
            d = d.replace(tzinfo=_dt.timezone.utc)
        if _BERLIN_TZ:
            d = d.astimezone(_BERLIN_TZ)
        return d
    except Exception:
        log.warning("retrospective: unparseable timestamp %r for Berlin conversion", iso_str, exc_info=True)
        return None
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/tracking/test_retrospective_v2.py -v`
Expected: PASS, all tests in the file.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/tracking/retrospective.py tests/tracking/test_retrospective_v2.py
git commit -m "fix(v41): log the two silent bare excepts in retrospective.py

_load_history (corrupt/unreadable file, not just missing) and
_to_berlin (unparseable timestamp) swallowed errors with no logging,
unlike this file's dominant log.exception-and-degrade pattern -- could
have been masking a real bug. Behavior unchanged (still returns []/None
on failure); only visibility changes. Found by the v40 audit."
```

---

### Task 6: Remove dead `import discord` and dead re-exports in `engine.py`

**Files:**
- Modify: `swingbot/core/scanning/engine.py:55` (delete), `:92-102` (edit)
- Test: `tests/scanning/test_engine_v2_plans.py` (add one structural test)

**Interfaces:**
- Consumes: nothing new.
- Produces: no signature change. `CONFIDENCE_COLORS`/`confidence_color`
  (the two re-exports that DO have external consumers via
  `scan_engine.CONFIDENCE_COLORS` in `admin/helpers.py` and
  `scan_engine.confidence_color`-equivalent in tests) are untouched — only
  `CONFIDENCE_EMOJI`/`CONFIDENCE_ANSI` (zero external consumers) and the
  unused `discord` import are removed.

- [ ] **Step 1: Write the failing test**

Add to `tests/scanning/test_engine_v2_plans.py`:

```python
def test_engine_has_no_discord_dependency():
    """docs/claude/architecture.md: core/ has no Discord dependency by
    design. engine.py had a stray, unused `import discord` -- guard
    against it coming back."""
    import inspect
    from swingbot.core.scanning import engine

    src = inspect.getsource(engine)
    assert "import discord" not in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/scanning/test_engine_v2_plans.py::test_engine_has_no_discord_dependency -v`
Expected: FAIL — `import discord` is still present.

- [ ] **Step 3: Delete the unused import**

In `swingbot/core/scanning/engine.py`, delete this line (and the blank line
that follows it, keeping one blank line between the stdlib imports and
`from swingbot import config`):

```python
import discord

```

- [ ] **Step 4: Remove the dead re-exports and fix the stale shim comment**

Change:

```python
# Several of these are unused HERE and re-exported on purpose: core/scan_engine.py
# is an `import *` shim over this module, and callers reach them through it
# (admin/helpers.py imports CONFIDENCE_COLORS, commands/trades.py uses
# scan_engine.regenerate_chart_for_trade). Check for importers before deleting one.
from .embeds import (  # noqa: F401
    CONFIDENCE_COLORS, CONFIDENCE_EMOJI, CONFIDENCE_ANSI,
    confidence_color, _build_requirement_checks, build_embed, build_simple_alert,
    plan_numbers_for_display,
    regenerate_chart_for_trade, build_closed_trade_embed, notify_closed_trades,
    build_near_close_embed, notify_near_close,
)
```

to:

```python
# Several of these are unused HERE and re-exported on purpose: callers reach
# them via `from swingbot.core.scanning import engine as scan_engine` --
# the live equivalent of the old core/scan_engine.py `import *` shim,
# removed 2026-08-15 by the v27 repo restructure (admin/helpers.py imports
# CONFIDENCE_COLORS, commands/trades.py uses
# scan_engine.regenerate_chart_for_trade). Check for importers before
# deleting one. CONFIDENCE_EMOJI/CONFIDENCE_ANSI were removed from this
# re-export list 2026-08-21 -- zero external consumers via scan_engine.*
# (they're still used directly inside embeds.py itself).
from .embeds import (  # noqa: F401
    CONFIDENCE_COLORS,
    confidence_color, _build_requirement_checks, build_embed, build_simple_alert,
    plan_numbers_for_display,
    regenerate_chart_for_trade, build_closed_trade_embed, notify_closed_trades,
    build_near_close_embed, notify_near_close,
)
```

- [ ] **Step 5: Verify no external consumer of the removed names, then run tests**

Run: `git grep -n "CONFIDENCE_EMOJI\|CONFIDENCE_ANSI"`
Expected: only hits inside `swingbot/core/scanning/embeds.py` (where they're
still defined and used directly) and this plan/audit doc — no
`scan_engine.CONFIDENCE_EMOJI`-style external reference.

Run: `python scripts/dev/testrun.py file tests/scanning/test_engine_v2_plans.py`
Expected: PASS, all tests in the file, including the new one.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/engine.py tests/scanning/test_engine_v2_plans.py
git commit -m "refactor(v41): remove dead import discord and dead re-exports in engine.py

import discord was unused and violated core/'s documented no-Discord-
dependency boundary. CONFIDENCE_EMOJI/CONFIDENCE_ANSI had zero external
consumers via scan_engine.* (unlike CONFIDENCE_COLORS/confidence_color,
which do and stay). Also fixes a stale comment still describing the
core/scan_engine.py shim removed 2026-08-15. Found by the v40 audit."
```

---

### Task 7: Add the missing disclaimer stamp in `analytics_charts.py`

**Files:**
- Modify: `swingbot/core/charts/analytics_charts.py:20-48`
- Test: `tests/charts/test_analytics_charts.py`

**Interfaces:**
- Consumes: `chart_style.DISCLAIMER_TEXT` (already exists, already used by
  the other three chart-save paths).
- Produces: no signature change — `_save(fig, out_dir, filename) -> str`
  still returns the same path; the saved PNG now includes the disclaimer
  text every other chart type already has.

Context: `render_equity_curve`/`render_calibration` (this module) are called
from `commands/stats.py` (`!stats`, `!calibration` Discord commands) — these
charts ARE Discord-posted, same audience as trade/decision/portfolio
charts, so the missing disclaimer here is drift, not an intentional
admin-only exemption (resolves the audit's "suspected" item).

- [ ] **Step 1: Write the failing test**

Add to `tests/charts/test_analytics_charts.py`:

```python
def test_save_stamps_disclaimer(tmp_path):
    """render_equity_curve/render_calibration/etc. are posted to Discord via
    commands/stats.py -- same disclaimer requirement as every other chart
    type. _save() was the one save path in this module missing it."""
    import matplotlib.pyplot as plt
    from swingbot.core.charts.analytics_charts import _save
    from swingbot.core.charts.chart_style import DISCLAIMER_TEXT

    fig, ax = plt.subplots()
    _save(fig, str(tmp_path), "test.png")
    assert any(t.get_text() == DISCLAIMER_TEXT for t in fig.texts)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/charts/test_analytics_charts.py::test_save_stamps_disclaimer -v`
Expected: FAIL — `fig.texts` is empty.

- [ ] **Step 3: Add `DISCLAIMER_TEXT` to the import and stamp it in `_save`**

Change:

```python
from .chart_style import (
    CHART_BG, CHIP_BG, DOWN_COLOR, GRID_COLOR, MUTED_TEXT_COLOR,
    SPINE_COLOR, TARGET_COLOR, TEXT_COLOR, UP_COLOR,
)
```

to:

```python
from .chart_style import (
    CHART_BG, CHIP_BG, DISCLAIMER_TEXT, DOWN_COLOR, GRID_COLOR, MUTED_TEXT_COLOR,
    SPINE_COLOR, TARGET_COLOR, TEXT_COLOR, UP_COLOR,
)
```

Change:

```python
def _save(fig, out_dir: str, filename: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, filename)
    try:
        fig.savefig(path, dpi=_DPI, bbox_inches="tight", facecolor=CHART_BG)
    finally:
        plt.close(fig)
    return path
```

to:

```python
def _save(fig, out_dir: str, filename: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, filename)
    fig.text(0.99, 0.01, DISCLAIMER_TEXT, color=MUTED_TEXT_COLOR, fontsize=6, ha="right")
    try:
        fig.savefig(path, dpi=_DPI, bbox_inches="tight", facecolor=CHART_BG)
    finally:
        plt.close(fig)
    return path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/charts/test_analytics_charts.py`
Expected: PASS, all tests in the file.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/charts/analytics_charts.py tests/charts/test_analytics_charts.py
git commit -m "fix(v41): stamp the disclaimer on analytics charts

render_equity_curve/render_calibration/etc. are posted to Discord via
!stats/!calibration -- same audience as every other chart type, all of
which already stamp DISCLAIMER_TEXT. This was the one save path
missing it, most likely drift rather than an intentional exemption.
Found by the v40 audit."
```

---

### Task 8: Guard `portfolio_charts.py._save` against a figure leak on `savefig` failure

**Files:**
- Modify: `swingbot/core/charts/portfolio_charts.py:20-26`
- Test: `tests/charts/test_portfolio_charts.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: no signature change — `_save(fig, out_dir, name) -> str`
  behaves identically on success; on a `savefig` failure, the figure is now
  guaranteed closed (was previously leaked, since `plt.close(fig)` ran
  unconditionally after `savefig`, never reached if `savefig` raised).

- [ ] **Step 1: Write the failing test**

Add to `tests/charts/test_portfolio_charts.py`:

```python
def test_save_closes_figure_even_if_savefig_raises(tmp_path, monkeypatch):
    """A savefig failure (disk full, bad path, encoder error) must not leak
    the matplotlib Figure in this long-running bot process."""
    import matplotlib.pyplot as plt
    from swingbot.core.charts.portfolio_charts import _save

    def _boom(*a, **kw):
        raise RuntimeError("disk full")

    fig, ax = plt.subplots()
    fignum = fig.number
    monkeypatch.setattr(fig, "savefig", _boom)

    with pytest.raises(RuntimeError):
        _save(fig, str(tmp_path), "test.png")

    assert fignum not in plt.get_fignums()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/charts/test_portfolio_charts.py::test_save_closes_figure_even_if_savefig_raises -v`
Expected: FAIL — `RuntimeError` propagates correctly, but
`fignum in plt.get_fignums()` is still True (the figure was never closed
because `plt.close(fig)` sat after the raising `fig.savefig(...)` call,
unreached).

- [ ] **Step 3: Wrap `savefig` in `try/finally`**

Change:

```python
def _save(fig, out_dir: str, name: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name)
    fig.text(0.99, 0.01, DISCLAIMER_TEXT, color=MUTED_TEXT_COLOR, fontsize=6, ha="right")
    fig.savefig(path, facecolor=CHART_BG, bbox_inches="tight")
    plt.close(fig)
    return path
```

to:

```python
def _save(fig, out_dir: str, name: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name)
    fig.text(0.99, 0.01, DISCLAIMER_TEXT, color=MUTED_TEXT_COLOR, fontsize=6, ha="right")
    try:
        fig.savefig(path, facecolor=CHART_BG, bbox_inches="tight")
    finally:
        plt.close(fig)
    return path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/charts/test_portfolio_charts.py`
Expected: PASS, all tests in the file (including the existing
`test_every_renderer_saves_through_the_disclaimer_helper` structural test,
which still holds — `fig.savefig(` still appears exactly once).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/charts/portfolio_charts.py tests/charts/test_portfolio_charts.py
git commit -m "fix(v41): guard portfolio_charts._save against a figure leak

plt.close(fig) ran unconditionally after fig.savefig(), so a savefig
failure (disk full, bad path, encoder error) leaked the Figure in this
long-running bot process. Found by the v40 audit."
```

---

### Task 9: Guard `decision_chart.py`'s save against a figure leak on `savefig` failure

**Files:**
- Modify: `swingbot/core/charts/decision_chart.py:139-143`
- Test: `tests/charts/test_decision_chart.py`

**Interfaces:**
- Consumes: `FakePlan`, `daily_df` fixture (already defined in the test
  file).
- Produces: no signature change — `render_decision_chart(...) -> str`
  behaves identically on success; on a `savefig` failure, the figure is now
  guaranteed closed.

- [ ] **Step 1: Write the failing test**

Add to `tests/charts/test_decision_chart.py`:

```python
def test_savefig_failure_still_closes_figure(tmp_path, daily_df, monkeypatch):
    """A savefig failure must not leak the matplotlib Figure -- same class
    of bug as portfolio_charts.py's, fixed in the same audit pass."""
    import matplotlib.figure
    import matplotlib.pyplot as plt
    from swingbot.core.charts.decision_chart import render_decision_chart

    def _boom(self, *a, **kw):
        raise RuntimeError("disk full")

    monkeypatch.setattr(matplotlib.figure.Figure, "savefig", _boom)
    open_before = len(plt.get_fignums())

    with pytest.raises(RuntimeError):
        render_decision_chart("TEST", daily_df, FakePlan(), {}, str(tmp_path))

    assert len(plt.get_fignums()) == open_before
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/charts/test_decision_chart.py::test_savefig_failure_still_closes_figure -v`
Expected: FAIL — `RuntimeError` propagates, but `plt.get_fignums()` grew by
one (the figure this call created was never closed).

- [ ] **Step 3: Wrap `savefig` in `try/finally`**

Change:

```python
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{symbol}_decision.png")
    fig.savefig(path, facecolor=CHART_BG, bbox_inches="tight")
    plt.close(fig)
    return path
```

to:

```python
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{symbol}_decision.png")
    try:
        fig.savefig(path, facecolor=CHART_BG, bbox_inches="tight")
    finally:
        plt.close(fig)
    return path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/charts/test_decision_chart.py`
Expected: PASS, all tests in the file.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/charts/decision_chart.py tests/charts/test_decision_chart.py
git commit -m "fix(v41): guard decision_chart's savefig against a figure leak

Same class of bug as portfolio_charts.py's _save(): plt.close(fig) ran
unconditionally after fig.savefig(), leaking the Figure on a savefig
failure. Found by the v40 audit. (trade_chart.py already had this
guard correctly -- audit was wrong to flag it, no change there.)"
```

---

### Task 10: Fix `_query_closed_trades()` doc/comment drift

**Files:**
- Modify: `docs/claude/known-traps.md` (Trade History section, ~line 95)
- Modify: `swingbot/admin/api_v1/__init__.py:75`

**Interfaces:** None — documentation and a comment only, zero code
behavior change.

- [ ] **Step 1: Confirm the real symbol name**

Run: `git grep -n "^def query_closed_trades"`
Expected: `swingbot/admin/dashboard.py:272:def query_closed_trades(...):` —
no leading underscore. Confirm no `_query_closed_trades` (with underscore)
exists anywhere: `git grep -n "_query_closed_trades"` should list only the
two doc/comment sites being fixed here (plus this plan and the audit doc,
which aren't touched by this task).

- [ ] **Step 2: Fix the comment in `admin/api_v1/__init__.py`**

Change:

```python
    `total` is the count AFTER filtering but BEFORE slicing -- the contract
    `_query_closed_trades()` already implements, generalised rather than
    reinvented. Passing `len(items)` here silently produces a one-page
    result set, so callers must pass the pre-slice count.
```

to:

```python
    `total` is the count AFTER filtering but BEFORE slicing -- the contract
    `query_closed_trades()` already implements, generalised rather than
    reinvented. Passing `len(items)` here silently produces a one-page
    result set, so callers must pass the pre-slice count.
```

- [ ] **Step 3: Fix `docs/claude/known-traps.md`**

Change:

```
  `_query_closed_trades()`, which survived the Jinja deletion precisely
```

to:

```
  `query_closed_trades()`, which survived the Jinja deletion precisely
```

- [ ] **Step 4: Verify**

Run: `git grep -n "_query_closed_trades"`
Expected: no matches (the audit doc and this plan file are not part of the
working tree search scope for correctness — they're historical records of
the finding, not live documentation, and are left as-is).

- [ ] **Step 5: Commit**

```bash
git add docs/claude/known-traps.md swingbot/admin/api_v1/__init__.py
git commit -m "docs(v41): fix _query_closed_trades() -> query_closed_trades() drift

Both known-traps.md and a code comment cited a symbol name with a
leading underscore that never existed -- the real function is
query_closed_trades() in admin/dashboard.py:272. Found by the v40
audit."
```

---

### Task 11: Fix the NUL-byte Map-key separator in `analytics.ts`

**Files:**
- Modify: `frontend/src/app/workspaces/analytics/analytics.ts` (3 sites:
  one `Map.set`, two `Map.get`, all building the same composite key)

**Interfaces:** None — internal Map-key format only, not part of any public
API or persisted data; changing the separator is invisible to callers of
the component.

This file contains three literal NUL bytes (`\x00`) used as a Map-key
separator. This is why it's a NUL byte and not a normal edit: ripgrep/
`git grep`/this repo's own `Grep` tool treat any file containing a NUL byte
as binary and silently skip its contents in text search, so the `Edit` tool
(which matches on literal string content) cannot reliably target a NUL byte
either. Do this fix with a small Python script instead.

- [ ] **Step 1: Confirm the three occurrences and their exact byte offset**

Run:

```bash
python -c "
path = 'frontend/src/app/workspaces/analytics/analytics.ts'
with open(path, 'rb') as f:
    data = f.read()
print('NUL byte count:', data.count(b'\x00'))
"
```

Expected: `NUL byte count: 3`

- [ ] **Step 2: Replace the NUL byte with `|` everywhere in the file**

Run:

```bash
python -c "
path = 'frontend/src/app/workspaces/analytics/analytics.ts'
with open(path, 'rb') as f:
    data = f.read()
assert data.count(b'\x00') == 3, f'expected 3 NUL bytes, found {data.count(chr(0).encode())}'
data = data.replace(b'\x00', b'|')
with open(path, 'wb') as f:
    f.write(data)
"
```

(`|` is safe here: the two values joined are a strategy display name and a
horizon key like `4w`/`3m`, neither of which contains `|` — checked via
`git grep -n "strategy:" swingbot/core/market/strategy_types.py` and the
`HORIZONS` definition, both plain alphanumeric/space names.)

- [ ] **Step 3: Verify the file is now readable by grep tooling and the fix is complete**

Run: `git grep -n "cell.strategy" frontend/src/app/workspaces/analytics/analytics.ts`
Expected: this now RETURNS matches (before this fix, the NUL byte made
`git grep` treat the whole file as binary and skip it silently — this is
the direct proof the landmine is gone).

Run:

```bash
python -c "
path = 'frontend/src/app/workspaces/analytics/analytics.ts'
with open(path, 'rb') as f:
    data = f.read()
assert data.count(b'\x00') == 0
assert data.count(b'|') >= 3
print('OK')
"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/workspaces/analytics/analytics.ts
git commit -m "fix(v41): replace NUL-byte Map-key separator in analytics.ts

A literal NUL byte joining strategy+horizon as a Map key made ripgrep/
git grep/this repo's Grep tool silently treat the whole file as binary,
hiding its contents (including createClientPage's real usages) from
grep-based verification -- a landmine for any future dead-code sweep
that trusts grep on this file. Replaced with '|'. Found by the v40 audit."
```

---

### Task 12: Delete the completed one-shot `migrate_market_data.py` script

**Files:**
- Delete: `scripts/data/migrate_market_data.py`

**Interfaces:** None — no other file imports or invokes this script (only
two historical plan/spec docs under `docs/superpowers/*/implemented/`
reference it, describing the v27 restructure that already ran it; neither
is live documentation).

- [ ] **Step 1: Confirm there is no live caller**

Run: `git grep -n "migrate_market_data"`
Expected: only `docs/superpowers/specs/implemented/2026-08-15-v26-repo-restructure-design.md`
and `docs/superpowers/plans/implemented/2026-08-15-v27-repo-restructure.md`
— both `implemented/`, both historical records of the migration that
already ran, neither a live caller.

- [ ] **Step 2: Delete the file**

```bash
git rm scripts/data/migrate_market_data.py
```

- [ ] **Step 3: Verify nothing breaks**

Run: `python scripts/dev/testrun.py fast`
Expected: PASS, same counts as before this task (no test imports this
script — it's a standalone CLI tool, confirmed in Step 1).

- [ ] **Step 4: Commit**

```bash
git commit -m "chore(v41): delete completed one-shot migrate_market_data.py

Its job (v27's market_data/ layout change, per-ticker -> per-timeframe)
completed 2026-08-15; market_data/ is gitignored, so a fresh checkout
can never hit the old layout this script converts from. No live
caller. Found by the v40 audit."
```

---

### Task 14: Remove the dead `from swingbot import config` import in `versions.py`

**Files:**
- Modify: `swingbot/admin/api_v1/versions.py:31`
- Test: `tests/admin/test_api_v1_versions.py` (existing — no new test needed, this changes zero output)

**Interfaces:**
- Consumes: nothing new.
- Produces: no signature change — `config` is never referenced anywhere
  else in this file, so removing the import cannot change output. (Found
  by a pyflakes sweep during v41's own brainstorming pass, 2026-08-22 —
  same audit lineage as the rest of this plan, one task late.)

- [ ] **Step 1: Confirm the import is genuinely unused**

Run: `python -m pyflakes swingbot/admin/api_v1/versions.py`
Expected output:
```
swingbot/admin/api_v1/versions.py:31:1: 'swingbot.config' imported but unused
```

Run: `git grep -n "config\." swingbot/admin/api_v1/versions.py`
Expected: no output — `config` is not referenced anywhere in the file.

- [ ] **Step 2: Remove the import**

Delete this line:

```python
from swingbot import config
```

- [ ] **Step 3: Verify pyflakes is clean and existing tests still pass**

Run: `python -m pyflakes swingbot/admin/api_v1/versions.py`
Expected: no output.

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_versions.py`
Expected: PASS, same pass count as before this change.

- [ ] **Step 4: Commit**

```bash
git add swingbot/admin/api_v1/versions.py
git commit -m "chore(v41): remove dead swingbot.config import in versions.py

config was imported and never referenced anywhere in the file. No
output change. Found by a pyflakes sweep during v41's own
brainstorming pass."
```

---

### Task 15: Fix the no-op `f`-string prefix in `commands/history.py`

**Files:**
- Modify: `swingbot/commands/history.py:245`
- Test: `tests/commands/test_history_format.py` (new — `_format_generated_plan`
  has no existing test coverage at all)

**Interfaces:**
- Consumes: nothing new.
- Produces: no signature or output change — this is a string literal with
  no `{}` placeholders, so the leading `f` was always a no-op. Same species
  as Task 4's fix in `growth.py`/`retrospective.py`, missed by the v40
  audit because `commands/*.py` was only grep-swept, never read line by
  line (see the audit's own "Coverage gaps" section).

- [ ] **Step 1: Write the failing test**

Create `tests/commands/test_history_format.py` (and `tests/commands/__init__.py`
if the directory doesn't already have one):

```python
from types import SimpleNamespace

from swingbot.commands.history import _format_generated_plan


def test_format_generated_plan_timeout_line_text():
    """The timeout line's f-string has no {} placeholders -- the f prefix
    was a no-op. Pin the literal text so a future edit can't silently
    reintroduce a missing placeholder either."""
    trade = SimpleNamespace(direction="bullish", outcome="timeout",
                             r_multiple=None, exit_date=None)
    line = _format_generated_plan("RSI", "4w", trade, "$")
    assert "→ ⏳ timed out (no exit within max hold)" in line
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/commands/test_history_format.py -v`
Expected: this actually PASSES already (the `f` prefix is a no-op, so
current output already matches) — the point of this step is confirming
the test is well-formed and reaches the target line, not a red/green
cycle. Run `python -m pyflakes swingbot/commands/history.py` alongside it
and confirm it reports the `F541` hit at line 245.

- [ ] **Step 3: Fix `history.py`**

Change:

```python
        exit_str = f"→ ⏳ timed out (no exit within max hold)"
```

to:

```python
        exit_str = "→ ⏳ timed out (no exit within max hold)"
```

- [ ] **Step 4: Verify pyflakes is clean and the test still passes**

Run: `python -m pyflakes swingbot/commands/history.py`
Expected: no `F541` hit remains.

Run: `python -m pytest tests/commands/test_history_format.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/commands/history.py tests/commands/test_history_format.py
git commit -m "style(v41): drop no-op f-string prefix in history.py

The timeout line's f-string had no {} in it -- the f prefix did
nothing. Same species as Task 4's growth.py/retrospective.py fix;
missed there because commands/*.py was only grep-swept by the v40
audit, never read line by line. No output change. Adds the first unit
test for _format_generated_plan, which had none."
```

---

### Task 16: Remove the dead `title` local in `trade_chart.py`

**Files:**
- Modify: `swingbot/core/charts/trade_chart.py:426-431`
- Test: `tests/charts/test_trade_chart_v2.py` (existing — no new test needed, this changes zero output)

**Interfaces:**
- Consumes: nothing new.
- Produces: no signature change. `title` is built and never passed
  anywhere — the mplfinance `title=` kwarg was deliberately dropped in
  favor of a top-left legend block (see the comment at the `_plot_kwargs`
  dict two lines below, already in the file: "No `title=`: the centered
  mplfinance title is replaced by the top-left legend block"). The string
  build was never removed when that happened.

- [ ] **Step 1: Confirm the variable is read nowhere in the function**

Run: `python -m pyflakes swingbot/core/charts/trade_chart.py`
Expected output includes:
```
swingbot/core/charts/trade_chart.py:428:5 local variable 'title' is assigned to but never used
```

Run: `git grep -n "\btitle\b" swingbot/core/charts/trade_chart.py`
Expected: the only reference to the bare `title` identifier is its own
assignment; every other hit is the substring inside a comment or a
differently-named variable (e.g. "chart title", "Panel title").

- [ ] **Step 2: Remove the dead block**

Delete these lines:

```python

    # Single-line title (first row only — stats are drawn separately with color)
    title = (
        f"{ticker} — {strategy} ({horizon_label}) — {direction_label}"
        f"  [{currency_symbol.strip()}, {window_note}]"
    )
```

(leaving exactly one blank line between the MACD stat-token block above and
the "Volume now overlays..." comment below — do not leave two).

- [ ] **Step 3: Verify pyflakes is clean and existing tests still pass**

Run: `python -m pyflakes swingbot/core/charts/trade_chart.py`
Expected: no `title`-related warning remains.

Run: `python scripts/dev/testrun.py file tests/charts/test_trade_chart_v2.py`
Expected: PASS, same pass count as before this change (output is
byte-identical — this local was never read).

- [ ] **Step 4: Commit**

```bash
git add swingbot/core/charts/trade_chart.py
git commit -m "refactor(v41): remove dead title local in trade_chart.py

title was computed and never used -- the mplfinance title= kwarg it
was built for was deliberately dropped in favor of a legend block, and
the string-building code was left behind. No output change. Found by
a pyflakes sweep during v41's own brainstorming pass."
```

---

### Task 17: Remove the unused `legend` local in `analytics_charts.py`

**Files:**
- Modify: `swingbot/core/charts/analytics_charts.py:86`
- Test: `tests/charts/test_analytics_charts.py` (existing — no new test needed, this changes zero output)
- **Sequencing:** must run after Task 7 (both edit this file — Task 7 touches
  `_save`, lines 20-48; this task touches `render_equity_curve`, line 86;
  disjoint ranges, but one file, one working tree).

**Interfaces:**
- Consumes: nothing new.
- Produces: no signature change. `ax.legend(...)`'s return value is
  assigned to `legend` and never read — the call's side effect (drawing
  the legend on the axes) still happens; only the unused assignment goes.

- [ ] **Step 1: Confirm the variable is read nowhere in the function**

Run: `python -m pyflakes swingbot/core/charts/analytics_charts.py`
Expected output includes:
```
swingbot/core/charts/analytics_charts.py:86:5: local variable 'legend' is assigned to but never used
```

- [ ] **Step 2: Drop the unused assignment, keep the call**

Change:

```python
    legend = ax.legend(loc="upper left", fontsize=8, framealpha=0.9, facecolor=CHIP_BG, edgecolor=SPINE_COLOR, labelcolor=TEXT_COLOR)
```

to:

```python
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9, facecolor=CHIP_BG, edgecolor=SPINE_COLOR, labelcolor=TEXT_COLOR)
```

- [ ] **Step 3: Verify pyflakes is clean and existing tests still pass**

Run: `python -m pyflakes swingbot/core/charts/analytics_charts.py`
Expected: no `legend`-related warning remains.

Run: `python scripts/dev/testrun.py file tests/charts/test_analytics_charts.py`
Expected: PASS, same pass count as before this change (the rendered
figure is byte-identical — only the discarded return value goes).

- [ ] **Step 4: Commit**

```bash
git add swingbot/core/charts/analytics_charts.py
git commit -m "refactor(v41): remove unused legend local in analytics_charts.py

ax.legend()'s return value was assigned and never read; the call's
side effect (drawing the legend) is unaffected. No output change.
Found by a pyflakes sweep during v41's own brainstorming pass."
```

---

### Task 18: Bump `VERSION.json` (bot patch) and regenerate `version_history.json`

**Files:**
- Modify: `VERSION.json`
- Modify: `swingbot/admin/version_history.json` (regenerated, not hand-edited)

**Interfaces:** None.

This is the LAST task. Do not start it until Tasks 1-17 are all committed
and `python scripts/dev/testrun.py full` shows `0 failed, 0 xfailed`.

- [ ] **Step 1: Confirm the full suite is green**

Run: `python scripts/dev/testrun.py full`
Expected: `0 failed, 0 xfailed` (skipped count and total pass count may
differ from any baseline recorded elsewhere in the docs — what matters
here is zero failures).

- [ ] **Step 2: Bump the bot patch version**

Read the current `bot` value from `VERSION.json` (this plan does not
hardcode it — it depends on what v36 landed at). Increment its patch
component by 1 (e.g. `1.4.0` -> `1.4.1`), and update `bot_updated` to the
current date/time in the file's existing `"YYYY-MM-DD HH-MM-SS"` format.
Leave `ui`/`ui_updated` untouched — this plan makes no frontend-visible UI
change beyond Task 11's internal Map-key fix, which is not itself a UI
version-worthy change per `docs/claude/working-conventions.md`'s
observable-difference test (Task 11 fixes a grep-tooling landmine, not
user-visible behavior).

- [ ] **Step 3: Commit the version bump alone**

```bash
git add VERSION.json
git commit -m "chore(v41): bump bot patch version for the repo-cleanup fixes"
```

- [ ] **Step 4: Regenerate `version_history.json` AFTER the bump commit lands**

Run: `python scripts/dev/build_version_matrix.py`

- [ ] **Step 5: Verify the regeneration is correct**

Run: `python -m pytest tests/scripts/test_build_version_matrix.py -v`
Expected: PASS, all tests.

Confirm directly (not just via the test) that the new version pair is
present and its commit is real:

```bash
python -c "
import json
h = json.load(open('swingbot/admin/version_history.json'))
print(h)
"
```

Expected: the new `bot` version from Step 2 appears, paired with the
current `ui` version, with a real (non-'uncommitted') commit hash.

- [ ] **Step 6: Commit the regenerated history**

```bash
git add swingbot/admin/version_history.json
git commit -m "chore(v41): regenerate version_history.json after the patch bump"
```

## Self-Review Notes

- **Spec coverage:** every task traces to a specific item in
  `docs/superpowers/results/2026-08-21-repo-cleanup-audit.md`; the
  "Not in this plan" section accounts for every audit item this plan does
  NOT act on, with a reason each.
- **Placeholder scan:** no TBD/TODO; every step has real code, real file
  paths, real line numbers verified against `main` @ `5235fd4`.
- **Type/signature consistency:** no task changes any public function
  signature — verified per-task in each "Interfaces" block.
- **Correction folded in during planning, not left for an implementer to
  discover:** the audit's trade_chart.py leak claim was independently
  verified (via `ast`) to be incorrect before this plan was written — no
  task references it as broken.

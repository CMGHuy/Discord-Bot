# Extended-hours exit check — design

**Version:** ui 1.11.0 · bot 1.5.2
**Bump:** bot minor (1.5.x → 1.6.0) · ui none
**Edge:** none (integrity)

The extended-hours check does incidentally cap the slippage a stop-loss can
run before the bot reacts, which should raise realised expectancy relative to
today's overnight blackout. **No measurement backs that and none is claimed
here** — this document ships a correctness/risk fix, and the `Edge:` line
says so rather than borrowing the language of a profit improvement it has not
demonstrated, the same posture `v64-live-exit-parity` took for the RTH gate
this document extends.

---

## 1. The problem

`PlanManager.poll()` (`swingbot/core/planning/plan_manager.py:140-142`) returns
`[]` immediately whenever `config.INTRADAY_RTH_ONLY` is true (default) and
`is_regular_session(now)` is false. `is_regular_session` is Mon–Fri
09:30–16:00 ET only (`swingbot/core/market/session.py:23-28`). Every open
plan is stop/target-monitored **exclusively** inside that 6.5-hour window;
the other ~17.5 hours a day, and all of Saturday/Sunday, no plan transition
of any kind can fire — not a stop-loss, not a target, nothing.

Since `PLAN_ENGINE_V2=on` in production, every trade is plan-linked, and the
legacy tick-based fallback (`TradeLog.close_if_live_price_hit`) explicitly
excludes plan-linked trades (`performance.py:1126-1128`) precisely because a
v2 plan's real stop/target moves after TP1 and that function only ever sees
the frozen original levels. So a plan-linked trade whose stop is breached
outside RTH has **no automatic path to close** until the next regular
session's first poll — and by then, price has had the whole gap to run
further.

### 1.1 Confirmed production incident

`data/trades.json` on the Hetzner production bot, checked 2026-09-03:

| | |
|---|---|
| Ticker / direction | DDOG, bearish |
| Plan opened | 2026-09-02 13:46 ET |
| Entry / stop | 209.85 / 214.25 |
| User closed manually | 2026-09-03 04:48 ET (premarket, `close_reason: "manual (plan close, admin UI)"`) |
| Exit price | **223.30** — 4.2% *past* the 214.25 stop |

Two earlier manual closes in the same file (SOFI 2026-09-01 22:05 ET, DDOG
2026-09-01 22:05 ET) show the identical pattern: both land at after-hours
timestamps, both plan-linked. This is not a one-off — it is the bot's normal
behavior whenever a stop or target is breached outside 09:30–16:00 ET, which
for a book of multi-day swing trades held overnight by design (`HORIZONS`
span 2 weeks to 9 months) is a routine occurrence, not an edge case.

### 1.2 Why the RTH gate exists, and why this document does not remove it

`v64-live-exit-parity` (`docs/superpowers/specs/implemented/2026-08-28-v64-live-exit-parity-design.md`,
§1.2, "Divergence B") added `INTRADAY_RTH_ONLY` specifically because
`get_current_price` fetches premarket/after-hours quotes (`prepost=True`),
and *a single thin extended-hours print previously armed break-even
permanently or closed a position outright* — the backtest reads regular-hours
daily bars only and cannot see or score any of this, so extended-hours prints
silently diverged live behavior from the validated backtest. Simply widening
`is_regular_session` or flipping `INTRADAY_RTH_ONLY` off would reopen exactly
that bug. Any fix here has to add overnight coverage **without** resurrecting
Divergence B.

---

## 2. Goal

When a plan's governing stop-loss or final remaining target is breached
outside regular trading hours but outside a narrow overnight quiet window
(23:00–08:00 ET, and all of Saturday/Sunday), close it as soon as the breach
is confirmed — not at the next regular session. During the quiet window
itself, monitoring stays fully off, matching today's behavior (and the
user's own request: closures happen "the moment the market opens" out of the
quiet window, not continuously through the dead of night).

---

## 3. Non-goals

- **Not full 24-hour lifecycle parity.** Break-even arming, TP1
  partial-banking (when a `tp2` remains), the chandelier trailing-stop
  ratchet, and pyramiding all stay exactly where `v64` put them: regular
  hours only. Extended hours gets exactly one capability — closing a plan
  that has unambiguously finished (stop hit, or its last remaining target
  hit) — and nothing else, to keep this change's blast radius to the one
  failure mode in §1.1.
- **Not touching `INTRADAY_RTH_ONLY` or `is_regular_session`.** The existing
  RTH-gated state machine (`_step_active`/`_step_partial`, called from the
  `is_regular_session` branch of `poll()`) is unchanged, byte for byte. This
  document adds a second, narrower branch alongside it.
- **Not wiring `check_bar()`.** Still dead code, per its own
  `known-traps.md` entry ("wiring it would create a second authority for
  `plans.json`"). The new branch lives inside `PlanManager.poll()`, the one
  existing authority, not as a parallel consumer.
- **Not re-measuring the registry or claiming an expectancy number.** Same
  posture as `v64` §1: this closes a risk/correctness gap, it does not
  claim a validated edge.
- **Not a holiday/half-day calendar.** Same accepted limitation `v64` §4.1
  already states for `is_regular_session`: a market holiday's stale last
  price is idempotent against this check the same way it is against the RTH
  one, so the gap is benign and out of scope here too.

---

## 4. Design

### 4.1 Three-way gate in `PlanManager.poll()`

Replace the current two-way gate (`swingbot/core/planning/plan_manager.py:140-142`)
with:

```python
def poll(self, now=None) -> list[PlanEvent]:
    # INTRADAY_RTH_ONLY=false is the documented pre-v64 escape hatch --
    # full 24/7 _step() every tick, no quiet-hours gate either. Untouched.
    if config.INTRADAY_RTH_ONLY:
        if is_quiet_hours(now):
            return []
        regular = is_regular_session(now)
        if not regular and not config.EXTENDED_HOURS_EXIT_CHECK:
            return []
    else:
        regular = True    # always take the full-_step branch below
    self.store.reload()
    if self.trade_log is not None:
        self.trade_log.reload()
    events: list[PlanEvent] = []
    for plan in self.store.open_plans():
        try:
            price = float(self.price_fn(plan.ticker))
        except Exception as exc:
            log.debug("poll: price fetch failed for %s: %s", plan.ticker, exc)
            continue
        if not price or price <= 0:
            continue
        self.store.reload()
        try:
            new_events = self._step(plan, price, now) if regular \
                else self._step_extended(plan, price, now)
        except Exception:
            log.warning("poll: step failed for plan %s", plan.plan_id, exc_info=True)
            continue
        self._last_seen[plan.plan_id] = (session_date(now), price)
        for event in new_events:
            self._on_event(plan, event)
        events.extend(new_events)
    return events
```

`_step` (today's full state machine) still runs exactly when it runs today —
during RTH, or always when `INTRADAY_RTH_ONLY` is off, unchanged. The new
`_step_extended` branch only runs when the RTH gate is on, the clock is
outside RTH, **and** outside quiet hours. `EXTENDED_HOURS_EXIT_CHECK=false`
collapses this back to today's exact two-way behavior; `INTRADAY_RTH_ONLY=false`
bypasses this document's gate entirely, exactly as it did before — the
quiet-hours window only ever applies on top of the RTH gate, never
independent of it.

### 4.2 `is_quiet_hours`

New function in `swingbot/core/market/session.py`, same shape as
`is_regular_session`:

```python
def is_quiet_hours(now: dt.datetime | None = None) -> bool:
    """True outside config.QUIET_HOURS_END_ET..QUIET_HOURS_START_ET ET, and
    for all of Saturday/Sunday -- the window the extended-hours exit check
    (v70) never runs in, matching a market that is fully shut all weekend."""
    et = now_et(now)
    if et.weekday() >= 5:
        return True
    start = dt.time(config.QUIET_HOURS_START_ET, 0)
    end = dt.time(config.QUIET_HOURS_END_ET, 0)
    t = et.time()
    return t >= start or t < end
```

Reads `config` directly (a new top-level `from swingbot import config` in
`session.py`, which currently has no dependency on `config` at all — safe:
`config.py` imports only stdlib and `python-dotenv`, nothing from
`core/market/`) rather than taking the bounds as parameters. The two config
fields are the only supported way to change the window, matching how
`plan_manager.py` already reads `config.INTRADAY_RTH_ONLY` directly rather
than threading it through as an argument.

### 4.3 `_step_extended` — terminal exits only

```python
def _step_extended(self, plan: TradePlanV2, price: float, now=None) -> list[PlanEvent]:
    if plan.status == PlanStatus.ACTIVE:
        candidate = self._extended_candidate_active(plan, price)
    elif plan.status == PlanStatus.PARTIAL:
        candidate = self._extended_candidate_partial(plan, price)
    else:
        candidate = None    # PENDING (and any other status): no extended-hours action
    key = plan.plan_id
    if candidate is None:
        self._eh_breach_streak.pop(key, None)
        return []
    streak = self._eh_breach_streak.get(key, 0) + 1
    if streak < config.EXTENDED_HOURS_DEBOUNCE_TICKS:
        self._eh_breach_streak[key] = streak
        return []
    self._eh_breach_streak.pop(key, None)
    return candidate(price)   # closures over plan/risk/sign; fills at `price`
```

`_extended_candidate_active` mirrors `_step_active`'s stop/tp1 comparisons
(`stop, _ = self._active_stop(plan, now)`; `hit_stop = price <= stop if
is_bull else price >= stop`) but returns a **callable** that performs the
close (reusing the exact `reason`/leg/`record_transition` logic already in
`_step_active`'s stop branch) rather than performing it inline — this keeps
the debounce check in one place instead of duplicated per branch. TP1 only
becomes a candidate when `plan.tp2 is None` (no second leg to run); when a
`tp2` exists, reaching TP1 during extended hours returns `None` — inert,
exactly as §3 requires.

`_extended_candidate_partial` mirrors `_step_partial`'s stop/tp2 comparisons
and reuses `_close_runner` the same way.

Both candidates fill at `price` — the price observed on the confirming tick,
never a nominal level — matching `trade_monitor`'s and `performance.py`'s
existing "never record a better fill than what was actually seen" convention.

### 4.4 Debounce state

```python
self._eh_breach_streak: dict[str, int] = {}   # plan_id -> consecutive extended-hours breach ticks
```

Initialized in `__init__` alongside `self._last_seen`. In-memory only, same
reasoning `v64` gave `_last_seen`: persisting a debounce counter to
`plans.json` would turn every 60s extended-hours poll into a disk write where
today only a transition does. A bot restart empties the map — the first
extended-hours tick after a restart always needs a fresh confirming tick
before it can close anything, the conservative direction.

A tick where the breach condition does **not** hold pops the plan's entry
entirely (not decrement) — a single reverting print fully resets the count
rather than leaving a partial streak that a later, unrelated breach could
complete early.

### 4.5 New config fields

Added to the `"Plan Engine v2"` group in `swingbot/config.py`, next to
`INTRADAY_RTH_ONLY`:

```python
Field("EXTENDED_HOURS_EXIT_CHECK", "EXTENDED_HOURS_EXIT_CHECK", "Plan Engine v2",
      "Close on stop/target hits during premarket and after-hours", type="checkbox",
      default="true",
      help="Outside regular hours but outside the quiet window below, check open plans "
           "for a confirmed stop-loss or final-target hit and close immediately -- no "
           "break-even arming, TP1 partial-banking or trailing-stop updates outside "
           "regular hours, only a terminal close. Set false to reproduce pre-v70 "
           "behaviour (fully dark outside 09:30-16:00 ET)."),
Field("QUIET_HOURS_START_ET", "QUIET_HOURS_START_ET", "Plan Engine v2",
      "Quiet hours start (ET, 24h)", type="number", default="23", min=0, max=23, step=1,
      help="No plan monitoring at all from this hour (America/New_York) through "
           "QUIET_HOURS_END_ET, and none at all on Saturday/Sunday."),
Field("QUIET_HOURS_END_ET", "QUIET_HOURS_END_ET", "Plan Engine v2",
      "Quiet hours end (ET, 24h)", type="number", default="8", min=0, max=23, step=1,
      help="Extended-hours exit checks resume at this hour (America/New_York)."),
Field("EXTENDED_HOURS_DEBOUNCE_TICKS", "EXTENDED_HOURS_DEBOUNCE_TICKS", "Plan Engine v2",
      "Extended-hours confirmation ticks", type="number", default="2", min=1, max=5, step=1,
      help="Consecutive 60s extended-hours polls that must confirm a stop/target breach "
           "before closing -- guards against a single thin premarket/after-hours print "
           "(see v64's Divergence B) triggering a close a liquid market never would have."),
```

### 4.6 Notifications and error handling

Unchanged. An extended-hours close produces the same `PlanEvent(...,
"closed", ...)` shape as any RTH close, goes through the same `_on_event` →
`trade_log.close_plan_trade` → `notify_closed_trades` path
(`swingbot/commands/scanning/loops.py`'s `trade_monitor`), and posts the same
Discord embed. `trade_monitor`'s existing outer `except Exception:
log.warning(...); continue` per ticker, and `poll()`'s own per-plan
`try/except` around `_step`/`_step_extended`, already isolate one plan's or
one ticker's failure — no new error handling is needed.

---

## 5. Verification

Unit tests only, injected clock, `FakePriceFeed` — same style as the
existing `tests/planning/test_plan_manager_*.py` suite. New file:
`tests/planning/test_plan_manager_extended_hours.py`.

1. `is_quiet_hours` at each boundary: 22:59, 23:00, 02:00, 07:59, 08:00 ET on
   a weekday, and every hour checked on Saturday and Sunday.
2. A single extended-hours tick past the stop produces no event; the same
   tick immediately back on the safe side resets the streak to absent (not
   decremented).
3. Two consecutive extended-hours ticks past the stop produce exactly one
   `closed` event on the second tick, `exit_price` equal to the second
   tick's price, correct `reason` for ACTIVE (`loss`) and PARTIAL
   (`tp1_runner_be`/`tp1_runner_trail`/`tp1_runner_tp2`).
4. An ACTIVE plan with `tp2` set: reaching `tp1` during extended hours, any
   number of confirming ticks, produces no event and no state change.
5. An ACTIVE plan with no `tp2`: reaching `tp1`, debounce-confirmed,
   produces a `closed` event with `reason == "win"`.
6. A PENDING plan never produces `filled`/`cancelled_*` from an extended-hours
   tick regardless of price or tick count.
7. Regression: with the clock inside regular hours, `poll()`'s behavior
   (break-even arm, TP1 partial, trailing) is byte-for-byte what the existing
   `test_plan_manager_active.py`/`_partial.py`/`_be_session.py`/
   `_runner_session.py` suites already assert — this PR changes none of it.
8. `EXTENDED_HOURS_EXIT_CHECK=false` reproduces the pre-v70 two-way gate:
   `poll()` returns `[]` for every extended-hours tick regardless of price.
9. `EXTENDED_HOURS_DEBOUNCE_TICKS=1` fires a close on the very first
   extended-hours tick (confirms the count is read from config, not
   hardcoded).

No backtest run: nothing here changes a threshold, a frozen constant, or the
exit simulator; `_step_extended` has no simulator counterpart to match
because the backtest's daily bars never modeled premarket/after-hours prices
in the first place.

---

## Parallelisation

- **Group 1 (parallel):** `is_quiet_hours` in `session.py`, and the three new
  `config.py` `Field()` entries — different files, neither consumes a symbol
  the other introduces.
- **Sequential after Group 1:** every `plan_manager.py` change (the `poll()`
  gate rewrite, `_step_extended`, the two `_extended_candidate_*` helpers,
  the `_eh_breach_streak` dict) — all one file, each piece consumes symbols
  the previous piece introduces.
- **Sequential last:** the new test file (exercises the finished behavior)
  and the full-suite verification task.

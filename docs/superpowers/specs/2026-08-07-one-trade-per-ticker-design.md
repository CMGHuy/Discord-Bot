# One trade per ticker, with invalidate-and-reverse — Design

**Date:** 2026-08-07
**Status:** Approved for implementation

## Problem

Two related defects in how the scanner decides whether to open a trade.

**Duplicates.** The guard at `swingbot/core/scanning/engine.py:1313` is
direction-scoped and setup-scoped:

```python
already_open = (
    trade_log.has_open_trade(ticker, strategy, horizon_key, trend)
    or trade_log.has_similar_open_trade(ticker, trend, entry, stop, target, tol_pct)
)
```

So a second trade on the same ticker still gets logged when it comes from a
different strategy, a different horizon with different price levels, or an
entry far enough from the existing one to clear `DEDUP_TOLERANCE_PCT`. And
because both checks match on `direction`, an *opposite*-direction trade is
never blocked at all — the bot can hold a long and a short on one ticker
simultaneously.

**No way out of a broken thesis.** When price action turns against an open
trade, the only exits are the stop, the target, the near-TP timeout, or a
human clicking Close. There is no path that recognises "this long is dead and
the short is the trade now", so the position rides down to its stop while the
opposite setup goes untaken.

Invalidation exists in the codebase but only *before* entry:
`pending_invalidated()` (`swingbot/core/plan_engine.py:650`) cancels a plan
whose price closed through the stop while still pending. There is no
equivalent for a filled, open trade.

## Decisions

Settled during design:

| Question | Decision |
| --- | --- |
| What triggers a flip | An opposite-direction signal that meets every requirement the bot already demands to open a trade. No new notion of validity. |
| Whipsaw guards | All four: cooldown, minimum hold, confidence margin, max flips per ticker per day. |
| How the early close is counted | New `close_reason="reversed"` on a `closed` status, so reversals are scratches, not wins or losses. |
| Rollout | Config flag, **default ON**. |
| How the inverse enters | The normal path — a v2 pending plan awaiting its trigger, or a legacy direct trade. |

## Design

### 1. Ticker-scoped duplicate guard

One new `TradeLog` method:

```python
def open_trade_for_ticker(self, ticker: str) -> dict | None:
    """The single open trade on this ticker, if any."""
```

The scan loop uses it in place of the two-part `already_open` expression.
`has_open_trade` / `has_similar_open_trade` remain: `backtest_wf.py` documents
itself as mirroring their semantics, and tests reference them. Only the call
site changes.

Result: at most one open trade per ticker, regardless of strategy, horizon,
entry price, or direction. A new trade in the same direction is only possible
once the existing one has closed.

### 2. The reversal decision — pure and isolated

New module `swingbot/core/reversal.py`, one function, no I/O:

```python
def evaluate_reversal(existing, candidate_conf_score, candidate_direction,
                      now, recent_flips, cfg) -> ReversalDecision
```

`ReversalDecision` carries `allowed: bool` and `reason: str` (the reason is
logged and shown in the funnel, so a blocked flip is explainable rather than
silent).

It lives apart from the scan engine deliberately. The engine is already large
and stateful; this is a decision that can be unit-tested exhaustively with no
scan, no price feed, and no Discord client. The engine calls it and acts on
the answer; it performs no I/O of its own.

A flip is allowed only when **all** hold:

- `REVERSAL_ENABLED`
- candidate direction is opposite the open trade's
- candidate has `all_requirements_met` (the existing bar — unchanged)
- open trade has been held at least `REVERSAL_MIN_HOLD_HOURS`
- no reversal on this ticker within `REVERSAL_COOLDOWN_HOURS`
- `candidate_score >= existing_score + REVERSAL_MIN_CONF_MARGIN`
- reversals for this ticker today `< REVERSAL_MAX_PER_DAY`

### 3. Configuration

Five `Field` entries in `swingbot/config.py`, section "Trade Filters & Risk",
so they reach both the `.env` schema and the admin Settings page:

| Setting | Type | Default |
| --- | --- | --- |
| `REVERSAL_ENABLED` | checkbox | `true` |
| `REVERSAL_MIN_HOLD_HOURS` | float | `24` |
| `REVERSAL_COOLDOWN_HOURS` | float | `48` |
| `REVERSAL_MIN_CONF_MARGIN` | float | `10` |
| `REVERSAL_MAX_PER_DAY` | number | `1` |

Defaults are deliberately conservative: at most one flip per ticker per day,
only after a full day held, needing a clearly better opposite setup.

### 4. The close

New `TradeLog.close_trade_reversed(trade_id, exit_price)`, modelled on
`check_near_tp_timeout`'s early close — **not** on `close_trade_manual`.

`close_trade_manual` records no `exit_price` and never calls
`_settle_account_balance()`. Routing a reversal through it would leave P&L and
R blank in Trade History and the account balance unsettled, hiding the very
benefit ("cut the loss sooner") the feature exists to produce.

The new method sets `status="closed"`, `exit_price=<live price>`,
`close_reason="reversed"`, settles the balance, journals the close, and
refreshes the analytics snapshot — the same sequence every other real close
performs.

Because the status is `closed` and not `win`/`loss`, reversals count as
scratches. Win rate is computed over wins+losses only, so it is not distorted;
`close_reason` keeps them filterable in Trade History and on the Performance
page.

### 5. Where it runs

In the alert-building loop of `run_scan_pass`, at the point that currently
computes `already_open`. Reversals fire on **automatic scans only**, never on
`!check` (`require_confirmation=False`) — that path is an on-demand snapshot
and must not mutate positions.

Order of operations on an allowed flip: close the existing trade at the live
price, record the flip for cooldown/quota accounting, then let the candidate
proceed through the unchanged trade-opening path.

### 6. Reversal history

Cooldown and the daily cap need to know about past flips. The closed trade
already carries `close_reason="reversed"` and `closed_at`, which is sufficient
— `recent_flips` is derived by reading closed trades for that ticker rather
than by adding a new persistent store. No new state file.

## Testing

- `evaluate_reversal` unit tests: each guard rejects in isolation; all-pass
  allows; same-direction never flips; disabled flag never flips.
- `open_trade_for_ticker` blocks a second trade across differing strategy,
  horizon, entry price, and direction.
- `close_trade_reversed` sets exit price, settles the balance, and produces a
  scratch rather than a win or loss.
- Scan-level: an opposite qualifying signal closes the old trade and opens the
  inverse; a blocked flip leaves the original untouched.
- `!check` never triggers a reversal.

## Non-goals

- **No new invalidation model.** "No longer valid" means "the opposite setup
  qualifies under the existing bar", nothing more. An open-trade analogue of
  `pending_invalidated` was considered and rejected as unnecessary for now.
- **No immediate market entry.** The inverse waits for its trigger like any
  other trade.
- **No backtest of the reversal behaviour.** See the risk below.

## Known risk

Shipping default-ON changes live strategy performance with no backtest behind
it. `docs/claude/backtest-methodology.md` treats the 2024-25 window as tainted
for selection decisions, and reversal behaviour shifts win rate, expectancy
and holding period — exactly the kind of change that methodology exists to
gate. The flag allows switching it off, but trades taken meanwhile are real
paper history. Recommended follow-up: run the reversal logic through a TRAIN
backtest before trusting its numbers.

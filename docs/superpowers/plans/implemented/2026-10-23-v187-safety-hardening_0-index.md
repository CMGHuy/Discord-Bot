# v187 — Safety hardening: admin-only state commands, validated account settings, live limit entries: Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`. **Never read a part whole**: `grep -n "^### Task V187-9:" -A 320 docs/superpowers/plans/2026-10-23-v187-safety-hardening_2-live-limit-entries.md`.

**Bump:** bot patch
**Edge:** none (integrity) — closes three safety holes and buys no expectancy. Production runs `risk_pct` mode at 1% with every stored setting valid, and the limit strategies are masked, so the live book's ExpR and win rate are predicted unchanged. The value is in what can no longer happen: a follower resetting the balance or wiping history, a 10% or negative risk setting sizing every alert, and a limit plan filling on the wrong side the day a limit strategy is unmasked.
**Screen:** exempt (integrity)
**Spec:** [2026-10-23-v187-safety-hardening-design.md](../../specs/implemented/2026-10-23-v187-safety-hardening-design.md)
**Brief:** `.superpowers/briefs/2026-10-23-v187-safety-hardening.md`
**Worktree:** implement every task in `.claude/worktrees/2026-10-23-v187-safety-hardening` (branch of the same name, created in V187-1's first step; `docs/claude/document-lifecycle.md`). V187-13 runs the full suite in the worktree and merges to `main`; then `/panel risk-manager,staff-engineer,quant-engineer` (the spec's `Panel:` line) and `/close-out` run on `main`.

## Goal

A read-only audit on 2026-10-23 found three holes that sit on the money path.
First, any member of the Discord server can change account or trade state: the
`!account` setters and their `/account` twins, `!trades clear`,
`!trades clear history`, `!trade delete`, `/trades-clear`,
`/trades-clear-history` and `/trade delete` carry no permission check, so a
follower can reset the balance, raise the risk or wipe the trade history.
Second, the 2% risk cap is not enforced in `risk_pct` mode. `set_risk_pct`
stores any float and `compute_position_size` sizes from it directly, so
`!account risk 10` sizes every alert at 10%, and a negative value produces
negative shares that slip under every cap and invert P&L. Third, the live plan
manager fills every pending plan with stop-entry semantics, so a buy limit would
fill when price rises above it, at a price worse than its own limit. The
backtest already fills limits correctly. This third hole is latent only
because the two limit strategies are masked.

Once this ships, the eight account setters and the six trade-wiping commands
answer only to server administrators. Read-only commands stay open, and a
coverage test fails CI if a new command in either module is neither gated nor
allowlisted. Every account setter, and the `.env` seed of a new account row,
goes through one validator (`_validated`) that refuses NaN, infinities,
negatives and out-of-range values with a message naming the setting and its
range. `compute_position_size` gains a backstop for rows the validator never
saw. Non-finite inputs return `None` with a warning, and a stored `risk_pct`
above 2% is clamped to 2% with a warning (shown in `!account` as
`10% stored → 2% used (hard cap)`). After every cap, shares are cut so that
`shares × stop distance ≤ 2%` of the balance in both sizing modes, and a
rounded figure that would breach that is floored. Live limit plans fill at
the limit price when a tick touches it (the conservative twin of the
backtest's non-gap fill). They are cancelled `cancelled_limit` beyond their
cancel level, and `cancelled_gap_through_stop` when the tick is already at or
through the stop. Every pending-cancel event comes from one
`PENDING_CANCEL_EVENTS` set, so none of them can leave a placeholder trade
stuck open.

The plan leaves the rest alone. There is no schema change and no data
migration. The admin UI, the backtest and its fill helpers, the stop-entry
path and every existing sizing output that already respects the 2% ceiling
stay as they are. Live invalidation timing and the four known live/backtest
differences are named in the spec and handed to the metric/parity spec.

Success is measured by the tests. Each gated command refuses a non-admin and
the coverage test passes. The validator table and the seed fallback hold. The
existing sizing tests stay green unchanged, and the legacy `risk_pct=10` alert
size equals the engine size at 2%. Every limit case in spec § Testing passes,
including the parity test against `_limit_entry_exit`, every
`PENDING_CANCEL_EVENTS` member discards its placeholder, every existing
`_step_pending` test passes unchanged, and the plan's one full-suite run,
complexity gate included, is green.

## Architecture

```
D1  commands/account.py, commands/trades.py
      prefix:  @commands.has_permissions(administrator=True)
      slash:   @app_commands.checks.has_permissions(administrator=True)
               + @app_commands.default_permissions(administrator=True) on the two top-level trades commands only
      tests/commands/test_state_command_gates.py: READ_ONLY_COMMANDS allowlist; every other command must be gated

D2  core/planning/account.py
      _validated(key, value) <- every set_* and the seed branch of load_account_config
      compute_position_size(entry, stop_loss, account_cfg=None, *, ..., ticker=None)
        inputs -> _edge_risk_pct (extracted edge chain) -> opex mult
        -> _sizing_inputs_finite -> [risk_pct mode] _usable_risk_pct (clamp / refuse)
        -> raw shares -> _apply_size_caps (existing % and absolute caps)
        -> _cap_to_risk_ceiling (both modes, rel 1e-9) -> _settle_shares (round, floor only on breach)
    commands/account.py: ValueError -> reply.send_error; "stored -> used" line; true cap copy
    config.py: RISK_PER_TRADE_PCT default "1.0", max=2, honest help

D3  core/planning/plan_manager.py
      PENDING_CANCEL_EVENTS (5) ; NOTICE_EVENTS = {"filled","closed"} | PENDING_CANCEL_EVENTS
      _on_event discard: `event.transition in PENDING_CANCEL_EVENTS`
      _step_pending: expiry/session -> [limit] _step_limit -> fill? at_or_beyond_stop? -> _fill_pending(.., "limit_fill")
                                                         -> limit_cancelled? -> cancelled_limit
                                    [other] crossed -> _fill_pending(.., "stop_entry_fill")   (unchanged behaviour)
                     -> pending_invalidated (unchanged)
    vocabulary: instructions.py, lifecycle_embeds.py, execution_embeds.py, session_expiry.py, follow_notify.py
```

## Global Constraints

- Gate exactly the commands in spec § Why 1, no others. Read-only commands stay open. `/account` and `/trade` groups get **no** `default_permissions`; only `/trades-clear` and `/trades-clear-history` get it (spec D1).
- Add decorators only: the slash and prefix command bodies stay byte-identical (`tests/commands/test_slash_parity.py` enforces one `handle_*` call per body and the `SLASH_TWIN` map).
- `RISK_CEILING_PCT` is imported from `swingbot/core/edge/sizing.py`; never a second `2.0` literal in `planning/account.py` or `commands/account.py`.
- Every existing sizing test passes **unchanged**; outputs that already respect the ceiling stay bit-identical (`round(raw_shares, 2)` kept; floor only when the rounded figure breaches).
- Complexity < 15 for every function written or changed. `compute_position_size` (baseline 18) and `PlanManager._on_event` (baseline 15) may only shrink or stay; `_step_pending` (10) stays < 15 through the shared `_fill_pending` helper. Check with `python scripts/dev/complexity_gate.py` in the task that touches them.
- The backtest (`exit_sim.py`, `lifecycle.py`) is not modified; D3 imports `limit_hit`, `limit_cancelled`, `at_or_beyond_stop` from `swingbot.core.planning.lifecycle`.
- The stop-entry path's events, detail keys and fill price are unchanged; only its code moves into `_fill_pending`.
- No schema change, no data migration, no Alembic revision.
- Tests that touch the account store hit Postgres: run `/replicate-prod-db` once before the first DB test run (CLAUDE.md). Per-task runs are `python scripts/dev/testrun.py file <test>`; the full suite runs once, in V187-13.
- New tests go in existing directories (`tests/commands/`, `tests/planning/`, `tests/tracking/`, `tests/presentation/`, `tests/scanning/`, `tests/infra/`); no `tests/suites.toml` edit.
- Do not touch `CLAUDE.md`, `docs/claude/` or `.claude/` (no Codex mirror change).
- Work in the worktree; commit each task as its own scoped commit there. Nothing is pushed to production by this plan.

## Spec clarifications (plan-writer decisions, 2026-10-23)

1. **Gap through the stop is tested on the tick.** D3 step 3 says `at_or_beyond_stop(plan, fill)` "(the tick gapped past the stop)". The live fill is `trigger_price`, so testing the fill would only catch a malformed plan. `_step_limit` tests `at_or_beyond_stop(plan, price)` on the tick price. Given the fill condition (`price <= trigger` bullish), this also covers a stop on the wrong side of the trigger.
2. **Ticker in the sizing warning.** `compute_position_size` has no ticker today. It gains a keyword-only `ticker: str | None = None`, used only in warning text (`ticker=?` when absent). `core/scanning/analyze.py:254` passes `ticker=plan.ticker`; every other caller is unchanged.
3. **What warns and what does not.** The stored `risk_pct` is checked only when the mode reads it (not `account_pct`). A stored value that is non-finite or `<= 0` → `None` + warning. After the edge chain and OPEX multiplier: non-finite → `None` + warning; `<= 0` (a deliberate throttle) → `None`, no warning; `> RISK_CEILING_PCT` → clamped to the ceiling + warning. Non-finite `balance`/`entry`/`stop_loss` or final shares → `None` + warning.
4. **Ceiling tolerance.** `limit = balance * RISK_CEILING_PCT / 100`. The reduction fires when `raw_shares * stop_distance > limit * (1 + 1e-9)`; the floor fires when `round(raw_shares, 2) * stop_distance > limit * (1 + 1e-9)`. Both are skipped when `stop_distance <= 0` (`account_pct` with entry == stop has no stop risk). When floored, `position_value` and `risk_amount` are computed from the floored shares; otherwise they are computed exactly as today.
5. **Seed fallback.** The `Field` default is read from `swingbot.config.FIELDS` by env key. `RISK_PER_TRADE_PCT`'s default becomes `"1.0"`, so the fallback is a sane 1%.
6. **Event details and wording** are fixed in § Contracts, so the vocabulary tasks can be written and run alongside V187-9.
7. **Kinds.** Both new cancel events render as `Kind.CANCEL` (the existing generic 🚫 MANAGE kind) in the execution feed and history embeds. The exception is `follow_notify`: there they map to `Kind.INVALIDATED`, because `test_follow_notify_policy.py::test_imperative_kinds_are_never_used` bans `Kind.CANCEL` from that module. No new `Kind` member is added. `_CANCEL_LEADS` uses `""` for both, because `FEED_SYMBOLS` (pinned by `test_feed_symbols.py`) has no `limit`/`gap` key. Both of these were synced from part 2's "Part-2 decisions".

## Contracts

### Admin gate (V187-1, V187-2)

```python
# swingbot/commands/account.py  (new import)
from discord.ext import commands
# every gated prefix subcommand:
@account_cmd.command(name="risk")
@commands.has_permissions(administrator=True)
async def account_risk(ctx, pct: float): ...        # body unchanged
# every gated /account subcommand:
@account_group.command(name="risk", description="Set the % of balance risked per trade")
@app_commands.describe(pct="Risk per trade, in percent")
@app_commands.checks.has_permissions(administrator=True)
async def slash_account_risk(interaction, pct: float): ...   # body unchanged
# /trades-clear and /trades-clear-history additionally:
@app_commands.default_permissions(administrator=True)
```

`tests/commands/test_state_command_gates.py` (created in V187-2; V187-1 creates the per-command account tests in `tests/commands/test_account_admin_gate.py`):

```python
GATED_MODULES = ("swingbot.commands.account", "swingbot.commands.trades")
READ_ONLY_COMMANDS = frozenset({
    # prefix (qualified_name): the group callbacks `account`, `trades`, `trade` are the read-only views
    "account", "trades", "trade", "tradecharts", "performance", "pnl", "summary",
    # slash (qualified_name)
    "account show", "trade show",
})   # "trades", "tradecharts", "performance", "pnl", "summary" are shared prefix/slash names
def _is_admin_gated(cmd) -> bool   # any check whose __qualname__ contains "has_permissions"
```

V187-2 confirms the allowlist against the registered names (`bot.walk_commands()` / `bot.tree.walk_commands()`) and adjusts the literal to the exact read-only names it finds. Any name that is not in spec § D1's read-only list is a stop-and-ask.

### Validator (V187-3, consumed by V187-4, V187-5)

```python
# swingbot/core/planning/account.py
from swingbot.core.edge.sizing import RISK_CEILING_PCT

def _validated(key: str, value) -> float | int:
    """Normalised value for an account setting, or ValueError naming the setting and its range."""
```

| key | accepts | returns | ValueError message |
|---|---|---|---|
| `risk_pct` | finite, `0 < x <= RISK_CEILING_PCT` | `float` | `Risk per trade must be above 0% and at most 2.0% (got {value}).` |
| `position_pct` | finite, `0 < x <= 100` | `float` | `Position size must be above 0% and at most 100% of the account (got {value}).` |
| `max_position_pct` | finite, `0 < x <= 100` | `float` | `Max position size must be above 0% and at most 100% of the account (got {value}).` |
| `max_position_value_absolute` | finite, `x >= 0` | `float` | `Max position value must be 0 (off) or more (got {value}).` |
| `max_risk_amount_absolute` | finite, `x >= 0` | `float` | `Max risk per trade must be 0 (off) or more (got {value}).` |
| `base_balance` | finite, `x > 0` | `float` | `Balance must be above 0 (got {value}).` |
| `max_open_positions` | `int` (not `bool`) or integral finite float, `x >= 1` | `int` | `Max open positions must be a whole number of 1 or more (got {value}).` |

The `2.0` in the `risk_pct` message is rendered from `RISK_CEILING_PCT`. An unknown key raises `KeyError`. `bool` is refused for every key.

### Sizing (V187-6, V187-7)

```python
def compute_position_size(entry: float, stop_loss: float, account_cfg: dict = None, *,
                          strategy_stats: dict = None, ticker_atr_pct: float = None,
                          open_positions: int = 0, ticker: str | None = None) -> dict | None
# result shape unchanged: shares, risk_amount, position_value, capped, balance, risk_pct,
# position_pct, max_position_pct, max_position_value_absolute, max_risk_amount_absolute, mode
_RISK_TOLERANCE = 1e-9                                                     # V187-7
def _edge_risk_pct(mode: str, risk_pct: float, strategy_stats, ticker_atr_pct, open_positions) -> tuple[float, str]   # V187-6
def _sizing_inputs_finite(balance: float, entry: float, stop_loss: float, ticker: str | None) -> bool               # V187-6
def _usable_risk_pct(stored: float, effective: float, ticker: str | None) -> float | None                           # V187-6
def _apply_size_caps(raw_shares: float, entry: float, stop_distance: float, balance: float,
                     max_position_pct: float, max_value_abs: float, max_risk_abs: float) -> tuple[float, bool]     # V187-6
def _cap_to_risk_ceiling(raw_shares: float, stop_distance: float, balance: float) -> tuple[float, bool]             # V187-7
def _settle_shares(raw_shares: float, stop_distance: float, balance: float) -> tuple[float, float]                 # V187-7: (basis_for_figures, reported_shares)
```

Warnings go to the module logger `log = logging.getLogger(__name__)` with the prefix `sizing:` and name `ticker` and the offending value. Wording is fixed in V187-6.

### Plan manager events (V187-8, V187-9; consumed by V187-10..V187-12)

```python
# swingbot/core/planning/plan_manager.py, module level
PENDING_CANCEL_EVENTS = frozenset({
    "cancelled_expired", "cancelled_invalidated", "cancelled_risk_cap",
    "cancelled_limit", "cancelled_gap_through_stop",
})
NOTICE_EVENTS = frozenset({"filled", "closed"}) | PENDING_CANCEL_EVENTS
# _TRANSITION_LOG additions
"cancelled_limit": ("limit cancelled", "live_price"),
"cancelled_gap_through_stop": ("gap through stop", "live_price"),

class PlanManager:
    def _fill_pending(self, plan: TradePlanV2, fill: float, price: float, reason: str) -> list[PlanEvent]
        # risk-cap check (planned_loss_pct vs plan_stop_ceiling) -> cancelled_risk_cap (detail unchanged)
        # else entry_price = fill, ACTIVE transition with `reason`, "filled" {"entry_price": fill, "live_price": price}
    def _step_limit(self, plan: TradePlanV2, price: float) -> list[PlanEvent] | None
        # None = nothing happened this tick (the caller falls through to the invalidation check)
```

| Event | Transition reason | `detail` keys |
|---|---|---|
| `filled` (limit) | `limit_fill` | `entry_price` (= `plan.trigger_price`), `live_price` |
| `cancelled_limit` | `limit_cancelled` | `live_price`, `limit_cancel_level` |
| `cancelled_gap_through_stop` | `gap_through_stop` | `entry_price` (= `plan.trigger_price`), `live_price`, `stop_loss` |

| Site | `cancelled_limit` | `cancelled_gap_through_stop` |
|---|---|---|
| `instructions._CANCEL_LEADS` | `""` | `""` |
| `instructions._cancel_why` | `Price ran past the limit's cancel level {limit_cancel_level} at {live_price} before the order filled. Nothing was opened.` | `Price touched the limit at {live_price}, already at or through the stop {stop_loss}. The order is cancelled, nothing was opened.` |
| `instructions._BUILDERS` | `_cancelled` | `_cancelled` |
| `lifecycle_embeds._EVENT_KINDS` / `execution_embeds` kind map | `Kind.CANCEL` | `Kind.CANCEL` |
| `lifecycle_embeds._EVENT_FIELDS` | `_limit_cancelled_fields` | `_gap_through_stop_fields` |
| `session_expiry._IN_SESSION_CODES` | `LIMIT_CANCELLED = "limit_cancelled"` | `GAP_THROUGH_STOP = "gap_through_stop"` |
| `follow_notify._BY_TRANSITION` | `"closed_other"` | `"closed_other"` |
| `follow_notify._CLOSED_OTHER_KIND` | `Kind.INVALIDATED` | `Kind.INVALIDATED` |
| `follow_notify._CANCEL_LABELS` | `"limit cancelled before fill"` | `"gapped through the stop before fill"` |

Prices in the `_cancel_why` sentences use the module's existing price formatter (the one the risk-cap sentence uses).

## Review Focus

- V187-6/7: every pre-existing sizing assertion passes untouched; `compute_position_size` complexity is at or below 18; the floor fires only on a breach.
- V187-8: `_on_event` complexity at or below 15; the discard branch reads `PENDING_CANCEL_EVENTS`.
- V187-9: stop-entry tests unchanged; limit fill is `trigger_price`, never the tick; gap-through-stop logs no trade.

## Parallelisation

| Task | May run alongside | Sequential edge and why |
|---|---|---|
| V187-1 | none | first task: creates the worktree; owns `commands/account.py` |
| V187-2 | V187-3, V187-4, V187-8, V187-10, V187-11, V187-12 | after V187-1's worktree step; disjoint files `commands/trades.py`, `test_slash_parity.py`; its coverage test enumerates `commands/account.py`, so it runs after V187-1's gates exist (contract dependency) |
| V187-3 | V187-2, V187-8, V187-10, V187-11, V187-12 | after V187-1's worktree step; owns `planning/account.py` |
| V187-4 | V187-2, V187-8, V187-10, V187-11, V187-12 | after V187-3: same file `planning/account.py` and consumes `_validated` |
| V187-5 | V187-8, V187-10, V187-11, V187-12 | after V187-1 (same file `commands/account.py`) and V187-3 (`ValueError` contract) |
| V187-6 | V187-2, V187-8, V187-10, V187-11, V187-12 | after V187-4: same file `planning/account.py` |
| V187-7 | V187-2, V187-8, V187-10, V187-11, V187-12 | after V187-6: same function `compute_position_size` |
| V187-8 | any of V187-2..V187-7, V187-10..V187-12 | after V187-1's worktree step; owns `plan_manager.py` |
| V187-9 | V187-2..V187-7, V187-10..V187-12 | after V187-8: same file `plan_manager.py` and consumes `PENDING_CANCEL_EVENTS` |
| V187-10 | anything before V187-13 | disjoint file `instructions.py`; event names and details fixed in § Contracts |
| V187-11 | anything before V187-13 | disjoint files `lifecycle_embeds.py`, `execution_embeds.py`; reads `NOTICE_EVENTS` by import only |
| V187-12 | anything before V187-13 | disjoint files `session_expiry.py`, `follow_notify.py` |
| V187-13 | none | after every other task: the plan's single full-suite run and complexity gate, then the merge |

At most two `task-implementer`s at once; two tasks that share a file never run together.

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-23-v187-safety-hardening_1-admin-gate-and-account-limits.md` | V187-1..V187-5 | worktree; administrator gates on the account and trades commands with the allowlist coverage test; the account-setting validator and validated `.env` seed; handler refusals and honest copy |
| 1b | `2026-10-23-v187-safety-hardening_1b-sizing-backstop.md` | V187-6..V187-7 | the sizing backstop (finite guards, risk clamp, 2% ceiling in both modes, floor on breach); `_apply_size_caps(…, position_value)` |
| 2 | `2026-10-23-v187-safety-hardening_2-live-limit-entries.md` | V187-8..V187-13 | one pending-cancel event set and the placeholder discard; the live limit branch with its shared fill helper and parity test; the two new events across instructions, embeds, session expiry and follow notices; full suite and merge |

## Task ledger

| Task | Title | Part | Model | Files created / modified | Creates (consumed later) |
|---|---|---|---|---|---|
| V187-1 | Worktree; administrator gate on the account setters | 1 | sonnet | M `swingbot/commands/account.py`; C `tests/commands/test_account_admin_gate.py` | worktree branch `2026-10-23-v187-safety-hardening`; gated `account_*` / `slash_account_*` setters; `from discord.ext import commands` in `commands/account.py` |
| V187-2 | Administrator gate on the trade-wiping commands; allowlist coverage test | 1 | sonnet | M `swingbot/commands/trades.py`, `tests/commands/test_slash_parity.py`; C `tests/commands/test_state_command_gates.py` | `READ_ONLY_COMMANDS`, `GATED_MODULES`, `_is_admin_gated(cmd) -> bool` |
| V187-3 | One validator for every account setter | 1 | sonnet | M `swingbot/core/planning/account.py`; C `tests/planning/test_account_validator.py` | `_validated(key: str, value) -> float \| int`; every `set_*` raises `ValueError` on an invalid value and saves nothing |
| V187-4 | Validated `.env` seed and an honest RISK_PER_TRADE_PCT field | 1 | sonnet | M `swingbot/core/planning/account.py`, `swingbot/config.py`, `tests/infra/test_env_example_sync.py`; C `tests/planning/test_account_seed_validation.py` | `_SEED_ENV_KEYS: dict[str, str]`, `_field_default(env_key: str) -> str`, `_validated_seed(defaults: dict) -> dict`; `RISK_PER_TRADE_PCT` default `"1.0"`, `max=2` |
| V187-5 | Discord handlers refuse invalid settings; true cap copy; stored → used line | 1 | sonnet | M `swingbot/commands/account.py`, `tests/commands/parity_cases/account.py`; C `tests/commands/test_account_handlers_validation.py` | `_risk_used_text(cfg: dict) -> str` |
| V187-6 | Sizing backstop: finite guards, risk clamp, helpers out of compute_position_size | 1 | opus | M `swingbot/core/planning/account.py`, `swingbot/core/scanning/analyze.py`; C `tests/planning/test_sizing_backstop.py` | `compute_position_size(..., ticker=None)`; `_edge_risk_pct`, `_sizing_inputs_finite`, `_usable_risk_pct`, `_apply_size_caps` |
| V187-7 | 2% ceiling in both modes and floor-on-breach rounding | 1 | opus | M `swingbot/core/planning/account.py`; C `tests/planning/test_sizing_risk_ceiling.py`, `tests/scanning/test_alert_size_matches_engine.py` | `_RISK_TOLERANCE`, `_cap_to_risk_ceiling`, `_settle_shares` |
| V187-8 | One pending-cancel event set drives the placeholder discard and notices | 2 | opus | M `swingbot/core/planning/plan_manager.py`; C `tests/tracking/test_pending_cancel_discard.py` | `PENDING_CANCEL_EVENTS`; derived `NOTICE_EVENTS`; `_TRANSITION_LOG` entries for `cancelled_limit`, `cancelled_gap_through_stop` |
| V187-9 | Live limit entries fill at the limit, cancel beyond the level, refuse a gap through the stop | 2 | opus | M `swingbot/core/planning/plan_manager.py`; C `tests/planning/test_plan_manager_limit_entry.py` | `PlanManager._fill_pending(plan, fill, price, reason) -> list[PlanEvent]`, `PlanManager._step_limit(plan, price) -> list[PlanEvent] \| None`; events `cancelled_limit`, `cancelled_gap_through_stop`; reasons `limit_fill`, `limit_cancelled`, `gap_through_stop` |
| V187-10 | Instruction wording for the two new cancel events | 2 | sonnet | M `swingbot/core/presentation/instructions.py`; C `tests/presentation/test_instructions_limit_cancels.py` | `_CANCEL_LEADS` / `_cancel_why` / `_BUILDERS` entries |
| V187-11 | Lifecycle and execution embeds for the two new cancel events | 2 | sonnet | M `swingbot/core/scanning/lifecycle_embeds.py`, `swingbot/core/scanning/execution_embeds.py`; C `tests/scanning/test_lifecycle_embeds_limit_cancels.py` | `_limit_cancelled_fields`, `_gap_through_stop_fields` |
| V187-12 | Session-expiry codes and follow notices for the two new cancel events | 2 | sonnet | M `swingbot/core/planning/session_expiry.py`, `swingbot/commands/scanning/follow_notify.py`; C `tests/commands/test_follow_notify_limit_cancels.py` | `session_expiry.LIMIT_CANCELLED`, `session_expiry.GAP_THROUGH_STOP` |
| V187-13 | Full suite, complexity gate, merge | 2 | sonnet | none (merge commit; `/close-out` bumps bot patch and regenerates `version_history.json`) | merged branch on `main` |


## Completion record (2026-10-26)

Implementation tasks V187-1 through V187-12 landed in scoped commits on the existing worktree; V187-13 merged them to `main` at `a7c30ecf`. The integration preserves v188's recorded fill-price history. A final review caught non-finite share settlement, fixed by `9854ab43`; xdist collection order was made deterministic in `d8291854`; seed-validation warnings retain tracebacks in `6cf95f98`.

The full suite at `558da35d` completed with **14,640 passed, 72 failed, 8 skipped, 0 xfailed**. All failures were resolved: 70 shell tests needed Git Bash/coreutils on PATH, the guidance size check was fixed by the incoming main revision, and the account warning needed `exc_info=True`. Fourteen focused file runs then returned **270 passed, 2 skipped, 0 failed, 0 xfailed**, including every originally failing file. Four formerly skipped shell tests now execute. The full suite was not repeated. Remaining platform/cache omissions are POSIX file modes, a POSIX-only installer, unavailable symlink creation and the optional missing `data/backtest_cache/AAPL.csv` fixture. No database tests were skipped in the focused verification.

The fresh V187-13 end-to-end render check passed for both cancellation events, and `python scripts/dev/complexity_gate.py` passed with 104 legacy functions and none new, risen, improved or gone. Detailed evidence is retained locally in `.superpowers/sdd/2026-10-23-v187-safety-hardening/`.

**Deployment and rollback constraint:** no limit strategy may be unmasked before v187 is deployed, and none may stay unmasked across a rollback past v187. Deployment is outside this plan.

**Residual integrity limitations:** the implementation panel qualified the spec's heat assurance because candidate checks still read stored risk. It also found that cancellation persistence and placeholder deletion remain separate writes; a deletion failure can leave a cancelled plan's placeholder open. The latter's blocking classification was rejected as an inherited mechanism explicitly retained by V187-8 and belonging with v189's cross-store transaction work; the defect is recorded, not treated as fixed. See the spec's Implementation panel for evidence, scope ruling and failure cost.

**Close-out:** bot `2.15.4` released locally (`42382d23`), version history regenerated in `d1e6600c`, and `testrun.py file tests/scripts/test_build_version_matrix.py` passed all 13 tests. Panel outcomes are recorded in the spec; no unresolved blocking finding remains. The merged worktree and branch were removed after preserving their local evidence. No deployment or push was performed.

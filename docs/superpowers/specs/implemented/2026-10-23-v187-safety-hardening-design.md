# v187 — Safety hardening: admin-only state commands, validated account settings, live limit entries

**Version:** ui 1.35.0 · bot 2.14.4 (at writing)
**Bump:** bot patch. Non-admins can no longer change account or trade state from Discord, invalid account settings are refused, and a limit entry fills on the correct side; nothing a normal admin workflow sees changes.
**Edge:** none (integrity). Closes holes; buys no expectancy.
**Screen:** exempt (integrity)
**Panel:** risk-manager, staff-engineer, quant-engineer
**Status:** spec written 2026-10-23 from a brainstorm with the partner (repo-wide audit, four read-only auditors), approved in chat. First of four audit specs: safety → book integrity + partial-trade truth → one metric definition → frontend hygiene.

## Why

A repo-wide read-only audit on 2026-10-23 found three safety holes. Each was verified by reading the code:

1. **Any guild member can change account or trade state from Discord.** The only permission decorators in the repo are on the kill switch (`swingbot/commands/growth.py:120,229`). `!account balance|risk|maxpositions|sizing|positionpct|maxpositionpct|maxposition|maxrisk` (`commands/account.py:165-225`), their slash twins under `/account` (`:242-290`), `!trades clear`, `!trades clear history` (`commands/trades.py:218,227`), `!trade delete` (`:397`), `/trades-clear`, `/trades-clear-history` (`:708,713`) and `/trade delete` (`:727`) carry no check. A follower can reset the balance, raise risk, or wipe the trade history.
2. **The 2% risk cap is not enforced in `risk_pct` mode.** `set_risk_pct` (`planning/account.py:199`) stores any float. `compute_position_size` (`:452`, `:500-503`) sizes from it directly; `RISK_CEILING_PCT` (`edge/sizing.py:19`) is applied only inside `kelly_risk_pct` / `vol_target_risk_pct`, and `effective_risk_pct` takes the `min` of the candidates, so with no edge estimate the stored value passes unclamped. `!account risk 10` sizes every alert (`swingbot/core/scanning/analyze.py:254`) at 10%; a negative value yields negative shares that slip under every cap (`position_value > max` is false), inverting P&L. The `!account` reply (`commands/account.py:58`) tells the user there is "the frozen 2% hard cap", which is untrue in this path. The `.env` help for `RISK_PER_TRADE_PCT` (`swingbot/config.py:521-527`) says nothing in the pipeline sizes from it, which is also untrue.
3. **Live limit entries fill as stop entries.** `PlanManager._step_pending` (`planning/plan_manager.py:932-955`) fills every pending plan on `price >= trigger` (bull) / `price <= trigger` (bear) at `max/min(price, trigger)`. That is stop-entry semantics. A buy limit would fill when price rises above it, at a price worse than its own limit. The backtest fills limits correctly (`exit_sim._limit_entry_exit`, `lifecycle.limit_hit` / `limit_fill_price` / `limit_cancelled`). Limit strategies (`Downtrend Overbought Fade`, `FIB_LIMIT`, `params.py:70,80`) are masked today, so this is latent until one is promoted.

Production state, checked read-only on 2026-10-23: `sizing_mode=risk_pct`, `risk_pct=1.0`, `max_position_pct=5.0`, absolute caps 1000 / 100, `max_open_positions=30`, nothing negative or non-finite. **No data migration is needed.**

## Decisions

### D1 — State-changing Discord commands require server administrator

Gate exactly the commands listed in Why §1, and no others. Read-only commands stay open: `!account` / `/account show`, `!trades`, `!trade` / `/trade show`, `!performance`, `!pnl`, `!summary`, `!tradecharts`, `!check`.

- **Prefix commands:** `@commands.has_permissions(administrator=True)`, the decorator `growth.py:120` uses. Refusals already go through `bot_core.on_command_error`.
- **Slash commands:** `@app_commands.checks.has_permissions(administrator=True)` on each gated command. `/trades-clear` and `/trades-clear-history` are top-level, so they also get `@app_commands.default_permissions(administrator=True)`, which hides them from non-admins in the client. The `/account` and `/trade` subcommands cannot carry `default_permissions` individually, because discord.py allows it only on top-level commands and the groups hold the read-only `show`. They rely on the check alone. Refusals already go through `slash.py` `APP_CHECK_REPLIES[MissingPermissions]` (ephemeral).
- **Coverage test.** The test is driven by a **read-only allowlist**, not by a list of the commands that change state. It enumerates every prefix command and app command registered from `commands/account.py` and `commands/trades.py`. Each must either appear in `READ_ONLY_COMMANDS` (held in the test module) or carry the administrator check. A new command added to either module is therefore gated by default: if someone forgets the gate, CI fails until the command is gated or deliberately allowlisted. Neither module has a command that moves a stop or edits a plan today. Commands in other modules (watchlist, scanning) are out of scope for this spec.

### D2 — One validator for every account setter; sizing clamps as a backstop

Add `_validated(key, value)` in `planning/account.py`, called by every `set_*` before `save_account_config`:

| Setter / key | Accepts | Notes |
|---|---|---|
| `risk_pct` | finite, `0 < x <= RISK_CEILING_PCT` | import the constant from `edge/sizing.py`; never a second `2.0` literal |
| `position_pct`, `max_position_pct` | finite, `0 < x <= 100` | |
| `max_position_value_absolute`, `max_risk_amount_absolute` | finite, `x >= 0` | `0` keeps meaning "off" |
| `base_balance` | finite, `x > 0` | |
| `max_open_positions` | integer, `x >= 1` | an `int`, or an integral finite float such as `3.0`, stored as `int`. Refused: a `bool`, a fractional float, NaN/inf. Not truncated |
| `sizing_mode` | unchanged | already normalised by `set_sizing_mode` |

- An invalid value raises `ValueError` whose message names the setting and its allowed range. The Discord handlers catch it and reply with that message, saving nothing. A reply rather than an exception keeps the user-facing text identical between prefix and slash.
- **Backstop.** `compute_position_size` clamps `risk_pct` into `(0, RISK_CEILING_PCT]` after the edge chain and the OPEX multiplier. A non-positive or non-finite value returns `None`, the same as the existing "can't size" path. This covers a hand-edited or legacy `account` row the setter never saw. The sizing result keeps its shape. A warning is logged **every** time the clamp fires or sizing is refused for a non-positive or non-finite value, naming the ticker and the stored value. A stream of unsized alerts must not read as a quiet day. `!account` / `/account show` displays a stored value above the cap as `10% stored → 2% used (hard cap)`, so the cut is visible and never silent. The alert's suggested size and the engine's size come from the same `compute_position_size` call, and a test pins that they are equal for a legacy `risk_pct=10`.
- **Numerics.** `compute_position_size` returns `None` with a warning when `balance`, `entry`, `stop_loss`, the stop distance or the final share count is not finite. The existing `<= 0` guards are false for NaN, so NaN would otherwise pass every cap. The 2% reduction below runs on the **returned** figure. Shares keep today's `round(…, 2)`. Only when the rounded figure would breach the ceiling are they floored to 2 decimals instead, so a round-up can never push delivered risk over the ceiling, and every output that already respects it stays bit-identical. The reduction fires only when risk exceeds the ceiling by more than a relative `1e-9`, so a config sitting exactly at `risk_pct = 2.0` is not reported as `capped` because of float noise, and existing sizing outputs stay unchanged. The test pins `round(shares) × stop_distance ≤ ceiling` on the returned value. The refusal warning fires only for an invalid **stored or configured** value, never for a deliberate 0 such as a throttle. `account_pct` mode does not read `risk_pct`, so it ignores a bad stored `risk_pct`. The 2% reduction there uses `RISK_CEILING_PCT` directly.
- **The 2% cap also binds in `account_pct` mode.** In that mode, size comes from `position_pct` (`account.py:493-496`), with nothing tied to risk, so a wide stop could risk more than 2%. After the final share count is settled (the absolute caps included), shares are reduced, in both modes, so that `shares × stop_distance ≤ balance × RISK_CEILING_PCT / 100`. When this reduction fires it sets `capped = True`, as the existing caps do. Production runs `risk_pct` mode at 1%, so nothing changes there today.
- **What still binds.** Setting both absolute caps to `0` turns those two caps off, as it does today; the sizing backstop still enforces the 2% per-trade dollar-risk ceiling. Existing portfolio-heat and correlated-exposure checks remain separate: `swingbot/core/scanning/scan_run.py:1167` and `swingbot/core/scanning/short_run.py:240` use stored `risk_pct` for the candidate rather than its actual sized risk. They can therefore understate an `account_pct` candidate (for example, checking 1% when sizing uses 2%). v187 does not establish accurate candidate heat across sizing modes; that existing gap needs a separate scan-risk correction.
- **The `.env` seed path is validated too.** `load_account_config` (`account.py:111-152`) seeds a missing account row from `.env` without calling a setter. Each seeded value goes through `_validated`. A seeded value that fails validation falls back to the `Field` default and logs a warning. The `RISK_PER_TRADE_PCT` `Field` default is `"0.01"` today, which as a fallback would mean 0.01% risk. It is corrected to `"1.0"`, matching `.env.example`, and the tolerance for that mismatch in `tests/infra/test_env_example_sync.py` is removed. The admin UI save already enforces `Field.max` (`admin/api_v1/system.py:156`). A hand-edited `.env` is covered by this seed-time check, and a stored row that predates this change is covered by the sizing backstop.
- **Copy.** Fix `commands/account.py:58` so the "hard cap" sentence is true (it now is). Rewrite the `RISK_PER_TRADE_PCT` help (`config.py:523-527`) to say it seeds the account's risk-per-trade, which sizes every alert, capped at 2%. Set that `Field`'s `max=2`. The help text on `MAX_POSITION_*` fields that also say "informational only" is checked and corrected in the same pass if equally stale.

### D3 — Live limit entries fill like the backtest

In `_step_pending`, after the expiry / session-window checks and before the existing stop-entry branch, add a limit branch for `plan.entry_type == "limit"`:

1. If `lifecycle.limit_hit(plan, price, price)` holds (a tick is a one-print bar, which keeps the `limit_strict_fill` rule intact), fill **at the limit price**. A 60-second poll that first sees price already through the limit usually missed the moment it traded at the limit. Booking the tick price would record a better entry than the backtest gives the same non-gap touch. So the live rule is the conservative one: entry = `trigger_price`, never better. On a true opening gap this slightly understates the improvement the backtest credits (`limit_fill_price` at the open), which is the safe direction for paper results. A parity test runs one `_step_pending` tick and `_limit_entry_exit` on a matching synthetic non-gap bar, and pins the same entry price.
2. Otherwise, if `lifecycle.limit_cancelled(plan, price, price)` holds, cancel with reason `limit_cancelled` and emit a `cancelled_limit` event.
3. **A fill at or through the stop opens nothing.** If `lifecycle.at_or_beyond_stop(plan, fill)` holds (the tick gapped past the stop), the plan is cancelled with reason `gap_through_stop` and emits a `cancelled_gap_through_stop` event. No trade is logged. This is the live twin of the backtest's 0R scratch for the same case (`exit_sim._fill_bar_exit`, `exit_sim.py:747`). Neither side books a loss, and no position exists. The check runs before the risk-cap check, because `planned_loss_pct` takes `abs()` and would score a stop on the wrong side as a small, acceptable risk.
4. Any other fill passes through the **same** risk-cap check (`planned_loss_pct` vs `plan_stop_ceiling`) and the same `filled` event as a stop entry. Only the transition reason differs: `limit_fill` instead of `stop_entry_fill`.

**Wiring the two new cancel events.** The pending-cancel vocabulary is hand-listed today. `_on_event`'s placeholder discard (`plan_manager.py:773`) knows only `cancelled_expired | cancelled_invalidated | cancelled_risk_cap`. If a new cancel event is not added there, the scan's placeholder trade stays "open" forever, which repeats the 2026-09-11 stuck-trade incident described in the comment at `:774-779`. So:

- One module-level `PENDING_CANCEL_EVENTS` frozenset in `plan_manager.py` holds all five cancel events. The placeholder-discard branch and `NOTICE_EVENTS` derive from it, so the next cancel event added cannot be half-wired.
- `_TRANSITION_LOG` gets an INFO label for each new event (`limit cancelled`, `gap through stop`).
- Each place that words or filters lifecycle events for Discord gets the two events, or is confirmed to need none, and that choice is written in the plan task. Those places are `commands/scanning/follow_notify.py:54,68,140`, `session_expiry.py:35`, `core/scanning/execution_embeds.py:33`, `core/scanning/lifecycle_embeds.py` (`_EVENT_KINDS`, `PLAN_EVENT_KINDS`, `_EVENT_FIELDS`), and `instructions.py` (`_CANCEL_LEADS`, `_BUILDERS`, `_cancel_why`, around `:543,578`). `_cancel_why` must get its own wording for both events. Without it, it falls through to the risk-cap wording and raises `KeyError` on detail keys the new events don't carry.
- A test pins that each member of `PENDING_CANCEL_EVENTS` discards the placeholder trade.

The fill check runs before the cancel check, as in `_limit_entry_exit`. The stop-entry branch is unchanged for every other `entry_type`. To keep `_step_pending` under complexity 15, the fill / risk-cap / record step moves into one helper shared by both branches.

**Known live/backtest differences, stated rather than fixed here.** All four are carried into the metric/parity spec.

- **Risk-cap cancel.** Live keeps the risk-cap cancel on limit fills as a safety check. `_limit_entry_exit` has none: only `_compression_fill` does (`exit_sim.py:774-785`). A limit plan whose trigger-to-stop distance exceeds its ceiling is therefore cancelled live but scored in the backtest.
- **Gap through the stop.** The backtest records it as an `outcome="scratch"` 0R row, which counts in N. Live logs no trade. The economics are the same, but the counted populations differ.
- **Fill rate.** Polling cannot see an intrabar touch, so live can miss a limit the bar's low reached, and limit fill rates will differ.
- **Transition reason.** The new `limit_fill` reason is read by no code path. `_entered_at` and `_days_since_entry` read the ACTIVE transition regardless of reason, and only tests and the `plan_manager.py:974` comment name `stop_entry_fill`. The comment is updated to say "the fill transition".

**Out of scope here:** live invalidation firing on any tick while the backtest checks it on the close (`_step_pending` → `pending_invalidated`, `lifecycle.py:144`). That is a live-vs-backtest parity question, and it belongs to the metric/parity spec.

## Testing

- **D1:** for each gated command, a non-admin invocation is refused with the existing message and leaves state unchanged; an admin invocation succeeds. The coverage test from D1. The read-only commands still answer for a non-admin.
- **D2:** a validator table test over NaN, ±inf, negative, 0, `RISK_CEILING_PCT`, `RISK_CEILING_PCT + 0.01`, 100, 100.01 and `2.5` for `max_open_positions`. A handler test checks that an invalid value replies with the message and does not save. `compute_position_size` with a legacy `risk_pct=10` sizes at 2%; with `risk_pct=-1` or NaN it returns `None`. Existing sizing tests stay green unchanged.
- **Numerics:** NaN or inf for balance, entry or stop → `None` plus a warning. At exactly `risk_pct = 2.0`, the result is unchanged with `capped=False`. The returned (floored) shares respect the ceiling. `max_open_positions` refuses `True`, `2.5` and NaN, and accepts `3.0`, storing it as `3`.
- **D2 additions:** in `account_pct` mode, a wide stop is cut to 2% risk with `capped=True`. A `.env` seed with `RISK_PER_TRADE_PCT=10` falls back to the default and logs a warning. The legacy clamp shows `stored → used` in `!account`.
- **D3:** bullish and bearish limits, each covering touch fill, strict-fill refusal on an exact touch, a tick strictly through the limit (fills at the limit, not at the tick), the parity test against `_limit_entry_exit`, cancel beyond `limit_cancel_level`, a tick that both fills and is beyond the cancel level (fills), a fill at or through the stop (cancelled `gap_through_stop`, no trade logged), and risk-cap cancellation on a limit fill. Every member of `PENDING_CANCEL_EVENTS` discards the placeholder trade. Every existing `_step_pending` stop-entry test passes unchanged.
- While iterating, run `testrun.py changed`. The full suite runs once, as the plan's final task.

## Blast radius and rollback

- **Who sees it:**
  - Discord users: non-admins lose the commands listed in D1; admins see refusal messages for invalid settings.
  - The Discord alert channel and the follow channel see the two new limit-cancel notices.
  - Nothing in the admin UI changes.
  - Backtests are untouched (D3 reuses their helpers and does not change them).
- **Rollback** is a plain redeploy of the previous image (`scripts/ops/rollback_to.sh`, `docs/deploy/DEPLOY_HETZNER.md`):
  - There is no schema change and no data migration.
  - The slash command tree re-syncs on every start (`commands/scanning/loops.py:1311`), so the old permissions come back with the old image.
  - The one hazard: a limit plan still PENDING at rollback time would be filled by the old stop-entry code on the wrong side. Limit strategies are masked (`swingbot/core/market/strategy_types.py:277,282`), so no limit plan can exist while they stay masked. Unmasking a limit strategy therefore requires v187 to be deployed first, and rolling back past v187 requires those strategies to be masked again first.

## Not in this spec

Everything else from the 2026-10-23 audit goes to the next three specs: book integrity and partial-trade display, metric definitions (counting unit, day, ledger, snapshot, drawdown), and frontend hygiene.

## Panel review

Run 2026-10-23, serially: risk-manager (sonnet), staff-engineer (opus), quant-engineer (sonnet).

**BLOCKING**
- risk-manager: a limit fill at or through the stop would open a position already beyond its stop, because `planned_loss_pct` takes `abs()`. Applied: the plan is cancelled with `gap_through_stop`, the live twin of the backtest's 0R scratch (D3 step 3).
- staff-engineer: the new cancel events never reach `discard_plan_placeholder` (`plan_manager.py:773`), which would leave stuck open placeholder trades as in the 2026-09-11 incident. Applied: a single `PENDING_CANCEL_EVENTS` set drives both the discard and the notices, with a test.
- quant-engineer: NaN or inf balance, entry or stop passes every `<=`/`>` guard. Applied: `isfinite` guards with `None` plus a warning (D2 Numerics).
- quant-engineer: the 2% invariant was checked before rounding, and float noise at exactly 2.0 could set `capped`. Applied: shares are floored after every cap, the reduction uses a relative 1e-9 tolerance, and the test pins the returned value.

**ADVISORY**
- risk-manager: the coverage test should start from a read-only allowlist. Applied (D1).
- risk-manager: log every sizing refusal. Applied, scoped to invalid stored or configured values per quant-engineer #7.
- risk-manager: alert size equals engine size for legacy `risk_pct=10`. Applied (test).
- risk-manager: make the legacy clamp visible to the user. Applied (`stored → used` in `!account`).
- risk-manager: state what still binds (heat and correlated caps) and consider a `max_open_positions` ceiling. Statement applied. Ceiling rejected: portfolio heat (`analyze.py:252`) already bounds total exposure, and production sits at 30.
- staff-engineer: name every place the transition vocabulary is listed. Applied (D3 wiring list).
- staff-engineer: the `.env` seed path bypasses the setters. Applied: seed values go through `_validated`.
- staff-engineer: no blast-radius or rollback section. Applied, including the rule that limit strategies may not be unmasked before v187.
- staff-engineer: the "never above 2%" claim is false in `account_pct` mode. Applied: the 2% reduction runs in both modes.
- quant-engineer: tick-price fills are better than the backtest's non-gap fills. Applied: live fills at the limit, never better, with a parity test.
- quant-engineer: risk-cap cancel divergence, scratch-vs-no-trade population, and polling granularity. Applied as stated known differences, handed to the metric/parity spec.
- quant-engineer: warning flood on a deliberate 0 risk, and `account_pct` reading `risk_pct`. Applied (D2 Numerics).
- quant-engineer: `max_open_positions` type edges. Applied (validator table and tests).
- quant-engineer: readers keyed on `stop_entry_fill`. Checked: no code reader (`git grep` finds only `plan_manager.py:951,974` and tests). Applied: the comment is updated.


## Implementation panel (2026-10-26)

- **risk-manager — ADVISORY, applied to D2 assurance:** candidate portfolio/correlated heat uses stored `risk_pct` rather than actual sized risk (`scan_run.py:1167`, `short_run.py:240`). This existing gap remains a separate scan-risk follow-up; v187's per-trade ceiling does not certify accurate portfolio heat in every sizing mode.
- **staff-engineer — BLOCKING classification rejected; underlying defect accepted as a follow-up:** cancellation persistence and placeholder deletion are separate writes (`plan_manager.py:1020,1030,827,850`). A delete failure can leave an open placeholder after cancellation; `_on_event`'s inherited catch logs it without recovery. Both the separate writes and catch exist in the merge's first parent. V187-8 explicitly extends this shared hook, while cross-store transaction integrity is the separate v189 D3 workstream. v187 fixes event coverage and successful-write behavior, and does not claim atomic cancellation during database failures. Expanding it into a general transactional lifecycle redesign after its final verification would cross that scope boundary. The cost of this deferral is a stale open placeholder after such a database failure; the transaction follow-up must cover cancellation plus placeholder deletion together and include rollback/retry tests.
- **quant-engineer — CLEAN:** sizing finite guards, clamping/rounding, gap-sizing compatibility and live-limit helper parity reviewed over `a7c30ecf^1...a7c30ecf`; no new numerical or lookahead finding. No feature-history computation changed.

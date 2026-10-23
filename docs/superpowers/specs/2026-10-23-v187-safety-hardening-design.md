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
2. **The 2% risk cap is not enforced in `risk_pct` mode.** `set_risk_pct` (`planning/account.py:199`) stores any float. `compute_position_size` (`:452`, `:500-503`) sizes from it directly; `RISK_CEILING_PCT` (`edge/sizing.py:19`) is applied only inside `kelly_risk_pct` / `vol_target_risk_pct`, and `effective_risk_pct` takes the `min` of the candidates, so with no edge estimate the stored value passes unclamped. `!account risk 10` sizes every alert (`scanning/analyze.py:254`) at 10%; a negative value yields negative shares that slip under every cap (`position_value > max` is false), inverting P&L. The `!account` reply (`commands/account.py:58`) tells the user there is "the frozen 2% hard cap", which is untrue in this path. The `.env` help for `RISK_PER_TRADE_PCT` (`swingbot/config.py:521-527`) says nothing in the pipeline sizes from it, which is also untrue.
3. **Live limit entries fill as stop entries.** `PlanManager._step_pending` (`planning/plan_manager.py:932-955`) fills every pending plan on `price >= trigger` (bull) / `price <= trigger` (bear) at `max/min(price, trigger)`. That is stop-entry semantics. A buy limit would fill when price rises above it, at a price worse than its own limit. The backtest fills limits correctly (`exit_sim._limit_entry_exit`, `lifecycle.limit_hit` / `limit_fill_price` / `limit_cancelled`). Limit strategies (`Downtrend Overbought Fade`, `FIB_LIMIT`, `params.py:70,80`) are masked today, so this is latent until one is promoted.

Production state, checked read-only on 2026-10-23: `sizing_mode=risk_pct`, `risk_pct=1.0`, `max_position_pct=5.0`, absolute caps 1000 / 100, `max_open_positions=30`, nothing negative or non-finite. **No data migration is needed.**

## Decisions

### D1 — State-changing Discord commands require server administrator

Gate exactly the commands listed in Why §1, and no others. Read-only commands stay open: `!account` / `/account show`, `!trades`, `!trade` / `/trade show`, `!performance`, `!pnl`, `!summary`, `!tradecharts`, `!check`.

- **Prefix commands:** `@commands.has_permissions(administrator=True)`, the decorator `growth.py:120` uses. Refusals already go through `bot_core.on_command_error`.
- **Slash commands:** `@app_commands.checks.has_permissions(administrator=True)` on each gated command. `/trades-clear` and `/trades-clear-history` are top-level, so they also get `@app_commands.default_permissions(administrator=True)`, which hides them from non-admins in the client. The `/account` and `/trade` subcommands cannot carry `default_permissions` individually, because discord.py allows it only on top-level commands and the groups hold the read-only `show`. They rely on the check alone. Refusals already go through `slash.py` `APP_CHECK_REPLIES[MissingPermissions]` (ephemeral).
- **Coverage test.** A test enumerates the bot's prefix commands and app-command tree, and asserts the gated set equals one declared constant (`STATE_CHANGING_COMMANDS`, held in the test module). A command that changes state but is not gated, or gated but not listed, fails CI. When a later command adds a state change, it updates the constant deliberately.

### D2 — One validator for every account setter; sizing clamps as a backstop

Add `_validated(key, value)` in `planning/account.py`, called by every `set_*` before `save_account_config`:

| Setter / key | Accepts | Notes |
|---|---|---|
| `risk_pct` | finite, `0 < x <= RISK_CEILING_PCT` | import the constant from `edge/sizing.py`; never a second `2.0` literal |
| `position_pct`, `max_position_pct` | finite, `0 < x <= 100` | |
| `max_position_value_absolute`, `max_risk_amount_absolute` | finite, `x >= 0` | `0` keeps meaning "off" |
| `base_balance` | finite, `x > 0` | |
| `max_open_positions` | integer, `x >= 1` | a float with a fractional part is refused, not truncated |
| `sizing_mode` | unchanged | already normalised by `set_sizing_mode` |

- An invalid value raises `ValueError` whose message names the setting and its allowed range. The Discord handlers catch it and reply with that message, saving nothing. A reply rather than an exception keeps the user-facing text identical between prefix and slash.
- **Backstop.** `compute_position_size` clamps `risk_pct` into `(0, RISK_CEILING_PCT]` after the edge chain and the OPEX multiplier. A non-positive or non-finite value returns `None`, the same as the existing "can't size" path. This covers a hand-edited or legacy `account` row the setter never saw. The clamp is silent in the sizing result, so it needs no new field, and it logs one warning per process when it fires.
- **Copy.** Fix `commands/account.py:58` so the "hard cap" sentence is true (it now is). Rewrite the `RISK_PER_TRADE_PCT` help (`config.py:523-527`) to say it seeds the account's risk-per-trade, which sizes every alert, capped at 2%. Set that `Field`'s `max=2`. The help text on `MAX_POSITION_*` fields that also say "informational only" is checked and corrected in the same pass if equally stale.

### D3 — Live limit entries fill like the backtest

In `_step_pending`, after the expiry / session-window checks and before the existing stop-entry branch, add a limit branch for `plan.entry_type == "limit"`:

1. If `lifecycle.limit_hit(plan, price, price)` holds (a tick is a one-print bar, which keeps the `limit_strict_fill` rule intact), fill at `lifecycle.limit_fill_price(plan, price)`. That is the limit or better, never worse.
2. Otherwise, if `lifecycle.limit_cancelled(plan, price, price)` holds, cancel with reason `limit_cancelled` and emit a `cancelled_limit` event.
3. A fill passes through the **same** risk-cap check (`planned_loss_pct` vs `plan_stop_ceiling`) and the same `filled` event as a stop entry. Only the transition reason differs: `limit_fill` instead of `stop_entry_fill`.

The fill check runs before the cancel check, as in `_limit_entry_exit`. The stop-entry branch is unchanged for every other `entry_type`. To keep `_step_pending` under complexity 15, the fill / risk-cap / record step moves into one helper shared by both branches.

**Out of scope here:** live invalidation firing on any tick while the backtest checks it on the close (`_step_pending` → `pending_invalidated`, `lifecycle.py:144`). That is a live-vs-backtest parity question, and it belongs to the metric/parity spec.

## Testing

- **D1:** for each gated command, a non-admin invocation is refused with the existing message and leaves state unchanged; an admin invocation succeeds. The coverage test from D1. The read-only commands still answer for a non-admin.
- **D2:** a validator table test over NaN, ±inf, negative, 0, `RISK_CEILING_PCT`, `RISK_CEILING_PCT + 0.01`, 100, 100.01 and `2.5` for `max_open_positions`. A handler test checks that an invalid value replies with the message and does not save. `compute_position_size` with a legacy `risk_pct=10` sizes at 2%; with `risk_pct=-1` or NaN it returns `None`. Existing sizing tests stay green unchanged.
- **D3:** bullish and bearish limits, each covering touch fill, strict-fill refusal on an exact touch, gap-through fill at the better price, cancel beyond `limit_cancel_level`, a tick that both fills and is beyond the cancel level (fills), and risk-cap cancellation on a limit fill. Every existing `_step_pending` stop-entry test passes unchanged.
- While iterating, run `testrun.py changed`. The full suite runs once, as the plan's final task.

## Not in this spec

Everything else from the 2026-10-23 audit goes to the next three specs: book integrity and partial-trade display, metric definitions (counting unit, day, ledger, snapshot, drawdown), and frontend hygiene.

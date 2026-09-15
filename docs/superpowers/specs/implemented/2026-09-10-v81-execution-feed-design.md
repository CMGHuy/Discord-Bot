# v81 — The execution feed: Discord messages you can place orders from

**Version:** ui 1.14.0 · bot 1.6.5
**Bump:** bot minor, ui patch
**Edge:** harvest
**Depends on:** v79's code merged to `main` — both edit
`swingbot/core/planning/plan_manager.py` (v79 Task 1 edits `_close_runner`).
Check: `git log --oneline main --grep="feat(v79)"` is non-empty.

## What this is

The simple-alerts channel (`DISCORD_CHANNEL_TRADES_SIMPLE_ID`) becomes an
**execution feed**: every message in it is something to do at a broker, phrased
as an order instruction, and every change to a position the bot is tracking
reaches it — including the trailing-stop moves that today send nothing.

`Bump:` **bot minor** — the one channel that pings the reader changes shape
entirely (status reports become order tickets and instructions) and gains a new
message type; someone who read it yesterday has to read it anew. **ui patch** —
the admin Settings page gains one control, `TRAIL_NOTIFY_MIN_R`.

`Edge:` **harvest**, stated precisely: pooled paper `ExpR` is unchanged **by
construction** — no exit, fill, gate or sizing rule changes. The R this buys is
the reader's **real-account** R: the human partner trades real money off these
alerts with resting broker orders, and every place the messages fail to say
what the bot's paper position just did is a place the real position diverges
from the validated one. It is not measurable from paper data; see "Verification".

## Why — measured 2026-09-10

1. **Trail ratchets are silent.** `_step_partial` moves `working_stop` along the
   chandelier trail (`plan_manager.py:414-428`) and returns `[]`. A reader's
   broker stop stays at the runner floor while the paper stop climbs; a runner
   that gives back gains exits later, and worse, in real money than on paper.
2. **The pinging alert is not an order ticket.** `build_simple_alert`
   (`alert_embeds.py:224-290`) has no order type, no expiry, no invalidation
   rule, no TP1 fraction, no share count and no break-even rule.
   `entry_line()` (`plan_table.py:52`) renders "BUY STOP above … (expires in N
   bars)" but has **no caller** outside its tests. The full alert gets the order
   type from `explain.py:77-83`; expiry appears in no alert at all.
3. **Lifecycle messages are status reports.** `PLAN_EVENT_STYLES`
   (`lifecycle_embeds.py:289-301`) says what happened, never what to do; a
   `closed` event shows only `Exit` (`lifecycle_embeds.py:337-338`).
4. **Break-even takes effect next session.** `_active_stop` keeps the original
   stop for the rest of the session `be_armed_session` names
   (`plan_manager.py:317-322`). An instruction without timing puts the reader's
   stop tighter than the bot's for the afternoon.
5. **Extended-hours exits are on.** `EXTENDED_HOURS_EXIT_CHECK` defaults `true`
   (`config.py:550`) and production does not override it. The bot can close on a
   confirmed premarket/after-hours print where resting broker stops do not fire.
6. **Delivery is lossy.** `notify_plan_events` has no per-event `try`
   (`lifecycle_embeds.py:342-363`); one failed send aborts the batch and
   `loops.py:581-584` logs and drops the rest. Nothing is retried.

Production flags read the same day: `PLAN_ENGINE_V2=on`,
`INTRADAY_MANAGER_V2=true`, `NEAR_CLOSE_ALERTS_ENABLED=false`,
`PYRAMIDING_ENABLED=false`, `ACCOUNT_BALANCE=1000000`, `RISK_PER_TRADE_PCT=1.0`.

## Decisions taken in the brainstorm (human partner, 2026-09-10)

- The reader trades real money, places **resting orders when the alert posts**,
  and has a broker with native trailing stops.
- **Exact stop pings, not a native broker trail.** A broker trail follows the
  intraday high by a fixed amount with no floor; the bot's chandelier trails
  `runner_high_close` by a re-read ATR(14) and never drops below the runner
  floor. That is a different, never-validated exit rule.
- **Pings are immediate**, once the stop has moved `≥ TRAIL_NOTIFY_MIN_R`
  (default `0.25`) of the plan's initial risk since the last delivered stop.
- **The execution feed is the simple-alerts channel.** The history channel
  keeps a **silent** copy of each lifecycle message.
- **Share counts use the bot's own sizing** (`account.compute_position_size`),
  chosen knowing production sizes against $1,000,000 at 1% risk.
- **Cap-blocked alerts say PLACE with a warning**, mirroring the paper book the
  stats come from (D1).
- **Architecture A:** a pure instruction projection plus one Discord renderer.
- **At-least-once delivery for every instruction**, not only stop moves.

## D1 — The verb mirrors the bot's own paper action

A ticket says **PLACE** exactly when `scan_run.py:682` logs a paper trade for the
item (`item.all_requirements_met and not already_open`). Otherwise it says
**DO NOT PLACE** and names the reason: the unmet requirements (listed), or
"already open". The implementation passes that one predicate's result from
`scan_run.py` to the ticket, not a second copy of it.

**Heat, cluster and kill-switch blocks do not change the verb.** They are set at
`scan_run.py:794-824`, after the trade is logged (`:714`) and the plan persisted
(`:742`), and they only label the alert — the paper trade keeps its full
`compute_position_size` share count (`performance.py:483-486`), and the plan is
managed to its end. So the ticket says **PLACE** and carries a warning line
above the orders naming the block and its numbers (e.g. `⚠ over portfolio heat
cap — open 6.2% / cap 6.0%; the bot tracks this at full size`). The reader
decides per trade (human partner, 2026-09-10).

Plans reach `PlanStore` only inside that same logging block
(`scan_run.py:733-745`), so every lifecycle event belongs to a position the bot
is paper-trading. No separate tracking filter is needed.

## D2 — The catalog

Long side shown; a short swaps each verb (entry `SELL STOP below`, stop
`BUY STOP`, TP1 `BUY LIMIT`, exit `BUY TO COVER AT MARKET`). Share counts are
whole shares, rounded down; TP1 takes `floor(shares × tp1_fraction)`, the runner
the remainder.

| Trigger | Message |
|---|---|
| Alert, stop entry | **PLACE** · `BUY STOP 102.50 · 2,439 sh (risk $10,000)` · `STOP 98.40` · `TP1 LIMIT 106.00 · 1,219 sh (50%)` · `RUNNER 1,220 sh → TP2 110.00 / trail 3.0×ATR — stop moves are pinged here` · `Stop → entry once price reaches 104.20` · `Cancel if: not triggered by the close of ≈ Thu 17 Sep (5 sessions), or price reaches 98.40 first` |
| Alert, market entry | **BUY AT MARKET ~102.50**, then the same bracket lines |
| Alert, heat / cluster / kill switch | **PLACE** with the D1 warning line above the orders |
| Alert, not logged | **DO NOT PLACE** — unmet requirements or already open, then the levels for reference |
| `filled` | **FILLED @ 102.61** (bot). Confirm your broker filled; the bot's R is measured from 102.61 |
| `be_moved` | **MOVE STOP → 102.61 after today's close** (break-even; keep 98.40 until then) |
| `tp1_partial` | **TP1 FILLED 1,219 sh @ 106.00 (+0.8R)** · **MOVE STOP** on the runner **→ 104.87 now** (runner floor) |
| `stop_moved` (new) | **MOVE STOP → 107.30 now** (trail; +0.31R since the last ping) |
| `cancelled_expired` | **CANCEL BUY STOP 102.50** — not triggered within 5 sessions |
| `cancelled_invalidated` | **CANCEL BUY STOP 102.50** — price reached the stop 98.40 before triggering |
| `closed`, regular session | **EXITED @ X** — stop / break-even / TP1 / runner floor / trail / TP2, `+1.4R total`. If your broker order did not fill: **CLOSE AT MARKET** |
| `closed`, extended session | **CLOSE AT MARKET** — the bot exited on an after-hours print @ X; resting stop orders do not fire outside regular hours |
| `closed` while the reader's stop lagged | adds: `your last pinged stop was 106.90 — that order may still be open` |

`+R total` is the fraction-weighted sum over `plan.legs_realized`. A fuller
close embed (P&L, per-leg lines, time held) is out of scope.

## D3 — Timing is part of every stop instruction

A stop instruction says **now** or **after today's close**. It says "after
today's close" exactly when `plan.be_armed_session == session_date(now)`, the
same condition `_active_stop` uses. The runner floor and trail moves are
**now**: `_step_partial` has no same-session guard (`plan_manager.py:391-399`).

## D4 — Expiry is counted in sessions; the date is approximate

Sessions left come from `plan_view`'s `bars_to_expiry` (`plan_view.py:61-63`)
with `bars_since_created=0` at alert time, so the ticket and `!plans` agree.
The last session that can trigger is bar `expiry_bars` after `created_at`
(`lifecycle.py:133`, strict `>`; `_bars_since` counts rows dated after
`created_at`). The date shown is `created_at` plus `expiry_bars` **weekdays**,
always prefixed `≈` — there is no holiday calendar in the repo, and a holiday
moves the real date one session later.

The invalidation clause is `pending_invalidated` (`lifecycle.py:140`): price at
or through the stop before the trigger, checked against the live price.

## D5 — At-least-once delivery; the manager is the only writer

`PlanStore.update` replaces the whole plan dict and every writer saves the full
list from its own snapshot (`plan_store.py:59-80`), so the notifier must not
write plans. Two new fields and one acknowledgement path:

- `TradePlanV2.notified_stop: float | None = None` — the stop last **delivered**.
  `None` reads as `stop_loss` (the ticket delivered it).
- `TradePlanV2.pending_notice: dict | None = None` — the latest FILLED, CANCEL
  or EXIT instruction not yet delivered, stored whole as `{"transition",
  "detail", "at"}`; `None` when nothing is owed, which includes every plan
  persisted before v81 (never resent). A later notice replaces an unsent
  earlier one: an EXIT supersedes an undelivered FILLED. *(Planning finding,
  2026-09-10: the first draft's `notified_status="UNSENT"` marker could not
  rebuild a pre-TP1 exit — those closes append nothing to `legs_realized`, so
  the exit price exists only in the event — and left FILLED with no re-send.)*

**Stop rule.** After `_step()` in a **regular** session, for a plan still ACTIVE
or PARTIAL whose tick produced no stop or notice event:
if `|resting_stop(plan) − last_told| ≥ TRAIL_NOTIFY_MIN_R × |entry_price −
stop_loss|`, emit `PlanEvent(plan_id, "stop_moved", {"old", "new", "r_moved",
"effective": "now" | "next_session"})`. Break-even (1R) and the runner floor
(above 1R) always clear the threshold, so a failed `be_moved` or `tp1_partial`
send is re-sent as `stop_moved` on the next tick. `resting_stop` (new, in
`plan_manager.py`) is the stop to leave resting, not today's `_active_stop`. It
is `effective_stop` except for a PARTIAL row persisted before v39 with no
`working_stop`, where it returns the runner floor `_step_partial` falls back
to — `effective_stop` would return the original risk stop there, the display
bug v73 removed *(planning finding)*. The threshold is clamped to `[0.01, 1]`
in `plan_manager.trail_notify_min_r()`: Field `min`/`max` bind only the admin
API (`admin/api_v1/system.py:154`), not `.env` loading *(planning finding)*.

**Notice sweep.** Each tick, before stepping, every plan whose `pending_notice`
was queued within the last 5 calendar days re-emits it unchanged; an older one
logs one warning and is dropped. Re-emitted events never pass through
`_on_event`. When `trade_monitor` has no open trade — exactly the state after
the last position closes — it runs the sweep alone (`run_notice_sweep`), so
that EXIT is re-sent too *(planning finding: `trade_monitor` returns before the
manager tick when nothing is open, `loops.py:531-533`)*.

**Acknowledgement.** `notify_plan_events` returns the deliveries it completed —
`Delivery(plan_id, "stop", price)` or `Delivery(plan_id, "notice", transition)`. `trade_monitor`
(`loops.py:579-584`) passes them to a new module function
`plan_manager.ack_notified(deliveries)`, which reloads the manager's own store,
sets the fields and saves — in the same loop, after the send, before the next
tick. A send counts as delivered when it reaches **any notifying destination**:
the execution feed, or the history channel when the feed is unset or its send
raised (that copy then keeps its notification — the hand-back rule
`_send_alerts` already uses, `alerts.py:231-249`).

**Consequences, all intended.** A failed acknowledgement write re-sends — a
duplicate, never a loss. The first tick after deploy sends one **MOVE STOP** per
open plan whose `resting_stop` already differs from its `stop_loss` by the
threshold: a catch-up for stops that were never pinged. Per-event `try` blocks
stop one failure from dropping the batch; repeated failures log at most one
warning per plan per 15 minutes.

**Closed events are stamped in `poll()`**, where `regular` is known
(`plan_manager.py:186-192`): `detail["session"] = "regular" | "extended"` and
`detail["notified_stop"] = last_told` and `detail["bot_stop"]` (the stop the
bot held); `tp1_partial` events gain `detail["working_stop"]`. `_close_runner` and `_close_extended` are
not edited, which keeps the v79 overlap to `poll()`.

`_on_event` ignores `stop_moved`: no trade-log bookkeeping changes.

## Architecture

| Unit | Does | Depends on |
|---|---|---|
| `swingbot/core/presentation/instructions.py` (new, no `discord` import) | `Instruction(verb, ticker, direction, lines, reason)`; `ticket_for(plan, sizing, blocked)`; `instruction_for(plan, event)` — D1-D4 | `plan_view`, `plan_numbers_for_display`, `tokens` |
| `swingbot/core/scanning/execution_embeds.py` (new) | `render(instruction) -> discord.Embed` via `ui.apply_chrome`; the only Discord-aware piece | `instructions`, `presentation` |
| `alert_embeds.build_simple_alert` | becomes a wrapper over `ticket_for` + `render` for items with a v2 plan; an item without one (`PLAN_ENGINE_V2` not `on`) keeps today's body unchanged; `scan_run.py:849` unchanged | the two above |
| `plan_manager.py` | stop rule, notice sweep, `pending_notice`, event stamps, `resting_stop`, `Delivery`, `ack_notified`, `run_notice_sweep` | `effective_stop`, `breakeven_trigger`, new fields |
| `lifecycle_embeds.notify_plan_events` | feed send + silent history copy, per-event `try`, returns deliveries; fills stop posting to `DISCORD_CHANNEL_TRADES_ID` | `execution_embeds`, `silence()` |
| `loops.trade_monitor` | passes deliveries to `ack_notified` | the two above |
| `plan_types.py` | `TradePlanV2.notified_stop`, `TradePlanV2.pending_notice`; `breakeven_trigger(plan, entry)`, which `_step_active` and the ticket share | — |
| `config.py` | `Field("TRAIL_NOTIFY_MIN_R", …, "Plan Engine v2", default="0.25")`, hot-reloaded; clamped to `[0.01, 1]` in `plan_manager.trail_notify_min_r()` — above 1R a failed break-even send would never be re-sent (D5) | — |

`pyramid_add` keeps today's rendering and does not enter the feed
(`PYRAMIDING_ENABLED=false`); see "Out of scope".

**Persistence.** `plan_from_dict` keeps known fields and defaults the rest
(`plan_types.py:102-104`), so old rows load. v67 stores each plan in a `doc`
JSONB column (`_2a-trading-state-trades.md:332-344`): no column is added, and
v67's Task P2-07 gains a note plus a round-trip assertion for both fields.

**v80.** Its part 4 edits `swingbot/core/presentation/tokens.py`; this spec only
reads tokens. If v80 renames a token used here, the renderer part rebases.

## Parts

- **P1** — `TradePlanV2` fields, config Field, load test for an old row.
- **P2** — `instructions.py` and `tests/presentation/test_instructions.py`.
- **P3** — `plan_manager.py`: stop rule, notice sweep, `pending_notice`, stamps,
  `ack_notified`; tests under `tests/planning/`.
- **P4** — `execution_embeds.py`, `build_simple_alert` wrapper; the shape tests
  in `tests/scanning/test_simple_alerts.py` rewritten to the ticket.
- **P5** — routing in `notify_plan_events`, `trade_monitor` wiring; routing tests.
- **P6** — `test_surface_agreement.py` gains the instruction surface; v67 P2-07 note.
- **P7** — `scripts/dev/preview_execution_feed.py`: prints every instruction for
  fixture plans (long, short, blocked, BE today, extended close) to stdout.
- **P8** — full suite, release.

## Parallelisation

- **Sequential:** P1 before P2 — the ticket reads `breakeven_trigger`, which P1
  adds to `plan_types.py` *(planning finding: the break-even formula was inline
  in `_step_active`; one copy, not two)*.
- **Group 2 (parallel):** P3, P4, P6 — disjoint files. P3 consumes P1's fields;
  P4 and P6 consume P2's `Instruction`; none consumes another's output.
- **Sequential:** P3 also waits on v79 merging (shared `plan_manager.py`). P5
  after P3 and P4 — it wires `ack_notified` and `render`, and edits
  `test_simple_alerts.py` after P4 has. P7 after P4. P8 last.

## Testing

**Pure (`test_instructions.py`).** One case per verb, long and short. Ticket:
stop entry, market entry, DO NOT PLACE for unmet requirements and for already
open, PLACE plus the warning line for each of heat, cluster and kill switch; runner line with and without
`tp2`; TP1/runner share split rounds down; expiry sessions from `bars_to_expiry`;
the `≈` date skips weekends and always carries `≈`; BE "after today's close"
exactly when `be_armed_session` is today. The surface-agreement test asserts a
partial runner's instruction stop equals `plan_view`'s and is never the original
risk stop.

**Manager.**
- A 0.24R stop move emits nothing; 0.25R emits `stop_moved`.
- No `stop_moved` in a tick that emitted `be_moved`, `tp1_partial` or `closed`.
- An unacknowledged stop re-emits next tick; an acknowledged one does not.
- A new manager on a persisted, current `notified_stop` does not re-ping.
- The deploy catch-up emits once per moved open plan, then stops after ack.
- A `pending_notice` is re-emitted until acknowledged; `None` never is; one
  older than 5 days is dropped with one warning; with no open trade,
  `trade_monitor` still runs the sweep.
- Closed events carry `session` and `notified_stop`; extended closes say `extended`.
- **Parity:** the existing scenarios in `test_plan_manager_partial.py` replay
  with `notified_stop`/`pending_notice` set to arbitrary values and yield
  identical exits, fills, legs and R. `lifecycle.py` has no diff in this plan.

**Routing.** The feed pings and the history copy is silent; an unset or raising
feed hands the notification to history and still counts as delivered; one
raising event does not drop the rest; fills no longer reach
`DISCORD_CHANNEL_TRADES_ID`; `test_no_adhoc_color` covers both new modules.

## Verification

- The plan's final task runs the full suite once.
- Before merge, P7's preview output is read end to end by the human partner.
- After deploy: the first live `stop_moved` in `/opt/swing-bot/logs/*.log` is
  checked against that plan's `working_stop` in the store, and the deploy
  catch-up count is compared against open PARTIAL/BE-armed plans.

## Out of scope

- **Any change to what the bot trades or how it exits** — fills, stops, trail,
  gates, sizing, `lifecycle.py` and the exit simulation.
- **A fuller plan-close embed** (P&L, per-leg lines, time held).
- **Near-close warnings on plan trades** read the frozen `stop_loss`/`take_profit`
  (`analyze.py:329-335`; frozen per `performance.py:1151-1158`), so a runner can
  be warned about a TP1 it already banked. Dormant: `NEAR_CLOSE_ALERTS_ENABLED=false`.
  Fix before enabling.
- **`pyramid_add` has no style** in `PLAN_EVENT_STYLES` and renders a bare
  "Plan update". Dormant: `PYRAMIDING_ENABLED=false`. Fix before enabling.
- Threads per plan, editing the original alert in place, Components V2.
- A native-trail ticket, any broker integration, or placing orders — the bot
  never places orders.
- A separate real-account sizing setting.

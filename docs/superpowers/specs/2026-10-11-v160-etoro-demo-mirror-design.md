# v160 — eToro demo mirror: plan events become demo-account trades

**Version:** ui 1.22.1 · bot 2.3.1 (at writing)
**Bump:** bot minor (the bot starts placing orders on an external account, which is a new observable behaviour, but only when the flag is on)
**Edge:** none (integrity). It measures how the bot's plans actually execute at the broker (slippage, fees, overnight cost) so Stage 2 is decided on evidence. It adds no strategy, threshold or filter.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, quant-engineer, risk-manager
**Status:** draft
**Depends on:** v159 § B2 (`swingbot/core/infra/etoro_guard.py` with `assert_demo`, `ETORO_ALLOW_REAL`, the AST scan) must be merged before this plan's first task that touches eToro code. v159 § B4 (`reconciler` agent) is reused for the manual reconciliation read, not rebuilt.

The panel line names seats that exist today. v159 adds `execution-specialist` and requires it on every eToro spec above v159. When v159 lands, its plan amends this line to `execution-specialist, risk-manager, staff-engineer`, or this plan's first task does if v159 lands first.

## Goal

Roadmap stage 1 (`docs/claude/etoro-roadmap.md`): every main-ledger trade plan the bot fills on paper is also traded, automatically, on the partner's eToro **demo** account. The bot's own plan ledger stays the single source of truth. eToro follows it, and every order and fill is recorded so a comparison report can show what the paper results would have looked like at a real broker.

## Decisions taken in the brainstorm (2026-10-11)

| Question | Decision |
|---|---|
| Broker | eToro, for both stages (`etoro-roadmap.md`, decided 2026-10-11) |
| Autonomy | **Fully automatic on demo.** This spec is the durable authorisation the roadmap asks for; it covers `account: demo` only and grants nothing for real |
| Which plans | `ledger == "main"` only |
| Sizing | 2% dollar-risk rule on a configured account size (`ETORO_ACCOUNT_SIZE`), not the demo's virtual equity |
| Bearish plans | Mirrored as CFD shorts (`sellShort`, stop attached) |
| Approach | **A, event follower.** Orders go out at the bot's own fill event. Approach B (resting limit orders at eToro at alert time) is out of scope and may be revisited only if the comparison report shows limit-entry fills lagging |

## eToro API facts this design rests on

Verified 2026-10-11 against the eToro Public API OpenAPI document v1.387.0 through the MCP catalog (`get-route-spec`):

- **Open:** `POST /api/v3/trading/execution/demo/orders` (`createTradingExecutionDemoOrdersV3`). Body: `action: open`, `transaction: buy|sellShort`, exactly one of `symbol`/`instrumentId`, exactly one of `amount`/`units`/`contracts`, `orderType: mkt|mit|limitIOC`, `leverage` (default 1), `stopLossRate`, `takeProfitRate`, `stopLossType: fixed|trailing`. On v3, `settlementType` (`real|cfd|...`) is **mandatory** for non-MIT orders. `amount` is USD only. Returns 202 with `orderId` and `referenceId` (which echoes `x-request-id`). The order is processed asynchronously.
- **Outcome:** `GET /api/v2/trading/info/demo/orders:lookup` by `orderId` or `referenceId`. `status.id` 3 (Filled) or 5 (PartiallyFilled) means executed; 4 or 10 means rejected (`errorCode`, `errorMessage`); 1, 2, 11 or 12 means still in flight. The response carries `positionId`, `avgPrice`, `units` and fees.
- **Partial or full close:** `POST /api/v1/trading/execution/demo/market-close-orders/positions/{positionId}` (close by units).
- **Move stop or target:** `PATCH /api/v2/trading/demo/positions/{positionId}` (`stopLossRate`, `takeProfitRate`, `stopLossType`, `clearTakeProfit`). Asynchronous, 60 requests per 60 s default pool.
- **Eligibility:** `POST /api/v2/trading/info/demo/eligibility`, a read-only POST: allowed directions, leverages, `leverageConfigs[].settlementType`, minimum exposure, maximum units. The spec says the result can be cached per session.
- **Rate limit:** the order routes (open, close, cancel, every version) **share one budget of 20 requests per 60 s**.
- **Resting entries:** a market-if-touched order only rests at a price *better* than the market (below it for a long). It cannot express the bot's `stop_entry` breakouts. This is why approach A places market orders at the fill event.
- **Base URL and auth headers** (`x-user-key`, `x-api-key`, `x-request-id`) are confirmed in the plan's first client task against eToro's developer docs. The MCP catalog does not expose the host.

## Design

### Components: new package `swingbot/core/broker/`

| Unit | Job | Depends on |
|---|---|---|
| `etoro_client.py` | Thin REST client. Sends the auth headers from config and a caller-supplied `x-request-id`. **Every request has a hard 10 s timeout.** A non-blocking token bucket of **15 per 60 s** sits over the shared order budget: when it is empty, the call returns `deferred` at once and **never sleeps**. Returns typed results (`status_code`, body, retry-after, `deferred`). Calls `etoro_guard.assert_demo("demo")` on construction. **Only demo route paths are written in it**; a guard test fails on any real-account path. | `requests`, `config`, `infra.etoro_guard` |
| `mirror.py` | **Pure translator.** `actions_for(event: PlanEvent, plan: TradePlanV2, sent: SentState) -> list[BrokerAction]`. `sent` is what the store says was already sent for this plan. No I/O, no clock. | `planning.plan_types` |
| `sizing.py` | `units_for(entry, stop, account_size, risk_pct, precision) -> float`. Pure. Clamps `risk_pct` through `risk_limits.capped_planned_loss_pct`, so the 2% hard cap holds whatever `.env` says. Returns 0 for a zero or NaN stop distance. | `core.risk_limits` |
| `pre_open.py` | **Pure.** The send-time checks for an `Open`, run against a live quote (§ Pre-open checks). Returns a skip reason or `None`. | `edge.heat`, `edge.correlation`, config |
| `executor.py` | Runs actions in per-plan order under a per-tick time budget. Writes each row before sending, looks up in-flight orders, runs the daily reconciliation, and applies the outcome rules below. | client, repository, `pre_open` |
| `core/db/repositories/broker_orders.py` + Alembic revision | Postgres table `broker_orders`, as a repository under `core/db/`, the persistence boundary (`architecture.md` § Module map, `schema-evolution.md`). | `core/db` |
| `__init__.py` | `mirror_events(events) -> None`, the single entry point the trade monitor calls. | executor |

`broker/` imports from `planning/`, `edge/`, `infra/` and `db/`. Nothing else under `swingbot/` imports `broker/` except `commands/scanning/loops.py`; `tests/broker/test_import_direction.py` pins that, scoped to `swingbot/` (scripts may import it). The plan's architecture task corrects the stale package count in `architecture.md` § Module map and in `CLAUDE.md`, and accounts for the flat `risk_limits.py`, instead of stacking another count on top of the drift.

**Hook:** `swingbot/commands/scanning/loops.py`, **after** `await _post_plan_events(plan_events)`, so Discord delivery never waits on eToro:

```python
if config.ETORO_MIRROR_ENABLED:
    try:
        await asyncio.wait_for(asyncio.to_thread(broker.mirror_events, plan_events),
                               timeout=MIRROR_TICK_BUDGET_S)   # 25 s
    except Exception as exc:
        log.warning("trade_monitor: eToro mirror failed: %s", exc, exc_info=True)
```

Inside `mirror_events`, the executor stops starting new requests once 20 s of the budget are spent. Anything left over stays `queued` for the next tick. The hook runs on every trade-monitor tick, including ticks where `poll()` returns `[]` (quiet hours), so in-flight lookups and the daily reconciliation still run.

**Config** (`swingbot/config.py`, section "eToro Paper Trading", hot-reloaded):
- `ETORO_MIRROR_ENABLED`: bool, default `false`.
- `ETORO_ACCOUNT_SIZE`: float USD, default `0`. With the flag on and a value of 0 or less, every open is skipped with reason `no_account_size`. **It is fixed, not compounded:** demo drawdowns and run-ups never change position size. This keeps every trade's dollar risk comparable for the report. Stage 2 may revisit it.
- `ETORO_RISK_PCT`: float, default `2.0`, clamped to `risk_limits.HARD_MAX_PLANNED_LOSS_PCT`.

There is deliberately no account or environment field. Demo is the only path the code contains.

### Event mapping (`mirror.actions_for`)

**Deduplication.** `poll()` starts with `resend_notices()` (`plan_manager.py:505`), and that re-emits `filled` and `closed` on every tick until Discord acknowledges them, with no marker that the event is a resend. So the mirror never trusts the event stream to be unique. Each action carries an `event_key`:
- the transition for `filled` and `closed`, which happen at most once per plan;
- `tp1_partial`, which happens once;
- the target stop rate for a stop move.

The repository holds a unique index on `(plan_id, action, event_key)`. An action whose key is already present is dropped before any request is sent. `seq` is then the next free per-plan sequence number, assigned only to an action that survives deduplication.

Every event whose plan has `ledger != "main"` maps to `[]`. Every non-`filled` event for a plan with no `filled` `open` row maps to `[]`. A plan is never adopted mid-lifecycle; for example, a plan already open when the flag was turned on stays paper-only.

| `PlanEvent.transition` | Actions |
|---|---|
| `filled` | `Open`: `transaction = buy` (bullish) or `sellShort` (bearish); `orderType = mkt`; `leverage = 1`; `units` from `sizing.units_for(...)`; `stopLossRate` = `plan.stop_loss` rounded to the instrument's rate precision; `takeProfitRate` = the rule below; `stopLossType = fixed`. `settlementType` is resolved by the executor from eligibility: a long is `real` when eligible at leverage 1, else `cfd`; a short is `cfd`. Pre-open checks run first. |
| `tp1_partial` | `CloseUnits(round_down(open_units × plan.tp1_fraction))`, then `MoveStop(target)`. The fraction actually closed is recorded. |
| `be_moved`, `stop_moved` | `MoveStop(target)`. |
| `closed` (every reason, including time, stall and structure exits) | `CloseAll`. |
| `cancelled_expired`, `cancelled_invalidated`, `cancelled_risk_cap` | `[]`. Nothing was placed, because orders go out only at fill. |
| `pyramid_add`, `time_exit_due`, `time_exit_unresolved`, any other | `[]`. |

**Stop-move target:** `event.detail["working_stop"]` when present (`plan_manager.py:433`), else `plan.working_stop`. When that is `None`, which means "use `stop_loss`" (`plan_types.py:46`), it is `plan.stop_loss`. The result is rounded to the instrument's precision. **No-widen guard:** a `MoveStop` whose target is farther from the price than the last stop sent (lower for a long, higher for a short), or equal to it, is dropped and logged at WARNING. The mirror enforces this independently of the paper side.

**Take-profit rule:** `plan.tp2` when it is set. Otherwise `plan.tp1` when `plan.tp1_fraction >= 1.0`. Otherwise none: the runner exits on the bot's trail or time rules, and those reach eToro as `MoveStop` and `CloseAll`.

### Sizing and pre-open checks

**Sizing:** `units = (ETORO_ACCOUNT_SIZE × capped(ETORO_RISK_PCT) / 100) / |entry − stop|`.
- `entry` is `plan.entry_price`, the paper fill.
- `stop` is the rounded `stopLossRate` that will actually be sent.
- Units are rounded down to the instrument's precision: whole units unless eligibility reports fractional units.

**Pre-open checks** (`pre_open.py`) run at send time, after a fresh quote (`get-instruments-overview`-equivalent market-data read, recorded as `quote_at_send`). The first failing check is the skip reason; **the size is never adjusted to fit**, and an open is never retried without its stop.

| Check | Skip reason |
|---|---|
| `ETORO_ACCOUNT_SIZE <= 0` | `no_account_size` |
| Not eligible for the direction, or no eligible settlement type at leverage 1 | `ineligible` |
| Stop already breached at the quote (long: `stop >= bid`; short: `stop <= ask`) | `stop_breached` |
| Stop distance from the quote exceeds `MAX_STOP_LOSS_PCT` (`config.py:182`), or is outside eToro's allowed stop bounds for the instrument | `stop_cap` / `stop_too_tight` |
| Rounded units are 0, below the minimum exposure, or above the maximum units | `zero_units` / `below_min_exposure` / `above_max_units` |
| Open mirror heat plus this trade's risk exceeds `PORTFOLIO_HEAT_CAP_PCT` (`config.py:518`), via `edge.heat.heat_check` on the mirror's own open rows against `ETORO_ACCOUNT_SIZE` | `heat_cap` |
| Correlated-cluster heat exceeds `CORRELATED_HEAT_CAP_PCT` (`config.py:524`), via `edge.correlation.cluster_check` | `correlated_cap` |

Each skip logs one INFO line in the form `etoro mirror skipped (<reason>): <ticker> <plan_id> ...`, so it can be grepped the same way as `plan rejected (`. The paper plan is unaffected.

### Executor rules

- **No row, no send.** The row is written with status `sending` **before** the HTTP call. If that write fails, the action is not sent; it is retried next tick from the event-key check. If the write after the response fails (`sending` → `in_flight`), the next tick finds the row still `sending` and recovers it with `orders:lookup` by `referenceId`, which is the request id, before it ever resends. The failure is reported through `core/db/write_failure.py`.
- **Idempotency:** `x-request-id = uuid5(NAMESPACE, f"{plan_id}:{action}:{event_key}")`. A resend after a crash, timeout or 5xx reuses it, and eToro's idempotency stops a second order.
- **Per-plan ordering:** an action for a plan is not sent while an earlier `seq` for the same plan is not final. It stays `queued` across ticks, in order.
- **Outcomes:**
  - 202 → `in_flight`, looked up each tick until final.
  - Filled or partially filled → `filled`, with `position_id`, `avg_price`, `units_filled` and `filled_at` recorded.
  - Rejected → `rejected`, with `error_code` and `error_message`. Never retried.
  - 429 or a deferral from the bucket → `queued`, retried no earlier than `Retry-After`.
  - 400 → `rejected`. 401 or 403 → `rejected`, plus one WARNING per process naming the missing scope.
  - Close or patch on an already-closed position (`631`, `632` or 409) → `closed_by_broker`.
- **At close:** when a position's last close fills, or is found `closed_by_broker`, the executor pulls that trade from trading history and **persists** `net_profit`, `fees` and overnight cost into the row. The report never re-reads mutable live routes.
- **Logging:** one INFO line per sent action and per final outcome, in the style of v111's plan-transition lines. Nothing goes to the Discord alert channels.

### Table `broker_orders`

`id` (PK), `plan_id`, `ticker`, `direction`, `action` (`open|close_units|close_all|move_stop`), `event_key`, `seq`, `request_id` (unique), `order_id`, `position_id`, `status` (`queued|sending|in_flight|filled|rejected|skipped|closed_by_broker`), `skip_reason`, `requested` (JSONB: the exact body sent), `settlement_type`, `stop_sent`, `tp_sent`, `units_requested`, `units_filled`, `fraction_closed`, `quote_at_send`, `avg_price`, `fees`, `overnight_fees`, `net_profit`, `event_at`, `sent_at`, `filled_at`, `error_code`, `error_message`, `created_at`, `updated_at`. Indexes: unique `(plan_id, action, event_key)`, `(plan_id, seq)`, and `status`.

### Comparison report: `scripts/reports/etoro_parity_report.py`

Read-only, over `broker_orders` and the plan store. Definitions are fixed here so the report is reproducible:

- **1R (price)** = `|plan.entry_price − plan.stop_loss|`. This is the paper plan's original risk; `stop_loss` is never mutated (`plan_manager.py:223`). `working_stop` is never used for 1R.
- **1R (dollars)** = `ETORO_ACCOUNT_SIZE × capped risk % / 100`, as recorded with the open row.
- **Paper R** = `Σ leg.fraction × leg.r` over `plan.legs_realized`. These are model fills (`gap_stop_fill`, `poll_stop_fill`) and gross of the friction model.
- **eToro R gross** = realised price P&L in dollars (from `avg_price` and the close fills, sign-adjusted for shorts) ÷ 1R in dollars. **eToro R net** = (persisted `net_profit` − `fees` − `overnight_fees`) ÷ 1R in dollars. The two are reported in separate columns.
- **Entry drift in R**, split in two:
  - *latency* = (`quote_at_send` − `plan.entry_price`) ÷ 1R (price);
  - *execution* = (`avg_price` − `quote_at_send`) ÷ 1R (price).

  Both are sign-adjusted so that a positive figure always hurts.
- **Leg matching:** paper legs, in `legs_realized` order, are paired with the broker's close actions in `seq` order. Each pair shows the paper fraction against `fraction_closed`.
- **Flags:**
  - `closed_by_broker` rows are flagged as divergent exits, never counted as zero slippage;
  - realised eToro R below −1 is counted per direction, which covers gap-through-stop losses on CFD shorts;
  - holding days are shown, so time-exit carry is visible.
- **Pooled totals:** N; mean paper R; mean eToro R gross and net; mean latency and execution drift. Split by direction, by `settlement_type` and by correlated cluster. Skip counts by reason.
- **Snapshot header:** the `broker_orders` row count, the maximum `updated_at`, and the plan-store cut-off.
- **Caveat line, printed on every run:** the mirror enters with a market order at the paper fill event, while the partner's real-money practice is resting orders placed at alert time. The report measures broker frictions on the bot's plans; it does not validate that execution style.

### Daily reconciliation

In-process, run by the executor on the first trade-monitor tick after 16:15 ET each NYSE session. The last-run date is persisted, so a restart does not double-run it or skip it. It compares the demo positions (`GET .../demo/portfolio`) with the repository's `filled`, still-open rows. Positions missing on either side, unit mismatches and stop mismatches are logged at WARNING. **Nothing is corrected automatically.** v159's `reconciler` agent is the on-demand deep read.

### Disable, drain and rollback

- **Disable:** `ETORO_MIRROR_ENABLED=false` makes `mirror_events` a no-op. Open demo positions keep their eToro-side stop and target, so they stay protected but stop following the bot's stop moves and closes. Turning the flag back on resumes only plans that already have a `filled` open row. Events missed while it was off are not replayed, and the next reconciliation reports the drift.
- **Drain:** `scripts/ops/etoro_mirror_drain.py` lists every open position with a mirror row and, with `--execute`, closes each one through the same client (demo-only) and marks the rows. `--dry-run` is the default. Run it before any rollback that removes `broker/`.
- **Rollback:** the Alembic revision is additive; older code ignores the table, so `scripts/ops/rollback_to.sh` needs no downgrade. The table is downgraded (dropped) only by a deliberate decision after a drain, never as part of a routine rollback.
- **Lifetime:** the table and the client outlive Stage 1 and are reused by the Stage 2 spec. `ETORO_MIRROR_ENABLED` is retired when Stage 2 replaces it with its own switch. The owner is the eToro roadmap (`etoro-roadmap.md`).

## Testing

- `tests/broker/test_mirror.py`: every row of the event table, the non-main ledger, a plan with no open row, deduplication of a resent `filled` and `closed`, all three stop-target branches, the no-widen guard for both directions, and every take-profit branch.
- `tests/broker/test_sizing.py`: the risk-percent clamp (`ETORO_RISK_PCT=5` sizes at 2%), rounding, fractional versus whole units, zero and NaN stop distance.
- `tests/broker/test_pre_open.py`: one test per skip reason, including heat and correlated caps on the mirror's own rows.
- `tests/broker/test_executor.py` against a fake client and an in-memory repository:
  - no row, no send;
  - recovery of a row stuck at `sending` by `referenceId`;
  - per-plan ordering across ticks;
  - bucket deferral and 429 handling;
  - the time budget leaving work `queued`;
  - each outcome mapping, and `closed_by_broker`;
  - close-time persistence.
- `tests/broker/test_client.py` against a fake HTTP transport: headers, the timeout passed, the bucket never sleeping, and `assert_demo` called.
- `tests/broker/test_demo_only_paths.py`: no real-account route string anywhere under `swingbot/core/broker/`.
- `tests/broker/test_import_direction.py`, scoped to `swingbot/`.
- The Alembic revision and the repository are tested in the existing migration-test pattern.
- **The suite makes no network call to eToro.** `scripts/ops/etoro_demo_smoke.py` is manual: one 1-unit demo buy with a stop attached, a lookup and a close, using the `.env` keys. It is run once by hand after deploy.

Every new function stays below cyclomatic complexity 15.

## Rollout

1. The plan merges with `ETORO_MIRROR_ENABLED=false`; deploy (`docs/deploy/DEPLOY_HETZNER.md`).
2. The partner generates an eToro key with `demo:write` and `demo:read` (and `market-data:read` for the send-time quote); `get-my-profile-and-scopes` confirms them.
3. On the VM, set `ETORO_USER_KEY`, `ETORO_API_KEY` and `ETORO_ACCOUNT_SIZE` in `.env` by editing in place (never `sed -i` on the bind-mounted file), run the smoke script, then set `ETORO_MIRROR_ENABLED=true` and send SIGHUP. Mirror the non-secret parts (`.env.example`, any ops script) into the repo (`mirror-prod`).
4. A first-week check through `prod-inspector`: the INFO lines, the skip reasons, one reconciliation, and one parity-report run.

## Parallelisation

- **Group 1, in parallel:** `sizing.py` + tests, `mirror.py` + tests, `pre_open.py` + tests, and the Alembic revision + repository. These are pure units, or a new table with no reader yet, and none of them shares a file.
- **Group 2, sequential after v159 § B2 merges:** `etoro_client.py`. It imports `infra.etoro_guard`, which does not exist until v159 lands. This is the plan's one external dependency.
- **Group 3, sequential after Groups 1 and 2:** `executor.py`, including reconciliation. It needs the client's result type, the translator's action type, the pre-open checks and the repository.
- **Group 4, sequential after Group 3:** the config fields, the `loops.py` hook and `broker/__init__.py`. They wire the executor in, and `loops.py` and `config.py` are shared files that other plans touch, so they go in one task. The architecture-doc correction rides along.
- **Group 5, in parallel after Group 3:** the parity report, the drain script, and the smoke script. They read the repository and touch disjoint files.
- **Final:** the full suite, once.

## Out of scope

Resting market-if-touched orders at eToro (approach B); anything on the real account; pyramid adds; an admin UI page; the bomeo-capital.com page; copy trading; eToro guaranteed stops; cancelling the paper plan because the eToro order failed. The paper ledger never depends on eToro.

## Risks

- **eToro's own stop or target fires between bot ticks.** The bot's next `closed` or `MoveStop` then hits an already-closed position, which is recorded as `closed_by_broker`. The two sides fill at different gap prices, so the report flags these as divergent exits.
- **Market closed at the fill event:** the order sits `WaitingForMarket` (`status.id` 11) and stays `in_flight` until it fills. The latency term in the report captures the gap.
- **US-listed ETFs may be ineligible** for an EU demo account (PRIIPs/KID). They come out as `skipped: ineligible` and are counted in the report, which answers the open item in `etoro-roadmap.md`.
- **Mirror heat differs from paper heat**, because the account bases differ. The mirror enforces its own caps, so mirror-only skips (`heat_cap`, `correlated_cap`) are expected and counted.
- **API drift:** the routes are versioned (v1, v2 and v3 coexist). The client pins the exact paths verified above, and the smoke script catches drift.

## Panel review

Run 2026-10-11 on commit `83a2a908`: staff-engineer, quant-engineer, risk-manager.

- staff-engineer 1 (BLOCKING): a resent `filled` or `closed` notice would open a duplicate position -- applied (event-key dedupe with a unique index; request id derived from the event key, not a counter).
- staff-engineer 2 (BLOCKING): the inline hook could stall the trade monitor -- applied (runs after `_post_plan_events`, 10 s request timeout, non-sleeping bucket, 25 s tick budget).
- staff-engineer 3 (BLOCKING): no disable or rollback procedure -- applied (§ Disable, drain and rollback, drain script, no mid-lifecycle adoption).
- staff-engineer 4: semantics of a failed store write -- applied (no row, no send; recovery by `referenceId`).
- staff-engineer 5: store belongs under `core/db/repositories/` -- applied.
- staff-engineer 6: the package count drifts -- applied (the plan corrects `architecture.md` and `CLAUDE.md`).
- staff-engineer 7: the import-direction test would trip on scripts -- applied (scoped to `swingbot/`).
- staff-engineer 8: no reconciliation trigger, and quiet-hours ticks -- applied (in-process after 16:15 ET with a persisted last-run date; the hook runs on empty ticks).
- staff-engineer 9: `working_stop` can be `None` -- applied (event detail, then `working_stop`, then `stop_loss`).
- staff-engineer 10: no owner or retirement -- applied (§ Lifetime).
- quant-engineer 1 (BLOCKING): paper exit and R undefined; legs not joined -- applied (`legs_realized`, joined by `seq`).
- quant-engineer 2 (BLOCKING): which stop defines 1R; gross versus net -- applied (1R from the original `stop_loss`; separate gross and net columns).
- quant-engineer 3 (BLOCKING): fill-event timing against the order price; a breached stop -- applied (event, sent and fill timestamps, `quote_at_send`, latency and execution split, `stop_breached` skip).
- quant-engineer 4: rounded close fraction -- applied (`fraction_closed` recorded and paired per leg).
- quant-engineer 5: rate precision, division by zero, NaN -- applied.
- quant-engineer 6: overnight carry and holding days -- applied.
- quant-engineer 7: reproducibility of live routes -- applied (close-time persistence, snapshot header).
- quant-engineer 8: `closed_by_broker` is not zero slippage -- applied (flagged as divergent).
- risk-manager 1 (BLOCKING): no portfolio or correlated heat cap on the mirror -- applied (`heat_cap` and `correlated_cap` pre-open checks on the mirror's own rows).
- risk-manager 2 (BLOCKING): `ETORO_RISK_PCT` bypasses the 2% hard cap -- applied (clamped through `capped_planned_loss_pct`, tested at 5%).
- risk-manager 3 (BLOCKING): `MAX_STOP_LOSS_PCT` not checked at send time -- applied (`stop_cap` check against the live quote).
- risk-manager 4: fixed or compounded account size -- applied (fixed, stated).
- risk-manager 5: the execution style differs from the partner's resting orders -- applied (caveat line printed by the report).
- risk-manager 6: gap-through-stop on CFD shorts -- applied (R below −1 counted per direction).
- risk-manager 7: eToro stop-distance limits -- applied (`stop_too_tight`; never an open without a stop).
- risk-manager 8: correlated clusters in the report -- applied (split by cluster).
- risk-manager 9: never widen a stop -- applied (no-widen guard).

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
| `etoro_client.py` | Thin REST client. Sends the auth headers from config and a caller-supplied `x-request-id`. Holds a client-side token bucket of **15 per 60 s** over the shared order budget. Returns typed results (`status_code`, body, retry-after). Calls `etoro_guard.assert_demo("demo")` on construction. **Only demo route paths are written in it**; a guard test fails on any real-account path (`/execution/orders`, `/execution/limit-orders`, `/trading/positions/` without `demo`). | `requests`, `config`, `infra.etoro_guard` |
| `mirror.py` | **Pure translator.** `actions_for(event: PlanEvent, plan: TradePlanV2, cfg) -> list[BrokerAction]`. No I/O, no clock. | `planning.plan_types` |
| `sizing.py` | `units_for(plan, account_size, risk_pct) -> float`. Pure. | none |
| `executor.py` | Runs actions in per-plan order. Writes each row before sending, polls in-flight orders on later ticks, and applies the outcome rules below. | client, store |
| `store.py` + Alembic revision | Postgres table `broker_orders` (`schema-evolution.md`; stores are Postgres-only). | `core/db` |
| `__init__.py` | `mirror_events(events) -> None`, the single entry point the trade monitor calls. | executor |

`architecture.md`'s module map gains a `broker/` row (twelve packages). `broker/` imports from `planning/` and `infra/`; nothing in `planning/`, `scanning/` or `backtesting/` imports `broker/`. A test pins that direction.

**Hook:** `swingbot/commands/scanning/loops.py`, directly after `plan_events = await asyncio.to_thread(plan_manager.run_manager_tick)`:

```python
if config.ETORO_MIRROR_ENABLED:
    try:
        await asyncio.to_thread(broker.mirror_events, plan_events)
    except Exception as exc:
        log.warning("trade_monitor: eToro mirror failed: %s", exc, exc_info=True)
```

It runs on every tick, including ticks with no events, so in-flight orders still get polled. An eToro failure can never stop the trade monitor or delay `_post_plan_events`.

**Config** (`swingbot/config.py`, section "eToro Paper Trading", hot-reloaded):
- `ETORO_MIRROR_ENABLED`: bool, default `false`.
- `ETORO_ACCOUNT_SIZE`: float USD, default `0`. With the flag on and a value of 0 or less, every open is skipped with reason `no_account_size`.
- `ETORO_RISK_PCT`: float, default `2.0`.

There is deliberately no account or environment field. Demo is the only path the code contains.

### Event mapping (`mirror.actions_for`)

Every event whose plan has `ledger != "main"` maps to `[]`.

| `PlanEvent.transition` | Actions |
|---|---|
| `filled` | `Open`: `transaction = buy` (bullish) or `sellShort` (bearish); `orderType = mkt`; `leverage = 1`; `units = sizing.units_for(...)`; `stopLossRate = plan.stop_loss`; `takeProfitRate` = the rule below; `stopLossType = fixed`; `settlementType` resolved by the executor from eligibility (long: `real` when eligible at leverage 1, else `cfd`; short: `cfd`). |
| `tp1_partial` | `CloseUnits(round_down(open_units × plan.tp1_fraction))`, then `MoveStop(plan.working_stop)`. |
| `be_moved`, `stop_moved` | `MoveStop(plan.working_stop)`. A no-op when it equals the last stop sent for that position. |
| `closed` (every reason, including time, stall and structure exits) | `CloseAll`. |
| `cancelled_expired`, `cancelled_invalidated`, `cancelled_risk_cap` | `[]`. Nothing was placed, because orders go out only at fill. |
| `pyramid_add`, `time_exit_due`, `time_exit_unresolved`, any other | `[]`. |

**Take-profit rule:** `plan.tp2` when it is set. Otherwise `plan.tp1` when `plan.tp1_fraction >= 1.0`. Otherwise none: the runner exits on the bot's trail or time rules, and those reach eToro as `MoveStop` and `CloseAll`.

**Sizing:** `units = (ETORO_ACCOUNT_SIZE × ETORO_RISK_PCT / 100) / |entry − plan.stop_loss|`, where `entry` is `plan.entry_price` (the paper fill). Units are rounded down to the instrument's precision: whole units unless eligibility reports fractional units. A result of 0 units, an exposure below eligibility's minimum, or more than the maximum units per order means **skip with a recorded reason**. The size is never adjusted to fit.

### Executor rules

- **Per-plan ordering:** an action for a plan is not sent while an earlier action for the same plan is in flight. It stays `queued` and is retried on the next tick, in order.
- **Idempotency:** `x-request-id = uuid5(NAMESPACE, f"{plan_id}:{action_kind}:{seq}")`. The row is written with status `sending` **before** the HTTP call. After a crash, timeout or 5xx, the same id is sent again, and eToro's idempotency stops a second order.
- **Outcomes:**
  - 202 → `in_flight`. Each tick looks the order up until it reaches a final state.
  - Filled or partially filled → `filled`, with `position_id`, `avg_price`, `units` and `fees` recorded.
  - Rejected → `rejected`, with `error_code` and `error_message`. Never retried.
  - 429 → `queued`, retried no earlier than `Retry-After`.
  - 400, 401 or 403 → `rejected`. A 401 or 403 also logs one WARNING per process naming the missing scope.
  - Close or patch on an already-closed position (`631`, `632` or 409) → `closed_by_broker`.
- **Skips** (`ineligible`, `below_min_exposure`, `above_max_units`, `zero_units`, `no_account_size`, `not_main_ledger`) are stored as rows with status `skipped`, so the report counts them.
- **Logging:** one INFO line per sent action and per final outcome, in the style of v111's plan-transition lines. Nothing goes to the Discord alert channels.

### Table `broker_orders`

`id` (PK), `plan_id`, `ticker`, `action` (`open|close_units|close_all|move_stop`), `seq`, `request_id` (unique), `order_id`, `position_id`, `status` (`queued|sending|in_flight|filled|rejected|skipped|closed_by_broker`), `skip_reason`, `requested` (JSONB: the body sent), `settlement_type`, `units_requested`, `units_filled`, `avg_price`, `fees`, `error_code`, `error_message`, `created_at`, `updated_at`. Indexes: `(plan_id, seq)` and `status`.

### Comparison report: `scripts/reports/etoro_parity_report.py`

Read-only. Joins `broker_orders` with the plan store. For each mirrored plan it shows:
- the paper entry against eToro's `avg_price`, as slippage in R;
- each exit leg's paper price against eToro's close price;
- fees, and overnight cost from trading history (`get-my-trading-history` route, `netProfit` minus `fees`);
- realised R on both sides.

Pooled totals (N, mean R paper, mean R eToro, mean slippage R) are split by direction and by `settlement_type`, with skip counts by reason. Every figure is derived from the live data at run time, never quoted.

### Reconciliation

Once a day, after the US close, the executor compares the demo positions (`GET .../demo/portfolio`) with its own `filled`, still-open rows. Positions missing on either side, unit mismatches and stop mismatches are logged at WARNING. **Nothing is corrected automatically.** v159's `reconciler` agent is the on-demand deep read.

## Testing

- `tests/broker/test_mirror.py`: every row of the event table, including the non-main ledger, both directions, every take-profit branch, and a stop move equal to the last stop sent.
- `tests/broker/test_sizing.py`: rounding, fractional versus whole units, zero units, minimum exposure and maximum units.
- `tests/broker/test_executor.py` against a fake client: idempotent resend after a simulated crash, per-plan ordering, 429 deferral, each outcome mapping, `closed_by_broker`.
- `tests/broker/test_client.py` against a fake HTTP transport: headers, token bucket, and `assert_demo` called.
- `tests/broker/test_demo_only_paths.py`: no real-account route string anywhere under `swingbot/core/broker/`.
- `tests/broker/test_import_direction.py`: nothing outside `broker/` (except `commands/scanning/loops.py`) imports it.
- The Alembic revision is tested in the existing migration-test pattern.
- **The suite makes no network call to eToro.** `scripts/ops/etoro_demo_smoke.py` is manual: one 1-unit demo buy with a stop attached, a lookup and a close, using the `.env` keys. It is run once by hand after deploy.

Every new function stays below cyclomatic complexity 15.

## Rollout

1. The plan merges with `ETORO_MIRROR_ENABLED=false`; deploy (`docs/deploy/DEPLOY_HETZNER.md`).
2. The partner generates an eToro key with `demo:write` and `demo:read` (and `market-data:read` if eligibility needs it); `get-my-profile-and-scopes` confirms them.
3. On the VM, set `ETORO_USER_KEY`, `ETORO_API_KEY` and `ETORO_ACCOUNT_SIZE` in `.env` by editing in place (never `sed -i` on the bind-mounted file), run the smoke script, then set `ETORO_MIRROR_ENABLED=true` and send SIGHUP. Mirror the non-secret parts (`.env.example`, any ops script) into the repo (`mirror-prod`).
4. A first-week check through `prod-inspector`: the INFO lines, the skip reasons and one parity-report run.

## Parallelisation

- **Group 1, in parallel:** `sizing.py` + tests, `mirror.py` + tests, and the Alembic revision + `store.py`. These are pure units, or a new table with no reader yet, and none of them shares a file.
- **Group 2, sequential after v159 § B2 merges:** `etoro_client.py`. It imports `infra.etoro_guard`, which does not exist until v159 lands. This is the plan's one external dependency.
- **Group 3, sequential after Groups 1 and 2:** `executor.py`. It needs the client's result type, the translator's action type and the store.
- **Group 4, sequential after Group 3:** the config fields, the `loops.py` hook and `broker/__init__.py`. They wire the executor in, and `loops.py` and `config.py` are shared files that other plans touch, so they go in one task.
- **Group 5, in parallel after Group 3:** the parity report, the daily reconciliation, and the smoke script. They read the store and touch disjoint files.
- **Final:** the full suite, once.

## Out of scope

Resting market-if-touched orders at eToro (approach B); anything on the real account; pyramid adds; an admin UI page; the bomeo-capital.com page; copy trading; cancelling the paper plan because the eToro order failed. The paper ledger never depends on eToro.

## Risks

- **eToro's own stop or target fires between bot ticks.** The bot's next `closed` or `MoveStop` then hits an already-closed position, which is recorded as `closed_by_broker`. Both sides closed at the same price level, so the report shows only the fill difference.
- **Market closed at the fill event** (for example a fill recorded at the close): the order sits `WaitingForMarket` (`status.id` 11) and stays `in_flight` until it fills. The report then shows the gap as slippage, which is accurate.
- **US-listed ETFs may be ineligible** for an EU demo account (PRIIPs/KID). They come out as `skipped: ineligible` and are counted in the report, which answers the open item in `etoro-roadmap.md`.
- **API drift:** the routes are versioned (v1, v2 and v3 coexist). The client pins the exact paths verified above, and the smoke script catches drift.

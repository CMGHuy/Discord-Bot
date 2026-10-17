# v170 Simple alerts: money beside R, symbol labels, plan buttons. Implementation Plan, index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this plan whole**: pull one task with `/task-brief V170-3` or `grep -n "^### Task V170-3" -A 300 docs/superpowers/plans/2026-10-16-v170-simple-alerts-money-symbols-buttons_*.md`.

**Spec:** [`docs/superpowers/specs/2026-10-16-v170-simple-alerts-money-symbols-buttons-design.md`](../specs/2026-10-16-v170-simple-alerts-money-symbols-buttons-design.md) (all sections; **§4 Amendments A1–A10 override §1–§3 where they differ**; every applied `## Panel review` finding is a requirement)
**Bump:** minor
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** veteran-trader, financial-advisor, senior-engineer

**Goal:** Every message in the simple-alerts (execution feed) channel carries a signed dollar figure beside each R at every money moment, labels values with one table of symbols while every order line keeps its broker verb, and carries persistent buttons (📊 Chart, 🔍 Breakdown, ⭐ Watch, 💵 P&L now) whose replies are ephemeral.

**Architecture:** `presentation/tokens.py` gains `fmt_money` (moved from `plan_table.signed_money`, re-exported), `FEED_SYMBOLS` and the legend. `presentation/instructions.py` stays pure: a frozen `Money` (currency, whole shares, settled amount, record share count) arrives as data; ticket, lifecycle and close builders become table-driven and print "if hit" projections (printed shares × printed move), realised TP1 legs (record arithmetic) and the close's settled `realized_pnl_amount`. `scanning/execution_embeds.py` builds `Money` from the sizing snapshot (ticket) or from the linked paper-trade record via the new `TradeLog.trade_for_plan` (lifecycle). The buttons live in `commands/views.py` (`PnlNowButton`, `FEED_BUTTONS`, `feed_view`); the reply is a new pure-plus-seams module `commands/pnl_now.py` that prices through a single-trade function extracted from `scan_run.get_all_unrealized_pnl`. `push_kwargs` takes an optional view; the simple-channel ticket send and the lifecycle feed/history sends attach `feed_view`.

**Tech Stack:** Python 3.11, discord.py (DynamicItem persistent buttons), pytest via `scripts/dev/testrun.py`, radon.

## Where to work

- **Branch and worktree:** `2026-10-16-v170-simple-alerts-money-symbols-buttons`, at `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v170-simple-alerts-money-symbols-buttons` (written `$WT` below). The main tree is `$R` = `E:/Documents/Private/Projects/Discord-Bot`. V170-1 Step 0 creates the worktree with the `worktree-lifecycle` skill (reuse it if `git worktree list` already shows it); name `$WT` in every subagent dispatch.
- **Never `cd`** (it breaks the guardrail hooks). Use absolute paths and `git -C $WT`. `python $WT/scripts/dev/testrun.py file tests/...` resolves test paths against `$WT`.
- **This plan file is committed on `main`.** Only the implementation is branched. Each task commits on the branch. After every task, `git -C $R status --short` must show the main tree unchanged.
- **Test database:** DB-backed tests SKIP (they do not fail) when the test Postgres is unreachable. Before any task whose tests touch the trade log or plan store (V170-2, V170-4, V170-6, V170-10, V170-14), confirm it is up: `docker compose --profile test up -d db-test`, then check `docker ps` for `swing-db-test`. If its published port is not `55432`, export `TEST_DATABASE_URL=postgresql+psycopg://swingbot:swingbot@127.0.0.1:<port>/swingbot_test` for every `testrun.py` call. **A run that reports skips for these files is not green.**

## Global Constraints

- **Bump: bot minor, ui none.** No task edits `VERSION.json` or `version_history.json`; `/close-out` resolves the bump.
- **Presentation only.** No change to sizing, stops, targets, what gets alerted, any trade record field or any stored shape (`schema-evolution.md`: nothing new is persisted; no `open_shares`, no `Money` on disk).
- **`instructions.py` stays pure:** no I/O, no clock, no `discord` import, no import from `swingbot.core.scanning`. No glyph from `FEED_SYMBOLS` is written as a literal in it (V170-7 greps for it).
- **D2 — broker verbs stay words on every order line:** long `BUY STOP` / `BUY AT MARKET` (entry), `SELL STOP` (stop), `SELL LIMIT` (targets), `SELL AT MARKET` (exit); short `SELL STOP` / `SELL SHORT AT MARKET`, `BUY STOP`, `BUY LIMIT`, `BUY TO COVER AT MARKET`. Every cancel says `CANCEL`. Stop moves say `MOVE SELL STOP` / `MOVE BUY STOP`.
- **Two kinds of $ (spec §1 + A3):** projected "if hit" / "if it fills" $ = printed whole shares × printed move, signed by direction; realised $ = record arithmetic (TP1 leg: `record_shares × fraction × (fill − entry) × sign`; close: the record's `realized_pnl_amount`). A close with `realized_amount is None` prints **R only**. A lifecycle message with no linked record prints **no $ at all** (share counts from today's sizing snapshot, as before).
- **Signs (A9):** `tokens.fmt_r` / `instructions.signed_r` keep U+2212 (`−1.0R`); `fmt_money` keeps ASCII `-` (`-$250.00`) and `+` on zero and above. Neither formatter changes. R stays 1 dp.
- **Cost basis:** every close P&L line and every P&L-now total ends `(paper, gross)` (`tokens.COST_BASIS`); the `!help` legend says "paper account, before fees, slippage and tax".
- **Buttons:** `PLAN_BUTTONS` is never extended (`PlanActionView` iterates it). `FEED_BUTTONS = (PnlNowButton,)`. `feed_view(plan_id)` always holds Chart, Breakdown, Watch, P&L now (A4: no `open_` argument). Dismiss is never on the feed. Every button reply is ephemeral; P&L now never posts in the channel and never raises to the user.
- **Views only on plan-backed feed messages (A7):** the v2 ticket (`Kind.TICKET_PLACE`, `Kind.TICKET_DO_NOT_PLACE`) in `alerts._mirror`, and the instruction embed (feed send and its history copy) in `notify_plan_events`. Never the strategy-signal mirror, the legacy mirror, or the history-only `build_plan_event_embed` status embed.
- **Layering (A8):** `core/scanning/lifecycle_embeds.py` reaches `feed_view` through a function-local import; core never imports `swingbot.commands` at module level.
- **`push_kwargs(embed)` output is byte-identical** when no view is given; the `view` key is added only when a view is passed.
- **`!pnl` unchanged:** `get_all_unrealized_pnl` keeps its output and its one-batch-call behaviour; `tests/scanning/test_unrealized_pnl_batch.py` passes untouched.
- **Out of scope:** `_legacy_simple_alert`, the full-alert channel, closed-trades/retrospective embeds, the phone push-preview line (`kinds.py`), total open risk, "I placed it" tracking.
- **Complexity < 15** for every function written or changed: each task ends with `python -m radon cc -s -n C <touched files>` and nothing it prints may be a function the task touched at grade C (≥ 15 shows as C 15+). `instruction_for` (C 13 today) and `notify_plan_events` (C 13 today) must drop, not grow.
- **Per-task verification is the narrow run** (`python $WT/scripts/dev/testrun.py file <test>`); one full-suite run as the final task (V170-14), dispatched to the `test-runner` subagent.

## Decisions taken while planning (binding; the controller may overrule before V170-3)

1. **`Money` carries a fourth field, `record_shares: float | None`** — the paper record's unrounded count. A3 requires realised TP1 $ from the record's arithmetic while `shares` is the printed whole count; the projection cannot do both from one int. `record_shares is None` is also the "no linked record → print no $" switch (spec §1 fallback). Built only through `instructions.money_from(...)`.
2. **The TP1 line keeps its share count** (spec §2 example; with a record of 54.35 shares it reads `💰 TP1 FILLED 27 sh @ 189.10 · 🧾 +$182.07 · +1.5R`, where 182.07 = 54.35 × 0.5 × 6.70) **and** its $ follows A3 (record arithmetic). On a fractional record the $ can differ from printed shares × move by under one share's move. A3's "those lines print no share count" premise does not hold for this one line; the plan follows the amendment's arithmetic and the spec's layout. Flagged for the controller.
3. **One task per message family, not one pass for money and another for symbols.** §1 and §2 rewrite the same lines; doing them in one pass per family (ticket V170-3, lifecycle V170-4, close V170-5) avoids rewriting every pinned string twice. The order still follows spec § Parallelisation (Money first, symbols with it, buttons beside).
4. **Glyph placement beyond the spec's examples** (spec: "only their lead label gets a symbol where the table has one"): `▶` leads the ticket headline and the `FILLED` headline; `⏳` leads the expiry cancel headline and `⛔` the invalidation cancel headline; the risk-cap cancel, do-not-place ticket, time-exit due/unresolved headlines and the extended-hours text keep no glyph (the table has no key for them, and a `⏳` before a time-exit `BUY TO COVER` would break the `⏳ … CANCEL` rule). Close headlines lead with `✅`/`❌`/`➖` (both `EXITED` and `CLOSE AT MARKET`); the exit word gets its glyph where one exists (`🛑 stop`, `⚖ break-even`, `🎯 target`, `🏃 runner floor`, `〜 trail`, `🎯 TP2`).
5. **`be_moved` also carries the `🔒 if it fills:` line** (it is a stop move); its projection is `+$0.00 · 0.0R total` at a break-even stop.
6. **P&L-now R and $ split:** the open line shows the open fraction's **contribution** (`open_fraction × R move`, `record_shares × open_fraction × move`), so open + banked = total on screen. `%` is `compute_unrealized_pnl(...).pct_change` (the `!pnl` figure).
7. **`trade_for_plan` is the thin A1 wrapper** over `trades_repo().by_plan_id` (`limit=1`, unordered). Legacy data with two records per plan id returns either one; no preference logic is added.
8. **The `!help` legend lives in `HELP_DESCRIPTION`**, not in a field: `test_help_catalog.py` pins the field list to `COMMANDS_BY_CATEGORY` exactly.
9. **The before/after render** is produced by a committed dev script, `scripts/dev/render_feed_samples.py`, run once against `$R` (pre-change `main`) and once against `$WT`, both with the same fixtures and monkeypatched sizing and trade record.

## Close-route trace (spec §1 / A2, verified on the test DB while planning)

Only plan_manager closes emit a feed `closed` event, and each settles the trade before the event exists (`_persist_terminal` → `close_plan_trade` → `_settle_account_balance` in one transaction, then the event is returned to `poll`). A probe on 2026-10-16 (account 10,000, risk 1 %, placeholder logged at 105, `_pending(stop_loss=104, tp1=110)`, fill 106, record `shares = 9.43`) gave:

| route | price series | closed `reason` | `realized_pnl_amount` |
|---|---|---|---|
| pre-TP1 stop | 106, 103 | `loss` | −28.29 |
| break-even scratch | 106, 108.5, 105 | `scratch` | −9.43 |
| runner trail (`tp2=None`, `atr_fn` ATR 4.0; with the default tp2 105 it closes `tp1_runner_tp2` at 140) | 106, 116, 140, 118 | `tp1_runner_trail` | 103.73 |
| runner TP2 (`tp2=120`) | 106, 111, 121 | `tp1_runner_tp2` | 94.30 |
| runner floor (`tp2=120`) | 106, 111, 106.5, 105 | `tp1_runner_be` | 25.93 |
| time exit (compression short, auction 98) | `test_compression_time_exit._short()` | `time_exit` | 20.00 (shares 10.0) |

Reversal (`close_trade_reversed`), manual close, `backfill_exit_price`, `update_open_trades`, `close_if_live_price_hit` and `check_near_tp_timeout` settle but never emit a feed message (the last three skip plan-linked trades); they get no render test. V170-6 pins every row above, the `_on_event` fallback, and the unsettled cases.

The figures depend on the wall clock (with a live tape a stop fills at the stop price, not the bar), so V170-6 passes `now=SATURDAY` to every poll and pins each figure per share against the record's own `shares` and `== settle_legs(record)`, not as the absolute amounts above (part 2 writer, re-verified on the test DB).

## Parallelisation

Two chains that meet at V170-12, then V170-13 and V170-14.

- **Chain A (feed text):** V170-1 → V170-3 → V170-4 → V170-5 → {V170-6, V170-7}.
  - V170-3 needs V170-1 (`tokens.FEED_SYMBOLS`, `tokens.fmt_money`).
  - V170-4 needs V170-3 (same `instructions.py`, `execution_embeds.py`, `test_instructions.py`, `test_execution_embeds.py`; `Money`, `money_from`, `_r_at`, `_join`) and V170-2 (`TradeLog.trade_for_plan`, read by `execution_embeds._linked_trade`).
  - V170-5 needs V170-4 (same files; the `money` builder signature).
  - V170-6 needs V170-5 (asserts the rendered close carries `realized_pnl_amount`). V170-7 needs V170-5 (every glyph key is used only once the close builder ships `win`/`loss`/`flat`). V170-6 and V170-7 touch disjoint new test files and may run side by side.
- **Chain B (buttons):** V170-8 and V170-9 depend on nothing in this plan and touch disjoint files (`components.py` / `scan_run.py`); either may run beside any Chain A task.
  - V170-10 needs V170-1 (`FEED_SYMBOLS`, `fmt_money`, `COST_BASIS`), V170-2 (`trade_for_plan`) and V170-9 (`scan_run.quote_trade`, `TradeQuote`).
  - V170-11 needs V170-10 (`pnl_now.reply_for`).
  - V170-12 needs V170-8 (`push_kwargs(..., view=)`) and V170-11 (`feed_view`).
- V170-2 touches only `performance.py` and a new test file; it may run beside V170-1.
- V170-13 needs V170-1 (`tokens.feed_legend`); it touches only `commands/info.py` and its test, so it may run beside anything after V170-1.
- V170-14 is last: it needs every other task (the after-render and the full suite cover them all).

Sequential edges forced by shared files (never run these pairs together): V170-3/V170-4/V170-5 (`instructions.py`, `execution_embeds.py` and their tests); V170-11 and V170-12 never share files but V170-12 consumes V170-11's contract.

## Task ledger

| Task | Title | Part | Model | Files (C = create, M = modify) | Creates, consumed later |
|---|---|---|---|---|---|
| V170-1 | `tokens.fmt_money`, `FEED_SYMBOLS`, legend; `plan_table.signed_money` re-export | 1 | haiku | M `swingbot/core/presentation/tokens.py`, M `swingbot/core/scanning/plan_table.py`, C `tests/presentation/test_feed_symbols.py` | `tokens.fmt_money(amount: float, currency: str) -> str` (body of today's `signed_money`); `plan_table.signed_money = tokens.fmt_money` (same object); `tokens.FEED_SYMBOLS: dict[str, str]` = `entry ▶, stop 🛑, tp1 💰, runner 🏃, tp2 🎯, trail 〜, breakeven ⚖, expiry ⏳, invalid ⛔, if_fills 🔒, pnl 🧾, win ✅, loss ❌, flat ➖, at_or_above ≥, at_or_below ≤` (this order); `tokens.FEED_SYMBOL_WORDS: dict[str, str]` (same keys); `tokens.COST_BASIS = "(paper, gross)"`; `tokens.COST_BASIS_SENTENCE = "Feed dollars: paper account, before fees, slippage and tax."`; `tokens.feed_legend() -> str` = `"Feed symbols: " + " · ".join(f"{glyph} {word}") + ". " + COST_BASIS_SENTENCE` |
| V170-2 | `TradeLog.trade_for_plan` (any status) | 1 | sonnet | M `swingbot/core/tracking/performance.py`, C `tests/tracking/test_trade_for_plan.py` | `TradeLog.trade_for_plan(self, plan_id: str) -> dict \| None` — `_json_record(trades_repo().by_plan_id(plan_id))` or `None`; placed after `get_trade_by_id` |
| V170-3 | `Money`, `money_from`; ticket with symbols, verbs and "if hit" $; ticket wiring | 1 | sonnet | M `swingbot/core/presentation/instructions.py`, M `swingbot/core/scanning/execution_embeds.py`, M `tests/presentation/test_instructions.py`, M `tests/scanning/test_execution_embeds.py`, M `tests/scanning/test_simple_alerts.py` | `instructions.Money` (frozen: `currency: str`, `shares: int \| None`, `realized_amount: float \| None = None`, `record_shares: float \| None = None`); `instructions.money_from(shares: float \| None, currency: str, *, realized_amount: float \| None = None, priced: bool = True) -> Money`; `ticket_for(plan, *, logged: bool, not_logged_reason: str \| None, money: Money \| None = None, warnings: tuple[str, ...] = (), level: int \| None = None) -> Instruction` (`sizing`/`currency` kwargs removed); private helpers `_S = tokens.FEED_SYMBOLS`, `_sign(direction) -> int`, `_r_at(plan, entry, level) -> float \| None`, `_join(*parts) -> str`, `_priced(money) -> bool`, `_toward(direction) -> str`, `_against(direction) -> str`; `execution_embeds._ticket_money(plan) -> Money` |
| V170-4 | Lifecycle transitions table-driven with symbols, verbs, TP1 realised $ and stop-move projection; linked-record money | 1 | sonnet | M `swingbot/core/presentation/instructions.py`, M `swingbot/core/scanning/execution_embeds.py`, M `tests/presentation/test_instructions.py`, M `tests/scanning/test_execution_embeds.py`, M `tests/scanning/test_compression_instructions.py` | `instruction_for(plan, event, *, money: Money \| None = None) -> Instruction` (`sizing` kwarg removed; every transition dispatched through `_BUILDERS`, builders take `(plan, event, side, common, money)`); `instructions.stop_projection(plan, new_stop: float, money: Money \| None) -> tuple[float \| None, float]` ($ or None, total R); `execution_embeds._linked_trade(plan_id: str) -> dict \| None`; `execution_embeds._event_money(plan) -> Money` |
| V170-5 | Close messages: outcome lead, exit glyph, `🧾` P&L line from the settled amount | 2 | sonnet | M `swingbot/core/presentation/instructions.py`, M `tests/presentation/test_instructions.py`, M `tests/scanning/test_execution_embeds.py` | `instructions.outcome_key(r: float) -> str` (`"win"` if r > 0.05, `"loss"` if r < −0.05, else `"flat"`); `instructions.pnl_line(r: float, money: Money \| None) -> str` (`"🧾 <$ · >R (paper, gross)"`) |
| V170-6 | Close-route tests: every emitting route renders the record's settled $ | 2 | opus | C `tests/scanning/test_feed_close_routes.py` | — |
| V170-7 | Guard tests: every glyph used, no glyph literal in `instructions.py`, broker verb on every order line | 2 | sonnet | C `tests/presentation/test_feed_guards.py` | `tests.presentation.test_feed_guards.rendered_feed() -> list[tuple[str, Instruction]]` (direction, instruction for every feed message kind; reused by nothing else) |
| V170-8 | `push_kwargs(embed, view=None)` | 2 | haiku | M `swingbot/core/presentation/components.py`, M `tests/presentation/test_components.py` | `components.push_kwargs(embed, view=None) -> dict` (adds `"view"` only when `view is not None`); `ui.push_kwargs` re-export unchanged |
| V170-9 | Extract the single-trade price + unrealised body from `get_all_unrealized_pnl` | 2 | sonnet | M `swingbot/core/scanning/scan_run.py`, C `tests/scanning/test_quote_trade.py` | `scan_run.TradeQuote` (frozen: `price: float \| None`, `daily_close: date \| None = None`); `scan_run._batch_prices(tickers: list) -> dict`; `scan_run.unrealized_for_trade(trade: dict, price_cache: dict, daily_dates: dict) -> tuple[TradeQuote, UnrealizedPnL \| None]`; `scan_run.quote_trade(trade: dict) -> tuple[TradeQuote, UnrealizedPnL \| None]` |
| V170-10 | `commands/pnl_now.py`: the P&L-now reply per plan status | 3 | sonnet | C `swingbot/commands/pnl_now.py`, C `tests/commands/test_pnl_now.py` | `pnl_now.GONE = "This plan no longer exists."`; `pnl_now.UNAVAILABLE = "price unavailable"`; `pnl_now.render_reply(plan, trade: dict \| None, quote, pnl, *, clock: datetime, market_open: bool) -> str`; `pnl_now.reply_for(plan_id: str, *, now: datetime \| None = None) -> str` (never raises); seams `_load_plan(plan_id)`, `_linked_trade(plan_id)`, `_quote(plan, trade) -> tuple[TradeQuote, UnrealizedPnL \| None]` |
| V170-11 | `PnlNowButton`, `FEED_BUTTONS`, `feed_view`, registration | 3 | sonnet | M `swingbot/commands/views.py`, M `tests/commands/test_views_persistent.py`, C `tests/commands/test_views_feed.py` | `views.PnlNowButton` (`ACTION = "pnl"`, `LABEL = "💵 P&L now"`, template `plan:pnl:<uuid>`); `views.FEED_BUTTONS: tuple[type, ...] = (PnlNowButton,)`; `views.feed_view(plan_id: str) -> discord.ui.View` (Chart, Breakdown, Watch, P&L now; empty view for a non-persistable id); `register_persistent_views` calls `bot.add_dynamic_items(*PLAN_BUTTONS, *FEED_BUTTONS)` |
| V170-12 | Attach `feed_view` to the feed ticket and every feed lifecycle send | 3 | sonnet | M `swingbot/commands/scanning/alerts.py`, M `swingbot/core/scanning/lifecycle_embeds.py`, C `tests/scanning/test_feed_buttons_attach.py` | `alerts._TICKET_KINDS = frozenset({Kind.TICKET_PLACE, Kind.TICKET_DO_NOT_PLACE})`; `alerts._ticket_view(simple_embed, plan) -> discord.ui.View \| None`; `lifecycle_embeds._feed_view(plan_id: str) -> discord.ui.View \| None`; `lifecycle_embeds._send_instruction(feed, history, embed, plan, event) -> bool` |
| V170-13 | `!help` legend from `FEED_SYMBOLS` | 3 | haiku | M `swingbot/commands/info.py`, M `tests/commands/test_help_catalog.py` | `info.HELP_DESCRIPTION` = old text + `"\n"` + `tokens.feed_legend()` |
| V170-14 | Radon sweep, before/after render results note, full suite once | 4 | sonnet | C `scripts/dev/render_feed_samples.py`, C `docs/superpowers/results/2026-10-16-v170-feed-before-after.md` | — |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `docs/superpowers/plans/2026-10-16-v170-simple-alerts-money-symbols-buttons_1-money-ticket-lifecycle.md` | V170-1..V170-4 | Tokens and symbol table, `trade_for_plan`, `Money` and the ticket, lifecycle transitions with linked-record money |
| 2 | `docs/superpowers/plans/2026-10-16-v170-simple-alerts-money-symbols-buttons_2-close-guards-plumbing.md` | V170-5..V170-9 | Close messages, close-route tests, glyph and verb guards, `push_kwargs` view, `!pnl` single-trade extraction |
| 3 | `docs/superpowers/plans/2026-10-16-v170-simple-alerts-money-symbols-buttons_3-buttons-render.md` | V170-10..V170-13 | P&L-now reply, buttons and registration, send-site wiring, `!help` legend |
| 4 | `docs/superpowers/plans/2026-10-16-v170-simple-alerts-money-symbols-buttons_4-render-suite.md` | V170-14 | Radon sweep, before/after render results note, full suite once (split from part 3: the 1500-line cap) |

## Spec coverage

| Spec item | Task(s) |
|---|---|
| §1 `Money`, two kinds of $, cost basis | V170-3, V170-4, V170-5 |
| §1 sources per message (snapshot ticket, linked record lifecycle, fallback no $) | V170-3, V170-4 |
| §1 / A1 `trade_for_plan` | V170-2 |
| §1 / A2 settle order, every close route tested | V170-6 |
| §1 `fmt_money` move + identity pin | V170-1 |
| §2 `FEED_SYMBOLS`, one meaning per glyph, comparisons in the table | V170-1, V170-7 |
| §2 layouts (ticket, TP1, stop move, close), verbs on every order line | V170-3, V170-4, V170-5, V170-7 |
| §2 legend in `!help` | V170-1, V170-13 |
| §3 / A4 / A10 `FEED_BUTTONS`, `feed_view`, no leak into `PlanActionView` | V170-11 |
| §3 / A7 / A8 attach sites, layering | V170-12 |
| §3 `push_kwargs` view | V170-8 |
| §3 / A5 / A6 P&L now reply, price source, as-of, market closed, failure | V170-9, V170-10 |
| Testing: alert-surface before/after gate, radon, full suite | V170-14 (radon also per task) |

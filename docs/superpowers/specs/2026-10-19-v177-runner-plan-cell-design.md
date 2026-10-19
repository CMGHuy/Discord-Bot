# v177 — Plan cell for trailing runners and closed partial trades

**Version:** ui 1.30.0 · bot 2.12.0 (at writing)
**Bump:** ui patch — the Plan cell on the PARTIAL tab, the Closed tab and the Trades page shows different content; no screen is rebuilt (`working-conventions.md` § The three levels reserves minor for a materially different component). bot patch — the trades list endpoint serves new row fields (additive, no stored data changes).
**Edge:** none (integrity) — display only. It changes no signal, gate, stop, size or badge; it shows facts the plan already holds.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, financial-advisor
**Status:** spec written 2026-10-19 from a chat with the partner. The cell format and the meaning of "TP2" (the runner's actual exit price) were decided by the partner in chat. Revised the same day after the panel (see `## Panel review`).

## Why

A post-TP1 runner with no TP2 shows today `original entry → TP1 fill ✓ / current
trailing stop (rise% - drop%)` (`plan_view.py:118-149`, `plan-cell.ts:23-30`).
The plan's original TP1 and original stop are gone from the row, and nothing
says where the runner's stop would take the trade if price turned. For the RKLB
short (entry 60.67, TP1 58.33, stop 61.85, best price 49.94, trailing stop
52.44) the partner could not see what the trailing stop locks in.

On the Closed tab a partial trade is two rows, one per realized leg, and both
carry the plan's TP1 as the target (`plan_view.py:168-172`). The runner's real
outcome appears nowhere in the Plan cell.

## What the partner asked for

**Open positions, PARTIAL tab, runner with a trailing stop.** Two lines in the
Plan cell. RKLB (short) is the worked example throughout.

| Line | Reads | RKLB |
|---|---|---|
| 1 | `Entry → TP1 / original SL (% to TP1 - % to SL)` | `60.67 → 58.33 / 61.85 (3.9% - 1.9%)` |
| 2 | `Trail best price → price the trailing stop exits at (max % gain / % gain at exit)` | `Trail 49.94 → 52.44 (+17.7% / +13.6%)` |

- Line 1 has the cell's existing shape (`entry → target / stop (rise% - drop%)`)
  with the plan's **original** TP1 and stop in place of the runner values.
  Its percentages are distances from the entry, unsigned, as today.
- Line 2 starts with a small muted `Trail` label so the second line is never
  read as a second plan. Its best price is the extreme price since TP1
  (`runner_best` = `runner_high_close`: the lowest for a short, the highest for
  a long). The exit price is the live trailing stop (`stop_loss`, which is
  `working_stop`; with v176 it includes the 5% give-back stop). Both
  percentages are profit **per share from the original entry**, signed in the
  trade's direction (a short gains when price falls), with an explicit `-` on
  the loss side.
- Line 2's meaning is spelled out in the tooltip (below), not only by its
  layout.

**Closed tab, partial trades.** The target slot shows the **runner's actual
exit price**, as the partner chose, and the percentage next to it is the profit
per share from the entry to that price, signed in the trade's direction. The
cell shows numbers only, never the word "TP2"; the tooltip names what closed
the runner (see Tooltips).

## Scope

- The two-line cell: a PARTIAL plan whose view has `bar_kind == "trailing"`
  (a runner with no `tp2`). A PARTIAL plan that has a `tp2` keeps today's cell.
- The **TP1-leg row of a still-PARTIAL plan** (a row with `status: "CLOSED"`
  that `_expand_plan_row` emits at `trades.py:424-443`) keeps today's cell. The
  runner is still open, so there is no runner exit to show. The gate is
  `status == "PARTIAL"` in the template, and `_row_from_leg` clears the new
  line-2 fields, so field presence alone can never draw the runner cell on a
  closed row.
- PENDING, ACTIVE, and the Closed tab's rows for plans that never scaled out
  are unchanged.
- The Closed-tab change applies to a CLOSED plan that reached TP1 and then
  closed its runner. Both rows of the trade (TP1 leg, runner leg) show the same
  Plan cell, as today.
- Where the cell appears: the Dashboard's positions table (`dashboard.ts:317`)
  and the Trades page (`trades.ts:404`), which render the same `TradeRow` with
  an identical template and so must give the same answer
  (`trades.py:239-241`). The Gallery (`gallery.ts:411, :629`) keeps passing
  nothing new and is unchanged. The trade-detail panel does not use this cell.
- Not changed: the P&L % column, the R column, the status bar, row ordering,
  paging, the columns' membership. Legacy trades without a `plan_id` keep their
  cell.

## Where it changes

**Backend** (`swingbot/admin/api_v1/trades.py`).

Existing row fields are reused, not duplicated:

| Need | Existing field | Source |
|---|---|---|
| original stop | `risk_stop` | `trades.py:300` |
| best price since TP1 | `runner_best` | `trades.py:277` |
| max % gain / % gain at exit | `best_pnl_pct` / `stop_pnl_pct` | `_trailing_pnl_ends`, `trades.py:978-986` |
| exit price | `stop_loss` (the view's stop) | `trades.py:269` |

- `_trailing_pnl_ends` currently runs only inside `_trailing_status_fields`,
  which returns its chip when there is no live price. The two percentages are
  now computed for every trailing PARTIAL row independently of the live price,
  by the same formula `(price − entry) × sign / entry × 100`, from one helper
  that feeds both the status bar and the Plan cell. The Plan cell must not lose
  line 2 when the price feed is down.
- When no tick has recorded a best price yet (`runner_best` is `None`), line 2
  uses the TP1 fill (`banked_exit_price`) as its best price, so a freshly
  banked runner still shows line 2.
- When `working_stop` is `None`, the view's stop is the derived floor
  (`stop_kind: "derived_floor"`, `plan_view.py:130-133`). Line 2 still shows,
  and its tooltip labels the stop "Locked-in floor".
- New fields on the row, `None` when they do not apply:
  - `tp1` — the plan's original TP1 (line 1).
  - `runner_exit_price` and `runner_exit_reason` — for a CLOSED plan whose first
    realized leg is the TP1 leg and whose runner has closed: the last leg's
    `exit_price` and its `reason`, taken when `len(legs) >= 2` and
    `legs[-1]["reason"] != "tp1"`. This excludes an ACTIVE stop-out, which
    writes one leg with `fraction: 1.0` (`plan_manager.py:1347-1349`).
  - A **manually closed** partial plan: `_close_plan`
    (`trade_commands.py:88-109`) adds no runner leg, so the runner's exit price
    is the trade's own `exit_price`, with `runner_exit_reason: "manual"`.
- `_row_from_leg` (`:373`) copies `_row_from_plan`, so both rows of a closed
  partial trade carry `runner_exit_price`; for the TP1-leg row of a
  still-PARTIAL plan it clears the line-2 fields (Scope above).
- `_row_from_plan` also builds the `GET /trades/<id>` row (`:745`) and the
  close/cancel response rows (`trade_commands.py:76`); they carry the new
  fields too, which is harmless. `_plan_detail` is not otherwise touched.
- The values are derived from fields already on the plan; nothing is stored.

**Frontend** (`frontend/src/app/api/models.ts`, `ui/plan-cell.ts`,
`workspaces/dashboard/dashboard.ts:317-333`, `workspaces/trades/trades.ts:404`).

- `TradeRow` gains `tp1`, `runner_exit_price`, `runner_exit_reason`
  (optional, nullable).
- `PlanCell` gains optional inputs for line 1's original TP1/stop, line 2's
  best price, exit price and two percentages, and a runner exit price and
  reason for the closed case. With none of them set the cell renders exactly
  as it does today.
- Both templates pass them only for the PARTIAL trailing row and the closed
  partial row, gated on `row.status`.

## Tooltips

The cell prints numbers; the tooltip says what they are.

- **Line 1:** "Original plan (TP1 already filled): entry → TP1 / original stop.
  Percentages are the distance from the entry to each level."
- **Line 2:** "Trailing stop. Best price so far → price the trailing stop would exit
  at. +17.7% is the peak since TP1 (unrealised); +13.6% is the profit if the
  stop fills at 52.44, per share from the original entry, before costs and tax.
  A short gains when price falls. The bot's paper level: your broker's resting
  orders are not synced, update your stop yourself." The stop word follows
  `stop_kind`: "Trailing stop" or "Locked-in floor".
- **Closed target:** "Runner exit (trailing stop | give-back stop | floor stop |
  TP2 | manual close): 52.44, +13.6% per share from the original entry." The
  reason comes from the runner leg's `reason` (`tp1_runner_trail`,
  `tp1_runner_be`, `tp1_runner_tp2`); a give-back close (`stop_source:
  "giveback"`, v176) reads "give-back stop".
- Neither tooltip claims the figure is the position's total return: the TP1
  half is already banked and the P&L % column covers the position.

## Layout

The cell is inline from `xs` at 12rem (`trades.columns.ts:159`);
`white-space: nowrap` is set on `.plan` (`plan-cell.ts:38`). A second line adds
height, not width: each line is its own block, each with `nowrap`, and the
375px no-wrap check applies to each line separately (the existing measured P&L
cell constraint, `dashboard.ts:550-558`). The three widths (phone 390, tablet
768, desktop 1440) are checked in a browser.

## Edge cases

- A runner exit on the loss side of the entry (a gap fill can put it there)
  keeps its sign and shows `-`; line 1's unsigned distances stay as they are.
- `runner_best`, stop or entry `None`: line 2 is omitted and the cell shows
  line 1 only. Never a dash for a number that exists.
- Currency formatting follows the cell's existing `currency` input.

## Testing

Backend, in `tests/admin/test_trades_partial_row.py` (the existing home of the
`_row_from_plan` / `_expand_plan_row` PARTIAL cases):

- RKLB fixture (entry 60.67, TP1 58.33, stop 61.85, best 49.94, trailing stop
  52.437): `tp1 = 58.33`, `best_pnl_pct = +17.69`, `stop_pnl_pct = +13.57`;
  a long mirror; no best price yet falls back to the TP1 fill; no price feed
  leaves the percentages intact; derived floor keeps line 2 and the floor label;
  a PARTIAL plan with a `tp2` gets none of the new fields.
- The TP1-leg row of a still-PARTIAL plan has the line-2 fields cleared.
- A two-leg CLOSED plan carries `runner_exit_price` and reason on **both** leg
  rows; an ACTIVE stop-out (one leg, `fraction: 1.0`) and a legacy trade do
  not; a manually closed partial plan gets the trade's `exit_price` and
  `manual`.

Frontend:

- `plan-cell.spec.ts`: two-line render for a short and a long; the existing
  cases unchanged when no new inputs are passed; the closed variant with its
  tooltip reasons.
- `positions-table.spec.ts`, `dashboard.spec.ts`, `trades.spec.ts`: the PARTIAL
  and CLOSED tabs and the Trades page pass the new fields; column floors
  unchanged; the TP1-leg row of a PARTIAL plan renders as today.
- Browser check at 390/768/1440 on the PARTIAL tab, the Closed tab and the
  Trades page (needs `ADMIN_USERNAME`/`ADMIN_PASSWORD` in `.env`).

## Panel review

Spec review, 2026-10-19 (staff-engineer, financial-advisor).

- staff-engineer 1: a manual close of a partial plan adds no runner leg -- applied (falls back to the trade's `exit_price`, reason `manual`; test added).
- staff-engineer 2: the TP1-leg row of a still-PARTIAL plan would inherit the line-2 fields -- applied (cleared in `_row_from_leg`, template gated on `status`; test added).
- staff-engineer 3: duplicate fields for best price and the two percentages -- applied (existing `runner_best`, `best_pnl_pct`, `stop_pnl_pct` reused; the price gate on the percentages removed).
- staff-engineer 4: the Trades page renders the same cell and would diverge; the trade-detail panel claim was wrong -- applied (Trades page wired; detail-panel claim removed).
- staff-engineer 5: the exit-price field and the derived-floor case were unnamed -- applied (`stop_loss`; line 2 kept, labelled "Locked-in floor").
- staff-engineer 6: "two realized legs" too loose -- applied (`len(legs) >= 2` and the last leg's reason is not `tp1`).
- staff-engineer 7: the other `_row_from_plan` consumers -- applied (named in Where it changes).
- staff-engineer 8: backend test file and cases -- applied.
- staff-engineer 9: `nowrap` location and per-line no-wrap -- applied.
- staff-engineer 10: the bump level -- applied (ui patch).
- staff-engineer 11: hand-off to financial-advisor -- see below.
- financial-advisor 1 [BLOCKING]: the line-2 % gain reads as banked profit -- applied (the `Trail` label; tooltip says peak is unrealised, exit % is if the stop fills, per share, before costs and tax).
- financial-advisor 2 [BLOCKING]: a stop or give-back exit under a take-profit label overstates the outcome -- applied in part. The cell prints numbers only and never "TP2"; the tooltip names the exit reason, and the percentage is signed with its base stated. Rejected: relabelling the cell, because the partner chose the runner exit price in the target slot.
- financial-advisor 3: unsigned line 1 beside signed line 2 -- applied (tooltips explain both; explicit `-` on the loss side).
- financial-advisor 4: original stop beside the live exit could mislead about risk -- applied (line 1 tooltip "Original plan (TP1 already filled)"). Rejected: adding the peak-to-exit giveback as a third number, because it is derivable from line 2.
- financial-advisor 5: paper levels vs the broker's resting orders -- applied (line 2 tooltip).
- financial-advisor 6: the peak is unrealised -- applied (line 2 tooltip).
- financial-advisor 7: per share, not the whole position -- applied (stated in the cell description and both tooltips).

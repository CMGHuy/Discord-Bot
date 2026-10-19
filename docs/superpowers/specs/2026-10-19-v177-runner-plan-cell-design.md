# v177 — Plan cell for trailing runners and closed partial trades

**Version:** ui 1.30.0 · bot 2.12.0 (at writing)
**Bump:** ui minor — the Plan cell on the Open positions table (PARTIAL tab) and the Closed tab shows different content; bot patch — the trades list endpoint serves new row fields (additive, no stored data changes).
**Edge:** none (integrity) — display only. It changes no signal, gate, stop, size or badge; it shows facts the plan already holds.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, financial-advisor
**Status:** spec written 2026-10-19 from a chat with the partner. The cell format and the meaning of "TP2" (the runner's actual exit price) were decided by the partner in chat.

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
| 2 | `best price → price the trailing stop exits at (max % gain / % gain at exit)` | `49.94 → 52.44 (+17.7% / +13.6%)` |

- Line 1 has the cell's existing shape (`entry → target / stop (rise% - drop%)`)
  with TP1 and the **original** stop in place of the runner values.
- Line 2's best price is the extreme price since TP1 (`runner_high_close`: the
  lowest for a short, the highest for a long). The exit price is the live
  trailing stop (`working_stop`), which with v176 includes the 5% give-back
  stop. Both percentages are profit measured from the original entry, positive
  for a gain in the trade's direction.

**Closed tab, partial trades.** The target slot shows the **runner's actual
exit price** as TP2, and the percentage next to it is measured from the entry to
that price. "TP2" here is where the second half exited, whatever closed it: the
trailing stop, the give-back stop, or a real TP2 when the plan had one.

## Scope

- The two-line cell: a PARTIAL plan whose view has `bar_kind == "trailing"`
  (a runner with no `tp2`). A PARTIAL plan that has a `tp2` keeps today's cell.
- PENDING, ACTIVE, and the Closed tab's rows for plans that never scaled out are
  unchanged.
- The Closed-tab change applies to a CLOSED plan with a realized runner leg
  (two legs). Both rows of the trade (TP1 leg, runner leg) show the same
  Plan cell, as today.
- Not changed: the P&L % column, the R column, the status bar, row ordering,
  paging, the Trades-page columns' membership. Legacy trades without a
  `plan_id` keep their cell.

## Where it changes

**Backend** (`swingbot/admin/api_v1/trades.py`).

- `_row_from_plan` (`:223`) gains optional row fields, `None` when they do not
  apply:
  - `tp1` — the plan's original TP1.
  - `trail_best`, `trail_best_pct`, `trail_exit_pct` — the best price, the profit
    % at that price, and the profit % at the trailing stop. Computed by one
    pure helper from the plan, alongside the existing
    `_trailing_pnl_ends` (`:978`) formula, `(price - entry) × sign / entry × 100`.
    They do **not** depend on a live price: the cell must not lose them when the
    price feed is down (`_trailing_status_fields` returns its chip then).
  - `trail_best` falls back to the TP1 fill (`banked_exit_price`) when no tick
    has recorded a best price yet, so a freshly banked runner still shows line 2.
  - `runner_exit_price` — for a CLOSED plan with two realized legs, the last
    leg's `exit_price`.
- `risk_stop` (the original stop, public since v166, `:300`) is read as-is.
- The values are derived from fields already on the plan; nothing is stored.
  Detail payloads (`_plan_detail`) are not touched.

**Frontend** (`frontend/src/app/api/models.ts`, `frontend/src/app/ui/plan-cell.ts`,
`frontend/src/app/workspaces/dashboard/dashboard.ts:317-333`).

- `TradeRow` gains the optional fields above.
- `PlanCell` gains optional inputs for line 1's original TP1/stop, line 2's
  best price, exit price and two percentages, and a runner exit price for the
  closed case. With none of them set the cell renders exactly as it does today,
  so the Trades page, the Gallery and the trade-detail panel are unaffected
  until they pass the new inputs.
- The dashboard template passes them only for the PARTIAL trailing row and the
  closed partial row. The tooltip names each number ("Original stop", "Trailing
  stop exits here", "Runner exit").

**Layout.** The cell is inline from `xs` at 12rem with `white-space: nowrap`
(`trades.columns.ts:159`). A second line adds height, not width. The three
widths (phone 390, tablet 768, desktop 1440) are all checked in a browser, and
the line must not wrap at 375px (the existing measured P&L cell constraint,
`dashboard.ts:550-558`).

## Edge cases

- A trailing-stop exit above entry for a long (below for a short) is a gain;
  a gap fill can put the exit on the loss side. The percentages carry their
  sign; the existing unsigned rise%/drop% on line 1 stays as it is.
- `runner_high_close` is `None`, stop `None` or entry `None`: line 2 is omitted
  and the cell shows line 1 only. Never a dash for a number that exists.
- Currency formatting follows the cell's existing `currency` input.

## Testing

- `plan_view`/row builder: the RKLB fixture (entry 60.67, TP1 58.33, stop 61.85,
  best 49.94, trailing stop 52.437) gives `tp1 = 58.33`, `trail_best = 49.94`,
  `trail_best_pct = +17.69`, `trail_exit_pct = +13.57`; a long mirror; no best
  price yet falls back to the TP1 fill; no price feed leaves the values intact;
  a PARTIAL plan with a `tp2` gets none of the new fields.
- Closed rows: two-leg CLOSED plan carries `runner_exit_price` on **both** leg
  rows; a single-leg closed plan and a legacy trade do not.
- `plan-cell.spec.ts`: two-line render for a short and a long; unchanged render
  with no new inputs (snapshot of the existing cases); closed variant.
- `positions-table.spec.ts` and `dashboard.spec.ts`: the PARTIAL and CLOSED tabs
  pass the new fields; column floors unchanged.
- Browser check at 390/768/1440 on the PARTIAL tab and the Closed tab.

## Panel review

(filled after the panel runs)

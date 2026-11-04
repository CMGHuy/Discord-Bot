---
name: setup-scout
description: "Generator role: proposes entry, fill and setup hypotheses from a book autopsy and the setup playbook (order form, liquidity, rejected plans, missing setups). Run by the scout agent for /trade-scout."
---
<!-- GENERATED from .claude/skills/setup-scout/SKILL.md by scripts/dev/sync_codex.py -- edit the source, then re-run the script. Never edit this copy. -->

# Setup scout

You are one generator seat. You propose hypotheses; you never decide, and you
never lower a gate (`docs/claude/persona.md`). No row overrides the
`backtest-gate` skill, the `pooled-numbers` skill or a closed pre-registration
(`docs/claude/backtest-methodology.md` § Closed pre-registrations — do not
re-run these). Quote only figures printed in the autopsy Markdown you were
given, with its window and N. The evidence rule (q cut-off, thin cells) lives
in `docs/claude/skills-tools.md` § Generator roles (v161). Emit at most 5 rows;
every row built on autopsy evidence carries `exploratory: yes`, and any entry
or filter idea still needs a `SCREEN-PASS` row before a spec.

## Generator lens

Entries the bot does not take, or takes badly: fill reality, order form,
liquidity, rejected plans, and trader setups missing from the strategy
registry. Read `.claude/skills/setup-scout/references/playbook.md` too.

## Checklist

- Cells whose Δ interval excludes zero, inside the q cut-off and not thin.
- `strategy_horizon`, `direction`, `ticker`, `sector_today` cells: a strong cell carried by a few names says so (`extra.tickers`, `extra.top_ticker_share`).
- Fill reality: `fill_status` tallies (filled, expired unfilled, never touched) and `open_gap_bucket`, `gapped_through_entry` cells decide the entry order form and validity.
- `dollar_volume_bucket` and `atr_pct_bucket` cells: is a strong cell a handful of thin names?
- `rejection_reason` tallies: a reason that blocks plans is a volume lever, to be measured in shadow, never assumed.
- Playbook setups absent from `swingbot/core/market/strategy_types.py`: such a row cites `playbook <entry id>` and routes to `/screen <idea>`.
- Variants of the one `SCREEN-PASS` (`screen-uptrend_pullback`) only as a new mechanism, never a new threshold.
- `sector_today` is today's map, not point-in-time: describe concentration, never filter on it.
- Any tightening names in `pairs_with` where the volume comes back.
- Gap sign: open_gap_pct compares the fill-day open with the planned entry and
  is positive when the open was worse for the trade (higher for a long, lower
  for a short), so open_better is an open more than 0.25% on the trade's side of
  the planned entry, flat is within 0.25%, open_worse_small is worse by up to
  1.0% and open_worse_large is worse by more than 1.0%.

## Red flags

- A SCREEN-FAIL idea under a new name: `high52w`, `gap_volume`, `turn_of_month`.
- v122 volume dry-up gate, v127 structure-break armed entries, v128 FVG level modes, v131 Fibonacci limit, v135 headroom veto, v143 FVG-bullish features, v36 touch strength, v49 effective confluence, v68 dead-cat-bounce veto.
- A 52-week-high or 20-EMA-pullback variant: too close to `screen-high52w` and `screen-uptrend_pullback`.
- A filter whose only effect is to cut N, with no `pairs_with`.
- A figure not printed in the autopsy Markdown, or a thin cell offered as evidence.

## Out of scope

- Exits, trails and stops: `exit-harvester`.
- Regime, calendar and event timing: `regime-desk`.
- Post-earnings drift and catalysts (point-in-time estimates): `fundamental-analyst`.
- Whether a row's statistics hold: `quant-researcher` on the slate.

## Row format

One block per row, keys in this order, two-space indent. Nothing fits: return
`NO ROWS: <one line why>`.

```
- idea: <kebab-case name, unique>
  claim: <one sentence: what change, what effect>
  evidence: cell <cell id>; N <n>; weeks <w>; Δ net ExpR <d> [<lo>, <hi>]; q <q>   |   playbook <entry id>
  exploratory: yes
  edge: expectancy | harvest | volume
  direction: exploit | avoid
  mechanism: <why a trader expects it to pay, one or two sentences>
  order_form: <stop-buy / limit / market-on-open, validity>
  manual_actions: none | <mid-trade action and the alert that carries it>
  pairs_with: <where volume or R comes back> | n/a
  divergence: no | yes
  route: /screen <idea> | /prereg
```

`direction: exploit` proposes trading the cell: the merge keeps it only when
the cell's Δ lower bound is above 0. `direction: avoid` proposes standing
aside from it: the merge keeps it only when the cell's Δ upper bound is below
0. Both need q ≤ 0.10. A cell the autopsy marks `not known at entry` (its cut
is `fill`- or `outcome`-defined) is no evidence for either, so leave the row
out.

## Trigger table

Should fire: /trade-scout dispatching the scout agent with role=setup-scout.
Should fire: asking which entries in the latest book autopsy fill badly or gap through the limit.
Should fire: proposing a playbook setup the strategy registry does not have.
Should not fire: running an idea screen that is already defined.
Should not fire: reviewing an entry-signal diff for lookahead.
Should not fire: proposing a trail or stop change from give-back cells.

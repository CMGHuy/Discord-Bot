# v156 — Trade autopsy: one closed trade reviewed in a fixed, measured shape

**Version:** ui 1.22.0 · bot 2.3.0 (at writing)
**Bump:** none (Claude/Codex tooling only; no shipped code)
**Edge:** none (integrity) — descriptive review only. It selects no parameter, moves no badge and registers no hypothesis; a pattern it surfaces becomes a separate pre-registration or nothing.
**Screen:** exempt (integrity)
**Panel:** quant-researcher, veteran-trader
**Status:** spec written 2026-10-10; panel review applied and scope cut from four skills to one; **not ready for a plan** — see "Open before a plan".
**Depends on:** v154 (frontmatter helper, `doc_section.py`) and v155 (`/prereg`, which cites the look record defined here).

## Why

"Why did this one trade lose?" is answered today by reading the journal row,
the trade record, the chart and the bars separately in the main context. The
analytics to measure it exist (`swingbot/core/analytics/mfe_mae.py`,
`journal.py`); a fixed shape for the answer does not, and without one the
answer drifts into a verdict on a sample of one.

This spec was written for four review skills. The panel removed three:

- **`/revalidate`** — `scripts/backtest/quarterly_revalidation.py` cannot
  return DEGRADED as wired: `--full --portfolio` writes a `portfolio_replay`
  dict holding none of the five `TRACKED_KEYS` (`:40`, `:111-113`,
  `:149-152`), so every comparison is skipped; and for `p_value`, `p_ruin` and
  `max_dd_p95` only a drop is flagged (`:155`), where a rise is the bad
  direction. A skill relaying that verdict would lend it authority it does not
  have. The script needs its own spec first.
- **`/market-day-review`** — `scripts/reports/market_day_report.py` takes no
  date and prints whole-book bucket tables (`:366-376`). It is not a review of
  one day, and wrapping it would only rename it.
- **`/live-drift`** — `parity_exits.py`, `parity_sizing.py` and
  `shadow_parity_report.py` compare the v2 engine with the legacy one on TRAIN
  and on shadow plans. None compares live fills with replay, so the name
  promised a measurement the repo does not have.

## Decisions taken in the brainstorm

- **Slash-only and forked** (`context: fork`, `model: sonnet`): raw rows and
  bars stay out of the main context, and nothing joins the listing.
- **Measurements, never a verdict.** No "stop too tight", no "bad setup".
- **Every look is recorded.** A review of live outcome data is a look at the
  holdout; uncounted looks are how a later filter gets chosen from memory.
- **Figures follow `pooled-numbers`:** each figure names the module that
  computed it and the price it was measured from.

## Design

### `/trade-autopsy <trade id>`

Refuses an open trade. For a closed one it prints, in this order and nothing
else:

1. **Plan as alerted** — entry, stop, targets, horizon, strategy, confidence,
   alert time, from the trade record. The journal row does not carry these
   (`journal.py:165-193` holds outcome, `r_realized`, MFE/MAE, `opened_at`,
   `closed_at`).
2. **Fill versus plan** — fill price and time, the gap at the open against the
   alerted entry, slippage in R, and whether the entry or the stop was gapped
   through.
3. **Placeable before the open** — alert time against the session
   (`session.py`): could it have rested as orders, yes or no.
4. **Excursions** — MFE and MAE in R from `mfe_mae.py`, each labelled with its
   reference price (`trade["entry"]`, stated as alerted or filled) and with the
   note that the `opened_at` day's whole range is included, so movement before
   the fill is counted (`mfe_mae.py:61-67`). No "bar on which it occurred":
   the module returns no bar index.
5. **Exit** — how and when it closed, expiry or time-exit state, `r_realized`.
6. **Context** — whether an earnings date fell inside the holding window, and
   dollar volume against position size.
7. The fixed line: "Descriptive only, N = 1. A pattern seen here is a
   hypothesis for `/screen` or `/prereg`, not a result."

Excluded on purpose: the journal's auto-lesson and tags (`journal.py:80-93`,
which already hold single-trade verdicts such as "Entry was wrong from the
first bar"), anything that happened after the exit, and any interval or
significance figure.

A field the data cannot supply is printed as `not recorded`, never estimated.

### The look record

Each run appends one line to `docs/superpowers/results/looks.jsonl`: skill,
date, trade id, and the trade's close date. `/prereg` (v155) lists the looks
that fall inside a new pre-registration's window in its stub. The file is
append-only and committed with whatever change follows the review.

### Codex mirror

`sync_codex.py` mirrors the skill; `AGENTS.md` names it in the same commit.

## Open before a plan

The panel showed this spec was written ahead of the data. A plan needs these
answered by a code brief first, and any "no" removes the line from the output
shape rather than adding code under a `Bump: none` spec:

1. Which store holds the alerted plan and the fill (price and time) for a
   closed trade, and whether a fill is recorded separately from the alerted
   entry at all — this is a paper-trading bot.
2. Whether that store is readable locally or only on production (then through
   `prod-inspector`, read-only).
3. Whether `trade["entry"]` in `mfe_mae.py` is the alerted entry or the fill.
4. Whether alert time, earnings dates and a dollar-volume figure are available
   per trade without new code.

## Edge cases

- An open trade: refused — excursions are not final.
- A trade id that does not exist: one line, and no look record.
- Production unreachable: the wrapper's error is reported and the skill stops;
  it never falls back to a stale local copy without saying so.

## Testing

- `tests/hooks/test_skill_shape.py`: the name joins `TIER_2` and the slash-only
  set; an assertion pins the fixed closing line and that the skill text names
  the excluded fields.
- A test for the look-record writer: one line appended, existing lines
  untouched.
- `tests/hooks/test_codex_mirror.py` green after `sync_codex.py`.
- Manual, recorded in the plan's results: one run against a real closed trade.

## Parallelisation

A chain of one: the look-record writer, then the skill that calls it.

## Out of scope

- Fixing `quarterly_revalidation.py`; a real per-day review; a live-versus-
  replay fill comparison. Each needs code and its own spec.
- Any new analytics module or any change to `mfe_mae.py` or `journal.py`.
- Any automatic action on a finding.

## Panel review

Run 2026-10-10 on `5def7b07`. quant-researcher returned two BLOCKING and seven
ADVISORY; veteran-trader two BLOCKING and four ADVISORY.

- quant-researcher: BLOCKING — "degraded" has no pre-registered definition in `quarterly_revalidation.py` — applied (`/revalidate` removed).
- quant-researcher: BLOCKING — the revalidation verdict can never be DEGRADED as wired — applied (removed; recorded under Why and Out of scope).
- veteran-trader: BLOCKING — no fill-versus-plan line, and the journal row lacks the plan — applied (lines 1–2; source left to the brief).
- veteran-trader: BLOCKING — MFE/MAE reference price, entry-day inclusion and no bar index — applied (line 4).
- quant-researcher: revalidation flags only a drop in `p_value`, `p_ruin`, `max_dd_p95` — recorded under Why; not this spec's to fix.
- quant-researcher: the v93 trust rule is an enable test, not a decay test — applied (citation removed with `/revalidate`).
- quant-researcher: pin that `/revalidate` never passes a window — rejected: the skill is removed.
- quant-researcher: the closing line is not enough for looks at the live book — applied (look record).
- quant-researcher: `market_day_report.py` has no date argument — applied (`/market-day-review` removed).
- quant-researcher: "past the stop afterwards" is hindsight; auto-lessons are N = 1 verdicts — applied (both excluded).
- quant-researcher: the test pinned only the closing string — applied (excluded fields pinned).
- veteran-trader: placeable before the open, expiry state, liquidity — applied (lines 3, 5, 6).
- veteran-trader: the day review is not a trader's day review — applied (removed).
- veteran-trader: the parity scripts do not compare live fills with replay — applied (`/live-drift` removed).
- veteran-trader: show gap and slippage so the trader can judge — applied (line 2).

# v211 — Avoid mode for the idea check, and the bearish-gap-in-path idea

**Version:** ui 1.39.1 · bot 2.16.5
**Bump:** none (a measurement instrument and one screen run; nothing live changes)
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** quant-researcher, quant-engineer, technical-analyst

## Why

On 2026-11-06 the partner asked what the live book's losses since September
teach. The export (`scripts/ops/export_book_rows.sh rows`, read-only) held 392
closed trades opened 2026-09-01..2026-11-06. One population stood out at the
signal level:

| Population (live book, exploratory, in-sample) | N | ExpR | WR |
|---|---|---|---|
| Longs whose plan attribution is `FVG (bearish)`, Sep 1 onward | 68 | −0.199 | 19% |
| Same, before Sep 1 | 61 | −0.060 | — |
| Longs attributed `FVG (bullish)`, Sep 1 onward | 33 | +0.298 | 36% |

The label is not the trigger. `primary_strategy_for`
(`swingbot/core/planning/builders.py`) names the highest-priority source
behind the plan's **target**: these longs bought at an ordinary support with
an unfilled bearish fair-value gap overhead acting as the target magnet. The
partner's hypothesis, chosen over a "recently broke down" framing: **an
unfilled bearish gap between entry and target stalls the move before TP1.**

These figures justify a screen, not a gate. They are why this idea is being
screened, and they say nothing about whether it holds out of sample.

Two obstacles stand in the way, and this spec removes both:

1. **The screen cannot test an avoid idea.** Stage −2
   (`backtest-methodology.md` § Funnel stages) passes an idea only when its
   events beat a matched random baseline by ≥ +0.10R. A veto written in
   keep form ("long only when the path is clear") selects most bars, so its
   events are nearly the baseline and the delta is diluted towards zero by
   construction. The near-high short veto worked in keep form only because
   its keep condition was narrow. Here the narrow, suspect population is the
   one to avoid.
2. **The closest closed row is v68 `DEAD_CAT_BOUNCE_VETO`** (validation
   failed, budget spent). It keyed on decline size and a gap. This idea keys
   on **where an unfilled bearish gap sits relative to the trade's path**,
   which v68 never measured. The keep-form "gap within X ATR overhead"
   variant was rejected by the partner as too close to v68.

## Goals

- **G1. Avoid mode for the Stage −2 screen.** An idea module may export
  `MODE = "avoid"` (default `"edge"`, today's behaviour). The mode is part of
  the idea's frozen definition, like `RACE`, `DIRECTION` and `ENTRY`. A
  changed mode is a new idea with a new name. An avoid idea passes only if
  all four mirrored clauses hold:
  1. paired ΔExpR ≤ −0.10R;
  2. upper 95% week-clustered bootstrap bound < 0 (10,000 resamples, seed
     42, as today);
  3. mean d < 0 in ≥ 7 of the 9 years 2011–2019 (an empty year counts
     against);
  4. N ≥ 300, or else `SCREEN-UNDERPOWERED`, closed like a fail.
  The verdicts are `SCREEN-AVOID-PASS` / `SCREEN-FAIL` /
  `SCREEN-UNDERPOWERED`. The thresholds are today's, sign-flipped: the
  instrument is new, the bar is not lowered.
- **G2. One shot, same discipline.** `screen_idea.py` refuses a second run
  of an id already in the ledger. Its p is the share of resamples ≥ 0.
- **G3. The idea `fvg_path_block`.**
  - **Event:** the event fires at the close of bar t. It needs an unfilled
    bearish FVG whose **bottom** lies strictly above `Close[t]` and at or
    below the race's target, `Close[t] + 3 × ATR14[t]`.
  - **Gap detection:** gaps come from the live detector,
    `swingbot/core/market/fvg.py` `find_fair_value_gaps_detailed`, with live
    defaults: `LOOKBACK_BARS`, `MAX_GAPS_PER_SIDE`, mode `all`.
  - **No lookahead:** detection sees only bars ≤ t. A gap formed at bar i
    is confirmed only at bar i+1 ≤ t, and "unfilled" is checked through t.
  - **Onset only:** the event fires on the first bar the condition becomes
    true for a given gap. It fires again only after the condition has
    been false for at least one bar.
  - **Race:** `RACE = "fixed"`, `DIRECTION = "long"`, `ENTRY = "next_open"`,
    `MODE = "avoid"`. `CAP` is chosen at idea registration and frozen in the
    module, never tuned.
  - **`SOURCE`:** live-book loss review 2026-11-06.
- **G4. Spec gate accepts an avoid pass.** `tests/hooks/test_spec_screen_header.py`
  accepts `<ledger-id> SCREEN-AVOID-PASS` for a spec whose `Edge:` is
  `expectancy` and which adds a **veto** filter. Every other case keeps
  requiring `SCREEN-PASS`.
- **G5. Docs.** `backtest-methodology.md` § Funnel stages gains the avoid
  mode, its clauses and the one-shot rule. `document-conventions.md`'s
  `Screen:` table gains the `SCREEN-AVOID-PASS` row. Each change gets its
  `AGENTS.md` mirror in the same commit.
- **G6. Run the one shot** through `backtest-runner`. Results go to
  `docs/superpowers/results/<date>-screen-fvg_path_block.md` and one ledger
  row. Record the verdict in this spec's closing commit.

## Non-goals

- No veto ships here. An avoid pass buys a **spec** for a confluence-plan
  veto ("no long when an unfilled bearish FVG sits between entry and TP1").
  That spec then runs the unchanged funnel (Stage −1..3) on the bot's own
  replay.
- No change to the edge-mode pass rule or any existing idea's verdict. Every
  existing idea reads `MODE = "edge"` byte-identically. A witness test pins
  this.
- No short-side mirror. A bullish FVG below a short's path is a different
  idea with its own name, and is not requested.
- No re-run of any closed idea under the avoid mode.

## Anti-goals

- **Threshold shopping.** If the avoid run fails, the idea is closed. A
  different gap rule (the gap mid instead of the bottom, a k × ATR band, the
  displacement mode) is a new idea that needs its own reason, never a retry.
- **Re-opening v68 by the back door.** The event must never key on decline
  size, drawdown depth or distance from a high.

## Constraints

- The live gap detector is reused, never reimplemented. If the screen needs
  a vectorised form for speed, a parity test must prove it gives the same
  gaps as `find_fair_value_gaps_detailed` on fixture frames.
- Every function stays under complexity 15.
- `screen/verdict.py` stays one module. The avoid clauses are table-driven
  beside the edge clauses, not a parallel copy.
- Tests are part of the work:
  - verdict clauses in both modes, including the edges (exactly −0.10, an
    empty year, N = 299/300);
  - the registry pin for `MODE`;
  - the onset rule;
  - no lookahead (a gap confirmed at t+1 must not fire at t);
  - the hook's new acceptance and rejection cases.

## Left to the builder

- Where `MODE` is read in `screen_idea.py`, and the results-doc wording for
  an avoid verdict.
- `CAP` for the idea (pick from the idea family's precedent and freeze it).
- Whether the avoid p and bound reuse `stats` helpers or need one small
  addition.

## What follows

- `SCREEN-AVOID-PASS`: brainstorm the confluence veto spec, which cites this
  ledger id.
- `SCREEN-FAIL` / `SCREEN-UNDERPOWERED`: closed. Record the result in
  `backtest-methodology.md`'s closed table. The live-book population stays
  visible in the autopsy and nothing more.

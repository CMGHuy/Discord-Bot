# Gatekeeper v7 - Part Index (split of the 219-task master plan)

> **Status (verified 2026-07-27): 0 of 219 tasks *implemented* (no code written).** Every checkbox across all 12 parts is unchecked, `swingbot/core/gate/` doesn't exist, no `tests/test_gate_*.py` exist, no `feature/gatekeeper-v6`/`-v7` branch was ever created, and git log has zero implementation commits for this plan — only planning commits (write, split, delete master). Treat this plan as not started, full stop.
>
> This is separate from plan-document *enrichment* (expanding collapsed task stubs into full TDD detail): that work tracked "G1-G130 enriched, resume at G131" as of 2026-07-17, but a check of the current 12 parts on 2026-07-27 finds **zero remaining stub markers anywhere** — every task, including G131 onward, already carries full failing-test/implementation/commit detail. That enrichment pass apparently continued to completion in a session that never updated its own progress note. Enrichment being done does not mean implementation is done — see above.

The master plan `2026-07-14-gatekeeper-v6.md` (~15k lines, 822 KB) was split into the part files below so executing agents work from a document sized to their context. Content is verbatim; every part repeats the master's goal, honesty rules, prerequisites, global constraints and target file structure, so a part is self-contained.

> **The master file was deleted on 2026-07-26** — at 822 KB (~210k tokens) it was larger than a context window and served no purpose once split. These parts are the plan. Verified before deletion: all 216 task sections (G1–G216) present with no gaps, and every phase preamble carried over (repeated at the head of each continuation part), making the parts a strict content superset. The other 12 files' "extracted verbatim from the master plan" notes now refer to a file that exists only in git history — recover it with `git show 79178a5:docs/superpowers/plans/2026-07-14-gatekeeper-v6.md` if ever needed.

**Execution rules**

- Execute parts in numeric order; within a part, tasks in order. A part may start only when every earlier part's tasks are checked off.
- Each part ends at a natural boundary (phase checkpoint or section boundary); phase checkpoints (G8, G44, G88, G118, G146, G166, G196, G216, G219) must be green before moving on.
- Update the **Progress** block of the part you are executing (and mirror completion into this index) after each batch.
- The master file stays as the reference copy - do not execute from it; if a part is edited during execution, back-port the edit to the master afterwards.

| Part | File | Tasks | Scope | Status |
|---|---|---|---|---|
| 1 | [2026-07-14-gatekeeper-v7_1.md](2026-07-14-gatekeeper-v7_1.md) | G1-G8 | Honest math, contracts & scaffolding | not started |
| 2 | [2026-07-14-gatekeeper-v7_2.md](2026-07-14-gatekeeper-v7_2.md) | G9-G28 | Macro data layer I: plumbing, FRED series, market internals | not started |
| 3 | [2026-07-14-gatekeeper-v7_3.md](2026-07-14-gatekeeper-v7_3.md) | G29-G44 | Macro data layer II: events, news, snapshot & degradation | not started |
| 4 | [2026-07-14-gatekeeper-v7_4.md](2026-07-14-gatekeeper-v7_4.md) | G45-G56 | Checklist engine I: HTF context & setup quality (sections 1-2) | not started |
| 5 | [2026-07-14-gatekeeper-v7_5.md](2026-07-14-gatekeeper-v7_5.md) | G57-G67 | Checklist engine II: the 11 red flags (section 3) | not started |
| 6 | [2026-07-14-gatekeeper-v7_6.md](2026-07-14-gatekeeper-v7_6.md) | G68-G88 | Checklist engine III: risk, timing & assembly (sections 4-5) | not started |
| 7 | [2026-07-14-gatekeeper-v7_7.md](2026-07-14-gatekeeper-v7_7.md) | G89-G118 | Backtest validation & the win-rate frontier | not started |
| 8 | [2026-07-14-gatekeeper-v7_8.md](2026-07-14-gatekeeper-v7_8.md) | G119-G146 | Scan pipeline & alert integration | not started |
| 9 | [2026-07-14-gatekeeper-v7_9.md](2026-07-14-gatekeeper-v7_9.md) | G147-G166 | Discord command suite | not started |
| 10 | [2026-07-14-gatekeeper-v7_10.md](2026-07-14-gatekeeper-v7_10.md) | G167-G196 | Admin frontend | not started |
| 11 | [2026-07-14-gatekeeper-v7_11.md](2026-07-14-gatekeeper-v7_11.md) | G197-G216 | Ops, governance & wrap-up (+ traceability appendix) | not started |
| 12 | [2026-07-14-gatekeeper-v7_12.md](2026-07-14-gatekeeper-v7_12.md) | G217-G219 | Carried-over verification debt from completed/skipped plans | not started |

Phase map: Part 1 = Phase G0 · Parts 2-3 = Phase G1 · Parts 4-6 = Phase G2 · Part 7 = Phase G3 · Part 8 = Phase G4 · Part 9 = Phase G5 · Part 10 = Phase G6 · Part 11 = Phase G7 + appendix · Part 12 = Phase G8 (carried-over debt, added 2026-07-27).

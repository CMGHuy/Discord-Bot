# Gatekeeper v7 - Part index (post win-rate audit, 2026-07-29)

> **Status: 24 of 90 tasks implemented — Parts 1-2 (Phases G0-G1) complete** (2026-07-29).
>
> Part 1 (G1-G8) and Part 2 (G9-G44) are committed and green. `swingbot/core/gate/` holds
> `wr_math.py`, `types.py`, `registry.py`, `score.py`; `swingbot/core/macro/` holds `httpcache.py`,
> `fred.py`, `vix.py`, `sectors.py`, `breadth.py`, `composite.py`, `calendar_events.py`,
> `sessions.py`, `earnings.py`, `snapshot.py`, `history.py`; the pre-scan refresh is wired into all
> four `run_scan` call sites. Phase G1 checkpoint passed at **1194 passed, 54 skipped, 1 failed** —
> that failure is the repo's documented pre-existing
> `test_trade_monitor_wiring.py::test_flag_on_polls_open_plans`, not a regression.
>
> **Partial data (needs a FRED key):** `event_history.json` is FOMC-only; `history/vix.json` is
> ungenerated. See Part 2's Progress block for the two commands.
>
> Work is happening **directly on `main`** (operator's choice 2026-07-29 — no feature branch), one
> commit per task, subject-tagged `type(Gxx):`. Everything from G9 on is unchecked. Verify with
> `git log --oneline --grep "^feat(G\|^test(G\|^chore(G"` before trusting this line.
>
> **Correction (2026-07-29):** G12 (FRED client) was cut by the audit and **restored** during
> execution — the cut was wrong. G21 pulls VIX via `fred_series`, and G29/G30/G41 need
> `fred_release_dates`. Only the G13-G20 series registry stays cut. Two smaller dangling references
> (G41's `series.py` import, G43's `health.py` monkeypatch) are handled with inline audit notes in
> Part 2 rather than restoring those tasks.

## What this plan is now

The plan was written as **219 tasks across 12 parts (~1 MB)**. Two audit passes (2026-07-28,
2026-07-29) pruned it to **90 tasks across 5 parts (~470 KB)** and merged the survivors back
together. The single admission test:

> **Does this task change which setups get filtered, or prove that the filtering works?**

Everything that only reported, rendered, sized, or administered was cut. What survives is the
checklist engine, the market-context data it needs, the fold/backtest machinery that proves the
filter earns its win-rate points, and the scan/alert wiring that puts it in front of the operator.

**Task IDs were not renumbered** (G1...G219, with gaps) so older notes, cross-references and the
`_task-brief` tooling still resolve. A gap is a cut task, not missing work. Prose inside a
surviving task may still name a cut task, command or admin page - treat those mentions as no-ops
and never re-add a cut task to satisfy one.

**Structural consequences** (also stated in each part's "Scope note"):

- No FRED / inflation / curve / credit layer. The macro snapshot is VIX + breadth + sector RS +
  the event/earnings/session calendars, and `composite.py` composites those three market-internal
  inputs only.
- No news or sentiment layer. Event *timing* is kept (calendar-driven, testable); headline
  *interpretation* is gone, and with it the two rumor red flags.
- No Discord command suite (G147-G165) and no admin frontend (G167-G196). Config Fields still
  render on the existing Settings page for free; every analysis surface is a report artifact under
  `docs/superpowers/results/` instead of a page.
- No sizing tasks. Sizing moves expectancy and risk of ruin, never win rate.
- The checklist registry is **21 checks**: 13 checklist checks + 8 red flags (was 27).

## Execution rules

- Execute parts in numeric order; within a part, tasks in order, skipping ID gaps.
- Phase checkpoints (G8, G44, G88, G118, G146, G216) must be green before moving on.
- Update the **Progress** block of the part you are executing, and mirror completion into the
  status table below, after each batch.
- Never read a part file whole - `grep -n "^### Task G53" -A 120 <part>` or `/task-brief G53`.

| Part | File | Tasks | Scope | Count | Status |
|---|---|---|---|---|---|
| 1 | [_1.md](2026-07-14-gatekeeper-v7_1.md) | G1-G8 | Foundations: honest WR math, config, result types, registry, scoring, fixtures | 7 | **done 2026-07-29** |
| 2 | [_2.md](2026-07-14-gatekeeper-v7_2.md) | G9-G44 | Market context: FRED client, VIX, breadth, sector rotation, event/earnings calendar, snapshot + no-lookahead history | 17 | **done 2026-07-29** |
| 3 | [_3.md](2026-07-14-gatekeeper-v7_3.md) | G45-G88 | Checklist engine: HTF context, setup quality, 8 red flags, risk, timing, assembly | 32 | not started |
| 4 | [_4.md](2026-07-14-gatekeeper-v7_4.md) | G89-G118 | Backtest validation: decile/frontier reports, folds, ablation, permutation, shadow mode | 18 | not started |
| 5 | [_5.md](2026-07-14-gatekeeper-v7_5.md) | G119-G219 | Scan + alert integration, E2E, 4-week forward gate, wrap-up (+ carried-over debt appendix) | 16 | not started |

Phase map: Part 1 = Phase G0 - Part 2 = Phase G1 - Part 3 = Phase G2 - Part 4 = Phase G3 -
Part 5 = Phase G4 + Phase G7 + the G217-G219 appendix.

> **History:** the 822 KB master (`2026-07-14-gatekeeper-v6.md`) was deleted 2026-07-26 -
> `git show 79178a5:docs/superpowers/plans/2026-07-14-gatekeeper-v6.md` recovers it. The 12-part
> split it became lives in git history too; parts 6-12 were removed on 2026-07-29 when their
> survivors were merged into parts 1-5.

---

## Appendix - the 129 cut tasks

Kept here so a future session can see what was dropped and why, without resurrecting it. Reasons
from the 2026-07-28 pass are quoted as written then; the rest are from the 2026-07-29 merge pass.

| Task | Cut because |
|---|---|
| G2 | Pure documentation/governance (freezing WR targets in a doc); doesn't change which setups get filtered. Cut. |
| G10 | Provider health ledger — ops observability; a dead provider already degrades to `unknown` (G43). No effect on which setups pass. |
| G11 | Quota meter — free-tier budget accounting; ops only. |
| G13 | CPI series registered but never consumed by any scoring/composite function in this plan; display-only filler. Cut. |
| G14 | PPI series, same issue as G13 — no consumer, display-only. Cut. |
| G15 | PCE series not fed into risk_composite/fear_greed; context-only. Cut. |
| G16 | Labor series (unemployment/payrolls/claims) has no tie to any scoring/gating function here. Cut. |
| G17 | Policy rate series is display-only; unused by composite or checklist inputs. Cut. |
| G18 | Treasury yield levels not used by curve_state (which uses separate FRED spread series). Cut. |
| G19 | Curve spreads + inversion flags — a multi-month macro cycle signal; cannot discriminate between individual 2w-9m setups. Cut with the FRED layer. |
| G20 | Breakevens/dollar index/WTI registered with no consumer anywhere in this plan. Cut. |
| G22 | Credit stress (HYG/LQD) — same category as G19; composite regime input trimmed so the composite runs on the three inputs that actually move day to day. |
| G28 | Redundant fear/greed display gauge; no checklist consumer, duplicates risk_composite's own inputs. Cut. |
| G31 | OPEX/quad-witching calendar never wired into the macro snapshot or any named checklist/red-flag consumer. Cut. |
| G34 | Market news headlines — Finnhub plumbing whose only consumers are the cut sentiment/rumor checks. |
| G35 | Company news — same as G34. |
| G36 | Headline sentiment scorer (lexicon) — weakest evidence in the plan; no fold-validatable WR lever. |
| G37 | Rumor vs. confirmed classifier — feeds G63/G64 only, both cut. |
| G40 | Live network smoke-test script is ops/verification tooling, not scoring or gating logic. Cut. |
| G42 | Snapshot data-quality validator is diagnostic/admin visibility only; never affects scoring or gating. Cut. |
| G51 | `check_vol_expansion_direction` never fails (weight-4 noise-prone true-range split); marginal signal for the complexity added. Cut. |
| G63 | `rf_rumor_spike` — depends on the cut news/sentiment layer. |
| G64 | `rf_buy_rumor_sell_fact` — depends on the cut news/sentiment layer. |
| G66 | `rf_opex_pin` (weight 4) — lowest-weight flag and needs its own opex calendar module; cost/benefit fails. |
| G69 | Check `size_formula` — position sizing changes expectancy and risk of ruin, never win rate. |
| G71 | Check `portfolio_room` — exposure management; same reason as G69. |
| G77 | Soft-flag sizing suggestion — sizing again. |
| G82 | Checklist Discord embed string builders — pure display formatting, doesn't change any verdict. Cut. |
| G83 | Gut-check ritual buttons/modal — optional UX ritual feature, no scoring effect. Cut. |
| G84 | Journal close-hook tagging trades with gate tier/flags — post-hoc analytics logging, not gating logic. Cut. |
| G85 | Red-flag outcome stats ("receipts") — reporting/evidence for future tuning, not itself a filter. Cut. |
| G86 | Gate section in analytics snapshot — dashboard reporting integration only. Cut. |
| G105 | Pre-registered inform→enforce promotion checklist — governance/sign-off ceremony, not validation. Cut. |
| G106 | Optional enforce mode (block/downgrade) — production delivery feature, opt-in action mechanism, not validation itself. Cut. |
| G107 | Doc note deferring a validation shot to E92 — pure documentation paragraph. Cut. |
| G108 | Monthly live-vs-fold WR drift audit — ops/monitoring cron, not evidence generation itself. Cut. |
| G109 | Low-N guard formatting helper (fmt_wr) — display/formatting discipline, doesn't change analysis. CAUTION: verify no surviving task (e.g. G123's alert embed field in part 8) still needs this low-N-safe WR formatting before deleting the underlying helper function from code; port the one-liner inline if so. |
| G111 | Frontier matplotlib chart — visualization polish. Cut. |
| G112 | Decile + ablation charts — visualization polish. Cut. |
| G113 | `!frontier` Discord command — visibility-only delivery surface (the whole Discord command suite in phase G5 was cut in this audit). Cut. |
| G114 | `!tierwr` live scoreboard command — visibility-only delivery surface. Cut. |
| G115 | `!redflags` receipts command — visibility-only delivery surface. Cut. |
| G116 | Tier-sized positions fold test — sizing; a tier-weighted size cannot move WR. |
| G117 | Tier sizing live wiring — same as G116. |
| G122 | Macro context line (🌍) on alert embed — display-only market context, not derived from the gate verdict. Cut. |
| G124 | Full per-check breakdown follow-up messages — opt-in verbose duplicate of info already in G123's embed field. Cut. |
| G125 | Gut-check ritual buttons on tier ≥ A alerts — behavioral UX nudge, not part of gate scoring/blocking. Cut. |
| G126 | Gut-check outcome WR stats — pure analytics/reporting. Cut. |
| G127 | Stamp compact macro snapshot on plan at creation — record-keeping for later reporting, not live gating. Cut. |
| G129 | Digest tier-sorted rows — secondary summary-message formatting, not the alert gate itself. Cut. |
| G130 | Retrospective gains gate lines — reporting cosmetics. |
| G131 | Advisor payload integration — llm-advisor-v5 is itself 0% implemented (see G219); optional integration with no WR effect. |
| G132 | Advisor headline nuance job — same as G131, and it depends on the cut news layer. |
| G133 | Nightly analysis gains gate stats — same as G131. |
| G136 | Scan latency budget — ops; G87's per-call performance guard already covers the runtime risk. |
| G137 | Alert routing by tier (channel option) — cosmetic routing; the tier is already on the embed (G123). |
| G138 | Config completeness sweep — housekeeping. |
| G139 | Startup diagnostics — ops visibility. |
| G142 | **E2E offline — shadow path** - E2E shadow path — covered by G103/G104's own tests. |
| G143 | **E2E offline — trigger re-check hold** - E2E trigger re-check hold — covered by G128's own tests. |
| G144 | **E2E offline — total darkness** - E2E total darkness — duplicate of G43's total-degradation proof. |
| G145 | Operator runbook — documentation. |
| G147 | Discord command-suite phase (G147-G165) cut in full — read-only visibility into already-computed gate/macro state, never affects which trades get filtered. See `2026-07-14-gatekeeper-v7_0-index.md` for the audit summary. |
| G148 | Discord command-suite phase (G147-G165) cut in full — read-only visibility into already-computed gate/macro state, never affects which trades get filtered. See `2026-07-14-gatekeeper-v7_0-index.md` for the audit summary. |
| G149 | Discord command-suite phase (G147-G165) cut in full — read-only visibility into already-computed gate/macro state, never affects which trades get filtered. See `2026-07-14-gatekeeper-v7_0-index.md` for the audit summary. |
| G150 | Discord command-suite phase (G147-G165) cut in full — read-only visibility into already-computed gate/macro state, never affects which trades get filtered. See `2026-07-14-gatekeeper-v7_0-index.md` for the audit summary. |
| G151 | Discord command-suite phase (G147-G165) cut in full — read-only visibility into already-computed gate/macro state, never affects which trades get filtered. See `2026-07-14-gatekeeper-v7_0-index.md` for the audit summary. |
| G152 | Discord command-suite phase (G147-G165) cut in full — read-only visibility into already-computed gate/macro state, never affects which trades get filtered. See `2026-07-14-gatekeeper-v7_0-index.md` for the audit summary. |
| G153 | Discord command-suite phase (G147-G165) cut in full — read-only visibility into already-computed gate/macro state, never affects which trades get filtered. See `2026-07-14-gatekeeper-v7_0-index.md` for the audit summary. |
| G154 | Discord command-suite phase (G147-G165) cut in full — read-only visibility into already-computed gate/macro state, never affects which trades get filtered. See `2026-07-14-gatekeeper-v7_0-index.md` for the audit summary. |
| G155 | Discord command-suite phase (G147-G165) cut in full — read-only visibility into already-computed gate/macro state, never affects which trades get filtered. See `2026-07-14-gatekeeper-v7_0-index.md` for the audit summary. |
| G156 | Discord command-suite phase (G147-G165) cut in full — read-only visibility into already-computed gate/macro state, never affects which trades get filtered. See `2026-07-14-gatekeeper-v7_0-index.md` for the audit summary. |
| G157 | Discord command-suite phase (G147-G165) cut in full — read-only visibility into already-computed gate/macro state, never affects which trades get filtered. See `2026-07-14-gatekeeper-v7_0-index.md` for the audit summary. |
| G158 | Discord command-suite phase (G147-G165) cut in full — read-only visibility into already-computed gate/macro state, never affects which trades get filtered. See `2026-07-14-gatekeeper-v7_0-index.md` for the audit summary. |
| G159 | Discord command-suite phase (G147-G165) cut in full — read-only visibility into already-computed gate/macro state, never affects which trades get filtered. See `2026-07-14-gatekeeper-v7_0-index.md` for the audit summary. |
| G160 | Discord command-suite phase (G147-G165) cut in full — read-only visibility into already-computed gate/macro state, never affects which trades get filtered. See `2026-07-14-gatekeeper-v7_0-index.md` for the audit summary. |
| G161 | Discord command-suite phase (G147-G165) cut in full — read-only visibility into already-computed gate/macro state, never affects which trades get filtered. See `2026-07-14-gatekeeper-v7_0-index.md` for the audit summary. |
| G162 | Discord command-suite phase (G147-G165) cut in full — read-only visibility into already-computed gate/macro state, never affects which trades get filtered. See `2026-07-14-gatekeeper-v7_0-index.md` for the audit summary. |
| G163 | Discord command-suite phase (G147-G165) cut in full — read-only visibility into already-computed gate/macro state, never affects which trades get filtered. See `2026-07-14-gatekeeper-v7_0-index.md` for the audit summary. |
| G164 | Discord command-suite phase (G147-G165) cut in full — read-only visibility into already-computed gate/macro state, never affects which trades get filtered. See `2026-07-14-gatekeeper-v7_0-index.md` for the audit summary. |
| G165 | Discord command-suite phase (G147-G165) cut in full — read-only visibility into already-computed gate/macro state, never affects which trades get filtered. See `2026-07-14-gatekeeper-v7_0-index.md` for the audit summary. |
| G166 | Phase G5 checkpoint — the whole Discord command phase is cut, so there is nothing to check. |
| G167 | `/api/macro/snapshot` read API — pure display endpoint; the gate reads the snapshot file directly, doesn't need this API. Cut. |
| G168 | `/api/macro/history` chart-data endpoint — feeds charts only, no config/gating effect. Cut. |
| G169 | `/api/macro/events` calendar endpoint — blackout logic lives elsewhere; this just displays it. Cut. |
| G170 | **`GET/POST /api/gate/config`** - Admin frontend — cut wholesale. Every config Field this plan adds already renders on the existing Settings page automatically (one `Field` entry feeds both the env parser and the UI), and each analysis page duplicates a Part 4 report artifact (frontier, deciles, ablation, blocked log). No page changes which setups pass. |
| G171 | `/api/gate/results` filtered/paginated results — inspection/analytics, doesn't change gate behavior. Cut. |
| G172 | `/api/gate/frontier` + `/api/gate/flags` artifact APIs — serve precomputed backtest artifacts for display. Cut. |
| G173 | `/api/gate/blocked` + `/api/gate/telemetry` endpoints — log/telemetry display only. Cut. |
| G174 | Macro dashboard page `/macro` — visual dashboard; snapshot already auto-refreshes pre-scan. Cut. |
| G175 | **Yields & curve chart panel** - Admin frontend — cut wholesale. Every config Field this plan adds already renders on the existing Settings page automatically (one `Field` entry feeds both the env parser and the UI), and each analysis page duplicates a Part 4 report artifact (frontier, deciles, ablation, blocked log). No page changes which setups pass. |
| G176 | **Inflation trend panel** - Admin frontend — cut wholesale. Every config Field this plan adds already renders on the existing Settings page automatically (one `Field` entry feeds both the env parser and the UI), and each analysis page duplicates a Part 4 report artifact (frontier, deciles, ablation, blocked log). No page changes which setups pass. |
| G177 | **Sector rotation heatmap page `/sectors`** - Admin frontend — cut wholesale. Every config Field this plan adds already renders on the existing Settings page automatically (one `Field` entry feeds both the env parser and the UI), and each analysis page duplicates a Part 4 report artifact (frontier, deciles, ablation, blocked log). No page changes which setups pass. |
| G178 | **Breadth + sentiment panels on `/macro`** - Admin frontend — cut wholesale. Every config Field this plan adds already renders on the existing Settings page automatically (one `Field` entry feeds both the env parser and the UI), and each analysis page duplicates a Part 4 report artifact (frontier, deciles, ablation, blocked log). No page changes which setups pass. |
| G179 | **Event calendar page `/events`** - Admin frontend — cut wholesale. Every config Field this plan adds already renders on the existing Settings page automatically (one `Field` entry feeds both the env parser and the UI), and each analysis page duplicates a Part 4 report artifact (frontier, deciles, ablation, blocked log). No page changes which setups pass. |
| G180 | **Checklist config page `/gate`** - Admin frontend — cut wholesale. Every config Field this plan adds already renders on the existing Settings page automatically (one `Field` entry feeds both the env parser and the UI), and each analysis page duplicates a Part 4 report artifact (frontier, deciles, ablation, blocked log). No page changes which setups pass. |
| G181 | **Red-flag analytics page `/gate/flags`** - Admin frontend — cut wholesale. Every config Field this plan adds already renders on the existing Settings page automatically (one `Field` entry feeds both the env parser and the UI), and each analysis page duplicates a Part 4 report artifact (frontier, deciles, ablation, blocked log). No page changes which setups pass. |
| G182 | **Frontier page `/gate/frontier`** - Admin frontend — cut wholesale. Every config Field this plan adds already renders on the existing Settings page automatically (one `Field` entry feeds both the env parser and the UI), and each analysis page duplicates a Part 4 report artifact (frontier, deciles, ablation, blocked log). No page changes which setups pass. |
| G183 | **Blocked-log viewer `/gate/blocked`** - Admin frontend — cut wholesale. Every config Field this plan adds already renders on the existing Settings page automatically (one `Field` entry feeds both the env parser and the UI), and each analysis page duplicates a Part 4 report artifact (frontier, deciles, ablation, blocked log). No page changes which setups pass. |
| G184 | **Gut-check journal browser section** - Admin frontend — cut wholesale. Every config Field this plan adds already renders on the existing Settings page automatically (one `Field` entry feeds both the env parser and the UI), and each analysis page duplicates a Part 4 report artifact (frontier, deciles, ablation, blocked log). No page changes which setups pass. |
| G185 | **Live gate status fragment on the dashboard** - Admin frontend — cut wholesale. Every config Field this plan adds already renders on the existing Settings page automatically (one `Field` entry feeds both the env parser and the UI), and each analysis page duplicates a Part 4 report artifact (frontier, deciles, ablation, blocked log). No page changes which setups pass. |
| G186 | **Provider health page `/macro/health`** - Admin frontend — cut wholesale. Every config Field this plan adds already renders on the existing Settings page automatically (one `Field` entry feeds both the env parser and the UI), and each analysis page duplicates a Part 4 report artifact (frontier, deciles, ablation, blocked log). No page changes which setups pass. |
| G187 | **Quality warnings surfacing** - Admin frontend — cut wholesale. Every config Field this plan adds already renders on the existing Settings page automatically (one `Field` entry feeds both the env parser and the UI), and each analysis page duplicates a Part 4 report artifact (frontier, deciles, ablation, blocked log). No page changes which setups pass. |
| G188 | **Config audit trail viewer** - Admin frontend — cut wholesale. Every config Field this plan adds already renders on the existing Settings page automatically (one `Field` entry feeds both the env parser and the UI), and each analysis page duplicates a Part 4 report artifact (frontier, deciles, ablation, blocked log). No page changes which setups pass. |
| G189 | **Navigation + empty states sweep** - Admin frontend — cut wholesale. Every config Field this plan adds already renders on the existing Settings page automatically (one `Field` entry feeds both the env parser and the UI), and each analysis page duplicates a Part 4 report artifact (frontier, deciles, ablation, blocked log). No page changes which setups pass. |
| G190 | **Auth/CSRF parity test** - Admin frontend — cut wholesale. Every config Field this plan adds already renders on the existing Settings page automatically (one `Field` entry feeds both the env parser and the UI), and each analysis page duplicates a Part 4 report artifact (frontier, deciles, ablation, blocked log). No page changes which setups pass. |
| G191 | **Fragment live-refresh wiring** - Admin frontend — cut wholesale. Every config Field this plan adds already renders on the existing Settings page automatically (one `Field` entry feeds both the env parser and the UI), and each analysis page duplicates a Part 4 report artifact (frontier, deciles, ablation, blocked log). No page changes which setups pass. |
| G192 | **Mobile pass** - Admin frontend — cut wholesale. Every config Field this plan adds already renders on the existing Settings page automatically (one `Field` entry feeds both the env parser and the UI), and each analysis page duplicates a Part 4 report artifact (frontier, deciles, ablation, blocked log). No page changes which setups pass. |
| G193 | **Admin e2e — fixture-city walkthrough** - Admin frontend — cut wholesale. Every config Field this plan adds already renders on the existing Settings page automatically (one `Field` entry feeds both the env parser and the UI), and each analysis page duplicates a Part 4 report artifact (frontier, deciles, ablation, blocked log). No page changes which setups pass. |
| G194 | **Accessibility pass** - Admin frontend — cut wholesale. Every config Field this plan adds already renders on the existing Settings page automatically (one `Field` entry feeds both the env parser and the UI), and each analysis page duplicates a Part 4 report artifact (frontier, deciles, ablation, blocked log). No page changes which setups pass. |
| G195 | **Visual QA checklist** - Admin frontend — cut wholesale. Every config Field this plan adds already renders on the existing Settings page automatically (one `Field` entry feeds both the env parser and the UI), and each analysis page duplicates a Part 4 report artifact (frontier, deciles, ablation, blocked log). No page changes which setups pass. |
| G196 | Phase G6 checkpoint — the whole admin frontend phase is cut (see below). |
| G197 | Nightly purge of expired macro HTTP cache files — disk hygiene, not gating; no effect on trade filtering if it never runs. Cut. |
| G198 | 200MB soft cap + oldest-first prune on macro/gate dirs — same category as G197, slow-moving risk, not decision-critical. Cut. |
| G199 | Discord alert on provider degraded >12h — pure visibility; degradation already never blocks per G43. Cut. |
| G200 | Daily API quota usage projection/warning — proactive convenience; quota exhaustion already degrades gracefully. Cut. |
| G201 | Secrets hygiene audit — repo hygiene. |
| G202 | --dry-run/--only/resume flags + rebuild runbook for backfill scripts — dev-ops convenience and docs, no gating impact. Cut. |
| G203 | Weekly Discord report of gate divergence/tier WR/quota — reporting ceremony, doesn't change any decision. Cut. |
| G204 | Monthly WR honesty audit — governance ritual; G102/G104 already produce the honest numbers. |
| G205 | Quarterly re-validation hook — governance ritual. |
| G207 | Promotion + rollback runbook — documentation; the promotion criteria live in G95/G206. |
| G208 | Pre-mortem doc of 7 failure modes — mostly brainstorming prose; any real code check it contains is trivial and already covered elsewhere. Cut. |
| G209 | README "Gatekeeper" section — pure documentation. Cut. |
| G210 | Deploy notes (env keys, backup scope, quota) — pure documentation. Cut. |
| G211 | .env.example keys + settings-page render test — UI completeness housekeeping, not gating logic. Cut. |
| G212 | AST tests proving pure gate modules do no I/O — code-quality/architecture hygiene, no effect on win rate. Cut. |
| G213 | Test suite time-budget tripwire for gate/macro tests — pure CI ergonomics. Cut. |
| G214 | Lint/type sweep over new files — pure ceremony. Cut. |

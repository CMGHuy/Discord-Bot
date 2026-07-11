# Trading Cockpit (Round 3) — Plan Index

Three separate, independently executable plans that turn the validated plan-engine-v2 output into a decision cockpit: the fastest possible path from "the bot scanned" to "this is the plan I follow, and here is the evidence."

**Total: 115 tasks across 3 plans.** Written 2026-07-11, assuming `2026-07-11-unified-plan-engine-v2.md` (110 tasks) is fully implemented and merged to `main`.

## The plans

| Plan | File | Branch | Tasks | Delivers |
|---|---|---|---|---|
| **A — Analytics & Insight Core** | `2026-07-11-analytics-core.md` | `feature/analytics-core` | **31** (A1–A31) | `swingbot/core/analytics/` package: equity/drawdown/streak/rolling metrics, MFE/MAE + exit efficiency, 10-dimension StatRow aggregation, quality-score calibration, pre-registered edge-decay rule, the shared `follow_score` ranking, per-trade lessons journal with auto-tags + templates, weekly digest, snapshot file for fast UIs, atomic JSON writes, backfill + export scripts. |
| **B — Discord Experience v3** | `2026-07-11-discord-ux-v3.md` | `feature/discord-ux-v3` | **38** (B1–B38) | Tier/badge-themed embed design system, follow-score-ranked alerts with "why follow this" breakdown, interactive Views (chart/breakdown/watch/dismiss, filterable paginated plan board), `!top` `!stats` `!lessons` `!calibration` `!journal` + slash parity, chart v2 overlays (R:R bands, trigger arrows, trail path, MFE/MAE markers), analytics charts (equity, R-histogram, calibration, heatmap), content-hash chart cache + async rendering, flag-gated daily Top-Plans digest. |
| **C — Admin Control Center** | `2026-07-11-admin-cockpit.md` | `feature/admin-cockpit` | **46** (C1–C46) | Live plan-lifecycle board with actions, Strategies page (registry provenance, strategy×horizon heatmap, drift alerts, sparklines), Calibration + Journal browser pages, TRAIN-only tuning workbench (job manager, guardrail, results grid, proposals with diffs), Settings v2 (diff preview, audit trail, export/import profiles), dashboard pedigree chips + equity sparkline, vendored assets / ETag / gzip / cache-header performance work, JSON API layer, Flask test harness. |

## Execution order & dependencies

```
plan-engine-v2 (merged)
        │
   Plan A  (analytics core — the data layer)
        │
   ┌────┴────────┐
Plan B         Plan C        ← independent; can run in PARALLEL branches
(Discord)      (Admin web)
```

- **Plan A first, alone.** Both B and C import `swingbot/core/analytics/*`; nothing in A depends on B/C.
- **B and C are parallel-safe**: they share no files except `swingbot/config.py` (each adds Fields) — a trivial merge. B also creates `charts/cache.py` which C12 optionally reuses; C12 explicitly works without it.
- Each plan ends with its own checkpoint task (full pytest + `make check` + live smoke) and leaves `main`-mergeable, independently useful software.

## Design decisions binding all three plans

1. **One ranking authority.** `analytics.rank.follow_score` (badge 40 + quality 40 + regime 10 + freshness 10) is computed in exactly one place; Discord alerts, `!plans`, `!top`, the digest, `/api/plans`, and the admin board all consume it. If the formula ever changes, every surface changes together.
2. **One stat definition.** Win rate / expectancy R keep the round-1/v2 semantics; every UI number traces to a Plan A function with a unit test. No formula lives in a template, embed builder, or route.
3. **Compute once, render everywhere.** `data/analytics_snapshot.json` (rebuilt post-scan and post-close) backs `!stats`, `/api/stats`, the Performance page, and the Strategies heatmap — request-time cost is a file read.
4. **Lessons are generated, not remembered.** Every trade close writes a journal entry (MFE/MAE, exit efficiency, tags, templated lesson); the daily retrospective, weekly digest, `!lessons`, and the admin Journal browser are different views of the same store.
5. **Validation hygiene survives the UI.** The tuning workbench physically cannot touch 2024–2025 (`assert_train_only`, tested); tuning output is a proposal file, never an applied change. The edge-decay alert rule (live N ≥ 20 and live WR < OOS WR − 10) is pre-registered here, before any live data exists.
6. **WEAK is de-emphasized, never hidden** — amber color, compact caution line, excluded only from the curated digest.
7. **No new pip dependencies anywhere**; admin JS assets vendored (offline-capable); all new Discord behavior that changes channel output ships behind default-off config Fields.

## Suggested execution

Per plan: create the branch, then run with superpowers:subagent-driven-development (fresh subagent per task, review between tasks) or superpowers:executing-plans (inline batches). Update each plan's Progress block as phases complete, as done for plan-engine-v2.

# Repo cleanup audit (Phase 1 of v40)

Design: `docs/superpowers/specs/implemented/2026-08-21-v40-repo-cleanup-audit-design.md`
(moved there 2026-08-22 when its one plan, v41, closed).
Six parallel read-only forks, one per subsystem, run concurrently with plan
v36 (which lives in a separate, unmerged worktree — nothing here reflects
v36's in-progress changes; `core/planning` etc. were audited at their
pre-v36 state on `main`). Each finding cleared three guardrail checks
(re-export grep, `docs/superpowers/results/` grep, edge-engine-wiring check)
before being listed; anything that didn't clear was dropped, not downgraded.

**Total: 1 confirmed bug, 14 candidates, 8 suspected items, across ~36K lines
directly reviewed.** No systemic spaghetti found — this codebase's own
cleanup discipline (v27 restructure, Release B, same-day shim removal) is
holding. What's here is mostly small, mechanical, low-risk.

## Confirmed bugs (1)

- **`swingbot/core/marketdata/backtest_cache.py:65` (`fetch()`) skips alias
  resolution** that every sibling fetch path (`data.py`, `data_store.py`,
  `export_data.py`) performs via `ticker_utils.candidate_symbols()`. Any
  alias ticker in `ticker_utils.ALIASES` (SPX, XAUUSD, WTI, BRENT, VIX, NDX,
  DJI, US500, US100, US30, DOWJONES, XAG, SILVER, XAGUSD, USOIL, UKOIL,
  BTCUSD, ETHUSD — everything except the bare-fetchable GOLD/OIL overrides)
  silently never gets `data/backtest_cache/{TICKER}.csv` populated, even
  though it resolves fine everywhere else (scanning, charting, live plans).
  Both watchlist-add entry points call this path with the raw, unresolved
  ticker. Repro'd with a monkeypatched `yf.download`:
  `backtest_cache.fetch("SPX")` requests only `['SPX']`;
  `data.get_daily_data("SPX")` requests `['SPX', '^GSPC']`. **Fix size:
  small** — mirror the `candidate_symbols` loop already used by the sibling
  modules. *(area 1: marketdata/infra)*

## Candidate dead-code & simplification (14)

**Trivial (no behavior risk, mechanical):**
- `core/infra/state.py:33` — `StateStore.get_last_trend`/`set_last_trend`
  have no production caller, only their own test. *(area 1)*
- `core/marketdata/backtest_cache.py:109` — `ensure_cached_background`'s
  already-cached branch spawns a no-op `Thread` purely for return-type
  uniformity. *(area 1)*
- `core/market/explain.py:49` — local `opp_word` assigned, never read.
  *(area 2)*
- `core/market/explain.py:66` — local `s_count` computed, never read
  (unlike its sibling `t_count`, which is used) — worth a glance in case the
  stop-side message is missing a pluralization the target-side has, before
  a pure delete. *(area 2)*
- `core/edge/growth.py:122-124` — three f-strings with no `{}`
  placeholders; the `f` prefix is a no-op. *(area 2)*
- `core/tracking/retrospective.py:703,708,713` — same no-op-`f`-prefix
  pattern, three more spots. *(area 3)*
- `core/scanning/engine.py:55` — `import discord` is never used in the
  file, and its presence is a stray violation of `architecture.md`'s "core/
  has no Discord dependency" boundary. *(area 4)*
- `core/scanning/engine.py:96-99` — re-exports `CONFIDENCE_EMOJI`/
  `CONFIDENCE_ANSI` from `embeds.py`; zero external consumers of either name
  via `scan_engine.*` (unlike `CONFIDENCE_COLORS`/`confidence_color`, which
  are genuinely consumed and must stay). Only worth doing alongside the
  `import discord` cleanup above, not alone. *(area 4)*
- `frontend/src/app/workspaces/analytics/analytics.ts:1412` — a literal NUL
  byte used as a Map-key separator makes ripgrep/`git grep`/this repo's
  `Grep` tool silently treat the whole file as binary, hiding its contents
  (including the real `createClientPage` usages) from grep-based
  verification. **This is a tooling landmine that will cause future false
  "unused" verdicts in this file specifically** — worth fixing precisely
  because it undermines the guardrail process itself, not because current
  behavior is wrong. *(area 5)*
- `docs/claude/known-traps.md` (Trade History section) and
  `admin/api_v1/__init__.py:75` (comment) both cite a nonexistent symbol
  `_query_closed_trades()`. The real function is `query_closed_trades()`
  (`admin/dashboard.py:272`, no leading underscore). Doc/comment drift —
  fix both references. *(area 5)*
- `scripts/data/migrate_market_data.py` — one-shot migration script whose
  job (v27's `market_data/` layout change) completed 2026-08-15; a fresh
  checkout can never hit the old layout it converts from. Not flagged for
  outright removal (cheap insurance) — a Phase 2 keep/delete call. *(area 6)*

**Small:**
- `core/planning/plan_engine.py:659-696` — `_resolve_stop_mult`,
  `_resolve_tp2_r`, `_resolve_time_stop_days` are three near-identical
  functions (flag check → `edge.stops` import+call → log+return-None on
  exception); collapsible into one helper parameterized by function + log
  label, no behavior change if done mechanically. *(area 3)*
- **Chart-save + disclaimer-stamp logic duplicated across 4 files with
  drifting behavior**: `core/charts/analytics_charts.py`, `portfolio_charts.py`,
  `decision_chart.py`, `trade_chart.py` each independently stamp
  `DISCLAIMER_TEXT` and call `fig.savefig()`. `analytics_charts.py`'s
  version skips the disclaimer entirely (the other three include it) and is
  the *only* one of the four wrapped in `try/finally: plt.close(fig)` — the
  other three leak the matplotlib `Figure` on a `savefig` exception (disk
  full, bad path, encoder error) in a long-running bot process. Worth fixing
  the leak and the inconsistency together via one shared helper (e.g. in
  `chart_style.py`) with a `stamp_disclaimer: bool` param. *(area 4)*

**Small-to-medium (needs per-file verification first):**
- 10 test files build OHLCV DataFrames by hand instead of using
  `tests/conftest.py:make_ohlcv`/`make_trend_df`
  (`tests/charts/test_trendline_fit.py` confirmed; 9 more flagged by the
  same grep pattern but not individually verified —
  `tests/admin/test_api_v1_market.py`, `tests/backtesting/test_wf_engine.py`,
  `tests/charts/test_chart_layout.py`, `test_chart_theme.py`,
  `test_trade_chart_stored_fit.py`, `test_trendline_fit_persistence.py`,
  `tests/edge/test_avwap.py`, `tests/market/test_mtf.py`,
  `tests/scanning/test_embeds_v3.py`. One suspected match,
  `tests/market/test_events.py`, was checked and is a false positive — its
  DataFrame is EPS-estimate data, not OHLCV). Phase 2 must verify each
  before assuming it's a real duplicate; some may need shapes the shared
  fixtures don't support. *(area 6)*

## Suspected (8 — not repro'd, Phase 2 should re-look before acting)

- Duplicated "loop `candidate_symbols(ticker)`, try/except, return first
  hit" shape across 4-5 fetch functions in `data.py`, `data_store.py`,
  `export_data.py`, `backtest_cache.py`. Not marked candidate — consolidating
  live network-fetch logic risks silently changing retry/exception semantics
  that differ subtly per site. *(area 1)*
- `df.columns.get_level_values(0)` MultiIndex-flatten logic copy-pasted
  verbatim in 4 files (`backtest_cache.py`, `data.py`, `data_store.py`,
  `export_data.py`). Same judgment-call caveat as above. *(area 1)*
- `core/marketdata/fmp_client.py` (330 lines, fully tested) has no caller
  inside `core`/`commands`/`admin` at runtime — only a standalone crawl
  script uses it. Not dead (matches its own data-collection framing) but
  worth a human call on whether it's meant to eventually feed the live scan
  path. *(area 1)*
- `core/tracking/retrospective.py:70,137` — two bare
  `except Exception: return []`/`return None` with no logging, unlike the
  file's dominant log-and-degrade pattern. Could be masking a real bug, or
  could be an intentionally-silent first-run case. *(area 3)*
- Density note: 35 broad `except Exception:` blocks across
  `planning`/`backtesting`/`tracking` (14 in retrospective.py, 9 in
  performance.py); ~10 sampled and found deliberate ("degrade this section,
  don't crash the report" / "bookkeeping must never break the manager").
  Not systemic — noted for spot-checking, not flagged as a problem. *(area 3)*
- `core/charts/analytics_charts.py`'s missing disclaimer (see candidate
  above): unclear if intentional (admin-only, never Discord-posted) or
  simple drift. Needs a human UX call, not a code read. *(area 4)*
- `core/scanning/engine.py:293`'s "live sizing chain not yet wired to this
  call site" comment likely matches the documented deliberately-unwired
  edge-engine pattern — noted by name for Phase 2 to check against a
  specific wiring task, not treated as a new finding. *(area 4)*
- `core/scanning/engine.py` (2014 lines) and `commands/scanning.py`
  (1768 lines) are both large; a partial read suggests each is one cohesive
  loop rather than several glued-together responsibilities, but neither got
  a full top-to-bottom read. Worth a closer look if simplification tasks are
  being sized in Phase 2. *(area 4)*

## Clean / explicitly cleared (no action needed)

- **Area 1** (marketdata/infra): 9 of 14 files clean —
  `asset_class.py`, `ticker_utils.py`, `ticker_directory.py`, `universe.py`,
  `watchlist.py`, `notifier.py`, `silent_channel.py`, `jsonio.py`,
  `data_refresh.py`.
- **Area 2** (market/edge): 0 confirmed bugs; `signals.py`/`entry_filters.py`
  verified as genuine single-source delegation (not duplication); ~15 bare
  `except: pass` blocks in `levels.py`/`strategy.py` confirmed deliberate
  per-source fault isolation; NO-LOOKAHEAD rule verified with zero
  violations (42 `.fillna(False)` occurrences in `entry_filters.py`); all 12
  `core/edge/` modules confirmed to have production callers, including two
  only reachable via aliased imports; `core/edge/gates.py:in_earnings_blackout`
  confirmed as a documented deferred-wiring gap, not dead code.
- **Area 3** (planning/backtesting/tracking): `backtest.py`'s
  `SR_VOLUME_MULTIPLE`/`STRATEGY_GATES`/etc. re-exports confirmed
  load-bearing for `tests/test_entry_filters.py`.
- **Area 4** (scanning/analytics/charts/commands): all four documented
  invariants (sizing placement, embed-field routing via
  `sections["headline"]`, scan-loop ordering, serial-state-mutation-after-join)
  verified to hold, no violations. `core/analytics/metrics.py` singled out as
  unusually well-guarded (explicit None-not-zero-not-infinity policy on
  every ratio) — a positive example.
- **Area 5** (admin/frontend): `admin/app.py`'s `docker_sdk`/`_SECTION_META`
  re-exports, the six documented non-atomic `data/*.json` writers, and
  `createClientPage` (Analytics' documented un-paged exception) all confirmed
  load-bearing/correct. No client-side Trade History filter/sort/page logic
  found outside the server-side path.
- **Area 6** (scripts/tests): all 205 files compile cleanly; zero
  `@pytest.mark.xfail` in the suite; all skip markers have live, checkable
  reasons consistent with the documented 66-skipped baseline; every
  low-reference `scripts/backtest/*.py`/`scripts/reports/*.py` script traced
  to a closed pre-registration in `docs/superpowers/results/` — correctly
  ruled out as reproducibility artifacts, not dead code.

## Coverage gaps (what Phase 2 should read more deeply if it picks these areas)

- `core/tracking/performance.py` (1392 lines) and
  `core/planning/plan_engine.py` (1402 lines) — pyflakes + targeted grep
  only, not read end-to-end.
- `core/backtesting/backtest.py` vs `backtest_wf.py` — not compared for
  duplicated walk-forward/single-run logic.
- `core/planning/account.py` (579 lines), `core/planning/quality.py`
  (156 lines) — not read in depth.
- `core/edge/stops.py`, `core/edge/ruin.py` — caller existence confirmed
  only, not deep-read.
- Area 4's `confidence.py`, `factors.py`, `regime.py`, most of
  `commands/*.py` (account/backtest/data/growth/history/info/plans/slash/
  stats/trades/watchlist), most of `core/analytics/*.py` beyond
  `metrics.py`, and 10 of 13 `core/charts/*.py` files beyond the save-helper
  grep — grep-swept, not individually spot-checked.
- `admin/api_v1/*` error-handling shape (58 try/except across 12 files) —
  skimmed for consistency, not deep-dived per endpoint.
- `frontend/` build config and the `chart-harness/` dev tool — explicitly
  out of scope.

## Next step

Phase 2 is a separate design cycle, not started here. Once plan v36 merges
to `main`, use this document as the input: the 1 confirmed bug and the 14
guardrail-cleared candidates are low-risk enough for a first, small cleanup
plan; the 8 suspected items need one more targeted look (repro attempt or a
human UX/behavior call) before any of them become a task.

**Status (2026-08-22): closed.** Phase 2 shipped as plan
`docs/superpowers/plans/implemented/2026-08-21-v41-repo-cleanup-phase2.md` —
all 14 candidates and the 1 confirmed bug landed (bar one explicitly declined
consolidation, recorded in that plan's "Not in this plan" section); of the 8
suspected items, 2 became tasks (the two bare excepts, the missing
disclaimer), 1 was confirmed a non-issue (the density note), and the
remaining 5 were re-examined and explicitly declined rather than silently
dropped. See that plan's Progress block for the full closing account,
including two Important findings its own final review caught and fixed.

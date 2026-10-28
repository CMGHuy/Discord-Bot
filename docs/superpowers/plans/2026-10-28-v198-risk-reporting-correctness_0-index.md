# Risk reporting correctness implementation plan

> For agentic workers: use subagent-driven-development or executing-plans, one task at a time with review. This is documentation, not execution authorization.

**Bump:** ui patch, bot patch
**Edge:** none (integrity)
**Spec:** [Approved risk spec](../specs/2026-10-28-v198-risk-reporting-correctness.md)

**Goal:** Correct three demonstrated reporting failures: unavailable sources appearing safe, short positions contributing long returns, and drawdown omitting initial losses or walking the wrong chronology. Preserve useful independent data when one source fails. Add explicit coverage and unknown states throughout the API, Risk page, shell killswitch display and Discord portfolio command. Keep scan gates, sizing, stops, account accounting and entry/exit behavior unchanged. Synthetic numerical cases and injected dependency failures establish success; this plan makes no live-book performance claim.

**Architecture:** First decompose the high-complexity portfolio collector without behavioral changes. Then keep availability beside each independently collected value and expose a nullable read contract to all reporting consumers. A small admin Risk read-model module owns signed gross-normalized weights and chronological closed-record selection. The pure drawdown helper gains its missing zero baseline; general r_multiples ordering remains unchanged.

**Tech stack:** Existing Python/pandas, Flask, Angular/Vitest and shared market-data/FX interfaces; no new paid service, database schema, external data source or persisted reporting store.

## Global Constraints

- Partner approved the written specs on 2026-10-28. Quant-engineer findings on invalid balances and uncomputable outcomes are applied in the spec. All tasks implement that spec; do not invent new trading policies.
- v194 prerequisite is satisfied on main by merge/close-out 65de3bc7 (2026-10-28). Recheck current main before execution. Execute v197 before v198 by default, following the agreed delivery-first priority; preserve its additive API/model fields when editing shared files. Execute only after v194 merges, or explicitly rebase onto its merged result. Re-brief its FX, money drawdown, sector state and fixtures before executing. Preserve account/quote currency semantics. Follow v195's final Risk/shell layout if merged; this plan does not recreate page architecture.
- Version numbers resolve from then-current VERSION.json at close-out. No version number is predicted here. Bot patch covers Discord portfolio reporting; UI patch covers API/read-model and page behavior.
- Authoring runs no tests, database commands or production operations. Implement in the plan worktree when separately requested; do not use main for implementation.
- No live trading gate, account P&L write, sizing, stop, target, fill, expiry or validation-registry change. No backtest or closed pre-registration rerun is licensed.
- Each changed/new function ends below complexity 15. collect_portfolio_state is already above that: preserve its behavior in V198-1, commit that decomposition separately, then change reporting behavior. Update the shrinking complexity baseline in that refactor commit when required.
- Preserve heat.open_heat([]) as a known empty-book calculation. Failed account reads and nonfinite/nonpositive balance mean unknown heat even if the old helper returns zero.
- Successful empty reads are ok; exceptions are unavailable; incomplete sector mappings are partial. Unknown never becomes false, zero, full throttle, an empty book or a clear killswitch.
- Validate killswitch writes as explicit booleans. Unknown reads never issue a mutation or imply scanning resumed. A retained last observation carries its original timestamp and is explicitly stale.
- Use the shared FX provider supplied by v194. Weight common-currency notionals at one valuation date; quote-return model excludes historical FX return risk and labels that basis explicitly.
- Preserve configured benchmark labels and underlying-assets correlation semantics. Do not invert asset correlation entries for short positions.
- R outcomes stay dimensionless; money drawdown stays in account currency using per-exit-date FX. Invalid timestamps and invalid outcomes have separate mutually exclusive exclusion counts.
- Test new edge and empty cases per task. No new test directory without membership in exactly one tests/suites.toml suite; split a full suite rather than raising its cap.
- Before eventual database tests, run replicate-prod-db into the one shared swing-db. No per-task database container. Pure metric tests do not require a database.
- Narrow backend tests use testrun.py file; frontend uses npm test -- --include. One full backend and frontend run, and the three-width layout audit, occur only in V198-6. Fix observed failures narrowly; no full rerun after a clean merge.

## Parallelisation

Default serial execution, one agent at a time. V198-1 precedes V198-2 because the latter changes collector behavior; V198-2 precedes V198-3 because the UI consumes the new API. V198-4 and V198-5 both edit risk.py and risk_read_model.py and therefore remain sequential even though the mathematical concerns differ. V198-6 follows every task. Pure test design may be independent, but parallel dispatch needs the partner's explicit permission.

## Task ledger

| ID | Title | Part | Model | Files | Cross-task contract |
|---|---|---|---|---|---|
| V198-1 | Decompose the portfolio collector with behavior pinned | 1 | opus | Modify swingbot/core/edge/portfolio_state.py, scripts/dev/complexity_baseline.json if shrinking; create tests/edge/test_portfolio_state_collection.py | Existing collect_portfolio_state() output preserved; bounded gather/project helpers permit later availability changes |
| V198-2 | Carry unknown/partial domains through collector and Risk API | 1 | opus | Modify swingbot/core/edge/portfolio_state.py, swingbot/admin/api_v1/risk.py, swingbot/commands/growth.py, tests/admin/test_api_v1_risk.py; extend tests/edge/test_portfolio_state_collection.py; create tests/commands/test_portfolio_availability.py | Nullable domain values and availability metadata below, both risk and dedicated killswitch endpoints; Discord handles unknown |
| V198-3 | Render unknown/partial/stale states without an implicit release | 2 | sonnet | Modify frontend/src/app/api/models.ts, frontend/src/app/stores/risk.store.ts, frontend/src/app/stores/risk.store.spec.ts, frontend/src/app/workspaces/risk/risk.ts, frontend/src/app/shell/shell.ts and their existing specs; create focused state tests only where no suitable file exists | UI understands V198-2 response; current and last-known state stay separate; mutation stays explicit boolean |
| V198-4 | Compute signed common-currency gross-normalized weights | 2 | sonnet | Create swingbot/admin/api_v1/risk_read_model.py, tests/admin/test_risk_read_model.py; modify swingbot/admin/api_v1/risk.py, tests/admin/test_api_v1_risk.py | signed_weights(open_trades, *, on, account=None) -> (weights, reason), basis label and complete coverage policy below |
| V198-5 | Baseline drawdown and order closed-record populations correctly | 3 | sonnet | Modify swingbot/core/analytics/risk_metrics.py, swingbot/admin/api_v1/risk_read_model.py, swingbot/admin/api_v1/risk.py, tests/analytics/test_risk_metrics.py, tests/admin/test_risk_read_model.py, tests/admin/test_api_v1_risk.py | max_drawdown_r unchanged signature; chronological_records helper and exclusion contract below |
| V198-6 | Verify complete reporting flows and record release readiness | 3 | sonnet | Extend integration assertions in existing backend/frontend test files only where required; update this index with verification evidence and any changed suite membership | One final full-suite task, layout audit and close-out handoff; no new runtime interface |

## Parts

| Part | File | Tasks |
|---|---|---|
| 1 | 2026-10-28-v198-risk-reporting-correctness_1-collector-and-api.md | V198-1, V198-2 |
| 2 | 2026-10-28-v198-risk-reporting-correctness_2-ui-and-weights.md | V198-3, V198-4 |
| 3 | 2026-10-28-v198-risk-reporting-correctness_3-drawdown-and-verification.md | V198-5, V198-6 |

## Proposed cross-task contracts

These names are explicit authoring proposals pending plan-briefer verification and plan-writer index validation. Resolve any real interface mismatch in this index before part writing; do not silently diverge across parts.

### Availability

Each domain entry in response availability maps to {state: 'ok'|'partial'|'unavailable', checked_at: UTC ISO string, reason: string|null}. Stable keys: positions, heat, sector_heat, clusters, throttle, killswitch. Add distribution_metrics and drawdown_r/drawdown_amount domains for the later math tasks. Internal exceptions are logged with sanitized reason codes; no raw credentials or tracebacks reach JSON.

Unknown positions serialize null, known-empty positions serialize []. Heat open_pct/utilisation_pct and throttle multiplier/paused are nullable. Killswitch on is bool|null. Keep optional last_known separate, timestamped, and stale; never fill current values from it. Legacy portfolio command prints unknown for unavailable domains. A cache holds values and availability together; the fresh killswitch read always determines current availability on each response.

### Signed weights

signed_weights(open_trades: list[dict], *, on: date, account: str|None=None) -> tuple[dict[str,float], str|None]. It consumes the v194 fx.account_currency_code/quote_currency_code/fx_rate seam. reason None means complete coverage; a reason means no distributional result is defensible. Validate finite positive entry/shares, recognized bullish/bearish direction and positive finite FX. Aggregate signed per-ticker notionals, divide by gross before netting. Keep net-zero tickers with zero weights so bar coverage remains explicit, rather than dropping positions. Empty input returns ({}, None).

Do not round weights. If any necessary lookup/record is invalid, return ({}, reason) rather than a partial normalized portfolio. Market-dependent figures become unavailable while trade-derived performance survives. The actual bar-reader uses the existing shared daily path. Label weight basis as entry notional valued in account currency on the valuation date; label returns as quote returns without historical FX effects.

### Chronological records and drawdown

chronological_records(closed: list[dict], *, outcome) -> tuple[list[dict], dict[str,int]], where outcome is a callable returning float|None. Parse closed_at into aware UTC (naive timestamps follow the repository's stored UTC convention); reject missing/unparseable timestamps. Then validate the relevant finite outcome. Count date failure before outcome failure. Sort valid records by (closed_at UTC, string trade ID). Return counts with excluded_count, invalid_date_count and invalid_outcome_count; excluded_count equals the two reasons' sum. Money conversion additionally preserves v194 fx_missing_count and reports its population honestly; do not double-count a date-invalid record as an FX exclusion.

For the pure max_drawdown_r helper, empty remains None, finite outcomes start with cumulative zero and running peak zero. Nonfinite values yield None at the reporting boundary; never NaN JSON. Audit analytics/report callers before changing the shared helper and preserve their ordered-population contracts; a backtest-linked behavior change requires backtest-gate. Do not globally change r_multiples ordering.

## Handoff

Written-spec approval and numerical panel findings are recorded in the spec. Root prepared the initial Risk brief while the delivery writer runs; a plan-briefer must verify missing frontend/test/symbol details before the plan-writer validates this index. No task bodies have been written yet. The plan-writer may split an oversized task into numbered letter suffixes and amend ledger/parts together, preserving full code/test detail and frozen public contracts. Implementation remains unstarted.

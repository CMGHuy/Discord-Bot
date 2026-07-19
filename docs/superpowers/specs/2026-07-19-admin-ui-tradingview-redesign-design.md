# Admin UI + TradingView-Style Charts — Design Spec

**Date:** 2026-07-19 · **Status:** Approved (brainstormed + user-approved in session)
**Implementation plan:** `docs/superpowers/plans/2026-07-19-admin-ui-tradingview-redesign.md`

## 1. Goal

One "terminal-grade" visual language across the three visual surfaces —
admin web pages, the mplfinance PNG charts (Discord + admin), and new
interactive charts in the admin — with the restraint of Linear, the density
of Bloomberg, and the chart chrome of TradingView. Dark-only by identity.

Success criteria:
1. Admin pages and chart PNGs draw from one shared palette (today the admin
   body is `#0d0f14` while charts are `#131722` — after this, one token set).
2. `trade_detail` (and a dashboard modal) render a genuinely interactive
   TradingView-engine chart (crosshair, zoom/pan, OHLC readout, plan levels).
3. Zero runtime CDN dependencies (Inter self-hosted, lightweight-charts vendored).
4. Every page still renders (smoke-tested), full suite green, no behavior change
   to routes/trading logic.

## 2. Scope decisions (user-approved)

- **Surfaces:** admin UI + charts, phased: PNG polish first, interactivity second.
- **Sequencing:** standalone plan on current `main`, lands **before** Cockpit v3
  Parts B/C; Part 3 inherits the theme via `base.html`/`style.css`, and its
  verbatim CSS snippets get a deviation note (one task here adds it).
- **Chart tech:** vendored TradingView `lightweight-charts` (standalone build,
  Apache-2.0, attribution kept) for admin interactivity; mplfinance stays the
  sole renderer for Discord PNGs.

## 3. Architecture

```
swingbot/admin/static/
  vendor/inter/            # self-hosted woff2 (4 weights) + inter.css
  vendor/lightweight-charts/  # standalone JS + LICENSE
  tokens.css               # NEW: the design-token single source of truth
  style.css                # rebuilt on top of tokens
  chart-init.js            # NEW: interactive-chart bootstrap (vanilla JS)
swingbot/admin/app.py      # + GET /api/ohlcv/<ticker> (auth'd, read-only)
swingbot/core/charts/chart_style.py   # palette re-derived from the same tokens
swingbot/core/charts/trade_chart.py   # last-price pill, edge labels, watermark
```

- **Tokens:** CSS custom properties (`--bg-0/1/2`, `--text-1/2/3`, `--accent`,
  `--up`, `--down`, `--warn`, spacing/radius/shadow/type scales). `chart_style.py`
  holds the same hex values with a comment cross-referencing `tokens.css` —
  Python cannot read CSS at render time, so the sync is by convention + a unit
  test asserting the shared constants match a small `THEME` dict duplicated in
  one place (`chart_style.py` is the authority the test reads).
- **Typography:** Inter self-hosted; `tabular-nums` on all numeric cells;
  scale 12/13/14/16/20.
- **Interactive charts:** `/api/ohlcv/<ticker>?bars=N&trade_id=X` returns
  `{bars: [{time, open, high, low, close, volume}], levels: {...}}` from
  `get_daily_data` with `data/backtest_cache/{TICKER}.csv` fallback; `chart-init.js`
  builds candlestick+volume series, price lines for entry/SL/TP1/TP2, markers,
  and a crosshair OHLC legend, themed from CSS vars at runtime.

## 4. Component inventory (Phase 1)

Sidebar (grouped nav, accent active-bar), cards, stat tiles (+delta chips),
tables (sticky head, hover, right-aligned tabular numerics, `.pos/.neg` P&L),
badges/pills (VALIDATED/WEAK/tier — same semantics as Discord), button
hierarchy (primary/secondary/danger/ghost), forms (settings), empty states,
skeletons, flash messages, scrollbars, `:focus-visible` rings, 120–150 ms
transitions.

## 5. Non-goals (fence)

No new pages · no SPA/framework · no route rewrites (one read-only API added)
· no Discord embed changes (Cockpit B) · no light theme · no trading-logic
changes of any kind.

## 6. Testing

- Flask test-client render smoke tests for all 7 pages (200 + marker classes).
- Endpoint tests: shape, auth required, cache fallback, bars limit.
- Chart render smoke test on a synthetic OHLCV fixture (no golden images — brittle).
- Theme-sync unit test (chart constants ↔ THEME dict).
- Full suite + py_compile green at every task (repo law).

## 7. Risks / mitigations

- **mplfinance annotation rework regressions** → keep every overlay, change
  only presentation; render-smoke test each change; PNG diffs eyeballed at the
  phase checkpoint.
- **lightweight-charts version drift** → pin exact version in the vendored
  filename + attribution file; no auto-update.
- **Cockpit C snippet conflicts** → deviation note added to that plan (task in
  this plan); its pages inherit tokens automatically via template inheritance.
- **yfinance latency on the OHLCV endpoint** → cache-first read; `bars` cap
  (default 260, max 1000); no background refresh in v1.

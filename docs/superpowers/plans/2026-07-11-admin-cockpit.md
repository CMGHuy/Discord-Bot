# Plan C — Admin Control Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Grow the Flask admin UI from a monitoring dashboard into a trading control center: a live plan-lifecycle board, per-strategy edge pages with drift alerts, calibration and lessons browsers, a TRAIN-only tuning workbench with job control and guardrails, settings v2 (diff preview, audit trail, profiles), and measurable page-speed improvements (vendored assets, snapshot-backed stats, ETag polling, chart caching).

**Architecture:** New pages follow the existing pattern — auth-guarded routes in `app.py` (split into blueprints where new), Jinja templates extending `base.html`, hand-written CSS in `style.css`, Chart.js for charts, morphdom for fragment polling. All numbers come from Plan A (`analytics` snapshot/journal/calibration); the UI renders, it never computes. Tuning jobs run existing `scripts/tune_strategy.py` as subprocesses through a `JobManager`, hard-wired to the TRAIN window.

**Tech Stack:** Flask + Jinja2, vanilla JS, Chart.js 4.4.1 + morphdom 2.7.4 (vendored locally in this plan), pytest ≥8 with Flask test client. **No new pip dependencies.**

**Prerequisites:** Plan-engine-v2 complete (PlanStore, registry); **Plan A merged**. Independent of Plan B (may run in parallel on separate branches; both touch no common files except `config.py` FIELDS — coordinate that one file at merge).

## Progress

> - **Branch:** `feature/admin-cockpit` (from `main` after Plan A merge)
> - **Completed:** —
> - **Next:** Task C1

## Global Constraints

- **TRAIN-only tuning, enforced in code:** the job layer refuses any date range overlapping 2024-01-01..2025-12-31 (the consumed VALIDATION window) and exposes no free-form date input. Validation runs stay manual + deliberate (CLI only). This is a hard guardrail with its own test (C31), not a convention.
- **Tuning results are proposals, never auto-applied.** The UI writes `data/tuning_proposals/*.json`; changing `DEFAULT_PARAMS`/`STRATEGY_GATES`/`STRATEGY_RR_OVERRIDE` remains a reviewed code change.
- **All routes auth-guarded** with the existing `require_auth` decorator — including every new `/api/*` endpoint (JSON 401, not redirect).
- **The UI renders, analytics computes:** any formula found in a template or route (beyond display formatting) is a review-rejection.
- **No CDN at runtime:** third-party JS/fonts vendored under `static/vendor/` (C1). Offline admin must work.
- **Dark theme + existing CSS variables** (`style.css` palette) for everything new; responsive at the existing 900/640/480 px breakpoints.
- **Every task ends green:** `python -m pytest tests/ -q` + `make check` before commit; conventional commits.
- **Flask test client for route tests** — no live server, no Discord, no yfinance in tests (monkeypatch `core.data` calls).

## File Structure (target state)

```
swingbot/admin/
  app.py                 MOD  registers blueprints, keeps existing routes
  api.py                 NEW  /api/* JSON blueprint (stats, plans, journal, calibration, registry, jobs)
  jobs.py                NEW  JobManager: subprocess tuning jobs + data/admin_jobs.json
  pages.py               NEW  blueprint: /plans, /strategies, /calibration, /journal, /tuning routes
  helpers.py             MOD  settings diff/profile helpers, audit log writer
  templates/
    plans.html           NEW  lifecycle board
    plan_detail.html     NEW  single-plan page (chart, timeline, breakdown)
    strategies.html      NEW  edge overview + heatmap + drift
    calibration.html     NEW  deciles + tier table
    journal.html         NEW  lessons browser
    tuning.html          NEW  workbench (params, launch, progress, results, proposals)
    settings.html        MOD  diff preview, profiles, changed-filter
    dashboard_fragment.html MOD tier/badge chips, leg rows, lifecycle strip, equity sparkline
    stats.html           MOD  snapshot-backed + calibration/drift panels + strategy heatmap
    base.html            MOD  vendored assets, nav additions
  static/
    vendor/chart.umd.min.js, vendor/morphdom-umd.min.js   NEW
    style.css            MOD  chips, heatmap grid, timeline, jobs, diff styles
tests/admin/
  conftest.py            NEW  Flask app/client fixtures (tmp data dir, auth header)
  test_api.py, test_pages.py, test_jobs.py, test_settings_v2.py,
  test_dashboard_v2.py, test_perf_headers.py
```

---

# Phase C0 — Foundations (Tasks C1–C5)

### Task C1: Vendor third-party JS

**Files:**
- Create: `swingbot/admin/static/vendor/chart.umd.min.js`, `swingbot/admin/static/vendor/morphdom-umd.min.js`
- Modify: `swingbot/admin/templates/stats.html` (:554 CDN script), `dashboard.html` (:66)

- [ ] **Step 1: Download the exact pinned versions already referenced** (Chart.js 4.4.1, morphdom 2.7.4) from the cdnjs URLs in the templates into `static/vendor/`.
- [ ] **Step 2: Swap both `<script src="https://cdnjs...">` tags for `{{ url_for('static', filename='vendor/...') }}`.** Also self-host the Inter font CSS or fall back to `system-ui` stack in `style.css` (`--font-sans` already defines fallbacks — remove the Google Fonts link in `base.html:26`).
- [ ] **Step 3: Manual check:** run `python admin_ui.py`, load Dashboard + Performance with network devtools offline — no external requests, charts render.
- [ ] **Step 4: Commit** — `perf: vendor Chart.js/morphdom, drop CDN + font dependency`

### Task C2: Flask test harness

**Files:**
- Create: `tests/admin/__init__.py`, `tests/admin/conftest.py`
- Test: `tests/admin/test_pages.py` (first smoke test)

**Interfaces:**
- Produces: fixtures `admin_app` (Flask app with `TESTING=True`, `config.DATA_DIR` monkeypatched to tmp_path with seeded empty `trades.json`/`account.json`/`plans.json`), `client` (test client), `auth` (`{"Authorization": "Basic ..."}` for admin/admin). Every route test in this plan uses these.

- [ ] **Step 1: Failing test**

```python
# tests/admin/test_pages.py
def test_index_requires_auth(client):
    assert client.get("/").status_code == 401

def test_index_renders(client, auth):
    r = client.get("/", headers=auth)
    assert r.status_code == 200 and b"Dashboard" in r.data
```

- [ ] **Step 2: Implement conftest (import `swingbot.admin.app`, patch paths before app use). Step 3: PASS. Step 4: Commit** — `test: flask test harness for admin UI`

### Task C3: Chip + component CSS

**Files:**
- Modify: `swingbot/admin/static/style.css`

**Interfaces:**
- Produces (used by every new template): `.chip` base + `.chip-tier-a` (green), `.chip-tier-b` (amber), `.chip-tier-c` (grey), `.chip-validated`, `.chip-weak`; `.lifecycle-strip` (flex counter row); `.heatmap-grid` (CSS grid with `--hm-color` cell var); `.timeline` (status-history list with left rule); `.sparkline` (inline SVG sizing); `.job-log` (mono scroll box); `.diff-add`/`.diff-del`. Colors from the existing palette variables.

- [ ] **Step 1: Add the classes (≈80 lines) mirroring existing `.confidence-badge`/`.stat-card` conventions.**
- [ ] **Step 2: Visual smoke on a scratch page or the Dashboard. Step 3: Commit** — `feat: cockpit component styles`

### Task C4: API blueprint

**Files:**
- Create: `swingbot/admin/api.py`
- Modify: `swingbot/admin/app.py` (register blueprint after route defs)
- Test: `tests/admin/test_api.py`

**Interfaces:**
- Produces: `api = Blueprint("api", __name__, url_prefix="/api")`; every view wrapped by `require_auth` returning JSON 401 `{"error": "auth"}` when unauthorized (small `require_auth_json` variant in api.py); `GET /api/health` → `{"ok": true, "versions": get_versions()}`. Registration: `app.register_blueprint(api)` in `app.py`.

- [ ] **Step 1: Failing test** — `/api/health` 401 without auth (JSON body), 200 with, contains `versions`.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: admin /api blueprint`

### Task C5: Pages blueprint + nav

**Files:**
- Create: `swingbot/admin/pages.py` (blueprint `pages`, template-rendering routes added in later tasks)
- Modify: `swingbot/admin/app.py` (`NAV_ITEMS` :80–86, register blueprint; `_render` must accept blueprint endpoints)
- Test: `tests/admin/test_pages.py`

**Interfaces:**
- Produces: nav order — Dashboard, **Plans**, Performance, **Strategies**, **Calibration**, **Journal**, **Tuning**, Watchlist, Settings, Logs. Placeholder routes return 200 with the page shell until their tasks land (`_render("Plans", "plans", "plans.html", ...)` with an empty-state message). `plans.html` etc. created as minimal `{% extends "base.html" %}` shells here.

- [ ] **Step 1: Failing test** — each new path (`/plans`, `/strategies`, `/calibration`, `/journal`, `/tuning`) returns 200 authed and its name appears in the sidebar HTML of `/`.
- [ ] **Step 2–4: Implement shells, PASS, commit** — `feat: cockpit nav + page shells`

---

# Phase C1 — Data endpoints & speed (Tasks C6–C13)

### Task C6: `/api/stats`

**Files:** Modify `api.py`; test `tests/admin/test_api.py`

**Interfaces:**
- Produces: `GET /api/stats` → the Plan A snapshot verbatim (`snapshots.load_snapshot(max_age_seconds=3600)`; on None: `refresh_snapshot()` then load — so first hit after deploy self-heals). Query `?fresh=1` forces refresh.

- [ ] **Step 1: Failing test** — seed tmp snapshot file → GET returns its `built_at`; `?fresh=1` with monkeypatched refresh → refresh called.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: /api/stats snapshot endpoint`

### Task C7: `/api/plans`

**Files:** Modify `api.py`; test `tests/admin/test_api.py`

**Interfaces:**
- Produces: `GET /api/plans?status=&tier=&badge=` → `{"plans": [plan dicts + "follow_score"], "counts": {"PENDING": n, "ACTIVE": n, "PARTIAL": n, "CLOSED": n, "CANCELLED": n}}`, ranked by `rank_plans`. Reads `PlanStore`.

- [ ] **Step 1: Failing test** — seed 3 plans in tmp plans.json → ranked order, counts correct, `?status=ACTIVE` filters.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: /api/plans`

### Task C8: `/api/journal`

**Files:** Modify `api.py`; test `tests/admin/test_api.py`

**Interfaces:**
- Produces: `GET /api/journal?strategy=&tag=&outcome=&has_note=&limit=100` → `{"entries": [...]}` via `JournalStore.entries`; `POST /api/journal/<trade_id>/note` (form/JSON `note`) → `{"ok": bool}` via `set_note`.

- [ ] **Step 1: Failing test** — seeded entries filter by tag; note POST roundtrips; unknown id → `{"ok": false}` 404.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: /api/journal + notes`

### Task C9: `/api/calibration` + `/api/registry`

**Files:** Modify `api.py`; test `tests/admin/test_api.py`

**Interfaces:**
- Produces: `GET /api/calibration` → `{"deciles": ..., "tiers": ..., "drift": ...}` (snapshot's calibration block, same self-heal as C6); `GET /api/registry` → parsed `validation_registry.json` + per-entry `live_n`/`live_wr` joined from snapshot `by.strategy`.

- [ ] **Step 1: Failing test** — registry endpoint joins live stats (fixture snapshot + registry); calibration keys present.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: /api/calibration + /api/registry`

### Task C10: ETag on the dashboard fragment

**Files:** Modify `swingbot/admin/app.py` (`dashboard_fragment` :604); test `tests/admin/test_perf_headers.py`

**Interfaces:**
- Produces: `/dashboard/fragment` computes `sha1(html)` → `ETag`; request with matching `If-None-Match` → `304` empty body. `dashboard.html`'s `refreshDashboard()` sends the stored ETag and skips morphdom on 304.

- [ ] **Step 1: Failing test** — GET fragment, GET again with returned ETag → 304.
- [ ] **Step 2–4: Implement (route + ~6 lines JS), PASS, commit** — `perf: 304 fragment polling`

### Task C11: gzip responses

**Files:** Modify `app.py` (`after_request` hook); test `tests/admin/test_perf_headers.py`

**Interfaces:**
- Produces: hand-rolled `@app.after_request` gzip for `text/html`/`application/json` bodies > 4 KB when client sends `Accept-Encoding: gzip` and response isn't already encoded/direct-passthrough (`send_file` excluded). No flask-compress dependency.

- [ ] **Step 1: Failing test** — large authed page with gzip header → `Content-Encoding: gzip`, decompresses to original; small response → not encoded.
- [ ] **Step 2–4: Implement, PASS, commit** — `perf: gzip admin responses`

### Task C12: Chart image caching

**Files:** Modify `app.py` (`trade_chart_image` :768); test `tests/admin/test_perf_headers.py`

**Interfaces:**
- Consumes: Plan B's `charts/cache.py` if merged; otherwise this task carries its own copy-free approach: closed trades regenerate deterministic charts, so respond with `Cache-Control: private, max-age=86400` + `Last-Modified`/`If-Modified-Since` 304 for closed trades; open trades `no-store`.

- [ ] **Step 1: Failing test** — closed-trade chart response has `max-age=86400`; open-trade has `no-store`.
- [ ] **Step 2–4: Implement, PASS, commit** — `perf: chart.png cache headers`

### Task C13: Server-side history pagination

**Files:** Modify `app.py` (`_render_dashboard_fragment` closed-trades section ~:534), `dashboard_fragment.html`
- Test: `tests/admin/test_dashboard_v2.py`

**Interfaces:**
- Produces: when closed trades > 500, the fragment renders only the newest 500 with a banner `"Showing latest 500 of N — use Performance page / export for full history"`; existing client-side pagination still paginates within that. Keeps the fragment payload bounded as history grows.

- [ ] **Step 1: Failing test** — seed 510 closed trades → fragment contains banner and ≤ 500 rows.
- [ ] **Step 2–4: Implement, PASS, commit** — `perf: bound dashboard history payload`

---

# Phase C2 — Plans board (Tasks C14–C19)

### Task C14: Plans page

**Files:** Modify `pages.py`; rewrite `templates/plans.html`; test `tests/admin/test_pages.py`

**Interfaces:**
- Produces: `/plans` renders the board server-side from the same helper as C7 (extract `_plan_rows(status, tier, badge) -> dict` shared by page and API): table columns `⭐/tier/badge chips · ticker · direction · status · follow score · entry/trigger · SL · TP1 · TP2 · age · quality`. Rows link to `/plans/<plan_id>` (C19).

- [ ] **Step 1: Failing test** — seeded plans render with chip classes (`chip-tier-a`, `chip-validated`) and ranked order.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: plans board page`

### Task C15: Lifecycle strip

**Files:** Modify `plans.html`, `pages.py`; test `tests/admin/test_pages.py`

**Interfaces:**
- Produces: counter strip atop the board — one `.lifecycle-strip` card per status (PENDING / ACTIVE / PARTIAL / CLOSED-today / CANCELLED-today) with counts from C7's `counts`; clicking a card applies that status filter (query param `?status=`).

- [ ] **Step 1: Failing test** — counts render; `?status=PENDING` filters rows.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: lifecycle strip`

### Task C16: Board filters

**Files:** Modify `plans.html`, `pages.py`; test `tests/admin/test_pages.py`

**Interfaces:**
- Produces: filter bar — status/tier/badge selects + ticker text box (GET form, server-side filtering via `_plan_rows`), `Clear` link. Mirrors Discord board filters (B13) so both surfaces slice identically.

- [ ] **Step 1: Failing test** — `?tier=A&badge=VALIDATED` returns only matching rows.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: plans board filters`

### Task C17: Plan actions (cancel / close)

**Files:** Modify `pages.py`; `plans.html` row buttons; test `tests/admin/test_pages.py`

**Interfaces:**
- Produces: `POST /plans/<plan_id>/cancel` — PENDING only: `record_transition(plan, CANCELLED, reason="manual")` + `PlanStore.update`, queue the existing `manual_close_notify.json` mechanism so the bot posts the transition to Discord; `POST /plans/<plan_id>/close` — ACTIVE/PARTIAL: delegates to the same manual-close path the dashboard uses for trades (`close_trade_manual` on the linked trade via `plan_id`). Confirm dialogs in the template (`onsubmit="return confirm(...)"` like existing clear buttons).

- [ ] **Step 1: Failing test** — cancel a PENDING plan → status CANCELLED persisted, notify file written; cancel an ACTIVE plan → 400.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: plan cancel/close actions`

### Task C18: Board auto-refresh

**Files:** Modify `plans.html`, `pages.py` (`/plans/fragment` route); test `tests/admin/test_pages.py`

**Interfaces:**
- Produces: `/plans/fragment` (board table + strip HTML only, ETag'd like C10); page JS polls every `DASHBOARD_REFRESH_SECONDS` and morphdom-patches — copy `dashboard.html`'s pattern verbatim, preserving filter query params in the poll URL.

- [ ] **Step 1: Failing test** — fragment 200 + ETag/304 behavior.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: live plans board`

### Task C19: Plan detail page

**Files:** Modify `pages.py`; create `templates/plan_detail.html`; test `tests/admin/test_pages.py`

**Interfaces:**
- Produces: `/plans/<plan_id>` — chart image (`/plans/<plan_id>/chart.png` route rendering via `generate_trade_chart(..., plan=plan)`; reuse trade-detail's lightbox JS), `.timeline` of `status_history`, quality breakdown table, badge stats verbatim, follow-score breakdown (Plan A `rank.follow_breakdown` if merged, else score only), linked trade (when a trades.json row carries this `plan_id`) with leg details.

- [ ] **Step 1: Failing test** — page 200 with timeline entries and breakdown rows for a seeded plan; unknown id → 404.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: plan detail page`

---

# Phase C3 — Strategies page (Tasks C20–C24)

### Task C20: Registry provenance table

**Files:** Modify `pages.py`; rewrite `templates/strategies.html`; test `tests/admin/test_pages.py`

**Interfaces:**
- Produces: `/strategies` — one row per strategy from `/api/registry`'s join (C9): badge chip, OOS N/WR/ExpR, window, run_date, gate description (from `strategy_types.STRATEGY_GATES` — render the dict readably), R:R override.

- [ ] **Step 1: Failing test** — 11 strategy rows, Fibonacci row shows its OOS WR and `bullish only` gate text.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: strategies registry table`

### Task C21: Strategy × horizon heatmap

**Files:** Modify `strategies.html`, `pages.py`; test `tests/admin/test_pages.py`

**Interfaces:**
- Produces: `.heatmap-grid` of live win-rate per (strategy, horizon) from snapshot `by.strategy` + a per-(strategy,horizon) aggregation added to the page route (compute via `aggregate.stats_by` on the filtered closed list — this is the one place the route may call analytics functions directly, still zero formulas). Cell color: linear red (≤60) → amber (75) → green (≥85), `--hm-color` inline style; cell text `WR% (n)`; n<5 cells greyed `n/a`.

- [ ] **Step 1: Failing test** — seeded trades produce a colored cell and a greyed low-N cell (assert style attr / class).
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: strategy×horizon live heatmap`

### Task C22: Drift columns + alert chips

**Files:** Modify `strategies.html`, `pages.py`; test `tests/admin/test_pages.py`

**Interfaces:**
- Produces: table gains `Live N / Live WR / Δ vs OOS` columns and a red `DECAY` chip when snapshot `calibration.drift` flags the strategy; page header shows an alert banner listing decayed strategies when any.

- [ ] **Step 1: Failing test** — fixture drift alert → chip + banner present; clean fixture → absent.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: edge-decay surfacing`

### Task C23: Rolling-WR sparklines

**Files:** Modify `pages.py` (sparkline SVG helper), `strategies.html`; test `tests/admin/test_pages.py`

**Interfaces:**
- Produces: `_sparkline_svg(points: list[float], *, width=120, height=28, ref: float | None = 80.0) -> str` (inline `<svg>` polyline, ref line dashed) in `pages.py`; per-strategy sparkline of `rolling_win_rate` over that strategy's closed trades (window 10). Empty data → em-dash.

- [ ] **Step 1: Failing test** — helper returns `<svg` containing a `polyline` with the right point count; page embeds one per strategy with data.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: strategy WR sparklines`

### Task C24: Cross-links

**Files:** Modify `strategies.html`, `plans.html`, `tuning.html` shell; test `tests/admin/test_pages.py`

**Interfaces:**
- Produces: each strategy row links to `/tuning?strategy=...` and `/journal?strategy=...`; plans-board strategy cells link to `/strategies#<slug>`; anchors (`id=` per row) added.

- [ ] **Step 1: Failing test** — hrefs present with URL-encoded strategy names.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: cockpit cross-links`

---

# Phase C4 — Calibration & Journal pages (Tasks C25–C28)

### Task C25: Calibration page

**Files:** Modify `pages.py`; rewrite `templates/calibration.html`; test `tests/admin/test_pages.py`

**Interfaces:**
- Produces: `/calibration` — Chart.js bar chart of score deciles (realized WR vs the 80 line, JSON injected via the `stats.html` `<script id="chart-data">` pattern), tier-calibration table (tier / n / live WR / expected band / ✅❌—), drift table. Explanatory copy: one paragraph on what calibration means ("does a higher score actually win more?") — the page must teach, not just chart.

- [ ] **Step 1: Failing test** — page 200, contains the chart-data JSON script tag with `deciles`, tier table renders ❌ for a failing fixture tier.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: calibration page`

### Task C26: Journal browser

**Files:** Modify `pages.py`; rewrite `templates/journal.html`; test `tests/admin/test_pages.py`

**Interfaces:**
- Produces: `/journal?strategy=&tag=&outcome=&has_note=` — filter bar + entry cards: outcome chip, ticker, `{r_realized:+.2f}R`, MFE/MAE/exit-efficiency mini-bar, tags as chips, `auto_lesson` text, note (when present), link to `/trades/<trade_id>`. Tag list for the filter select gathered from entries.

- [ ] **Step 1: Failing test** — seeded entries filter by tag; card shows the lesson text.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: journal browser`

### Task C27: Journal note editing

**Files:** Modify `journal.html` (inline note form per card → C8's POST endpoint via fetch); test `tests/admin/test_api.py` (already covers endpoint) + `tests/admin/test_pages.py` (form present)

- [ ] **Step 1: Failing test** — card contains a form/textarea wired to `/api/journal/<id>/note`.
- [ ] **Step 2–4: Implement (fetch POST + optimistic update), PASS, commit** — `feat: edit journal notes in browser`

### Task C28: Weekly digest view

**Files:** Modify `pages.py`, `journal.html` (tab), test `tests/admin/test_pages.py`

**Interfaces:**
- Produces: `/journal?view=weekly` — renders `insights.weekly_digest` messages for the trailing week as cards, plus `insights.top_lessons` list. Same content the Discord `!lessons week` posts — one source.

- [ ] **Step 1: Failing test** — weekly view contains digest headline figures from fixtures.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: weekly digest view`

---

# Phase C5 — Tuning workbench (Tasks C29–C37)

### Task C29: JobManager

**Files:**
- Create: `swingbot/admin/jobs.py`
- Test: `tests/admin/test_jobs.py`

**Interfaces:**
- Produces: `class JobManager` (module singleton `manager`): `start(kind: str, args: list[str]) -> str` (job_id; raises `RuntimeError("job already running")` if one is active — tuning is serialized), `status(job_id) -> dict` (`{id, kind, args, state: queued|running|done|failed, started_at, finished_at, returncode, log_path}`), `tail(job_id, n=100) -> str`, `all() -> list[dict]`. Runs `subprocess.Popen([sys.executable, script, *args], stdout=logfile)` in a daemon thread; state persisted to `data/admin_jobs.json` via `jsonio` (survives admin restart; a running job found on startup with a dead pid → `failed`). Log files under `logs/jobs/<job_id>.log`.

- [ ] **Step 1: Failing test** — start a job running `python -c "print('hi')"` (kind `"test"` allows a raw argv in tests), poll until `done`, tail contains `hi`; second concurrent start raises.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: admin JobManager`

### Task C30: Job API

**Files:** Modify `api.py`; test `tests/admin/test_jobs.py`

**Interfaces:**
- Produces: `POST /api/jobs/tune` (form: `strategy`, optional `params` — validated against a whitelist, C31) → `{"job_id": ...}` or 409 when busy; `GET /api/jobs/<id>` → status dict + last 50 log lines; `GET /api/jobs` → recent 20.

- [ ] **Step 1: Failing test** — POST with monkeypatched manager returns job_id; busy manager → 409.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: tuning job API`

### Task C31: TRAIN-only guardrail

**Files:** Modify `jobs.py`; test `tests/admin/test_jobs.py`

**Interfaces:**
- Produces: `build_tune_args(strategy: str, params: dict | None) -> list[str]` — the ONLY constructor of tuning argv: whitelists `strategy` against `backtest.ALL_STRATEGIES`, always appends the fixed TRAIN flags used by `scripts/tune_strategy.py`, accepts no date arguments at all. `assert_train_only(args)` raises `ValueError` on any `--from/--to/--validation` token or any date string ≥ `2024-01-01`; `JobManager.start(kind="tune", ...)` calls it unconditionally. Module constant `VALIDATION_WINDOW = ("2024-01-01", "2025-12-31")` with a docstring explaining WHY (window consumed; reuse = silent overfitting).

- [ ] **Step 1: Failing test**

```python
def test_guardrail_blocks_validation_window():
    import pytest
    from swingbot.admin.jobs import assert_train_only, build_tune_args
    with pytest.raises(ValueError):
        assert_train_only(["--from", "2024-06-01", "--to", "2024-12-31"])
    with pytest.raises(ValueError):
        assert_train_only(["--validation"])
    assert_train_only(build_tune_args("RSI", None))  # must not raise
```

- [ ] **Step 2–4: Implement, PASS, commit** — `feat: TRAIN-only tuning guardrail`

### Task C32: Tuning page — current state

**Files:** Modify `pages.py`; rewrite `templates/tuning.html`; test `tests/admin/test_pages.py`

**Interfaces:**
- Produces: `/tuning` top section "Current parameters" — per strategy: `STRATEGY_GATES` entry, `STRATEGY_RR_OVERRIDE`, `entry_filters.DEFAULT_PARAMS` subset, badge chip, and provenance line (`window`, `run_date` from registry). Read-only; a visible note: *"Values are code, changed only via reviewed commits. This page proposes; it never applies."*

- [ ] **Step 1: Failing test** — page shows RSI's R:R 0.40 and the provenance run_date.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: tuning current-state view`

### Task C33: Grid launch form

**Files:** Modify `tuning.html`, `pages.py`; test `tests/admin/test_pages.py`

**Interfaces:**
- Produces: "Run TRAIN grid" card — strategy select (ALL_STRATEGIES), optional param-subset checkboxes (from the tunable-param names `scripts/tune_strategy.py` exposes; hardcode the known list with a comment pointing at the script), submit → `POST /api/jobs/tune`; busy state renders the running job's card instead of the form. TRAIN window displayed prominently, immutable.

- [ ] **Step 1: Failing test** — form posts to the API path; with a running job fixture the form is absent and the job card present.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: grid launch form`

### Task C34: Job progress UI

**Files:** Modify `tuning.html`; test `tests/admin/test_pages.py`

**Interfaces:**
- Produces: running-job card polls `GET /api/jobs/<id>` every 3 s, streams tail into a `.job-log` box, flips to done/failed state with returncode; history list of last 5 jobs with links to their result files.

- [ ] **Step 1: Failing test** — page HTML includes the poll JS bound to the job id (source assertion).
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: job progress streaming`

### Task C35: Results comparison

**Files:** Modify `pages.py`, `tuning.html`; possibly `scripts/tune_strategy.py` (add `--json PATH` output if it doesn't already write one)
- Test: `tests/admin/test_jobs.py`

**Interfaces:**
- Produces: tuning jobs write `data/tuning_results/<job_id>.json` (`{strategy, grid: [{params, n, win_rate, expectancy_r, excl_pct, passes: bool}], best: {...}}`); `/tuning` renders a finished job's grid as a sortable table with the current in-code params highlighted and pass-gate rows (WR≥80, ExpR>0, N≥30, excl≤50%) tinted green. `_load_result(job_id) -> dict | None` in `pages.py`.

- [ ] **Step 1: Failing test** — fixture result file renders rows, gate-passing row carries the pass class.
- [ ] **Step 2–4: Implement (incl. the script's `--json` flag if missing, with its own mini-test), PASS, commit** — `feat: grid results table`

### Task C36: Export proposal

**Files:** Modify `pages.py`, `tuning.html`; test `tests/admin/test_jobs.py`

**Interfaces:**
- Produces: `POST /tuning/propose` (form: job_id, selected grid row index) → writes `data/tuning_proposals/<ts>-<strategy>.json`: `{strategy, proposed_params, train_stats, current_params, job_id, created_at, note}` — and shows the exact next steps text: *"Apply by editing `entry_filters.DEFAULT_PARAMS`, run the suite, and only then consider a validation shot — remembering the window is spent."*

- [ ] **Step 1: Failing test** — POST writes the file with all keys; proposal listed on the page afterward.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: tuning proposals`

### Task C37: Proposal browser + diff

**Files:** Modify `tuning.html`, `pages.py`; test `tests/admin/test_pages.py`

**Interfaces:**
- Produces: proposals section — each proposal card shows `current → proposed` per param with `.diff-add`/`.diff-del` styling, train stats, and a Delete button (`POST /tuning/proposals/<name>/delete`).

- [ ] **Step 1: Failing test** — fixture proposal renders the param diff pair; delete removes the file.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: proposal browser`

---

# Phase C6 — Settings v2 (Tasks C38–C41)

### Task C38: Diff preview before save

**Files:**
- Modify: `swingbot/admin/helpers.py` (`settings_diff(form, existing) -> list[dict]`), `app.py` (`POST /settings/preview`), `templates/settings.html`
- Test: `tests/admin/test_settings_v2.py`

**Interfaces:**
- Produces: `settings_diff` returns `[{key, label, old, new, sensitive}]` for changed fields only (sensitive values masked `"•••"`); `/settings/preview` returns a modal-fragment HTML table; the Save button first fetches the preview into a confirm modal (`Confirm & Save` submits the real `/settings/save`). No-changes → "Nothing changed" message, no save.

- [ ] **Step 1: Failing test** — `settings_diff` masks `DISCORD_TOKEN`, includes only changed keys; preview route renders both old and new values.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: settings diff preview`

### Task C39: Settings audit trail

**Files:** Modify `helpers.py` (`append_settings_audit(diff: list) -> None` → `data/settings_audit.jsonl`), `app.py` (`save_settings` :659 calls it), `settings.html` (collapsible "Recent changes" panel, last 20)
- Test: `tests/admin/test_settings_v2.py`

**Interfaces:**
- Produces: one JSONL line per save: `{"ts", "changes": [{key, old, new}]}` — sensitive values masked at write time (never on read). Panel renders newest first.

- [ ] **Step 1: Failing test** — save with a change appends a line with masked token; panel shows it.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: settings audit log`

### Task C40: Export / import profiles

**Files:** Modify `app.py` (`GET /settings/export`, `POST /settings/import`), `helpers.py` (`import_env_text(text) -> tuple[int, list[str]]` — applies known keys, returns (applied_count, unknown_keys)), `settings.html` (buttons)
- Test: `tests/admin/test_settings_v2.py`

**Interfaces:**
- Produces: export downloads the current `.env` **minus sensitive fields** (attachment `swingbot-settings-<date>.env`); import accepts a pasted/uploaded env text, validates each key against `FIELDS_BY_KEY`, type-checks numerics via the existing casters, previews as a C38 diff before applying. Sensitive keys in an import are applied but never exported.

- [ ] **Step 1: Failing test** — export body lacks `DISCORD_TOKEN`; import of `SCAN_INTERVAL_MINUTES=7\nBOGUS=1` → applied 1, unknown `["BOGUS"]`.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: settings profiles export/import`

### Task C41: Changed-from-default filter + per-field reset

**Files:** Modify `settings.html` (the `render_field` macro already computes a changed-dot — add a toolbar toggle "Only changed" using it; per-field ↺ reset button filling the default into the input client-side)
- Test: `tests/admin/test_settings_v2.py`

- [ ] **Step 1: Failing test** — page contains the toggle and reset buttons carry `data-default` attributes.
- [ ] **Step 2–4: Implement (JS show/hide on the existing changed marker class), PASS, commit** — `feat: changed-only settings view + resets`

---

# Phase C7 — Dashboard v2 & wrap-up (Tasks C42–C46)

### Task C42: Pedigree in dashboard tables

**Files:** Modify `app.py` (`_render_dashboard_fragment` open/closed loops :452/:534), `dashboard_fragment.html`
- Test: `tests/admin/test_dashboard_v2.py`

**Interfaces:**
- Produces: open- and closed-trade rows gain tier + badge chips (from A12's persisted fields; None → no chip) and, for two-leg v2 trades, an indented runner sub-row (leg exit price/R once closed, else `runner: live`).

- [ ] **Step 1: Failing test** — seeded v2 trade renders `chip-tier-a` and a runner sub-row.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: pedigree chips + leg rows on dashboard`

### Task C43: Lifecycle strip + equity sparkline on dashboard

**Files:** Modify `app.py` (fragment context), `dashboard_fragment.html`
- Test: `tests/admin/test_dashboard_v2.py`

**Interfaces:**
- Produces: the C15 lifecycle strip (linked to `/plans?status=`) rendered above the stat cards; a new stat card "Equity (30d)" embedding `_sparkline_svg` (import from `pages.py`) over the snapshot equity curve's last 30 points with the current balance as the headline number.

- [ ] **Step 1: Failing test** — fragment contains strip counts and an `<svg>` in the equity card.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: dashboard lifecycle strip + equity sparkline`

### Task C44: Performance page v2

**Files:** Modify `app.py` (`stats_page` :1095), `templates/stats.html`
- Test: `tests/admin/test_pages.py`

**Interfaces:**
- Produces: `stats_page` context adds the Plan A snapshot (`snapshot=load_snapshot() or refresh+load`) alongside the existing `get_chart_data()`; new panels at top: calibration deciles (reusing C25's chart config), drift table, tier StatRow table, strategy×horizon heatmap (C21 partial include — extract `_heatmap.html` Jinja partial used by both pages). Existing 18 charts untouched. Page-load work drops because KPI numbers come from the snapshot instead of recomputation where the two overlap (keep `get_chart_data` for the per-trade client-side charts).

- [ ] **Step 1: Failing test** — `/performance` contains the drift table and heatmap partial; still contains the legacy `chart-data` JSON block.
- [ ] **Step 2–4: Implement, PASS, commit** — `feat: performance page v2 panels`

### Task C45: Mobile + polish pass

**Files:** Modify `style.css`, new templates
- Test: manual

- [ ] **Step 1: Audit every new page at 900/640/480 px** (browser devtools): heatmap scrolls horizontally in its own container (`overflow-x: auto`), tables collapse like existing ones, filter bars wrap, job log doesn't overflow.
- [ ] **Step 2: Empty states:** every new page renders a helpful empty-state card (no plans / no journal / no jobs) instead of a bare table.
- [ ] **Step 3: Commit** — `style: cockpit responsive + empty states`

### Task C46: Checkpoint — full verification

**Files:** Modify plan Progress block, `README.md`, `DOCKER.md` if paths changed.

- [ ] **Step 1: `python -m pytest tests/ -q` + `make check` — green.**
- [ ] **Step 2: Live smoke:** `python admin_ui.py` → walk Dashboard, Plans (filter/cancel), Strategies (drift), Calibration, Journal (note edit), Tuning (launch a real small TRAIN grid, watch progress, export a proposal), Settings (diff preview, export/import), Performance v2. Confirm zero external network requests and fragment 304s in the access log.
- [ ] **Step 3: Docs:** README admin section — new pages, job system, guardrail statement, audit log location.
- [ ] **Step 4: Commit** — `docs: admin cockpit wrap-up`. Update Progress block. **Plan C done.**

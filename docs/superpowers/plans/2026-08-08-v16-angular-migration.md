# Angular admin UI migration — Implementation Plan (v16)

> ## ✅ COMPLETE — closed 2026-08-13
>
> The Angular SPA is built, deployed and serving production as of Release A
> (2026-08-13, `ui` 1.1.0). NG1–NG55 are done; the acceptance gate passed and
> is recorded in spec Appendix B.
>
> **NG57 (deleting the Jinja UI) is NOT part of this plan any more.** It has
> been handed to a separate plan, deliberately: it is the one irreversible
> step here, it is gated on live-session time rather than on engineering, and
> keeping it open would leave this plan permanently 98% done. Everything a
> future plan needs to execute it — the verified chart-route prerequisite, the
> triage of all 23 affected test files, and the corrected verify command — is
> written up in **spec Appendix C**.
>
> **The Jinja UI stays live and untouched until that plan runs.** Both UIs are
> mounted; `ADMIN_UI` chooses which answers `/`. Do not delete Jinja code as a
> side effect of unrelated work.
>
> **The second gate is RELEASED, 2026-08-14.** It was added on 2026-08-13 to
> hold NG57 until **`2026-08-13-v21-spa-refresh.md`** completed, because v21
> ports the compact/full density model, the SL→TP status bar and the combined
> plan cell *out of* these templates. **v21 is now complete** — SR1–SR64,
> `ui` 1.2.0.
>
> The evidence that nothing is lost by deleting the templates is
> `docs/superpowers/results/2026-08-13-jinja-feature-parity.md`: all 19
> templates audited row by row, every gap ranked, and every one either filled
> or explicitly recorded as dropped on purpose. The 33 cosmetic rows were
> filled rather than dropped (SR59–SR63); the 88 *blocks NG57* rows were
> closed by SR48–SR58. **Read that document before deleting anything** — it is
> the only place the per-template detail exists once the templates are gone.
>
> **NG57 therefore remains gated on ONE thing: the soak** (no earlier than
> 2026-08-27), plus the manual QA still outstanding on v21 — see that plan's
> SR64 Step 3, which was not walked. See spec v18 Decision 13.
>
> Unchecked boxes below are not a to-do list. Sessions committed work without
> ticking them (NG8–NG53 read as unstarted while their code is in the git log),
> so **derive status from the git history and each task's outcome note**, never
> from the checkboxes.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute in order NG1→NG57.

**Goal:** Replace the Flask/Jinja admin UI with an Angular SPA, without the bot process changing and without the existing UI breaking at any point before cutover.

**Architecture:** Five sub-projects executed in dependency order. A versioned REST API (`/api/v1/`) is added beside the existing routes; an SSE endpoint pushes thin change events sourced from a filesystem watcher; an Angular 21 app with NgRx SignalStore consumes both, built by a Docker multi-stage so no Node reaches the runtime image; six workspaces replace eleven pages; a flag-gated cutover then deletes Jinja two weeks later.

**Tech Stack:** Flask + Python 3.11 (server) · Angular 21.2 + `@ngrx/signals` 21.1 + TypeScript (client) · `lightweight-charts` 5.x · pytest · Docker multi-stage.

## Specs

Read the spec for a phase before starting it. They contain the reasoning; this plan contains only the sequence.

| # | Sub-project | Spec | Phase |
|---|---|---|---|
| 1 | REST API | `docs/superpowers/specs/2026-08-08-v11-admin-rest-api-design.md` | 1 |
| 2 | Real-time push | `docs/superpowers/specs/2026-08-08-v12-realtime-push-design.md` | 2 |
| 3 | Design system | `docs/superpowers/specs/2026-08-08-v20-admin-design-system-design.md` | ✅ done |
| 4 | Angular shell | `docs/superpowers/specs/2026-08-08-v13-angular-shell-design.md` | 3 |
| 5 | Workspaces | `docs/superpowers/specs/2026-08-08-v14-angular-workspaces-design.md` | 4 |
| 6 | Cutover | `docs/superpowers/specs/2026-08-08-v15-jinja-cutover-design.md` | 5 |

## Progress

> **Plan closed 2026-08-13.** Nothing here is waiting on an executing session.
>
> - **Branch:** `worktree-angular-migration`, **merged to `main` 2026-08-13**.
> - **Completed:** NG1–NG55. The checkboxes below are unreliable — earlier
>   sessions committed work without ticking them, so derive status from the
>   git log and the task outcome notes, not from `[ ]`.
> - **Release A shipped 2026-08-13** (NG55). `ui` 1.0.9 → 1.1.0. Deployed and
>   verified live: `scripts/smoke_spa.py` passed 16/16 on the server, including
>   every asset the built `index.html` asks for.
> - **NG56 / NG57 are out of scope for this plan.** The soak is an operational
>   matter, and the deletion belongs to a separate plan — see the banner at the
>   top and spec Appendix C for the handover.
> - **The Jinja UI stays.** Both UIs are mounted; `ADMIN_UI` picks which
>   answers `/`, defaulting to `spa`. Rollback is `ADMIN_UI=jinja` in the
>   server's `.env` plus `docker compose restart admin` — no rebuild, no
>   revert. That rollback exists precisely because Jinja has not been deleted,
>   and it stops working the day it is.

## Global Constraints

- **The Jinja UI must work at every commit** until Phase 5. It is the only UI there is. `/api/v1/` is a parallel surface; the old `/api/*` routes and all HTML routes stay untouched until cutover.
- **The bot process is never modified by this plan.** If a task appears to need a bot change, stop — that is a design error, not a task.
- **v1 lives in `swingbot/admin/api_v1/`**, its own package. Never alongside the old blueprint.
- **"Refetch, never patch."** Every event handler in the SPA reissues a query. No client-side reconciliation of server state.
- **Zero runtime CDN calls.** Fonts and charts are self-hosted. A network request to a third-party host is a defect.
- **`visible` columns carry no order.** The data table renders in `columns` order. Do not add an ordering input at any call site.
- **Colour rules (spec 3):** green/red = money only · amber = caution · blue = interactive only · everything else greyscale. Quality chips (confidence, tier) are greyscale, not green/amber/red.
- **Merge to `main` once per phase, not per task.** Work accumulates on `worktree-angular-migration` and fast-forwards to `main` at each phase boundary — Phase 1 lands after NG19, Phase 2 after NG24, and so on. Rationale: a phase is the smallest unit that leaves `main` in a coherent state, and `main` is shared with concurrent sessions. Check `git status` on the main tree before merging; other sessions leave it dirty.
- Windows dev machine: `python`, never `python3`.
- `python scripts/testrun.py full` green (`0 failed`) before each commit; `... file tests/admin` while iterating. Conventional commits, one per task, `git add <explicit paths>` — never `-A`.
- New docs follow the `-vN` naming convention in `docs/claude/working-conventions.md`.

## File Structure

```
swingbot/admin/api_v1/__init__.py        blueprint, error helpers, auth       (NG2)
swingbot/admin/api_v1/{trades,cockpit,analytics,universe,risk,system,market}.py   (NG5–NG18)
swingbot/admin/events/watcher.py         stat() loop + debounce                (NG20)
swingbot/admin/events/broker.py          fan-out, seq, connection cap          (NG21)
swingbot/admin/events/stream.py          SSE endpoint                          (NG22)
frontend/                                Angular project (outside swingbot/)   (NG25+)
frontend/src/app/{shell,api,stores,ui,workspaces}/
swingbot/admin/static/app/               build output — GITIGNORED             (NG33)
swingbot/admin/static/vendor/jetbrains-mono/                                   (NG26)
Dockerfile                               multi-stage: node build → python      (NG33)
tests/admin/test_api_v1_contract.py      the API contract gate                 (NG3)
```

## Dependency notes

- **Phase 1 gates Phase 4.** Workspaces cannot be built against endpoints that do not exist.
- **Phase 3 does not depend on Phase 1 or 2** beyond the tracer bullet (NG36). It may run in parallel with Phase 1 if two sessions are available; NG36 is the only join.
- **Phase 2 can land any time after NG11** (a workspace needs something to refetch). It is placed second because it is small and its absence shapes how stores are written.
- **Phase 5 is last and irreversible at NG57.** NG56 is not.

---

# Phase 0 — Preflight (NG1–NG3)

### Task NG1: Verify trade/plan ID uniqueness

**Files:** read `swingbot/core/plan_store.py`, `swingbot/core/data_store.py`; write `tests/admin/test_id_uniqueness.py`

**Blocks:** every Trades endpoint. Spec v11 Decision 2 — a collision found later invalidates all of them.

- [x] Trace how IDs are allocated in `plans.json` and `trades.json`
- [x] Determine whether the two ID spaces can collide
- [x] If they can: adopt `plan:<id>` / `trade:<id>` prefixing and record it in spec v11 as an amendment
- [x] Add a test asserting the chosen invariant against real fixture data
- [x] **Verify:** `python scripts/testrun.py file tests/admin/test_id_uniqueness.py`

**Outcome:** IDs **cannot** collide — plan ids are 36-char dashed uuid4, trade ids are 16-char dash-free alphanumeric; disjoint by length and by charset independently. No prefixing. Pinned by `tests/admin/test_id_uniqueness.py`.

**Second finding, larger than the one this task was looking for:** the two stores **overlap**. A filled plan stays in `plans.json` as `ACTIVE` while `log_trade()` writes a linked row into `trades.json`, so concatenating the two row sets double-counts every closed v2 position. The union is a **join**: all plans (authoritative for the five statuses), enriched by their linked trade record, plus trades where `plan_id is None` (legacy v1). Recorded as an amendment in spec v11; **NG5 rewritten accordingly**.

### Task NG2: `api_v1` package skeleton

**Files:** `swingbot/admin/api_v1/__init__.py`, register in `swingbot/admin/app.py`

**Produces:** the blueprint, error helper and auth decorator every later task uses.

- [x] Blueprint at `/api/v1`
- [x] `error(code, message, status)` returning `{"error": {"code", "message"}}`
- [x] `require_auth_json` reused from `api.py` — do not write a second auth path
- [x] `collection(items, total, page, per_page)` helper; `per_page` caps at 200
- [x] Unknown filter parameter → `400 invalid` (spec v11: never silently ignore)
- [x] ISO-8601 UTC serialisation helper for all timestamps
- [x] **Verify:** `GET /api/v1/` unknown route returns the JSON error shape, not HTML

**Two constraints discovered here that NG4+ must respect:**

1. **`api_v1/__init__.py` imports nothing from `swingbot.admin`.** Importing `require_auth_json` there deadlocked on the circular import `app.py` documents (api.py → app.py → bottom-of-app.py → api.py). **Endpoint modules** import `require_auth_json` from `swingbot.admin.api` instead — they are imported from app.py's bottom, where the ordering is already sound. `register(app)` mounts the blueprint *and* the two error handlers, because the 404 handler must be app-level (an unmatched URL never reaches a blueprint).
2. **Tests must import the module, not its names** — `from swingbot.admin import api_v1 as v1`, then `v1.ApiError`. `importlib.reload` in conftest mutates the module dict in place, so a bound `ApiError` goes stale and `pytest.raises` silently stops matching. Documented in `tests/admin/conftest.py`. Each new `api_v1.*` endpoint module must also be added to that file's `_RELOAD_MODULES`, or its routes get re-added to a blueprint that already has them.

### Task NG3: Contract test harness

**Files:** `tests/admin/test_api_v1_contract.py`

**Produces:** the gate that keeps the hand-written TS interfaces honest.

- [x] Helper asserting exact top-level key set **and value types** of a response
- [x] Helper asserting the error shape and status of a failure path
- [x] One passing case against NG2's error handler
- [x] **Verify:** `python scripts/testrun.py file tests/admin/test_api_v1_contract.py`

**Where it lives:** helpers in `tests/admin/api_v1_contract.py` (not `test_*`, so pytest does not collect it); its own self-tests in `tests/admin/test_api_v1_contract.py`, each exercising an assertion in both directions — a contract helper that cannot fail would make every endpoint test vacuous.

**`assert_shape` rejects undeclared keys as loudly as missing ones.** An endpoint returning a field nobody declared is an undocumented contract change the SPA will grow a dependency on. It also excludes `bool` from numeric types: `isinstance(True, int)` is `True`, so a naive check would let a boolean satisfy a price field — precisely the type drift spec v11 Decision 6 names as its residual risk.

---

# Phase 1 — REST API (NG4–NG19)

Every task in this phase: add endpoints, add contract-test cases, change nothing existing.

### Task NG4: Session and health

**Files:** `api_v1/session.py`

- [x] `POST /api/v1/session` (login), `DELETE` (logout), `GET` (am I authenticated)
- [x] Reuse the existing session cookie and `pw_hash` check — no new auth mechanism
- [x] `GET /api/v1/health` returning `{ok, versions}` from `helpers.get_versions()`
- [x] Contract cases incl. `401` body shape
- [x] **Verify:** `testrun.py file tests/admin`

**Correction to NG2's plan text, found by the contract assertions:** `require_auth_json` from `api.py` could **not** be reused directly. It returns `{"error": "auth"}` — `error` as a bare string — which is not v1's `{"error": {"code", "message"}}`. The *predicate* is shared (`_session_authenticated` plus the same credential comparison, imported not reimplemented); only the failure rendering differs. v1's decorator lives in `swingbot/admin/api_v1/auth.py`. The legacy decorator is left untouched because `dashboard.js` branches on its body today. Pinned by `test_v1_and_legacy_401_bodies_deliberately_differ`.

**`GET /api/v1/session` is deliberately not auth-guarded** — it *is* the question "am I logged in", so 401-ing an unauthenticated caller makes it unanswerable to the only caller that needs it. Returns `200 {"authenticated": false}`.

**v1 401s send no `WWW-Authenticate` header**, or the browser's native Basic dialog appears over the SPA.

**Endpoint modules are imported inside `register()`**, not at `api_v1/__init__.py`'s top — see NG2's constraint 1. Each also joins `_RELOAD_MODULES` in `tests/admin/conftest.py`.

### Task NG5: Trades collection — the union

**Files:** `api_v1/trades.py`

**Done.** Implemented in `swingbot/admin/api_v1/trades.py`; row contract pinned in `tests/admin/test_api_v1_trades.py::TRADE_ROW`.

**Corrections to spec v11 found while building it:**
- The function the spec names as `_query_closed_trades()` in `app.py:740` is really **`dashboard.query_closed_trades()`**, and it is *closed-only and mode-scoped* — tuned for the dashboard's Trade History table, not reusable for a five-status collection. What was reused instead: `dashboard.closed_pnl`, `closed_r`, and the `prefetch_prices` + `get_current_price` batching idiom from `build_open_trade_views`.
- **Orphaned linked trades** (a `plan_id` naming a plan that no longer exists) are included as legacy rows, not dropped. Losing real trading history is a worse failure than showing a row unjoined. The join condition is "trades no plan claimed", which covers `plan_id is None` and orphans in one branch.
- **Live prices are fetched after slicing, for the page only** — one batched round trip for at most `per_page` tickers. Prefetching before slicing would fetch every ticker in the store on every request.

**A third reload trap, worse than NG2's.** `app.py` is reloaded *before* `api_v1` in conftest, and `app.py`'s body calls `register(app)` — so Flask captured `ApiError` class **A** in its error handler while the later-reloaded parse helpers raised class **B**. Every 400 escaped its handler as a 500. Fixed by removing `api_v1.*` from `_RELOAD_MODULES` entirely and making its modules reach `app.py` through **module attribute access** (`_app.ADMIN_USERNAME`) rather than binding names at import. Any future `api_v1` module must follow that rule and must not bake an import-time path.

**Original task text:** Spec v11 Decision 2 **and its NG1 amendment** — read the amendment, not just the decision. The stores overlap; a concatenation double-counts.

- [x] Build the union as a **join, structurally**: all plans from `_plan_rows()`, each enriched by its `trades.json` row matched on `plan_id`, **plus** trades where `plan_id is None`. Not a concatenate-then-dedup.
- [x] Map legacy v1 statuses: `open → ACTIVE`, `win|loss|closed → CLOSED`. Do not synthesise `PENDING`/`PARTIAL`/`CANCELLED` for them.
- [x] `status` filter spans `PENDING|ACTIVE|PARTIAL|CLOSED|CANCELLED`; absent = all
- [x] Fields absent on one side are `null` — do not synthesise
- [x] Filters: `status`, `ticker`, `strategy`, `horizon`, `has_note`; `sort`, `page`, `per_page`
- [x] `total` = post-filter, pre-slice
- [x] Numbers stay numbers — no pre-formatted strings
- [x] **Verify:** a fixture with one filled v2 plan (present in *both* stores) yields **exactly one** row — the regression NG1 found. Plus a legacy `plan_id is None` trade, seeded explicitly.

### Task NG6: Trade detail

**Files:** `api_v1/trades.py`

- [x] `GET /api/v1/trades/{id}` resolving against both stores
- [x] `404 not_found` for unknown ids
- [x] Decide (spec v11 open question 1) whether detail extends the list row or is a distinct shape; record the answer in the spec

**Spec v11 open question 1, answered: detail EXTENDS the list row**, adding exactly one key — `detail` — holding the heavy fields (status history, legs, quality/confidence breakdowns, source lists, plan execution parameters). The SPA's store already holds list rows; a detail response with a different shape for the same seven columns would force it to reconcile two representations of one position. `test_detail_row_fields_match_the_list_exactly` pins the equivalence.

**Routing uses NG1's invariant** — a 36-char four-dash id is a plan — so detail loads *one* store, not both. `_looks_like_a_plan_id` in `trades.py` is where that lives; if `test_id_uniqueness.py` ever fails, that function breaks first.

**`detail.trade_id` is exposed deliberately:** the plan id is the public identity, but close/cancel act on the underlying trade record and the SPA would otherwise have no way to name it.

### Task NG7: Trade commands

**Files:** `api_v1/trades.py`

- [x] `POST /{id}/close` (optional manual price — preserve the `manual_close_notify.json` path), `POST /{id}/cancel`, `DELETE /{id}`
- [x] `POST /trades/clear-open`, `POST /trades/clear-history`
- [x] Reuse the existing handlers' logic; do not reimplement close semantics
- [x] **Verify:** behavioural tests rewritten from the Jinja equivalents (see NG19)

**`DELETE` refuses plan ids (422), and that is a parity decision, not an omission.** The Jinja UI has no plan-delete route — only `/trades/<id>/delete`. A plan is a lifecycle record whose `CANCELLED`/`CLOSED` states exist to record how it ended; erasing one destroys that history, and deleting only its linked trade row would leave a position with no execution behind it. Supporting it needs a `PlanStore.delete()` in core, which this plan's Global Constraints rule out. **Open question for sub-project 5:** should the Trades workspace offer plan deletion at all? If yes, it needs its own decision and a core change.

**No manual exit price.** The task text mentions one, but `TradeLog.close_trade_manual()` takes only a reason — the Jinja UI has never accepted an exit price on a manual close, and adding one would change realised-P&L semantics. Parity kept; flag for sub-project 5 if the UI wants it.

**Pre-existing bug left alone (out of scope, worth knowing):** `_queue_manual_close_notify` writes plan transitions with uppercase statuses, but `scanning/embeds.notify_closed_trades()` only recognises lowercase `win|loss|closed` — so plan-level entries are silently skipped by the consumer. Documented in `pages.py` as a known gap from an earlier task. v1 reproduces the existing write behaviour rather than fixing it; **sub-project 6's acceptance walk should decide whether to fix it.**

### Task NG8: Trade note

**Files:** `api_v1/trades.py`

- [ ] `PUT /api/v1/trades/{id}/note` via `JournalStore().set_note`
- [ ] `404` when the trade is unknown, matching today's behaviour

### Task NG9: CSV export

**Files:** `api_v1/trades.py`

- [ ] `GET /api/v1/trades/export.csv` — stays CSV, same columns and ordering as today
- [ ] **Verify:** byte-compare against the current `/trades/export.csv` for the same data

### Task NG10: Cockpit

**Files:** `api_v1/cockpit.py`

- [ ] Exactly the nine metrics of spec 3 (3 primary + 6 chips) + 30d equity series
- [ ] Source from `dashboard.py`'s existing view-model builders — compute nothing new
- [ ] The six relocated metrics are **not** here
- [ ] "Risk used" = open portfolio heat as % of `PORTFOLIO_HEAT_CAP_PCT`

### Task NG11: Analytics — snapshot, performance, strategies, calibration, registry

**Files:** `api_v1/analytics.py`

- [ ] `/analytics/snapshot` (was `/api/stats`, incl. `?fresh=1` self-heal), `/performance`, `/strategies`, `/calibration`, `/registry`
- [ ] `/performance` carries the six metrics relocated from the Cockpit header
- [ ] Reuse `load_snapshot` / `refresh_snapshot` and `_registry_rows()`

### Task NG12: Tuning proposals and jobs

**Files:** `api_v1/analytics.py`, `api_v1/jobs.py`

- [ ] `GET/POST /analytics/tuning/proposals`, `DELETE /analytics/tuning/proposals/{f}`
- [ ] `GET /jobs`, `GET /jobs/{id}` (with `log_tail`), `POST /jobs/tune`
- [ ] `409 conflict` when a job is already running — preserve today's behaviour

### Task NG13: Universe

**Files:** `api_v1/universe.py`

- [ ] `GET /universe/tickers`; `POST` taking **an array** (absorbs single + bulk add)
- [ ] `DELETE /universe/tickers/{symbol}`; `GET /universe/suggest?q=`
- [ ] Partial-success reporting for bulk add — do not fail the batch on one bad symbol

### Task NG14: Risk

**Files:** `api_v1/risk.py`

- [ ] `GET /risk` — exposure, heat vs cap, killswitch state
- [ ] `POST /risk/killswitch`

### Task NG15: System settings

**Files:** `api_v1/system.py`

**The highest-risk endpoint in this phase** — a bad write takes the bot down.

- [ ] `GET /system/settings` returns **schema and values together**, from `config.py`'s `Field` entries. No hardcoded field list anywhere.
- [ ] `POST /system/settings/preview` → diff; `PUT /system/settings` → save + audit entry
- [ ] `GET /system/settings/export` — omits sensitive fields entirely; `POST .../import` — applies recognised keys, skips unknown
- [ ] Sensitive values masked `•••` in responses, diffs and the audit log
- [ ] **Verify:** round trip — export, edit, import, SIGHUP, bot reads the change

### Task NG16: System logs, scan, bot restart

**Files:** `api_v1/system.py`

- [ ] `GET /system/logs`, `GET /system/logs/raw` (text/plain), `DELETE /system/logs`
- [ ] `GET /system/scan` (the `/scan/status` payload), `POST /system/scan/{trigger,stop,pause,resume}`
- [ ] Flag-file names must match exactly what the bot reads — a wrong name is invisible in the UI
- [ ] `POST /system/bot/restart` → `503 unavailable` when the Docker socket is absent

### Task NG17: Market OHLCV

**Files:** `api_v1/market.py`

- [ ] `GET /market/ohlcv/{ticker}?bars=&trade_id=` — 260 default, 1000 cap, CSV-cache fallback, levels when `trade_id` given

### Task NG18: Route coverage audit

**Files:** `docs/superpowers/specs/2026-08-08-v11-admin-rest-api-design.md`

- [ ] `grep -rn "\.route(" swingbot/admin/*.py`; classify every route as replaced / dropped / **unmapped**
- [ ] Fix any unmapped route now, or record the deliberate drop with a reason
- [ ] Update the spec's mapping table if reality diverged

### Task NG19: Test triage, first pass

**Files:** `tests/admin/*`

Spec v15 Decision 4 — do this now, not at cutover.

- [ ] Classify each `tests/admin/` file: HTML-structure (delete at cutover) / behavioural (rewrite against v1 **now**) / builder-level (keep untouched)
- [ ] Rewrite the behavioural ones against v1; leave the Jinja originals in place until Phase 5
- [ ] Record the classification in the file headers so Phase 5 does not re-derive it
- [ ] **Verify:** `python scripts/testrun.py full`

---

# Phase 2 — Real-time push (NG20–NG24)

### Task NG20: File watcher

**Files:** `swingbot/admin/events/watcher.py`

- [ ] `stat()` loop at **500ms**, not configurable; compares `(exists, mtime, size)` — never parses
- [ ] Path→event-type map per spec v12's taxonomy table
- [ ] 250ms **trailing** debounce per event type
- [ ] Daemon thread; survives per-path exceptions; logs at most once per path per minute
- [ ] **Verify:** unit test driving it with `os.replace` writes and asserting coalescing

### Task NG21: Event broker

**Files:** `swingbot/admin/events/broker.py`

- [ ] One watcher for the process, started lazily; fan-out to per-connection queues
- [ ] Process-wide monotonic `seq`
- [ ] Cap of **8** concurrent connections → `503 unavailable`
- [ ] **Verify:** test asserts one watcher regardless of connection count, and the cap

### Task NG22: SSE endpoint

**Files:** `swingbot/admin/events/stream.py`

- [ ] `GET /api/v1/events`, auth-guarded — `401` JSON **before** the stream opens
- [ ] `event:` name, `id:` = seq, `data:` = `{seq, at}` — thin, never the object
- [ ] `ping` every 20s
- [ ] `resync` on connect; `Last-Event-ID` accepted and logged but not replayed
- [ ] **Verify:** manual `curl -N` shows events on a real file write

### Task NG23: Confirm atomic writes cover every watched path

**Files:** audit only; note in `docs/claude/known-traps.md`

Spec v12 Decision 2 — load-bearing, so check rather than assume.

- [ ] Confirm each watched `.json` path is written through `jsonio` / `plan_store` / `data_store` / `data_refresh` (all `os.replace`)
- [ ] Confirm `.jsonl` and `.flag` paths are treated as non-parsed, per spec
- [ ] Record any path that is **not** atomic as a trap

### Task NG24: Watcher cost measurement

- [ ] Measure admin idle CPU before and after the watcher, per spec v12's risk
- [ ] Record the numbers in `docs/claude/testing-cost.md`
- [ ] If the cost is material, raise the interval — do not add a config knob

---

# Phase 3 — Angular shell (NG25–NG36)

### Task NG25: Scaffold `frontend/`

**Files:** `frontend/**`, root `.gitignore`

- [ ] **Re-check `npm view @ngrx/signals peerDependencies` first.** If `@ngrx/signals@22` is stable, take Angular 22 for both and amend spec v13.
- [ ] Otherwise pin `@angular/core@~21.2`, `@angular/cli@~21.2`, `@ngrx/signals@~21.1`
- [ ] `ng new` standalone, zoneless (`provideZonelessChangeDetection()`), no SSR, no Zone.js
- [ ] Gitignore `swingbot/admin/static/app/` and `frontend/node_modules/`
- [ ] `frontend/` sits **outside** `swingbot/` so pytest and `py_compile` never see it
- [ ] **Verify:** `npm run build` succeeds; `python scripts/testrun.py fast` unaffected

### Task NG26: Design tokens and fonts

**Files:** `frontend/src/styles/`, `swingbot/admin/static/vendor/jetbrains-mono/`

- [ ] Vendor JetBrains Mono alongside the existing Inter — self-hosted, no CDN
- [ ] Import spec 3's tokens; **dark only**, no light theme
- [ ] Type scale 9/10/11/12/14/18/23 · spacing 4/6/8/10/14/20/28 · radii 4px/3px · 120ms ease-out
- [ ] **Do not change `static/tokens.css` yet** — that is NG38, and it changes the bot's Discord chart colours

### Task NG27: `ApiClient` and interceptors

**Files:** `frontend/src/app/api/`

- [ ] Hand-written TS interfaces mirroring `test_api_v1_contract.py`
- [ ] `authInterceptor` (`withCredentials`, `401` → login, **no retry**)
- [ ] `errorInterceptor` → typed `ApiError`; non-JSON failures become `unavailable`
- [ ] `loadingInterceptor` counting in-flight requests
- [ ] Components never touch `HttpClient` — stores call `ApiClient`

### Task NG28: `SessionStore` and login

**Files:** `frontend/src/app/stores/session.store.ts`, `shell/login/`

- [ ] `GET /api/v1/session` at boot **before** the shell renders — no dashboard flash
- [ ] Login view rendered *instead of* the shell, so workspace code never loads unauthenticated
- [ ] Logout → `DELETE` then full page reload
- [ ] A `401` from a `pw_hash` change is a normal logout, not an error state

### Task NG29: Shell layout

**Files:** `frontend/src/app/shell/`

- [ ] Sidebar with **six** entries · workspace header · bot/connection status · toast host
- [ ] Killswitch-engaged state visible from the shell in every workspace
- [ ] Scan and bot status live here only — never duplicated into Cockpit

### Task NG30: Routing and guard

**Files:** `frontend/src/app/app.routes.ts`

- [ ] Six lazy `loadComponent` routes + `/trades/:id` + `/universe/:symbol`; `/` → `/cockpit`
- [ ] `authGuard` as a `CanMatchFn`
- [ ] `withComponentInputBinding()`
- [ ] Placeholder components — **no workspace content in this phase**

### Task NG31: `EventStream` and `ConnectionStore`

**Files:** `frontend/src/app/stores/connection.store.ts`, `api/event-stream.ts`

- [ ] One `EventSource` for the app; parsed event exposed as a signal
- [ ] Three reconnects in a minute → degrade to 5s polling, flag it on the store
- [ ] Stores subscribe by event type; the service knows nothing about stores
- [ ] **Reaction is always refetch, never patch**

### Task NG32: `PreferencesStore`

**Files:** `frontend/src/app/stores/preferences.store.ts`

- [ ] Server-side persistence via a System setting — **not `localStorage`**
- [ ] Read once at boot, debounced writes
- [ ] Holds column-picker visibility per table id

### Task NG33: Docker multi-stage and Flask serving

**Files:** `Dockerfile`, `swingbot/admin/app.py`

- [ ] `node:22-alpine` build stage; `COPY frontend/package*.json` **before** the source, mirroring the existing `requirements.txt` layering
- [ ] `COPY --from=frontend` into `static/app`; **no Node in the runtime image**
- [ ] Flask serves `index.html` for the six workspace prefixes — an **allow-list**, not a catch-all
- [ ] Hashed assets long-cached; `index.html` `no-cache`
- [ ] **Verify:** `docker compose up --build`; confirm image has no `node` binary

### Task NG34: Dev proxy

**Files:** `frontend/proxy.conf.json`

- [ ] `ng serve` on 4200 proxying `/api` → `localhost:1234`
- [ ] Never added to `docker-compose.yml`

### Task NG35: `CockpitStore`

**Files:** `frontend/src/app/stores/cockpit.store.ts`

- [ ] `withState` / `withComputed` / `withMethods` — the shape every other store copies
- [ ] Refetch on `account` and `trades`

### Task NG36: Tracer bullet

**Files:** `frontend/src/app/workspaces/cockpit/`

**The join between Phase 1 and Phase 3.** Everything in Phase 4 repeats this shape.

- [ ] Three primary `MetricCard`s fed by `/api/v1/cockpit` through `ApiClient` → `CockpitStore`
- [ ] Refetches on an `account` event
- [ ] **Verify:** blocking `/api/v1/events` flips the connection indicator to degraded and the cards still update by polling

---

# Phase 4 — Workspaces (NG37–NG52)

### Task NG37: `DataTableComponent`

**Files:** `frontend/src/app/ui/data-table/`

**Nothing else in this phase starts until this is settled.** Spec v14 Decision 1.

- [ ] Generic over row type; the exact input/output contract in spec v14
- [ ] Server-side sort/page — the table never slices its own rows
- [ ] `visible` is keys only; **render order comes from `columns`** — no ordering input exists
- [ ] Row expansion is a caller `TemplateRef`
- [ ] `total` is post-filter/pre-slice; document it at the input
- [ ] No data access of any kind
- [ ] **Verify:** review the contract on paper against all four intended call sites before moving on

### Task NG38: `tokens.css` palette swap

**Files:** `swingbot/admin/static/tokens.css`, `swingbot/admin/chart_style.py`

**This changes the colours of charts the bot posts to Discord.** Spec v15 — land it deliberately, here, not as a side effect at cutover.

- [ ] Apply spec 3's palette to `tokens.css`
- [ ] Update `chart_style.THEME` to match; **the sync test must stay green**
- [ ] Look at a generated PNG before committing
- [ ] **Verify:** `python scripts/testrun.py file tests/test_chart_theme.py`

### Task NG39: Column picker, pagination, empty state

**Files:** `frontend/src/app/ui/`

- [ ] Default set is a **distinct input** from the current set; "Reset to default" always present
- [ ] Visibility only — no ordering affordance
- [ ] Persists through `PreferencesStore`, keyed by table id

### Task NG40: Display components

**Files:** `frontend/src/app/ui/`

- [ ] `MetricCard`, `MetricChip`, `Sparkline`, `StatusIndicator` (dot + SL→TP bar), `Chip`, `ChartContainer` shell
- [ ] **`Chip` renders quality on the greyscale ramp** — `Lv5/A` `--text`, `Lv3/B` `--text-secondary`, `Lv1/C` `--warn`. Never green/amber/red.

### Task NG41: Input and layout components

**Files:** `frontend/src/app/ui/`

- [ ] `Button` (primary/secondary/danger/ghost/icon), `Select`, `TextInput`, `Checkbox`, `FilterBar`, `ConfirmDialog`, `Panel`, `TabBar`, `SplitView`, `Drawer`
- [ ] Nothing outside spec 3's inventory. A new component means amending that spec.

### Task NG42: Trades list

**Files:** `frontend/src/app/workspaces/trades/`, `stores/trades.store.ts`

- [ ] Seven default columns: `#` · Status · Ticker · Now · P&L% · Held · actions
- [ ] Eleven expansion fields in four groups (plan levels / setup / sizing / opened)
- [ ] **Query parameters are the source of truth** for filters, sort, page
- [ ] Status is a filter chip row, **not** tabs
- [ ] Refetch on `trades` reissues the current query

### Task NG43: Trade detail — shell and Plan tab

- [ ] `TabBar` over Plan · Live · Chart · Notes · Strategy
- [ ] Plan tab: entry, stop, TP1/TP2, R:R, sizing

### Task NG44: Live tab and trade actions

- [ ] Price, unrealised P&L, `StatusIndicator` SL→TP progress; refetch on `trades`
- [ ] Close / cancel / delete via `ConfirmDialog` that **names what is destroyed**

### Task NG45: `ChartContainer` and Chart tab

- [ ] `lightweight-charts` **5.x** — read the v4→v5 migration notes first; v4 examples will mislead
- [ ] Theme from tokens, never hardcoded colours; price lines from `?trade_id=`
- [ ] Resize handling, disposal on destroy, `OnPush`-safe imperative state

### Task NG46: Notes and Strategy tabs

- [ ] Notes: `PUT .../note`, debounced autosave, visible saved/unsaved state, refetch on `journal`
- [ ] Strategy: read-only window into `/analytics/strategies` filtered to this trade's strategy

### Task NG47: Cockpit, complete

- [ ] Three cards + six chips per spec 3, including the equity `Sparkline`
- [ ] Open-positions table = **`DataTableComponent`**, filtered and capped, linking to `/trades`
- [ ] No card-flash animation

### Task NG48: Analytics

- [ ] `TabBar`: Performance · Strategies · Calibration · Tuning (**tabs, not sub-nav** — spec v14 Decision 6)
- [ ] Performance shows the six metrics relocated from the Cockpit — verify they are actually present
- [ ] Tuning job progress via the `jobs` event, replacing polling

### Task NG49: Risk

- [ ] Exposure table, heat vs `PORTFOLIO_HEAT_CAP_PCT`, killswitch (`danger` + `ConfirmDialog`)
- [ ] Engaged state also surfaces in the shell

### Task NG50: System

- [ ] Tabs: Settings · Logs · Scan
- [ ] **Settings form renders from the schema** — no hardcoded field list. Preview → diff → save. Masking preserved.
- [ ] `settings` event while editing → warn, do not silently reload the form
- [ ] Bot restart degrades honestly on `503`

### Task NG51: Universe

- [ ] Ticker list, add (single + bulk through one endpoint), remove, suggest
- [ ] Per-ticker detail reuses `DataTableComponent` + `ChartContainer` — build nothing new

### Task NG52: Parity mapping and 1280px check

**Files:** `docs/superpowers/specs/2026-08-08-v15-jinja-cutover-design.md`

- [ ] Table: every Jinja page → its Angular successor, or a named deliberate drop
- [ ] Verify the Trades expansion content at **1280px** — spec 3 flags mono digits as wide
- [ ] Colour-rule review: nothing green/red but money, nothing blue but interactive
- [ ] Confirm `DataTableComponent` has exactly four call sites and there is no second table

---

# Phase 5 — Cutover (NG53–NG57)

### Task NG53: `ADMIN_UI` flag

**Files:** `swingbot/config.py`, `swingbot/admin/app.py`, `.env.example`

- [ ] `ADMIN_UI=spa|jinja`, default `spa`, as a `config.py` `Field`
- [ ] `spa` serves the SPA at `/`; **all Jinja routes stay mounted and reachable**
- [ ] **Verify:** flipping the value and restarting swaps the UI with no rebuild

### Task NG54: Acceptance gate

**Files:** record results in the spec

Spec v15 Decision 2. Do not ship Release A until every item passes.

- [x] Re-derive route coverage — nothing unmapped. Done from the live `app.url_map`, not the grep, which cannot see `spa.py`'s `add_url_rule` routes; one route (`GET /dashboard`, NG53) had appeared since the NG52 audit. Spec Appendix B1.
- [x] Walk every Jinja page against the SPA — walked in a browser on synthetic fixtures. Found the SPA did not load at all (`<base href="/">` vs the `/app/` mount; fixed + regression test) and two open defects: five of six status chips return nothing, and the Export CSV link carries a query the endpoint ignores. Settings round trip, bot restart, destructive actions, all four scan controls' flag files and the CSV byte-compare all pass. Manual-price close does not exist in this codebase. Spec Appendix B2.
- [x] Degraded mode: block `/api/v1/events`, confirm every workspace stays correct — all six correct; indicator escalates LIVE → CONNECTING → POLLING in ~7.5s. Spec Appendix B3.
- [x] A5's browser half at 1280px (owed by NG52, closed here) — fonts load and A5's digit estimate held; the Trades table at all 24 columns scrolled the whole document (1877px at a 1280px viewport) instead of itself. Fixed with a scroller in `DataTable`. Spec Appendix B6.
- [x] `python scripts/testrun.py full` → `0 failed` — 1537 passed, 136 skipped, 1 xfailed. Frontend too (not named in the gate, run anyway): 294 passed, and 7 pre-existing unhandled rejections fixed. Spec Appendix B4.

### Task NG55: Release A

**NG54's gate passes — unblocked.** Its two defects (the status chips and the
Export CSV query) are fixed; see spec Appendix B2 and B5.

Two things to do rather than assume, both from what NG54 found:

- **Re-run the route derivation from the live `url_map`** (spec B1's command,
  not the grep) immediately before shipping. One route appeared in the five
  days between the NG52 audit and the gate.
- **Rebuild and reinstall the bundle, then load one page in a browser.**
  `static/app/` is gitignored, so what the suite validates is never the
  artifact that ships — which is exactly how NG54's blocker survived 1544
  passing tests.

**Files:** `VERSION.json`

- [x] `ui` `1.0.9` → `1.1.0` (minor — a different UI is not a patch)
- [x] Deploy; **write down the date**. Release B is ≥ 2 weeks of live sessions later. — **2026-08-13**, by merging to `main`, which triggers `deploy.yml`.
- [x] Update the Progress block with that date — soak ends **2026-08-27** at the earliest.

### Task NG56: Wait, and watch — MOVED OUT OF THIS PLAN

**Not a code task**, and not one that can be finished early. The two weeks are
the mitigation, and they will feel unnecessary by day three. Started
2026-08-13 with Release A.

Everything NG57 asks for that is *not* the irreversible deletion has been done
in advance and is recorded in spec Appendix C: the chart-route prerequisite is
verified, the test triage is inventoried across all 23 affected files, and the
verify command is corrected. Release B should be mechanical when the date
arrives.

- [ ] Two weeks of live trading sessions on `ADMIN_UI=spa`
- [ ] Record anything that required a flip back to `jinja`
- [ ] Do not proceed early. Slow-horizon behaviour (TP2, weekly rollovers, a tuning cycle) does not occur in a few days.

### Task NG57: Release B — delete Jinja — MOVED OUT OF THIS PLAN

**Do not execute this from here.** It is owned by a separate plan now, for
three reasons that all point the same way: it is the only irreversible step in
this document, it is gated on live-session time rather than on any engineering
being finished, and leaving it open would keep a plan that is otherwise
complete permanently at 98%.

The checklist below is kept verbatim as the handover, and spec **Appendix C**
holds the work already done for it: the chart-route prerequisite verified, all
23 affected test files triaged, and the verify command corrected (the grep this
task names is blind to `spa.py`'s `add_url_rule` routes and would pass on a
broken build).

One correction the future plan needs, found while attempting it: **deleting
`pages.py` outright breaks the SPA.** `api_v1` imports eight helpers from it —
`_registry_rows`, `_strategy_horizon_heatmap`, `_rolling_win_rate_series`,
`_load_result`, `_list_proposals`, `_JOB_ID_RE`, `_PROPOSAL_FILENAME_RE`,
`TUNING_PROPOSALS_DIR_NAME` — none of which have anything to do with Jinja;
they merely live beside the routes. They have to move somewhere neutral before
the module can go. The wording below ("the HTML routes and the `pages`
blueprint") reads as though the file is disposable, and it is not.

**Irreversible.** Everything before this point is not.

- [ ] Delete: 20 templates · the HTML routes and the `pages` blueprint · `api.py` and the 10 legacy `/api/*` routes · `dashboard.js`, `chart-init.js`, `style.css` · vendored `lightweight-charts` 4.2.3 · the `ADMIN_UI` flag
- [ ] Delete `/trades/<id>/chart.png` and `/plans/<id>/chart.png` — **prerequisite VERIFIED 2026-08-13** (spec C1): the only admin importer of `generate_trade_chart` is `pages.py` itself, every bot caller imports `core/charts/*` directly, and no bot path touches the admin HTTP layer. Safe to delete.
- [ ] **Keep:** `tokens.css`, `chart_style.THEME` and their sync test (the bot's Discord charts need them); vendored Inter and JetBrains Mono
- [ ] Apply NG19's test triage: delete HTML-structure tests, keep builder-level ones untouched — **inventory of all 23 affected files is in spec C2**, with five marked *check* because they mix Jinja rendering with logic that has no other coverage
- [ ] Record the **new test baseline** in `CLAUDE.md` in this same commit — an unexplained drop is indistinguishable from lost coverage
- [ ] Update `README.md` (Admin UI section), `CLAUDE.md`, `docs/claude/architecture.md`, `DOCKER.md`, `DEPLOY_HETZNER.md`, `docs/claude/known-traps.md`
- [ ] `ui` patch bump
- [ ] **Verify:** use the live `app.url_map` dump in spec C3, **not** the grep this line used to name — the grep cannot see `spa.py`'s `add_url_rule` routes and would pass on a broken build. Must show only `/api/v1/*`, the SPA routes and Flask's `static`; `python scripts/testrun.py full` green

---

## Adding nothing

Phase 5 adds no features. The urge to fix "one small thing" while deleting is how a low-risk cutover becomes a high-risk one.

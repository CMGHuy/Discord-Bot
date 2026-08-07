# Trade History: mode-scoping + server-side paging — Implementation Plan (v9)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute in order H1→H8.

**Goal:** Make the dashboard's Trade History table respect the top mode filter (Today + Open / Today only / All days), and fetch one page at a time from the server instead of shipping up to 500 pre-rendered rows.

**Architecture:** One server-side query function owns scoping, filtering, sorting and slicing; a new JSON endpoint exposes it; the row markup moves to a shared partial so the initial server render and the AJAX page fetches produce identical HTML. The six `ct-*` filters move from DOM-hiding to query parameters — mandatory, not optional (see Global Constraints).

**Tech Stack:** Flask + Jinja2, vanilla JS, pytest.

## Progress

> Updated by the executing session after each task. Resume from the first unchecked task.
>
> - **Branch:** `worktree-trade-history-filter` (worktree at `.claude/worktrees/trade-history-filter`)
> - **Completed:** none
> - **Next:** H1

## Global Constraints

- **The six filters MUST move server-side together with paging.** They are currently client-side DOM-hiding (`dashboard_fragment.html` ~1078-1095). Paging server-side while filtering client-side means a filter only applies to the 25 rows currently on screen — strictly worse than today. Do not ship H2 without H4.
- **Filter dropdown *options* stay built from the FULL history**, never from the current page. `closed_trade_filter_options` already does this deliberately (`app.py` ~509) after a past bug where values only present in older trades could not be selected. Do not regress it.
- **"Today" for this table means `closed_at` is today (Europe/Berlin)**, via the existing `_is_today_berlin`. Trade History shows only `win`/`loss`/`closed`, so `opened_at` is not consulted here.
- **`today` and `active` modes behave identically for this table.** Open trades never appear in it, and that is the only thing distinguishing those two modes. Do not invent a difference.
- This deliberately reverses the "Deliberately NOT scoped to the dashboard mode" decision at `app.py` ~476. Update that comment; do not leave it contradicting the code.
- Windows dev machine: `python`, never `python3`.
- Verify with `python scripts/testrun.py file tests/admin` (fast) and `... full` before the final commit. Green means `0 failed`.
- Conventional commits, one per task. `git add <explicit paths>`, never `git add -A`.

## File Structure

```
swingbot/admin/app.py                                  _query_closed_trades() + /api/trade-history (H1, H2)
swingbot/admin/templates/_trade_history_rows.html      NEW  shared row partial (H3)
swingbot/admin/templates/dashboard_fragment.html       rows -> partial; ct-* JS fetches (H3, H4, H5)
tests/admin/test_trade_history_paging.py               NEW  (H6)
docs/claude/known-traps.md                             note the filter/paging coupling (H8)
```

---

# Phase 0 — Server-side query (H1–H2)

### Task H1: Extract `_query_closed_trades()`

**Files:** Modify `swingbot/admin/app.py`

**Interfaces — Produces:** the single query path H2 and H5 both call.

- [ ] **Step 1: Write the function**

```python
def _query_closed_trades(all_raw, *, mode="all", filters=None, page=1, per_page=25):
    """Scope -> filter -> sort -> slice, in that order.

    Returns (rows, total) where total is the count AFTER scoping+filtering but
    BEFORE slicing, so the pager can compute page count.
    """
```

Scope: `mode in ("today", "active")` keeps only trades whose `closed_at` is today (Europe/Berlin, via `_is_today_berlin`); `"all"` keeps everything. Filters: `outcome`, `ticker`, `strategy` (via `_primary_strategy_label`), `horizon` (`horizon_key`), `dir` (`direction`), `conf` (`confidence_level`) — each absent/empty value means "no filter". Sort: `closed_at` descending, matching today's behaviour. Slice: `[(page-1)*per_page : page*per_page]`; `per_page=0` means All.

- [ ] **Step 2: Unit-test it directly** (no HTTP) — scoping per mode, each filter independently, filters combined, sort order, slicing, out-of-range page returns empty with correct `total`, and `per_page=0`.

- [ ] **Step 3:** `python scripts/testrun.py file tests/admin`. Commit.

### Task H2: `/api/trade-history` endpoint

**Files:** Modify `swingbot/admin/app.py`

- [ ] **Step 1:** Add an authed GET route accepting `mode`, `page`, `per_page`, and the six filter params. Return JSON:

```json
{"rows_html": "<tr>...", "total": 412, "page": 3, "pages": 17, "shown": 25}
```

`rows_html` is the H3 partial rendered with the same context keys the table already uses (`cur_map`, sizing, etc.) so rows are byte-identical to the initial render.

- [ ] **Step 2:** Reuse the existing admin auth decorator — do not invent a new one; this exposes trade data.
- [ ] **Step 3:** Clamp `per_page` to the allowed set (10/25/50/All) and `page` to `>= 1`; never trust the client.
- [ ] **Step 4:** Test: auth required, each mode, pagination maths, bad params don't 500. Commit.

---

# Phase 1 — Template and JS (H3–H5)

### Task H3: Extract the row partial

**Files:** Create `swingbot/admin/templates/_trade_history_rows.html`; modify `dashboard_fragment.html`

- [ ] **Step 1:** Move the `{% for t in closed_trades %}` body (`dashboard_fragment.html` ~809-890), including the `.ct-leg-row` scaled-out second row, into the partial. Include it from the fragment so the initial render is unchanged.
- [ ] **Step 2:** Verify the rendered dashboard HTML is identical to before (diff the table markup). Commit.

### Task H4: Move the six filters + pager to the server

**Files:** Modify `dashboard_fragment.html`

- [ ] **Step 1:** Replace the DOM-hiding filter logic and client pager with a single `loadTradeHistory()` that fetches `/api/trade-history` with the current mode + filters + page, replaces `tbody`, and updates `#ct-page-info` / `#ct-info` / prev+next disabled state.
- [ ] **Step 2:** Debounce filter changes (~150ms) so rapid dropdown changes don't stack requests, and ignore out-of-order responses (track a request sequence number).
- [ ] **Step 3:** Any filter change resets to page 1. Changing the dashboard mode also resets to page 1.
- [ ] **Step 4:** Keep the density toggle purely client-side — it is presentation only and must not trigger a fetch.
- [ ] **Step 5:** On fetch failure, leave the existing rows and show an inline error rather than blanking the table. Commit.

### Task H5: Wire the initial render through the same path

**Files:** Modify `swingbot/admin/app.py`, `dashboard_fragment.html`

- [ ] **Step 1:** Have `_render_dashboard_fragment()` call `_query_closed_trades()` for page 1 so first paint and later pages cannot diverge.
- [ ] **Step 2:** Remove `CLOSED_TRADES_FRAGMENT_LIMIT` and the `closed_trades_truncated` banner — with real paging, the 500-row cap and its "Showing latest N of M" warning are obsolete. Confirm no other template references them.
- [ ] **Step 3:** Update the stale `app.py` ~476 comment. Commit.

---

# Phase 2 — Verification and docs (H6–H8)

### Task H6: Tests

**Files:** Create `tests/admin/test_trade_history_paging.py`

- [ ] **Step 1:** Cover: today-mode shows only trades closed today; `active` matches `today` for this table; `all` shows everything; paging returns disjoint pages whose union is the full filtered set; filters apply across the whole set, not just one page; dropdown options still come from full history.
- [ ] **Step 2:** Regression guard for `32afe78` ("Trade History showed no trades on page 1") — assert page 1 is non-empty when trades exist.
- [ ] **Step 3:** `python scripts/testrun.py full`. Commit.

### Task H7: Manual check

- [ ] **Step 1:** Run the admin UI, switch all three modes, page through, combine filters with paging, confirm counts. Charts/templates changed, so `testrun.py fast` will auto-escalate to `full` — let it.

### Task H8: Docs

**Files:** Modify `docs/claude/known-traps.md`

- [ ] **Step 1:** Record the coupling: Trade History's filters and pagination must stay on the same side (both server or both client), because splitting them silently filters only the visible page. Commit.

---

## Verification Summary

| Behaviour | Before | After |
| --- | --- | --- |
| Today + Open / Today only | table ignored mode, showed all history | only trades closed today |
| All days | up to 500 rows shipped at once | one page per request |
| Filters | client-side, current DOM only | server-side, whole filtered set |
| Row cap | 500 + truncation banner | none |

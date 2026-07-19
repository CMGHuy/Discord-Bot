# Admin UI + TradingView-Style Charts — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute in order U1→U36.

**Goal:** One terminal-grade visual language across admin pages, mplfinance PNG charts, and new vendored-TradingView interactive charts — per `docs/superpowers/specs/2026-07-19-admin-ui-tradingview-redesign-design.md`.

**Architecture:** A CSS design-token layer (`tokens.css`) becomes the single visual source of truth; `style.css` is rebuilt on top of it and `chart_style.py` mirrors the same hex values (sync enforced by a unit test). Interactivity comes from TradingView's open-source `lightweight-charts` (vendored, Apache-2.0) fed by one new read-only authed endpoint `/api/ohlcv/<ticker>`.

**Tech Stack:** Flask + Jinja2, vanilla JS, vendored `lightweight-charts@4.2.3`, self-hosted Inter, matplotlib/mplfinance, pytest.

## Progress

> Updated by the executing session after each task. Resume from the first unchecked task.
>
> - **Branch:** `feature/ui-tradingview` (from `main`)
> - **Completed:** —
> - **Next:** Task U1

## Global Constraints

- **No runtime CDN** — after U2, `base.html` must contain zero external `<link>`/`<script>` origins.
- **No behavior changes** to routes/trading logic; the ONLY backend addition is `/api/ohlcv/<ticker>` (U27–U28).
- **Never suppress WEAK** — badges restyle only.
- Every task ends green: `python -m pytest tests/ -q` and the py_compile loop (`python -m py_compile bot.py admin_ui.py` + all of `swingbot/**/*.py`) before commit. Conventional commits, one per task.
- Windows dev machine: use `python`, never `python3`; no `%-d` strftime flags.
- All numeric table cells get class `num` (`tabular-nums`, right-aligned); P&L cells additionally `pos`/`neg`.

## File Structure

```
swingbot/admin/static/tokens.css                    NEW  design tokens (U3)
swingbot/admin/static/style.css                     REBUILT on tokens (U4–U9, U10–U17)
swingbot/admin/static/vendor/inter/*                NEW  self-hosted font (U2)
swingbot/admin/static/vendor/lightweight-charts/*   NEW  vendored engine (U26)
swingbot/admin/static/chart-init.js                 NEW  interactive chart bootstrap (U29)
swingbot/admin/templates/*.html                     restyled markup passes (U10–U16, U30–U31)
swingbot/admin/app.py                               + /api/ohlcv (U27–U28)
swingbot/core/charts/chart_style.py                 THEME dict + palette sync (U19, U23)
swingbot/core/charts/trade_chart.py                 price pill, edge labels, watermark (U20–U24)
tests/test_admin_pages.py                           NEW  render smoke tests (U1, U18)
tests/test_admin_api_ohlcv.py                       NEW  endpoint tests (U27–U28, U32)
tests/test_chart_theme.py                           NEW  theme sync + render smoke (U19, U25)
```

---

# Phase 0 — Foundations (U1–U9)

### Task U1: Admin render smoke-test harness

**Files:** Create `tests/test_admin_pages.py`

**Interfaces — Produces:** pytest fixture `client` (authed Flask test client) that every later admin test imports from this module.

- [ ] **Step 1: Write the harness + first test**

```python
# tests/test_admin_pages.py
"""Render smoke tests: every admin page returns 200 and carries the marker
classes the redesign relies on. Auth is satisfied by pointing config at
known credentials for the duration of each test."""
import base64

import pytest

from swingbot import config
from swingbot.admin.app import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_USERNAME", "testadmin", raising=False)
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "testpass", raising=False)
    app.config["TESTING"] = True
    token = base64.b64encode(b"testadmin:testpass").decode()
    with app.test_client() as c:
        c.environ_base["HTTP_AUTHORIZATION"] = f"Basic {token}"
        yield c


PAGES = ["/", "/stats", "/watchlist", "/settings", "/logs"]


@pytest.mark.parametrize("path", PAGES)
def test_page_renders(client, path):
    resp = client.get(path)
    assert resp.status_code == 200, f"{path} -> {resp.status_code}"
```

- [ ] **Step 2: Run** `python -m pytest tests/test_admin_pages.py -v`. If a 401 comes back, read `swingbot/admin/app.py`'s `require_auth` to see where it reads credentials (module global vs `config.X` at call time) and adjust the monkeypatch target so the fixture authenticates — the fixture, not the app, is what changes. Expected: 5 PASS.
- [ ] **Step 3: Commit** `test: admin page render smoke harness`

### Task U2: Self-host Inter, drop the Google Fonts CDN

**Files:** Create `swingbot/admin/static/vendor/inter/inter.css` (+ 4 woff2 files); Modify `swingbot/admin/templates/base.html`

- [ ] **Step 1: Download the four weights** (Inter is OFL-licensed) into `swingbot/admin/static/vendor/inter/`:

```bash
cd swingbot/admin/static/vendor/inter
for w in 400 500 600 700; do curl -sL -o inter-$w.woff2 "https://cdn.jsdelivr.net/fontsource/fonts/inter@latest/latin-$w-normal.woff2"; done
```

Also save the OFL license: `curl -sL -o LICENSE.txt "https://raw.githubusercontent.com/rsms/inter/master/LICENSE.txt"`

- [ ] **Step 2: Write `inter.css`**

```css
/* Inter (SIL OFL 1.1) — self-hosted; see LICENSE.txt in this folder. */
@font-face { font-family: "Inter"; font-style: normal; font-weight: 400; font-display: swap; src: url("inter-400.woff2") format("woff2"); }
@font-face { font-family: "Inter"; font-style: normal; font-weight: 500; font-display: swap; src: url("inter-500.woff2") format("woff2"); }
@font-face { font-family: "Inter"; font-style: normal; font-weight: 600; font-display: swap; src: url("inter-600.woff2") format("woff2"); }
@font-face { font-family: "Inter"; font-style: normal; font-weight: 700; font-display: swap; src: url("inter-700.woff2") format("woff2"); }
```

- [ ] **Step 3: In `base.html`** delete the two `fonts.googleapis.com`/`fonts.gstatic.com` preconnect links and the Google `<link href="https://fonts.googleapis.com/css2?family=Inter...">`; in their place add, ABOVE the style.css link:

```html
<link rel="stylesheet" href="{{ url_for('static', filename='vendor/inter/inter.css') }}">
```

- [ ] **Step 4: Verify** `python -m pytest tests/test_admin_pages.py -q` (5 pass) and `grep -n "googleapis\|gstatic" swingbot/admin/templates/base.html` returns nothing.
- [ ] **Step 5: Commit** `feat: self-host Inter, remove Google Fonts CDN`

### Task U3: Design tokens (`tokens.css`)

**Files:** Create `swingbot/admin/static/tokens.css`; Modify `base.html` (link it before `style.css`); Modify `style.css` (delete its old `:root` block, keep `--font-sans` value moved into tokens)

**Interfaces — Produces:** every CSS custom property below; ALL later CSS tasks reference these names verbatim.

- [ ] **Step 1: Write `tokens.css` in full**

```css
/* ============================================================
   Design tokens — the single visual source of truth.
   chart_style.py mirrors the color values (THEME dict); a unit
   test (tests/test_chart_theme.py) keeps the two in sync.
   ============================================================ */
:root {
  color-scheme: dark;
  /* --- Surfaces (TradingView-derived family) --- */
  --bg-0: #0e1118;        /* page */
  --bg-1: #131722;        /* panels / cards — matches chart background */
  --bg-2: #1c2230;        /* raised: chips, hovers, inputs */
  --border-1: #232734;    /* hairline borders / gridline family */
  --border-2: #2a2e39;    /* stronger borders (chart spine family) */
  /* --- Text --- */
  --text-1: #d1d4dc;      /* primary */
  --text-2: #9aa0ac;      /* secondary */
  --text-3: #787b86;      /* muted / fine print */
  /* --- Semantics --- */
  --accent: #2f7dfa;      /* actions, links, active nav (entry-line blue) */
  --accent-soft: rgba(47, 125, 250, .14);
  --up: #26a69a;  --up-soft: rgba(38, 166, 154, .14);
  --down: #ef5350; --down-soft: rgba(239, 83, 80, .14);
  --warn: #ffa726; --warn-soft: rgba(255, 167, 38, .14);
  --purple: #ab47bc;      /* TP2 family */
  /* --- Type --- */
  --font-sans: "Inter", -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  --font-mono: ui-monospace, "Cascadia Mono", "Consolas", monospace;
  --fs-xs: 12px; --fs-sm: 13px; --fs-md: 14px; --fs-lg: 16px; --fs-xl: 20px;
  /* --- Space / radius / elevation / motion --- */
  --sp-1: 4px; --sp-2: 8px; --sp-3: 12px; --sp-4: 16px; --sp-5: 24px; --sp-6: 32px;
  --r-sm: 6px; --r-md: 10px; --r-lg: 14px; --r-pill: 999px;
  --shadow-1: 0 1px 2px rgba(0,0,0,.4);
  --shadow-2: 0 6px 24px rgba(0,0,0,.45);
  --ease: 140ms cubic-bezier(.4, 0, .2, 1);
}
.num { font-variant-numeric: tabular-nums; text-align: right; }
.pos { color: var(--up); }
.neg { color: var(--down); }
```

- [ ] **Step 2:** In `base.html` add `<link rel="stylesheet" href="{{ url_for('static', filename='tokens.css') }}">` immediately before the `style.css` link. In `style.css`, delete the existing `:root { ... }` block (its `--font-sans` now lives in tokens.css) and replace raw `#0d0f14` body background with `var(--bg-0)`, body color with `var(--text-1)`, `a` color with `var(--accent)`.
- [ ] **Step 3: Verify + commit** — smoke tests pass; visually load `/` once (`python admin_ui.py`, browser) to confirm no unstyled flash. Commit `feat: design token layer (tokens.css)`.

### Task U4: Shell + sidebar restyle

**Files:** Modify `style.css` (sidebar/shell sections), `base.html` (nav markup gains an active-bar span)

- [ ] **Step 1:** In `base.html`, inside each nav `<a>`, prepend `<span class="nav-bar"></span>` before the icon span.
- [ ] **Step 2:** Replace the sidebar CSS block in `style.css` with:

```css
.shell { display: flex; min-height: 100vh; }
.sidebar {
  width: 216px; flex-shrink: 0; background: var(--bg-1);
  border-right: 1px solid var(--border-1);
  display: flex; flex-direction: column; position: sticky; top: 0; height: 100vh;
}
.sidebar nav { flex: 1; overflow-y: auto; padding: var(--sp-2) 0; }
.sidebar nav a {
  position: relative; display: flex; align-items: center; gap: var(--sp-3);
  padding: 9px var(--sp-4); margin: 1px var(--sp-2); border-radius: var(--r-sm);
  color: var(--text-2); text-decoration: none; font-size: var(--fs-sm);
  font-weight: 500; transition: background var(--ease), color var(--ease);
}
.sidebar nav a:hover { background: var(--bg-2); color: var(--text-1); }
.sidebar nav a.active { background: var(--accent-soft); color: var(--text-1); }
.sidebar nav a .nav-bar {
  position: absolute; left: -8px; top: 20%; height: 60%; width: 3px;
  border-radius: 2px; background: transparent;
}
.sidebar nav a.active .nav-bar { background: var(--accent); }
.brand { padding: var(--sp-4); border-bottom: 1px solid var(--border-1); }
```

Keep every existing sidebar rule this doesn't replace (mobile overlay, footer) but re-express their colors via tokens (`#13161d`→`var(--bg-1)`, `#1f2330`→`var(--border-1)` etc. — grep `#` in the sidebar section and convert each).

- [ ] **Step 3: Verify + commit** — smoke tests; visual check active state on each page. Commit `feat: sidebar + shell restyle on tokens`.

### Task U5: Buttons + pills/badges

**Files:** Modify `style.css`

- [ ] **Step 1:** Replace the existing button and `.pill` rules with:

```css
button, .btn {
  font: 500 var(--fs-sm)/1 var(--font-sans); color: #fff;
  background: var(--accent); border: 1px solid transparent;
  padding: 8px 14px; border-radius: var(--r-sm); cursor: pointer;
  transition: filter var(--ease), transform var(--ease);
}
button:hover, .btn:hover { filter: brightness(1.12); }
button:active, .btn:active { transform: translateY(1px); }
button.secondary, .btn.secondary {
  background: var(--bg-2); color: var(--text-1); border-color: var(--border-2);
}
button.danger, .btn.danger { background: var(--down); }
button.ghost, .btn.ghost { background: transparent; color: var(--text-2); border-color: transparent; }
button.small, .btn.small { padding: 5px 10px; font-size: var(--fs-xs); }
button:disabled { opacity: .45; cursor: not-allowed; }
.pill {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 10px; border-radius: var(--r-pill);
  font-size: var(--fs-xs); font-weight: 600; line-height: 18px;
  background: var(--bg-2); color: var(--text-2); border: 1px solid var(--border-2);
}
.pill.validated { background: var(--up-soft); color: var(--up); border-color: transparent; }
.pill.weak      { background: var(--warn-soft); color: var(--warn); border-color: transparent; }
.pill.tier-a { background: var(--up-soft); color: var(--up); border-color: transparent; }
.pill.tier-b { background: var(--accent-soft); color: var(--accent); border-color: transparent; }
.pill.tier-c { background: var(--warn-soft); color: var(--warn); border-color: transparent; }
```

- [ ] **Step 2: Verify + commit** `feat: button hierarchy + badge pill system`

### Task U6: Cards + stat tiles

**Files:** Modify `style.css`

- [ ] **Step 1:** Replace/add:

```css
.card {
  background: var(--bg-1); border: 1px solid var(--border-1);
  border-radius: var(--r-md); padding: var(--sp-4); box-shadow: var(--shadow-1);
}
.card > h2, .card > h3 { margin: 0 0 var(--sp-3); font-size: var(--fs-md); font-weight: 600; color: var(--text-1); }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: var(--sp-3); }
.tile {
  background: var(--bg-1); border: 1px solid var(--border-1); border-radius: var(--r-md);
  padding: var(--sp-3) var(--sp-4);
}
.tile .label { font-size: var(--fs-xs); font-weight: 500; color: var(--text-3); text-transform: uppercase; letter-spacing: .04em; }
.tile .value { font-size: var(--fs-xl); font-weight: 700; font-variant-numeric: tabular-nums; margin-top: 2px; }
.tile .delta { font-size: var(--fs-xs); font-weight: 600; margin-left: var(--sp-1); }
```

- [ ] **Step 2: Verify + commit** `feat: card + stat tile components`

### Task U7: Tables

**Files:** Modify `style.css`

- [ ] **Step 1:** Replace the table rules:

```css
table { width: 100%; border-collapse: collapse; font-size: var(--fs-sm); }
thead th {
  position: sticky; top: 0; z-index: 1; background: var(--bg-1);
  color: var(--text-3); font-size: var(--fs-xs); font-weight: 600;
  text-transform: uppercase; letter-spacing: .05em; text-align: left;
  padding: 8px 10px; border-bottom: 1px solid var(--border-2);
}
tbody td { padding: 8px 10px; border-bottom: 1px solid var(--border-1); color: var(--text-1); }
tbody tr { transition: background var(--ease); }
tbody tr:hover { background: var(--bg-2); }
thead th.num { text-align: right; }
```

- [ ] **Step 2: Verify + commit** `feat: table restyle (sticky head, hover, tabular nums)`

### Task U8: Forms (settings inputs)

**Files:** Modify `style.css`

- [ ] **Step 1:** Replace input/select/label rules:

```css
input[type="text"], input[type="number"], input[type="password"], select, textarea {
  background: var(--bg-2); color: var(--text-1);
  border: 1px solid var(--border-2); border-radius: var(--r-sm);
  padding: 7px 10px; font: 400 var(--fs-sm) var(--font-sans);
  transition: border-color var(--ease), box-shadow var(--ease);
}
input:focus, select:focus, textarea:focus {
  outline: none; border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
label { color: var(--text-2); font-size: var(--fs-sm); }
input[type="checkbox"] { accent-color: var(--accent); }
```

- [ ] **Step 2: Verify + commit** `feat: form input restyle`

### Task U9: States, focus, scrollbars, flash

**Files:** Modify `style.css`

- [ ] **Step 1:** Add:

```css
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb { background: var(--border-2); border-radius: 5px; }
::-webkit-scrollbar-thumb:hover { background: #3a3f4e; }
.empty-state { text-align: center; color: var(--text-3); padding: var(--sp-6); font-size: var(--fs-sm); }
.empty-state .glyph { font-size: 28px; display: block; margin-bottom: var(--sp-2); opacity: .5; }
.skeleton {
  background: linear-gradient(90deg, var(--bg-2) 25%, var(--border-1) 50%, var(--bg-2) 75%);
  background-size: 200% 100%; animation: shimmer 1.2s infinite; border-radius: var(--r-sm);
}
@keyframes shimmer { to { background-position: -200% 0; } }
.flash { border-radius: var(--r-sm); padding: 10px 14px; font-size: var(--fs-sm);
  background: var(--accent-soft); color: var(--text-1); border: 1px solid var(--accent); }
.flash.error { background: var(--down-soft); border-color: var(--down); }
```

- [ ] **Step 2: Verify + commit** `feat: focus rings, scrollbars, empty/skeleton/flash states`

---

# Phase 1 — Page passes (U10–U18)

> Pattern for every page task: (1) read the template, (2) apply the class conversions listed, (3) run smoke tests, (4) load the page in a browser once, (5) commit. No route/logic edits anywhere in this phase.

### Task U10: Dashboard header + controls

**Files:** Modify `swingbot/admin/templates/dashboard.html`, `style.css`

- [ ] **Step 1:** Wrap the mode buttons row in `<div class="toolbar">`; convert mode buttons to `class="btn ghost small dashboard-mode-btn"` with the active one getting `secondary` (keep `data-mode` attributes and all JS hooks/ids untouched). Status cluster (`bot-status-dot`, pause badge, trigger buttons) stays functionally identical — only classes change (`secondary small`, `danger small` already exist and now inherit U5 styling).
- [ ] **Step 2:** Add to `style.css`:

```css
.toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: var(--sp-2); margin-bottom: var(--sp-4); }
.toolbar .spacer { flex: 1; }
.trade-status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.trade-status-dot.ok { background: var(--up); box-shadow: 0 0 6px var(--up); }
.trade-status-dot.bad { background: var(--down); }
```

- [ ] **Step 3: Verify + commit** `feat: dashboard toolbar restyle`

### Task U11: Dashboard open-trades fragment

**Files:** Modify `swingbot/admin/templates/dashboard_fragment.html`

- [ ] **Step 1:** Add `class="num"` to every numeric `<td>`/`<th>` (entry, stop, target, price, P/L%, R); add `class="num pos"`/`"num neg"` conditionally where the template already computes P/L sign (follow the template's existing Jinja conditionals — e.g. `class="num {{ 'pos' if t.pnl_pct and t.pnl_pct > 0 else 'neg' if t.pnl_pct and t.pnl_pct < 0 else '' }}"`). Add `data-ticker="{{ t.ticker }}"` to each `<tr>` (consumed by U31's modal). Badge cells: render `<span class="pill validated">✅ VALIDATED</span>` / `<span class="pill weak">⚠️ WEAK</span>` based on the existing badge field.
- [ ] **Step 2: Verify + commit** `feat: dashboard trades table markup pass`

### Task U12: Stats page

**Files:** Modify `swingbot/admin/templates/stats.html`

- [ ] **Step 1:** Convert the headline stat row into `tiles`/`tile` markup (`label`/`value`, delta chip with `pos`/`neg`); wrap each stats table in `<div class="card">`; `num` classes on all numeric columns as in U11.
- [ ] **Step 2: Verify + commit** `feat: stats page tiles + cards`

### Task U13: Watchlist page

**Files:** Modify `swingbot/admin/templates/watchlist.html`

- [ ] **Step 1:** Ticker chips become `pill`; the add form inputs inherit U8; wrap sections in `card`; empty watchlist renders `<div class="empty-state"><span class="glyph">📄</span>No tickers yet — add one above.</div>`.
- [ ] **Step 2: Verify + commit** `feat: watchlist page pass`

### Task U14: Settings page

**Files:** Modify `swingbot/admin/templates/settings.html`, `style.css`

- [ ] **Step 1:** Each config section becomes a `card` with the section name as `<h3>`; two-column field grid:

```css
.settings-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: var(--sp-3) var(--sp-5); }
.field-row { display: flex; flex-direction: column; gap: 4px; }
.field-row .help { color: var(--text-3); font-size: var(--fs-xs); line-height: 1.45; }
```

Save button: `class="btn"` sticky footer bar (`position: sticky; bottom: 0; background: var(--bg-0); padding: var(--sp-3) 0;`).

- [ ] **Step 2: Verify + commit** `feat: settings page cards + field grid`

### Task U15: Logs page

**Files:** Modify `swingbot/admin/templates/logs.html`, `style.css`

- [ ] **Step 1:** Log viewer becomes:

```css
.log-view { font-family: var(--font-mono); font-size: var(--fs-xs); line-height: 1.6;
  background: var(--bg-1); border: 1px solid var(--border-1); border-radius: var(--r-md);
  padding: var(--sp-3); overflow: auto; }
.log-view .lvl-warn { color: var(--warn); } .log-view .lvl-error { color: var(--down); }
```

If the template renders raw lines, keep it raw — add the level classes only if it already splits lines; do not add server-side parsing.

- [ ] **Step 2: Verify + commit** `feat: logs viewer restyle`

### Task U16: Trade-detail layout

**Files:** Modify `swingbot/admin/templates/trade_detail.html`, `style.css`

- [ ] **Step 1:** Two-column layout — chart area (flexible) + facts card (fixed 320px): plan numbers in a `card` with `num` values, badge pill, status pill, close button as `btn danger`. CSS:

```css
.detail-grid { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: var(--sp-4); }
@media (max-width: 900px) { .detail-grid { grid-template-columns: 1fr; } }
```

The PNG chart `<img>` gets `style="width:100%; border-radius: var(--r-md); border: 1px solid var(--border-1);"` (via a class `chart-img`).

- [ ] **Step 2: Verify + commit** `feat: trade detail two-column layout`

### Task U17: Responsive/mobile pass

**Files:** Modify `style.css`

- [ ] **Step 1:** Audit at 380px/768px widths: keep the existing sidebar-overlay mechanism; ensure `.tiles` collapses (it does via auto-fit); wrap wide tables in `<div class="table-scroll">` where needed with `.table-scroll { overflow-x: auto; }`; toolbar wraps (already `flex-wrap`).
- [ ] **Step 2: Verify + commit** `fix: responsive pass at 380/768px`

### Task U18: Marker-class smoke tests

**Files:** Modify `tests/test_admin_pages.py`

- [ ] **Step 1: Append**

```python
def test_tokens_and_font_are_linked(client):
    html = client.get("/").get_data(as_text=True)
    assert "tokens.css" in html and "vendor/inter/inter.css" in html
    assert "googleapis" not in html  # no-CDN constraint


def test_stats_page_has_tiles(client):
    html = client.get("/stats").get_data(as_text=True)
    assert 'class="tile' in html or "tiles" in html


def test_settings_page_has_cards(client):
    assert 'class="card' in client.get("/settings").get_data(as_text=True)
```

- [ ] **Step 2: Run all + commit** `test: marker-class assertions for redesigned pages`

---

# Phase 2 — PNG chart theme v2 (U19–U25)

### Task U19: THEME dict + palette sync test

**Files:** Modify `swingbot/core/charts/chart_style.py`; Create `tests/test_chart_theme.py`

**Interfaces — Produces:** `chart_style.THEME: dict[str, str]` — the Python mirror of tokens.css; later chart tasks read colors ONLY via existing constants (unchanged names).

- [ ] **Step 1:** At the top of `chart_style.py` (after the existing constants), add:

```python
# Mirror of swingbot/admin/static/tokens.css — the admin UI and the chart
# PNGs share one palette. tests/test_chart_theme.py asserts these pairs
# stay equal to the module constants; change BOTH files together.
THEME = {
    "bg-1": "#131722", "border-1": "#232734", "border-2": "#2a2e39",
    "text-1": "#d1d4dc", "text-3": "#787b86",
    "up": "#26a69a", "down": "#ef5350", "accent": "#2f7dfa",
    "warn": "#ffa726", "purple": "#ab47bc",
}
```

- [ ] **Step 2: Test**

```python
# tests/test_chart_theme.py
from swingbot.core.charts import chart_style as cs


def test_theme_dict_matches_module_constants():
    assert cs.THEME["bg-1"] == cs.CHART_BG
    assert cs.THEME["border-1"] == cs.GRID_COLOR
    assert cs.THEME["border-2"] == cs.SPINE_COLOR
    assert cs.THEME["text-1"] == cs.TEXT_COLOR
    assert cs.THEME["text-3"] == cs.MUTED_TEXT_COLOR
    assert cs.THEME["up"] == cs.UP_COLOR
    assert cs.THEME["down"] == cs.DOWN_COLOR
    assert cs.THEME["accent"] == cs.ENTRY_COLOR
    assert cs.THEME["warn"] == cs.CURRENT_PRICE_COLOR
    assert cs.THEME["purple"] == cs.TARGET2_COLOR


def test_theme_matches_tokens_css():
    """Parse tokens.css and compare the shared hex values byte-for-byte."""
    import re
    from pathlib import Path
    css = Path("swingbot/admin/static/tokens.css").read_text(encoding="utf-8")
    tokens = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", css))
    for key in ("bg-1", "border-1", "border-2", "text-1", "text-3", "up", "down", "accent", "warn", "purple"):
        assert tokens[key].lower() == cs.THEME[key].lower(), key
```

- [ ] **Step 3: Run — both must PASS already** (values chosen to match). If a constant differs, fix `tokens.css` (charts are the authority). Commit `feat: chart/admin palette sync (THEME dict + test)`.

### Task U20: Last-price line + right-edge price pill

**Files:** Modify `swingbot/core/charts/trade_chart.py`

- [ ] **Step 1:** Add a helper near the other drawing helpers:

```python
def _draw_last_price_pill(ax, df, color=CURRENT_PRICE_COLOR):
    """TradingView-style: dashed horizontal ray at the last close plus a
    solid price pill pinned to the right edge of the axes."""
    last = float(df["Close"].iloc[-1])
    ax.axhline(last, color=color, linewidth=0.8, linestyle=(0, (4, 3)), alpha=0.9, zorder=4)
    ax.annotate(
        f" {last:,.2f} ", xy=(1.0, last), xycoords=("axes fraction", "data"),
        xytext=(2, 0), textcoords="offset points", va="center", ha="left",
        fontsize=8, fontweight="bold", color=CHART_BG, zorder=6,
        bbox=dict(boxstyle="round,pad=0.28", fc=color, ec="none"),
        annotation_clip=False,
    )
```

- [ ] **Step 2:** Call it from `generate_trade_chart` on the price axes right after the candles/addplots are drawn (locate the block where existing level annotations are drawn on panel 0 and call `_draw_last_price_pill(price_ax, plot_df)` there). Right margin: ensure `fig.subplots_adjust(right=0.90)` (or the existing tight-layout equivalent) leaves room so the pill isn't clipped.
- [ ] **Step 3: Verify** with U25's smoke test pattern run manually (`python -c` snippet from U25 Step 1) — a PNG file is produced. Commit `feat: last-price line + right-edge pill on charts`.

### Task U21: Entry/SL/TP right-edge pills

**Files:** Modify `swingbot/core/charts/trade_chart.py` (and the chart_levels helper module if the chips are drawn there — grep `CHIP_BG` to find the exact call sites)

- [ ] **Step 1:** Add a generic pill helper (same file as U20's, directly below it):

```python
def _draw_level_pill(ax, y, text, color):
    """Right-edge pill for a plan level (entry/SL/TP). Replaces the old
    mid-chart chip boxes, matching TradingView's price-scale labels."""
    ax.annotate(
        f" {text} ", xy=(1.0, y), xycoords=("axes fraction", "data"),
        xytext=(2, 0), textcoords="offset points", va="center", ha="left",
        fontsize=7.5, fontweight="bold", color=CHART_BG, zorder=5,
        bbox=dict(boxstyle="round,pad=0.25", fc=color, ec="none"),
        annotation_clip=False,
    )
```

- [ ] **Step 2:** For each of entry/stop/TP1/TP2 level lines currently annotated with mid-chart chips, keep the horizontal line exactly as-is but replace the chip annotation with `_draw_level_pill(ax, level, f"{label} {price:,.2f}", LEVEL_COLOR)` using the existing per-level colors (`ENTRY_COLOR`, `STOP_COLOR`, `TARGET_COLOR`, `TARGET2_COLOR`). If two pills would overlap (|y1−y2| < 0.8% of the axis range), offset the later one by ±10 offset-points via the `xytext` parameter.
- [ ] **Step 3: Verify** render smoke (as U20) + eyeball one generated PNG. Commit `feat: level lines get right-edge pills`.

### Task U22: Ticker watermark

**Files:** Modify `swingbot/core/charts/trade_chart.py`

- [ ] **Step 1:** After the axes exist in `generate_trade_chart`, add:

```python
    price_ax.text(
        0.012, 0.985, f"{ticker}  ·  {horizon_label}",
        transform=price_ax.transAxes, ha="left", va="top",
        fontsize=15, fontweight="bold", color=TEXT_COLOR, alpha=0.16, zorder=1,
    )
```

(`horizon_label` = the horizon string the function already receives/derives; if only `horizon_key` exists, use it directly.)

- [ ] **Step 2: Verify + commit** `feat: subtle ticker watermark on charts`

### Task U23: Volume tint + quieter axes

**Files:** Modify `swingbot/core/charts/chart_style.py` (mpf style), `trade_chart.py`

- [ ] **Step 1:** In the mpf style/marketcolors construction in `chart_style.py`, set volume up/down colors to translucent variants: `volume="in"` marketcolors replaced with explicit `mpf.make_marketcolors(..., volume={"up": "#26a69a55", "down": "#ef535055"})` (keep every other argument as it is today).
- [ ] **Step 2:** In `trade_chart.py` where axes are finalized, reduce tick density and mute labels:

```python
    for ax_ in fig.axes:
        ax_.tick_params(labelsize=7, colors=MUTED_TEXT_COLOR, length=0)
        ax_.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(nbins=6, prune="both"))
```

- [ ] **Step 3: Verify + commit** `feat: tinted volume + quieter axes`

### Task U24: Inter on charts (optional font registration)

**Files:** Modify `swingbot/core/charts/chart_style.py`

- [ ] **Step 1:** After the imports:

```python
import os
from matplotlib import font_manager as _fm

_INTER = os.path.join(os.path.dirname(__file__), "..", "..", "admin", "static", "vendor", "inter", "inter-500.woff2")
# matplotlib cannot load woff2 — only register if a ttf/otf is present.
# Optional nicety: drop Inter-Medium.ttf into that folder to activate; the
# charts fall back to the default sans (DejaVu) otherwise, by design.
_INTER_TTF = _INTER.replace("inter-500.woff2", "Inter-Medium.ttf")
if os.path.exists(_INTER_TTF):
    _fm.fontManager.addfont(_INTER_TTF)
    matplotlib.rcParams["font.family"] = "Inter"
```

- [ ] **Step 2: Verify + commit** `feat: optional Inter registration for chart text`

### Task U25: Chart render smoke test

**Files:** Modify `tests/test_chart_theme.py`

- [ ] **Step 1: Append**

```python
def test_generate_trade_chart_smoke(tmp_path, monkeypatch):
    """End-to-end render on synthetic OHLCV: produces a non-trivial PNG.
    No golden pixels (brittle) — existence + size only."""
    import numpy as np
    import pandas as pd
    from swingbot.core.charts.trade_chart import generate_trade_chart

    idx = pd.bdate_range("2025-01-01", periods=120)
    close = pd.Series(100 + np.cumsum(np.random.default_rng(7).normal(0, 1, 120)), index=idx)
    df = pd.DataFrame({"Open": close.shift(1).fillna(close), "High": close + 1,
                       "Low": close - 1, "Close": close, "Volume": 1_000_000}, index=idx)
    out = generate_trade_chart(
        ticker="TEST", df=df, entry=float(close.iloc[-1]),
        stop_loss=float(close.iloc[-1]) * 0.95, take_profit=float(close.iloc[-1]) * 1.08,
        direction="bullish", out_dir=str(tmp_path),
    )
    assert out is not None
    import os
    assert os.path.getsize(out) > 20_000  # a real rendered chart, not a stub
```

Before running, read `generate_trade_chart`'s real signature (`swingbot/core/charts/trade_chart.py:147`) and adapt the call's parameter names to it — the assertion contract (non-None path, >20KB PNG) is the fixed part, the kwargs are whatever the function actually takes.

- [ ] **Step 2: Run + commit** `test: chart render smoke on synthetic OHLCV`

---

# Phase 3 — Interactive charts (U26–U32)

### Task U26: Vendor lightweight-charts

**Files:** Create `swingbot/admin/static/vendor/lightweight-charts/lightweight-charts.standalone.production.js` + `LICENSE` + `VERSION`

- [ ] **Step 1:**

```bash
cd swingbot/admin/static/vendor && mkdir -p lightweight-charts && cd lightweight-charts
curl -sL -o lightweight-charts.standalone.production.js "https://unpkg.com/lightweight-charts@4.2.3/dist/lightweight-charts.standalone.production.js"
curl -sL -o LICENSE "https://raw.githubusercontent.com/tradingview/lightweight-charts/master/LICENSE"
echo "4.2.3 — pinned; do not auto-update (v5 changed the series API)" > VERSION
```

- [ ] **Step 2:** Sanity: file starts with `/*!` banner mentioning TradingView and is >100KB. Commit `feat: vendor lightweight-charts 4.2.3 (Apache-2.0)`.

### Task U27: `/api/ohlcv/<ticker>` endpoint

**Files:** Modify `swingbot/admin/app.py`; Create `tests/test_admin_api_ohlcv.py`

**Interfaces — Produces:** `GET /api/ohlcv/<ticker>?bars=N` → `{"ticker": str, "bars": [{"time": "YYYY-MM-DD", "open": f, "high": f, "low": f, "close": f, "volume": f}]}`; consumed by U29's JS.

- [ ] **Step 1: Failing tests**

```python
# tests/test_admin_api_ohlcv.py
import numpy as np
import pandas as pd

from tests.test_admin_pages import client  # noqa: F401  (authed fixture)


def _fake_df(n=300):
    idx = pd.bdate_range("2024-01-01", periods=n)
    c = pd.Series(50 + np.cumsum(np.random.default_rng(3).normal(0, .5, n)), index=idx)
    return pd.DataFrame({"Open": c, "High": c + .5, "Low": c - .5, "Close": c, "Volume": 9_999}, index=idx)


def test_ohlcv_shape_and_default_cap(client, monkeypatch):
    monkeypatch.setattr("swingbot.admin.app._ohlcv_frame", lambda t: _fake_df())
    data = client.get("/api/ohlcv/AAPL").get_json()
    assert data["ticker"] == "AAPL"
    assert len(data["bars"]) == 260  # default cap
    b = data["bars"][-1]
    assert set(b) == {"time", "open", "high", "low", "close", "volume"}
    import re
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", b["time"])  # ISO date string


def test_ohlcv_bars_param_and_max(client, monkeypatch):
    monkeypatch.setattr("swingbot.admin.app._ohlcv_frame", lambda t: _fake_df(1500))
    assert len(client.get("/api/ohlcv/AAPL?bars=50").get_json()["bars"]) == 50
    assert len(client.get("/api/ohlcv/AAPL?bars=99999").get_json()["bars"]) == 1000  # hard max


def test_ohlcv_no_data_404(client, monkeypatch):
    monkeypatch.setattr("swingbot.admin.app._ohlcv_frame", lambda t: None)
    assert client.get("/api/ohlcv/NOPE").status_code == 404


def test_ohlcv_requires_auth():
    from swingbot.admin.app import app
    app.config["TESTING"] = True
    with app.test_client() as anon:
        assert anon.get("/api/ohlcv/AAPL").status_code == 401
```

- [ ] **Step 2: Implement in `app.py`** (near the other `/trades` routes):

```python
def _ohlcv_frame(ticker: str):
    """Daily OHLCV for the interactive chart: live fetch first, falling back
    to the backtest CSV cache so the chart still renders offline. Split out
    of the route for testability (tests monkeypatch this)."""
    try:
        from swingbot.core.data import get_daily_data
        df = get_daily_data(ticker)
        if df is not None and len(df):
            return df
    except Exception:
        pass
    import pandas as pd
    safe = ticker.replace("=", "_").replace("^", "_").replace("/", "_")
    p = os.path.join(config.DATA_DIR, "backtest_cache", f"{safe}.csv")
    if os.path.exists(p):
        try:
            return pd.read_csv(p, index_col="Date", parse_dates=True)
        except Exception:
            return None
    return None


@app.route("/api/ohlcv/<ticker>", methods=["GET"])
@require_auth
def api_ohlcv(ticker):
    ticker = ticker.upper()
    try:
        bars = max(1, min(int(request.args.get("bars", 260)), 1000))
    except ValueError:
        bars = 260
    df = _ohlcv_frame(ticker)
    if df is None or not len(df):
        return Response(json.dumps({"error": "no data"}), status=404, mimetype="application/json")
    df = df.tail(bars)
    payload = {
        "ticker": ticker,
        "bars": [
            {"time": idx.strftime("%Y-%m-%d"), "open": round(float(r["Open"]), 4),
             "high": round(float(r["High"]), 4), "low": round(float(r["Low"]), 4),
             "close": round(float(r["Close"]), 4), "volume": float(r["Volume"])}
            for idx, r in df.iterrows()
        ],
    }
    return Response(json.dumps(payload), mimetype="application/json")
```

(Reuse the module's existing `os`/`json`/`request`/`Response`/`config` imports — add any that are missing.)

- [ ] **Step 3: Run tests → PASS. Commit** `feat: /api/ohlcv endpoint (cache-fallback, capped)`

### Task U28: Plan levels in the payload

**Files:** Modify `swingbot/admin/app.py`, `tests/test_admin_api_ohlcv.py`

**Interfaces — Produces:** optional `?trade_id=X` adds `"levels": {"entry": f|null, "stop_loss": f|null, "tp1": f|null, "tp2": f|null, "direction": str|null}`.

- [ ] **Step 1: Failing test**

```python
def test_ohlcv_levels_from_trade(client, monkeypatch):
    monkeypatch.setattr("swingbot.admin.app._ohlcv_frame", lambda t: _fake_df())
    fake = {"id": "t1", "ticker": "AAPL", "entry": 100.0, "stop_loss": 95.0,
            "take_profit": 108.0, "target2_price": 115.0, "direction": "bullish"}
    monkeypatch.setattr("swingbot.admin.app._trade_for_levels", lambda tid: fake)
    data = client.get("/api/ohlcv/AAPL?trade_id=t1").get_json()
    assert data["levels"] == {"entry": 100.0, "stop_loss": 95.0, "tp1": 108.0,
                             "tp2": 115.0, "direction": "bullish"}
```

- [ ] **Step 2: Implement** — helper + 3 lines in the route:

```python
def _trade_for_levels(trade_id: str):
    from swingbot.core.performance import TradeLog
    return TradeLog().get_trade_by_id(trade_id)
```

and in `api_ohlcv`, before building `payload`:

```python
    trade_id = request.args.get("trade_id")
    levels = None
    if trade_id:
        t = _trade_for_levels(trade_id)
        if t:
            levels = {"entry": t.get("entry"), "stop_loss": t.get("stop_loss"),
                      "tp1": t.get("take_profit"), "tp2": t.get("target2_price"),
                      "direction": t.get("direction")}
```

then `if levels is not None: payload["levels"] = levels`.

- [ ] **Step 3: Run + commit** `feat: plan levels in ohlcv payload`

### Task U29: `chart-init.js`

**Files:** Create `swingbot/admin/static/chart-init.js`

**Interfaces — Produces:** global `SwingChart.mount(el)` — reads `data-ticker`, optional `data-trade-id`, `data-bars` off `el`, fetches the API, renders the chart. Consumed by U30/U31.

- [ ] **Step 1: Write in full**

```javascript
/* Interactive chart bootstrap — themed from tokens.css at runtime so the
   chart always matches the page. Requires vendored lightweight-charts 4.x. */
(function () {
  "use strict";
  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }
  function levelLine(series, price, color, title) {
    if (price == null) return;
    series.createPriceLine({ price: price, color: color, lineWidth: 1,
      lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: title });
  }
  async function mount(el) {
    const ticker = el.dataset.ticker;
    if (!ticker) return;
    const qs = new URLSearchParams({ bars: el.dataset.bars || "260" });
    if (el.dataset.tradeId) qs.set("trade_id", el.dataset.tradeId);
    const resp = await fetch(`/api/ohlcv/${encodeURIComponent(ticker)}?` + qs);
    if (!resp.ok) { el.innerHTML = '<div class="empty-state">No chart data.</div>'; return; }
    const data = await resp.json();

    const chart = LightweightCharts.createChart(el, {
      autoSize: true,
      layout: { background: { color: cssVar("--bg-1") }, textColor: cssVar("--text-3"),
                fontFamily: cssVar("--font-sans") },
      grid: { vertLines: { color: cssVar("--border-1") }, horzLines: { color: cssVar("--border-1") } },
      crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
      rightPriceScale: { borderColor: cssVar("--border-2") },
      timeScale: { borderColor: cssVar("--border-2") },
    });
    const candles = chart.addCandlestickSeries({
      upColor: cssVar("--up"), downColor: cssVar("--down"),
      wickUpColor: cssVar("--up"), wickDownColor: cssVar("--down"), borderVisible: false,
    });
    candles.setData(data.bars);
    const vol = chart.addHistogramSeries({ priceFormat: { type: "volume" },
      priceScaleId: "vol" });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    vol.setData(data.bars.map(b => ({ time: b.time, value: b.volume,
      color: b.close >= b.open ? cssVar("--up") + "55" : cssVar("--down") + "55" })));

    if (data.levels) {
      levelLine(candles, data.levels.entry, cssVar("--accent"), "Entry");
      levelLine(candles, data.levels.stop_loss, cssVar("--down"), "SL");
      levelLine(candles, data.levels.tp1, cssVar("--up"), "TP1");
      levelLine(candles, data.levels.tp2, cssVar("--purple"), "TP2");
    }

    // Crosshair OHLC legend (top-left, TradingView style)
    const legend = document.createElement("div");
    legend.className = "chart-legend";
    el.style.position = "relative";
    el.appendChild(legend);
    const last = data.bars[data.bars.length - 1];
    function renderLegend(b) {
      const dir = b.close >= b.open ? "pos" : "neg";
      legend.innerHTML = `<b>${data.ticker}</b> · ` +
        `O <span class="${dir}">${b.open}</span> H <span class="${dir}">${b.high}</span> ` +
        `L <span class="${dir}">${b.low}</span> C <span class="${dir}">${b.close}</span>`;
    }
    renderLegend(last);
    chart.subscribeCrosshairMove(p => {
      const b = p && p.seriesData ? p.seriesData.get(candles) : null;
      renderLegend(b && b.open !== undefined ? b : last);
    });
    chart.timeScale().fitContent();
    return chart;
  }
  window.SwingChart = { mount };
  document.addEventListener("DOMContentLoaded", () =>
    document.querySelectorAll("[data-swing-chart]").forEach(mount));
})();
```

- [ ] **Step 2:** Add legend CSS to `style.css`:

```css
.chart-legend { position: absolute; top: 8px; left: 10px; z-index: 3;
  font-size: var(--fs-xs); color: var(--text-2); pointer-events: none;
  font-variant-numeric: tabular-nums; }
.swing-chart { height: 460px; border: 1px solid var(--border-1); border-radius: var(--r-md); overflow: hidden; }
```

- [ ] **Step 3: Commit** `feat: SwingChart interactive chart bootstrap`

### Task U30: Wire trade_detail

**Files:** Modify `swingbot/admin/templates/trade_detail.html`, `base.html`

- [ ] **Step 1:** In `base.html`, before `</body>`: `<script src="{{ url_for('static', filename='vendor/lightweight-charts/lightweight-charts.standalone.production.js') }}"></script>` and `<script src="{{ url_for('static', filename='chart-init.js') }}"></script>`.
- [ ] **Step 2:** In `trade_detail.html`, above the existing PNG `<img>`:

```html
<div class="swing-chart" data-swing-chart data-ticker="{{ trade.ticker }}" data-trade-id="{{ trade.id }}"></div>
<details style="margin-top: var(--sp-3);"><summary class="muted">Static chart (Discord parity)</summary>
  {# existing PNG <img> moves inside this details block, unchanged #}
</details>
```

- [ ] **Step 3: Verify** — smoke tests still pass; manual browser check on a trade detail page (crosshair, zoom, level lines). Commit `feat: interactive chart on trade detail`.

### Task U31: Dashboard quick-chart modal

**Files:** Modify `swingbot/admin/templates/dashboard.html`, `style.css`

- [ ] **Step 1:** Add modal markup at the end of `dashboard.html`'s body block + inline JS:

```html
<div class="chart-modal" id="chart-modal" hidden>
  <div class="chart-modal-panel">
    <div class="toolbar"><b id="chart-modal-title"></b><span class="spacer"></span>
      <button type="button" class="btn ghost small" id="chart-modal-close">✕</button></div>
    <div class="swing-chart" id="chart-modal-chart" style="height:380px;"></div>
  </div>
</div>
<script>
(function () {
  const modal = document.getElementById("chart-modal");
  const host = document.getElementById("chart-modal-chart");
  document.addEventListener("click", (e) => {
    const row = e.target.closest("tr[data-ticker]");
    if (row && !e.target.closest("a, button, form")) {
      modal.hidden = false;
      document.getElementById("chart-modal-title").textContent = row.dataset.ticker;
      host.innerHTML = ""; host.dataset.ticker = row.dataset.ticker;
      SwingChart.mount(host);
    }
    if (e.target === modal || e.target.id === "chart-modal-close") { modal.hidden = true; host.innerHTML = ""; }
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") { modal.hidden = true; host.innerHTML = ""; } });
})();
</script>
```

```css
.chart-modal { position: fixed; inset: 0; background: rgba(0,0,0,.6); z-index: 50;
  display: flex; align-items: center; justify-content: center; }
.chart-modal-panel { width: min(860px, 94vw); background: var(--bg-1);
  border: 1px solid var(--border-2); border-radius: var(--r-lg);
  padding: var(--sp-4); box-shadow: var(--shadow-2); }
```

- [ ] **Step 2: Verify + commit** `feat: dashboard quick-chart modal`

### Task U32: Endpoint hardening test

**Files:** Modify `tests/test_admin_api_ohlcv.py`

- [ ] **Step 1: Append**

```python
def test_ohlcv_bad_bars_param_falls_back(client, monkeypatch):
    monkeypatch.setattr("swingbot.admin.app._ohlcv_frame", lambda t: _fake_df())
    assert len(client.get("/api/ohlcv/AAPL?bars=banana").get_json()["bars"]) == 260


def test_ohlcv_fetch_failure_uses_cache(client, monkeypatch, tmp_path):
    """Live fetch raising must fall through to the CSV cache."""
    import swingbot.admin.app as admin_app
    from swingbot import config as cfg
    cache = tmp_path / "backtest_cache"; cache.mkdir()
    _fake_df(60).rename_axis("Date").to_csv(cache / "ZZZZ.csv")
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr("swingbot.core.data.get_daily_data",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("net down")))
    data = client.get("/api/ohlcv/ZZZZ").get_json()
    assert len(data["bars"]) == 60
```

- [ ] **Step 2: Run + commit** `test: ohlcv endpoint hardening (bad params, cache fallback)`

---

# Phase 4 — Wrap-up (U33–U36)

### Task U33: Cross-page consistency audit

**Files:** Modify `style.css` / templates as found

- [ ] **Step 1:** With the server running, walk all 7 pages against this checklist and fix inline: (a) zero raw hex colors left in templates (`grep -n "#[0-9a-fA-F]\{6\}" swingbot/admin/templates/*.html` — inline styles must use tokens or move to style.css); (b) every numeric cell has `num`; (c) all buttons use the U5 hierarchy; (d) `grep -cn "var(--" swingbot/admin/static/style.css` should dominate — any remaining raw hex in style.css gets converted or gets a comment explaining why not.
- [ ] **Step 2: Verify + commit** `fix: cross-page token consistency audit`

### Task U34: Cockpit-v3 deviation note

**Files:** Modify `docs/superpowers/plans/2026-07-11-cockpit-v3.md` (Part 3 intro, after the "Notes on assumptions" block)

- [ ] **Step 1:** Add:

```markdown
> **Deviation note (2026-07-19, admin-ui-tradingview-redesign):** the admin UI now
> uses a design-token layer (`static/tokens.css`) + component classes (`card`,
> `tile`, `pill`, `btn`, `num`, `toolbar` — see that plan). Part 3 tasks whose
> verbatim snippets carry raw hex colors or ad-hoc classes should be adapted to
> the tokens/components at execution time; template inheritance via base.html
> already applies the theme to any new page automatically. lightweight-charts
> 4.2.3 is vendored at `static/vendor/lightweight-charts/` and `SwingChart.mount`
> is available for any Part 3 page needing an interactive chart.
```

- [ ] **Step 2: Commit** `docs: cockpit-v3 deviation note for UI redesign`

### Task U35: README section

**Files:** Modify `README.md` (after the "Analytics core" section)

- [ ] **Step 1:** Add an "## Admin UI" section documenting: the token layer (`tokens.css` as the palette source of truth, mirrored by `chart_style.THEME` with a sync test), self-hosted Inter + vendored lightweight-charts 4.2.3 (no runtime CDN), the `/api/ohlcv/<ticker>?bars=&trade_id=` endpoint (authed, read-only, cache-fallback, 1000-bar cap), and the interactive chart surfaces (trade detail + dashboard modal). Match the README's existing voice (short paragraphs + one table max).
- [ ] **Step 2: Commit** `docs: admin UI redesign section`

### Task U36: Final checkpoint

- [ ] **Step 1:** `python -m pytest tests/ -q` — full suite green; py_compile loop clean; `grep -rn "googleapis\|unpkg.com\|cdn\." swingbot/admin/templates/` → no matches (vendor files are local).
- [ ] **Step 2:** Manual QA pass: all 7 pages at desktop + 380px, one interactive chart with levels, one Discord-style PNG regenerated and eyeballed side-by-side with an old one.
- [ ] **Step 3:** Update this plan's Progress block (`Completed: U1–U36`), empty checkpoint commit `chore: ui-tradingview redesign checkpoint — all tasks complete`.

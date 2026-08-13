# Dashboard Table Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drop the Dashboard's Open Trades table from 18 columns to 8 and Trade History from 16 to 8 by default, behind a per-table `[Compact | Full]` toggle that defaults to Compact.

**Architecture:** The server keeps rendering every column. Density is a CSS class (`density-compact`) on each table's wrapper; full-only cells carry `col-full` and compact-only cells carry `col-compact`, and CSS shows one set or the other. Nothing is removed from the DOM, so column indices — which `ctColIndex()`, `colIndexById()` and `reorderTableColumns()` all depend on — stay stable.

**Tech Stack:** Jinja2 templates, vanilla ES5-style JS (no build step, no framework), plain CSS, pytest + Flask test client.

**Spec:** `docs/superpowers/specs/2026-08-07-v8-dashboard-table-simplification-design.md`

## Global Constraints

- **No new dependencies.** No build step, no framework. Match the file's existing ES5-flavoured style (`var`, `function`, no arrow functions in the table scripts).
- **Compact is the default.** A browser with no stored preference renders compact.
- **Independent state per table:** `ot_density` and `ct_density` in `localStorage`, values `'compact'` / `'full'`, defaulting to `'compact'` — mirroring how `ct_per_page` defaults to `'10'`.
- **Every column keeps rendering server-side in both densities.** No Jinja conditional may omit a cell.
- **Cell-count invariant (Open Trades only):** `reorderTableColumns()` in `dashboard_fragment.html` bails out unless every row has exactly as many cells as the header has `<th>`s. Any new column needs a `<th>` *and* a `<td>` on every trade row, and the `.ot-leg-row` colspan must be bumped to match.
- **Leg rows stay excluded from pagination.** `.ot-leg-row` / `.ct-leg-row` behaviour from commit `32afe78` must not regress.
- Files touched: `swingbot/admin/templates/dashboard_fragment.html`, `swingbot/admin/static/style.css`, `tests/admin/test_dashboard_v2.py`. Nothing else.

## File Structure

| File | Responsibility for this change |
|---|---|
| `swingbot/admin/static/style.css` | The two density rules (`.density-compact .col-full { display:none }`, `.density-full .col-compact { display:none }`) and the toggle control's styling. |
| `swingbot/admin/templates/dashboard_fragment.html` | `col-full` / `col-compact` markers on both tables' `<th>`/`<td>`; the new Open Trades `Plan` column; the compact direction glyph in both ticker cells; the two toggle controls and their persistence + re-apply hooks. |
| `tests/admin/test_dashboard_v2.py` | Markup-contract regression tests. |

## Column reference (from the spec)

**Open Trades — compact keeps 8:** `rownum`, `status` (renders as *Prog*), `ticker`, `pnl`, `current_price`, `plan` (NEW), `days`, `action`.
**Open Trades — `col-full` (11):** `strategy`, `horizon`, `direction`, `confidence`, `score`, `entry`, `stop`, `target`, `rr`, `size`, `opened`.
Physical columns go 18 → 19.

**Trade History — compact keeps 8:** row-number, `outcome`, `ticker`, `gainloss`, `r`, `days`, `closed`, actions.
**Trade History — `col-full` (8):** `strategy`, `horizon`, `dir`, `conf`, `entry`, `exit`, `pnlpct`, `opened`.
Physical columns stay 16 — no new columns, so the `.ct-leg-row` colspan is unchanged.

---

### Task 1: Trade History density toggle

Trade History first because it needs **no new columns** — it proves the whole mechanism (CSS, toggle, persistence, refresh re-apply) against the simpler table.

**Files:**
- Modify: `swingbot/admin/static/style.css` (append density rules)
- Modify: `swingbot/admin/templates/dashboard_fragment.html` (Trade History table + its toolbar + its `<script>`)
- Test: `tests/admin/test_dashboard_v2.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: the CSS contract `.density-compact .col-full { display: none }` / `.density-full .col-compact { display: none }`, and the wrapper-class convention `<div class="table-density density-compact" data-density-for="ct">`, both reused verbatim by Task 2.

- [ ] **Step 1: Write the failing tests** (append to `tests/admin/test_dashboard_v2.py`)

```python
def test_history_defaults_to_compact_density(client, auth, admin_app):
    """A browser with no stored preference must get the compact table."""
    from swingbot import config
    _seed_closed_pair_with_runner(config.DATA_DIR)
    html = client.get("/dashboard/fragment?mode=all", headers=auth).data.decode("utf-8")
    assert 'data-density-for="ct"' in html
    wrapper = html.split('data-density-for="ct"', 1)[0].rsplit("<div", 1)[1]
    assert "density-compact" in wrapper


def test_history_full_only_columns_are_marked(client, auth, admin_app):
    """The 8 analytical columns must carry col-full on BOTH th and td, or
    they will not hide together."""
    from swingbot import config
    _seed_closed_pair_with_runner(config.DATA_DIR)
    html = client.get("/dashboard/fragment?mode=all", headers=auth).data.decode("utf-8")
    table = html.split('id="closed-trades-table"', 1)[1].split("</table>", 1)[0]
    head, body = table.split("<tbody>", 1)
    for col in ("strategy", "horizon", "dir", "conf", "entry", "exit", "pnlpct", "opened"):
        th = [h for h in head.split("<th")[1:] if 'data-col-id="%s"' % col in h]
        assert th and "col-full" in th[0].split(">", 1)[0], "th %s missing col-full" % col
    # one col-full td per full-only column, per trade row (2 trades seeded)
    assert body.count("col-full") == 8 * 2


def test_history_still_renders_every_column_server_side(client, auth, admin_app):
    """Density is presentational -- nothing may be dropped server-side."""
    import re
    from swingbot import config
    _seed_closed_pair_with_runner(config.DATA_DIR)
    html = client.get("/dashboard/fragment?mode=all", headers=auth).data.decode("utf-8")
    table = html.split('id="closed-trades-table"', 1)[1].split("</table>", 1)[0]
    # NB: count "<th " / "<th>" -- a bare "<th" also matches "<thead>".
    assert len(re.findall(r"<th[ >]", table)) == 16, "all 16 columns must still render"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/admin/test_dashboard_v2.py -k density -p no:warnings -q`
Expected: FAIL — `data-density-for="ct"` is not in the markup yet.

- [ ] **Step 3: Add the density CSS** (append to `swingbot/admin/static/style.css`)

```css
/* ── Table density (Compact | Full) ──────────────────────────────────────
   The server always renders every column; these two rules decide which set
   is on screen. Hiding rather than removing keeps column indices stable for
   sortClosedTable/sortByHeader and reorderTableColumns, all of which resolve
   a column by its position among thead th. */
.density-compact .col-full { display: none; }
.density-full .col-compact { display: none; }

.density-toggle { display: inline-flex; border: 1px solid #1f2330; border-radius: 6px; overflow: hidden; }
.density-toggle button {
  background: #13161d; color: #8b93a7; border: 0; padding: 4px 10px;
  font-size: 12px; font-family: inherit; cursor: pointer;
}
.density-toggle button.active { background: #232838; color: #dde1ea; }
```

- [ ] **Step 4: Mark the Trade History full-only columns**

In the `#closed-trades-table` `<thead>`, add `class="col-full"` to the 8 `<th>`s whose `data-col-id` is one of `strategy`, `horizon`, `dir`, `conf`, `entry`, `exit`, `pnlpct`, `opened`. Where a `<th>` already has a `class` (e.g. `class="num"`), append: `class="num col-full"`.

In the `<tbody>` row, add `col-full` to the matching 8 `<td>`s in the same order. The `dir` cell is the one rendering `▲`/`▼`; the `pnlpct` cell is the one whose `data-sort` is `c_pnl`.

Then add the compact-only direction glyph inside the ticker `<td>`, immediately after the ticker `<strong>…</strong>`:

```html
        <span class="col-compact" title="{{ 'Long (bullish)' if t.direction == 'bullish' else 'Short (bearish)' }}"
              style="color:{{ '#6dda9e' if t.direction == 'bullish' else '#da6d6d' }};font-size:11px;font-weight:600;">{{ '▲' if t.direction == 'bullish' else '▼' }}</span>
```

Carry `pnl%` onto the Gain/Loss cell so it survives in compact — append to that `<td>`'s existing `title`:
` · {{ '%+.2f%%'|format(c_pnl) if c_pnl is not none else '—' }} vs entry`

- [ ] **Step 5: Wrap the table and add the toggle control**

Wrap the existing `<div class="table-wrap">` (or the table itself) for Trade History in:

```html
<div class="table-density density-compact" data-density-for="ct">
```

…closing it after the table's pagination bar. Then, in the Trade History toolbar next to the `ct-per-page` selector, add:

```html
      <span class="density-toggle" id="ct-density-toggle">
        <button type="button" data-density="compact">Compact</button>
        <button type="button" data-density="full">Full</button>
      </span>
```

- [ ] **Step 6: Wire persistence** — inside the Trade History IIFE, next to the `STORAGE_KEY` declarations

```javascript
    // Density: compact by default, per-table, same localStorage pattern as
    // ct_per_page. The class lives on a wrapper rather than the table so a
    // morphdom patch of the table itself can't drop it.
    var DENSITY_KEY = 'ct_density';
    var density = localStorage.getItem(DENSITY_KEY) || 'compact';

    function applyDensity() {
      var wrap = document.querySelector('[data-density-for="ct"]');
      if (!wrap) return;
      wrap.classList.toggle('density-compact', density === 'compact');
      wrap.classList.toggle('density-full', density === 'full');
      var btns = document.querySelectorAll('#ct-density-toggle button');
      for (var i = 0; i < btns.length; i++) {
        btns[i].classList.toggle('active', btns[i].dataset.density === density);
      }
    }

    document.querySelectorAll('#ct-density-toggle button').forEach(function(b) {
      b.addEventListener('click', function() {
        density = this.dataset.density;
        localStorage.setItem(DENSITY_KEY, density);
        applyDensity();
      });
    });
```

Then call `applyDensity();` inside `window.refreshClosedTradesTable`, immediately before `render();` — morphdom may revert a class it did not render, so it must be re-applied on every refresh, not just at load.

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/admin/test_dashboard_v2.py -p no:warnings -q`
Expected: PASS, including the pre-existing leg-row tests.

- [ ] **Step 8: Commit**

```bash
git add swingbot/admin/static/style.css swingbot/admin/templates/dashboard_fragment.html tests/admin/test_dashboard_v2.py
git commit -m "feat(admin): compact/full density toggle on Trade History"
```

---

### Task 2: Open Trades density + the Plan column

**Files:**
- Modify: `swingbot/admin/templates/dashboard_fragment.html` (Open Trades table + toolbar + its `<script>`)
- Test: `tests/admin/test_dashboard_v2.py`

**Interfaces:**
- Consumes: the CSS rules and the `data-density-for` wrapper convention from Task 1 — reuse them exactly, do not add new CSS.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Write the failing tests** (append to `tests/admin/test_dashboard_v2.py`)

```python
def _seed_open_trade_with_runner(data_dir):
    trades = [{
        "id": "o1", "ticker": "AAPL", "status": "open", "direction": "bullish",
        "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
        "opened_at": "2026-07-01T00:00:00+00:00", "confidence_level": 3,
        "confidence_score": 60, "strategy": "RSI", "horizon_key": "4w",
        "legs": [{"fraction": 0.5, "exit_price": 104.0, "r": 0.4},
                 {"fraction": 0.5, "exit_price": None, "r": None}],
    }]
    with open(os.path.join(data_dir, "trades.json"), "w") as f:
        json.dump(trades, f)


def test_open_trades_cell_count_matches_header(client, auth, admin_app):
    """reorderTableColumns() bails out unless every trade row has exactly as
    many cells as the header has columns -- adding Plan must not break it."""
    import re
    from swingbot import config
    _seed_open_trade_with_runner(config.DATA_DIR)
    html = client.get("/dashboard/fragment", headers=auth).data.decode("utf-8")
    table = html.split('id="trades-table"', 1)[1].split("</table>", 1)[0]
    head, body = table.split("<tbody>", 1)
    # NB: count "<th " / "<th>" -- a bare "<th" also matches "<thead>".
    n_cols = len(re.findall(r"<th[ >]", head))
    assert n_cols == 19, "18 original columns + Plan"
    trade_row = [r for r in body.split("<tr")[1:] if "ot-leg-row" not in r.split(">", 1)[0]][0]
    assert trade_row.count("<td") == n_cols


def test_open_trades_leg_row_colspan_covers_every_column(client, auth, admin_app):
    from swingbot import config
    _seed_open_trade_with_runner(config.DATA_DIR)
    html = client.get("/dashboard/fragment", headers=auth).data.decode("utf-8")
    table = html.split('id="trades-table"', 1)[1].split("</table>", 1)[0]
    leg = [r for r in table.split("<tr")[1:] if "ot-leg-row" in r.split(">", 1)[0]][0]
    assert 'colspan="17"' in leg, "2 empty td + colspan 17 == 19 columns"


def test_open_trades_defaults_to_compact_density(client, auth, admin_app):
    from swingbot import config
    _seed_open_trade_with_runner(config.DATA_DIR)
    html = client.get("/dashboard/fragment", headers=auth).data.decode("utf-8")
    assert 'data-density-for="ot"' in html
    wrapper = html.split('data-density-for="ot"', 1)[0].rsplit("<div", 1)[1]
    assert "density-compact" in wrapper


def test_open_trades_full_only_columns_are_marked(client, auth, admin_app):
    from swingbot import config
    _seed_open_trade_with_runner(config.DATA_DIR)
    html = client.get("/dashboard/fragment", headers=auth).data.decode("utf-8")
    table = html.split('id="trades-table"', 1)[1].split("</table>", 1)[0]
    head, body = table.split("<tbody>", 1)
    for col in ("strategy", "horizon", "direction", "confidence", "score",
                "entry", "stop", "target", "rr", "size", "opened"):
        th = [h for h in head.split("<th")[1:] if 'data-col-id="%s"' % col in h]
        assert th and "col-full" in th[0].split(">", 1)[0], "th %s missing col-full" % col
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/admin/test_dashboard_v2.py -k open_trades -p no:warnings -q`
Expected: FAIL — header count is 18, not 19.

- [ ] **Step 3: Add the Plan column**

In the `#trades-table` `<thead>`, immediately after the `pnl` `<th>`, add:

```html
      <th data-col-id="plan" draggable="true" class="num col-compact" title="Entry → Target / Stop">Plan <span class="sort-arrow" data-col-id="plan"></span></th>
```

Note: no `onclick="sortByHeader(this)"` — Plan is a composite cell with no single sortable value, and `sortByHeader` would compare its rendered text. Sorting by entry/stop/target remains available in Full.

In the `<tbody>` row, at the matching position (immediately after the `pnl` `<td>`), add:

```html
      <td class="num col-compact" style="font-size:11px;white-space:nowrap;"
          title="Entry {{ '%.2f'|format(t.entry) }} · Target {{ '%.2f'|format(t.take_profit) }} · Stop {{ '%.2f'|format(t.stop_loss) }}">
        <span class="muted">{{ '%.2f'|format(t.entry) }}</span>→<span style="color:#6dda9e;">{{ '%.2f'|format(t.take_profit) }}</span>/<span style="color:#da6d6d;">{{ '%.2f'|format(t.stop_loss) }}</span>
      </td>
```

- [ ] **Step 4: Bump the leg-row colspan**

In the `.ot-leg-row` block, change `<td colspan="16"` to `<td colspan="17"` (2 empty `<td>`s + 17 = 19 columns).

- [ ] **Step 5: Mark the 11 full-only columns and add the compact glyph**

Add `col-full` to the `<th>` and matching `<td>` for each of `strategy`, `horizon`, `direction`, `confidence`, `score`, `entry`, `stop`, `target`, `rr`, `size`, `opened` — appending to any existing class (`class="num"` → `class="num col-full"`).

Carry the unrealised amount onto the P&L cell so it survives in compact (the
`size` / "Unreal. P&L" column is hidden there) — append to the `pnl` `<td>`'s
existing `title`:
` · Unrealized {{ '%+.2f'|format(unreal_amt) }} {{ cur_map.get(t.ticker, '') }}` ,
guarded with `{% if unreal_amt is not none %}`.

Add the compact direction glyph inside the ticker `<td>`, after the ticker `<strong>…</strong>`, identical in shape to Task 1's:

```html
        <span class="col-compact" title="{{ 'Long (bullish)' if is_bull else 'Short (bearish)' }}"
              style="color:{{ '#6dda9e' if is_bull else '#da6d6d' }};font-size:11px;font-weight:600;">{{ '▲' if is_bull else '▼' }}</span>
```

- [ ] **Step 6: Wrap the table, add the toggle, wire persistence**

Wrap the Open Trades table + its pagination bar in:

```html
<div class="table-density density-compact" data-density-for="ot">
```

Add to the Open Trades toolbar, next to `ot-per-page`:

```html
      <span class="density-toggle" id="ot-density-toggle">
        <button type="button" data-density="compact">Compact</button>
        <button type="button" data-density="full">Full</button>
      </span>
```

In the Open Trades `<script>` block (the one holding `otRefreshRows`), add:

```javascript
  var OT_DENSITY_KEY = 'ot_density';
  var otDensity = localStorage.getItem(OT_DENSITY_KEY) || 'compact';

  function otApplyDensity() {
    var wrap = document.querySelector('[data-density-for="ot"]');
    if (!wrap) return;
    wrap.classList.toggle('density-compact', otDensity === 'compact');
    wrap.classList.toggle('density-full', otDensity === 'full');
    var btns = document.querySelectorAll('#ot-density-toggle button');
    for (var i = 0; i < btns.length; i++) {
      btns[i].classList.toggle('active', btns[i].dataset.density === otDensity);
    }
  }

  document.querySelectorAll('#ot-density-toggle button').forEach(function(b) {
    b.addEventListener('click', function() {
      otDensity = this.dataset.density;
      localStorage.setItem(OT_DENSITY_KEY, otDensity);
      otApplyDensity();
    });
  });
```

Call `otApplyDensity();` inside `window.refreshOpenTradesTable`, immediately before `otRender();`.

- [ ] **Step 7: Run the affected tests**

Run: `python -m pytest tests/admin/test_dashboard_v2.py -p no:warnings -q`
Expected: PASS, including every leg-row test from `32afe78`.

- [ ] **Step 8: Full suite + syntax gate**

```bash
python -m pytest tests/ -q
python -m py_compile bot.py admin_ui.py
```

Expected: `1 failed, 1011 passed` — the one failure being the pre-existing
`tests/test_trade_monitor_wiring.py::test_flag_on_polls_open_plans`
wall-clock failure documented in CLAUDE.md. Any other failure is yours.

- [ ] **Step 9: Commit**

```bash
git add swingbot/admin/templates/dashboard_fragment.html tests/admin/test_dashboard_v2.py
git commit -m "feat(admin): compact/full density toggle on Open Trades"
```

---

## Manual verification (no JS test runner in this repo)

The class-swap itself has no automated coverage. After Task 2, in a browser:

1. Load `/dashboard` with cleared localStorage → both tables render 8 columns.
2. Click **Full** on each → all 19 / 16 columns appear; reload → the choice sticks.
3. In Compact, sort by a visible column, then toggle to Full → sort survives.
4. Wait for one auto-refresh cycle → density must NOT snap back to compact.
5. On Open Trades in Full, drag a column header → reordering still works (this is the `reorderTableColumns` cell-count invariant in practice).
6. With a scaled-out trade present, confirm its runner row still sits directly under its parent in both densities.

## Considered and rejected

**Reusing the existing drag-to-reorder persistence for per-column show/hide.**
Open Trades already stores a user column order under
`swingbot_dashboard_column_order`, so per-column visibility checkboxes would
be a natural extension. Rejected because it gives the operator a
configuration task rather than a good default — the spec's goal is a curated
8-column view that is right on first load, which a checkbox list does not
provide. The density toggle is also strictly simpler to reason about.

**Note for existing users:** `applyColumnOrder()` appends column ids it does
not recognise to the end of the saved order, so anyone with a stored column
order will find `Plan` at the far right until they drag it. This is graceful,
not a bug, and needs no migration.

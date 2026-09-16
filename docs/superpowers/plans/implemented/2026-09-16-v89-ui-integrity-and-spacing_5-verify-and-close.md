# v89 Admin UI Integrity and Spacing — Part 5: verify, deploy, map, close

> Header, global constraints, parallelisation and the task index live in `2026-09-16-v89-ui-integrity-and-spacing_0-index.md`. Every task here implicitly includes that file's Global Constraints.

# Phase 5 — Verification (worktree), then main

### Task UA14: Gap audit script, empty the pending list, full suites, merge

**Files:**
- Create: `scripts/dev/ui_spacing_audit.js`
- Modify: `frontend/src/app/ui/spacing.spec.ts` (delete `PENDING_MARGIN_RULES`)

**Interfaces:**
- Consumes: every earlier task.
- Produces:
  - `scripts/dev/ui_spacing_audit.js`, a self-contained function body. Pasted into a browser console on any admin page (or passed to Playwright's `browser_evaluate`), it returns `{ expected, checked, offenders: string[] }`.
  - The merged branch on `main`.

- [ ] **Step 1: Write the audit script**

Create `scripts/dev/ui_spacing_audit.js`:

```js
// v89 spec §4.3 -- measures the gap between sibling panels on the current admin
// page. Paste into the browser console (or Playwright browser_evaluate as
// `() => { ...this file... }`). Needs no credentials: it reads the page you are on.
//
// Every visible child of a stacking container is compared with its nearest
// neighbour below (same column) and to its right (same row). Any gap that is
// not the computed --section-gap is an offender. Zero-height and
// display:contents children are skipped, which is what those hosts are for.
(() => {
  const root = getComputedStyle(document.documentElement);
  const expected = parseFloat(root.getPropertyValue('--section-gap')) ||
    parseFloat(getComputedStyle(document.body).getPropertyValue('--section-gap'));
  const containers = [
    ...document.querySelectorAll('.workspace-content > :not(router-outlet)'),
    ...document.querySelectorAll('.sb-stack, .sb-row, .panels, .chart-grid, .bottom-row, .split'),
  ];
  const visibleChildren = (el) => [...el.children].flatMap((c) => {
    const style = getComputedStyle(c);
    if (style.display === 'contents') return visibleChildren(c);
    const r = c.getBoundingClientRect();
    return style.display === 'none' || r.height < 1 || r.width < 1 ? [] : [{ el: c, r }];
  });
  const name = (el) => el.tagName.toLowerCase() + (el.classList.length ? '.' + [...el.classList].join('.') : '');
  const offenders = [];
  let checked = 0;
  for (const container of new Set(containers)) {
    const kids = visibleChildren(container);
    for (const a of kids) {
      let below = null;
      let right = null;
      for (const b of kids) {
        if (a === b) continue;
        const hOverlap = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left);
        const vOverlap = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
        const dy = b.r.top - a.r.bottom;
        const dx = b.r.left - a.r.right;
        if (hOverlap > 40 && dy >= -1 && (below === null || dy < below.gap)) below = { b, gap: dy };
        if (vOverlap > 20 && dx >= -1 && (right === null || dx < right.gap)) right = { b, gap: dx };
      }
      for (const [dir, hit] of [['below', below], ['right', right]]) {
        if (!hit) continue;
        checked += 1;
        if (Math.abs(hit.gap - expected) > 1) {
          offenders.push(`${name(container)}: ${name(a.el)} -> ${dir} ${name(hit.b.el)} = ${Math.round(hit.gap)}px`);
        }
      }
    }
  }
  return { path: location.pathname, width: innerWidth, expected, checked, offenders };
})();
```

- [ ] **Step 2: Delete the pending list**

In `frontend/src/app/ui/spacing.spec.ts`, confirm `PENDING_MARGIN_RULES` is now `new Set<string>([])`. If any entry remains, its owning task did not finish: stop and finish that task. Otherwise delete the constant, and change the offender check line to:

```ts
          offenders.push(`${path}|${selector}`);
```

Update the constant's doc comment reference in the `describe` above it, if any.

Run: `npm --prefix frontend test -- --include src/app/ui/spacing.spec.ts` → PASS.

- [ ] **Step 3: Commit**

```bash
git add scripts/dev/ui_spacing_audit.js frontend/src/app/ui/spacing.spec.ts
git commit -m "test(v89): gap audit script; the panel-margin guard has no pending exceptions left"
```

- [ ] **Step 4: Full Python suite, once**

Dispatch the `test-runner` subagent (or run `python scripts/dev/testrun.py full`) over the worktree.
Expected: `0 failed`, `0 xfailed`. If not green, fix forward from the named failures. They are this plan's regressions.

- [ ] **Step 5: Full frontend suite and production build, once**

Run: `npm --prefix frontend test`
Expected: every spec file passes.
Run: `npm --prefix frontend run build -- --configuration production`
Expected: build succeeds, with no budget **error**. A budget warning is recorded in the merge commit body, not ignored.

- [ ] **Step 6: Merge**

Use `superpowers:finishing-a-development-branch`. Before merging, follow the stale-checkout rule:
- `git -C <repo root> fetch origin`
- `git -C <repo root> rev-list --left-right --count main...origin/main`

If `main` is behind, fast-forward it first. Merge the branch into `main` with a merge commit (`Merge branch '2026-09-16-v89-ui-integrity-and-spacing'`), matching recent history.

**Do not re-run either suite after a conflict-free merge.** If the merge resolved conflicts, run each touched suite once more.

Do **not** delete the branch or remove the worktree yet; UA16 may need it.

---

### Task UA15: Deploy and live audit

**Files:** none (production verification). Findings that need a code change become a fix commit on `main` referencing `v89`.

- [ ] **Step 1: Ask the partner to approve the deploy**

Pushing `main` triggers the GitHub Actions deploy to the Hetzner VM (`docs/deploy/DEPLOY_HETZNER.md`). This is outward-facing: ask, in one message, whether to push now. Do not push without an explicit yes.

- [ ] **Step 2: Push and watch the deploy**

After approval: `git -C <repo root> push origin main`. Then `gh run watch` on the deploy workflow run for that commit, until it completes. If it fails, stop and report the failing job's log excerpt.

- [ ] **Step 3: Live audit at 1440 and 390**

With Playwright, open `https://bomeo-capital.com/` and have the partner sign in in that browser window. Never type credentials yourself.

For each of `/dashboard`, `/watchlist`, `/risk`, `/trades`, one `/trades/<id>` (click the first row), `/calendar`, `/analytics` (with Breakdowns opened), `/system` and `/versions`:
1. `browser_resize` 1440×1800 and navigate.
2. Wait for no "Loading" text.
3. `browser_evaluate` with the contents of `scripts/dev/ui_spacing_audit.js`.

Repeat the loop at 390×1500.

Record per page: `checked`, and `offenders` (expected: `[]`; `expected` is 20 at 1440 and 14 at 390).

For each offender, fix it on `main` (a new selector owning a margin, or a missed `sb-async` wrapper), commit `fix(v89): …`, and re-run the audit on that page after the next deploy. The partner approves each push again, per Step 1.

- [ ] **Step 4: Live integrity checks**

In the same logged-in browser, `browser_evaluate`:

```js
async () => {
  const get = async (u) => (await fetch(u, { credentials: 'include' })).json();
  const dash = await get('/api/v1/dashboard?mode=all');
  const perf = await get('/api/v1/analytics/performance');
  const eq = await get('/api/v1/analytics/exit-quality');
  const trades = await get('/api/v1/trades?status=open&per_page=5');
  const risk = await get('/api/v1/risk');
  return {
    risk_metrics_as_of: risk.metrics?.as_of ?? null,
    dashboard: { expectancy_r: dash.expectancy_r, expectancy_n: dash.expectancy_n, win_rate: dash.win_rate, win_rate_n: dash.win_rate_n },
    overall: { expectancy_r: perf.expectancy_r, derived: perf.derived.expectancy_r, win_rate: perf.win_rate, derived_wr: perf.derived.win_rate },
    returns: { total: perf.derived.total_return_pct, annualised: perf.derived.annualised_return_pct, months: perf.calendar },
    unmapped: eq.unmapped_reasons,
    prices_as_of: trades.prices_as_of,
  };
}
```

Pass criteria:
- `dashboard.expectancy_r` equals `overall.expectancy_r` equals `overall.derived` to 3 dp. Pre-v89 production read −0.030R against −0.142R.
- `returns.total` is within a few tenths of a percent of the Analytics `Total P&L` ÷ base balance, not −94%.
- No month in `returns.months` below −5% unless the calendar P&L for that month really is that large relative to the balance.
- `prices_as_of` is non-null during market hours with open positions.
- `risk_metrics_as_of` is non-null. Risk › Risk metrics and Correlation matrix read "age unknown" on 2026-09-16 because this is null (spec §3.10).
  - If it is still null: find where `swingbot/admin/api_v1/risk.py` builds `metrics`, trace why `as_of` is absent (no daily-bar date reached it), and fix it on `main` with a failing test first in `tests/admin/test_api_v1_risk.py` asserting `metrics.as_of` is the latest daily-bar date when positions exist.
  - Commit it as `fix(v89): risk metrics carry their bar date`, and deploy with approval.

Copy `unmapped` verbatim into the UA16 commit body.

Take one screenshot each of Analytics › By month and By horizon (1440) into `.playwright-mcp/audit/v89-after-*.jpg`, and confirm visually that losses draw left of the zero axis in red.

---

### Task UA16: Map production's unmapped close reasons, by exact match

**Files:**
- Modify: `swingbot/core/analytics/metrics.py` (`EXIT_REASONS` block; `_exit_reason_bucket`)
- Test: `tests/analytics/test_metrics_exit_reasons.py`

**Interfaces:**
- Consumes: UA15 Step 4's `unmapped` list (production data).
- Produces: `_EXIT_REASON_ALIASES: dict[str, str]`, where the key is the exact lowercased close-reason text and the value is an `EXIT_REASONS` member.

Work on a new branch from `main` (`2026-09-16-v89-exit-reason-aliases`) in the existing v89 worktree, or directly on `main` if the partner prefers for a one-file change. Ask once, in one message.

- [ ] **Step 1: Classify each production string**

Build a table from UA15's `unmapped` rows: `text | status | n | bucket | why`.

Assign a bucket **only** when the text's meaning is unambiguous:
- **It names the exit mechanism outright**, e.g. a text that says the stop was hit → `stop`; a text that says take-profit 1 filled → `tp1`.
- **The code that writes it says so.** Confirm by finding the writer: `git grep -n -F "<the text>" -- swingbot`, and read the `close_reason=`/`reason=` assignment around it. Cite that `file:line` in the `why` column.

A text whose writer cannot be found, or that could mean two buckets (for example a bare `"closed"`), stays unmapped. `""` (no reason recorded) always stays `other`. Never map by substring.

Commit the table into the spec as a new `§3.5a Production close reasons (UA16)` section, before writing code.

- [ ] **Step 2: Write the failing test from the real strings**

Append to `tests/analytics/test_metrics_exit_reasons.py`, with one `pytest.param` per row mapped in Step 1, using the exact production text:

```python
@pytest.mark.parametrize(("text", "status", "bucket"), [
    # One row per string mapped in spec §3.5a, copied verbatim from production's
    # /analytics/exit-quality unmapped_reasons on the UA15 date.
    pytest.param("<exact text from §3.5a row 1>", "<status>", "<bucket>", id="row-1"),
])
def test_production_close_reasons_map_by_exact_text(text, status, bucket):
    trade = {"status": status, "close_reason": text, "entry": 100.0, "stop_loss": 99.0,
             "direction": "bullish", "exit_price": 100.0}
    assert metrics._exit_reason_bucket(trade) == bucket


def test_an_unlisted_text_that_merely_contains_a_mapped_word_is_still_other():
    # Exact match only (metrics._exit_reason_bucket docstring): a substring rule
    # is how a table like this starts lying.
    trade = {"status": "win", "close_reason": "not a stop at all", "entry": 100.0,
             "stop_loss": 99.0, "direction": "bullish", "exit_price": 101.0}
    assert metrics._exit_reason_bucket(trade) == "other"
```

The angle-bracket values are filled from §3.5a's table in this same step. The committed test must contain only real strings.

Run: `python scripts/dev/testrun.py file tests/analytics/test_metrics_exit_reasons.py` → FAIL on every mapped row.

- [ ] **Step 3: Implement**

In `metrics.py`, directly after `_RUNNER_SUBSTRINGS`:

```python
#: Exact production close-reason texts (lowercased) that name an EXIT_REASONS
#: bucket unambiguously -- spec v89 §3.5a, each traced to the code that writes
#: it. Exact keys only; never a substring. A text not listed here stays "other",
#: which `unmapped_exit_reasons` keeps reporting.
_EXIT_REASON_ALIASES: dict[str, str] = {
    # "<text>": "<bucket>",   # <writer file:line>
}
```

Populate it with Step 1's mapped rows, one per line, each with its writer `file:line` comment. In `_exit_reason_bucket`, directly after the `if text in _EXIT_REASON_SET: return text` check, add:

```python
    alias = _EXIT_REASON_ALIASES.get(text)
    if alias is not None:
        return alias
```

Run the test file → PASS.

- [ ] **Step 4: Commit, merge and deploy**

```bash
git add swingbot/core/analytics/metrics.py tests/analytics/test_metrics_exit_reasons.py docs/superpowers/specs/2026-09-16-v89-ui-integrity-and-spacing-design.md
git commit -m "fix(v89): map production close reasons to exit buckets by exact text"
```

Put UA15's `unmapped` list in the commit body.
- If this was on a branch: run `python scripts/dev/testrun.py fast` (the change is one module), merge as in UA14 Step 6, and deploy with the partner's approval as in UA15 Steps 1–2.
- After the deploy, re-run UA15 Step 4's `unmapped` read. Record the new "other" share in the close-out.

---

### Task UA17: Close-out

**Files:**
- Modify: `VERSION.json`, `swingbot/admin/version_history.json` (regenerated)
- Move: the spec and all six plan files to `implemented/`
- Modify: `.codex/AGENTS.md`, only if the spacing rule should reach Codex (see Step 3)

- [ ] **Step 1: Bump the ui line**

Read `VERSION.json` from disk. Increment `ui` at **patch** level, leave `bot` untouched, and set `ui_updated` to now in `YYYY-MM-DD HH-MM-SS`. Then run `python scripts/dev/build_version_matrix.py` and stage its output. Commit both together:

```bash
git add VERSION.json swingbot/admin/version_history.json
git commit -m "chore(v89): ui patch release -- admin UI integrity and one spacing rule"
```

If the observed impact came out larger or smaller than a patch, amend the spec's `Bump:` line in this commit with one clause saying why (`document-conventions.md`, "The header block").

- [ ] **Step 2: Record the rule where the next UI session will read it**

Add one row to the `CLAUDE.md` reference table only if `CLAUDE.md` stays under 200 lines. Otherwise add the paragraph to `docs/claude/architecture.md`, under its frontend section:

> **Spacing between panels (v89):** one token, `--section-gap`; workspaces stack panels in `.sb-stack`/host grids; panels never own outer margins. Enforced by `frontend/src/app/ui/spacing.spec.ts` and `frontend/src/app/workspaces/workspace-gaps.spec.ts`; measured live with `scripts/dev/ui_spacing_audit.js`.

- [ ] **Step 3: Codex mirror**

If Step 2 changed `CLAUDE.md` or `docs/claude/*.md`, add the same rule, condensed to one line, to `.codex/AGENTS.md`.

- [ ] **Step 4: Move the documents and remove the worktree**

```bash
git mv docs/superpowers/specs/2026-09-16-v89-ui-integrity-and-spacing-design.md docs/superpowers/specs/implemented/
git mv docs/superpowers/plans/2026-09-16-v89-ui-integrity-and-spacing_0-index.md docs/superpowers/plans/implemented/
git mv docs/superpowers/plans/2026-09-16-v89-ui-integrity-and-spacing_1-foundation.md docs/superpowers/plans/implemented/
git mv docs/superpowers/plans/2026-09-16-v89-ui-integrity-and-spacing_2-backend.md docs/superpowers/plans/implemented/
git mv docs/superpowers/plans/2026-09-16-v89-ui-integrity-and-spacing_3-workspaces.md docs/superpowers/plans/implemented/
git mv docs/superpowers/plans/2026-09-16-v89-ui-integrity-and-spacing_4-analytics.md docs/superpowers/plans/implemented/
git mv docs/superpowers/plans/2026-09-16-v89-ui-integrity-and-spacing_5-verify-and-close.md docs/superpowers/plans/implemented/
git commit -m "docs(v89): close out -- admin UI integrity and spacing implemented"
```

Remove the worktree per `docs/claude/document-lifecycle.md`. Delete the merged branch only after `git rev-list --count main..2026-09-16-v89-ui-integrity-and-spacing` prints `0` (`docs/claude/git-safety.md`).

- [ ] **Step 5: Hand over to spec 2**

Tell the partner: v89 is closed, the live audit result per page, and the post-UA16 "other" share. Say that the next item in the agreed order is spec 2 (phone layouts), to be brainstormed when they are ready. Then stop.

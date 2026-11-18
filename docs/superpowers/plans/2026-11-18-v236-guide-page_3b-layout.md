# v236 — Guide page, Part 3b: layout check and CI (V236-11, V236-11b, V236-12)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V236-11b" -A 200 <this file>`).

**Spec:** v215 — [2026-11-06-v215-guide-page.md](../specs/2026-11-06-v215-guide-page.md) (Plan A, frontend half: § Testing "Layout")
**Index:** [2026-11-18-v236-guide-page_0-index.md](2026-11-18-v236-guide-page_0-index.md) — Goal, `## Global Constraints`, `## Parallelisation`, the task ledger and `## Handoff` live there and bind every task below. Part 3 ([2026-11-18-v236-guide-page_3-chapters.md](2026-11-18-v236-guide-page_3-chapters.md)) holds V236-8..V236-10; these tasks moved here when that file passed the 1500-line cap.

DOM this part reads (V236-4/6/6b, do not change): `article.guide-chapter .md`; `nav.guide-rail` (≥ 1024, `position: sticky`), `button.guide-contents` + `sb-drawer` (640–1023), `sb-select.guide-picker` (< 640); `a.toc-chapter`, `a.toc-heading`, `a.permalink`, `a.guide-result`; `a.pipeline-link` (V236-9). Deep-link targets from V236-8/V236-10: `what-it-is#the-notice`, `glossary#r-multiple`.

---

# Phase 7 — Layout and CI

### Task V236-11: Layout check at three widths

**Model:** sonnet — a Playwright script on the `admin_browser_probe.py` pattern with unit-tested verdicts, then one run against a local admin.

**Files:**
- Create: `scripts/dev/guide_layout_check.py`
- Create: `tests/scripts/test_guide_layout_check.py` (suite `tooling`; no `suites.toml` edit)

Split at the 20 KB task cap: this task builds and unit-tests the check; **V236-11b** adds the guide to the layout audit's routes, runs both checks against a local admin and commits the result note.

**Interfaces:**
- Consumes: `LoginFailed`, `default_env_path()`, `load_credentials(env_path) -> (user, password)`, `_login(context, base, credentials)` from `scripts/ops/admin_browser_probe.py` (credentials never printed; Playwright imported lazily); the page DOM from V236-4/6/6b (part header); chapters and anchors from V236-8..V236-10 (`what-it-is#the-notice`, `glossary#r-multiple`).
- Produces (V236-11b runs it): `guide_layout_check.main(argv=None, *, runner=None, env_path=None) -> int` (0 clean, 1 problems, 2 cannot run); pure verdicts `expected_toc(width) -> "picker" | "drawer" | "rail"`, `toc_problems`, `overflow_problems`, `target_problems`, `deep_link_problems`, `render_report`; screenshots `logs/v236-layout/guide@<width>.png` (not committed).

What it checks at 390, 820 and 1440 px on `/insights/guide`, `/insights/guide/what-it-is`, `/insights/guide/glossary` and `/insights/guide/pipeline`: no sideways overflow of the document or the shell's `main` pane; the contents mode each width owns (picker < 640, drawer 640–1023 with the drawer listing the three chapters, sticky rail ≥ 1024); every guide control (buttons, selects, `summary`, TOC links, permalinks, search results, pipeline links) at least 44 px each way on 390 and 820, counting `.sb-hit`'s `::after`; and both deep links landing their heading in the top half of the viewport. Inline links inside prose are exempt from the 44 px rule, as in WCAG 2.5.8.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_guide_layout_check.py`:

```python
"""scripts/dev/guide_layout_check.py: the v236 guide layout check (V236-11).

Only the Playwright loop goes without a unit test; every verdict the result
note records comes from the pure functions pinned here.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))
import guide_layout_check as glc  # noqa: E402

USER, PASSWORD = "user-secret-1", "pw-secret-2"


def test_importing_the_check_does_not_import_playwright():
    assert "playwright" not in sys.modules


@pytest.mark.parametrize("width, mode", [
    (390, "picker"), (639, "picker"), (640, "drawer"), (820, "drawer"),
    (1023, "drawer"), (1024, "rail"), (1440, "rail")])
def test_expected_toc_follows_the_breakpoints(width, mode):
    assert glc.expected_toc(width) == mode


def test_toc_wants_its_own_mode_and_no_other():
    assert glc.toc_problems(820, {"drawer": True, "rail": False, "picker": False}) == []
    assert glc.toc_problems(390, {"picker": False, "rail": True, "drawer": False}) == [
        "390px: contents picker (sb-select.guide-picker) not shown",
        "390px: contents rail (nav.guide-rail) shown, expected only the picker"]


def test_overflow_allows_one_pixel_of_rounding():
    assert glc.overflow_problems(390, "glossary", 1.0) == []
    assert glc.overflow_problems(390, "glossary", 12.4) == ["390px glossary: page overflows sideways by 12px"]
    assert glc.overflow_problems(1440, "", 3) == ["1440px /: page overflows sideways by 3px"]


def test_targets_count_on_phone_and_tablet_only():
    targets = [{"name": "Contents", "w": 90.0, "h": 30.0}, {"name": "#", "w": 44.0, "h": 44.0}]
    assert glc.target_problems(820, "pipeline", targets) == ["820px pipeline: Contents hit area 90x30px < 44"]
    assert glc.target_problems(1440, "pipeline", targets) == []


def test_deep_link_must_land_in_the_top_half():
    assert glc.deep_link_problems(390, "glossary#r-multiple", 64.0) == []
    assert glc.deep_link_problems(390, "glossary#r-multiple", None) == [
        "390px glossary#r-multiple: heading not found"]
    assert glc.deep_link_problems(390, "glossary#r-multiple", 700.0) == [
        "390px glossary#r-multiple: heading at 700px, not scrolled into the top half"]
    assert glc.deep_link_problems(390, "x#y", -5.0)[0].endswith("not scrolled into the top half")


def test_report_lists_each_width_and_every_problem():
    text = glc.render_report([{"width": 390, "problems": []},
                              {"width": 820, "problems": ["820px pipeline: x"]}],
                             "http://localhost:1234", "2026-11-18")
    assert "| 390 | picker | 0 |" in text and "| 820 | drawer | 1 |" in text
    assert "FAIL: 1 problems." in text and "- 820px pipeline: x" in text


def _env(tmp_path: Path) -> Path:
    env = tmp_path / ".env"
    env.write_text(f"ADMIN_USERNAME={USER}\nADMIN_PASSWORD={PASSWORD}\n", encoding="utf-8")
    return env


def test_main_writes_the_note_exits_by_verdict_and_never_prints_credentials(tmp_path, capsys):
    report = tmp_path / "note.md"
    argv = ["--report", str(report), "--out", str(tmp_path / "shots")]
    seen = []

    def clean(args, credentials):
        seen.append(credentials)
        return [{"width": width, "problems": []} for width in glc.WIDTHS]

    assert glc.main(argv, runner=clean, env_path=_env(tmp_path)) == 0
    assert seen == [(USER, PASSWORD)]
    assert "PASS: no problems." in report.read_text(encoding="utf-8")

    def broken(args, credentials):
        return [{"width": 390, "problems": ["390px /: page overflows sideways by 9px"]}]

    assert glc.main(argv, runner=broken, env_path=_env(tmp_path)) == 1
    captured = capsys.readouterr()
    assert USER not in captured.out + captured.err and PASSWORD not in captured.out + captured.err
    assert USER not in report.read_text(encoding="utf-8")


def test_missing_credentials_exit_2_and_run_nothing(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text("OTHER=1\n", encoding="utf-8")
    called = []
    report = tmp_path / "note.md"
    assert glc.main(["--report", str(report)], runner=lambda a, c: called.append(1), env_path=env) == 2
    assert called == [] and not report.exists()
    assert "cannot run" in capsys.readouterr().err
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_guide_layout_check.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'guide_layout_check'`.

- [ ] **Step 3: Write the script**

Create `scripts/dev/guide_layout_check.py`:

```python
"""Guide page layout check at three widths (v236 V236-11; spec v215 § Testing, "Layout").

Logs into a running admin with Playwright and opens the guide at 390, 820
and 1440 px. At each width: no sideways overflow; the contents mode the
width owns (picker < 640, drawer 640-1023, sticky rail >= 1024); every
guide control at least 44 px on phone and tablet (counting .sb-hit's
::after); a deep link lands its heading in the top half of the viewport.

    python scripts/dev/guide_layout_check.py [--base http://localhost:1234]
        [--out logs/v236-layout] [--report docs/superpowers/results/2026-11-18-v236-guide-layout.md]

Credentials are .env's ADMIN_USERNAME / ADMIN_PASSWORD, loaded in this
process and never printed (admin_browser_probe.load_credentials). Playwright
is imported lazily, so the verdicts import and test without it.
Exit 0 clean, 1 problems found, 2 cannot run.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ops"))

from admin_browser_probe import LoginFailed, _login, default_env_path, load_credentials  # noqa: E402

WIDTHS = (390, 820, 1440)
HEIGHT = 900
MIN_TARGET_PX = 44
TOUCH_MAX_WIDTH = 1023
PAGES = ("", "what-it-is", "glossary", "pipeline")   # the last one is screenshotted
DEEP_LINKS = ("what-it-is#the-notice", "glossary#r-multiple")
CHAPTERS_IN_DRAWER = 3
DEFAULT_BASE = "http://localhost:1234"
DEFAULT_OUT = ROOT / "logs" / "v236-layout"
DEFAULT_REPORT = ROOT / "docs" / "superpowers" / "results" / "2026-11-18-v236-guide-layout.md"
TOC_SELECTORS = {"picker": "sb-select.guide-picker", "drawer": "button.guide-contents", "rail": "nav.guide-rail"}
TARGETS = ", ".join(f"sb-guide {sel}" for sel in (
    "button", "select", "summary", "a.toc-chapter", "a.toc-heading", "a.permalink", "a.guide-result",
    "a.pipeline-link"))

_TARGETS_JS = """(selector) => [...document.querySelectorAll(selector)]
  .filter((el) => el.getClientRects().length > 0)
  .map((el) => {
    const box = el.getBoundingClientRect();
    const after = getComputedStyle(el, '::after');
    const hit = after.content !== 'none' && after.position === 'absolute';
    return { name: (el.getAttribute('aria-label') || el.textContent || el.tagName).trim().slice(0, 40),
             w: Math.max(box.width, hit ? parseFloat(after.width) || 0 : 0),
             h: Math.max(box.height, hit ? parseFloat(after.height) || 0 : 0) };
  })"""
_OVERFLOW_JS = """() => {
  const main = document.querySelector('main');
  return Math.max(document.documentElement.scrollWidth - window.innerWidth,
                  document.body.scrollWidth - window.innerWidth,
                  main ? main.scrollWidth - main.clientWidth : 0);
}"""
_VISIBLE_JS = "(sel) => { const el = document.querySelector(sel); return !!el && el.getClientRects().length > 0; }"
_POSITION_JS = "(sel) => { const el = document.querySelector(sel); return el ? getComputedStyle(el).position : null; }"
_TOP_JS = "(id) => { const el = document.getElementById(id); return el ? el.getBoundingClientRect().top : null; }"


# --- verdicts (pure) ---------------------------------------------------------

def expected_toc(width: int) -> str:
    if width < 640:
        return "picker"
    return "drawer" if width < 1024 else "rail"


def toc_problems(width: int, visible: dict[str, bool]) -> list[str]:
    want = expected_toc(width)
    problems = [] if visible.get(want) else [f"{width}px: contents {want} ({TOC_SELECTORS[want]}) not shown"]
    return problems + [f"{width}px: contents {mode} ({TOC_SELECTORS[mode]}) shown, expected only the {want}"
                       for mode in sorted(TOC_SELECTORS) if mode != want and visible.get(mode)]


def overflow_problems(width: int, page: str, excess: float) -> list[str]:
    return [f"{width}px {page or '/'}: page overflows sideways by {excess:.0f}px"] if excess > 1 else []


def target_problems(width: int, page: str, targets: list[dict]) -> list[str]:
    if width > TOUCH_MAX_WIDTH:
        return []
    return [f"{width}px {page or '/'}: {t['name']} hit area {t['w']:.0f}x{t['h']:.0f}px < {MIN_TARGET_PX}"
            for t in targets if min(t["w"], t["h"]) < MIN_TARGET_PX]


def deep_link_problems(width: int, link: str, top: float | None, height: int = HEIGHT) -> list[str]:
    if top is None:
        return [f"{width}px {link}: heading not found"]
    if not 0 <= top <= height / 2:
        return [f"{width}px {link}: heading at {top:.0f}px, not scrolled into the top half"]
    return []


def render_report(results: list[dict], base: str, today: str) -> str:
    problems = [p for row in results for p in row["problems"]]
    lines = [f"# v236 guide layout check -- {today}", "",
             f"Base `{base}`; widths {', '.join(str(w) for w in WIDTHS)}; pages "
             + ", ".join(f"`/insights/guide/{p}`" for p in PAGES)
             + f"; deep links {', '.join(f'`{d}`' for d in DEEP_LINKS)}. "
             "Script: `scripts/dev/guide_layout_check.py`.", "",
             "| Width | Contents | Problems |", "|---|---|---|"]
    lines += [f"| {row['width']} | {expected_toc(row['width'])} | {len(row['problems'])} |" for row in results]
    lines += ["", "## Verdict", "", "PASS: no problems." if not problems else f"FAIL: {len(problems)} problems."]
    return "\n".join(lines + [f"- {p}" for p in problems]) + "\n"


# --- browser loop ------------------------------------------------------------

def _shown(page, selector: str, timeout_ms: int = 15_000) -> bool:
    try:
        page.locator(selector).first.wait_for(state="visible", timeout=timeout_ms)
    except Exception:  # noqa: BLE001 -- Playwright's TimeoutError: recorded as a problem, not a crash
        return False
    return True


def _open(page, base: str, path: str) -> bool:
    page.goto(f"{base}/insights/guide{'/' + path if path else ''}", wait_until="domcontentloaded")
    return _shown(page, "article.guide-chapter .md", 30_000)


def _page_problems(page, base: str, width: int, path: str) -> list[str]:
    if not _open(page, base, path):
        return [f"{width}px {path or '/'}: the chapter never rendered"]
    return (overflow_problems(width, path, page.evaluate(_OVERFLOW_JS))
            + target_problems(width, path, page.evaluate(_TARGETS_JS, TARGETS)))


def _contents_problems(page, width: int) -> list[str]:
    problems = toc_problems(width, {mode: page.evaluate(_VISIBLE_JS, sel) for mode, sel in TOC_SELECTORS.items()})
    mode = expected_toc(width)
    if mode == "rail" and page.evaluate(_POSITION_JS, TOC_SELECTORS["rail"]) != "sticky":
        problems.append(f"{width}px: nav.guide-rail is not position: sticky")
    if mode == "drawer" and page.evaluate(_VISIBLE_JS, TOC_SELECTORS["drawer"]):
        page.click(TOC_SELECTORS["drawer"])
        _shown(page, "sb-drawer a.toc-chapter")
        count = page.locator("sb-drawer a.toc-chapter").count()
        if count != CHAPTERS_IN_DRAWER:
            problems.append(f"{width}px: the drawer lists {count} chapters, expected {CHAPTERS_IN_DRAWER}")
        problems += target_problems(width, "drawer", page.evaluate(
            _TARGETS_JS, "sb-drawer a.toc-chapter, sb-drawer a.toc-heading"))
        page.keyboard.press("Escape")
    return problems


def _deep_link_top(page, base: str, link: str) -> float | None:
    slug, anchor = link.split("#", 1)
    if not _open(page, base, f"{slug}#{anchor}") or not _shown(page, f"[id='{anchor}']"):
        return None
    page.wait_for_timeout(500)   # the page scrolls after its body renders
    return page.evaluate(_TOP_JS, anchor)


def check_width(page, base: str, width: int, out: Path) -> dict:
    page.set_viewport_size({"width": width, "height": HEIGHT})
    problems: list[str] = []
    for path in PAGES:
        problems += _page_problems(page, base, width, path)
    problems += _contents_problems(page, width)
    page.screenshot(path=str(out / f"guide@{width}.png"))
    for link in DEEP_LINKS:
        problems += deep_link_problems(width, link, _deep_link_top(page, base, link))
    return {"width": width, "problems": problems}


def run_browser(args, credentials: tuple[str, str]) -> list[dict]:
    try:
        from playwright.sync_api import sync_playwright  # lazy: not a declared dependency
    except ImportError:
        raise LoginFailed("playwright is not installed") from None
    base = args.base.rstrip("/")
    args.out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(viewport={"width": WIDTHS[-1], "height": HEIGHT},
                                          service_workers="block")
            _login(context, base, credentials)
            page = context.new_page()
            return [check_width(page, base, width, args.out) for width in WIDTHS]
        finally:
            browser.close()


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Guide page layout check at 390/820/1440 px (v236).")
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="screenshot directory")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="Markdown result note")
    return parser.parse_args(argv)


def main(argv=None, *, runner=None, env_path=None) -> int:
    args = parse_args(argv)
    try:
        credentials = load_credentials(env_path or default_env_path())
        results = (runner or run_browser)(args, credentials)
    except LoginFailed as exc:
        print(f"guide layout: cannot run: {exc}", file=sys.stderr)
        return 2
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_report(results, args.base, date.today().isoformat()), encoding="utf-8")
    problems = sum(len(row["problems"]) for row in results)
    print(f"guide layout: {problems} problems at {', '.join(str(r['width']) for r in results)} px -> {args.report}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_guide_layout_check.py`
Expected: PASS (`0 failed`).

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (`_contents_problems` is the largest new function, about 7).

- [ ] **Step 5: Commit**

```bash
git add scripts/dev/guide_layout_check.py tests/scripts/test_guide_layout_check.py
git commit -m "test(guide): layout check script for 390/820/1440 with unit-tested verdicts (v236 V236-11)"
```

### Task V236-11b: Layout run, audit routes and the result note

**Model:** sonnet — runs V236-11's check and the layout audit against a local admin; a two-line route edit; fixes, if any, stay in the guide files.

**Files:**
- Modify: `frontend/scripts/layout-audit-lib.mjs` (`ROUTES` += `/insights/guide`, `/insights/guide/pipeline`)
- Modify: `frontend/scripts/layout-audit-lib.test.mjs` (the route count and list)
- Create: `docs/superpowers/results/2026-11-18-v236-guide-layout.md` (written by `python scripts/dev/guide_layout_check.py`)

**Interfaces:**
- Consumes: `guide_layout_check.main` and its exit codes (V236-11); the full page, route and chapters (V236-4..V236-10); `node frontend/scripts/layout-audit.mjs` (`--base`, `--widths`; exit 0 clean, 1 findings, 2 cannot run).
- Produces: the result note and its `PASS`/`FAIL` verdict, which V236-12 records in the index `## Handoff`.

- [ ] **Step 1: Write the failing route test**

In `frontend/scripts/layout-audit-lib.test.mjs`, in the test `ROUTES visits every destination, section and tab once, on the v202 paths only (32)`: change `(32)` in its name to `(34)` and `assert.equal(ROUTES.length, 32);` to `assert.equal(ROUTES.length, 34);` (if another plan has changed the count since, add 2 to the count on disk), and add `'/insights/guide', '/insights/guide/pipeline',` to the `for (const route of [...])` list after `'/insights/reports?tab=gates',`.

Run: `node --test frontend/scripts/layout-audit-lib.test.mjs`
Expected: FAIL — `32 !== 34` and the missing `/insights/guide` route.

- [ ] **Step 2: Add the guide to the audit's routes**

In `frontend/scripts/layout-audit-lib.mjs`, change the `ROUTES` line `'/insights/research', '/insights/reports', '/insights/reports?tab=gates',` to:

```js
  '/insights/research', '/insights/reports', '/insights/reports?tab=gates', '/insights/guide', '/insights/guide/pipeline',
```

The header of that file says a route added to the app is added here in the same commit; V236-7 added the route without it.

Run: `node --test frontend/scripts/layout-audit-lib.test.mjs`
Expected: PASS.

- [ ] **Step 3: Run both checks against a local admin and write the result note**

1. Run `/replicate-prod-db` (the shared `swing-db` container; login needs the users table). In a worktree, `.env`'s `DATABASE_URL` wins over the process environment: point it at the local replica, never print it.
2. Build and serve the current bundle: `cd frontend && npm run build`, then copy `frontend/dist/frontend/browser/.` over `swingbot/admin/static/app/` (`cp -r`; the served `main-*.js` name must equal the `dist` one, or the check measures a stale bundle).
3. Start the admin in the background: `python admin_ui.py` (listens on port 1234).
4. Run: `python scripts/dev/guide_layout_check.py`
   Expected: `guide layout: 0 problems at 390, 820, 1440 px -> docs/superpowers/results/2026-11-18-v236-guide-layout.md`, exit 0. Exit 2 means no session or no Playwright (`pip install playwright && python -m playwright install chromium`); it never prints the credentials.
5. Run: `node frontend/scripts/layout-audit.mjs --base http://localhost:1234 --widths 390,768,1440`
   Expected: exit 0. A finding on a `/insights/guide` route is fixed in the guide files (V236-4/6/6b/9 code), the touched spec re-run alone, and both checks re-run. A finding on another page that `main` also shows is not this plan's: append it to the result note under `## Other pages` and leave it.
6. Read a screenshot (`logs/v236-layout/guide@<width>.png`) only to diagnose a failing check, at most 4 image reads in this task.
7. Stop the admin server.

The result note is the script's output; add nothing by hand except the `## Other pages` section of item 5.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/results/2026-11-18-v236-guide-layout.md frontend/scripts/layout-audit-lib.mjs frontend/scripts/layout-audit-lib.test.mjs
git commit -m "test(guide): guide in the layout audit routes; layout note at 390/820/1440 (v236 V236-11b)"
```

### Task V236-12: Full-suite verification

**Model:** haiku — run-only task; no code.

**Files:** none (run only).

- [ ] **Step 1: Push the branch and watch CI**

Push the implementation branch; CI runs one job per suite from `tests/suites.toml` plus the `frontend-test` job (`ng test` over every spec, `pipeline-diagram.spec.ts` and `guide-anchors.spec.ts` included). Never run the full suite locally (CLAUDE.md).

Expected: every job green, `0 failed` and `0 xfailed`. A failing test is fixed and re-run alone (`python scripts/dev/testrun.py file <test>` or `cd frontend && npx ng test --watch=false --include <spec>`), then pushed again until CI is green.

- [ ] **Step 2: Record the result**

Add a line to the index `## Handoff`: CI run id, date, green, and the layout note `docs/superpowers/results/2026-11-18-v236-guide-layout.md` verdict. Then `/close-out` (bump: ui minor; v235's bot patch closes with v235).


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

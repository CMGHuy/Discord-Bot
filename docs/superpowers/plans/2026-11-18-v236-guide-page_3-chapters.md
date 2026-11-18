# v236 — Guide page, Part 3: chapters 1, 3 and 12 (V236-8, V236-9, V236-9b, V236-10)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V236-9" -A 400 <this file>`).

**Spec:** v215 — [2026-11-06-v215-guide-page.md](../specs/2026-11-06-v215-guide-page.md) (Plan A, frontend half: § What the reader gets rows 1, 3, 12; § Three layers per chapter; § Testing "Layout")
**Index:** [2026-11-18-v236-guide-page_0-index.md](2026-11-18-v236-guide-page_0-index.md) — Goal, `## Global Constraints`, `## Parallelisation`, the task ledger and `## Handoff` live there and bind every task below.
The layout check and CI (V236-11, V236-11b, V236-12) live in [2026-11-18-v236-guide-page_3b-layout.md](2026-11-18-v236-guide-page_3b-layout.md): this file would pass the 1500-line cap with them.

Contracts this part consumes (do not change them):

- **Chapter format (v235 V235-2/2b).** `docs/guide/NN-<slug>.md`; YAML front matter with exactly `title`, `slug`, `order`, `reviewed_for` (`2.19.2`), `sources` (a list; `path` or `path:symbol`, where a `.py` symbol is a module-level name, `Class.method`, or a `Field("NAME", …)` in `swingbot/config.py`); the file name must equal `f"{order:02d}-{slug}.md"`. Headings are `##`/`###` only, never inside `<details>`, never holding `{{…}}`. The page renders the chapter title as the page `h1`, so a chapter has **no `#` heading**.
- **Placeholders (V235-3/3b/4).** Only these names resolve: `MAX_STOP_LOSS_PCT`, `MIN_STOP_DISTANCE_PCT`, `CLAMP_STOP_TO_HARD_CAP` (`on`/`off`), `RISK_PER_TRADE_PCT`, `RISK_PER_TRADE_PCT.max`, `MAX_RISK_AMOUNT_ABSOLUTE` (`$100`), `PORTFOLIO_HEAT_CAP_PCT`, `CORRELATED_HEAT_CAP_PCT`, `SECTOR_HEAT_CAP_PCT`, `POSITION_SIZING_MODE`, `correlation.threshold`, `correlation.window`, `correlation.sector_fallback`, `sizing.kelly_cap`, `sizing.risk_floor`, `sizing.risk_ceiling`, `sizing.gap`, `version.bot`, `levels.families` (one `- <family>` line each: put it on its own paragraph), `CLUSTER_TOLERANCE_PCT` (`1.5%`), `horizons.table` (a Markdown table: own paragraph), `gates.list`, `alerts.per_week`. Percent placeholders render with their `%` sign.
- **Content test (V235-6, `tests/admin/test_guide_content.py`).** Every placeholder resolves, every `sources:` entry exists, `horizons.table` appears in some chapter, every `<!-- figure:<name> -->` names a `GUIDE_FIGURES` key, `reviewed_for` ≤ `VERSION.json` bot, and `guide-anchors.json` equals `python scripts/dev/guide_anchors.py`'s output.
- **Page (V236-3/4/6).** A figure line splits the chapter; the figure component renders between Markdown segments inside `article.guide-chapter`, whose `(click)` handler routes any `a[href]` it contains (SVG links included) through the router. In-chapter links are plain Markdown: `[text](/insights/guide/<slug>#<anchor>)` or `[text](#<anchor>)`. DOM the layout check reads: `nav.guide-rail` (≥ 1024, `position: sticky`), `button.guide-contents` + `sb-drawer` (640–1023), `sb-select.guide-picker` (< 640), `a.toc-chapter`, `a.toc-heading`, `a.permalink`, `a.guide-result`.

Commands (from the repo root): `python scripts/dev/testrun.py file <test>`; `cd frontend && npx ng test --watch=false --include <spec>` (a 60 s "Timeout waiting for worker" is a known flake: re-run once).

**Glossary anchors are final here.** Chapters 1 and 3 (V236-8, V236-9) link to glossary anchors that V236-10 creates; V236-10's test then fails on any link whose anchor is missing. The anchors used: `alert`, `trade-plan`, `paper-trade`, `horizon`, `long-and-short`, `confidence`, `watchlist-and-universe`, `level`, `level-family`, `confluence`, `scenario`, `strategy`, `completed-bar`, `gate`, `market-regime`, `relative-strength`, `stop`, `tp1-and-tp2`, `runner`, `scale-out`, `reward-to-risk-rr`, `stop-distance-cap`, `risk-per-trade`, `dollar-risk-cap`, `portfolio-heat`, `correlated-heat`, `size-0-alert`, `gap-through-the-stop`, `r-multiple`, `badge`.

---

# Phase 6 — Chapters

### Task V236-8: Chapter 1: What the bot is (and isn't)

**Model:** sonnet — fixed chapter text plus a small pytest module; the text is given whole below, no design calls.

**Files:**
- Create: `docs/guide/01-what-it-is.md`
- Create: `tests/admin/test_guide_chapter_text.py` (suite `admin-core` by its `test_[b-z]*.py` glob; no `suites.toml` edit; V236-9 and V236-10 append to it)
- Regenerate: `frontend/src/app/workspaces/guide/guide-anchors.json` (created by v235 V235-6; written only by `python scripts/dev/guide_anchors.py`)

**Interfaces:**
- Consumes: `chapters.load_chapters(root=None)`, `Chapter` (`slug`, `title`, `order`, `body`, `headings`, `path`), `Heading.anchor` (V235-2/2b); `placeholders.resolve(text) -> str` (V235-3b); `live_market._load_trades` (V235-4, patched so nothing reads the database).
- Produces: slug `what-it-is`, order 1; anchors `what-it-does`, `what-it-does-not-do`, `swing-horizons`, `what-an-alert-is`, `where-alerts-appear`, `the-notice` (Plan C's `?` links may target `what-it-is#the-notice`). Helpers in `tests/admin/test_guide_chapter_text.py` that V236-9/10 reuse: `SPEC_SLUGS`, `_by_slug()`, `_chapter(slug)`, `_anchors(chapter)`, `_section(body, heading)`, `_link_problems(loaded)`, `_GUIDE_LINK`.

Every fact below was checked against the code on 2026-11-18: `config.py` `ETORO_USER_KEY` (section comment "credentials only; nothing consumes them yet"), the `DISCORD_CHANNEL_*` help texts, `SCAN_UNIVERSE` ("The watchlist is ALWAYS included"), `alert_embeds.py` (the `⛔ ENTRY BLOCKED — portfolio heat cap` headline with suggested size 0), `strategy_types.HORIZONS` / `live_horizons()`. No rule number is typed into the prose; horizons come from `{{horizons.table}}`.

- [ ] **Step 1: Write the failing test**

Create `tests/admin/test_guide_chapter_text.py`:

```python
"""v236 V236-8..V236-10: what chapters 1, 3 and 12 must keep saying (spec v215).

The generic checks (placeholders, sources, headings, figures, anchor fixture)
live in test_guide_content.py; this module pins each chapter's own promises.
"""
from __future__ import annotations

import re

import pytest

from swingbot.admin.guide import chapters, live_market, placeholders

#: Spec v215 § What the reader gets: the twelve chapter slugs.
SPEC_SLUGS = frozenset({
    "what-it-is", "reading-an-alert", "pipeline", "levels", "strategies", "gates",
    "trade-plan", "sizing-risk", "after-the-alert", "measuring-edge", "admin-tour", "glossary"})
_GUIDE_LINK = re.compile(r"\]\(/insights/guide/([a-z0-9-]+)(?:#([a-z0-9_-]+))?\)")
_SELF_LINK = re.compile(r"\]\(#([a-z0-9_-]+)\)")


@pytest.fixture(autouse=True)
def _no_live_book(monkeypatch):
    """alerts.per_week would read the database."""
    monkeypatch.setattr(live_market, "_load_trades", lambda: [])


def _by_slug() -> dict[str, chapters.Chapter]:
    return {chapter.slug: chapter for chapter in chapters.load_chapters()}


def _chapter(slug: str) -> chapters.Chapter:
    found = _by_slug().get(slug)
    assert found is not None, f"docs/guide has no chapter '{slug}'"
    return found


def _anchors(chapter: chapters.Chapter) -> list[str]:
    return [heading.anchor for heading in chapter.headings]


def _section(body: str, heading: str) -> str:
    """The text under one `## heading`, up to the next `## `."""
    return body.split(f"## {heading}\n", 1)[1].split("\n## ", 1)[0]


def _link_problems(loaded: dict[str, chapters.Chapter]) -> list[str]:
    problems = []
    for chapter in loaded.values():
        name = chapter.path.name
        for slug, anchor in _GUIDE_LINK.findall(chapter.body):
            if slug not in SPEC_SLUGS:
                problems.append(f"{name}: /insights/guide/{slug} is not a guide chapter")
            elif anchor and slug in loaded and anchor not in _anchors(loaded[slug]):
                problems.append(f"{name}: #{anchor} is not a heading of {slug}")
        problems += [f"{name}: #{anchor} is not a heading of this chapter"
                     for anchor in _SELF_LINK.findall(chapter.body)
                     if anchor not in _anchors(chapter)]
    return problems


# --- chapter 1: what-it-is ---------------------------------------------------

def test_chapter_1_header_and_plain_words_callout():
    chapter = _chapter("what-it-is")
    assert (chapter.order, chapter.title) == (1, "What the bot is (and isn't)")
    assert chapter.path.name == "01-what-it-is.md"
    assert chapter.body.startswith("> **In plain words**")


def test_chapter_1_sections_in_order():
    assert _anchors(_chapter("what-it-is")) == [
        "what-it-does", "what-it-does-not-do", "swing-horizons", "what-an-alert-is",
        "where-alerts-appear", "the-notice"]


def test_chapter_1_says_paper_only_and_that_the_demo_is_not_live():
    section = _section(_chapter("what-it-is").body, "What it does not do")
    assert "It never places an order." in section
    assert "A demo account is not a live account" in section
    assert "nothing is sent to eToro today" in section


def test_chapter_1_carries_the_full_notice():
    notice = _section(_chapter("what-it-is").body, "The notice")
    for phrase in ("This guide is education about a paper-trading tool",
                   "Alerts are not recommendations tailored to you",
                   "A suggested size is a default, not advice",
                   "Past results do not predict future ones"):
        assert phrase in notice, phrase


def test_chapter_1_horizons_come_from_the_live_table():
    section = _section(_chapter("what-it-is").body, "Swing horizons")
    assert "{{horizons.table}}" in section
    rendered = placeholders.resolve(section)
    assert "| Horizon | Swing | Longest hold | Status |" in rendered
    assert "{{" not in rendered


# --- every chapter -----------------------------------------------------------

def test_internal_links_name_a_guide_chapter_and_a_real_anchor():
    """Anchors are checked for chapters that exist; V236-10 also requires the chapter."""
    assert _link_problems(_by_slug()) == []


def test_link_checker_reports_a_bad_slug_and_a_missing_anchor(tmp_path):
    (tmp_path / "01-what-it-is.md").write_text(
        "---\ntitle: T\nslug: what-it-is\norder: 1\nreviewed_for: 2.19.2\nsources: []\n---\n"
        "> **In plain words** x.\n\n## Real\n\n[a](/insights/guide/nowhere) [b](#ghost) "
        "[c](/insights/guide/what-it-is#real) [d](/insights/guide/what-it-is#gone)\n",
        encoding="utf-8")
    loaded = {c.slug: c for c in chapters.load_chapters(tmp_path)}
    assert _link_problems(loaded) == [
        "01-what-it-is.md: /insights/guide/nowhere is not a guide chapter",
        "01-what-it-is.md: #gone is not a heading of what-it-is",
        "01-what-it-is.md: #ghost is not a heading of this chapter",
    ]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: FAIL — the five chapter-1 tests report `docs/guide has no chapter 'what-it-is'`; the two link tests pass (no chapter links yet; the checker works on its fixture).

- [ ] **Step 3: Write the chapter**

Create `docs/guide/01-what-it-is.md` with exactly this text (UTF-8, LF line endings, no `#` heading: the page shows the title):

````markdown
---
title: What the bot is (and isn't)
slug: what-it-is
order: 1
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/strategy_types.py:HORIZONS
  - swingbot/core/market/strategy_types.py:live_horizons
  - swingbot/core/scanning/scan_run.py:run_scan
  - swingbot/core/scanning/alert_embeds.py
  - swingbot/core/tracking/performance.py:TradeLog
  - swingbot/config.py:SCAN_UNIVERSE
  - swingbot/config.py:DISCORD_CHANNEL_TRADES_ID
  - swingbot/config.py:DISCORD_CHANNEL_TRADES_SIMPLE_ID
  - swingbot/config.py:DISCORD_CHANNEL_TRADES_HISTORY_ID
  - swingbot/config.py:DISCORD_CHANNEL_NOTIFY_ID
  - swingbot/config.py:ETORO_USER_KEY
---

> **In plain words** The bot reads daily price charts, looks for places where a stock tends to turn, and posts a ready-made trade plan when one lines up. It never buys or sells anything. Every plan it posts is followed as a paper trade, so you can see how it would have done.

## What it does

The bot is a swing-trade alert tool. It watches a list of US stocks and ETFs (the [watchlist](/insights/guide/glossary#watchlist-and-universe)), finds price [levels](/insights/guide/glossary#level) where several independent methods agree, and turns a good setup into a [trade plan](/insights/guide/glossary#trade-plan): where to enter, where the [stop](/insights/guide/glossary#stop) sits, and where to take profit ([TP1 and TP2](/insights/guide/glossary#tp1-and-tp2)).

It holds trades for days to months, not minutes. It is built for [swing horizons](#swing-horizons) and judges setups on completed daily bars.

[The scan pipeline](/insights/guide/pipeline) shows every step from the watchlist to a closed trade.

## What it does not do

- **It never places an order.** The bot sends no orders to any broker. Every plan it posts becomes a [paper trade](/insights/guide/glossary#paper-trade): a record the bot follows bar by bar to see whether the stop or a target would have been hit.
- **It is not a live account.** A planned next step sends the same plans to an eToro *demo* account, which trades practice money. A demo account is not a live account, and nothing is sent to eToro today.
- **It does not know you.** It does not know your account, your other positions, your taxes or your goals. Its suggested size is worked out for the account size stored in its settings, not for yours.
- **It does not predict.** A plan says where the setup is proved wrong (the stop) and where it pays (the targets). It does not say the trade will work.

## Swing horizons

A [horizon](/insights/guide/glossary#horizon) is how long a plan is meant to run. Each horizon has its own settings: how far back levels are drawn from, how far away a stop may sit, and how long a trade may be held. A horizon marked *masked — research only* is measured in backtests but never alerted.

{{horizons.table}}

## What an alert is

An [alert](/insights/guide/glossary#alert) is one trade plan for one ticker on one horizon. It carries:

- the direction, [long or short](/insights/guide/glossary#long-and-short);
- the entry, the stop, TP1 and TP2, and the [reward to risk](/insights/guide/glossary#reward-to-risk-rr) to TP1;
- a [confidence](/insights/guide/glossary#confidence) level and, for a strategy setup, the strategy's [badge](/insights/guide/glossary#badge) with its sample size and date;
- a chart with the levels drawn on it;
- warnings when something needs attention, for example an unusually tight stop, or a position the [portfolio heat](/insights/guide/glossary#portfolio-heat) cap blocks (the alert still posts, with a suggested size of zero).

Most scans post nothing. A quiet day means no setup cleared every check, not that the bot is broken.

## Where alerts appear

- **Discord.** New plans go to the alerts channel, and a short text version to the simple-alerts channel. Wins, losses and near-stop or near-target notices go to the closed-trades channel. Updates on plans people follow (near the stop, TP1, TP2) go to the plan-updates channel.
- **bomeo-capital.com.** The admin site shows the same plans and every paper trade: open ones on Dashboard and Trades, closed ones with their result, and the measurements behind them under Insights.

<details><summary>Under the hood</summary>

The scan entry point is `run_scan` in `swingbot/core/scanning/scan_run.py`; the Discord embed is built in `swingbot/core/scanning/alert_embeds.py`; paper trades live in the trade log (`TradeLog`, `swingbot/core/tracking/performance.py`). The channels are the `DISCORD_CHANNEL_*` settings in `swingbot/config.py`. What is scanned is `SCAN_UNIVERSE`: the watchlist always, plus an optional wider universe. The horizon table is built from `HORIZONS` and `live_horizons()` in `swingbot/core/market/strategy_types.py` each time the chapter is served, so a horizon masked or unmasked in code shows correctly here without editing this text. The eToro keys (`ETORO_USER_KEY`, `ETORO_API_KEY`) exist in the settings, and nothing reads them yet.

</details>

## The notice

Read this before acting on anything the bot posts.

- **This guide is education about a paper-trading tool.** It explains how the tool works. It is not financial, investment or tax advice.
- **Alerts are not recommendations tailored to you.** They come from rules that know nothing about your situation.
- **A suggested size is a default, not advice.** It is sized to the account stored in the bot's settings; choose your own size for your own account.
- **Past results do not predict future ones.** Win rates, expectancy and badges measure what already happened, in backtests or in the paper book. Paper results also differ from real fills: real orders pay costs and can fill worse than the plan, especially across a gap.

If you trade from these alerts, you do so on your own judgement and at your own risk.
````

The glossary and pipeline links resolve once V236-9 and V236-10 land; until then those routes show the page's "No guide chapter called …" empty state, which is expected on this branch.

- [ ] **Step 4: Regenerate the anchor fixture**

Run: `python scripts/dev/guide_anchors.py`
Then: `python scripts/dev/guide_anchors.py --check`
Expected: exit 0; `frontend/src/app/workspaces/guide/guide-anchors.json` now lists `"what-it-is": ["what-it-does", "what-it-does-not-do", "swing-horizons", "what-an-alert-is", "where-alerts-appear", "the-notice"]`. Never edit the JSON by hand.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: PASS (`0 failed`).

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_content.py`
Expected: PASS — placeholders resolve, every `sources:` entry exists (`SCAN_UNIVERSE`, `ETORO_USER_KEY` and the `DISCORD_CHANNEL_*` names are `Field(...)` names in `swingbot/config.py`), `horizons.table` is rendered, the fixture is current.

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_guide.py`
Expected: PASS.

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/guide/guide-anchors.spec.ts`
Expected: PASS (it reads the regenerated fixture).

- [ ] **Step 6: Commit**

```bash
git add docs/guide/01-what-it-is.md tests/admin/test_guide_chapter_text.py frontend/src/app/workspaces/guide/guide-anchors.json
git commit -m "docs(guide): chapter 1, what the bot is and isn't, with the full notice (v236 V236-8)"
```

### Task V236-9: Chapter 3: the pipeline and its diagram

**Model:** sonnet — one presentational SVG component on the `plan-lifecycle-diagram.ts` pattern plus fixed chapter text; contracts fixed in the ledger.

**Files:**
- Create: `frontend/src/app/workspaces/guide/pipeline-diagram.ts`
- Create: `frontend/src/app/workspaces/guide/pipeline-diagram.spec.ts`
- Modify: `frontend/src/app/workspaces/guide/guide-figures.ts` (add `pipeline`)

Split at the 20 KB task cap: this task ships the diagram and registers it; **V236-9b** writes `docs/guide/03-pipeline.md` (which places it) and its tests. The registry entry must land first, because V235-6's content test fails a chapter naming a figure `GUIDE_FIGURES` lacks.

**Interfaces:**
- Consumes: `GuideStore.chapters(): GuideChapterSummary[]` and `ensureLoaded()` (V236-1); `ViewportService.isPhone` (`frontend/src/app/ui/breakpoints.ts`); `chartWidth(host, fallback)` (`frontend/src/app/ui/chart/chart-width.ts`); `GUIDE_FIGURES` literal (V236-3); the page's `onContentClick`, which routes any `a[href]` inside `article.guide-chapter`, SVG `<a>` included (V236-4).
- Produces: `GuidePipelineDiagram` (selector `sb-guide-pipeline-diagram`), `PIPELINE_STAGES: readonly PipelineStage[]` (`{label: string; lines: readonly string[]; slug: string}`, eleven stages in spec order); `GUIDE_FIGURES.pipeline` (V236-9b's chapter places it).

Diagram rules: tablet and desktop draw an inline SVG (viewBox 680×272, eleven 140×52 boxes in a snake of 4/4/3, arrows between neighbours), colours from theme tokens only, so light and dark both read. A box is an SVG `<a href="/insights/guide/<slug>">` only while that slug is in `GuideStore.chapters()`; otherwise the same `<a>` has no `href` (not focusable, not a link). Phones (< 640) get the same stages as an ordered list of real text (the precedent's v179 lesson: a shrunk viewBox makes 5px text). Boxes are 52 user units tall so a linked box is still ≥ 44px at the narrowest tablet width.

- [ ] **Step 1: Write the failing diagram spec**

Create `frontend/src/app/workspaces/guide/pipeline-diagram.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';

import { GuideIndex } from '../../api/models';
import { GuideStore } from '../../stores/guide.store';
import { ViewportService } from '../../ui/breakpoints';
import { GUIDE_FIGURES } from './guide-figures';
import { GuidePipelineDiagram, PIPELINE_STAGES } from './pipeline-diagram';

const LABELS = ['Watchlist', 'Price data', 'Levels from every method', 'Duplicate merge', 'Strategy signals',
  'Gates', 'Plan construction', 'Sizing and caps', 'Alert', 'Monitoring', 'Close'];

function index(slugs: string[]): GuideIndex {
  return { chapters: slugs.map((slug, i) => ({ slug, title: slug, order: i + 1, reviewed_for: '2.19.2', headings: [] })) };
}

async function render(phone: boolean, slugs: string[]): Promise<HTMLElement> {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [provideZonelessChangeDetection(), provideHttpClient(), provideHttpClientTesting(), GuideStore,
      { provide: ViewportService, useValue: { isPhone: signal(phone) } }],
  });
  const loaded = TestBed.inject(GuideStore).ensureLoaded();
  TestBed.inject(HttpTestingController).expectOne('/api/v1/guide').flush(index(slugs));
  await loaded;
  const fixture = TestBed.createComponent(GuidePipelineDiagram);
  fixture.detectChanges();
  await fixture.whenStable();
  return fixture.nativeElement as HTMLElement;
}

const text = (el: Element) => (el.textContent ?? '').replace(/\s+/g, ' ').trim();
/** An SVG box's label: its <text> lines joined (textContent would glue them). */
const boxLabel = (el: Element) => [...el.querySelectorAll('text')].map(text).join(' ');

describe('GuidePipelineDiagram', () => {
  it('lists the eleven stages of spec v215 chapter 3, in order', () => {
    expect(PIPELINE_STAGES.map((s) => s.label)).toEqual(LABELS);
    expect(PIPELINE_STAGES.map((s) => s.lines.join(' '))).toEqual(LABELS);
  });

  it('draws one SVG box per stage on tablet and desktop, no list', async () => {
    const el = await render(false, ['pipeline']);
    expect(el.querySelector('svg[role="group"]')).not.toBeNull();
    expect(el.querySelector('ol.pipeline-steps')).toBeNull();
    expect([...el.querySelectorAll('a.pipeline-node')].map(boxLabel)).toEqual(LABELS);
    expect(el.querySelectorAll('line.edge')).toHaveLength(10);
  });

  it('links no box while its chapter does not exist', async () => {
    const el = await render(false, ['what-it-is', 'pipeline', 'glossary']);
    expect(el.querySelectorAll('a.pipeline-link')).toHaveLength(0);
    expect([...el.querySelectorAll('a.pipeline-node')].every((a) => !a.hasAttribute('href'))).toBe(true);
  });

  it('links every box whose chapter exists, to that chapter', async () => {
    const el = await render(false, ['pipeline', 'levels', 'gates']);
    const links = [...el.querySelectorAll('a.pipeline-link')];
    expect(links.map(boxLabel)).toEqual(['Price data', 'Levels from every method', 'Duplicate merge', 'Gates']);
    expect(links.map((a) => a.getAttribute('href'))).toEqual([
      '/insights/guide/levels', '/insights/guide/levels', '/insights/guide/levels', '/insights/guide/gates']);
  });

  it('becomes an ordered list of real text on phones, with the same links', async () => {
    const el = await render(true, ['pipeline', 'gates']);
    expect(el.querySelector('svg')).toBeNull();
    expect([...el.querySelectorAll('ol.pipeline-steps > li')].map(text)).toEqual(LABELS);
    const links = [...el.querySelectorAll('ol.pipeline-steps a.pipeline-link')];
    expect(links.map((a) => [text(a), a.getAttribute('href')])).toEqual([['Gates', '/insights/guide/gates']]);
    expect(links.every((a) => a.classList.contains('sb-hit'))).toBe(true);
  });

  it('is registered as the pipeline figure', () => {
    expect(GUIDE_FIGURES['pipeline']).toBe(GuidePipelineDiagram);
  });

  it('colours with theme tokens only', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/guide/pipeline-diagram.ts'), 'utf-8');
    expect(src).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/);
  });
});
```

- [ ] **Step 2: Run the spec to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/guide/pipeline-diagram.spec.ts`
Expected: FAIL — `Cannot find module './pipeline-diagram'`.

- [ ] **Step 3: Write the component**

Create `frontend/src/app/workspaces/guide/pipeline-diagram.ts`:

```ts
import { ChangeDetectionStrategy, Component, ElementRef, computed, inject } from '@angular/core';

import { GuideStore } from '../../stores/guide.store';
import { ViewportService } from '../../ui/breakpoints';
import { chartWidth } from '../../ui/chart/chart-width';

const VIEWBOX_W = 680;
const BOX_W = 140;
const BOX_H = 52;
const LINE_GAP = 16;
const COLS = [10, 180, 350, 520] as const;
const ROWS = [10, 110, 210] as const;

export interface PipelineStage { label: string; lines: readonly string[]; slug: string }

/** Spec v215 chapter 3: watchlist to close, each with the chapter that explains it. */
export const PIPELINE_STAGES: readonly PipelineStage[] = [
  { label: 'Watchlist', lines: ['Watchlist'], slug: 'admin-tour' },
  { label: 'Price data', lines: ['Price data'], slug: 'levels' },
  { label: 'Levels from every method', lines: ['Levels from', 'every method'], slug: 'levels' },
  { label: 'Duplicate merge', lines: ['Duplicate', 'merge'], slug: 'levels' },
  { label: 'Strategy signals', lines: ['Strategy', 'signals'], slug: 'strategies' },
  { label: 'Gates', lines: ['Gates'], slug: 'gates' },
  { label: 'Plan construction', lines: ['Plan', 'construction'], slug: 'trade-plan' },
  { label: 'Sizing and caps', lines: ['Sizing', 'and caps'], slug: 'sizing-risk' },
  { label: 'Alert', lines: ['Alert'], slug: 'reading-an-alert' },
  { label: 'Monitoring', lines: ['Monitoring'], slug: 'after-the-alert' },
  { label: 'Close', lines: ['Close'], slug: 'after-the-alert' },
];

interface Point { x: number; y: number }
interface Edge { x1: number; y1: number; x2: number; y2: number }

/** Snake layout: rows of four, the middle row right to left. */
function place(index: number): Point {
  const row = Math.floor(index / 4);
  const step = index % 4;
  return { x: COLS[row % 2 === 1 ? 3 - step : step], y: ROWS[row] };
}

function edge(a: Point, b: Point): Edge {
  if (a.y !== b.y) return { x1: a.x + BOX_W / 2, y1: a.y + BOX_H, x2: b.x + BOX_W / 2, y2: b.y - 2 };
  const y = a.y + BOX_H / 2;
  return b.x > a.x ? { x1: a.x + BOX_W, y1: y, x2: b.x - 2, y2: y } : { x1: a.x, y1: y, x2: b.x + BOX_W + 2, y2: y };
}

const POINTS = PIPELINE_STAGES.map((_, i) => place(i));
const EDGES = POINTS.slice(1).map((point, i) => edge(POINTS[i], point));

/**
 * The scan pipeline of guide chapter 3, placed by a `<!-- figure:pipeline -->`
 * line. Links are plain hrefs: the guide page's click handler routes them.
 */
@Component({
  selector: 'sb-guide-pipeline-diagram',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '[style.--pl-scale]': 'scale()' },
  template: `
    @if (phone()) {
      <ol class="pipeline-steps" aria-label="The scan pipeline">
        @for (stage of stages(); track stage.label) {
          <li><a class="pipeline-node" [class.pipeline-link]="!!stage.href" [class.sb-hit]="!!stage.href"
                 [attr.href]="stage.href">{{ stage.label }}</a></li>
        }
      </ol>
    } @else {
      <svg viewBox="0 0 680 272" role="group" aria-label="The scan pipeline, from the watchlist to a closed trade">
        <defs>
          <marker id="guide-pipeline-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7"
                  orient="auto-start-reverse">
            <path d="M0,0 L8,4 L0,8 Z" class="arrowhead" />
          </marker>
        </defs>
        @for (e of edges; track $index) {
          <line class="edge" [attr.x1]="e.x1" [attr.y1]="e.y1" [attr.x2]="e.x2" [attr.y2]="e.y2"
                marker-end="url(#guide-pipeline-arrow)" />
        }
        @for (stage of stages(); track stage.label) {
          <a class="pipeline-node" [class.pipeline-link]="!!stage.href" [attr.href]="stage.href"
             [attr.aria-label]="stage.href ? stage.label : null">
            <rect [attr.x]="stage.x" [attr.y]="stage.y" width="140" height="52" rx="8" />
            @for (line of stage.text; track $index) {
              <text [attr.x]="stage.x + 70" [attr.y]="line.y">{{ line.text }}</text>
            }
          </a>
        }
      </svg>
    }
  `,
  styles: `
    :host { display: block; max-width: 680px; margin: var(--space-14) 0; }
    svg { display: block; width: 100%; height: auto; overflow: visible; }
    .edge { fill: none; stroke: var(--text-faint); stroke-width: 1.5; }
    .arrowhead { fill: var(--text-faint); }
    rect { fill: var(--surface); stroke: var(--border); stroke-width: 1; }
    text {
      fill: var(--text); font-weight: 600; text-anchor: middle; dominant-baseline: middle;
      font-size: calc(var(--text-chip) / var(--pl-scale, 1));
    }
    .pipeline-link rect { stroke: var(--accent); }
    .pipeline-link text { fill: var(--accent); }
    .pipeline-link:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

    .pipeline-steps {
      display: flex; flex-direction: column; gap: var(--space-6); margin: 0; padding-left: var(--space-20);
      font-size: var(--text-body); overflow-wrap: anywhere;
    }
    .pipeline-steps li { padding: var(--space-4) 0; }
    .pipeline-node { color: var(--text); text-decoration: none; }
    .pipeline-steps .pipeline-link { color: var(--accent); text-decoration: underline; }
  `,
})
export class GuidePipelineDiagram {
  private readonly store = inject(GuideStore);
  protected readonly phone = inject(ViewportService).isPhone;
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly width = chartWidth(() => this.host.nativeElement, VIEWBOX_W);
  /** 1 at full size, below 1 as the host narrows; the CSS divides the text token by it. */
  protected readonly scale = computed(() => Math.round(Math.min(1, this.width() / VIEWBOX_W) * 1000) / 1000);
  protected readonly edges = EDGES;

  protected readonly stages = computed(() => {
    const written = new Set(this.store.chapters().map((c) => c.slug));
    return PIPELINE_STAGES.map((stage, i) => {
      const { x, y } = POINTS[i];
      const middle = y + BOX_H / 2 - ((stage.lines.length - 1) * LINE_GAP) / 2;
      return {
        ...stage, x, y,
        href: written.has(stage.slug) ? `/insights/guide/${stage.slug}` : null,
        text: stage.lines.map((line, j) => ({ text: line, y: middle + j * LINE_GAP })),
      };
    });
  });
}
```

- [ ] **Step 4: Register the figure**

Replace the registry line in `frontend/src/app/workspaces/guide/guide-figures.ts` so the file reads (keep the comment brace-free; V235-6's `figure_names()` reads keys up to the first `}` after `= {`):

```ts
import { Type } from '@angular/core';

import { GuidePipelineDiagram } from './pipeline-diagram';

/*
 * Figures a chapter can place with a line of its own reading
 * <!-- figure:NAME -->. Keys are the NAME; the content test fails a chapter
 * that names a figure missing here. Keep this a flat literal of
 * name: Component pairs, one per line.
 */
export const GUIDE_FIGURES: Record<string, Type<unknown>> = {
  pipeline: GuidePipelineDiagram,
};
```

- [ ] **Step 5: Run the spec to verify it passes**

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/guide/pipeline-diagram.spec.ts`
Expected: PASS (7 tests).

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/guide/guide.spec.ts`
Expected: PASS (the page spec's own `test-figure` entry still works beside `pipeline`).

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_content.py`
Expected: PASS (`figure_names()` now reads `{"pipeline"}`; no chapter names a figure yet).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/guide/pipeline-diagram.ts frontend/src/app/workspaces/guide/pipeline-diagram.spec.ts frontend/src/app/workspaces/guide/guide-figures.ts
git commit -m "feat(guide): inline-SVG pipeline diagram, registered as the pipeline figure (v236 V236-9)"
```

### Task V236-9b: Chapter 3 text: the scan pipeline, end to end

**Model:** sonnet — fixed chapter text and appended pytest cases; the text is given whole below.

**Files:**
- Create: `docs/guide/03-pipeline.md`
- Modify: `tests/admin/test_guide_chapter_text.py` (append the chapter-3 tests)
- Regenerate: `frontend/src/app/workspaces/guide/guide-anchors.json` (`python scripts/dev/guide_anchors.py`)

**Interfaces:**
- Consumes: `GUIDE_FIGURES.pipeline` (V236-9; must be merged first); test helpers `_chapter`, `_anchors`, `_section` (V236-8); `chapters.FIGURE_RE`, `placeholders.names_in`, `placeholders.resolve` (V235-2/3b).
- Produces: slug `pipeline`, order 3; anchors `watchlist`, `price-data`, `levels-from-every-method`, `duplicate-merge`, `setups-and-strategy-signals`, `confluence-scenarios`, `strategy-signals`, `gates`, `plan-construction`, `sizing-and-caps`, `alert`, `monitoring`, `close`.

Facts checked against the code on 2026-11-18 (brief § Chapter 3 map): `run_scan` runs the synchronous pipeline in a background thread and handles closes and near-close warnings; `_scan_one` applies the liquidity and data-quality screens before analysis; `collect_candidate_levels` skips a failing method; `_cluster_levels(candidates, tolerance_pct=CLUSTER_TOLERANCE_PCT)`; `dedup_scan_items` keeps the highest-confidence plan of near-identical ones per ticker and direction; `build_scenarios`' hard requirements; `strategy_signals` fires on the last completed bar; `STRATEGY_ALERTS_MODE` off/shadow/live; `SIGNAL_CONFIRMATION_SCANS`; `veto_bullish_for` (dead-cat bounce), `_apply_headroom` (blocked path to target 1); `build_confluence_plan` picks a structural TP1 with no fixed-multiple fallback; `build_strategy_plan` uses the backtest's conditions; heat and correlation caps flag the alert with size 0 (`scan_run.py` E7/E8 comments); `plan rejected (` is logged and the plan not posted (`qualify.py`); `update_open_trades` checks the live quote as a virtual bar; `monitor_open_only`; plan states from `plan_engine.py`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/admin/test_guide_chapter_text.py`:

```python
# --- chapter 3: pipeline -----------------------------------------------------

PIPELINE_ANCHORS = [
    "watchlist", "price-data", "levels-from-every-method", "duplicate-merge",
    "setups-and-strategy-signals", "confluence-scenarios", "strategy-signals", "gates",
    "plan-construction", "sizing-and-caps", "alert", "monitoring", "close"]


def test_chapter_3_header_and_plain_words_callout():
    chapter = _chapter("pipeline")
    assert (chapter.order, chapter.title) == (3, "The scan pipeline, end to end")
    assert chapter.body.startswith("> **In plain words**")


def test_chapter_3_walks_the_pipeline_in_order():
    assert _anchors(_chapter("pipeline")) == PIPELINE_ANCHORS


def test_chapter_3_places_the_diagram_once_before_the_first_stage():
    body = _chapter("pipeline").body
    assert chapters.FIGURE_RE.findall(body) == ["pipeline"]
    assert body.index("<!-- figure:pipeline -->") < body.index("## Watchlist")


def test_chapter_3_takes_every_rule_number_from_a_placeholder():
    names = set(placeholders.names_in(_chapter("pipeline").body))
    assert {"levels.families", "CLUSTER_TOLERANCE_PCT", "MAX_STOP_LOSS_PCT", "CLAMP_STOP_TO_HARD_CAP",
            "RISK_PER_TRADE_PCT", "MAX_RISK_AMOUNT_ABSOLUTE", "POSITION_SIZING_MODE",
            "PORTFOLIO_HEAT_CAP_PCT", "CORRELATED_HEAT_CAP_PCT"} <= names
    rendered = placeholders.resolve(_section(_chapter("pipeline").body, "Sizing and caps"))
    assert "{{" not in rendered and "%" in rendered


def test_chapter_3_names_the_three_sizing_outcomes():
    section = _section(_chapter("pipeline").body, "Sizing and caps")
    for outcome in ("**rejected**", "**clamped**", "**size-0 alert**", "`plan rejected (`"):
        assert outcome in section, outcome


def test_chapter_3_sources_cover_every_stage():
    paths = {entry.partition(":")[0] for entry in _chapter("pipeline").sources}
    assert {
        "swingbot/core/scanning/scan_run.py", "swingbot/core/scanning/fetch.py",
        "swingbot/core/market/levels.py", "swingbot/core/scanning/dedup.py",
        "swingbot/core/scanning/strategy_pass.py", "swingbot/core/scanning/analyze.py",
        "swingbot/core/scanning/gating.py", "swingbot/core/planning/builders.py",
        "swingbot/core/planning/account.py", "swingbot/core/edge/heat.py",
        "swingbot/core/edge/correlation.py", "swingbot/core/scanning/alert_embeds.py",
        "swingbot/core/tracking/performance.py", "swingbot/core/planning/plan_engine.py",
        "frontend/src/app/workspaces/guide/pipeline-diagram.ts"} <= paths
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: FAIL — the six chapter-3 tests report `docs/guide has no chapter 'pipeline'`; the chapter-1 and link tests pass.

- [ ] **Step 3: Write the chapter**

Create `docs/guide/03-pipeline.md` with exactly this text (UTF-8, LF; the figure line stands alone with blank lines around it):

````markdown
---
title: The scan pipeline, end to end
slug: pipeline
order: 3
reviewed_for: 2.19.2
sources:
  - swingbot/core/scanning/scan_run.py:run_scan
  - swingbot/core/scanning/analyze.py:_scan_one
  - swingbot/core/scanning/fetch.py
  - swingbot/core/market/levels.py:collect_candidate_levels
  - swingbot/core/market/levels.py:_cluster_levels
  - swingbot/core/market/levels.py:build_scenarios
  - swingbot/core/market/levels.py:ALL_STRATEGY_FAMILIES
  - swingbot/core/market/levels.py:CLUSTER_TOLERANCE_PCT
  - swingbot/core/scanning/dedup.py:dedup_scan_items
  - swingbot/core/scanning/strategy_pass.py:run_strategy_pass
  - swingbot/core/scanning/strategy_pass.py:strategy_signals
  - swingbot/core/scanning/regime.py:get_market_regime
  - swingbot/core/scanning/regime.py:get_htf_bias
  - swingbot/core/scanning/analyze.py:veto_bullish_for
  - swingbot/core/scanning/analyze.py:_apply_headroom
  - swingbot/core/scanning/analyze.py:attach_plan_v2
  - swingbot/core/scanning/analyze.py:_reject_plan
  - swingbot/core/scanning/analyze.py:monitor_open_only
  - swingbot/core/scanning/gating.py:passes_confluence
  - swingbot/core/market/strategy_types.py:admits
  - swingbot/core/planning/builders.py:build_confluence_plan
  - swingbot/core/planning/builders.py:build_strategy_plan
  - swingbot/core/planning/account.py
  - swingbot/core/edge/heat.py:heat_check
  - swingbot/core/edge/correlation.py:cluster_check
  - swingbot/core/scanning/alert_embeds.py
  - swingbot/core/tracking/performance.py:TradeLog.update_open_trades
  - swingbot/core/planning/plan_manager.py:PlanManager.poll
  - swingbot/core/planning/plan_engine.py
  - swingbot/config.py:SCAN_UNIVERSE
  - swingbot/config.py:STRATEGY_ALERTS_MODE
  - swingbot/config.py:SIGNAL_CONFIRMATION_SCANS
  - swingbot/config.py:CLAMP_STOP_TO_HARD_CAP
  - frontend/src/app/workspaces/guide/pipeline-diagram.ts:GuidePipelineDiagram
---

> **In plain words** Every few minutes the bot looks at every stock on its list. For each one it draws the price levels that matter, checks whether a trade toward the next level makes sense, runs the idea past a set of filters, works out a size that keeps the possible loss small, and posts the plan. Then it watches the trade until it closes.

<!-- figure:pipeline -->

Each box is one stage below, in order. A box becomes a link to the chapter that explains it in depth once that chapter is written.

## Watchlist

The scan starts from the [watchlist](/insights/guide/glossary#watchlist-and-universe): the tickers you follow, edited on the Watchlist page. A setting can add a wider universe (for example S&P 500 names or ETFs) on top; the watchlist is always included. Scans run on a fixed interval while the bot is up, and every scan does two jobs: it looks for new trades, and it checks every open paper trade.

## Price data

For each ticker the bot loads daily bars (open, high, low, close, volume) from its local store first and fetches only what is missing. Each ticker is loaded once per scan, and every later stage reads that same copy. A ticker that trades too thinly, or whose data look broken, is dropped here, before any analysis.

## Levels from every method

For each horizon the bot asks every [level family](/insights/guide/glossary#level-family) where support and resistance sit:

{{levels.families}}

Each family proposes candidate prices. A method that fails on one ticker is skipped; the others still count.

## Duplicate merge

Candidates closer together than {{CLUSTER_TOLERANCE_PCT}} merge into one [level](/insights/guide/glossary#level). A level's [confluence](/insights/guide/glossary#confluence) is the number of different families behind it, not the number of raw candidates, so one method that draws three lines at the same price counts once. Later in the scan, when one ticker produces near-identical plans in the same direction (for example on two horizons), only the plan with the highest confidence is posted.

## Setups and strategy signals

A setup is found in one of two ways.

### Confluence scenarios

From the current price the bot builds two [scenarios](/insights/guide/glossary#scenario): long toward the next resistance above, and short toward the next support below. A scenario survives only if it clears every hard requirement: a first target far enough away to be worth the trade, a stop neither too tight nor too wide, and enough reward for the risk. The level it trades from needs enough confluence to count at all.

### Strategy signals

Separately, each registered [strategy](/insights/guide/glossary#strategy) checks its own entry rule on the last [completed daily bar](/insights/guide/glossary#completed-bar), with the same functions its backtests are measured with. A setting switches this path between three modes: off; shadow, where plans are built and recorded but never alerted or traded; and live.

## Gates

[Gates](/insights/guide/glossary#gate) are filters a setup must pass. The [market regime](/insights/guide/glossary#market-regime) and each ticker's longer-term trend are read once per scan for the gates that need them. A strategy may be allowed only long, only short, or only on some horizons; a masked cell never alerts. Strategy plans also face a [relative strength](/insights/guide/glossary#relative-strength) check. Confluence scenarios are dropped when another level blocks the path to the first target, and longs are blocked when the chart looks like a dead-cat bounce. Finally a signal must appear on enough consecutive scans to be confirmed, which filters out intraday flicker.

## Plan construction

A setup that passes becomes a [trade plan](/insights/guide/glossary#trade-plan). For a confluence setup, TP1 is a real level on the chart: the nearest one that pays at least the minimum [reward to risk](/insights/guide/glossary#reward-to-risk-rr). If none does, no plan is built; the bot never invents a target from a fixed multiple of the risk. A strategy plan is built under the same conditions its backtest used, so a live plan and a backtested one follow the same rules. Plans scale out: part of the position closes at TP1 and the [runner](/insights/guide/glossary#runner) aims for TP2.

## Sizing and caps

The size comes from the risk: the distance from entry to [stop](/insights/guide/glossary#stop), and how much one trade may lose. Three separate limits apply.

- The stop may sit at most {{MAX_STOP_LOSS_PCT}} from the entry (the [stop-distance cap](/insights/guide/glossary#stop-distance-cap)). A stop further away is clamped to that distance or the plan is dropped; clamping is {{CLAMP_STOP_TO_HARD_CAP}}.
- The sizing mode is {{POSITION_SIZING_MODE}}. In the fixed-risk mode one trade loses at most {{RISK_PER_TRADE_PCT}} of the account at its stop ([risk per trade](/insights/guide/glossary#risk-per-trade)).
- No trade risks more than {{MAX_RISK_AMOUNT_ABSOLUTE}} ([dollar risk cap](/insights/guide/glossary#dollar-risk-cap)).

Then the open book is checked. When the new trade would push [portfolio heat](/insights/guide/glossary#portfolio-heat) over {{PORTFOLIO_HEAT_CAP_PCT}}, or put more than {{CORRELATED_HEAT_CAP_PCT}} of risk into one group of stocks that move together ([correlated heat](/insights/guide/glossary#correlated-heat)), the alert still posts, flagged, with a suggested size of zero.

So a plan ends this stage in one of three ways: **rejected** (logged as `plan rejected (` and never posted), **clamped** (posted with the stop moved in to the cap), or posted as a **size-0 alert** ([size-0 alert](/insights/guide/glossary#size-0-alert)) that shows what the cap cost.

## Alert

The plan is posted with its chart, and a paper trade is opened from it. [Where alerts appear](/insights/guide/what-it-is#where-alerts-appear) lists the Discord channels and the admin pages.

## Monitoring

Every scan checks each open paper trade against the newest bars and the live quote, pre-market and after-hours included, so a stop or target hit during the day is caught at once rather than at the next daily close. Trades on tickers not scanned for new entries that day are still checked. When price comes near the stop or a target, a notice goes to Discord.

## Close

A trade closes at its stop, at its targets (part at TP1, the rest at TP2 or on its trailing stop), or when it runs out of time for its horizon. A plan moves from PENDING (waiting for its entry) to ACTIVE, to PARTIAL after TP1, and to CLOSED; one whose entry never fills is CANCELLED. The result is recorded in [R](/insights/guide/glossary#r-multiple), the profit or loss as a multiple of the risk taken. When the price gaps past the stop overnight, the fill is worse than −1R ([gap through the stop](/insights/guide/glossary#gap-through-the-stop)).

<details><summary>Under the hood</summary>

All paths are under `swingbot/core/`.

| Stage | Code |
|---|---|
| Scan run | `run_scan` (`scanning/scan_run.py`) runs the pipeline in a worker thread; per ticker `_scan_one` (`scanning/analyze.py`) |
| Price data | `scanning/fetch.py`, cache first, one crawl per scan |
| Levels | `collect_candidate_levels` (`market/levels.py`) |
| Merge | `_cluster_levels(candidates, tolerance_pct=CLUSTER_TOLERANCE_PCT)`; `dedup_scan_items` (`scanning/dedup.py`) |
| Scenarios | `build_scenarios` (`market/levels.py`); `passes_confluence` (`scanning/gating.py`) |
| Strategy signals | `run_strategy_pass`, `strategy_signals` (`scanning/strategy_pass.py`); setting `STRATEGY_ALERTS_MODE` |
| Gates | `get_market_regime`, `get_htf_bias` (`scanning/regime.py`); `veto_bullish_for`, `_apply_headroom` (`scanning/analyze.py`); `admits` (`market/strategy_types.py`); setting `SIGNAL_CONFIRMATION_SCANS` |
| Plan | `build_confluence_plan`, `build_strategy_plan` (`planning/builders.py`); `attach_plan_v2` (`scanning/analyze.py`) |
| Sizing and caps | `planning/account.py`; `heat_check` (`edge/heat.py`); `cluster_check` (`edge/correlation.py`); rejects through `_reject_plan` |
| Alert | `scanning/alert_embeds.py` |
| Monitoring | `TradeLog.update_open_trades` (`tracking/performance.py`); `monitor_open_only`; `PlanManager.poll` (`planning/plan_manager.py`) |
| Close | plan states in `planning/plan_engine.py` |

</details>
````

- [ ] **Step 4: Regenerate the anchor fixture**

Run: `python scripts/dev/guide_anchors.py`
Then: `python scripts/dev/guide_anchors.py --check`
Expected: exit 0; the fixture gains `"pipeline": [...]` with the thirteen anchors of `PIPELINE_ANCHORS`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: PASS (`0 failed`).

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_content.py`
Expected: PASS — every `sources:` symbol is defined (`TradeLog.update_open_trades` and `PlanManager.poll` as class methods; `pipeline-diagram.ts:GuidePipelineDiagram` by text search), the figure is registered, the fixture is current.

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/guide/guide-anchors.spec.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add docs/guide/03-pipeline.md tests/admin/test_guide_chapter_text.py frontend/src/app/workspaces/guide/guide-anchors.json
git commit -m "docs(guide): chapter 3, the scan pipeline end to end (v236 V236-9b)"
```

### Task V236-10: Chapter 12: Glossary

**Model:** sonnet — fixed chapter text and appended pytest cases; the text is given whole below.

**Files:**
- Create: `docs/guide/12-glossary.md`
- Modify: `tests/admin/test_guide_chapter_text.py` (append the glossary tests)
- Regenerate: `frontend/src/app/workspaces/guide/guide-anchors.json` (`python scripts/dev/guide_anchors.py`)

**Interfaces:**
- Consumes: test helpers `SPEC_SLUGS`, `_by_slug`, `_chapter`, `_anchors`, `_GUIDE_LINK`, `_link_problems` (V236-8); chapters 1 and 3 (V236-8, V236-9b), whose glossary links this chapter must satisfy.
- Produces: slug `glossary`, order 12; one `###` heading (one anchor) per term under six `##` groups. Every anchor in this part's header list exists; Plans B and C link here.

Each definition is one to three sentences, number-free except through placeholders. Facts checked on 2026-11-18: `registry.Badge.status` is `"VALIDATED" | "WEAK"` with `n`, `window`, `run_date` and a read-time `decay` (`fresh`/`aging`/`stale`); `provenance_label` reads `Source: …; N = …; as of …; costs … ; before tax`; plan states from `plan_engine.py`; the runner exits at TP2, its trailing stop, break-even or a time limit (`exit_sim.py` `runner_outcome`); `HORIZONS[*]["rs_window"]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/admin/test_guide_chapter_text.py`:

```python
# --- chapter 12: glossary ----------------------------------------------------

GLOSSARY_GROUPS = ["the-bot-and-its-alerts", "levels-and-setups", "inside-a-trade-plan",
                   "risk-and-sizing", "measuring-results", "about-this-guide"]
#: Anchors chapters 1 and 3 link to (part 3 header of plan v236).
GLOSSARY_LINKED = {
    "alert", "trade-plan", "paper-trade", "horizon", "long-and-short", "confidence",
    "watchlist-and-universe", "level", "level-family", "confluence", "scenario", "strategy",
    "completed-bar", "gate", "market-regime", "relative-strength", "stop", "tp1-and-tp2", "runner",
    "scale-out", "reward-to-risk-rr", "stop-distance-cap", "risk-per-trade", "dollar-risk-cap",
    "portfolio-heat", "correlated-heat", "size-0-alert", "gap-through-the-stop", "r-multiple", "badge"}


def test_glossary_header_and_plain_words_callout():
    chapter = _chapter("glossary")
    assert (chapter.order, chapter.title, chapter.path.name) == (12, "Glossary", "12-glossary.md")
    assert chapter.body.startswith("> **In plain words**")


def test_glossary_groups_terms_one_heading_each():
    headings = _chapter("glossary").headings
    assert [h.anchor for h in headings if h.level == 2] == GLOSSARY_GROUPS
    terms = [h.text.lower() for h in headings if h.level == 3]
    assert len(terms) >= 45
    assert len(set(terms)) == len(terms), "a term is defined twice"


def test_glossary_defines_every_term_the_guide_links_to():
    assert GLOSSARY_LINKED <= set(_anchors(_chapter("glossary")))
    linked = {anchor for chapter in _by_slug().values()
              for slug, anchor in _GUIDE_LINK.findall(chapter.body) if slug == "glossary" and anchor}
    assert linked <= set(_anchors(_chapter("glossary")))


def test_every_linked_chapter_is_written():
    """From V236-10 on, prose links only to chapters that exist (no dead links)."""
    loaded = _by_slug()
    dead = sorted({f"{c.path.name} -> {slug}" for c in loaded.values()
                   for slug, _anchor in _GUIDE_LINK.findall(c.body) if slug not in loaded})
    assert dead == []
    assert _link_problems(loaded) == []


def test_glossary_risk_numbers_come_from_placeholders():
    body = _chapter("glossary").body
    assert {"MAX_STOP_LOSS_PCT", "RISK_PER_TRADE_PCT", "RISK_PER_TRADE_PCT.max", "MAX_RISK_AMOUNT_ABSOLUTE",
            "PORTFOLIO_HEAT_CAP_PCT", "CORRELATED_HEAT_CAP_PCT", "correlation.threshold",
            "correlation.window", "CLUSTER_TOLERANCE_PCT"} <= set(placeholders.names_in(body))
    assert "{{" not in placeholders.resolve(body)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: FAIL — the five glossary tests report `docs/guide has no chapter 'glossary'` (`test_every_linked_chapter_is_written` reports the dead `glossary` links of chapters 1 and 3); every earlier test passes.

- [ ] **Step 3: Write the chapter**

Create `docs/guide/12-glossary.md` with exactly this text (UTF-8, LF):

````markdown
---
title: Glossary
slug: glossary
order: 12
reviewed_for: 2.19.2
sources:
  - swingbot/core/backtesting/registry.py:Badge
  - swingbot/core/backtesting/registry.py:decay_for
  - swingbot/core/market/strategy_types.py:HORIZONS
  - swingbot/core/market/strategy_types.py:admits
  - swingbot/core/market/levels.py:CLUSTER_TOLERANCE_PCT
  - swingbot/core/planning/plan_engine.py
  - swingbot/core/edge/correlation.py:cluster_check
  - swingbot/core/edge/heat.py:heat_check
  - swingbot/config.py:MAX_STOP_LOSS_PCT
  - swingbot/config.py:CLAMP_STOP_TO_HARD_CAP
  - swingbot/config.py:RISK_PER_TRADE_PCT
  - swingbot/config.py:MAX_RISK_AMOUNT_ABSOLUTE
  - swingbot/config.py:PORTFOLIO_HEAT_CAP_PCT
  - swingbot/config.py:CORRELATED_HEAT_CAP_PCT
  - swingbot/config.py:STRATEGY_ALERTS_MODE
---

> **In plain words** Every word the guide uses, in one place. Each term has its own link, so other chapters point straight at it.

## The bot and its alerts

### Alert

One trade plan for one ticker on one horizon, posted to Discord and shown on the admin site.

### Trade plan

The full instruction behind an alert: direction, entry, stop, TP1, TP2 and a suggested size.

### Paper trade

A trade the bot only records. It follows the plan bar by bar and books the result as if the orders had filled; no money moves.

### Live paper book

Every paper trade opened from a live alert. Figures labelled "live paper book" come from it.

### Horizon

How long a plan is meant to run, from a short swing to several months. Each horizon has its own lookbacks, stop limits and longest hold.

### Masked

A horizon, or a strategy on one side and horizon, that is measured in research but never alerted. Shown as *masked — research only*.

### Long and short

A long profits when the price rises; a short profits when it falls. Every plan is one or the other.

### Confidence

A level and a score on every alert that rank how well a setup lines up. It is a ranking, not the chance of winning.

### Watchlist and universe

The watchlist is the list of tickers you follow, and it is always scanned. The universe is an optional wider set scanned on top.

### Shadow mode

A setting under which strategy plans are built and recorded but never alerted or traded, so they can be measured first.

## Levels and setups

### Support and resistance

Support is a price where falling stocks have tended to stop; resistance is where rising ones have. The bot trades from one toward the next.

### Level

One support or resistance price after nearby candidates from different methods have merged.

### Level family

One method of drawing levels, for example moving averages, Fibonacci retracements or pivots. The level chapter lists them all.

### Confluence

How many different level families agree on one level. Candidates within {{CLUSTER_TOLERANCE_PCT}} of each other merge, and each family counts once, however many lines it draws.

### Scenario

A possible trade from the current price: long toward the next resistance or short toward the next support. It must clear hard requirements to become a plan.

### Strategy

A named entry rule, such as a breakout or a pullback, measured in backtests and allowed only on the sides and horizons its results support.

### Completed bar

A daily bar after its session has closed. Signals read completed bars only, so the live bot and a backtest see the same data.

### Gate

A filter a setup must pass before it becomes a plan, kept because a measurement showed it helped.

### Market regime

The state of the broad market, read once per scan. Gates that care about the market use it.

### Relative strength

How a stock has moved against the market or its sector over a window set per horizon.

## Inside a trade plan

### Entry

The price at which the plan opens. Until the price reaches it, the plan waits.

### Stop

The price where the idea is proved wrong. The trade closes there at −1R, and the stop never moves further away after entry.

### TP1 and TP2

The two profit targets. TP1 is a real level on the chart; TP2 lies further out.

### Runner

The part of the position left open after TP1. It aims for TP2 and can also close on its trailing stop, at break-even or on a time limit.

### Scale-out

Closing part of the position at TP1 and leaving the runner to work.

### Reward to risk (R:R)

The distance to TP1 divided by the distance to the stop. A plan needs a minimum before it is built.

### Plan states

PENDING (waiting for the entry), ACTIVE, PARTIAL (after TP1), then CLOSED. A plan whose entry never fills is CANCELLED.

## Risk and sizing

### Stop-distance cap

The furthest a stop may sit from the entry: {{MAX_STOP_LOSS_PCT}} of the price.

### Clamp

What happens to a stop beyond the stop-distance cap when clamping is on: it moves in to the cap. When clamping is off, the plan is dropped instead.

### Risk per trade

The share of the account one trade loses at its stop in the fixed-risk sizing mode: {{RISK_PER_TRADE_PCT}}, never more than {{RISK_PER_TRADE_PCT.max}}.

### Dollar risk cap

The most one trade may lose at its stop in money: {{MAX_RISK_AMOUNT_ABSOLUTE}}.

### Rejected plan

A plan that broke a rule. It is logged as `plan rejected (` with the reason and never posted.

### Portfolio heat

The total risk of every open trade at its stop, as a share of the account. A new trade that would push it over {{PORTFOLIO_HEAT_CAP_PCT}} is posted as a size-0 alert. The Risk page shows the same figure.

### Correlated heat

The risk sitting in one group of stocks whose daily returns correlate above {{correlation.threshold}} over {{correlation.window}}, capped at {{CORRELATED_HEAT_CAP_PCT}} of the account.

### Size-0 alert

An alert a heat cap blocks. It still posts, flagged, with a suggested size of zero, so you see what the cap cost.

### Suggested size

The number of shares that loses the risk per trade at the stop for the account stored in the bot's settings. A default, not advice.

### Gap through the stop

The price opens beyond the stop, so the fill is worse than −1R. Risk and heat are measured to the stop, not to the gap.

## Measuring results

### R-multiple

A result divided by the risk taken. +2R made twice the risk; −1R lost the risk.

### Expectancy (ExpR)

The average R per closed trade. Positive means the method made money on average in that sample; it says nothing certain about the next trade.

### Win rate

The share of closed trades that made money. It can rise while expectancy falls, when winners get smaller.

### Drawdown and losing streak

A drawdown is a fall from a peak in account value; a losing streak is losses in a row. Both happen even when expectancy is positive.

### Badge

A strategy's backtest grade, VALIDATED or WEAK, always shown with its N, window and run date. It ages to *aging* and then *stale* as the run date gets older. A measurement, not a forecast.

### Provenance label

The note beside every performance figure: its source, N, date, whether costs are included, and "before tax".

### TRAIN and validation

Two separate backtest windows. Rules are tuned on TRAIN and confirmed once on validation, never tuned on it.

### Idea screen

A quick historical test a new entry idea must pass before any work is planned on it.

### Pre-registration

A test whose pass bar is written down before it runs. A failed one is closed and never re-run.

### No-lift

The verdict on a change that did not improve results. The change is not shipped, and the record is kept.

## About this guide

### Reviewed for

The bot version a chapter was last checked against, shown at the top of each chapter.

### Under the hood

The collapsed boxes for developers: the module, setting and algorithm behind a section.
````

- [ ] **Step 4: Regenerate the anchor fixture**

Run: `python scripts/dev/guide_anchors.py`
Then: `python scripts/dev/guide_anchors.py --check`
Expected: exit 0; the fixture gains `"glossary": [...]` (six group anchors and one anchor per term, in document order).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: PASS (`0 failed`): every glossary link from chapters 1 and 3 resolves; no prose links to an unwritten chapter.

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_content.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_guide.py`
Expected: PASS.

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/guide/guide-anchors.spec.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add docs/guide/12-glossary.md tests/admin/test_guide_chapter_text.py frontend/src/app/workspaces/guide/guide-anchors.json
git commit -m "docs(guide): chapter 12, the glossary, one anchor per term (v236 V236-10)"
```

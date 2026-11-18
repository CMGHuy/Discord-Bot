# v237 — Guide trading core, part 3: chapters 5 (strategies), 6 (gates) and 7 (trade plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V237-11" -A 400 <this file>`); never read this part whole.

**Spec:** v215 — [2026-11-06-v215-guide-page.md](../specs/2026-11-06-v215-guide-page.md), Plan B, chapters 5–7.
**Index:** [2026-11-18-v237-guide-trading-core_0-index.md](2026-11-18-v237-guide-trading-core_0-index.md) — Goal, Global Constraints, Parallelisation, the task ledger and the binding `## Handoff` live there. Read its Global Constraints and Handoff 5, 6, 8, 9 before any task here.

Tasks V237-10, V237-11, V237-12 run one at a time, in that order, after V237-9b (all three edit `tests/admin/test_guide_chapter_text.py` and regenerate `guide-anchors.json`). Each task carries the whole chapter; the code facts in it were read from the tree on 2026-11-18 (HEAD 09ba3e70) and every `sources:` entry was checked with `git grep`. Step 1 of each task re-checks them, because v235/v236/v237 land later.

Rules every chapter here follows (index Global Constraints, Handoff 5/6/8):

- Only what the live scan does today is described as live; anything behind a switch takes its state from a placeholder (`{{gates.switches}}` or a single-flag name), never a typed "on"/"off".
- Every rule number is a placeholder; chapter 7 (order 7) has no bare number before `%` outside code fences (the real content test `[bare percent]` checks it).
- Links go only to chapters that exist when the task runs (`what-it-is`, `pipeline`, `glossary`, `levels`, then each chapter of this part as it lands) and to glossary anchors in `GLOSSARY_LINKED`. Chapters not yet written are named in plain text ("chapter 6", "chapter 8"); V237-13 (part 4) may turn those into links once chapter 8 exists.
- The layout check pins three chapters until V237-14; do not run it here.

# Phase 5 — Chapters 5 to 7

### Task V237-10: Chapter 5: Strategies

**Model:** sonnet — chapter text given whole below plus pinned text tests; the implementer must re-verify every `sources:` symbol and placeholder and patch the badge reader in the new tests.

**Why.** Spec v215 § chapter 5. The cards (V237-7/7b) and `strategies.cards` (V237-5) exist; this chapter frames them: strategies versus level families, how a strategy alert is sent (`STRATEGY_ALERTS_MODE`, read live), how to read a card, what masked means. Index Handoff "For part 3": the cards say "the shared gates", so `reading-a-card` defines them. Chapter 10 (Plan C) holds the long badge framing, so this chapter carries its own not-a-forecast note (brief T3).

**Files:**
- Create: `docs/guide/05-strategies.md`
- Modify (created by v236 V236-8): `tests/admin/test_guide_chapter_text.py` (append the chapter-5 tests)
- Regenerate: `frontend/src/app/workspaces/guide/guide-anchors.json`

**Interfaces:**
- Consumes: placeholder `strategies.cards` and module attrs `live_strategies._badge`, `NO_ROW_MASKED`, `badge_line` (V237-5); placeholders `STRATEGY_ALERTS_MODE`, `STRATEGY_ALERTS_LIVE_STRATEGIES` (V237-3b); `live_market.registered_strategy_keys()` (V235-4); the nineteen card files (V237-7/7b); the glossary anchors linked below (all in `GLOSSARY_LINKED` after V237-8); chapter-1 anchor `swing-horizons` (V236); test helpers `_chapter`, `_anchors`, `_section`, `_GUIDE_LINK`, `GLOSSARY_LINKED` and the autouse `_no_live_book` / `_stored_account` fixtures (V236-8, V237-1).
- Produces (ledger): `docs/guide/05-strategies.md` — slug `strategies`, order 5, title `Strategies`, anchors `strategies-are-not-level-families`, `how-a-strategy-alert-is-sent`, `reading-a-card`, `masked-strategies`, `the-cards`; `{{strategies.cards}}` is the last line of the chapter. Test names `CH5_ANCHORS`, `_NO_PCT` (V237-11 and V237-12 reuse `_NO_PCT`) and the fixture `_unmeasured_badges`.

Links: `what-it-is`, `pipeline`, `glossary`, `levels` and this chapter only; chapters 6 and 7 do not exist yet and are named in plain text.

- [ ] **Step 1: Confirm every source and placeholder exists**

Run: `git grep -n "^STRATEGY_FUNCS" swingbot/core/market/strategy.py; git grep -n "^STRATEGY_GATES\|^MASKED_BY_DEFAULT_HORIZONS\|^def admits\|^def live_horizons" swingbot/core/market/strategy_types.py`
Expected: five lines.

Run: `git grep -n "^ENTRY_FUNCS\|^def entries_for\|^def compute_shared_gates\|^def gate_override" swingbot/core/market/entry_filters.py`
Expected: four lines.

Run: `git grep -n "^def completed_frame\|^def strategy_signals\|^def run_strategy_pass" swingbot/core/scanning/strategy_pass.py; git grep -n "^def _maybe_run_strategy_pass" swingbot/core/scanning/scan_run.py; git grep -n "^def build_strategy_plan" swingbot/core/planning/builders.py; git grep -n "^def stamp_badge" swingbot/core/planning/params.py; git grep -n "^def risk_sizing_ok" swingbot/core/planning/stop_scope.py; git grep -n "^class Badge\|^def get_badge" swingbot/core/backtesting/registry.py; git grep -n "^def badge_line\|^NO_ROW_MASKED" swingbot/admin/guide/live_strategies.py`
Expected: twelve lines (the last two from V237-5).

Run: `git grep -n -e 'Field("STRATEGY_ALERTS_MODE"' -e 'Field("STRATEGY_ALERTS_LIVE_STRATEGIES"' swingbot/config.py; ls docs/guide/strategies/*.md | wc -l`
Expected: two lines, then `19`.

Run: `python -c "from swingbot.admin.guide import placeholders as p; need={'strategies.cards','STRATEGY_ALERTS_MODE','STRATEGY_ALERTS_LIVE_STRATEGIES'}; print(sorted(need-set(p.PLACEHOLDERS)))"`
Expected: `[]`.

The "Under the hood" paragraphs below name the functions the text was read from on 2026-11-18 (`strategy_pass._emit_signal`, `_goes_live`, `_maybe_run_strategy_pass`); if one changed, correct the matching sentence and say so in the task report.

- [ ] **Step 2: Write the failing tests**

Append to `tests/admin/test_guide_chapter_text.py`:

```python
# --- chapter 5: strategies (v237 V237-10) ----------------------------------------------

CH5_ANCHORS = ["strategies-are-not-level-families", "how-a-strategy-alert-is-sent",
               "reading-a-card", "masked-strategies", "the-cards"]
CH5_LINKABLE = {"glossary", "pipeline", "what-it-is", "levels", "strategies"}
_NO_PCT = re.compile(r"(?<![\w.])\d+(?:\.\d+)?[ \t]?%")


@pytest.fixture
def _unmeasured_badges(monkeypatch):
    """Every key reads as having no registry row, so no test depends on the committed registry."""
    from swingbot.admin.guide import live_strategies
    from swingbot.core.backtesting.registry import Badge
    monkeypatch.setattr(live_strategies, "_badge", lambda key: Badge("WEAK", 0, 0.0, 0.0))


def test_chapter_5_header_and_plain_words_callout():
    chapter = _chapter("strategies")
    assert (chapter.order, chapter.title) == (5, "Strategies")
    assert chapter.path.name == "05-strategies.md"
    assert chapter.body.startswith("> **In plain words**")


def test_chapter_5_sections_in_order():
    assert _anchors(_chapter("strategies")) == CH5_ANCHORS


def test_chapter_5_cards_placeholder_closes_the_chapter():
    body = _chapter("strategies").body
    assert body.rstrip().endswith("{{strategies.cards}}")
    assert placeholders.names_in(body).count("strategies.cards") == 1


def test_chapter_5_renders_one_card_per_registered_key(_unmeasured_badges):
    from swingbot.admin.guide import live_strategies
    rendered = placeholders.resolve(_section(_chapter("strategies").body, "The cards"))
    for key in live_market.registered_strategy_keys():
        assert f"### {key}\n" in rendered
    assert live_strategies.NO_ROW_MASKED in rendered
    assert "**Badge:** WEAK" not in rendered   # a key with no row never shows a tier


def test_chapter_5_badge_carries_its_provenance(monkeypatch):
    from swingbot.admin.guide import live_strategies
    from swingbot.core.backtesting.registry import Badge
    row = Badge("VALIDATED", 112, 50.0, 0.219, window="2024-01-01..2025-12-31",
                run_date="2026-08-17")
    monkeypatch.setattr(live_strategies, "_badge", lambda key: row)
    rendered = placeholders.resolve(_section(_chapter("strategies").body, "The cards"))
    assert "N = 112; as of 2026-08-17; costs not recorded; before tax" in rendered


def test_chapter_5_alert_path_reads_the_live_switches():
    section = _section(_chapter("strategies").body, "How a strategy alert is sent")
    assert {"STRATEGY_ALERTS_MODE", "STRATEGY_ALERTS_LIVE_STRATEGIES"} <= set(
        placeholders.names_in(section))
    assert all(f"| {mode} |" in section for mode in ("off", "shadow", "live"))


def test_chapter_5_reading_a_card_defines_the_shared_gates():
    import pandas as pd
    from swingbot.core.market.entry_filters import compute_shared_gates
    section = _section(_chapter("strategies").body, "Reading a card")
    assert "the shared gates" in section
    for label in ("Uptrend", "Medium-term trend", "Not dead flat", "Not panicking", "Real volume"):
        assert f"**{label}**" in section
    frame = pd.DataFrame({"Open": [10.0] * 30, "High": [11.0] * 30, "Low": [9.0] * 30,
                          "Close": [10.0] * 30, "Volume": [1000.0] * 30})
    gates = compute_shared_gates(frame)
    for name in ("bull_regime", "trend50_bull", "atr_floor", "atr_calm", "vol_ok"):
        assert name in gates and f"`{name}`" in section
    assert "not a forecast" in section
    assert "costs not recorded" in section and "before tax" in section


def test_chapter_5_masked_strategies_never_show_an_empty_badge():
    from swingbot.admin.guide import live_strategies
    section = _section(_chapter("strategies").body, "Masked strategies")
    assert live_strategies.NO_ROW_MASKED in section
    assert "masked — research only" in section
    assert "](/insights/guide/what-it-is#swing-horizons)" in section


def test_chapter_5_resolves_and_links_only_written_chapters(_unmeasured_badges):
    chapter = _chapter("strategies")
    assert "{{" not in placeholders.resolve(chapter.body)
    links = _GUIDE_LINK.findall(chapter.body)
    glossary = {anchor for slug, anchor in links if slug == "glossary"}
    assert glossary and glossary <= GLOSSARY_LINKED
    assert {slug for slug, _anchor in links} <= CH5_LINKABLE
    assert not _NO_PCT.search(re.sub(r"\{\{[^}]*\}\}", "", chapter.body))
```

`re`, `pytest`, `placeholders` and `live_market` are already imported (v236 V236-8). If chapter 1's "Swing horizons" anchor is not `swing-horizons`, change the test and the link together.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: FAIL — the nine chapter-5 tests report `docs/guide has no chapter 'strategies'`; every earlier test passes.

- [ ] **Step 4: Write the chapter**

Create `docs/guide/05-strategies.md` with exactly this text (UTF-8, LF, one trailing newline):

````markdown
---
title: Strategies
slug: strategies
order: 5
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/strategy.py:STRATEGY_FUNCS
  - swingbot/core/market/strategy_types.py:STRATEGY_GATES
  - swingbot/core/market/strategy_types.py:MASKED_BY_DEFAULT_HORIZONS
  - swingbot/core/market/strategy_types.py:admits
  - swingbot/core/market/strategy_types.py:live_horizons
  - swingbot/core/market/entry_filters.py:ENTRY_FUNCS
  - swingbot/core/market/entry_filters.py:entries_for
  - swingbot/core/market/entry_filters.py:compute_shared_gates
  - swingbot/core/market/entry_filters.py:gate_override
  - swingbot/core/scanning/strategy_pass.py:completed_frame
  - swingbot/core/scanning/strategy_pass.py:strategy_signals
  - swingbot/core/scanning/strategy_pass.py:run_strategy_pass
  - swingbot/core/scanning/scan_run.py:_maybe_run_strategy_pass
  - swingbot/core/planning/builders.py:build_strategy_plan
  - swingbot/core/planning/params.py:stamp_badge
  - swingbot/core/planning/stop_scope.py:risk_sizing_ok
  - swingbot/core/backtesting/registry.py:Badge
  - swingbot/core/backtesting/registry.py:get_badge
  - swingbot/admin/guide/live_strategies.py:badge_line
  - swingbot/config.py:STRATEGY_ALERTS_MODE
  - swingbot/config.py:STRATEGY_ALERTS_LIVE_STRATEGIES
---

> **In plain words** A strategy is a fixed entry rule, such as "the fast average crosses above the slow one", checked on the last finished daily bar. Each one has been measured on years of past prices, and its card below shows that record: how often it won, what it made per unit of risk, how many trades the figures rest on and when they were measured. Some strategies are kept for research only and cannot alert; their cards say so.

## Strategies are not level families

The level families of [chapter 4](/insights/guide/levels#level-families) draw prices. A [strategy](/insights/guide/glossary#strategy) decides when to enter: its rule either fires on the last finished bar or it does not, and it has its own measured record, its [badge](/insights/guide/glossary#badge). A few names appear in both lists, such as VWAP, Volume Profile and Fibonacci, because the same idea can draw a level or time an entry; the two uses are measured separately.

The bot has two ways to reach an alert. A level alert starts from support and resistance and is the path the [pipeline](/insights/guide/pipeline) and chapter 4 describe. A strategy alert starts from one of the rules on this page, and it has its own switch, described next.

<details><summary>Under the hood</summary>

The registered strategies are the union of `strategy.STRATEGY_FUNCS` and `strategy_types.STRATEGY_GATES`; `entry_filters.ENTRY_FUNCS` maps each of them to its entry function. `entries_for(strategy, df, horizon_key)` runs that function, then applies the direction and horizon mask (`strategy_types.admits`) and the regime gate of chapter 6.

</details>

## How a strategy alert is sent

One setting decides what a fired rule does. It is now {{STRATEGY_ALERTS_MODE}}.

| Mode | What happens when a rule fires |
|---|---|
| off | the strategy pass does not run; every alert comes from the level path |
| shadow | a full trade plan is built and stored, nothing is posted |
| live | the plan is stored, posted as an alert and opened as a [paper trade](/insights/guide/glossary#paper-trade) |

Shadow mode collects evidence without posting ([shadow mode](/insights/guide/glossary#shadow-mode)). In live mode only strategies on the live list post; that list is now: {{STRATEGY_ALERTS_LIVE_STRATEGIES}}. A ticker that already has an open trade gets no second one: the new plan is stored, not posted. A manual check from Discord never posts, whatever the mode.

Each scan the pass looks at every watchlist ticker on every live [horizon](/insights/guide/glossary#horizon), on finished daily bars only. During the session today's forming bar is dropped first, so a rule never fires on a bar that may still change (a [completed bar](/insights/guide/glossary#completed-bar)). One signal, meaning one ticker, strategy, horizon and bar, is stored once however many scans see it.

Between the signal and the alert sit a few checks. A short is dropped when the stock is not weak enough against the market (relative strength, chapter 6). Two vetoes, pullback volume and headroom, act only while their settings switch them on (chapter 6). The plan must exist: with no stop or no target that pays for the risk there is no alert (chapter 7). A plan that keeps a stop wider than the usual cap must also size to a fixed dollar risk, or it is not stored.

<details><summary>Under the hood</summary>

`scan_run._maybe_run_strategy_pass` reads `STRATEGY_ALERTS_MODE` and the allow-list `STRATEGY_ALERTS_LIVE_STRATEGIES` (empty means every strategy; the masked compression short must be named), forces shadow for a manual check, and calls `strategy_pass.run_strategy_pass` with `live_horizons()`. There `completed_frame` drops the forming bar, `strategy_signals` asks every entry function about the last bar, and `_emit_signal` runs `already_emitted`, the relative-strength laggard rule, the pullback dry-up veto, `build_strategy_plan`, the headroom veto and `stop_scope.risk_sizing_ok`, in that order.

</details>

## Reading a card

Every card has the same parts:

- **Status**: `live`, or `masked — research only` when no direction is allowed on any live horizon.
- **Long / Short**: the horizons the mask allows for each direction: a list, "every live horizon", or "—" for none. Where the rule itself fires can be narrower, and the card body then says so under **Where it fires**.
- **Badge**: the tier (VALIDATED or WEAK), the expectancy in R and the win rate, then where the figures come from: the backtest window that produced them (a TRAIN-window refresh or the later validation window), N, the run date, "costs not recorded" (the registry does not store whether trading costs were in that run) and "before tax". A live strategy without a measured row shows "no registry row" instead of an empty badge.
- **Idea**, **Entry rule** and **Where it fires**: the rule in words, written from the code. A card never types a performance figure; those come only from the badge line.

Many entry rules end with "the shared gates pass". These are five market-condition checks most strategies require on the signal bar; shorts use the downtrend versions:

- **Uptrend**: price is above its long-term moving average, and that average is rising.
- **Medium-term trend**: price is above its medium-term moving average.
- **Not dead flat**: the average true range (ATR) is at least a minimum share of the price.
- **Not panicking**: the ATR is not far above its own recent average.
- **Real volume**: the bar's volume is not well below its recent average.

The dip-buying RSI rule uses a looser trend test and skips the medium-term one. Every other gate is in chapter 6.

A badge is a measurement of the past, not a forecast. Read it with its [expectancy (ExpR)](/insights/guide/glossary#expectancy-expr), its window ([TRAIN and validation](/insights/guide/glossary#train-and-validation)) and its [provenance label](/insights/guide/glossary#provenance-label): a high win rate on a small N, or a TRAIN-window figure, says much less than it seems to.

<details><summary>Under the hood</summary>

`live_strategies.badge_line` builds the badge line from `registry.get_badge("strategy", key)`: `Badge.window` decides the window label, and a row with `n == 0` and no run date counts as no row. A strategy plan is stamped with the same badge by `params.stamp_badge`. The shared gates are the `bull_regime`, `trend50_bull`, `atr_floor`, `atr_calm` and `vol_ok` series of `entry_filters.compute_shared_gates` (bear variants for shorts); their thresholds are `ATR_FLOOR_PCT`, `ATR_CALM_MULT` and `VOL_OK_MULT` in `entry_filters.py`. The RSI rule reads `bull_regime_slope_only` instead.

</details>

## Masked strategies

A [masked](/insights/guide/glossary#masked) strategy keeps its rule and its research but cannot fire live: its [direction mask](/insights/guide/glossary#direction-mask) allows no direction on any live horizon, so its card reads "masked — research only". The shortest horizon is masked for every strategy by default; [the horizon table](/insights/guide/what-it-is#swing-horizons) shows which horizons are live.

A masked strategy has no row in the badge registry, so its card says "no registry row — masked, research only" and never shows a WEAK badge with no trades behind it. Leaving the mask takes a pre-registered test on prices the strategy was never tuned on; until one passes, it stays research only.

<details><summary>Under the hood</summary>

`admits(strategy, direction, horizon_key)` checks the strategy's named research cells first, then `MASKED_BY_DEFAULT_HORIZONS`, then the `directions` and horizons in `STRATEGY_GATES`. A research measurement opens one cell for one run with `entry_filters.gate_override`; the live scan never does.

</details>

## The cards

One card per registered strategy, in name order. Status, horizons and badge are read live; the text comes from the checked card files.

{{strategies.cards}}
````

- [ ] **Step 5: Regenerate the anchor fixture**

Run: `python scripts/dev/guide_anchors.py`
Then: `python scripts/dev/guide_anchors.py --check`
Expected: exit 0; the fixture gains `"strategies"` with the five `CH5_ANCHORS` (card `###` headings come from the placeholder and are not in it).

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: PASS (`0 failed`), including v236's `test_every_linked_chapter_is_written` and `test_glossary_defines_every_term_the_guide_links_to` over the new chapter.

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_content.py`
Expected: PASS — `[sources]`, `[placeholders]`, `[headings]`, the card checks and the anchor-fixture check.

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_guide.py`
Then: `python scripts/dev/testrun.py file tests/admin/test_guide_strategies.py`
Expected: PASS both. Chapter 5 now reads the committed `validation_registry.json` through `strategies.cards` (a file read, not the database); if the API test fails on it, patch `live_strategies._badge` in its autouse fixture as `_unmeasured_badges` does and report it.

If `[sources]` reports a symbol no longer defined, find its new home with `git grep -n`, fix the `sources:` entry and the matching "Under the hood" sentence, and report it.

- [ ] **Step 7: Commit**

```bash
git add docs/guide/05-strategies.md tests/admin/test_guide_chapter_text.py frontend/src/app/workspaces/guide/guide-anchors.json
git commit -m "docs(guide): chapter 5 -- strategies, the strategy alert path, reading a card (v237 V237-10)"
```

### Task V237-11: Chapter 6, part one: what a gate does, the live scan, masks, shared gates, regime

**Model:** sonnet — chapter text given whole below plus pinned text tests; the implementer re-verifies every `sources:` symbol and placeholder.

**Why.** Spec v215 § chapter 6: market regime, relative strength, direction masks, shared gates, horizon alignment, post-signal fill vetoes, and closed pre-registrations labelled "measured, not used", each with why it exists and the result behind it. Written from the code (index Handoff 5/6): every switchable gate takes its on/off state from `{{gates.switches}}` (V237-3) or a single-flag placeholder, never typed; the market regime is a confidence input, and its strategy gate lets everything through while `REGIME_ALLOW` is empty. Measured results are told in words, no figure typed (records: `docs/claude/backtest-methodology.md`). The chapter is split over two tasks to stay under the 20 KB task cap (SPLIT V237-11 → V237-11b): this task creates the file with its first five sections and the full `sources:` list; V237-11b appends relative strength, higher-horizon alignment, the post-signal fill vetoes and the switch table. **Merge both together**; V237-11b runs right after this task.

**Files:**
- Create: `docs/guide/06-gates.md`
- Modify (created by v236 V236-8): `tests/admin/test_guide_chapter_text.py` (append the chapter-6 tests)
- Regenerate: `frontend/src/app/workspaces/guide/guide-anchors.json`

**Interfaces:**
- Consumes: placeholders `gates.list` (V235-4), `SIGNAL_CONFIRMATION_SCANS`, `MIN_ALERT_CONFIDENCE_LEVEL` (V237-2); chapter anchors `strategies#reading-a-card`, `strategies#masked-strategies`, `strategies#how-a-strategy-alert-is-sent` (V237-10); test names `CH5_LINKABLE`, `_NO_PCT` (V237-10) and the v236 helpers.
- Produces: `docs/guide/06-gates.md` — slug `gates`, order 6, title `Filters and gates`, the full `sources:` list for both tasks, anchors `what-a-gate-does`, `gates-in-the-live-scan`, `direction-and-horizon-masks`, `shared-entry-gates`, `market-regime`; test names `CH6_ANCHORS` (V237-11b extends it to the ledger's nine) and `CH6_LINKABLE`.

Links: chapters `what-it-is`, `pipeline`, `glossary`, `levels`, `strategies` and this one; chapters 7 and 8 are named in plain text. Self-links name only headings this task writes; the sections V237-11b adds are referred to in words ("below", "the switch table at the end of this chapter").

- [ ] **Step 1: Confirm every source and placeholder exists**

Run: `git grep -n "^REGIME_ALLOW\|^def admits" swingbot/core/market/strategy_types.py; git grep -n "^def compute_shared_gates\|^def apply_regime_gate" swingbot/core/market/entry_filters.py; git grep -n "^def get_market_regime\|^def get_htf_bias" swingbot/core/scanning/regime.py; git grep -n "^def _confirmed\|^def _rs_blocked" swingbot/core/scanning/qualify.py; git grep -n "^def _rs_blocked" swingbot/core/scanning/strategy_pass.py`
Expected: nine lines.

Run: `git grep -n "^def rs_verdict" swingbot/core/edge/rs_gate.py; git grep -n "^def adjacent_aligned" swingbot/core/market/mtf.py; git grep -n "^def veto_bullish_for" swingbot/core/scanning/analyze.py; git grep -n "^def pullback_dryup_blocks\|^def headroom_active" swingbot/core/edge/gates.py; git grep -n "^def _build_requirement_checks" swingbot/core/scanning/requirements.py; git grep -n "^def enforce_gap_reclaim_coupling" swingbot/config.py; git grep -n "^SWITCH_ROWS" swingbot/admin/guide/live_switches.py`
Expected: eight lines (the last from V237-3).

Run: `git grep -c -e 'Field("REGIME_GATES_ENABLED"' -e 'Field("MARKET_REGIME_TICKER"' -e 'Field("RS_GATE"' -e 'Field("RS_LEADER_PERCENTILE"' -e 'Field("RS_LAGGARD_PERCENTILE"' -e 'Field("MTF_ADJACENT_GATE"' -e 'Field("HTF_CONFLUENCE_ENABLED"' -e 'Field("SIGNAL_CONFIRMATION_SCANS"' -e 'Field("MARKET_ENTRY_NEXT_OPEN"' -e 'Field("GAP_RECLAIM_ATR"' swingbot/config.py`
Expected: `swingbot/config.py:10` (on Windows Git Bash the count may print without the path; the number is what matters).

Run: `python -c "from swingbot.admin.guide import placeholders as p; need={'gates.list','SIGNAL_CONFIRMATION_SCANS','MIN_ALERT_CONFIDENCE_LEVEL'}; print(sorted(need-set(p.PLACEHOLDERS)))"`
Expected: `[]`.

Code facts this half states (read 2026-11-18): the legacy confidence scorer adds points for regime alignment and none against it (`scanning/confidence.py`, factor "Market regime alignment"); `apply_regime_gate` returns its input unchanged unless `REGIME_GATES_ENABLED` is set and `REGIME_ALLOW` names the strategy; `entries_for` zeroes a masked side right after the entry function. If one changed, correct its sentence and report it.

- [ ] **Step 2: Write the failing tests**

Append to `tests/admin/test_guide_chapter_text.py`:

```python
# --- chapter 6: gates (v237 V237-11, V237-11b) ------------------------------------------

CH6_ANCHORS = ["what-a-gate-does", "gates-in-the-live-scan", "direction-and-horizon-masks",
               "shared-entry-gates", "market-regime"]
CH6_LINKABLE = CH5_LINKABLE | {"gates"}


def test_chapter_6_header_and_plain_words_callout():
    chapter = _chapter("gates")
    assert (chapter.order, chapter.title) == (6, "Filters and gates")
    assert chapter.path.name == "06-gates.md"
    assert chapter.body.startswith("> **In plain words**")


def test_chapter_6_sections_in_order():
    assert _anchors(_chapter("gates")) == CH6_ANCHORS


def test_chapter_6_masks_come_from_the_live_table():
    section = _section(_chapter("gates").body, "Direction and horizon masks")
    assert "{{gates.list}}" in section
    assert "| Strategy | Long | Short | Status |" in placeholders.resolve(section)


def test_chapter_6_live_scan_numbers_are_placeholders():
    section = _section(_chapter("gates").body, "Gates in the live scan")
    assert {"SIGNAL_CONFIRMATION_SCANS", "MIN_ALERT_CONFIDENCE_LEVEL"} <= set(
        placeholders.names_in(section))


def test_chapter_6_regime_is_a_score_and_its_gate_reads_the_switch_table():
    section = _section(_chapter("gates").body, "Market regime")
    assert "a score, not a gate" in section
    assert "first row of the switch table" in section


def test_chapter_6_never_types_a_switch_state():
    assert not re.search(r"\b(?:is|are) (?:on|off)\b", _chapter("gates").body)


def test_chapter_6_resolves_and_links_only_written_chapters():
    chapter = _chapter("gates")
    assert "{{" not in placeholders.resolve(chapter.body)
    links = _GUIDE_LINK.findall(chapter.body)
    glossary = {anchor for slug, anchor in links if slug == "glossary"}
    assert glossary and glossary <= GLOSSARY_LINKED
    assert {slug for slug, _anchor in links} <= CH6_LINKABLE
    assert not _NO_PCT.search(re.sub(r"\{\{[^}]*\}\}", "", chapter.body))
```

The `Market regime` heading is the last one this task writes, so `_section(..., "Market regime")` runs to the end of the file here; after V237-11b it stops at `## Relative strength`, and the test still holds.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: FAIL — the seven chapter-6 tests report `docs/guide has no chapter 'gates'`; every earlier test passes.

- [ ] **Step 4: Write the first part of the chapter**

Create `docs/guide/06-gates.md` with exactly this text (UTF-8, LF, one trailing newline). The front matter already lists the sources V237-11b's sections describe; all exist today (Step 1).

````markdown
---
title: Filters and gates
slug: gates
order: 6
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/strategy_types.py:admits
  - swingbot/core/market/strategy_types.py:REGIME_ALLOW
  - swingbot/core/market/entry_filters.py:compute_shared_gates
  - swingbot/core/market/entry_filters.py:apply_regime_gate
  - swingbot/core/scanning/regime.py:get_market_regime
  - swingbot/core/scanning/regime.py:get_htf_bias
  - swingbot/core/scanning/confidence.py
  - swingbot/core/scanning/requirements.py:_build_requirement_checks
  - swingbot/core/scanning/qualify.py:_confirmed
  - swingbot/core/scanning/qualify.py:_rs_blocked
  - swingbot/core/scanning/strategy_pass.py:_rs_blocked
  - swingbot/core/edge/rs_gate.py:rs_verdict
  - swingbot/core/market/mtf.py:adjacent_aligned
  - swingbot/core/scanning/analyze.py:veto_bullish_for
  - swingbot/core/edge/gates.py:pullback_dryup_blocks
  - swingbot/core/edge/gates.py:headroom_active
  - swingbot/admin/guide/live_switches.py:SWITCH_ROWS
  - swingbot/config.py:enforce_gap_reclaim_coupling
  - swingbot/config.py:REGIME_GATES_ENABLED
  - swingbot/config.py:MARKET_REGIME_TICKER
  - swingbot/config.py:RS_GATE
  - swingbot/config.py:RS_LEADER_PERCENTILE
  - swingbot/config.py:RS_LAGGARD_PERCENTILE
  - swingbot/config.py:MTF_ADJACENT_GATE
  - swingbot/config.py:HTF_CONFLUENCE_ENABLED
  - swingbot/config.py:SIGNAL_CONFIRMATION_SCANS
  - swingbot/config.py:MARKET_ENTRY_NEXT_OPEN
  - swingbot/config.py:GAP_RECLAIM_ATR
---

> **In plain words** A gate is a yes-or-no check that can stop a setup from becoming an alert. It never moves a price; it only says "not this one". A gate is used live only after it helped on past prices it was not tuned on. Several gates were built, measured and found not to help: they stay in the code, unused, and the table at the end of this chapter shows which is which, read straight from the settings.

## What a gate does

A [gate](/insights/guide/glossary#gate) drops a setup; it never changes a plan's entry, stop or target. Each one exists because a measured group of past trades lost money or diluted the rest, and each is judged the same way: measured on one stretch of history, then tested once on a later stretch it was never tuned on ([TRAIN and validation](/insights/guide/glossary#train-and-validation)). A gate that passes ships; one that fails stays in the code, unused, so the result is not lost.

Fewer alerts is a cost, not a goal. A gate that raises the win rate but lowers what the average trade earns ([expectancy](/insights/guide/glossary#expectancy-expr)) is not used.

## Gates in the live scan

A level setup from [chapter 4](/insights/guide/levels) must pass:

- the level rules of chapter 4: minimum move, minimum stop distance, reward-to-risk and confluence count;
- confirmation: the same setup seen on {{SIGNAL_CONFIRMATION_SCANS}} consecutive scans before it alerts;
- relative strength (below);
- a confidence level of at least {{MIN_ALERT_CONFIDENCE_LEVEL}}, a score the [market regime](#market-regime) feeds;
- a trade plan that can be built within the stop rules (chapter 7), then the portfolio limits (chapter 8);
- every row of the switch table at the end of this chapter that reads "applied".

A strategy signal from [chapter 5](/insights/guide/strategies#how-a-strategy-alert-is-sent) must pass:

- the [direction and horizon masks](#direction-and-horizon-masks) and the [shared entry gates](#shared-entry-gates) its rule uses;
- for a short, relative strength;
- a plan that can be built within the stop rules (chapter 7);
- every row of the switch table that reads "applied".

<details><summary>Under the hood</summary>

Level setups: the level rules are `requirements._build_requirement_checks`, the confirmation debounce `qualify._confirmed`, the relative-strength block `qualify._rs_blocked` and its twin in `scan_run`. Strategy signals: `entries_for` applies the mask and the regime gate; `strategy_pass._emit_signal` applies the rest.

</details>

## Direction and horizon masks

Each strategy may trade only some directions on some horizons. The live mask, read from the code:

{{gates.list}}

A mask is not a filter on a finished signal: the rule's output is switched off before anything else sees it, so a masked cell produces no signal, no plan and no record. A cell is opened only where the strategy's measured record supports it; a [masked](/insights/guide/glossary#masked) strategy is closed everywhere ([chapter 5](/insights/guide/strategies#masked-strategies)). The glossary's [direction mask](/insights/guide/glossary#direction-mask) has the short version.

<details><summary>Under the hood</summary>

`strategy_types.admits` reads each strategy's `directions`, `horizons`, `horizons_by_direction` and research `cells` in `STRATEGY_GATES`, plus `MASKED_BY_DEFAULT_HORIZONS`. `entries_for` zeroes a masked side right after the entry function runs.

</details>

## Shared entry gates

The five shared gates defined in [chapter 5](/insights/guide/strategies#reading-a-card) are part of each strategy's own entry rule rather than a separate filter: uptrend, medium-term trend, a floor and a ceiling on the average daily range, and volume. They keep a rule from firing in a falling market, in dead-flat or panicking trade, or on a bar few people traded. A rule's card says which it uses; shorts use the downtrend versions.

Their thresholds are constants of the strategy code, not settings: changing one changes every strategy that uses it, and is measured as such.

<details><summary>Under the hood</summary>

`entry_filters.compute_shared_gates(df)` computes every gate once per frame; each entry function combines the series it needs. The thresholds are the module constants `ATR_FLOOR_PCT`, `ATR_CALM_MULT` and `VOL_OK_MULT`.

</details>

## Market regime

The [market regime](/insights/guide/glossary#market-regime) is the broad market's trend: the benchmark named by the setting `MARKET_REGIME_TICKER`, measured against its long-term average and that average's slope. In the live scan it is a score, not a gate: a level setup in line with the regime earns [confidence](/insights/guide/glossary#confidence) points, one against it earns none, and the confidence threshold does the rest.

A true regime gate exists for strategy signals: a table of which strategy may trade in which regime. When it was measured, no strategy-and-regime pair cleared the rule, so the table is empty and the gate lets everything through whatever its switch says. Its state is the first row of the switch table at the end of this chapter.

<details><summary>Under the hood</summary>

`regime.get_market_regime` compares the benchmark's close with its long EMA (`ema200` in the code) and that EMA's slope; the result feeds the "Market regime alignment" factor of `scanning/confidence.py`. The strategy gate is `entry_filters.apply_regime_gate`, active only with `REGIME_GATES_ENABLED` set and a non-empty `strategy_types.REGIME_ALLOW`.

</details>
````

- [ ] **Step 5: Regenerate the anchor fixture**

Run: `python scripts/dev/guide_anchors.py`
Then: `python scripts/dev/guide_anchors.py --check`
Expected: exit 0; the fixture gains `"gates": [...]` with the five `CH6_ANCHORS`, in order.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: PASS (`0 failed`), including v236's link and glossary checks over the new chapter.

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_content.py`
Then: `python scripts/dev/testrun.py file tests/admin/test_api_v1_guide.py`
Expected: PASS both — `[sources]`, `[placeholders]`, `[headings]` and the anchor-fixture check.

If `[sources]` reports a symbol no longer defined, find its new home with `git grep -n`, fix the `sources:` entry and the matching "Under the hood" sentence, and report it.

- [ ] **Step 7: Commit (V237-11b completes the chapter; merge both together)**

```bash
git add docs/guide/06-gates.md tests/admin/test_guide_chapter_text.py frontend/src/app/workspaces/guide/guide-anchors.json
git commit -m "docs(guide): chapter 6 part one -- gates, live scan, masks, shared gates, regime (v237 V237-11)"
```

### Task V237-11b: Chapter 6, part two: relative strength, alignment, fill vetoes, the switch table

**Model:** sonnet — four sections appended to a chapter, given whole below, plus pinned text tests for the live switch table.

**Why.** The rest of spec v215 § chapter 6. Relative strength has two arms whose thresholds are placeholders, because the long arm ships at its floor and only the short arm blocks (`RS_LEADER_PERCENTILE`, `RS_LAGGARD_PERCENTILE`). The adjacent-horizon gate and the post-signal fill vetoes are measured and not adopted, and their state comes from the table, never typed (index Handoff 5). The last section renders `{{gates.switches}}` and says in words what each closed measurement found: the dead-cat and headroom vetoes are "built but off by default". Second half of the SPLIT V237-11 → V237-11b; **merge both together**.

**Files:**
- Modify (created by V237-11): `docs/guide/06-gates.md` (append four sections)
- Modify (created by v236 V236-8): `tests/admin/test_guide_chapter_text.py` (`CH6_ANCHORS`, four new tests)
- Regenerate: `frontend/src/app/workspaces/guide/guide-anchors.json`

**Interfaces:**
- Consumes: V237-11's chapter file (its front matter already lists `rs_gate.py:rs_verdict`, both `_rs_blocked`, `mtf.py:adjacent_aligned`, `regime.py:get_htf_bias`, `gates.py:pullback_dryup_blocks`/`headroom_active`, `analyze.py:veto_bullish_for`, `live_switches.py:SWITCH_ROWS`, `config.py:enforce_gap_reclaim_coupling` and the config fields used here) and its tests (`CH6_ANCHORS`, the no-state, link and no-percent tests, which now cover the new sections too); placeholders `gates.switches`, `live_switches.SWITCH_ROWS` (`.label`), `RS_GATE`, `RS_LEADER_PERCENTILE`, `RS_LAGGARD_PERCENTILE`, `HTF_CONFLUENCE_ENABLED` (V237-3/3b); chapter anchor `levels#higher-horizon-alignment` (V237-9b).
- Produces (ledger): the chapter's nine anchors — V237-11's five plus `relative-strength`, `higher-horizon-alignment`, `post-signal-fill-vetoes`, `measured-not-used`.

- [ ] **Step 1: Confirm the consumed names**

Run: `git grep -n "^## Market regime" docs/guide/06-gates.md; git grep -n "^CH6_ANCHORS" tests/admin/test_guide_chapter_text.py`
Expected: one line each (V237-11).

Run: `python -c "from swingbot.admin.guide import placeholders as p, live_switches as ls; need={'gates.switches','RS_GATE','RS_LEADER_PERCENTILE','RS_LAGGARD_PERCENTILE','HTF_CONFLUENCE_ENABLED'}; print(sorted(need-set(p.PLACEHOLDERS)), [r.label for r in ls.SWITCH_ROWS][:5])"`
Expected: `[] ['Market regime gate', 'Adjacent-horizon alignment', 'Relative strength, long arm', 'Relative strength, short arm', 'Dead-cat bounce veto']`.

Code facts this half states (read 2026-11-18): `strategy_pass._rs_blocked` checks bearish signals only and does not read `RS_GATE`; the level path checks it only while `RS_GATE` is set (`qualify._rs_blocked`, `scan_run`); `rs_verdict` exempts symbols `is_rs_eligible` rejects and scans without a benchmark reading; `get_htf_bias` returns None while `HTF_CONFLUENCE_ENABLED` is off and only flags the alert; `adjacent_aligned` drops only an "opposed" verdict; `config.enforce_gap_reclaim_coupling` zeroes `GAP_RECLAIM_ATR` with an error log when `MARKET_ENTRY_NEXT_OPEN` is off. The findings list rests on the closed rows of `docs/claude/backtest-methodology.md` (`DEAD_CAT_BOUNCE_VETO` v68, headroom v135, pullback dry-up v122, `EARNINGS_BLACKOUT_SESSIONS` v82, the v84 S/R, MA Ribbon and RSI Divergence axes, `FVG_LEVELS_MODE` v128, `DATA_DRIVEN_STOPS_ENABLED`, `STALL_EXIT_ENABLED`, `RUNNER_STRUCTURE_EXIT` v123, the reclaim veto v192, `RS_GATE` v34). If one changed, correct its sentence and report it.

- [ ] **Step 2: Write the failing tests**

In `tests/admin/test_guide_chapter_text.py`, replace the `CH6_ANCHORS = [...]` assignment V237-11 wrote with:

```python
CH6_ANCHORS = ["what-a-gate-does", "gates-in-the-live-scan", "direction-and-horizon-masks",
               "shared-entry-gates", "market-regime", "relative-strength",
               "higher-horizon-alignment", "post-signal-fill-vetoes", "measured-not-used"]
```

Then append after the chapter-6 tests:

```python
def test_chapter_6_switch_table_lists_every_row():
    from swingbot.admin.guide import live_switches
    section = _section(_chapter("gates").body, "Measured, not used")
    assert "{{gates.switches}}" in section
    rendered = placeholders.resolve(section)
    assert "| Gate | Setting | Now | In the live scan |" in rendered
    assert all(f"| {row.label} |" in rendered for row in live_switches.SWITCH_ROWS)


@pytest.mark.parametrize("value, verdict", [(False, "measured, not used"), (True, "applied")])
def test_chapter_6_switch_state_follows_the_setting(monkeypatch, value, verdict):
    from swingbot import config
    monkeypatch.setattr(config, "DEAD_CAT_BOUNCE_VETO", value)
    rendered = placeholders.resolve(_section(_chapter("gates").body, "Measured, not used"))
    row = next(line for line in rendered.splitlines()
               if line.startswith("| Dead-cat bounce veto |"))
    assert row.endswith(f"| {verdict} |")


@pytest.mark.parametrize("heading, names", [
    ("Relative strength", {"RS_GATE", "RS_LEADER_PERCENTILE", "RS_LAGGARD_PERCENTILE"}),
    ("Higher-horizon alignment", {"HTF_CONFLUENCE_ENABLED"}),
])
def test_chapter_6_switch_values_are_placeholders(heading, names):
    assert names <= set(placeholders.names_in(_section(_chapter("gates").body, heading)))


def test_chapter_6_names_the_built_but_unused_vetoes():
    section = _section(_chapter("gates").body, "Measured, not used")
    assert "dead-cat bounce veto" in section and "headroom veto" in section
    assert "built but off by default" in section
    assert "whatever this list says" in section   # the table, not the prose, decides
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: FAIL — `test_chapter_6_sections_in_order` (five anchors found, nine expected) and the six new test cases (`IndexError` from `_section`: no such heading); every other test passes.

- [ ] **Step 4: Append the four sections**

Append exactly this text to `docs/guide/06-gates.md`, after the `Market regime` section's closing `</details>` and one blank line (UTF-8, LF, the file still ends with one trailing newline):

````markdown
## Relative strength

[Relative strength](/insights/guide/glossary#relative-strength) ranks a stock's recent move against the benchmark and its sector, as a percentile of the scanned universe. The gate's switch reads {{RS_GATE}}, and it has two arms:

- **Long arm**: a long needs a percentile of at least {{RS_LEADER_PERCENTILE}}. When measured, this arm cut good trades with the bad at every threshold tried, so it ships at its floor, where every long passes.
- **Short arm**: a short needs a percentile of at most {{RS_LAGGARD_PERCENTILE}}: the bot shorts laggards, not leaders. This arm passed its validation test with a small win-rate gain for a small cut in alerts: a measured improvement, not a large edge.

ETFs and other symbols without a meaningful benchmark comparison are exempt, as is every setup in a scan where the benchmark could not be fetched.

<details><summary>Under the hood</summary>

`edge/rs_gate.rs_verdict` returns pass, block or exempt. Level setups are checked in `scan_run` and `qualify._rs_blocked` while `RS_GATE` is set; the strategy pass checks bearish signals only, in `strategy_pass._rs_blocked`, without reading `RS_GATE`.

</details>

## Higher-horizon alignment

Two readings compare a setup with the trend of a longer horizon ([chapter 4](/insights/guide/levels#higher-horizon-alignment)):

- **Adjacent-horizon gate**: drops a setup when the next horizon up trends against it, such as a short-horizon long while the longer horizon falls. In its validation test it lowered the win rate slightly and was not adopted; whether it applies now is in [the switch table](#measured-not-used).
- **Higher-timeframe bias**, now {{HTF_CONFLUENCE_ENABLED}}: compares the stock with its own longer moving average and marks a counter-trend alert with a warning. It informs the reader and blocks nothing.

<details><summary>Under the hood</summary>

The gate is `mtf.adjacent_aligned`, called in `analyze` only while `MTF_ADJACENT_GATE` is set; only an "opposed" verdict drops a scenario. The bias is `regime.get_htf_bias`, computed only while `HTF_CONFLUENCE_ENABLED` is set.

</details>

## Post-signal fill vetoes

Two linked settings change how a market plan is filled once the signal is decided. The first makes the plan wait for the next session's open instead of entering at the scan price. The second adds a veto: if that open has already gapped toward the stop by a set multiple of the ATR, the plan waits for price to come back to its planned entry during that session, or is cancelled at the close. The second works only with the first; set alone, it is ignored and an error is logged.

Because they act after the signal, they are judged as a change to the fill, not as a new entry idea. Measured, the reclaim veto raised the win rate but cut the average result per trade, because the trades it re-priced turned from winners into roughly break-even ones; it was not adopted. Its state is the "Next-open market entry and gap reclaim" row of [the switch table](#measured-not-used).

<details><summary>Under the hood</summary>

The settings are `MARKET_ENTRY_NEXT_OPEN` and `GAP_RECLAIM_ATR`; `config.enforce_gap_reclaim_coupling` zeroes the reclaim threshold, with an error log, while next-open entry is not set.

</details>

## Measured, not used

Every gate and exit rule that was built and measured, with its settings, their values now and whether the live scan applies the rule. The table is read from the settings each time the page loads, so a switch flipped on the server shows here at once:

{{gates.switches}}

"Measured, not used" means the rule is in the code and was tested, and the test did not justify using it. What the measurements found:

- The dead-cat bounce veto (no long when the chart looks like a dead-cat bounce) and the headroom veto (no setup when another level blocks the path to the first target) are built but off by default. The first passed its first stage and failed validation; the second showed no lift for strategies and changed nothing measurable for level setups.
- The pullback volume dry-up veto showed no lift for either path.
- No earnings blackout window cleared the rule.
- Minimum touches for Support/Resistance, extra confirm bars for MA Ribbon and a longer turn for RSI Divergence each measured below the bar the strategy already clears; the fair value gap level modes were refused at the first stage.
- Data-driven stops and the stall exit could not be measured as built, and the runner structure exit was refused at its early stages; none of them is adopted.

A row that reads "applied" is in use, whatever this list says about how it was measured.

<details><summary>Under the hood</summary>

`live_switches.SWITCH_ROWS` lists each row's settings and the test that decides "applied". The full records are the closed pre-registration rows in `docs/claude/backtest-methodology.md`.

</details>
````

- [ ] **Step 5: Regenerate the anchor fixture**

Run: `python scripts/dev/guide_anchors.py`
Then: `python scripts/dev/guide_anchors.py --check`
Expected: exit 0; `"gates"` now lists the nine `CH6_ANCHORS`, in order.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: PASS (`0 failed`), including V237-11's no-state, link and no-percent tests over the whole chapter and v236's self-link check (`#measured-not-used` is now a heading).

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_content.py`
Then: `python scripts/dev/testrun.py file tests/admin/test_api_v1_guide.py`
Expected: PASS both.

- [ ] **Step 7: Commit (merge together with V237-11)**

```bash
git add docs/guide/06-gates.md tests/admin/test_guide_chapter_text.py frontend/src/app/workspaces/guide/guide-anchors.json
git commit -m "docs(guide): chapter 6 part two -- relative strength, alignment, fill vetoes, switch table (v237 V237-11b)"
```

### Task V237-12: Chapter 7, part one: entry, the stop, the cap and the clamp

**Model:** sonnet — chapter text given whole below plus pinned text tests; the implementer re-verifies every `sources:` symbol and placeholder.

**Why.** Spec v215 § chapter 7: entry, structural and ATR stops, the stop never widens after entry, structural stops bounded by the cap live and in backtests, the minimum-stop rule, targets that pay for the risk, scale-out, exit model v2. Written from the code, not the spec (index Handoff 6): stops are built in `planning/builders.py`, `planning/stop_scope.py`, `planning/lifecycle.py` and `core/risk_limits.py`; `edge/stops.py` is named only as measured, not used. The hard cap is the constant `HARD_MAX_PLANNED_LOSS_PCT`; scenario admission uses the larger of `MAX_STOP_LOSS_PCT` and the horizon's `max_risk_pct` (`gating.scenario_gate_inputs`), so the chapter never claims the setting is what binds. No bare number before `%` (order 7, `[bare percent]`); every rule number is a placeholder. The chapter is split over two tasks to stay under the 20 KB task cap (SPLIT V237-12 → V237-12b): this task creates the file with its first three sections and the full `sources:` list; V237-12b appends the never-widen rule, targets, scale-out, how a plan closes and the backtest parity section. **Merge both together**; V237-12b runs right after this task.

**Files:**
- Create: `docs/guide/07-trade-plan.md`
- Modify (created by v236 V236-8): `tests/admin/test_guide_chapter_text.py` (append the chapter-7 tests)
- Regenerate: `frontend/src/app/workspaces/guide/guide-anchors.json`

**Interfaces:**
- Consumes: placeholders `MIN_STOP_DISTANCE_PCT`, `MAX_STOP_LOSS_PCT`, `CLAMP_STOP_TO_HARD_CAP` (V235-3), `stop.hard_cap`, `stop.clamp_level`, `plan.expiry_bars` (V237-2), `LEVEL_LIFECYCLE_STOPS_ENABLED` (V237-3b); chapter anchors `levels#the-next-level-idea`, `levels#touch-break-and-the-four-states` (V237-9), `strategies#the-cards` (V237-10), `gates#post-signal-fill-vetoes`, `gates#measured-not-used` (V237-11b); test names `CH6_LINKABLE`, `_NO_PCT` (V237-10/11) and the v236 helpers.
- Produces: `docs/guide/07-trade-plan.md` — slug `trade-plan`, order 7, title `Building the trade plan`, the full `sources:` list for both tasks, anchors `entry`, `the-stop`, `the-stop-distance-cap-and-the-clamp`; test names `CH7_ANCHORS` (V237-12b extends it to the ledger's eight) and `CH7_LINKABLE`.

Links: chapters `what-it-is`, `pipeline`, `glossary`, `levels`, `strategies`, `gates` and this one; chapter 8 is named in plain text. The one self-link (`#the-stop-distance-cap-and-the-clamp`) names a heading this task writes.

- [ ] **Step 1: Confirm every source and placeholder exists**

Run: `git grep -n "^def build_confluence_plan\|^def build_strategy_plan\|^def scenario_is_breakout\|^def confluence_stop_geometry\|^def _clamp_stop_to_hard_cap\|^CLAMP_HEADROOM_PCT\|^_STRUCTURAL_BRANCHES = \|^def _atr_branch\|^def _bounded_stop\|^def _confluence_tp2" swingbot/core/planning/builders.py`
Expected: ten lines.

Run: `git grep -n "^HARD_MAX_PLANNED_LOSS_PCT\|^def capped_planned_loss_pct" swingbot/core/risk_limits.py; git grep -n "^def scenario_gate_inputs" swingbot/core/scanning/gating.py; git grep -n "^def stop_ceiling\|^def plan_stop_ceiling\|^def risk_sizing_ok" swingbot/core/planning/stop_scope.py; git grep -n "^def apply_level_lifecycle\|^def pending_invalidated" swingbot/core/planning/lifecycle.py; git grep -n "^def select_structural_target\|^def select_tp2" swingbot/core/planning/targets.py; git grep -n "^def clears" swingbot/core/planning/reward_floor.py`
Expected: eleven lines.

Run: `git grep -n "^TP1_FRACTION\|^RUNNER_FLOOR_FRACTION\|^TRAIL_ATR_MULT\|^DEFAULT_EXPIRY_BARS\|^PLAN_SHAPES\|^def exit_params_for" swingbot/core/planning/params.py; git grep -n "^BREAKEVEN_TRIGGER_FRACTION" swingbot/core/market/strategy_types.py; git grep -n "^def runner_floor\|^def chandelier_stop\|^def giveback_stop\|^def tighter_stop" swingbot/core/planning/exit_sim.py; git grep -n "^def simulate_exit_v2(" swingbot/core/planning/exit_sim_v2.py`
Expected: twelve lines.

Run: `git grep -n "    def _step_pending\|    def _fill_pending\|    def _step_active\|    def _step_partial" swingbot/core/planning/plan_manager.py; git grep -n "    def update" swingbot/core/planning/plan_store.py; git grep -n "^def attach_plan_v2" swingbot/core/scanning/analyze.py; ls swingbot/core/edge/stops.py`
Expected: six lines, then the path.

Run: `git grep -c -e 'Field("MIN_STOP_DISTANCE_PCT"' -e 'Field("MAX_STOP_LOSS_PCT"' -e 'Field("CLAMP_STOP_TO_HARD_CAP"' -e 'Field("MIN_RISK_REWARD_RATIO"' -e 'Field("MAX_RISK_REWARD_RATIO"' -e 'Field("MIN_REWARD_PCT"' -e 'Field("STRUCTURAL_STOP_SCOPE"' -e 'Field("RUNNER_GIVEBACK_ENABLED"' -e 'Field("DATA_DRIVEN_STOPS_ENABLED"' -e 'Field("PLAN_ENGINE_V2"' swingbot/config.py`
Expected: `10` (with or without the path prefix).

Run: `python -c "from swingbot.admin.guide import placeholders as p; need={'MIN_STOP_DISTANCE_PCT','MAX_STOP_LOSS_PCT','CLAMP_STOP_TO_HARD_CAP','stop.hard_cap','stop.clamp_level','plan.expiry_bars','LEVEL_LIFECYCLE_STOPS_ENABLED'}; print(sorted(need-set(p.PLACEHOLDERS)))"`
Expected: `[]`.

Code facts this half states (read 2026-11-18): `_clamp_stop_to_hard_cap` moves a confluence stop past the cap to `HARD_MAX_PLANNED_LOSS_PCT - CLAMP_HEADROOM_PCT` only while `CLAMP_STOP_TO_HARD_CAP` is set; `_bounded_stop` caps a strategy stop at `stop_ceiling`'s value, or returns None (drop) for the `stop_scope._ALWAYS_IN_SCOPE` group (shorts, Turtle Soup) whose ceiling is the horizon's `max_risk_pct`; `_fill_pending` cancels `risk_cap` past `plan_stop_ceiling`; the minimum stop distance applies to level scenarios only (`build_strategy_plan`'s `_geometry_ok` checks a non-zero stop and the reward floor). If one changed, correct its sentence and report it.

- [ ] **Step 2: Write the failing tests**

Append to `tests/admin/test_guide_chapter_text.py`:

```python
# --- chapter 7: trade plan (v237 V237-12, V237-12b) -------------------------------------

CH7_ANCHORS = ["entry", "the-stop", "the-stop-distance-cap-and-the-clamp"]
CH7_LINKABLE = CH6_LINKABLE | {"trade-plan"}


def test_chapter_7_header_and_plain_words_callout():
    chapter = _chapter("trade-plan")
    assert (chapter.order, chapter.title) == (7, "Building the trade plan")
    assert chapter.path.name == "07-trade-plan.md"
    assert chapter.body.startswith("> **In plain words**")


def test_chapter_7_sections_in_order():
    assert _anchors(_chapter("trade-plan")) == CH7_ANCHORS


@pytest.mark.parametrize("heading, names", [
    ("Entry", {"plan.expiry_bars"}),
    ("The stop", {"MIN_STOP_DISTANCE_PCT", "LEVEL_LIFECYCLE_STOPS_ENABLED"}),
    ("The stop-distance cap and the clamp",
     {"stop.hard_cap", "stop.clamp_level", "MAX_STOP_LOSS_PCT", "CLAMP_STOP_TO_HARD_CAP"}),
])
def test_chapter_7_rule_numbers_are_placeholders(heading, names):
    assert names <= set(placeholders.names_in(_section(_chapter("trade-plan").body, heading)))


def test_chapter_7_clamp_renders_the_live_numbers():
    from swingbot.core.planning.builders import CLAMP_HEADROOM_PCT
    from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT
    section = _section(_chapter("trade-plan").body, "The stop-distance cap and the clamp")
    rendered = placeholders.resolve(section)
    assert f"{HARD_MAX_PLANNED_LOSS_PCT:g}%" in rendered
    assert f"{HARD_MAX_PLANNED_LOSS_PCT - CLAMP_HEADROOM_PCT:g}%" in rendered
    assert "`risk_cap`" in section


def test_chapter_7_names_edge_stops_only_as_not_adopted():
    body = _chapter("trade-plan").body
    assert "`edge/stops.py`" in body and "DATA_DRIVEN_STOPS_ENABLED" in body
    assert "](/insights/guide/gates#measured-not-used)" in body
    # The live plan manager scales out whenever tp1_fraction < 1; SCALE_OUT_ENABLED has no
    # live reader (scan_params.scale_out_enabled is never read), so the chapter does not cite it.
    assert "SCALE_OUT_ENABLED" not in body


def test_chapter_7_resolves_and_links_only_written_chapters():
    chapter = _chapter("trade-plan")
    assert "{{" not in placeholders.resolve(chapter.body)
    links = _GUIDE_LINK.findall(chapter.body)
    glossary = {anchor for slug, anchor in links if slug == "glossary"}
    assert glossary and glossary <= GLOSSARY_LINKED
    assert {slug for slug, _anchor in links} <= CH7_LINKABLE
    assert not _NO_PCT.search(re.sub(r"\{\{[^}]*\}\}", "", chapter.body))
```

`_section(body, "The stop")` matches only the `## The stop\n` line, not the longer headings that start with the same words.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: FAIL — the chapter-7 tests report `docs/guide has no chapter 'trade-plan'`; every earlier test passes.

- [ ] **Step 4: Write the first part of the chapter**

Create `docs/guide/07-trade-plan.md` with exactly this text (UTF-8, LF, one trailing newline). The front matter already lists the sources V237-12b's sections describe; all exist today (Step 1).

````markdown
---
title: Building the trade plan
slug: trade-plan
order: 7
reviewed_for: 2.19.2
sources:
  - swingbot/core/planning/builders.py:build_confluence_plan
  - swingbot/core/planning/builders.py:build_strategy_plan
  - swingbot/core/planning/builders.py:scenario_is_breakout
  - swingbot/core/planning/builders.py:confluence_stop_geometry
  - swingbot/core/planning/builders.py:_clamp_stop_to_hard_cap
  - swingbot/core/planning/builders.py:CLAMP_HEADROOM_PCT
  - swingbot/core/planning/builders.py:_STRUCTURAL_BRANCHES
  - swingbot/core/planning/builders.py:_atr_branch
  - swingbot/core/planning/builders.py:_bounded_stop
  - swingbot/core/planning/builders.py:_confluence_tp2
  - swingbot/core/risk_limits.py:HARD_MAX_PLANNED_LOSS_PCT
  - swingbot/core/risk_limits.py:capped_planned_loss_pct
  - swingbot/core/scanning/gating.py:scenario_gate_inputs
  - swingbot/core/planning/stop_scope.py:stop_ceiling
  - swingbot/core/planning/stop_scope.py:plan_stop_ceiling
  - swingbot/core/planning/stop_scope.py:risk_sizing_ok
  - swingbot/core/planning/lifecycle.py:apply_level_lifecycle
  - swingbot/core/planning/lifecycle.py:pending_invalidated
  - swingbot/core/planning/targets.py:select_structural_target
  - swingbot/core/planning/targets.py:select_tp2
  - swingbot/core/planning/reward_floor.py:clears
  - swingbot/core/planning/params.py:TP1_FRACTION
  - swingbot/core/planning/params.py:RUNNER_FLOOR_FRACTION
  - swingbot/core/planning/params.py:TRAIL_ATR_MULT
  - swingbot/core/planning/params.py:DEFAULT_EXPIRY_BARS
  - swingbot/core/planning/params.py:PLAN_SHAPES
  - swingbot/core/planning/params.py:exit_params_for
  - swingbot/core/market/strategy_types.py:BREAKEVEN_TRIGGER_FRACTION
  - swingbot/core/planning/exit_sim.py:runner_floor
  - swingbot/core/planning/exit_sim.py:chandelier_stop
  - swingbot/core/planning/exit_sim.py:giveback_stop
  - swingbot/core/planning/exit_sim.py:tighter_stop
  - swingbot/core/planning/exit_sim_v2.py:simulate_exit_v2
  - swingbot/core/planning/plan_manager.py:PlanManager._step_pending
  - swingbot/core/planning/plan_manager.py:PlanManager._fill_pending
  - swingbot/core/planning/plan_manager.py:PlanManager._step_active
  - swingbot/core/planning/plan_manager.py:PlanManager._step_partial
  - swingbot/core/planning/plan_store.py:PlanStore.update
  - swingbot/core/scanning/analyze.py:attach_plan_v2
  - swingbot/core/edge/stops.py
  - swingbot/config.py:MIN_STOP_DISTANCE_PCT
  - swingbot/config.py:MAX_STOP_LOSS_PCT
  - swingbot/config.py:CLAMP_STOP_TO_HARD_CAP
  - swingbot/config.py:MIN_RISK_REWARD_RATIO
  - swingbot/config.py:MAX_RISK_REWARD_RATIO
  - swingbot/config.py:MIN_REWARD_PCT
  - swingbot/config.py:STRUCTURAL_STOP_SCOPE
  - swingbot/config.py:RUNNER_GIVEBACK_ENABLED
  - swingbot/config.py:DATA_DRIVEN_STOPS_ENABLED
  - swingbot/config.py:PLAN_ENGINE_V2
---

> **In plain words** A trade plan is the full set of numbers an alert carries: where to get in, where the idea is wrong (the stop), where to take profit (one or two targets), and how the stop follows the trade once it moves your way. The stop comes from the chart, is never further from the entry than a fixed cap, and never moves against you after entry. A target must pay enough for the risk taken, or there is no trade at all.

## Entry

A plan enters in one of three ways (see [entry](/insights/guide/glossary#entry)):

| Entry | When | Fills |
|---|---|---|
| market | the setup is already in place | at the price the scan saw |
| stop entry | the target lies beyond the recent trading range, so the trade needs a breakout | when price trades through the trigger |
| limit | a few strategies buy a pullback or sell a rally | when price comes back to the limit |

A stop-entry or limit plan waits. A level plan that has not filled within {{plan.expiry_bars}} is cancelled as expired; some strategy plans carry a shorter window. A waiting plan is also cancelled when price closes through its stop before the entry fires (the idea broke before the trade began), and when the fill itself would leave the stop further away than [the stop-distance cap](#the-stop-distance-cap-and-the-clamp) allows.

<details><summary>Under the hood</summary>

`builders.scenario_is_breakout` gives a level plan a stop entry when reaching its target needs a new extreme of the recent range; every other level plan is a market plan. Strategy plans take their entry type and waiting window from `params.PLAN_SHAPES` or its defaults. A waiting plan is stepped by `PlanManager._step_pending` (expiry, then `lifecycle.pending_invalidated`); `PlanManager._fill_pending` cancels with reason `risk_cap` when the planned loss from the fill exceeds `stop_scope.plan_stop_ceiling`. The setting that makes market plans wait for the next open is in [chapter 6](/insights/guide/gates#post-signal-fill-vetoes).

</details>

## The stop

The [stop](/insights/guide/glossary#stop) is where the trade idea is wrong, so it comes from the chart, never from a fixed percentage:

- **Level plans** put it beyond the level the setup leans on: the nearest support under a long, the nearest resistance over a short ([chapter 4](/insights/guide/levels#the-next-level-idea)). A level setup whose stop sits closer than {{MIN_STOP_DISTANCE_PCT}} to the entry is inside ordinary daily noise and is dropped before it is scored.
- **Strategy plans** use the structure the strategy reads (a swing point, a Fibonacci level, a broken range) for Fibonacci, Support/Resistance, Elliott Wave and the research strategies, and a multiple of the average true range (ATR), set per horizon, for every other strategy. Level-lifecycle stops are {{LEVEL_LIFECYCLE_STOPS_ENABLED}}; when on, a strategy plan's stop then moves beyond a tested level ([chapter 4](/insights/guide/levels#touch-break-and-the-four-states)).

Stops sized from how far past winners moved against their entry exist in the code and were not adopted ([chapter 6](/insights/guide/gates#measured-not-used)).

<details><summary>Under the hood</summary>

Level stops come from `levels.build_scenarios(..., min_stop_distance_pct=MIN_STOP_DISTANCE_PCT)`. Strategy stops: `builders._STRUCTURAL_BRANCHES` names the structural strategies, and `builders._atr_branch` serves the rest with the horizon's `atr_stop_multiple`; `lifecycle.apply_level_lifecycle` makes the move while `LEVEL_LIFECYCLE_STOPS_ENABLED` is set. `edge/stops.py` holds the MAE-informed helpers used only with `DATA_DRIVEN_STOPS_ENABLED`; it builds no stop.

</details>

## The stop-distance cap and the clamp

The distance from entry to stop, as a share of the entry price, has a hard cap of {{stop.hard_cap}} ([stop-distance cap](/insights/guide/glossary#stop-distance-cap)). The cap is a constant in the code, not a setting; the setting for the maximum stop distance, now {{MAX_STOP_LOSS_PCT}}, cannot go above it. Setups are first admitted with the horizon's own, wider stop ceiling, so that historical replays see the same candidates; the cap is applied when the plan is built.

A level plan whose stop lies beyond the cap is [clamped](/insights/guide/glossary#clamp) while the clamp setting is {{CLAMP_STOP_TO_HARD_CAP}}: its stop moves in to {{stop.clamp_level}} from the entry, a little inside the cap, so a fill slightly past the trigger is still allowed. The target is then chosen again against the smaller risk, and if no level pays enough the setup is dropped. Without the clamp such a plan is [rejected](/insights/guide/glossary#rejected-plan) with reason `risk_cap` and logged as `plan rejected (risk_cap, stop … from entry) -- not posted`.

A strategy plan whose stop lies beyond its ceiling has the stop moved in to the ceiling. A few research strategies whose stop is the structure itself, the shorts and Turtle Soup, keep their stop up to the horizon's own ceiling or are dropped, and must then size to a fixed dollar risk; their [cards](/insights/guide/strategies#the-cards) say whether they can fire live.

Live, the cap is checked once more at the fill: a fill far enough past the trigger to put the stop beyond the ceiling cancels the plan (`risk_cap`).

<details><summary>Under the hood</summary>

`risk_limits.HARD_MAX_PLANNED_LOSS_PCT` is the cap; `capped_planned_loss_pct` takes the stricter of it and a configured value. Scenario admission uses the larger of `MAX_STOP_LOSS_PCT` and the horizon's `max_risk_pct` (`gating.scenario_gate_inputs`). The clamp is `builders._clamp_stop_to_hard_cap` (cap minus `CLAMP_HEADROOM_PCT`), called through `confluence_stop_geometry`; `analyze.attach_plan_v2` rejects a plan past `stop_scope.plan_stop_ceiling` as `risk_cap`. Strategy stops pass `builders._bounded_stop`, which caps or drops by `stop_scope.stop_ceiling` (`STRUCTURAL_STOP_SCOPE` can add pairs to the drop group); `stop_scope.risk_sizing_ok` enforces the fixed dollar risk.

</details>
````

- [ ] **Step 5: Regenerate the anchor fixture**

Run: `python scripts/dev/guide_anchors.py`
Then: `python scripts/dev/guide_anchors.py --check`
Expected: exit 0; the fixture gains `"trade-plan": [...]` with the three `CH7_ANCHORS`, in order.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: PASS (`0 failed`), including v236's link and glossary checks over the new chapter.

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_content.py`
Then: `python scripts/dev/testrun.py file tests/admin/test_api_v1_guide.py`
Expected: PASS both — `[bare percent]` now runs live over chapter 7, with `[sources]`, `[placeholders]`, `[headings]` and the anchor-fixture check.

If `[sources]` reports a symbol no longer defined, find its new home with `git grep -n`, fix the `sources:` entry and the matching "Under the hood" sentence, and report it.

- [ ] **Step 7: Commit (V237-12b completes the chapter; merge both together)**

```bash
git add docs/guide/07-trade-plan.md tests/admin/test_guide_chapter_text.py frontend/src/app/workspaces/guide/guide-anchors.json
git commit -m "docs(guide): chapter 7 part one -- entry, stops, the cap and the clamp (v237 V237-12)"
```

### Task V237-12b: Chapter 7, part two: never widens, targets, scale-out, how a plan closes, backtest parity

**Model:** sonnet — five sections appended to a chapter, given whole below, plus pinned text tests.

**Why.** The rest of spec v215 § chapter 7: the stop never widens after entry (every move takes the tighter stop; `PlanStore.update` refuses a looser one; a gap can still pass it), targets that must pay for the risk (nearest level at the minimum reward-to-risk, a synthetic TP1 at the maximum, no fallback), scale-out and the runner (break-even move, TP1 share, runner floor, chandelier trail, give-back), how a plan closes, and exit model v2 as the backtest's twin of the live plan. Written from the code (index Handoff 6, brief T4): a TP2 exists only where `exit_params_for(strategy)["tp2"]` or the level map gives one; the live plan manager scales out whenever a plan's TP1 share is below the whole position, so the chapter does not cite `SCALE_OUT_ENABLED` (no live reader, see the task report note below). Second half of the SPLIT V237-12 → V237-12b; **merge both together**.

**Files:**
- Modify (created by V237-12): `docs/guide/07-trade-plan.md` (append five sections)
- Modify (created by v236 V236-8): `tests/admin/test_guide_chapter_text.py` (`CH7_ANCHORS`, four new tests)
- Regenerate: `frontend/src/app/workspaces/guide/guide-anchors.json`

**Interfaces:**
- Consumes: V237-12's chapter file (its front matter already lists `targets.py`, `reward_floor.py:clears`, `params.py` names, `exit_sim.py` names, `exit_sim_v2.py:simulate_exit_v2`, the `PlanManager` steps, `config.py:RUNNER_GIVEBACK_ENABLED` and `config.py:PLAN_ENGINE_V2`) and its tests (`CH7_ANCHORS`, the rule-number, link and no-percent tests, which now cover the new sections); placeholders `MIN_RISK_REWARD_RATIO`, `MAX_RISK_REWARD_RATIO`, `MIN_REWARD_PCT`, `plan.breakeven_trigger`, `plan.tp1_share`, `plan.runner_floor`, `plan.trail_atr` (V237-2), `PLAN_ENGINE_V2` (V237-3b); chapter anchors `levels#the-minimum-move` (V237-9b), `gates#measured-not-used` (V237-11b).
- Produces (ledger): the chapter's eight anchors — V237-12's three plus `the-stop-never-widens`, `targets-that-pay-for-the-risk`, `scale-out-and-the-runner`, `how-a-plan-closes`, `backtest-and-live-use-the-same-plan`.

Report note for the controller (do not fix here): `SCALE_OUT_ENABLED` reaches only `scan_params.scale_out_enabled`, which nothing reads; `PlanManager._step_active` closes `plan.tp1_fraction` at TP1 regardless of the flag. If the admin help text should say so, that is its own change.

- [ ] **Step 1: Confirm the consumed names**

Run: `git grep -n "^## The stop-distance cap and the clamp" docs/guide/07-trade-plan.md; git grep -n "^CH7_ANCHORS" tests/admin/test_guide_chapter_text.py`
Expected: one line each (V237-12).

Run: `python -c "from swingbot.admin.guide import placeholders as p; need={'MIN_RISK_REWARD_RATIO','MAX_RISK_REWARD_RATIO','MIN_REWARD_PCT','plan.breakeven_trigger','plan.tp1_share','plan.runner_floor','plan.trail_atr','PLAN_ENGINE_V2'}; print(sorted(need-set(p.PLACEHOLDERS)))"`
Expected: `[]`.

Run: `git grep -n '"tp1_runner_be"\|"tp1_runner_trail"\|"tp1_runner_tp2"\|reason="expired"\|reason="invalidated"\|reason="gap_through_stop"' swingbot/core/planning/plan_manager.py`
Expected: at least six lines (the close reasons the table names).

Code facts this half states (read 2026-11-18): `exit_sim.tighter_stop` never loosens and `PlanStore.update` never loosens the stop of an ACTIVE/PARTIAL plan (its module docstring); `select_structural_target` returns the nearest candidate at or above `min_rr`, a synthetic price at `max_rr` when the nearest is beyond it, and None otherwise ("no fallback", its docstring); `select_tp2` drops a candidate more than `MAX_TARGET2_LEG_MULTIPLE` times the first leg past TP1; `_step_active` arms the break-even stop at `breakeven_trigger(plan, entry)` and at TP1 sets `working_stop = runner_floor(entry, tp1)`; `_step_partial` applies `_apply_giveback` (only while `RUNNER_GIVEBACK_ENABLED`) and `_ratchet_chandelier`; `simulate_exit_v2` fills gaps at the open, stop first, books costs once and caps the hold at the horizon's `max_holding_days`. If one changed, correct its sentence and report it.

- [ ] **Step 2: Write the failing tests**

In `tests/admin/test_guide_chapter_text.py`, replace the `CH7_ANCHORS = [...]` assignment V237-12 wrote with:

```python
CH7_ANCHORS = ["entry", "the-stop", "the-stop-distance-cap-and-the-clamp",
               "the-stop-never-widens", "targets-that-pay-for-the-risk",
               "scale-out-and-the-runner", "how-a-plan-closes",
               "backtest-and-live-use-the-same-plan"]
```

Then append after the chapter-7 tests:

```python
def test_chapter_7_stop_never_widens_and_gaps_can_pass_it():
    section = _section(_chapter("trade-plan").body, "The stop never widens")
    assert "tighter" in section and "loosen" in section
    assert "glossary#gap-through-the-stop" in section


@pytest.mark.parametrize("heading, names", [
    ("Targets that pay for the risk",
     {"MIN_RISK_REWARD_RATIO", "MAX_RISK_REWARD_RATIO", "MIN_REWARD_PCT"}),
    ("Scale-out and the runner",
     {"plan.breakeven_trigger", "plan.tp1_share", "plan.runner_floor", "plan.trail_atr"}),
    ("Backtest and live use the same plan", {"PLAN_ENGINE_V2"}),
])
def test_chapter_7_exit_numbers_are_placeholders(heading, names):
    assert names <= set(placeholders.names_in(_section(_chapter("trade-plan").body, heading)))


def test_chapter_7_targets_have_no_fallback_and_tp2_is_optional():
    section = _section(_chapter("trade-plan").body, "Targets that pay for the risk")
    assert "no fallback" in section
    assert "has a TP2 only when" in section


def test_chapter_7_close_table_lists_every_outcome():
    section = _section(_chapter("trade-plan").body, "How a plan closes")
    for outcome in ("expired", "invalidated", "cancelled at the cap", "gap through the stop",
                    "loss", "scratch", "TP1, runner at the floor", "TP1, runner trailed",
                    "TP1, then TP2"):
        assert f"| {outcome} |" in section
    for reason in ("tp1_runner_be", "tp1_runner_trail", "tp1_runner_tp2"):
        assert f"`{reason}`" in section
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: FAIL — `test_chapter_7_sections_in_order` (three anchors found, eight expected) and the six new test cases (`IndexError` from `_section`: no such heading); every other test passes.

- [ ] **Step 4: Append the five sections**

Append exactly this text to `docs/guide/07-trade-plan.md`, after the `The stop-distance cap and the clamp` section's closing `</details>` and one blank line (UTF-8, LF, the file still ends with one trailing newline):

````markdown
## The stop never widens

Once a plan is open, its stop only moves toward profit: to the entry after the break-even trigger, to the runner floor at TP1, then by the trail and the give-back stop. Each move takes the tighter of the old and the new stop, and the plan store refuses any write that would loosen the stop of an open plan.

A stop is not a guaranteed exit price. A gap can open beyond it, and the loss is then worse than one [R](/insights/guide/glossary#r-multiple) ([gap through the stop](/insights/guide/glossary#gap-through-the-stop)). Risk and size are still computed to the stop (chapter 8).

<details><summary>Under the hood</summary>

`exit_sim.tighter_stop` picks the tighter of two runner stops; a missing term never loosens. `PlanStore.update` takes the plan row lock, refuses a stale write over a closed plan and never loosens the stop of an ACTIVE or PARTIAL plan.

</details>

## Targets that pay for the risk

TP1 is the nearest real level beyond the entry whose [reward-to-risk](/insights/guide/glossary#reward-to-risk-rr) is at least {{MIN_RISK_REWARD_RATIO}}. If the nearest such level's reward-to-risk is above {{MAX_RISK_REWARD_RATIO}}, TP1 is placed at exactly that ratio and the real level stays available as TP2. If no level pays enough there is no plan: there is no fallback target. Before any of this, a level setup's target must be at least {{MIN_REWARD_PCT}} away ([the minimum move](/insights/guide/levels#the-minimum-move)).

Level plans choose from the whole level map. Strategy plans choose from their own levels (Fibonacci levels, the broken range, or a ladder of ATR steps) and must also clear their horizon's reward floor.

[TP2](/insights/guide/glossary#tp1-and-tp2) is the next level beyond TP1, left unset when it lies too far past TP1. A strategy plan has a TP2 only when its strategy's measured exit settings use one; the others let the runner ride on its trailing stop alone.

<details><summary>Under the hood</summary>

`targets.select_structural_target(entry, stop, is_bull, candidates, min_rr, max_rr)` serves live and backtest alike; `targets.select_tp2` and `builders._confluence_tp2` pick TP2, bounded by `levels.MAX_TARGET2_LEG_MULTIPLE`. `params.exit_params_for(strategy)["tp2"]` reads the frozen TRAIN-grid table `EXIT_V2_PARAMS`; `reward_floor.clears` is the strategy reward floor.

</details>

## Scale-out and the runner

Before TP1, once price has covered {{plan.breakeven_trigger}} of the way to TP1, the stop moves to the entry; a stop hit after that closes the trade as a scratch.

At TP1 the plan closes {{plan.tp1_share}} of the position ([scale-out](/insights/guide/glossary#scale-out)); a plan with a single target closes in full. The rest is the [runner](/insights/guide/glossary#runner), and its stop moves at once to the runner floor, which locks in {{plan.runner_floor}} of the move from entry to TP1.

After TP1 the runner's stop is the tightest of three: the floor; a chandelier trail {{plan.trail_atr}} behind the best price since TP1 (a strategy plan may use its own measured multiple); and, while the setting `RUNNER_GIVEBACK_ENABLED` is set, a give-back stop a set share below the best price. The runner closes at TP2 when there is one, otherwise when its stop is hit. A stall exit and a runner structure exit were measured and not adopted ([chapter 6](/insights/guide/gates#measured-not-used)).

<details><summary>Under the hood</summary>

`PlanManager._step_active` moves the stop to entry at `breakeven_trigger` (`BREAKEVEN_TRIGGER_FRACTION` unless the plan shape sets its own), closes `tp1_fraction` (`TP1_FRACTION`) at TP1 and sets `working_stop = exit_sim.runner_floor(entry, tp1)` (`RUNNER_FLOOR_FRACTION`). `PlanManager._step_partial` applies the give-back (`exit_sim.giveback_stop`) and ratchets the chandelier (`exit_sim.chandelier_stop`, `TRAIL_ATR_MULT` or the strategy's `exit_params_for` value) through `tighter_stop`.

</details>

## How a plan closes

Every plan ends in one of these [plan states](/insights/guide/glossary#plan-states):

| Outcome | When |
|---|---|
| expired | a waiting plan did not fill in time |
| invalidated | price closed through the stop before the entry fired |
| cancelled at the cap | the fill would have left the stop beyond the cap (`risk_cap`) |
| gap through the stop | a limit order would have filled at or beyond the stop, so nothing opened |
| loss | the stop was hit before the break-even move |
| scratch | the stop was hit at the entry, after the break-even move |
| TP1, runner at the floor | the runner's stop fired at the runner floor |
| TP1, runner trailed | the trail or the give-back stop closed the runner |
| TP1, then TP2 | the runner reached the second target |

A single-target plan that reaches TP1 closes there in full.

<details><summary>Under the hood</summary>

Close reasons as stored: `expired`, `invalidated`, `risk_cap`, `gap_through_stop`, `loss`, `scratch`, `tp1_runner_be`, `tp1_runner_trail`, `tp1_runner_tp2`. The plan manager steps every open plan on its regular live-price poll.

</details>

## Backtest and live use the same plan

The functions that build a plan, the stops, the clamp, the targets, the runner floor and the give-back stop, are the same in backtests and live, so a backtest measures the plan an alert would carry. The backtest walk reads daily bars: a gap fills at the open in either direction, on a bar that touches both the stop and a target the stop is taken first, costs are booked once per trade, and a trade still open at the horizon's longest hold is closed there. Live reads a price poll, so live fills can differ: better on a gap toward the target, worse on a gap through the stop.

Everything in this chapter describes the plan engine setting `on`; it is now {{PLAN_ENGINE_V2}}.

<details><summary>Under the hood</summary>

`build_strategy_plan` and `build_confluence_plan` are the only plan constructors, used by the scan and by the backtest. The walk is `exit_sim_v2.simulate_exit_v2` (instrument v2: fills and costs from `backtesting/instrument/`), with the horizon's `max_holding_days` as its hold cap.

</details>
````

- [ ] **Step 5: Regenerate the anchor fixture**

Run: `python scripts/dev/guide_anchors.py`
Then: `python scripts/dev/guide_anchors.py --check`
Expected: exit 0; `"trade-plan"` now lists the eight `CH7_ANCHORS`, in order.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: PASS (`0 failed`), including V237-12's link and no-percent tests over the whole chapter.

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_content.py`
Then: `python scripts/dev/testrun.py file tests/admin/test_api_v1_guide.py`
Expected: PASS both — `[bare percent]` finds no bare number before `%` in chapter 7.

- [ ] **Step 7: Commit (merge together with V237-12)**

```bash
git add docs/guide/07-trade-plan.md tests/admin/test_guide_chapter_text.py frontend/src/app/workspaces/guide/guide-anchors.json
git commit -m "docs(guide): chapter 7 part two -- never widens, targets, scale-out, closes, parity (v237 V237-12b)"
```


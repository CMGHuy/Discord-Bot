# v237 — Guide trading core, part 2: the nineteen strategy cards, glossary terms, chapter 4

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V237-8" -A 300 <this file>`); never read the file whole.

**Spec:** v215 — [2026-11-06-v215-guide-page.md](../specs/2026-11-06-v215-guide-page.md), Plan B ("Trading core").
**Index:** [2026-11-18-v237-guide-trading-core_0-index.md](2026-11-18-v237-guide-trading-core_0-index.md) — Goal, Global Constraints, `## Parallelisation`, the task ledger and `## Handoff`.
**Part 1:** [_1-placeholders.md](2026-11-18-v237-guide-trading-core_1-placeholders.md) (V237-1..4) and [_1b-strategies-checks.md](2026-11-18-v237-guide-trading-core_1b-strategies-checks.md) (V237-5..6); their "Starting state" and "Test runs" notes apply here too.

**Split (index fallback, plan-writer part 2).** The nineteen cards do not fit one 20 KB task, so they ship as **V237-7** (the eleven live cards) and **V237-7b** (the eight masked cards). v235's `strategy cards` check fails while `docs/guide/strategies/` holds only part of the set, so V237-7's verification deselects `test_the_real_guide_passes[strategy cards]` (named in its step) and V237-7b turns it green. **Both tasks are reviewed and merged together**; never push V237-7 alone. The controller adds the `V237-7b` ledger row directly below `V237-7`.

**Split (chapter 4, plan-writer part 2).** The full chapter-4 task measured 20.1 KB, so it ships as **V237-9** (file, front matter and the first five sections) and **V237-9b** (the last four sections and their tests); both are reviewed and merged together. The controller adds the `V237-9b` ledger row directly below `V237-9`.

**Card contract (V237-4, V237-5).** Front matter keys `strategy` (exact registry key, quoted), `reviewed_for: 2.19.2`, `sources` (non-empty list of real `path` or `path:symbol` entries — module-level `def`s only here, never an annotated dict such as `STRATEGY_GATES` or `DEFAULT_PARAMS`). File stem = `live_market.strategy_file_slug(strategy)`. Body: no line starting with `#`, no `{{`, no performance figure. The page adds `### <key>`, the status, the Long/Short cells from `admits()` and the badge line; the card supplies only the prose below them.

**Card body shape** (pinned by `test_real_card_bodies_follow_the_shape`):

```markdown
**Idea.** <one or two sentences, plain words>

**Entry rule.**

- <condition>
- <condition>

**Where it fires.** <where the rule itself can fire, beside what the mask allows>

<details><summary>Under the hood</summary>

<function names, parameter tables; no heading>

</details>
```

Rule numbers (RSI bands, lookbacks, volume multiples) are not typed in card prose: they live in `DEFAULT_PARAMS` and the functions named under the hood, so a retune cannot leave a card stale. Horizon codes (`4w`, `2w`) and the classic Fibonacci ratios are names, not tunables, and may appear.

# Phase 3 — Strategy cards

### Task V237-7: The eleven live strategy cards

**Model:** sonnet — fixed Markdown given whole below plus three pytest checks; the judgement (rule wording against the code) is done here, the implementer copies and verifies.

**Why.** Chapter 5 renders one card per registered strategy (spec v215 § chapter 5, index Handoff 1): the idea and entry rule are prose a trader can check, written from the entry functions — not from the stale per-key comments in `strategy_types.py` (brief T7). This task writes the eleven strategies the live mask admits somewhere; V237-7b writes the eight masked ones. Each card says where its rule can fire as well as what the mask allows, because they differ (Elliott Wave fires on `4w` only although `admits()` opens every live horizon, `entry_filters.py:1188`).

**Files:**
- Create: `docs/guide/strategies/{break-retest,ema-crossover,elliott-wave,fibonacci,ma-ribbon,macd,rsi,rsi-divergence,supportresistance,volume-profile,vwap}.md`
- Test: modify `tests/admin/test_guide_strategies.py` (V237-5)

**Interfaces:**
- Consumes: `cards.cards_dir`, `parse_card`, `load_cards` (V237-4); `live_market.registered_strategy_keys`, `strategy_file_slug` (V235-4); `strategy_types.admits`, `live_horizons`; `REAL_CHECKS` entries `"card format"`, `"card sources"`, `"card reviewed_for"` (V237-6); the module imports `cards`, `lm`, `strategy_types` of `tests/admin/test_guide_strategies.py` (V237-5).
- Produces: eleven card files; test helpers `_is_live(key) -> bool`, `_real_card(key) -> StrategyCard`, `_ENTRY_MODULES`, `_FIGURE`, `_BODY_MAX_BYTES = 1000` in `tests/admin/test_guide_strategies.py` (V237-7b reuses them).

- [ ] **Step 1: Confirm the consumed names and the eleven live keys**

Run: `git grep -n "^def parse_card\|^def load_cards\|^def cards_dir" swingbot/admin/guide/cards.py`
Expected: three lines (V237-4).

Run: `python -c "from swingbot.admin.guide import live_market as lm; from swingbot.core.market import strategy_types as st; L=st.live_horizons(); print(sorted(k for k in lm.registered_strategy_keys() if any(st.admits(k,s,h) for s in ('bullish','bearish') for h in L)))"`
Expected: `['Break & Retest', 'EMA Crossover', 'Elliott Wave', 'Fibonacci', 'MA Ribbon', 'MACD', 'RSI', 'RSI Divergence', 'Support/Resistance', 'VWAP', 'Volume Profile']`. A different list means the mask changed since 2026-11-18: stop and report.

Run: `git grep -n "^def break_retest_entries\|^def ema_cross_entries\|^def elliott_wave_entries\|^def fibonacci_entries\|^def ma_ribbon_entries\|^def macd_entries\|^def rsi_entries\|^def rsi_divergence_entries\|^def support_resistance_entries\|^def volume_profile_entries\|^def vwap_entries\|^def compute_shared_gates\|^def _vectorized_hvn\|^def adx_series" swingbot/core/market/entry_filters.py`
Expected: fourteen lines. Also `git grep -n "^def elliott_wave3_entries" swingbot/core/market/indicators.py` (one line).

- [ ] **Step 2: Write the failing tests**

In `tests/admin/test_guide_strategies.py` add `import re` to the imports, then append:

```python
# --- the real cards (v237 V237-7, V237-7b) ---------------------------------------------

_ENTRY_MODULES = ("swingbot/core/market/entry_filters.py:",
                  "swingbot/core/market/short_entries.py:",
                  "swingbot/core/market/turtle_soup.py:")
#: A performance figure on a card: figures come only from the registry badge.
_FIGURE = re.compile(r"\d\s*%|[+-]\d+(?:\.\d+)?\s*R\b|\bN\s*=|\bExpR\b|\bwin rate\b", re.I)
_BODY_MAX_BYTES = 1000


def _is_live(key: str) -> bool:
    live = strategy_types.live_horizons()
    return any(strategy_types.admits(key, side, h)
               for side in ("bullish", "bearish") for h in live)


def _real_card(key: str) -> cards.StrategyCard:
    path = cards.cards_dir() / f"{lm.strategy_file_slug(key)}.md"
    assert path.is_file(), f"no card {path.name} for {key}"
    return cards.parse_card(path)


def test_every_live_strategy_has_a_real_card():
    live_keys = [key for key in lm.registered_strategy_keys() if _is_live(key)]
    assert len(live_keys) == 11
    for key in live_keys:
        assert _real_card(key).strategy == key


def test_real_card_bodies_follow_the_shape():
    found = cards.load_cards()
    assert found, "docs/guide/strategies/ holds no card"
    for card in found:
        body, name = card.body, card.path.name
        assert body.startswith("**Idea.** "), name
        assert "\n\n**Entry rule.**\n\n- " in body, name
        assert "\n\n**Where it fires.** " in body, name
        assert (body.index("**Idea.**") < body.index("**Entry rule.**")
                < body.index("**Where it fires.**")), name
        assert not _FIGURE.search(body), f"{name}: a performance figure belongs to the badge"
        assert len(body.encode("utf-8")) <= _BODY_MAX_BYTES, name


def test_real_cards_cite_their_entry_function_and_the_mask():
    for card in cards.load_cards():
        assert any(s.startswith(_ENTRY_MODULES) for s in card.sources), card.path.name
        assert "swingbot/core/market/strategy_types.py:admits" in card.sources, card.path.name
```

These read the real files directly (`cards.load_cards()`); the module's autouse `_offline` fixture patches only `live_strategies._load_cards` and `_badge`, so it does not hide them.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_strategies.py`
Expected: FAIL — `test_every_live_strategy_has_a_real_card` (`no card break-retest.md for Break & Retest`) and `test_real_card_bodies_follow_the_shape` (`docs/guide/strategies/ holds no card`); V237-5's tests still pass; `test_real_cards_cite_their_entry_function_and_the_mask` passes vacuously.

- [ ] **Step 4: Write the eleven cards**

Create each file under `docs/guide/strategies/` with exactly this text (UTF-8, LF, one trailing newline).

`break-retest.md`:

```markdown
---
strategy: "Break & Retest"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/entry_filters.py:break_retest_entries
  - swingbot/core/market/entry_filters.py:compute_shared_gates
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** A range high that held price back often becomes the floor once it breaks on heavy volume. The trade buys the first pullback that holds the old high.

**Entry rule.**

- Within the last few bars price broke the prior range high on volume well above its recent average.
- Price is back near that level, the bar's low held it, and the close cleared the previous bar's high.
- RSI sits in a middle band, and the shared trend and volatility gates pass.

**Where it fires.** Both sides on every horizon (shorts mirror it at a broken range low); the mask keeps the horizons its measurement supported.

<details><summary>Under the hood</summary>

`entry_filters.break_retest_entries`. The level is the prior `sr_lookback` high or low (`_break_retest_levels`); how recent the break and how close the retest must be, per horizon: `BRT_RECENT_BARS`, `BRT_RETEST_PCT`.

</details>
```

`ema-crossover.md`:

```markdown
---
strategy: "EMA Crossover"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/entry_filters.py:ema_cross_entries
  - swingbot/core/market/entry_filters.py:compute_shared_gates
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** A fast moving average crossing a slow one marks a turn in trend. Waiting for the first pullback to the fast average buys the new trend at a better price than the cross.

**Entry rule.**

- The fast EMA crossed above the slow EMA and stayed above on the next bar, with the slow EMA rising.
- Within a set number of bars price dips to the fast EMA and closes back above it; the first such touch is the entry.
- RSI dipped before the cross and is above its midline now, momentum agrees, price is not stretched away from the fast EMA, and the shared gates pass.

**Where it fires.** Both sides (shorts mirror it) on every horizon, with the periods of the averages set per horizon.

<details><summary>Under the hood</summary>

`entry_filters.ema_cross_entries` with `DEFAULT_PARAMS["EMA Crossover"]` (`entry_mode` "pullback", the touch window, the re-arm count); periods `HORIZONS[h]["ema_fast"]` and `HORIZONS[h]["ema_slow"]`.

</details>
```

`elliott-wave.md`:

```markdown
---
strategy: "Elliott Wave"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/entry_filters.py:elliott_wave_entries
  - swingbot/core/market/indicators.py:elliott_wave3_entries
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** A mechanical stand-in for the start of an Elliott third wave: after a first impulse and a corrective second wave, price breaks back past the first wave's extreme.

**Entry rule.**

- Three swing pivots mark wave 1 and wave 2, and the bar breaks past the wave-1 extreme.
- Wave 2 retraced a textbook share of wave 1, stayed short of its origin and did not drag on too long.
- RSI is above its midline and rising, and the shared gates pass. Shorts mirror it.

**Where it fires.** The rule fires on the 4w horizon only; on every other horizon it returns no signal, so the wider opening of the mask reduces to 4w in practice.

<details><summary>Under the hood</summary>

`entry_filters.elliott_wave_entries` (returns nothing off `4w`); pivots from `indicators.elliott_wave3_entries` with the horizon's `max_risk_pct` as the pivot threshold; wave-2 depth and duration bounds in `DEFAULT_PARAMS["Elliott Wave"]`.

</details>
```

`fibonacci.md`:

```markdown
---
strategy: "Fibonacci"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/entry_filters.py:fibonacci_entries
  - swingbot/core/market/entry_filters.py:compute_shared_gates
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** In an uptrend, pullbacks often pause at the classic retracement ratios of the last swing. The trade buys the bounce from one of them.

**Entry rule.**

- In the look-back window the swing low came before the swing high, so the swing is an up-move.
- After pulling back for several bars, price sits near the 0.382, 0.5 or 0.618 retracement of that swing.
- The bar bounces and closes in its upper half, RSI is in a lower-middle band, and the shared gates pass.

**Where it fires.** The rule has a short mirror (a bounce down from a retracement of a down-swing), but the mask admits only longs.

<details><summary>Under the hood</summary>

`entry_filters.fibonacci_entries`; ratios and RSI band in `DEFAULT_PARAMS["Fibonacci"]`, window `HORIZONS[h]["fib_lookback"]`. Two optional filters, `FIB_SR_CONFLUENCE_ATR` and `FIB_LEVEL_STOP_ATR`, are settings where `0` turns them off.

</details>
```

`ma-ribbon.md`:

```markdown
---
strategy: "MA Ribbon"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/entry_filters.py:ma_ribbon_entries
  - swingbot/core/market/entry_filters.py:compute_shared_gates
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** When short, medium and long moving averages stack in order and the short one crosses the medium one, an uptrend is gathering pace.

**Entry rule.**

- The fast EMA crosses above the mid EMA while both sit above the slow SMA, and the slow SMA is rising.
- Price is not stretched far above the slow SMA, RSI is in a healthy band, and MACD is above zero.
- The shared gates pass; the setting `MA_RIBBON_CONFIRM_BARS` can demand that the stack holds for more bars.

**Where it fires.** The rule has a short mirror, but the mask admits only longs.

<details><summary>Under the hood</summary>

`entry_filters.ma_ribbon_entries`; periods per horizon in `RIBBON_PERIODS_BY_HORIZON`, thresholds in `DEFAULT_PARAMS["MA Ribbon"]`.

</details>
```

`macd.md`:

```markdown
---
strategy: "MACD"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/entry_filters.py:macd_entries
  - swingbot/core/market/entry_filters.py:compute_shared_gates
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** A MACD line turning up through its signal line, with the gap widening, shows momentum returning to an uptrend.

**Entry rule.**

- The MACD line crosses above its signal line, or the histogram turned positive and held.
- The histogram has grown on consecutive bars, the MACD line is above zero and RSI is above its midline.
- Price is not stretched away from the fast average, and the shared gates pass.

**Where it fires.** The rule has a short mirror, but the mask admits only longs, and only on the horizons its measurement supported.

<details><summary>Under the hood</summary>

`entry_filters.macd_entries`; MACD periods per horizon in `strategy_types.MACD_PERIODS_BY_HORIZON`, stretch limit in `DEFAULT_PARAMS["MACD"]`.

</details>
```

`rsi.md`:

```markdown
---
strategy: "RSI"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/entry_filters.py:rsi_entries
  - swingbot/core/market/entry_filters.py:adx_series
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** A short oversold dip inside a healthy long-term uptrend tends to snap back. The trade buys the first strong bar after RSI leaves oversold.

**Entry rule.**

- RSI was oversold on the two previous bars and is now back above the oversold line, still low.
- The long moving average is rising; the close is above where it was a few bars ago and above the previous bar's high.
- The market is ranging rather than trending hard (low ADX), and the volatility and volume gates pass.

**Where it fires.** The rule has a short mirror (an overbought fade under a falling long average), but the mask admits only longs.

<details><summary>Under the hood</summary>

`entry_filters.rsi_entries`; oversold line, confirmation mode and ADX ceiling in `DEFAULT_PARAMS["RSI"]`. It uses only the slope of the long average (`bull_regime_slope_only` in `compute_shared_gates`), not price above it, because a dip trades below the short averages.

</details>
```

`rsi-divergence.md`:

```markdown
---
strategy: "RSI Divergence"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/entry_filters.py:rsi_divergence_entries
  - swingbot/core/market/entry_filters.py:compute_shared_gates
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** Hidden divergence: price makes a higher low while RSI makes a lower low. In an uptrend that marks a pullback losing force; the entry waits for RSI to turn back up.

**Entry rule.**

- Over the look-back window price set a higher low and RSI a lower low.
- RSI has reclaimed its reclaim line and is rising, inside a lower-middle band; `RSI_DIV_MIN_CONSECUTIVE_TURN` sets how many rising bars count as a turn.
- The shared gates pass. Shorts mirror it: a lower high in price against a higher high in RSI.

**Where it fires.** Both sides on every live horizon.

<details><summary>Under the hood</summary>

`entry_filters.rsi_divergence_entries`, a rolling formulation without discrete swing points; reclaim line and the optional volume and reclaim-strength filters in `DEFAULT_PARAMS["RSI Divergence"]`.

</details>
```

`supportresistance.md` (the anchor rule drops `/`, so the stem is `supportresistance`):

```markdown
---
strategy: "Support/Resistance"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/entry_filters.py:support_resistance_entries
  - swingbot/core/market/entry_filters.py:compute_shared_gates
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** A breakout from a tight base through the range high, on heavy volume and with a strong close, often starts a new leg up.

**Entry rule.**

- The close crosses above the prior range high on volume well above its recent average.
- The bars before it formed a tight base, measured against ATR, and the bar closes near its high.
- The open did not gap far above the level, and the shared trend and volatility gates pass.

**Where it fires.** The rule has a short mirror (a breakdown through the range low), but the mask admits only longs, and only on the horizons its measurement supported. The setting `SR_MIN_LEVEL_TOUCHES` can also demand earlier rejections at the level.

<details><summary>Under the hood</summary>

`entry_filters.support_resistance_entries`; the range spans `HORIZONS[h]["sr_lookback"]` bars; base, close and gap limits in `DEFAULT_PARAMS["Support/Resistance"]`.

</details>
```

`volume-profile.md`:

```markdown
---
strategy: "Volume Profile"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/entry_filters.py:volume_profile_entries
  - swingbot/core/market/entry_filters.py:_vectorized_hvn
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** Prices where a lot of volume traded act as memory: buyers who defended them before tend to defend them again. The trade buys a bounce just above such a node.

**Entry rule.**

- The busiest price band of the window holds a large enough share of all volume to count as a node.
- The close sits just above that node and is up on the bar.
- RSI is in a middle band, and the shared gates pass.

**Where it fires.** The rule has a short mirror, but the mask admits only longs, and only on the horizon its measurement supported.

<details><summary>Under the hood</summary>

`entry_filters.volume_profile_entries`; the node comes from `_vectorized_hvn` over `HORIZONS[h]["sr_lookback"]` bars; node share and proximity in `DEFAULT_PARAMS["Volume Profile"]`.

</details>
```

`vwap.md`:

```markdown
---
strategy: "VWAP"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/entry_filters.py:vwap_entries
  - swingbot/core/market/entry_filters.py:compute_shared_gates
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** VWAP is the average price paid, weighted by volume. Reclaiming a rising VWAP and holding it suggests buyers are back in control.

**Entry rule.**

- The close was below the rolling VWAP and has now held above it for a few bars, while VWAP is rising.
- Price is still close to VWAP (no chasing), and RSI is in a middle band.
- The shared gates pass.

**Where it fires.** The rule has a short mirror, but the mask admits only longs, and only on the horizon its measurement supported.

<details><summary>Under the hood</summary>

`entry_filters.vwap_entries`; window `HORIZONS[h]["vwap_window"]`; hold length (its own value on 2w), stretch limit and RSI band in `DEFAULT_PARAMS["VWAP"]`.

</details>
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_strategies.py`
Expected: PASS (`0 failed`).

Run: `python -m pytest tests/admin/test_guide_content.py -q -p no:cacheprovider`
Expected: exactly one failure, `test_the_real_guide_passes[strategy cards]`, naming the eight masked stems V237-7b writes (`bull-trap`, `downtrend-overbought-fade`, `earnings-gap-drift`, `fibonacci-continuation`, `fibonacci-limit`, `first-bearish-compression-release`, `turtle-soup`, `vol-expansion-breakdown`). `[card format]`, `[card sources]` and `[card reviewed_for]` now run over real files and pass; any failure there is a card defect — fix the card, never the check.

Run: `python -m pytest tests/admin/test_guide_content.py -q -p no:cacheprovider --deselect "tests/admin/test_guide_content.py::test_the_real_guide_passes[strategy cards]"`
Expected: PASS.

- [ ] **Step 6: Commit (WIP — V237-7b completes the set; merge both together)**

```bash
git add docs/guide/strategies/ tests/admin/test_guide_strategies.py
git commit -m "docs(guide): the eleven live strategy cards (v237 V237-7; set completed by V237-7b)"
```

### Task V237-7b: The eight masked strategy cards

**Model:** sonnet — fixed Markdown given whole below plus four pytest checks that close the card set; no production code.

**Why.** The eight strategies with an empty mask (`STRATEGY_GATES[key] = {"directions": ()}`) still render on chapter 5, as `masked — research only` with `no registry row — masked, research only` for the badge (index Handoff 2). Their cards say what the rule would trade and how it is measured, so a reader understands why it never alerts. This task completes the file set, which turns v235's `strategy cards` check green and lets `strategies.cards` render over the real files. **Merge together with V237-7** (split of one ledger row; see this part's header).

**Files:**
- Create: `docs/guide/strategies/{bull-trap,downtrend-overbought-fade,earnings-gap-drift,fibonacci-continuation,fibonacci-limit,first-bearish-compression-release,turtle-soup,vol-expansion-breakdown}.md`
- Test: modify `tests/admin/test_guide_strategies.py`

**Interfaces:**
- Consumes: V237-7's helpers `_is_live`, `_real_card` and the shape checks; V237-5's `_render`, the autouse `_offline` fixture (keeps `_badge` fake, so nothing reads `validation_registry.json`) and `lst` (`live_strategies`).
- Produces: the full card set (nineteen files, stems equal `{strategy_file_slug(k) for k in registered_strategy_keys()}`); `test_real_cards_render_for_every_registered_key` (ledger).

- [ ] **Step 1: Confirm the consumed names and the eight masked keys**

Run: `git grep -n "^def bull_trap_frame\|^def vol_breakdown_frame\|^def gap_drift_frame\|^def fade_frame\|^def compression_short_frame\|^def earnings_ok" swingbot/core/market/short_entries.py`
Expected: six lines.

Run: `git grep -n "^def fib_continuation_entries\|^def fibonacci_limit_entries\|^def fibonacci_limit_setups\|^def turtle_soup_entries\|^def gate_override" swingbot/core/market/entry_filters.py`
Expected: five lines.

Run: `git grep -n "^def sweep_frame" swingbot/core/market/turtle_soup.py` and `git grep -n "^RESEARCH_CELL = " swingbot/core/backtesting/arms/turtle_soup_research.py` and `git grep -n "^def squeeze_release_series" swingbot/core/market/volatility.py`
Expected: one line each.

- [ ] **Step 2: Write the failing tests**

Append to `tests/admin/test_guide_strategies.py`:

```python
def test_every_masked_strategy_has_a_real_card_that_says_so():
    masked = [key for key in lm.registered_strategy_keys() if not _is_live(key)]
    assert len(masked) == 8
    for key in masked:
        where = _real_card(key).body.split("**Where it fires.**", 1)[1]
        assert "masked" in where, key


def test_live_cards_never_call_themselves_masked():
    for key in (k for k in lm.registered_strategy_keys() if _is_live(k)):
        where = _real_card(key).body.split("**Where it fires.**", 1)[1].split("<details>")[0]
        assert "masked" not in where.lower(), key


def test_the_card_files_are_exactly_the_registered_keys():
    stems = {path.stem for path in cards.cards_dir().glob("*.md")}
    assert stems == {lm.strategy_file_slug(key) for key in lm.registered_strategy_keys()}


def test_real_cards_render_for_every_registered_key(monkeypatch):
    monkeypatch.setattr(lst, "_load_cards", cards.load_cards)
    text = _render()
    for card in cards.load_cards():
        assert f"### {card.strategy}\n" in text
        assert card.body in text
    assert "{{" not in text
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_strategies.py`
Expected: FAIL — `test_every_masked_strategy_has_a_real_card_that_says_so` (`no card bull-trap.md for Bull Trap`), `test_the_card_files_are_exactly_the_registered_keys` (eight stems missing) and `test_real_cards_render_for_every_registered_key` (`GuideFormatError: strategies/: no card for Bull Trap, …`); the rest pass.

- [ ] **Step 4: Write the eight cards**

Create each file under `docs/guide/strategies/` with exactly this text (UTF-8, LF, one trailing newline).

`bull-trap.md`:

```markdown
---
strategy: "Bull Trap"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/short_entries.py:bull_trap_frame
  - swingbot/core/market/short_entries.py:earnings_ok
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** A short. A breakout above the range high that fails fast traps the buyers who chased it; their exits push price back down.

**Entry rule.**

- The close broke above the prior range high, then closed back below it within a few bars.
- Volatility is not dead, volume is normal or better, and no earnings report is near.
- The stop sits a small ATR buffer above the failed high; the targets are the base under the breakout and the range low.

**Where it fires.** Short only, on every horizon. The mask admits no cell, so it is masked: measured in research, never alerted, until its pre-registered holdout test passes.

<details><summary>Under the hood</summary>

`short_entries.bull_trap_frame`; the failure window and earnings handling in `DEFAULT_PARAMS["Bull Trap"]`.

</details>
```

`vol-expansion-breakdown.md`:

```markdown
---
strategy: "Vol Expansion Breakdown"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/short_entries.py:vol_breakdown_frame
  - swingbot/core/market/short_entries.py:earnings_ok
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** A short. A weak stock breaking support in a falling market, while its daily range is expanding, tends to keep falling.

**Entry rule.**

- The close falls under the prior range low on heavy volume, with ATR expanding above its recent mean.
- The broad market is falling (SPY under a falling medium average) and the stock has lagged SPY.
- No earnings report is near; the stop sits a small ATR buffer above the broken support.

**Where it fires.** Short only, on every horizon, and only when the market context is attached. The mask admits no cell, so it is masked: research only until its holdout test passes.

<details><summary>Under the hood</summary>

`short_entries.vol_breakdown_frame` (no signal without the `ctx_spy_down` / `ctx_spy_ret63` columns).

</details>
```

`earnings-gap-drift.md`:

```markdown
---
strategy: "Earnings Gap Drift"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/short_entries.py:gap_drift_frame
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** A short. After earnings, a large gap down that fails to recover often keeps drifting lower for days.

**Entry rule.**

- The reaction session to an earnings report opened with a large gap down.
- On the next session the close is still below the close of the reaction day.
- The stop sits a small ATR buffer above the high of the reaction day.

**Where it fires.** Short only; the rule ignores the horizon and needs the earnings calendar. The mask admits no cell, so it is masked: research only until its holdout test passes.

<details><summary>Under the hood</summary>

`short_entries.gap_drift_frame`; minimum gap size in `DEFAULT_PARAMS["Earnings Gap Drift"]`; no signal without the `evt_reaction` column.

</details>
```

`downtrend-overbought-fade.md`:

```markdown
---
strategy: "Downtrend Overbought Fade"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/short_entries.py:fade_frame
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** A short. In a stock already in a downtrend, a sharp few-day rally to overbought is usually sold into.

**Entry rule.**

- The close is under a falling long moving average.
- A very short RSI spikes to an extreme overbought reading.
- No earnings report is due in the next few bars; a sell limit rests at the close, with a stop a fixed small distance above.

**Where it fires.** Short only; the rule ignores the horizon, and a holdout pass would admit it on the 1w horizon alone. Until then it is masked: research only.

<details><summary>Under the hood</summary>

`short_entries.fade_frame`; the frozen constants `FADE_SMA`, `FADE_RSI_PERIOD`, `FADE_RSI_MIN`, `FADE_STOP_PCT`, `FADE_EARNINGS_BARS`; needs the `evt_bars_to_next` column.

</details>
```

`first-bearish-compression-release.md`:

```markdown
---
strategy: "First Bearish Compression Release"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/short_entries.py:compression_short_frame
  - swingbot/core/market/volatility.py:squeeze_release_series
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** A short. After a volatility squeeze, the first release that breaks downward often starts a move lower.

**Entry rule.**

- A squeeze (Bollinger Bands inside the Keltner Channel) releases.
- The release is the first one confirmed to the downside.
- The stop sits a small ATR buffer above the bar's high; the planning layer sets the final stop and target.

**Where it fires.** Short only, on the 2w horizon only. The mask admits no cell, so it is masked: research only until its pre-registered test passes.

<details><summary>Under the hood</summary>

`short_entries.compression_short_frame` reads `volatility.squeeze_release_series` (`bearish_confirmed`) and returns nothing off `2w`.

</details>
```

`fibonacci-continuation.md`:

```markdown
---
strategy: "Fibonacci Continuation"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/entry_filters.py:fib_continuation_entries
  - swingbot/core/market/entry_filters.py:fib_continuation_frame
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** Instead of buying the bounce at a retracement, wait for the trend to prove itself: buy when price breaks back through the swing high after a held pullback.

**Entry rule.**

- The pullback held between the 0.382 and 0.618 retracement of the swing and lasted a few bars.
- The close breaks back through the swing extreme, with the shared gates passing.
- The stop sits a small ATR buffer beyond the swing extreme and must fit the planned-loss cap, or there is no signal. Shorts mirror it.

**Where it fires.** Both sides, every horizon. The mask admits no cell, so it is masked: research only until a direction passes its pre-registered test.

<details><summary>Under the hood</summary>

`entry_filters.fib_continuation_frame` and `fib_continuation_entries`; depth bounds and pullback length in `DEFAULT_PARAMS["Fibonacci Continuation"]`; stop buffer `FIB_CONTINUATION_STOP_ATR`.

</details>
```

`fibonacci-limit.md`:

```markdown
---
strategy: "Fibonacci Limit"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/entry_filters.py:fibonacci_limit_entries
  - swingbot/core/market/entry_filters.py:fibonacci_limit_setups
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** A long. Rather than waiting for a bounce, rest a buy limit order at the 0.618 retracement of an up-leg and let the pullback come to it.

**Entry rule.**

- An up-leg whose high is a few bars old has started to pull back.
- A buy limit rests at the 0.618 retracement of the leg; each leg arms at most once.
- The order lives a few bars and is cancelled if price trades above the swing high first.

**Where it fires.** Long only. The mask admits no cell, so it is masked: research measures it by lifting the mask for the replay only, and live wiring is a later spec.

<details><summary>Under the hood</summary>

`entry_filters.fibonacci_limit_setups` (arming, order life, cancel); `fibonacci_limit_entries` returns nothing while masked; constants `FIB_LIMIT_MIN_RETRACE`, `FIB_LIMIT_MIN_AGE`; research unmasks it with `gate_override`.

</details>
```

`turtle-soup.md`:

```markdown
---
strategy: "Turtle Soup"
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/turtle_soup.py:sweep_frame
  - swingbot/core/market/entry_filters.py:turtle_soup_entries
  - swingbot/core/backtesting/arms/turtle_soup_research.py:RESEARCH_CELL
  - swingbot/core/market/strategy_types.py:admits
---
**Idea.** A long. A dip below a well-known recent low runs the stops parked under it; when price closes back above that low, the sellers are spent.

**Entry rule.**

- The bar trades below the lowest low of the recent channel, a low set some bars earlier.
- The same bar closes back above that low.
- The trade buys the next open.

**Where it fires.** Long only. The mask admits no cell, so it is masked: it is measured only in the long 2w research cell of the arms replay, and promotion is a later spec.

<details><summary>Under the hood</summary>

`turtle_soup.sweep_frame` with the frozen `CHANNEL` and `MIN_AGE`; `entry_filters.turtle_soup_entries` returns nothing while masked; research cell `arms/turtle_soup_research.RESEARCH_CELL`.

</details>
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_strategies.py`
Expected: PASS (`0 failed`), including V237-7's shape and source checks over all nineteen cards.

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_content.py`
Expected: PASS with nothing deselected — `[strategy cards]` is green now that the set is complete; `[card format]`, `[card sources]`, `[card reviewed_for]` pass.

Run: `python scripts/dev/testrun.py file tests/scripts/test_guide_sources.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add docs/guide/strategies/ tests/admin/test_guide_strategies.py
git commit -m "docs(guide): the eight masked strategy cards, card set complete (v237 V237-7b)"
```

# Phase 4 — Glossary terms and chapter 4

### Task V237-8: Glossary: terms chapters 4–8 link

**Model:** haiku — four short definitions inserted at named places in an existing Markdown file, a set literal extended, two small tests; every word is given below.

**Why.** Chapters 4–8 link glossary terms, and v236's `test_glossary_defines_every_term_the_guide_links_to` fails on any link to an anchor the glossary lacks (index Handoff 8). Four terms the trading chapters need are missing; eleven existing terms become pinned link targets so a later rename cannot break chapters 4–8 silently.

**Files:**
- Modify (created by v236 V236-10): `docs/guide/12-glossary.md`
- Modify (created by v236 V236-8): `tests/admin/test_guide_chapter_text.py` (`GLOSSARY_LINKED`, two new tests)
- Regenerate: `frontend/src/app/workspaces/guide/guide-anchors.json` (`python scripts/dev/guide_anchors.py`)

**Interfaces:**
- Consumes: `GLOSSARY_LINKED`, `_chapter`, `_section`, `_anchors` (V236-8/10); placeholder `DD_THROTTLE_ENABLED` (V237-2, renders `on`/`off`); `levels_lifecycle.STATES` (`swingbot/core/market/levels_lifecycle.py:48`).
- Produces (ledger): glossary anchors `level-lifecycle`, `direction-mask`, `drawdown-throttle`, `kill-switch`; `GLOSSARY_LINKED` grows by those four plus `masked`, `clamp`, `rejected-plan`, `suggested-size`, `entry`, `shadow-mode`, `support-and-resistance`, `provenance-label`, `train-and-validation`, `plan-states`, `expectancy-expr` (45 anchors).

Facts behind the wording (checked 2026-11-18): lifecycle states `fresh`/`tested`/`delivered`/`decaying`, no "retest" (`levels_lifecycle.classify_levels`); a stop prefers a tested level and never a delivered one (`preferred_stop_anchor`); the drawdown ladder applies only while `DD_THROTTLE_ENABLED` is on and pauses at its last rung, resuming below `RESUME_DD_PCT` (`edge/throttle.py:current_throttle`); the kill switch is engaged by the scan on a deep drawdown, a violent SPY day or a broken data feed (`scan_run.py:900`, `throttle.check_kill_triggers`), released only by `!killswitch off`, and while on every alert posts with suggested size 0 (`alert_embeds.py:260`).

- [ ] **Step 1: Confirm the consumed names**

Run: `git grep -n "^GLOSSARY_LINKED\|^def _section\|^def test_glossary_defines_every_term_the_guide_links_to" tests/admin/test_guide_chapter_text.py`
Expected: three lines.

Run: `git grep -n "^### Level family$\|^### Strategy$\|^### Gap through the stop$\|^## Measuring results$\|^### Masked$\|^### Clamp$\|^### Rejected plan$\|^### Suggested size$\|^### Entry$\|^### Shadow mode$\|^### Support and resistance$\|^### Provenance label$\|^### TRAIN and validation$\|^### Plan states$\|^### Expectancy (ExpR)$" docs/guide/12-glossary.md`
Expected: fifteen lines.

Run: `git grep -n '"DD_THROTTLE_ENABLED"' swingbot/admin/guide/live_rules.py`
Expected: one line (V237-2).

- [ ] **Step 2: Write the failing tests**

In `tests/admin/test_guide_chapter_text.py`, replace the `GLOSSARY_LINKED = {...}` literal (V236-10) with:

```python
#: Anchors chapters 1 and 3 link to (part 3 header of plan v236), plus the terms
#: chapters 4-8 link to (v237 V237-8).
GLOSSARY_LINKED = {
    "alert", "trade-plan", "paper-trade", "horizon", "long-and-short", "confidence",
    "watchlist-and-universe", "level", "level-family", "confluence", "scenario", "strategy",
    "completed-bar", "gate", "market-regime", "relative-strength", "stop", "tp1-and-tp2", "runner",
    "scale-out", "reward-to-risk-rr", "stop-distance-cap", "risk-per-trade", "dollar-risk-cap",
    "portfolio-heat", "correlated-heat", "size-0-alert", "gap-through-the-stop", "r-multiple", "badge",
    # v237 V237-8
    "level-lifecycle", "direction-mask", "drawdown-throttle", "kill-switch", "masked", "clamp",
    "rejected-plan", "suggested-size", "entry", "shadow-mode", "support-and-resistance",
    "provenance-label", "train-and-validation", "plan-states", "expectancy-expr"}
```

Append after the glossary tests:

```python
# --- v237 V237-8: glossary terms for chapters 4-8 ----------------------------------------

def _term(heading: str) -> str:
    return _chapter("glossary").body.split(f"### {heading}\n", 1)[1].split("\n#", 1)[0]


def test_glossary_holds_the_v237_terms_in_their_groups():
    body = _chapter("glossary").body
    assert len(GLOSSARY_LINKED) == 45
    for group, term in [("Levels and setups", "Level lifecycle"),
                        ("Levels and setups", "Direction mask"),
                        ("Risk and sizing", "Drawdown throttle"),
                        ("Risk and sizing", "Kill switch")]:
        assert f"### {term}\n" in _section(body, group), term


def test_glossary_level_lifecycle_and_throttle_follow_the_code():
    from swingbot.core.market import levels_lifecycle
    lifecycle = _term("Level lifecycle")
    assert all(state in lifecycle for state in levels_lifecycle.STATES)
    assert "retest" not in lifecycle.lower()
    assert "{{DD_THROTTLE_ENABLED}}" in _term("Drawdown throttle")
    assert "size of zero" in _term("Kill switch")
    assert "{{" not in placeholders.resolve(_term("Drawdown throttle"))
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: FAIL — `test_glossary_defines_every_term_the_guide_links_to` (the four new anchors are missing), `test_glossary_holds_the_v237_terms_in_their_groups` and `test_glossary_level_lifecycle_and_throttle_follow_the_code` (`IndexError` in `_term`); every other test passes.

- [ ] **Step 4: Add the four terms**

In `docs/guide/12-glossary.md` make three insertions; nothing else changes.

(a) Directly after the `### Level family` paragraph (before `### Confluence`):

```markdown
### Level lifecycle

What price has done to a level, read from finished bars: fresh (never touched), tested (touched and held), delivered (price closed through it) or decaying (not touched for a long time). A stop prefers to sit beyond a tested level and never leans on a delivered one.

```

(b) Directly after the `### Strategy` paragraph (before `### Completed bar`):

```markdown
### Direction mask

The sides (long, short) and horizons on which a strategy may alert, set from its measured results. A strategy whose mask admits nothing is masked: measured in research, never alerted.

```

(c) Directly after the `### Gap through the stop` paragraph (the last term before `## Measuring results`):

```markdown
### Drawdown throttle

When switched on, new entries are sized down step by step as the account falls from its peak, and paused at the deepest step until the account recovers part of the fall. It is {{DD_THROTTLE_ENABLED}} now.

### Kill switch

A pause on new entries that the scan engages on its own after a deep drawdown, a violent market day or a broken data feed, and that only a person can release. While it is on, alerts still post, with a suggested size of zero.

```

Each insertion keeps one blank line before the next `###`/`##` heading.

- [ ] **Step 5: Regenerate the anchor fixture**

Run: `python scripts/dev/guide_anchors.py`
Then: `python scripts/dev/guide_anchors.py --check`
Expected: exit 0; the `"glossary"` list gains `level-lifecycle` (after `level-family`), `direction-mask` (after `strategy`), `drawdown-throttle` and `kill-switch` (after `gap-through-the-stop`).

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: PASS (`0 failed`).

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_content.py`
Expected: PASS (placeholders whitelisted, anchor fixture in sync).

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/guide/guide-anchors.spec.ts`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add docs/guide/12-glossary.md tests/admin/test_guide_chapter_text.py frontend/src/app/workspaces/guide/guide-anchors.json
git commit -m "docs(guide): glossary terms for chapters 4-8 -- level lifecycle, direction mask, throttle, kill switch (v237 V237-8)"
```


### Task V237-9: Chapter 4, part one: levels, families, confluence, lifecycle

**Model:** sonnet — chapter text given whole below plus pinned text tests; the implementer must re-verify every `sources:` symbol and every placeholder before committing.

**Why.** Spec v215 § chapter 4: how the bot finds the next support or resistance, which level families exist (kept apart from the signal strategies of chapter 5), why confluence counts families rather than raw lines, the bonus confirmations that add no level, and the level lifecycle. Written from the code, not the spec (index Handoff 6): the lifecycle has four states and no "retest" (`levels_lifecycle.STATES`), and every rule number is a placeholder. The chapter is split over two tasks to stay under the 20 KB task cap (SPLIT V237-9 → V237-9b): this task creates the file with its first five sections; V237-9b appends the last four (alignment, closed bars, minimum move, duplicate merge). **Merge both together.**

**Files:**
- Create: `docs/guide/04-levels.md`
- Modify (created by v236 V236-8): `tests/admin/test_guide_chapter_text.py` (append the chapter-4 tests)
- Regenerate: `frontend/src/app/workspaces/guide/guide-anchors.json`

**Interfaces:**
- Consumes: placeholders `levels.families`, `CLUSTER_TOLERANCE_PCT` (V235-4), `CONFLUENCE_DEVIATION_PCT`, `MIN_TARGET_CONFLUENCE_COUNT`, `MIN_ALERT_CONFIDENCE_LEVEL`, `levels.touch_atr`, `levels.break_atr` (V237-2), `LEVEL_LIFECYCLE_STOPS_ENABLED` (V237-3b); glossary anchors in `GLOSSARY_LINKED` (V237-8); test helpers `_chapter`, `_anchors`, `_section`, `_GUIDE_LINK`, `GLOSSARY_LINKED` and the autouse `_no_live_book` / `_stored_account` fixtures (V236-8, V237-1).
- Produces: `docs/guide/04-levels.md` (slug `levels`, order 4, title `Finding levels and setups`, the full `sources:` list for both tasks) with anchors `the-next-level-idea`, `level-families`, `confluence-counts-families`, `bonus-confirmations`, `touch-break-and-the-four-states`; test constant `CH4_ANCHORS` (V237-9b extends it to the ledger's nine).

Links: only chapters written by then (`what-it-is`, `pipeline`, `glossary`, and `levels` itself); chapters 5–7 are named in plain text, not linked, because they do not exist yet (`test_every_linked_chapter_is_written`). The layout check pins three chapters in the drawer until V237-14; run it only there.

- [ ] **Step 1: Confirm every source and placeholder exists**

Run: `git grep -n "^ALL_STRATEGY_FAMILIES\|^CLUSTER_TOLERANCE_PCT\|^def collect_candidate_levels\|^def _cluster_levels\|^def count_confirming_strategies\|^def build_level_map\|^def build_scenarios\|^def atr_floor_pct" swingbot/core/market/levels.py`
Expected: eight lines.

Run: `git grep -n "^def classify_levels\|^def preferred_stop_anchor\|^TOUCH_ATR_MULT\|^BREAK_ATR_MULT\|^STATES" swingbot/core/market/levels_lifecycle.py`
Expected: five lines.

Run: `git grep -n "^def adjacent_aligned" swingbot/core/market/mtf.py; git grep -n "^def completed_frame" swingbot/core/scanning/strategy_pass.py; git grep -n "^def _horizon_scenarios" swingbot/core/scanning/analyze.py; git grep -n "^def _build_requirement_checks" swingbot/core/scanning/requirements.py; git grep -n "^def dedup_scan_items" swingbot/core/scanning/dedup.py; git grep -n "^def apply_level_lifecycle" swingbot/core/planning/lifecycle.py`
Expected: six lines.

Run: `git grep -n 'Field("\(AVWAP_LEVELS_ENABLED\|MIN_REWARD_PCT\|CONFLUENCE_DEVIATION_PCT\|MIN_TARGET_CONFLUENCE_COUNT\|MIN_ALERT_CONFIDENCE_LEVEL\|SIGNAL_CONFIRMATION_SCANS\|DEDUP_TOLERANCE_PCT\|HTF_CONFLUENCE_ENABLED\|MTF_ADJACENT_GATE\|LEVEL_LIFECYCLE_STOPS_ENABLED\)"' swingbot/config.py`
Expected: ten lines.

Run: `python -c "from swingbot.admin.guide import placeholders as p; need={'levels.families','CLUSTER_TOLERANCE_PCT','CONFLUENCE_DEVIATION_PCT','MIN_TARGET_CONFLUENCE_COUNT','MIN_ALERT_CONFIDENCE_LEVEL','levels.touch_atr','levels.break_atr','LEVEL_LIFECYCLE_STOPS_ENABLED'}; print(sorted(need-set(p.PLACEHOLDERS)))"`
Expected: `[]`.

- [ ] **Step 2: Write the failing tests**

Append to `tests/admin/test_guide_chapter_text.py`:

```python
# --- chapter 4: levels (v237 V237-9, V237-9b) ------------------------------------------

CH4_ANCHORS = ["the-next-level-idea", "level-families", "confluence-counts-families",
               "bonus-confirmations", "touch-break-and-the-four-states"]


def test_chapter_4_header_and_plain_words_callout():
    chapter = _chapter("levels")
    assert (chapter.order, chapter.title) == (4, "Finding levels and setups")
    assert chapter.path.name == "04-levels.md"
    assert chapter.body.startswith("> **In plain words**")


def test_chapter_4_sections_in_order():
    assert _anchors(_chapter("levels")) == CH4_ANCHORS


def test_chapter_4_families_come_from_the_live_list():
    from swingbot.core.market.levels import ALL_STRATEGY_FAMILIES
    section = _section(_chapter("levels").body, "Level families")
    assert "{{levels.families}}" in section
    rendered = placeholders.resolve(section)
    assert all(f"- {family}" in rendered for family in ALL_STRATEGY_FAMILIES)
    assert "chapter 5" in section          # families are kept apart from strategies


def test_chapter_4_confluence_counts_families_with_live_numbers():
    section = _section(_chapter("levels").body, "Confluence counts families")
    assert {"CLUSTER_TOLERANCE_PCT", "CONFLUENCE_DEVIATION_PCT", "MIN_TARGET_CONFLUENCE_COUNT",
            "MIN_ALERT_CONFIDENCE_LEVEL"} <= set(placeholders.names_in(section))
    assert "counts once" in section


def test_chapter_4_lifecycle_has_four_states_and_no_retest():
    from swingbot.core.market import levels_lifecycle
    body = _chapter("levels").body
    section = _section(body, "Touch, break and the four states")
    assert all(f"| {state} |" in section for state in levels_lifecycle.STATES)
    assert {"levels.touch_atr", "levels.break_atr",
            "LEVEL_LIFECYCLE_STOPS_ENABLED"} <= set(placeholders.names_in(section))
    assert "retest" not in body.lower()


def test_chapter_4_types_no_rule_number_before_a_percent_sign():
    body = re.sub(r"\{\{[^}]*\}\}", "", _chapter("levels").body)
    assert not re.search(r"(?<![\w.])\d+(?:\.\d+)?[ \t]?%", body)


def test_chapter_4_resolves_and_links_only_written_chapters():
    chapter = _chapter("levels")
    assert "{{" not in placeholders.resolve(chapter.body)
    links = _GUIDE_LINK.findall(chapter.body)
    glossary = {anchor for slug, anchor in links if slug == "glossary"}
    assert glossary and glossary <= GLOSSARY_LINKED
    assert {slug for slug, _anchor in links} <= {"glossary", "pipeline", "what-it-is", "levels"}
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: FAIL — the seven chapter-4 tests report `docs/guide has no chapter 'levels'`; every earlier test passes.

- [ ] **Step 4: Write the first part of the chapter**

Create `docs/guide/04-levels.md` with exactly this text (UTF-8, LF, one trailing newline). The front matter already lists the sources V237-9b's sections describe; all exist today (Step 1).

````markdown
---
title: Finding levels and setups
slug: levels
order: 4
reviewed_for: 2.19.2
sources:
  - swingbot/core/market/levels.py:ALL_STRATEGY_FAMILIES
  - swingbot/core/market/levels.py:CLUSTER_TOLERANCE_PCT
  - swingbot/core/market/levels.py:collect_candidate_levels
  - swingbot/core/market/levels.py:count_confirming_strategies
  - swingbot/core/market/levels.py:build_level_map
  - swingbot/core/market/levels.py:build_scenarios
  - swingbot/core/market/levels_lifecycle.py:classify_levels
  - swingbot/core/market/levels_lifecycle.py:preferred_stop_anchor
  - swingbot/core/market/mtf.py:adjacent_aligned
  - swingbot/core/scanning/strategy_pass.py:completed_frame
  - swingbot/core/scanning/analyze.py:_horizon_scenarios
  - swingbot/core/scanning/requirements.py:_build_requirement_checks
  - swingbot/core/scanning/confidence.py
  - swingbot/core/scanning/dedup.py:dedup_scan_items
  - swingbot/core/planning/lifecycle.py:apply_level_lifecycle
  - swingbot/config.py:AVWAP_LEVELS_ENABLED
  - swingbot/config.py:MIN_REWARD_PCT
  - swingbot/config.py:CONFLUENCE_DEVIATION_PCT
  - swingbot/config.py:MIN_TARGET_CONFLUENCE_COUNT
  - swingbot/config.py:MIN_ALERT_CONFIDENCE_LEVEL
  - swingbot/config.py:SIGNAL_CONFIRMATION_SCANS
  - swingbot/config.py:DEDUP_TOLERANCE_PCT
  - swingbot/config.py:HTF_CONFLUENCE_ENABLED
  - swingbot/config.py:MTF_ADJACENT_GATE
  - swingbot/config.py:LEVEL_LIFECYCLE_STOPS_ENABLED
---

> **In plain words** The bot looks for prices where a stock has turned before: support below today's price, resistance above it. It plans a trade from today's price toward the next one. A level counts for more when several independent methods agree on it, only finished daily bars decide a signal, and a setup must promise a big enough move before it is considered at all.

## The next-level idea

Every scan starts from today's price, one ticker and one horizon at a time. Below the price sit [support](/insights/guide/glossary#support-and-resistance) levels, above it resistance. A long [scenario](/insights/guide/glossary#scenario) aims at the nearest resistance, with its stop beyond the nearest support; a short does the reverse. Both directions are tried every time, and either, both or neither may qualify.

The bot never invents a level. With no real support or resistance on one side there is no stop or no target, and the scenario is not built. Quiet days without alerts are the expected result of that rule, not a fault. Where this step sits in the whole scan is shown in [the pipeline](/insights/guide/pipeline).

<details><summary>Under the hood</summary>

`levels.build_level_map` clusters the candidate levels and returns supports below and resistances above the current price, nearest first. `levels.build_scenarios` builds at most one scenario per direction from them. Both run once per ticker and horizon inside `analyze._horizon_scenarios`.

</details>

## Level families

A [level family](/insights/guide/glossary#level-family) is one method of drawing price levels. The live list:

{{levels.families}}

Families are not the strategies of chapter 5. A family only draws prices; a strategy is an entry rule with its own measured record. A few names appear in both lists, such as VWAP, Volume Profile and Fibonacci, because the same idea can be used either way.

<details><summary>Under the hood</summary>

`levels.collect_candidate_levels` runs every family and labels each candidate with its source. `levels.strategy_family` folds the labels back into `ALL_STRATEGY_FAMILIES`, so the several anchors of an anchored VWAP still count as one AVWAP family. AVWAP candidates exist only while `AVWAP_LEVELS_ENABLED` is on.

</details>

## Confluence counts families

Candidates from different families that sit within {{CLUSTER_TOLERANCE_PCT}} of each other merge into one [level](/insights/guide/glossary#level). The [confluence](/insights/guide/glossary#confluence) of a target is then measured in a second, looser pass: how many distinct families put their own level within {{CONFLUENCE_DEVIATION_PCT}} of it. Each family counts once, however many lines it draws: several Fibonacci ratios near one price are one vote, not several.

A scenario needs at least {{MIN_TARGET_CONFLUENCE_COUNT}} families on its target, or it is dropped before it is scored. The same count, capped, is the starting point of the alert's [confidence](/insights/guide/glossary#confidence) level, so the filter and the score never disagree about how many families agree. Only alerts at confidence level {{MIN_ALERT_CONFIDENCE_LEVEL}} or higher are posted.

<details><summary>Under the hood</summary>

`levels._cluster_levels` merges candidates with `CLUSTER_TOLERANCE_PCT`. `levels.count_confirming_strategies(..., tolerance_pct=CONFLUENCE_DEVIATION_PCT)` runs for the target and again for the stop: the target count feeds the requirement `min_confluence` (`requirements._build_requirement_checks`) and step 1 of `scanning/confidence.py`; the stop count feeds a quality factor.

</details>

## Bonus confirmations

Two signals raise confidence but add no level: a volatility squeeze that breaks out on volume, and a candlestick reversal pattern. Neither can be measured against a target price, so neither counts as a family or moves a level.

<details><summary>Under the hood</summary>

Both are scored in `scanning/confidence.py`. `levels._STRATEGY_FAMILY_PREFIXES` maps their labels to "Volatility Squeeze" and "Candlestick Pattern", names deliberately absent from `ALL_STRATEGY_FAMILIES`.

</details>

## Touch, break and the four states

A level is judged by what price has done to it, on finished bars only. That record is the [level lifecycle](/insights/guide/glossary#level-lifecycle):

- **Touch**: a bar reaches within {{levels.touch_atr}} of the level and closes back on its own side.
- **Break**: a bar closes beyond the level by more than {{levels.break_atr}}.

| State | Meaning |
|---|---|
| fresh | never touched in the look-back window |
| tested | touched and held, recently |
| delivered | the latest decisive event was a break: price went through |
| decaying | touched and held, but not for a long time |

The most recent event wins, so a level that broke and was later touched and held again is no longer delivered. Level-lifecycle stops are {{LEVEL_LIFECYCLE_STOPS_ENABLED}}: when on, a plan's [stop](/insights/guide/glossary#stop) moves beyond a tested level instead of sitting inside the noise around a fresh one, and the target is chosen again against the wider risk. If no target then pays enough, the original stop and target are kept. Chapter 7 covers stops in full.

<details><summary>Under the hood</summary>

`levels_lifecycle.classify_levels(df, i, levels, horizon_key=...)` slices the frame to bar `i` before reading it. The window is the horizon's `sr_lookback` times `WINDOW_LOOKBACK_MULT` bars; a level decays after `sr_lookback` times `DECAY_LOOKBACK_MULT` bars without a touch. `preferred_stop_anchor` ranks tested over decaying over fresh and never returns a delivered level. The stop move is `planning/lifecycle.apply_level_lifecycle`.

</details>
````

- [ ] **Step 5: Regenerate the anchor fixture**

Run: `python scripts/dev/guide_anchors.py`
Then: `python scripts/dev/guide_anchors.py --check`
Expected: exit 0; the fixture gains `"levels": [...]` with the five anchors of `CH4_ANCHORS`, in order.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: PASS (`0 failed`), including v236's `test_every_linked_chapter_is_written` and `test_glossary_defines_every_term_the_guide_links_to` over the new chapter.

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_content.py`
Expected: PASS — `[sources]` resolves every `path:symbol` above, `[placeholders]` finds every name whitelisted, `[headings]` sees no heading inside `<details>` and none on a placeholder line, and the anchor fixture is in sync.

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_guide.py`
Expected: PASS.

If `[sources]` reports a symbol as no longer defined, the code moved after 2026-11-18: find its new home with `git grep -n`, correct the `sources:` entry and the matching "Under the hood" sentence, and say so in the task report.

- [ ] **Step 7: Commit (V237-9b completes the chapter; merge both together)**

```bash
git add docs/guide/04-levels.md tests/admin/test_guide_chapter_text.py frontend/src/app/workspaces/guide/guide-anchors.json
git commit -m "docs(guide): chapter 4 part one -- levels, families, confluence, lifecycle (v237 V237-9)"
```

### Task V237-9b: Chapter 4, part two: alignment, closed bars, minimum move, duplicate merge

**Model:** sonnet — four sections appended to a chapter, given whole below, plus two pinned text tests and an extended anchor list.

**Why.** The rest of spec v215 § chapter 4: multi-timeframe alignment (`mtf.py`), closed-bar-only confirmation, the minimum-move filters and the duplicate merge. Written from the code (index Handoff 6): the minimum move is `MIN_REWARD_PCT`, raised per horizon by `analyze._horizon_scenarios`, not the spec's "5%+"; adjacent-horizon alignment is a switch whose live state chapter 6 reads from the setting, so this chapter never hard-codes "off" (Handoff 5). Second half of the SPLIT V237-9 → V237-9b; **merge both together**.

**Files:**
- Modify (created by V237-9): `docs/guide/04-levels.md` (append four sections)
- Modify (created by v236 V236-8): `tests/admin/test_guide_chapter_text.py` (`CH4_ANCHORS`, two new tests)
- Regenerate: `frontend/src/app/workspaces/guide/guide-anchors.json`

**Interfaces:**
- Consumes: V237-9's chapter file (its front matter already lists `mtf.py:adjacent_aligned`, `strategy_pass.py:completed_frame`, `analyze.py:_horizon_scenarios`, `requirements.py:_build_requirement_checks`, `dedup.py:dedup_scan_items` and the config fields used here) and its tests (`CH4_ANCHORS`, the no-percent and link tests, which now also cover the new sections); placeholders `MIN_STOP_DISTANCE_PCT` (V235-3), `MIN_REWARD_PCT`, `MIN_RISK_REWARD_RATIO`, `DEDUP_TOLERANCE_PCT`, `SIGNAL_CONFIRMATION_SCANS` (V237-2), `HTF_CONFLUENCE_ENABLED` (V237-3b).
- Produces (ledger): the chapter's nine anchors — V237-9's five plus `higher-horizon-alignment`, `closed-bars-only`, `the-minimum-move`, `duplicate-merge`.

- [ ] **Step 1: Confirm the consumed names**

Run: `git grep -n "^## Touch, break and the four states" docs/guide/04-levels.md; git grep -n "^CH4_ANCHORS" tests/admin/test_guide_chapter_text.py`
Expected: one line each (V237-9).

Run: `git grep -n "^def horizon_trend\|^def adjacent_aligned" swingbot/core/market/mtf.py; git grep -n "^def atr_floor_pct" swingbot/core/market/levels.py; git grep -n "^def _plans_similar" swingbot/core/scanning/dedup.py; git grep -n "required_confirmations=config.SIGNAL_CONFIRMATION_SCANS" swingbot/core/scanning/scan_run.py`
Expected: five lines.

Run: `python -c "from swingbot.admin.guide import placeholders as p; need={'MIN_STOP_DISTANCE_PCT','MIN_REWARD_PCT','MIN_RISK_REWARD_RATIO','DEDUP_TOLERANCE_PCT','SIGNAL_CONFIRMATION_SCANS','HTF_CONFLUENCE_ENABLED'}; print(sorted(need-set(p.PLACEHOLDERS)))"`
Expected: `[]`.

- [ ] **Step 2: Write the failing tests**

In `tests/admin/test_guide_chapter_text.py`, replace V237-9's `CH4_ANCHORS` with:

```python
CH4_ANCHORS = ["the-next-level-idea", "level-families", "confluence-counts-families",
               "bonus-confirmations", "touch-break-and-the-four-states",
               "higher-horizon-alignment", "closed-bars-only", "the-minimum-move",
               "duplicate-merge"]
```

and append after the chapter-4 tests:

```python
def test_chapter_4_alignment_reads_the_switch_not_a_hard_coded_state():
    section = _section(_chapter("levels").body, "Higher-horizon alignment")
    assert "{{HTF_CONFLUENCE_ENABLED}}" in section
    assert "chapter 6" in section
    assert not re.search(r"\b(is|are|switched) (off|on)\b", section)


def test_chapter_4_minimum_move_and_confirmation_use_live_settings():
    body = _chapter("levels").body
    assert {"MIN_REWARD_PCT", "MIN_STOP_DISTANCE_PCT", "MIN_RISK_REWARD_RATIO"} <= set(
        placeholders.names_in(_section(body, "The minimum move")))
    assert "{{SIGNAL_CONFIRMATION_SCANS}}" in _section(body, "Closed bars only")
    assert "{{DEDUP_TOLERANCE_PCT}}" in _section(body, "Duplicate merge")
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: FAIL — `test_chapter_4_sections_in_order` (four anchors missing) and the two new tests (`IndexError` in `_section`); everything else passes.

- [ ] **Step 4: Append the four sections**

Append to `docs/guide/04-levels.md`, after the closing `</details>` of "Touch, break and the four states" (one blank line between, file still ends with one newline), exactly:

````markdown
## Higher-horizon alignment

Each horizon has its own trend, read from its fast and slow moving averages. Two checks compare a setup with a longer view:

- **Higher-timeframe bias** ({{HTF_CONFLUENCE_ENABLED}}): a counter-trend setup is flagged on the alert and in the plan's quality score. It never removes an alert or lowers its confidence.
- **Adjacent-horizon alignment**: drops a scenario when the next horizon up trends against it. The longest horizon, and any horizon with too little history, is exempt and never counted as agreement. Whether the live scan applies it is listed in chapter 6, read from its setting.

<details><summary>Under the hood</summary>

`mtf.adjacent_aligned(df, horizon_key, direction)` returns `aligned`, `opposed` or `exempt`; `mtf.horizon_trend` compares the horizon's `ema_fast` with its `ema_slow`. The drop is guarded by `MTF_ADJACENT_GATE`. The bias flag is `HTF_CONFLUENCE_ENABLED`, informational by design.

</details>

## Closed bars only

A daily bar is final only after its session closes. Strategy signals read [completed bars](/insights/guide/glossary#completed-bar) only: during the trading session the still-forming bar is dropped, so the live scan sees the bars a backtest of that day would see. Levels are measured against the current price, so a setup must also appear the same way on {{SIGNAL_CONFIRMATION_SCANS}} consecutive scans before it is confirmed, which filters out intraday flicker.

<details><summary>Under the hood</summary>

`strategy_pass.completed_frame(df, now)` removes only today's bar, and only during the regular session. `SIGNAL_CONFIRMATION_SCANS` drives the confirmation debounce in `scanning/scan_run.py`; in a replay one scan runs per completed bar, so the count is in daily bars there.

</details>

## The minimum move

A scenario is built only when it clears hard requirements, with no "close enough":

- The first target is at least {{MIN_REWARD_PCT}} away from today's price. Longer horizons raise this floor from their own target scale; they never lower it.
- The stop is at least {{MIN_STOP_DISTANCE_PCT}} from the entry, so ordinary noise does not reach it, and no further than the horizon's own stop limit. The tighter caps a plan must then meet are in chapter 7.
- The first target pays at least {{MIN_RISK_REWARD_RATIO}} [reward to risk](/insights/guide/glossary#reward-to-risk-rr).

<details><summary>Under the hood</summary>

`analyze._horizon_scenarios` uses the larger of `MIN_REWARD_PCT` and a fixed share of the horizon's `sr_target_min_pct` as the reward floor, and the larger of `MAX_STOP_LOSS_PCT` and the horizon's `max_risk_pct` as the stop limit; `levels.atr_floor_pct` adds a volatility floor under the stop distance. `requirements._build_requirement_checks` records which checks a scenario passed for the requirement table.

</details>

## Duplicate merge

Several horizons can point at almost the same trade. Before alerts post, plans on the same ticker and direction whose entry, stop and target all lie within {{DEDUP_TOLERANCE_PCT}} of each other merge into one alert. The plan with the highest confidence score is kept, and the alert lists what it absorbed.

<details><summary>Under the hood</summary>

`dedup.dedup_scan_items` groups items by ticker and direction, clusters them with `_plans_similar`, keeps the highest `conf.score` and records the others in `combined_from`.

</details>
````

- [ ] **Step 5: Regenerate the anchor fixture**

Run: `python scripts/dev/guide_anchors.py`
Then: `python scripts/dev/guide_anchors.py --check`
Expected: exit 0; `"levels"` now lists all nine anchors of `CH4_ANCHORS`, in order.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: PASS (`0 failed`) — including V237-9's `test_chapter_4_types_no_rule_number_before_a_percent_sign` and `test_chapter_4_resolves_and_links_only_written_chapters` over the whole chapter.

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_content.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_guide.py`
Expected: PASS.

Run: `cd frontend && npx ng test --watch=false --include src/app/workspaces/guide/guide-anchors.spec.ts`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add docs/guide/04-levels.md tests/admin/test_guide_chapter_text.py frontend/src/app/workspaces/guide/guide-anchors.json
git commit -m "docs(guide): chapter 4 part two -- alignment, closed bars, minimum move, duplicate merge (v237 V237-9b)"
```

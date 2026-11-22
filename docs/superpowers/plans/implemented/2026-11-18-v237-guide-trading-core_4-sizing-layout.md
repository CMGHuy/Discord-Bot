# v237 — Guide trading core, part 4: chapter 8 (sizing and risk), chapter links, layout check, CI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V237-13b" -A 300 <this file>`).

**Spec:** v215 — [2026-11-06-v215-guide-page.md](../specs/2026-11-06-v215-guide-page.md), Plan B, chapter 8 and the Plan B layout check.
**Index:** [2026-11-18-v237-guide-trading-core_0-index.md](2026-11-18-v237-guide-trading-core_0-index.md) — Global Constraints, Parallelisation, the task ledger and the Handoff apply to every task here.

Part rules (from the index, repeated because each task is read alone):
- Chapter 8 (order 8) has no bare number before `%` outside code fences (the real content test `[bare percent]`); every rule number is a placeholder. Example arithmetic in dollars and shares is allowed; a percent never is.
- Chapter 8 describes only what is live (index Handoff 5). Portfolio heat, correlated heat and the kill switch act on alerts. The sector heat cap, the per-horizon cap, `MAX_OPEN_POSITIONS`, the drawdown ladder, the losing-streak cut and the Kelly/volatility estimates do not (verified 2026-11-18: `sector_check`, `horizon_check`, `streak_multiplier` and `DD_THROTTLE_ENABLED` have no reader in `swingbot/` outside their own module and `config.py`; `current_throttle` is called only by `backtesting/backtest_wf.py`, `edge/portfolio_state.py` and `tracking/account_reset.py`; the alert path passes no `strategy_stats`/`ticker_atr_pct` to `compute_position_size`).
- `max_position_pct` is a percent and a fresh account renders `0.1%` (index Handoff, part 1 split): the chapter never calls the position cap large or small.
- Links: every chapter of v236 + v237 exists by now (`what-it-is`, `pipeline`, `levels`, `strategies`, `gates`, `trade-plan`, `sizing-risk`, `glossary`); glossary anchors only from `GLOSSARY_LINKED`; no link to chapters 2, 9, 10, 11.

**Split and move (plan-writer part 4) — controller, please check.** Chapter 8 with its tests measured 30.7 KB as one task, so it ships as **V237-13** (front matter, callout, notice and the four per-trade sections) and **V237-13b** (the five portfolio-level sections and their sources); both merge together. The controller added the `V237-13b` ledger row directly below `V237-13`; to stay at 20 tasks, the old V237-15 (CI run) is folded into V237-14 as Steps 9–12. With the cap reached, the job the Handoff gave V237-13 — turning the plain "chapter N" mentions in chapters 4–7 into links ("Links for V237-13") — moves into **V237-14**, which runs right after V237-13b and already re-checks every chapter page. V237-14 therefore also modifies `docs/guide/04-levels.md`, `05-strategies.md`, `06-gates.md`, `07-trade-plan.md` and `tests/admin/test_guide_chapter_text.py`; no other part depends on its file list.

**Finding fixed in V237-13b.** V237-8's glossary term `Drawdown throttle` says "When switched on, new entries are sized down …", but `DD_THROTTLE_ENABLED` has no reader outside `config.py` and the live suggested size never applies the ladder. V237-13b rewrites that sentence so the glossary agrees with chapter 8 (V237-8's test still finds `{{DD_THROTTLE_ENABLED}}` in it). Wiring the throttle into live sizing changes trading behaviour: out of scope, a candidate for its own spec.

# Phase 6 — Chapter 8, links, layout, CI

### Task V237-13: Chapter 8, part one: the limits, the share count, sizing modes, gap-aware sizing

**Model:** sonnet — chapter text given whole below plus pinned text tests; the implementer re-verifies every `sources:` symbol and placeholder.

**Why.** Spec v215 § chapter 8: the three separate limits and which binds first, how the suggested size is computed for the stored account, the sizing mode and gap-aware sizing: everything that sizes one trade. Written from the code (index Handoff 4–6): the sizing numbers come from the stored account row (`load_account_config`, V237-1), not the `.env` seeds; the chapter says that the Kelly and volatility modes get no estimate on the alert path. Split at the 20 KB cap (SPLIT V237-13 → V237-13b): this task creates the file with the callout, the notice and sections 1–4; V237-13b appends the portfolio-level sections (heat, the brakes, the three outcomes, the caps that are not applied, costs). **Merge both together**; V237-13b runs right after this task.

**Files:**
- Create: `docs/guide/08-sizing-risk.md`
- Modify (created by v236 V236-8): `tests/admin/test_guide_chapter_text.py` (append the chapter-8 tests)
- Regenerate: `frontend/src/app/workspaces/guide/guide-anchors.json`

**Interfaces:**
- Consumes: placeholders `MAX_STOP_LOSS_PCT`, `RISK_PER_TRADE_PCT.max`, `sizing.kelly_cap`, `sizing.risk_floor`, `sizing.risk_ceiling`, `sizing.gap` (V235-3), `RISK_PER_TRADE_PCT`, `MAX_RISK_AMOUNT_ABSOLUTE`, `POSITION_SIZING_MODE`, `MAX_POSITION_SIZE_PCT`, `MAX_POSITION_VALUE_ABSOLUTE` (V237-1, stored row), `stop.hard_cap` (V237-2); anchor `trade-plan#the-stop-distance-cap-and-the-clamp` (V237-12); test names `CH7_LINKABLE` (V237-12), `_NO_PCT` (V237-10), `GLOSSARY_LINKED` (V237-8), `live_risk`, `_ACCOUNT_ROW` (V237-1), v236 helpers `_chapter`, `_anchors`, `_section`, `_GUIDE_LINK`.
- Produces: `docs/guide/08-sizing-risk.md` — slug `sizing-risk`, order 8, title `Sizing and risk`, anchors `three-limits-not-one`, `how-the-share-count-is-found`, `sizing-modes`, `gap-aware-sizing`; test names `CH8_ANCHORS` (V237-13b extends it to the ledger's nine), `CH8_LINKABLE` (V237-14 uses it), `CH8_NOTICE`.

Links: every chapter exists; self-links name only headings this task writes.

- [ ] **Step 1: Confirm every source and placeholder exists**

Run: `git grep -n "^def compute_position_size\|^def load_account_config\|^_SEED_ENV_KEYS\|^def _edge_risk_pct\|^def _sizing_distance\|^def _apply_size_caps\|^def _cap_to_risk_ceiling" swingbot/core/planning/account.py`
Expected: seven lines.

Run: `git grep -n "^def size_for(\|^def size_for_plan\|^def stamp_gap_sizing\|^LOOKBACK" swingbot/core/planning/gap_sizing.py; git grep -n "^def effective_risk_pct\|^def kelly_risk_pct\|^def vol_target_risk_pct\|^KELLY_FRACTION_CAP\|^RISK_FLOOR_PCT\|^RISK_CEILING_PCT" swingbot/core/edge/sizing.py`
Expected: ten lines.

Run: `git grep -n "^def size_mult" swingbot/core/market/opex.py; git grep -n "^HARD_MAX_PLANNED_LOSS_PCT" swingbot/core/risk_limits.py`
Expected: two lines.

Run: `git grep -c -e 'Field("RISK_PER_TRADE_PCT"' -e 'Field("MAX_RISK_AMOUNT_ABSOLUTE"' -e 'Field("MAX_STOP_LOSS_PCT"' -e 'Field("POSITION_SIZING_MODE"' -e 'Field("MAX_POSITION_SIZE_PCT"' -e 'Field("MAX_POSITION_VALUE_ABSOLUTE"' -e 'Field("SHORT_GAP_SIZING"' -e 'Field("LONG_GAP_SIZING"' -e 'Field("OPEX_CAUTION_ENABLED"' -e 'Field("OPEX_SIZE_REDUCTION_PCT"' swingbot/config.py`
Expected: `10` (with or without the path prefix).

Run: `python -c "from swingbot.admin.guide import placeholders as p; need={'MAX_STOP_LOSS_PCT','RISK_PER_TRADE_PCT','RISK_PER_TRADE_PCT.max','MAX_RISK_AMOUNT_ABSOLUTE','POSITION_SIZING_MODE','MAX_POSITION_SIZE_PCT','MAX_POSITION_VALUE_ABSOLUTE','sizing.kelly_cap','sizing.risk_floor','sizing.risk_ceiling','sizing.gap','stop.hard_cap'}; print(sorted(need-set(p.PLACEHOLDERS)))"`
Expected: `[]`.

Code facts this half states (read 2026-11-18): `compute_position_size` applies `max_position_pct`, `MAX_POSITION_VALUE_ABSOLUTE`, `MAX_RISK_AMOUNT_ABSOLUTE`, then `RISK_CEILING_PCT` last in both modes, and recomputes risk and value from the final shares; `_edge_risk_pct` runs an estimator only when `strategy_stats` / `ticker_atr_pct` are passed, and `gap_sizing.size_for_plan` passes neither, so `effective_risk_pct` returns the stored risk floored at `RISK_FLOOR_PCT`; `opex.size_mult` scales the budget on a monthly expiration while `OPEX_CAUTION_ENABLED`. If one changed, correct its sentence and report it.

- [ ] **Step 2: Write the failing tests**

Append to `tests/admin/test_guide_chapter_text.py`:

```python
# --- chapter 8: sizing and risk (v237 V237-13, V237-13b) --------------------------------

CH8_ANCHORS = ["three-limits-not-one", "how-the-share-count-is-found", "sizing-modes",
               "gap-aware-sizing"]
CH8_LINKABLE = CH7_LINKABLE | {"sizing-risk"}
CH8_NOTICE = ("Education about a paper-trading tool, not advice: alerts are not tailored to you, "
              "a suggested size is a default, and past results do not predict future ones.")


def test_chapter_8_header_callout_and_notice():
    chapter = _chapter("sizing-risk")
    assert (chapter.order, chapter.title) == (8, "Sizing and risk")
    assert chapter.path.name == "08-sizing-risk.md"
    blocks = chapter.body.split("\n\n")
    assert blocks[0].startswith("> **In plain words**")
    assert blocks[1] == CH8_NOTICE


def test_chapter_8_sections_in_order():
    assert _anchors(_chapter("sizing-risk")) == CH8_ANCHORS


@pytest.mark.parametrize("heading, names", [
    ("Three limits, not one", {"stop.hard_cap", "MAX_STOP_LOSS_PCT", "RISK_PER_TRADE_PCT",
                               "RISK_PER_TRADE_PCT.max", "MAX_RISK_AMOUNT_ABSOLUTE"}),
    ("How the share count is found", {"MAX_POSITION_SIZE_PCT", "MAX_POSITION_VALUE_ABSOLUTE",
                                      "sizing.risk_ceiling"}),
    ("Sizing modes", {"POSITION_SIZING_MODE", "sizing.kelly_cap", "sizing.risk_floor"}),
    ("Gap-aware sizing", {"sizing.gap"}),
])
def test_chapter_8_sizing_numbers_are_placeholders(heading, names):
    assert names <= set(placeholders.names_in(_section(_chapter("sizing-risk").body, heading)))


def test_chapter_8_limits_come_from_the_stored_account(monkeypatch):
    monkeypatch.setattr(live_risk, "_load_account",
                        lambda: {**_ACCOUNT_ROW, "risk_pct": 0.5, "max_risk_amount_absolute": 250.0})
    rendered = placeholders.resolve(_section(_chapter("sizing-risk").body, "Three limits, not one"))
    assert "0.5%" in rendered and "$250" in rendered


def test_chapter_8_says_the_edge_modes_get_no_estimate_live():
    section = _section(_chapter("sizing-risk").body, "Sizing modes")
    assert "The alert path passes them no strategy record and no volatility reading" in section


def test_chapter_8_resolves_and_links_only_written_chapters():
    chapter = _chapter("sizing-risk")
    rendered = placeholders.resolve(chapter.body)
    assert "{{" not in rendered and "not available right now" not in rendered
    links = _GUIDE_LINK.findall(chapter.body)
    glossary = {anchor for slug, anchor in links if slug == "glossary"}
    assert glossary and glossary <= GLOSSARY_LINKED
    assert {slug for slug, _anchor in links} <= CH8_LINKABLE
    assert not _NO_PCT.search(re.sub(r"\{\{[^}]*\}\}", "", chapter.body))
```

`_section(body, heading)` matches only the full `## <heading>\n` line. The account fixture (`_stored_account`, V237-1) is autouse, so the "now" values render from `_ACCOUNT_ROW` and never read the database.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: FAIL — the chapter-8 tests report `docs/guide has no chapter 'sizing-risk'`; every earlier test passes.

- [ ] **Step 4: Write the first part of the chapter**

Create `docs/guide/08-sizing-risk.md` with exactly this text (UTF-8, LF, one trailing newline). V237-13b adds the sources of its own sections to the front matter.

````markdown
---
title: Sizing and risk
slug: sizing-risk
order: 8
reviewed_for: 2.19.2
sources:
  - swingbot/core/planning/account.py:compute_position_size
  - swingbot/core/planning/account.py:load_account_config
  - swingbot/core/planning/account.py:_SEED_ENV_KEYS
  - swingbot/core/planning/account.py:_edge_risk_pct
  - swingbot/core/planning/account.py:_sizing_distance
  - swingbot/core/planning/account.py:_apply_size_caps
  - swingbot/core/planning/account.py:_cap_to_risk_ceiling
  - swingbot/core/planning/gap_sizing.py:size_for
  - swingbot/core/planning/gap_sizing.py:size_for_plan
  - swingbot/core/planning/gap_sizing.py:stamp_gap_sizing
  - swingbot/core/planning/gap_sizing.py:LOOKBACK
  - swingbot/core/edge/sizing.py:effective_risk_pct
  - swingbot/core/edge/sizing.py:kelly_risk_pct
  - swingbot/core/edge/sizing.py:vol_target_risk_pct
  - swingbot/core/edge/sizing.py:KELLY_FRACTION_CAP
  - swingbot/core/edge/sizing.py:RISK_FLOOR_PCT
  - swingbot/core/edge/sizing.py:RISK_CEILING_PCT
  - swingbot/core/market/opex.py:size_mult
  - swingbot/core/risk_limits.py:HARD_MAX_PLANNED_LOSS_PCT
  - swingbot/config.py:RISK_PER_TRADE_PCT
  - swingbot/config.py:MAX_RISK_AMOUNT_ABSOLUTE
  - swingbot/config.py:MAX_STOP_LOSS_PCT
  - swingbot/config.py:POSITION_SIZING_MODE
  - swingbot/config.py:MAX_POSITION_SIZE_PCT
  - swingbot/config.py:MAX_POSITION_VALUE_ABSOLUTE
  - swingbot/config.py:SHORT_GAP_SIZING
  - swingbot/config.py:LONG_GAP_SIZING
  - swingbot/config.py:OPEX_CAUTION_ENABLED
  - swingbot/config.py:OPEX_SIZE_REDUCTION_PCT
---

> **In plain words** The suggested size on an alert is the number of shares that loses a set amount of money if the stop is hit, worked out for the account stored in the bot's settings, not for yours. Several separate limits shape it, and the smallest one wins. When the portfolio already carries as much risk as it may, the alert still posts, with a size of zero, so you can see what the limit cost.

Education about a paper-trading tool, not advice: alerts are not tailored to you, a suggested size is a default, and past results do not predict future ones.

## Three limits, not one

Three different numbers limit what one trade can lose, and each acts at a different step:

| Limit | What it measures | Now | Past it |
|---|---|---|---|
| [Stop-distance cap](/insights/guide/glossary#stop-distance-cap) | distance from entry to stop, as a share of the entry price | {{stop.hard_cap}}; the setting, now {{MAX_STOP_LOSS_PCT}}, cannot go above it | the stop is clamped or the plan rejected ([chapter 7](/insights/guide/trade-plan#the-stop-distance-cap-and-the-clamp)) |
| [Risk per trade](/insights/guide/glossary#risk-per-trade) | share of the account lost at the stop | {{RISK_PER_TRADE_PCT}}, never more than {{RISK_PER_TRADE_PCT.max}} | fewer shares |
| [Dollar risk cap](/insights/guide/glossary#dollar-risk-cap) | money lost at the stop | {{MAX_RISK_AMOUNT_ABSOLUTE}} | fewer shares |

The first decides whether a plan exists at all; the other two decide how many shares it gets. Of the two money limits, whichever is less money wins: on a small account the risk per trade usually binds, on a large one the dollar cap does.

The values shown are the stored account's, read when this page is drawn. The `.env` settings only seed a new account; `!account risk` and `!account maxrisk` change the stored values.

<details><summary>Under the hood</summary>

`account.load_account_config()` returns the stored account row; `account._SEED_ENV_KEYS` lists the settings that seed it when it is first created. The stop-distance cap is the constant `risk_limits.HARD_MAX_PLANNED_LOSS_PCT`, not a setting.

</details>

## How the share count is found

1. The risk budget is the balance times the risk per trade.
2. The share count is the budget divided by the distance from entry to stop (or a wider sizing distance, see [gap-aware sizing](#gap-aware-sizing)).
3. Three caps can cut it, and the tightest wins: the position's value may not pass {{MAX_POSITION_SIZE_PCT}} of the balance, nor {{MAX_POSITION_VALUE_ABSOLUTE}}, and its loss at the stop may not pass the dollar risk cap.
4. Last, in every sizing mode, the loss at the stop may never pass {{sizing.risk_ceiling}} of the balance; the share count is rounded down when rounding up would break it.

For example, a balance of $10,000 with a risk budget of $100 and a stop $2.00 below a $50.00 entry gives 50 shares, a $2,500 position; a position cap below $2,500 cuts the shares further. The risk and position value an alert shows are recomputed from the final share count, so they are what a stop-out would really cost.

The balance is the stored starting balance plus everything the paper book has realised since. The [suggested size](/insights/guide/glossary#suggested-size) is copied onto the trade when it is logged, so a later change of balance or mode never resizes an open trade. On a monthly options-expiration day the size can be cut further.

<details><summary>Under the hood</summary>

Alerts size through `gap_sizing.size_for_plan`, which calls `account.compute_position_size`. Caps 1 to 3 are `account._apply_size_caps`; the ceiling is `account._cap_to_risk_ceiling` with `sizing.RISK_CEILING_PCT`. `opex.size_mult` scales the budget on a monthly expiration while `OPEX_CAUTION_ENABLED` is set, by `OPEX_SIZE_REDUCTION_PCT`.

</details>

## Sizing modes

The stored account's sizing mode is now {{POSITION_SIZING_MODE}}.

| Mode | How the size is set |
|---|---|
| `risk_pct` | the steps above: a stop-out loses the risk per trade |
| `account_pct` | the position's value is a fixed share of the balance, whatever the stop distance; the caps and the ceiling still apply |
| `kelly` | a fraction of the Kelly bet from the strategy's record, capped at {{sizing.kelly_cap}} |
| `vol_target` | a risk that keeps the portfolio's estimated daily swing near a target |
| `min_of_all` | the lowest of the estimates |

The last three can only lower the risk per trade, never raise it, and never take it below {{sizing.risk_floor}}. The alert path passes them no strategy record and no volatility reading, so in those modes an alert today is sized on the risk per trade, floored at {{sizing.risk_floor}}.

<details><summary>Under the hood</summary>

`account._edge_risk_pct` resolves the three edge modes through `sizing.effective_risk_pct` (the minimum of the estimates that exist, floored at `RISK_FLOOR_PCT`). `sizing.kelly_risk_pct` runs only with `strategy_stats` and `sizing.vol_target_risk_pct` only with `ticker_atr_pct`; `gap_sizing.size_for_plan` passes neither.

</details>

## Gap-aware sizing

A stop is the price where you intend to get out, but a stock can open beyond it ([gap through the stop](/insights/guide/glossary#gap-through-the-stop)). Gap-aware sizing divides the risk budget by the larger of the stop distance and a bad but routine gap for that ticker, so such a gap stays inside the money you meant to risk. It only ever lowers the share count: the stop does not move, and [R](/insights/guide/glossary#r-multiple) is still measured on the stop.

{{sizing.gap}}

The rule in force is stamped on a plan when it is created, so switching it later never resizes an alert already posted.

<details><summary>Under the hood</summary>

`gap_sizing.stamp_gap_sizing` records the rule and the ticker's gaps over `gap_sizing.LOOKBACK` completed bars; `gap_sizing.size_for` passes the gap as `gap_floor_pct` and `account._sizing_distance` takes the larger distance. Settings: `SHORT_GAP_SIZING`, `LONG_GAP_SIZING`.

</details>
````

- [ ] **Step 5: Regenerate the anchor fixture**

Run: `python scripts/dev/guide_anchors.py`
Then: `python scripts/dev/guide_anchors.py --check`
Expected: exit 0; the fixture gains `"sizing-risk": [...]` with the four `CH8_ANCHORS`, in order.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: PASS (`0 failed`), including v236's link, self-link and glossary checks over the new chapter.

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_content.py`
Then: `python scripts/dev/testrun.py file tests/admin/test_api_v1_guide.py`
Expected: PASS both — `[bare percent]` now runs over chapter 8, with `[sources]`, `[placeholders]`, `[headings]` and the anchor-fixture check.

If `[sources]` reports a symbol no longer defined, find its new home with `git grep -n`, fix the `sources:` entry and the matching "Under the hood" sentence, and report it. The layout check pins three chapters until V237-14; do not run it here.

- [ ] **Step 7: Commit (V237-13b completes the chapter; merge both together)**

```bash
git add docs/guide/08-sizing-risk.md tests/admin/test_guide_chapter_text.py frontend/src/app/workspaces/guide/guide-anchors.json
git commit -m "docs(guide): chapter 8 part one -- limits, share count, sizing modes, gap sizing (v237 V237-13)"
```

### Task V237-13b: Chapter 8, part two: heat, the brakes, reject/clamp/size 0, caps not applied, costs

**Model:** sonnet — five sections appended to a chapter, given whole below, a one-paragraph glossary correction and pinned text tests that tie the "not applied" claims to the code.

**Why.** The rest of spec v215 § chapter 8: portfolio and correlated heat (the same figure as the Risk page), the three outcomes **reject** (logged `plan rejected (`), **clamp** and **size-0 alert**, and frictions, turnover and tax drag (educational, no jurisdiction advice). Written from the code (index Handoff 5): only portfolio heat, correlated heat and the kill switch act on alerts; the sector and per-horizon caps, `MAX_OPEN_POSITIONS`, the drawdown ladder and the streak cut exist but do not. A test fails the moment one of those gains a live caller, so the chapter cannot silently go stale. The glossary's `Drawdown throttle` term (V237-8) claims the ladder sizes entries down "when switched on"; it never does live, so this task corrects it (part header, "Finding"). Second half of the SPLIT V237-13 → V237-13b; **merge both together**.

**Files:**
- Modify (created by V237-13): `docs/guide/08-sizing-risk.md` (front-matter sources, five sections)
- Modify (V237-8): `docs/guide/12-glossary.md` (the `Drawdown throttle` paragraph only)
- Modify (created by v236 V236-8): `tests/admin/test_guide_chapter_text.py` (`CH8_ANCHORS`, new tests)
- Regenerate: `frontend/src/app/workspaces/guide/guide-anchors.json`

**Interfaces:**
- Consumes: V237-13's chapter file and tests (`CH8_ANCHORS`, `CH8_LINKABLE`, the link and no-percent test, which now covers the new sections); placeholders `CLAMP_STOP_TO_HARD_CAP`, `PORTFOLIO_HEAT_CAP_PCT`, `CORRELATED_HEAT_CAP_PCT`, `SECTOR_HEAT_CAP_PCT`, `correlation.threshold`, `correlation.window`, `correlation.sector_fallback` (V235-3), `alerts.per_week` (V235-4), `MAX_OPEN_POSITIONS` (V237-1), `stop.clamp_level`, `throttle.ladder`, `throttle.resume`, `throttle.streak`, `DD_THROTTLE_ENABLED`, `KILLSWITCH_DEFAULT_ON` (V237-2); anchors `trade-plan#targets-that-pay-for-the-risk` (V237-12b), `strategies#reading-a-card` (V237-10); `_term` (V237-8).
- Produces (ledger): the chapter's nine anchors — V237-13's four plus `portfolio-and-correlated-heat`, `drawdown-throttle-and-kill-switch`, `reject-clamp-or-size-0` (V237-14's deep link), `caps-that-are-not-applied`, `costs-turnover-and-tax`; test helper `_code_calls(pattern: str, *, skip: tuple[str, ...]) -> list[str]`.

- [ ] **Step 1: Confirm the consumed names and the "not applied" facts**

Run: `git grep -n "^## Gap-aware sizing" docs/guide/08-sizing-risk.md; git grep -n "^CH8_ANCHORS\|^CH8_LINKABLE" tests/admin/test_guide_chapter_text.py; git grep -n "^### Drawdown throttle" docs/guide/12-glossary.md`
Expected: four lines (V237-13, V237-8).

Every `sources:` entry this task adds is checked by `test_guide_content.py[sources]` in Step 6 (defs, assignments and `config.py` `Field` names); a missing one fails there.

Run: `python -c "from swingbot.admin.guide import placeholders as p; need={'CLAMP_STOP_TO_HARD_CAP','PORTFOLIO_HEAT_CAP_PCT','CORRELATED_HEAT_CAP_PCT','SECTOR_HEAT_CAP_PCT','correlation.threshold','correlation.window','correlation.sector_fallback','alerts.per_week','MAX_OPEN_POSITIONS','stop.clamp_level','throttle.ladder','throttle.resume','throttle.streak','DD_THROTTLE_ENABLED','KILLSWITCH_DEFAULT_ON'}; print(sorted(need-set(p.PLACEHOLDERS)))"`
Expected: `[]`.

Run: `git grep -n -e "sector_check(" -e "horizon_check(" -e "streak_multiplier(" -e "DD_THROTTLE_ENABLED" -- swingbot ":!swingbot/core/edge/heat.py" ":!swingbot/core/edge/throttle.py" ":!swingbot/config.py" ":!swingbot/admin/guide"`
Expected: no output.

Code facts this half states (read 2026-11-18): `scan_run` re-reads open trades per alert and calls `heat_check` / `cluster_check` with the account's `risk_pct`, passing no `sectors` to `cluster_exposure`; a block sets `item.heat_blocked` / `cluster_blocked` / `kill_switch_blocked` and `alert_embeds` posts the alert with the headline and size 0; `check_kill_triggers` runs once per scan and only engages, `!killswitch off` releases, and `KILLSWITCH_DEFAULT_ON` is only the state before a switch row exists (`KillswitchRepository.state`); `current_throttle` is called by `backtest_wf`, `portfolio_state` and `account_reset`; `MAX_OPEN_POSITIONS` adds the embed's "⚠️ Position limit" warning. If one changed, correct its sentence and report it.

- [ ] **Step 2: Write the failing tests**

In `tests/admin/test_guide_chapter_text.py`, replace the `CH8_ANCHORS = [...]` assignment V237-13 wrote with:

```python
CH8_ANCHORS = ["three-limits-not-one", "how-the-share-count-is-found", "sizing-modes",
               "gap-aware-sizing", "portfolio-and-correlated-heat",
               "drawdown-throttle-and-kill-switch", "reject-clamp-or-size-0",
               "caps-that-are-not-applied", "costs-turnover-and-tax"]
```

Then append after the chapter-8 tests:

```python
def _code_calls(pattern: str, *, skip: tuple[str, ...]) -> list[str]:
    """Files under swingbot/ (outside the `skip` prefixes) whose text matches `pattern`."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    found = []
    for path in sorted((root / "swingbot").rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if not rel.startswith(skip) and re.search(pattern, path.read_text(encoding="utf-8")):
            found.append(rel)
    return found


@pytest.mark.parametrize("heading, names", [
    ("Portfolio and correlated heat", {"PORTFOLIO_HEAT_CAP_PCT", "CORRELATED_HEAT_CAP_PCT",
                                       "correlation.threshold", "correlation.window"}),
    ("Drawdown throttle and kill switch", {"throttle.ladder", "throttle.resume", "throttle.streak",
                                           "DD_THROTTLE_ENABLED", "KILLSWITCH_DEFAULT_ON"}),
    ("Reject, clamp or size 0", {"stop.clamp_level", "CLAMP_STOP_TO_HARD_CAP"}),
    ("Caps that are not applied", {"SECTOR_HEAT_CAP_PCT", "MAX_OPEN_POSITIONS",
                                   "correlation.sector_fallback"}),
    ("Costs, turnover and tax", {"alerts.per_week"}),
])
def test_chapter_8_portfolio_numbers_are_placeholders(heading, names):
    assert names <= set(placeholders.names_in(_section(_chapter("sizing-risk").body, heading)))


def test_chapter_8_size_0_headlines_match_the_alert_embed():
    from pathlib import Path
    embeds = (Path(__file__).resolve().parents[2]
              / "swingbot" / "core" / "scanning" / "alert_embeds.py").read_text(encoding="utf-8")
    section = _section(_chapter("sizing-risk").body, "Reject, clamp or size 0")
    for headline in ("⛔ ENTRY BLOCKED — portfolio heat cap", "⛔ ENTRY BLOCKED — correlated cluster",
                     "⛔ ENTRIES PAUSED (kill switch"):
        assert headline in section and headline in embeds
    assert "`plan rejected (" in section


def test_chapter_8_says_which_brake_acts_on_alerts():
    section = _section(_chapter("sizing-risk").body, "Drawdown throttle and kill switch")
    assert "does not apply it" in section and "`!killswitch off`" in section


def test_chapter_8_unapplied_caps_are_still_unwired():
    """If one of these gains a live caller, chapter 8 must change with it."""
    section = _section(_chapter("sizing-risk").body, "Caps that are not applied")
    assert "MAX_OPEN_PER_HORIZON" in section and "not applied to the live scan" in section
    assert _code_calls(r"\b(sector_check|horizon_check|streak_multiplier)\(",
                       skip=("swingbot/core/edge/heat.py", "swingbot/core/edge/throttle.py")) == []
    assert _code_calls(r"\bDD_THROTTLE_ENABLED\b",
                       skip=("swingbot/config.py", "swingbot/admin/guide/")) == []


def test_chapter_8_costs_section_gives_no_tax_advice():
    section = _section(_chapter("sizing-risk").body, "Costs, turnover and tax")
    assert "before tax" in section and "ask a tax adviser" in section


def test_glossary_drawdown_throttle_agrees_with_chapter_8():
    term = _term("Drawdown throttle")
    assert "does not apply it" in term and "{{DD_THROTTLE_ENABLED}}" in term
    assert "When switched on" not in term
```

`_code_calls` reads every `swingbot/**/*.py` file once per call (well under a second); `swingbot/admin/guide/` is skipped because `live_rules.py` renders `{{DD_THROTTLE_ENABLED}}`.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: FAIL — `test_chapter_8_sections_in_order` (four anchors found, nine expected), the new chapter-8 tests (`IndexError` from `_section`: no such heading) and `test_glossary_drawdown_throttle_agrees_with_chapter_8`; every other test passes.

- [ ] **Step 4: Add the sources, the five sections and the glossary correction**

(a) In `docs/guide/08-sizing-risk.md`, insert these lines directly after the front-matter line `  - swingbot/config.py:OPEX_SIZE_REDUCTION_PCT` (still before the closing `---`):

```yaml
  - swingbot/core/edge/heat.py:open_heat
  - swingbot/core/edge/heat.py:heat_check
  - swingbot/core/edge/heat.py:sector_heat
  - swingbot/core/edge/heat.py:sector_check
  - swingbot/core/edge/heat.py:horizon_check
  - swingbot/core/edge/correlation.py:cluster_exposure
  - swingbot/core/edge/correlation.py:cluster_check
  - swingbot/core/edge/portfolio_state.py:open_heat_state
  - swingbot/core/edge/throttle.py:DD_LADDER
  - swingbot/core/edge/throttle.py:current_throttle
  - swingbot/core/edge/throttle.py:streak_multiplier
  - swingbot/core/edge/throttle.py:check_kill_triggers
  - swingbot/core/edge/throttle.py:set_kill
  - swingbot/core/edge/throttle.py:kill_state
  - swingbot/core/edge/frictions.py
  - swingbot/core/backtesting/backtest_wf.py
  - swingbot/core/planning/builders.py:_clamp_stop_to_hard_cap
  - swingbot/core/scanning/analyze.py:attach_plan_v2
  - swingbot/core/scanning/analyze.py:_sizing_reject_reason
  - swingbot/core/scanning/scan_run.py:_skip_rejected_plan
  - swingbot/core/scanning/alert_embeds.py
  - swingbot/config.py:CLAMP_STOP_TO_HARD_CAP
  - swingbot/config.py:PORTFOLIO_HEAT_CAP_PCT
  - swingbot/config.py:CORRELATED_HEAT_CAP_PCT
  - swingbot/config.py:SECTOR_HEAT_CAP_PCT
  - swingbot/config.py:MAX_OPEN_POSITIONS
  - swingbot/config.py:MAX_OPEN_PER_HORIZON
  - swingbot/config.py:DD_THROTTLE_ENABLED
  - swingbot/config.py:KILLSWITCH_DEFAULT_ON
  - swingbot/config.py:SLIPPAGE_BPS
  - swingbot/config.py:COMMISSION_PER_TRADE
```

(b) Append exactly this text to `docs/guide/08-sizing-risk.md`, after the `Gap-aware sizing` section's closing `</details>` and one blank line (UTF-8, LF, the file still ends with one trailing newline):

````markdown
## Portfolio and correlated heat

[Portfolio heat](/insights/guide/glossary#portfolio-heat) is what every open paper trade would lose at its original stop, added up, as a share of the account. It is the same figure the Risk page shows. Before an alert posts, the scan adds one more trade at the risk per trade; if the total would pass {{PORTFOLIO_HEAT_CAP_PCT}}, the alert posts as a [size-0 alert](/insights/guide/glossary#size-0-alert).

[Correlated heat](/insights/guide/glossary#correlated-heat) is the same sum over the open trades whose daily returns over the last {{correlation.window}} correlate above {{correlation.threshold}} with the new ticker. With the new trade added it may not pass {{CORRELATED_HEAT_CAP_PCT}}; past it, the alert also posts with size 0. Three trades in stocks that move together are close to one trade at three times the size, which is why this cap is tighter. In the scan, a pair with too little shared price history counts as not correlated.

<details><summary>Under the hood</summary>

Per alert, `scan_run` re-reads the open trades (so trades logged earlier in the same scan count) and calls `heat.heat_check(open_trades, balance, candidate_risk_pct=risk_pct)` and `correlation.cluster_check(correlation.cluster_exposure(...), risk_pct)`. The Risk page reads `portfolio_state.open_heat_state`, built on the same `heat.open_heat`.

</details>

## Drawdown throttle and kill switch

Two account-level brakes exist in the code; only the kill switch acts on alerts today.

The [drawdown throttle](/insights/guide/glossary#drawdown-throttle) is a ladder that sizes new entries down as the account falls from its peak:

{{throttle.ladder}}

Once paused, entries would resume only when the fall is back under {{throttle.resume}}. A losing streak adds its own cut: {{throttle.streak}}. The walk-forward backtest applies the ladder and the Risk page shows where the account stands on it, but the live suggested size does not apply it, whatever its setting says (now {{DD_THROTTLE_ENABLED}}); the streak cut is applied nowhere yet.

The [kill switch](/insights/guide/glossary#kill-switch) engages on its own when a scan sees a deep drawdown, a violent day in the S&P 500 ETF (SPY) or a broken data feed, and only a person can release it, with `!killswitch off`. While it is on, every alert posts with a suggested size of zero. On a fresh install it starts {{KILLSWITCH_DEFAULT_ON}}; after that its stored state rules.

<details><summary>Under the hood</summary>

`throttle.check_kill_triggers` runs once per scan and `throttle.set_kill` engages the switch; each alert reads `throttle.kill_state()`. `throttle.current_throttle` is called by `backtesting/backtest_wf.py` and `portfolio_state`; `DD_THROTTLE_ENABLED` has no reader outside `config.py`, and `throttle.streak_multiplier` has no caller.

</details>

## Reject, clamp or size 0

A plan that meets a limit ends in one of three ways:

| Outcome | When | What you see |
|---|---|---|
| reject | the plan broke a rule: a stop beyond the cap with clamping off, no target that pays for the risk, or a wide-stop plan that cannot size to its fixed dollar risk | nothing posts; the log reads `plan rejected (<reason>, stop … from entry) -- not posted` ([rejected plan](/insights/guide/glossary#rejected-plan)) |
| clamp | a level plan's stop lies beyond the cap and the clamp setting, now {{CLAMP_STOP_TO_HARD_CAP}}, is on | the alert posts with the stop moved in to {{stop.clamp_level}} from the entry ([clamp](/insights/guide/glossary#clamp)) |
| size 0 | portfolio heat, correlated heat or the kill switch | the alert posts flagged, with a suggested size of zero |

A size-0 alert carries one of these headlines:

- `⛔ ENTRY BLOCKED — portfolio heat cap`
- `⛔ ENTRY BLOCKED — correlated cluster`
- `⛔ ENTRIES PAUSED (kill switch: <reason>)`

It is shown rather than hidden so you see the setup and what the limit cost; free some heat, or release the switch, and the next alert sizes normally. A clamped plan has its target chosen again against the smaller risk ([chapter 7](/insights/guide/trade-plan#targets-that-pay-for-the-risk)).

<details><summary>Under the hood</summary>

`analyze.attach_plan_v2` sets the reject reason (`risk_cap`, or `risk_sizing` and the band reasons from `analyze._sizing_reject_reason`) and `scan_run._skip_rejected_plan` logs it. The clamp is `builders._clamp_stop_to_hard_cap`. The headlines come from `alert_embeds` reading `item.heat_blocked`, `item.cluster_blocked` and `item.kill_switch_blocked`.

</details>

## Caps that are not applied

Some limits exist in the settings or the code but do not act on alerts today. They are listed so you do not rely on them:

- **Sector heat cap** ({{SECTOR_HEAT_CAP_PCT}}): the Risk page shows heat per sector, but no sector limit is applied to the live scan.
- **Open trades per horizon** (`MAX_OPEN_PER_HORIZON`): a setting with a check behind it, not applied to the live scan. The help text of both settings describes a block the scan does not make.
- **Sector fallback for correlation**: on the Risk page, {{correlation.sector_fallback}}; the scan passes no sectors, so there such a pair counts as not correlated.
- **Max open positions** ({{MAX_OPEN_POSITIONS}}): never blocks; past it an alert carries a position-limit warning.
- **Drawdown throttle and streak cut**: see [above](#drawdown-throttle-and-kill-switch).
- **Kelly and volatility estimates**: see [sizing modes](#sizing-modes).

<details><summary>Under the hood</summary>

`heat.sector_check` and `heat.horizon_check` have no caller; `scan_run` calls `correlation.cluster_exposure` without `sectors`. The Risk page computes sector heat with `heat.sector_heat` and passes sectors to its own cluster view.

</details>

## Costs, turnover and tax

Swing trading turns an account over often. Alert rate: {{alerts.per_week}}. Each round trip pays a spread and possibly a commission, and a short also pays a fee to borrow the stock; a strategy that earns little per trade can lose all of it to these costs. Paper trades carry none of them, which is why every live figure in this guide says "costs not included".

The backtests behind the strategy badges can charge slippage, a commission and the short borrow fee, but the registry rows do not record whether a run did, so each card says "costs not recorded" ([chapter 5](/insights/guide/strategies#reading-a-card)).

Tax is the other drag. In many countries gains on positions held for days or weeks are taxed differently from gains held for years, and very frequent trading can change how an account is treated. Rules differ by country and by person: this guide gives no tax advice, and every result in it is labelled "before tax". For your own case, ask a tax adviser.

<details><summary>Under the hood</summary>

`edge/frictions.py`: `apply_frictions` (`SLIPPAGE_BPS` per side), `commission_r` (`COMMISSION_PER_TRADE` each way, in R) and `borrow_r` (shorts only). Every figure the guide prints goes through `provenance_label`, which states costs and "before tax".

</details>
````

(c) In `docs/guide/12-glossary.md`, under `### Drawdown throttle`, replace the paragraph V237-8 wrote (`When switched on, new entries are sized down step by step as the account falls from its peak, and paused at the deepest step until the account recovers part of the fall. It is {{DD_THROTTLE_ENABLED}} now.`) with:

```markdown
A ladder that sizes new entries down step by step as the account falls from its peak, and pauses them at the deepest step until the account recovers part of the fall. The walk-forward backtest applies it and the Risk page shows where the account stands on it; the live suggested size does not apply it yet, whatever its setting says (now {{DD_THROTTLE_ENABLED}}).
```

- [ ] **Step 5: Regenerate the anchor fixture**

Run: `python scripts/dev/guide_anchors.py`
Then: `python scripts/dev/guide_anchors.py --check`
Expected: exit 0; `"sizing-risk"` now lists the nine `CH8_ANCHORS`, in order (the glossary's anchors are unchanged).

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: PASS (`0 failed`), including V237-13's link and no-percent test over the whole chapter and V237-8's `test_glossary_level_lifecycle_and_throttle_follow_the_code`.

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_content.py`
Then: `python scripts/dev/testrun.py file tests/admin/test_api_v1_guide.py`
Expected: PASS both — `[bare percent]` finds no bare number before `%` in chapter 8; `[sources]` resolves every added entry.

- [ ] **Step 7: Commit (merge together with V237-13)**

```bash
git add docs/guide/08-sizing-risk.md docs/guide/12-glossary.md tests/admin/test_guide_chapter_text.py frontend/src/app/workspaces/guide/guide-anchors.json
git commit -m "docs(guide): chapter 8 part two -- heat, brakes, reject/clamp/size 0, unapplied caps, costs (v237 V237-13b)"
```


### Task V237-14: Layout check covers chapters 4–8 (and the chapter links), then CI

**Model:** sonnet — constant edits to v236's layout check with unit tests, fourteen exact text replacements in four chapters, one browser run against a local admin, then push and watch CI.

**Why.** v236's layout check (`scripts/dev/guide_layout_check.py`, V236-11) expects three chapters in the drawer and visits only v236's pages, so it fails from V237-9 on and never looks at the widest pages this plan adds: the strategy cards (chapter 5) and the limit table (chapter 8). This task moves it to the eight written chapters, adds both pages and a deep link to chapter 8's `reject-clamp-or-size-0`, adds the strategies page to the app-wide layout audit, and records the run. It also takes over the Handoff job "Links for V237-13" (part header, "Split and move"): chapters 4–7 name later chapters in plain text because those did not exist yet; now every one does, so each plain "chapter N" becomes a link to the section it means, and a test keeps it that way.

**Files:**
- Modify (created by v236 V236-11): `scripts/dev/guide_layout_check.py` (`PAGES`, `DEEP_LINKS`, `CHAPTERS_IN_DRAWER`, the report title)
- Modify (created by v236 V236-11): `tests/scripts/test_guide_layout_check.py`
- Modify (v236 V236-11b added the guide routes): `frontend/scripts/layout-audit-lib.mjs`, `frontend/scripts/layout-audit-lib.test.mjs`
- Modify (created by V237-9..V237-12b): `docs/guide/04-levels.md`, `docs/guide/05-strategies.md`, `docs/guide/06-gates.md`, `docs/guide/07-trade-plan.md` (links only; no heading changes, so `guide-anchors.json` stays as V237-13b left it)
- Modify (created by v236 V236-8): `tests/admin/test_guide_chapter_text.py` (four slug assertions, three new tests)
- Create: `docs/superpowers/results/2026-11-18-v237-guide-layout.md` (written by the script)

**Interfaces:**
- Consumes: `guide_layout_check.PAGES`, `DEEP_LINKS`, `CHAPTERS_IN_DRAWER`, `render_report(results, base, today)`, `main(argv, *, runner, env_path)` (`--base`, `--out`, `--report`; exit 0/1/2) from V236-11; `chapters.load_chapters()` and `Heading.anchor` (v235); `_chapter`, `_anchors`, `_GUIDE_LINK` (V236-8), `CH5_LINKABLE`/`CH6_LINKABLE`/`CH7_LINKABLE` (V237-10..12), `CH8_LINKABLE` (V237-13) in `tests/admin/test_guide_chapter_text.py`; chapter anchors from the ledger (V237-9..13b).
- Produces: `CHAPTERS_IN_DRAWER = 8`; `PAGES = ("", "what-it-is", "glossary", "strategies", "sizing-risk", "pipeline")`; `DEEP_LINKS = ("what-it-is#the-notice", "glossary#r-multiple", "sizing-risk#reject-clamp-or-size-0")`; layout-audit `ROUTES` += `/insights/guide/strategies`; the result note and its verdict, which Step 12 records in the index `## Handoff`; a green CI run (Steps 9–12), which `/close-out` reads.

- [ ] **Step 1: Check the names this task edits**

Run: `git grep -n "^PAGES\|^DEEP_LINKS\|^CHAPTERS_IN_DRAWER\|v236 guide layout check" scripts/dev/guide_layout_check.py`
Run: `git grep -n "^CH[5-8]_LINKABLE\|^_GUIDE_LINK\|^def _anchors\|links_only_written_chapters" tests/admin/test_guide_chapter_text.py`
Run: `git grep -n "insights/guide/pipeline\|ROUTES.length" frontend/scripts/layout-audit-lib.mjs frontend/scripts/layout-audit-lib.test.mjs`
Expected: each name found (five `test_chapter_N_resolves_and_links_only_written_chapters`, N = 4..8). If v236 or an earlier v237 task named one differently, use the name on disk and say so in the report.

- [ ] **Step 2: Write the failing layout-check tests**

Append to `tests/scripts/test_guide_layout_check.py`:

```python
# --- v237 V237-14: chapters 4-8 ----------------------------------------------------------

def _written():
    from swingbot.admin.guide import chapters
    return {chapter.slug: chapter for chapter in chapters.load_chapters()}


def test_drawer_expects_every_written_chapter():
    assert glc.CHAPTERS_IN_DRAWER == 8 == len(_written())


def test_pages_add_the_widest_trading_chapters_and_keep_pipeline_last():
    assert glc.PAGES == ("", "what-it-is", "glossary", "strategies", "sizing-risk", "pipeline")
    written = _written()
    assert all(page in written for page in glc.PAGES if page)


def test_every_deep_link_names_a_real_heading():
    assert "sizing-risk#reject-clamp-or-size-0" in glc.DEEP_LINKS
    written = _written()
    for link in glc.DEEP_LINKS:
        slug, anchor = link.split("#", 1)
        assert anchor in [heading.anchor for heading in written[slug].headings], link


def test_report_title_names_no_plan_and_lists_the_new_pages():
    text = glc.render_report([{"width": 1440, "problems": []}], "http://localhost:1234", "2026-11-18")
    assert text.startswith("# Guide layout check -- 2026-11-18\n")
    assert "`/insights/guide/strategies`" in text and "`/insights/guide/sizing-risk`" in text
    assert "`sizing-risk#reject-clamp-or-size-0`" in text
```

Run: `python scripts/dev/testrun.py file tests/scripts/test_guide_layout_check.py`
Expected: FAIL — `3 != 8`, the old `PAGES` tuple, the missing deep link, and the title `# v236 guide layout check`; v236's tests pass.

- [ ] **Step 3: Move the check to eight chapters**

In `scripts/dev/guide_layout_check.py`:

```python
PAGES = ("", "what-it-is", "glossary", "strategies", "sizing-risk", "pipeline")   # the last one is screenshotted
DEEP_LINKS = ("what-it-is#the-notice", "glossary#r-multiple", "sizing-risk#reject-clamp-or-size-0")
CHAPTERS_IN_DRAWER = 8
```

In `render_report`, change the first line from `f"# v236 guide layout check -- {today}"` to `f"# Guide layout check -- {today}"` (the note now serves v236 and v237). In the module docstring, change the first line to `Guide page layout check at three widths (v236 V236-11, v237 V237-14; spec v215 § Testing, "Layout").` and "drawer 640-1023" to "drawer 640-1023 listing every written chapter". `DEFAULT_OUT` and `DEFAULT_REPORT` stay; Step 7 passes `--out` and `--report`.

Run: `python scripts/dev/testrun.py file tests/scripts/test_guide_layout_check.py`
Expected: PASS (`0 failed`).

- [ ] **Step 4: Write the failing chapter-link tests**

In `tests/admin/test_guide_chapter_text.py`, in each of `test_chapter_4_resolves_and_links_only_written_chapters` and the chapter 5, 6 and 7 tests of the same name, replace the slug assertion's right-hand side (`{"glossary", "pipeline", "what-it-is", "levels"}`, `CH5_LINKABLE`, `CH6_LINKABLE`, `CH7_LINKABLE`) with `CH8_LINKABLE`: every chapter of v236 + v237 exists now. Then append:

```python
# --- v237 V237-14: chapters 4-8 link every chapter they name ---------------------------

TRADING_CHAPTERS = ("levels", "strategies", "gates", "trade-plan", "sizing-risk")
_PLAIN_CHAPTER = re.compile(r"(?<!\[)\bchapters? [4-8]\b", re.I)


@pytest.mark.parametrize("slug", TRADING_CHAPTERS)
def test_trading_chapters_link_every_chapter_they_name(slug):
    assert _PLAIN_CHAPTER.findall(_chapter(slug).body) == []


@pytest.mark.parametrize("slug", TRADING_CHAPTERS)
def test_trading_chapter_links_land_on_real_headings(slug):
    for target, anchor in _GUIDE_LINK.findall(_chapter(slug).body):
        if anchor and target != "glossary":
            assert anchor in _anchors(_chapter(target)), f"{slug} -> {target}#{anchor}"


def test_chapter_links_point_where_the_text_says():
    expected = {
        "levels": {("strategies", "strategies-are-not-level-families"), ("trade-plan", "the-stop"),
                   ("gates", "higher-horizon-alignment"), ("trade-plan", "the-stop-distance-cap-and-the-clamp")},
        "strategies": {("levels", ""), ("gates", "market-regime"), ("gates", "relative-strength"),
                       ("gates", "measured-not-used"), ("trade-plan", "targets-that-pay-for-the-risk"),
                       ("gates", "")},
        "gates": {("levels", "the-minimum-move"), ("trade-plan", "the-stop-distance-cap-and-the-clamp"),
                  ("sizing-risk", "portfolio-and-correlated-heat")},
        "trade-plan": {("sizing-risk", "how-the-share-count-is-found")},
    }
    for slug, links in expected.items():
        assert links <= set(_GUIDE_LINK.findall(_chapter(slug).body)), slug
```

`_GUIDE_LINK.findall` returns `(slug, "")` for a link without an anchor (its anchor group is optional). `re` and `pytest` are already imported (V236-8).

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: FAIL — `test_trading_chapters_link_every_chapter_they_name[levels|strategies|gates|trade-plan]` list the plain mentions, and `test_chapter_links_point_where_the_text_says` fails on `levels`; `[sizing-risk]` and every earlier test pass.

- [ ] **Step 5: Turn the plain mentions into links**

Replace each text exactly once (every old text occurs once in its file; if one is missing, the chapter task worded it differently: find the sentence and link it to the same target):

| File | Old text | New text |
|---|---|---|
| `04-levels.md` | `strategies of chapter 5.` | `strategies of [chapter 5](/insights/guide/strategies#strategies-are-not-level-families).` |
| `04-levels.md` | `Chapter 7 covers stops in full.` | `[Chapter 7](/insights/guide/trade-plan#the-stop) covers stops in full.` |
| `04-levels.md` | `is listed in chapter 6, read from its setting.` | `is listed in [chapter 6](/insights/guide/gates#higher-horizon-alignment), read from its setting.` |
| `04-levels.md` | `must then meet are in chapter 7.` | `must then meet are in [chapter 7](/insights/guide/trade-plan#the-stop-distance-cap-and-the-clamp).` |
| `05-strategies.md` | `and chapter 4 describe.` | `and [chapter 4](/insights/guide/levels) describe.` |
| `05-strategies.md` | `the regime gate of chapter 6.` | `the regime gate of [chapter 6](/insights/guide/gates#market-regime).` |
| `05-strategies.md` | `(relative strength, chapter 6)` | `(relative strength, [chapter 6](/insights/guide/gates#relative-strength))` |
| `05-strategies.md` | `switch them on (chapter 6).` | `switch them on ([chapter 6](/insights/guide/gates#measured-not-used)).` |
| `05-strategies.md` | `there is no alert (chapter 7).` | `there is no alert ([chapter 7](/insights/guide/trade-plan#targets-that-pay-for-the-risk)).` |
| `05-strategies.md` | `Every other gate is in chapter 6.` | `Every other gate is in [chapter 6](/insights/guide/gates).` |
| `06-gates.md` | `- the level rules of chapter 4:` | `- the level rules of [chapter 4](/insights/guide/levels#the-minimum-move):` |
| `06-gates.md` | `- a trade plan that can be built within the stop rules (chapter 7), then the portfolio limits (chapter 8);` | `- a trade plan that can be built within the stop rules ([chapter 7](/insights/guide/trade-plan#the-stop-distance-cap-and-the-clamp)), then the portfolio limits ([chapter 8](/insights/guide/sizing-risk#portfolio-and-correlated-heat));` |
| `06-gates.md` | `- a plan that can be built within the stop rules (chapter 7);` | `- a plan that can be built within the stop rules ([chapter 7](/insights/guide/trade-plan#the-stop-distance-cap-and-the-clamp));` |
| `07-trade-plan.md` | `computed to the stop (chapter 8).` | `computed to the stop ([chapter 8](/insights/guide/sizing-risk#how-the-share-count-is-found)).` |

Change nothing else in those files: no wording, no `sources:`, no `reviewed_for`.

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: PASS (`0 failed`) — including V237-9's `"chapter 5" in section` and V237-9b's `"chapter 6" in section` (the link text keeps the words) and v236's `test_every_linked_chapter_is_written`.

Run: `python scripts/dev/guide_anchors.py --check`
Then: `python scripts/dev/testrun.py file tests/admin/test_guide_content.py`
Expected: exit 0 (no heading changed); PASS (`0 failed`).

- [ ] **Step 6: Add the strategies page to the layout audit**

In `frontend/scripts/layout-audit-lib.test.mjs`, test `ROUTES visits every destination, section and tab once, on the v202 paths only (34)`: change `(34)` to `(35)` and `assert.equal(ROUTES.length, 34);` to `35` (if the count on disk differs, add 1 to it), and add `'/insights/guide/strategies',` after `'/insights/guide/pipeline',` in its `for (const route of [...])` list.

Run: `node --test frontend/scripts/layout-audit-lib.test.mjs`
Expected: FAIL — `34 !== 35` and the missing route.

In `frontend/scripts/layout-audit-lib.mjs`, change `'/insights/guide', '/insights/guide/pipeline',` in `ROUTES` to `'/insights/guide', '/insights/guide/pipeline', '/insights/guide/strategies',`.

Run: `node --test frontend/scripts/layout-audit-lib.test.mjs`
Expected: PASS.

- [ ] **Step 7: Run both checks against a local admin and write the result note**

1. Run `/replicate-prod-db` (shared `swing-db` container; login needs the users table). In a worktree, point `.env`'s `DATABASE_URL` at the local replica; never print it.
2. Build and serve the current bundle: `cd frontend && npm run build`, then `cp -r frontend/dist/frontend/browser/. swingbot/admin/static/app/` (the served `main-*.js` name must equal the `dist` one).
3. Start the admin in the background: `python admin_ui.py` (port 1234).
4. Run: `python scripts/dev/guide_layout_check.py --out logs/v237-layout --report docs/superpowers/results/2026-11-18-v237-guide-layout.md`
   Expected: `guide layout: 0 problems at 390, 820, 1440 px -> docs/superpowers/results/2026-11-18-v237-guide-layout.md`, exit 0. Exit 2: no session or no Playwright (`pip install playwright && python -m playwright install chromium`); the credentials are never printed.
5. Run: `node frontend/scripts/layout-audit.mjs --base http://localhost:1234 --widths 390,768,1440`
   Expected: exit 0. A finding on `/insights/guide/strategies` or `/insights/guide/sizing-risk` (a card table or the limit table pushing the page sideways, a target under 44 px) is fixed in the chapter's Markdown or in v236's `sb-guide .md table` rule, the touched test re-run alone, and both checks re-run. A finding on a page outside the guide is not this plan's: append it to the result note under `## Other pages` and leave it.
6. Read a screenshot (`logs/v237-layout/guide@<width>.png`) only to diagnose a failing check, at most 4 image reads.
7. Stop the admin server. If the copy left `swingbot/admin/static/app/` changes the branch does not otherwise carry, restore them with `git checkout -- swingbot/admin/static/app/`.

The note is the script's output; add nothing by hand except `## Other pages`.

- [ ] **Step 8: Commit (two scoped commits)**

```bash
git add docs/guide/04-levels.md docs/guide/05-strategies.md docs/guide/06-gates.md docs/guide/07-trade-plan.md tests/admin/test_guide_chapter_text.py
git commit -m "docs(guide): chapters 4-7 link every later chapter they name (v237 V237-14)"
git add scripts/dev/guide_layout_check.py tests/scripts/test_guide_layout_check.py frontend/scripts/layout-audit-lib.mjs frontend/scripts/layout-audit-lib.test.mjs docs/superpowers/results/2026-11-18-v237-guide-layout.md
git commit -m "test(guide): layout check covers chapters 4-8; strategies page in the audit (v237 V237-14)"
```

**Full-suite verification via CI (Steps 9–12).** This used to be V237-15; it is folded in here to keep the plan at 20 tasks (controller, 2026-11-18). Every earlier task ran only its own test files (index Global Constraints). The full suite, the `frontend-test` job (`guide-anchors.spec.ts` checks the regenerated fixture) and the complexity gate run once, in CI, over the merged branch. No step runs the full suite locally (CLAUDE.md, "Naming specs and plans"). A test that fails in CI is fixed in the file the failing task owns.

- [ ] **Step 9: Check that every task is on the branch**

Run: `for id in 1 2 3 3b 4 5 6 7 7b 8 9 9b 10 11 11b 12 12b 13 13b 14; do git log --oneline main..HEAD | grep -q "(v237 V237-$id)" || echo "missing V237-$id"; done`
Expected: no output. A `missing` line means that task is not on the branch: stop and report it.

Run: `git status --short`
Expected: empty (nothing left uncommitted; in particular no `swingbot/admin/static/app/` copy from Step 7).

- [ ] **Step 10: Push the branch and watch CI**

Run: `git push -u origin HEAD`
Then: `gh run list --branch "$(git branch --show-current)" --limit 1` and `gh run watch <run id> --exit-status`

CI runs one job per suite from `tests/suites.toml`, the `frontend-test` job and the complexity gate. Never run `python scripts/dev/testrun.py full` locally.

Expected: every job green, `0 failed` and `0 xfailed` in each suite summary (`gh run view <run id> --log | grep -E "[0-9]+ (passed|failed|xfailed)"`). A changed pass count is not a failure.

- [ ] **Step 11: Fix a red job (only if Step 10 is not green)**

For each failing test: read its failure from `gh run view <run id> --log-failed`, fix it in the file the owning task changed, and re-run it alone:
- Python: `python scripts/dev/testrun.py file <tests/…/test_file.py>` (a test that reaches the database: `/replicate-prod-db` first)
- Frontend: `cd frontend && npx ng test --watch=false --include <spec path>`
- Complexity gate: `python scripts/dev/complexity_gate.py` (split the function into named helpers; never `--update` to raise the baseline)

Commit the fix with a single-line message naming the task, e.g. `git commit -m "fix(guide): <what> (v237 V237-<n>)"`, push, and watch the new run. Repeat until green.

- [ ] **Step 12: Record the result**

Append one line to `## Handoff` in `docs/superpowers/plans/2026-11-18-v237-guide-trading-core_0-index.md`:

```markdown
- **CI (V237-14)**: run <run id>, <YYYY-MM-DD>, green (`0 failed`, `0 xfailed`); layout note `docs/superpowers/results/2026-11-18-v237-guide-layout.md`: <PASS|FAIL> at 390/820/1440 px.
```

```bash
git add docs/superpowers/plans/2026-11-18-v237-guide-trading-core_0-index.md
git commit -m "docs(v237): CI green, layout note recorded (v237 V237-14)"
git push
```

Then `/close-out` (bump level from the index header).

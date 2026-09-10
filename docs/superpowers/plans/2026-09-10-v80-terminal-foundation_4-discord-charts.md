# v80 — Terminal foundation, part 4: Discord charts

Part of `2026-09-10-v80-terminal-foundation_0-index.md`. Read its Global
Constraints before starting any task here.

# Phase 3 — Discord charts

## Parallelisation

- **Sequential: F21 → F22 → F23.**
  - F21 and F22 both edit `swingbot/core/charts/chart_style.py` and
    `tests/charts/test_chart_theme.py`, and F23 edits that test again.
  - F23 deletes `swingbot/admin/static/tokens.css`, which F21 stops reading.
- **F24 runs alongside F21–F23.** It touches only
  `swingbot/core/presentation/tokens.py` and `tests/presentation/test_tokens.py`.
- **When this phase can start.**
  - **F21 waits for F2** (and so F1): its test reads D1's colours and D2's
    series out of `frontend/src/styles/tokens.css`.
  - Otherwise the phase runs alongside F3 and all of Group A. No task here
    edits a frontend file.
- **Per-task Python command:** `python scripts/dev/testrun.py file <path>`,
  which takes exactly one target, so tasks run it once per file.
  `test_chart_theme.py` is in the slow tier; `file` runs it regardless.

## The D5 role assignment

The spec left the per-role colours to this plan, under three rules:
1. roles that can share the price pane get distinct colours;
2. indicator panes may reuse series;
3. nothing sits within ΔE 10 of gain or loss.

ΔE here is OKLab distance ×100, the normal-vision ΔE the dataviz validator
reports. CIE76 cannot enforce rule 3: today's pink resistance line is 15.4
CIE76 from `--neg`, which clears 10, but only 5.9 in OKLab.

**Who shares a pane** (read from `trade_chart.py:300-375, 765-800` and
`decision_chart.py`):

| Where | Drawn together |
|---|---|
| Price pane, always | candles and volume (gain/loss), entry, target, stop, last price, TP2 (when set), Keltner bands, volume profile, branch path arrows |
| Price pane, no confirming source (`target_primary is None and stop_primary is None`) | support and resistance trendlines |
| Price pane, confirming source passed | target-side and stop-side strategy overlays, primary and dimmed secondaries |
| Stat-chip row above the price pane | R:R (last-price colour), T2 (TP2), RSI, ADX (signal colour), MACD |
| MACD pane | histogram (gain/loss), MACD, signal |
| Decision chart price pane | entry, target, stop, AVWAP, regime shading (gain/loss) |

The two trendline branches are exclusive, so support/resistance can reuse the
stop-side/target-side colours. Even so, the price pane needs seven identities
at once besides gain and loss: entry, last price, TP2, Keltner, volume
profile and the two sides.

The six series cannot supply them. `--chart-1`/`--chart-6` measure 6.8 and
`--chart-2`/`--chart-4` 6.2, so at most four series are mutually ≥ 10 apart
alongside entry's `--chart-1`. The assignment therefore adds two D1 tokens,
lavender `--info` and grey `--text-muted`, and needs no dash-style sharing:

| Constant(s) | Today | Token | Hex |
|---|---|---|---|
| `CHART_BG` | `#0a0a0a` | `--surface` | `#131722` |
| `GRID_COLOR` / `SPINE_COLOR` | `#1c1c1c` / `#2a2a2a` | `--border` / `--border-strong` | `#2a2e39` / `#363a45` |
| `TEXT_COLOR` / `MUTED_TEXT_COLOR` | `#f0f0f0` / `#666666` | `--text` / `--text-muted` | `#d9dce4` / `#9195a0` |
| `CHIP_BG` / `CHIP_EDGE` | `#121212` / `#2a2a2a` | `--surface-raised` / `--border-strong` | `#1c212d` / `#363a45` |
| `UP_COLOR`, `TARGET_COLOR` | `#00d26a` | `--pos` | `#17c98e` |
| `DOWN_COLOR`, `STOP_COLOR` | `#ff4d4d` | `--neg` | `#ff5470` |
| `CURRENT_PRICE_COLOR` | `#ffb020` | `--warn` | `#ffb43d` |
| `ENTRY_COLOR` | `#4d9fff` | `--chart-1` | `#4c8dff` |
| `TARGET2_COLOR` | `#ab47bc` | `--chart-3` | `#a868e0` |
| `TARGET_STRATEGY_COLOR`, `TRENDLINE_RESISTANCE_COLOR` | `#ff9800`, `#ec407a` | `--chart-2` | `#c97a22` |
| `STOP_STRATEGY_COLOR`, `TRENDLINE_SUPPORT_COLOR` | `#29b6f6`, `#26c6da` | `--chart-5` | `#1a9db3` |
| `KC_COLOR` | `#4dd0e1` | `--text-muted` | `#9195a0` |
| `VOLUME_PROFILE_COLOR` | `#d4a94c` | `--info` | `#b39ddb` |
| `AVWAP_COLOR` | `#b39ddb` | `--info` | `#b39ddb` |
| `MACD_LINE_COLOR` / `SIGNAL_LINE_COLOR` / `RSI_LINE_COLOR` | `#42a5f5` / `#ff7043` / `#ba68c8` | `--chart-1` / `--chart-2` / `--chart-5` | `#4c8dff` / `#c97a22` / `#1a9db3` |
| `PATH_COLOR` | `#555555` | `--text-faint` | `#4e5361` |
| `DISCLAIMER_COLOR` (F22, new) | `#e2b25a` in `trade_chart.py` | `--warn` | `#ffb43d` |
| `HEATMAP_INK_DARK` / `_LIGHT` (F22, new) | `"black"` / `"white"` in `analytics_charts.py` | `--bg` / `--text` | `#0c0f16` / `#d9dce4` |
| `FOLD_YEAR_COLORS` (F22, new) | three hexes in `portfolio_charts.py` | `--chart-1..3` | adjacent series |

**Measured.** The distances below were computed with the OKLab helper F21 adds to the test:

| Check | Floor | Closest pair / value |
|---|---|---|
| Price pane, confirming-source branch | ≥ 10 | Keltner vs volume profile, 10.2; Keltner vs stop side, 10.3; TP2 vs volume profile, 13.5 |
| Price pane, plain-trendline branch | ≥ 10 | same values: support takes stop side's colour, resistance target side's |
| Stat-chip row | ≥ 10 | RSI vs MACD, 13.7; TP2 vs MACD, 14.3 |
| MACD pane | ≥ 10 | MACD vs signal, 31.5 |
| Decision chart | ≥ 10 | entry vs AVWAP, 14.9 |
| Every non-gain/loss constant vs gain and loss | ≥ 10 | 15.6 (`--chart-2` from loss, `--chart-5` from gain) |

**Corrections found while measuring, now recorded in the spec (D2, D5).**
- Every series is ≥ 15.6 from `--pos` (`--chart-5` is closest); the spec first said 12.1.
- `portfolio_charts.py` holds a three-hex tuple, not one hex.
- There is a fifth stray literal, `chart_drawing.py:180` `edgecolors="white"`.
  F22 moves all five, or its literal ban would fail.

---

### Task F21: The admin palette on every Discord chart

**Files:**
- Modify: `swingbot/core/charts/chart_style.py`:
  - the palette block, lines 25–93, from the `# ----` banner above
    "Professional dark theme" through `VOLUME_PROFILE_COLOR = "#d4a94c"`;
  - `PATH_COLOR` at line 241.
- Test: `tests/charts/test_chart_theme.py` (full rewrite)

**Interfaces:**
- Consumes: D1 and D2 values in `frontend/src/styles/tokens.css` (F1, F2).
- Produces:
  - `chart_style.THEME`, a dict keyed by admin token name without the
    leading `--`;
  - every existing colour constant, re-derived from `THEME` per the table
    above. The names are unchanged, so no importer changes.

  F22 adds `THEME["bg"]` and three constants; F23 removes the old mirror file.

- [ ] **Step 1: Write the failing tests**

Replace the whole of `tests/charts/test_chart_theme.py` with:

```python
# tests/charts/test_chart_theme.py
"""The Discord chart palette is the admin palette (spec v80 D5).

`chart_style.THEME` copies the frontend tokens it names. This file reads
`frontend/src/styles/tokens.css` and holds every chart colour to D5's rules:
it is a D1 token or a D2 series, it is not confusable with gain or loss, and
roles drawn together are distinct.
"""
import itertools
import math
import re
from pathlib import Path

import pytest

from swingbot.core.charts import chart_style as cs
from tests.conftest import assert_rendered

# ~85% of suite runtime lives in nine files like this one; excluded from
# the fast tier (scripts/dev/testrun.py fast). See docs/claude/testing-cost.md.
pytestmark = pytest.mark.slow

REPO = Path(__file__).resolve().parents[2]
TOKENS_CSS = REPO / "frontend" / "src" / "styles" / "tokens.css"

D1_TOKENS = frozenset({
    "bg", "surface", "surface-raised", "surface-overlay", "border", "border-strong",
    "text", "text-secondary", "text-muted", "text-faint",
    "accent", "accent-fill", "info", "pos", "neg", "warn",
})
D2_SERIES = frozenset(f"chart-{i}" for i in range(1, 7))

# constant -> the THEME key it must equal (the plan's D5 role table)
COLOUR_CONSTANTS = {
    "CHART_BG": "surface",
    "GRID_COLOR": "border",
    "SPINE_COLOR": "border-strong",
    "TEXT_COLOR": "text",
    "MUTED_TEXT_COLOR": "text-muted",
    "CHIP_BG": "surface-raised",
    "CHIP_EDGE": "border-strong",
    "UP_COLOR": "pos",
    "TARGET_COLOR": "pos",
    "DOWN_COLOR": "neg",
    "STOP_COLOR": "neg",
    "CURRENT_PRICE_COLOR": "warn",
    "ENTRY_COLOR": "chart-1",
    "TARGET2_COLOR": "chart-3",
    "TARGET_STRATEGY_COLOR": "chart-2",
    "STOP_STRATEGY_COLOR": "chart-5",
    "TRENDLINE_RESISTANCE_COLOR": "chart-2",
    "TRENDLINE_SUPPORT_COLOR": "chart-5",
    "AVWAP_COLOR": "info",
    "VOLUME_PROFILE_COLOR": "info",
    "KC_COLOR": "text-muted",
    "MACD_LINE_COLOR": "chart-1",
    "SIGNAL_LINE_COLOR": "chart-2",
    "RSI_LINE_COLOR": "chart-5",
    "PATH_COLOR": "text-faint",
}

GAIN_LOSS = frozenset({"UP_COLOR", "DOWN_COLOR", "TARGET_COLOR", "STOP_COLOR"})

# Roles drawn at the same time. trade_chart.py draws plain trendlines only
# when no confirming source was passed and strategy overlays otherwise, so
# the two branches are separate sets; the stat chips above the price pane
# and the decision chart are sets of their own.
_PRICE_PANE = ("ENTRY_COLOR", "CURRENT_PRICE_COLOR", "TARGET2_COLOR", "KC_COLOR",
               "VOLUME_PROFILE_COLOR", "PATH_COLOR")
CO_OCCURRING = {
    "price pane, confirming source": _PRICE_PANE + ("TARGET_STRATEGY_COLOR", "STOP_STRATEGY_COLOR"),
    "price pane, plain trendlines": _PRICE_PANE + ("TRENDLINE_RESISTANCE_COLOR", "TRENDLINE_SUPPORT_COLOR"),
    "stat-chip row": ("CURRENT_PRICE_COLOR", "TARGET2_COLOR", "RSI_LINE_COLOR",
                      "SIGNAL_LINE_COLOR", "MACD_LINE_COLOR"),
    "MACD pane": ("MACD_LINE_COLOR", "SIGNAL_LINE_COLOR"),
    "decision chart": ("ENTRY_COLOR", "AVWAP_COLOR"),
}


def _tokens() -> dict[str, str]:
    css = TOKENS_CSS.read_text(encoding="utf-8")
    return {name: value.lower()
            for name, value in re.findall(r"^\s*--([\w-]+):\s*(#[0-9a-fA-F]{6});", css, flags=re.M)}


def _oklab(hex_colour: str) -> tuple[float, float, float]:
    def linear(channel: float) -> float:
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(int(hex_colour[i:i + 2], 16) / 255) for i in (1, 3, 5))
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def delta_e(a: str, b: str) -> float:
    """OKLab distance x100 -- the normal-vision dE the dataviz validator
    reports. Not CIE76: the old pink resistance line is 15.4 CIE76 from loss
    and only 5.9 here, and it read as a loss."""
    return 100 * math.dist(_oklab(a), _oklab(b))


def test_delta_e_matches_the_validator_on_a_known_pair():
    assert delta_e("#ec407a", "#ff5470") == pytest.approx(5.9, abs=0.1)
    assert delta_e("#c97a22", "#ff5470") == pytest.approx(15.6, abs=0.1)


def test_theme_names_only_d1_tokens_and_d2_series():
    assert set(cs.THEME) <= D1_TOKENS | D2_SERIES


def test_theme_matches_the_admin_tokens_byte_for_byte():
    tokens = _tokens()
    for name, value in cs.THEME.items():
        assert tokens[name] == value.lower(), name


@pytest.mark.parametrize("constant, token", sorted(COLOUR_CONSTANTS.items()))
def test_each_colour_constant_is_its_token(constant, token):
    assert getattr(cs, constant) == cs.THEME[token]


def test_every_colour_constant_is_accounted_for():
    """A new colour constant has to join COLOUR_CONSTANTS, which is what puts
    it through the token and gain/loss checks."""
    declared = {name for name in vars(cs)
                if name.endswith("_COLOR") or name in {"CHART_BG", "CHIP_BG", "CHIP_EDGE"}}
    assert declared == set(COLOUR_CONSTANTS)


@pytest.mark.parametrize("constant", sorted(set(COLOUR_CONSTANTS) - GAIN_LOSS))
def test_no_colour_reads_as_gain_or_loss(constant):
    colour = getattr(cs, constant)
    assert delta_e(colour, cs.UP_COLOR) >= 10, f"{constant} vs gain"
    assert delta_e(colour, cs.DOWN_COLOR) >= 10, f"{constant} vs loss"


@pytest.mark.parametrize("group", sorted(CO_OCCURRING))
def test_roles_drawn_together_are_distinct(group):
    for a, b in itertools.combinations(CO_OCCURRING[group], 2):
        assert delta_e(getattr(cs, a), getattr(cs, b)) >= 10, f"{group}: {a} vs {b}"


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
        direction="bullish", strategy="RSI", horizon_label="2w", out_dir=str(tmp_path),
    )
    assert out is not None
    assert_rendered(out)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/charts/test_chart_theme.py`

Expected: FAIL.
- `test_theme_names_only_d1_tokens_and_d2_series` fails on `bg-1`, `up` and others.
- `test_theme_matches_the_admin_tokens_byte_for_byte` raises `KeyError: 'bg-1'`.
- Every `test_each_colour_constant_is_its_token` case raises `KeyError`.
- `test_no_colour_reads_as_gain_or_loss[TRENDLINE_RESISTANCE_COLOR]` fails at 5.9.
- The two `delta_e` pins and the smoke test pass.

- [ ] **Step 3: Implement**

In `swingbot/core/charts/chart_style.py`, replace lines 25–93. The span runs
from the `# ---------------------------------------------------------------------------`
banner that opens `# Professional dark theme -- a TradingView/Bloomberg-terminal-style palette`,
through `VOLUME_PROFILE_COLOR = "#d4a94c"`. Replace it with:

```python
# ---------------------------------------------------------------------------
# The admin palette, on every Discord chart -- spec v80 D5, direction C
# ("TradingView Blue").
#
# THEME copies, byte for byte, the tokens it names from
# frontend/src/styles/tokens.css: D1's colours and D2's chart series. Every
# colour constant below is one of them. tests/charts/test_chart_theme.py reads
# that file, maps each constant to its token, and holds three rules:
#   1. roles drawn together are distinct (OKLab dE >= 10);
#   2. indicator panes may reuse a series;
#   3. nothing but the gain/loss constants sits within dE 10 of gain or loss.
# Change a colour in tokens.css and that test names the constant to follow.
# ---------------------------------------------------------------------------
THEME = {
    "surface": "#131722",
    "surface-raised": "#1c212d",
    "border": "#2a2e39",
    "border-strong": "#363a45",
    "text": "#d9dce4",
    "text-muted": "#9195a0",
    "text-faint": "#4e5361",
    "pos": "#17c98e",
    "neg": "#ff5470",
    "warn": "#ffb43d",
    "info": "#b39ddb",
    "chart-1": "#4c8dff",
    "chart-2": "#c97a22",
    "chart-3": "#a868e0",
    "chart-5": "#1a9db3",
}

CHART_BG = THEME["surface"]             # figure + every panel's background: TradingView's chart pane
GRID_COLOR = THEME["border"]            # gridlines -- subtle, never competes with data
SPINE_COLOR = THEME["border-strong"]    # axis borders
TEXT_COLOR = THEME["text"]              # primary text (titles, axis labels)
MUTED_TEXT_COLOR = THEME["text-muted"]  # tick labels, fine print: 5.97:1 on CHART_BG (#666666 was 3.6:1)
UP_COLOR = THEME["pos"]                 # bullish candle body/wick
DOWN_COLOR = THEME["neg"]               # bearish candle body/wick
CHIP_BG = THEME["surface-raised"]       # background for the small rounded "chip" labels every overlay uses
CHIP_EDGE = THEME["border-strong"]      # neutral chip border when no accent color applies

# One green and one red across the whole image, per the palette's first rule:
# green and red mean P&L direction and nothing else. A target IS the profit
# side and a stop IS the loss side, so they take the same two colours the
# candles do rather than near-miss shades of them -- the old #00c896 target
# against #26a69a candles was two greens that meant the same thing. Line
# weight, dashing and the labelled chip are what separate a level from a
# candle body, not a third hue.
ENTRY_COLOR = THEME["chart-1"]
STOP_COLOR = THEME["neg"]
TARGET_COLOR = THEME["pos"]
TARGET2_COLOR = THEME["chart-3"]
CURRENT_PRICE_COLOR = THEME["warn"]  # distinct from entry -- entry is a planned limit level, this is where price actually is

# Support and resistance take the stop-side and target-side strategy colours
# below. The two never share a chart: trade_chart.py draws plain trendlines
# only when no confirming source was passed and the strategy overlays
# otherwise, so the pairing costs no distinctness and keeps the side meaning
# (for a long, support is the stop side). Resistance was pink #ec407a, OKLab
# dE 5.9 from loss: a line that read as a loss on every chart.
TRENDLINE_SUPPORT_COLOR = THEME["chart-5"]
TRENDLINE_RESISTANCE_COLOR = THEME["chart-2"]
AVWAP_COLOR = THEME["info"]

# Fixed accent colors for the confirmed-strategy overlay -- one per
# SIDE of the scenario (whatever confirmed target 1, whatever confirmed
# the stop), not per method, so the chart reads as a consistent
# two-color system no matter which specific method (EMA, VWAP, Fib,
# FVG, trendline, ...) actually gets picked for a given trade.
TARGET_STRATEGY_COLOR = THEME["chart-2"]
STOP_STRATEGY_COLOR = THEME["chart-5"]

# Indicator-panel accent colors (MACD/Signal/RSI). Indicator panes may reuse
# series (D5 rule 2); the three also colour the stat chips above the price
# pane, where they sit >= 13.7 dE from each other, from TP2 and from amber.
MACD_LINE_COLOR = THEME["chart-1"]
SIGNAL_LINE_COLOR = THEME["chart-2"]
RSI_LINE_COLOR = THEME["chart-5"]

# Keltner bands are background context on the price pane, dashed at 55%
# alpha, so they take the neutral muted grey rather than a hue. Six series
# cannot give seven price-pane roles each a hue >= 10 dE from every other:
# chart-1/chart-6 sit 6.8 apart and chart-2/chart-4 6.2.
KC_COLOR = THEME["text-muted"]

# Volume Profile is drawn on EVERY chart, always -- both as the left-side
# overlay (see chart_volume_profile._draw_volume_profile_overlay) and,
# when Volume Profile actually confirmed this scenario's target/stop, as a
# highlighted level on the price panel itself. It takes info lavender:
# background market structure is a neutral fact, not a level, and lavender
# is unlike every strategy or level colour on the pane (>= 10.2 dE, the
# nearest being the grey Keltner bands).
VOLUME_PROFILE_COLOR = THEME["info"]
```

Replace:

```python
PATH_COLOR = "#555555"
```

with:

```python
PATH_COLOR = THEME["text-faint"]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run each, one file per call:

```bash
python scripts/dev/testrun.py file tests/charts/test_chart_theme.py
python scripts/dev/testrun.py file tests/charts/test_chart_layout.py
python scripts/dev/testrun.py file tests/charts/test_decision_chart.py
```

Expected: PASS all three.
- `test_chart_layout.py`'s volume-profile test finds bars by
  `VOLUME_PROFILE_COLOR`, whatever its value.
- `trade_chart.py:493,677` detect Keltner addplots by `KC_COLOR`, and no other
  panel-0 addplot uses the muted grey.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/charts/chart_style.py tests/charts/test_chart_theme.py
git commit -m "feat(v80): Discord charts adopt the admin palette -- THEME copies tokens.css"
```

---

### Task F22: Stray chart colour literals move into `chart_style.py`

**Files:**
- Modify: `swingbot/core/charts/chart_style.py` (`THEME` gains `bg`; four
  constants after `DISCLAIMER_TEXT`)
- Modify: `swingbot/core/charts/analytics_charts.py:20-23,177`
- Modify: `swingbot/core/charts/portfolio_charts.py:14-17,166`
- Modify: `swingbot/core/charts/trade_chart.py:84,929,1087`
- Modify: `swingbot/core/charts/chart_drawing.py:16,180`
- Test: `tests/charts/test_chart_theme.py`

**Interfaces:**
- Consumes: F21's `THEME` and `TEXT_COLOR`.
- Produces:
  - `THEME["bg"]`;
  - `DISCLAIMER_COLOR = THEME["warn"]`;
  - `HEATMAP_INK_DARK = THEME["bg"]` and `HEATMAP_INK_LIGHT = THEME["text"]`;
  - `FOLD_YEAR_COLORS = (THEME["chart-1"], THEME["chart-2"], THEME["chart-3"])`;
  - a test banning any hex or CSS4 colour-name string literal in
    `swingbot/core/charts/` outside `chart_style.py`.

- [ ] **Step 1: Write the failing tests**

In `tests/charts/test_chart_theme.py`, replace:

```python
import itertools
```

with:

```python
import ast
import itertools
```

In `COLOUR_CONSTANTS`, replace:

```python
    "PATH_COLOR": "text-faint",
}
```

with:

```python
    "PATH_COLOR": "text-faint",
    "DISCLAIMER_COLOR": "warn",
    "HEATMAP_INK_DARK": "bg",
    "HEATMAP_INK_LIGHT": "text",
}
```

Replace `test_every_colour_constant_is_accounted_for` with:

```python
def test_every_colour_constant_is_accounted_for():
    """A new colour constant has to join COLOUR_CONSTANTS, which is what puts
    it through the token and gain/loss checks."""
    declared = {name for name in vars(cs)
                if name.endswith("_COLOR") or name.startswith("HEATMAP_INK_")
                or name in {"CHART_BG", "CHIP_BG", "CHIP_EDGE"}}
    assert declared == set(COLOUR_CONSTANTS)


def test_fold_years_are_three_adjacent_series_clear_of_gain_and_loss():
    assert cs.FOLD_YEAR_COLORS == (cs.THEME["chart-1"], cs.THEME["chart-2"], cs.THEME["chart-3"])
    for colour in cs.FOLD_YEAR_COLORS:
        assert delta_e(colour, cs.UP_COLOR) >= 10
        assert delta_e(colour, cs.DOWN_COLOR) >= 10


_HEX = re.compile(r"^#[0-9a-fA-F]{3,8}$")


def _colour_literals(path: Path) -> list[str]:
    import matplotlib.colors as mcolors

    names = set(mcolors.CSS4_COLORS)
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.strip()
            if _HEX.match(value) or value.lower() in names:
                found.append(f"{path.name}:{node.lineno}: {value!r}")
    return found


def test_no_colour_literal_outside_chart_style():
    """Every chart colour goes through THEME, so a colour cannot escape the
    token and dE checks by being typed straight into a drawing module."""
    charts = Path(cs.__file__).parent
    offenders = [hit for path in sorted(charts.glob("*.py")) if path.name != "chart_style.py"
                 for hit in _colour_literals(path)]
    assert offenders == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/charts/test_chart_theme.py`

Expected: FAIL.
- The three new `test_each_colour_constant_is_its_token` cases raise `AttributeError`.
- The fold-year test raises `AttributeError`.
- `test_no_colour_literal_outside_chart_style` lists eight literals:
  - `analytics_charts.py:177` `'black'` and `'white'`;
  - `chart_drawing.py:180` `'white'`;
  - three hexes at `portfolio_charts.py:166`;
  - `trade_chart.py:929` `'white'` and `trade_chart.py:1087` `'#e2b25a'`.

- [ ] **Step 3: Implement**

In `swingbot/core/charts/chart_style.py`, replace:

```python
THEME = {
    "surface": "#131722",
```

with:

```python
THEME = {
    "bg": "#0c0f16",
    "surface": "#131722",
```

Replace:

```python
DISCLAIMER_TEXT = "Not financial advice — for informational purposes only. Trade at your own risk."
```

with:

```python
DISCLAIMER_TEXT = "Not financial advice — for informational purposes only. Trade at your own risk."
# The fine print's colour on a trade chart: caution amber, which is what the
# line is. Was a stray #e2b25a typed into trade_chart.py.
DISCLAIMER_COLOR = THEME["warn"]

# Ink for the strategy heatmap's cell labels (analytics_charts.py): dark on
# the pale middle of RdYlGn, light on its saturated ends. Were the named
# colours "black" and "white".
HEATMAP_INK_DARK = THEME["bg"]
HEATMAP_INK_LIGHT = THEME["text"]

# One bar colour per walk-forward fold year, 2021/2022/2023
# (portfolio_charts.py). Three ADJACENT series: adjacency is the pairing D2
# validated for distinctness.
FOLD_YEAR_COLORS = (THEME["chart-1"], THEME["chart-2"], THEME["chart-3"])
```

In `swingbot/core/charts/analytics_charts.py`, replace:

```python
from .chart_style import (
    CHART_BG, CHIP_BG, DISCLAIMER_TEXT, DOWN_COLOR, GRID_COLOR, MUTED_TEXT_COLOR,
    SPINE_COLOR, TARGET_COLOR, TEXT_COLOR, UP_COLOR,
)
```

with:

```python
from .chart_style import (
    CHART_BG, CHIP_BG, DISCLAIMER_TEXT, DOWN_COLOR, GRID_COLOR, HEATMAP_INK_DARK,
    HEATMAP_INK_LIGHT, MUTED_TEXT_COLOR, SPINE_COLOR, TARGET_COLOR, TEXT_COLOR, UP_COLOR,
)
```

and replace:

```python
               color="black" if abs(norm[i, 0]) < 0.6 else "white", fontweight="bold")
```

with:

```python
               color=HEATMAP_INK_DARK if abs(norm[i, 0]) < 0.6 else HEATMAP_INK_LIGHT, fontweight="bold")
```

In `swingbot/core/charts/portfolio_charts.py`, replace:

```python
from swingbot.core.charts.chart_style import (CHART_BG, DISCLAIMER_TEXT,
                                              DOWN_COLOR, GRID_COLOR,
                                              MUTED_TEXT_COLOR, TEXT_COLOR,
                                              UP_COLOR)
```

with:

```python
from swingbot.core.charts.chart_style import (CHART_BG, DISCLAIMER_TEXT,
                                              DOWN_COLOR, FOLD_YEAR_COLORS,
                                              GRID_COLOR, MUTED_TEXT_COLOR,
                                              TEXT_COLOR, UP_COLOR)
```

and replace:

```python
    year_colors = ("#4dd0e1", "#ba68c8", "#ffa726")   # 2021/2022/2023
```

with:

```python
    year_colors = FOLD_YEAR_COLORS   # 2021/2022/2023
```

In `swingbot/core/charts/trade_chart.py`, replace:

```python
    DEFAULT_TRENDLINE_LOOKBACK_DAYS, DISCLAIMER_TEXT, DOWN_COLOR, ENTRY_COLOR, KC_COLOR,
```

with:

```python
    DEFAULT_TRENDLINE_LOOKBACK_DAYS, DISCLAIMER_COLOR, DISCLAIMER_TEXT, DOWN_COLOR, ENTRY_COLOR, KC_COLOR,
```

Replace the one occurrence (line 929, the `v2` corner tag):

```python
                    color="white",
```

with:

```python
                    color=TEXT_COLOR,
```

and replace:

```python
            ha="center", va="bottom", fontsize=9, color="#e2b25a", fontweight="bold",
```

with:

```python
            ha="center", va="bottom", fontsize=9, color=DISCLAIMER_COLOR, fontweight="bold",
```

In `swingbot/core/charts/chart_drawing.py`, replace:

```python
from .chart_style import MIN_LABEL_GAP_FRAC, _label_bbox
```

with:

```python
from .chart_style import MIN_LABEL_GAP_FRAC, TEXT_COLOR, _label_bbox
```

and replace:

```python
        ax.scatter(xs, ys, color=color, s=55, marker="D", zorder=6, edgecolors="white", linewidths=0.8)
```

with:

```python
        ax.scatter(xs, ys, color=color, s=55, marker="D", zorder=6, edgecolors=TEXT_COLOR, linewidths=0.8)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/charts/test_chart_theme.py
python scripts/dev/testrun.py file tests/charts/test_analytics_charts.py
python scripts/dev/testrun.py file tests/charts/test_portfolio_charts.py
python scripts/dev/testrun.py file tests/charts/test_trade_chart_v2.py
```

Expected: PASS all four.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/charts/chart_style.py swingbot/core/charts/analytics_charts.py swingbot/core/charts/portfolio_charts.py swingbot/core/charts/trade_chart.py swingbot/core/charts/chart_drawing.py tests/charts/test_chart_theme.py
git commit -m "feat(v80): move the last chart colour literals into chart_style, and ban new ones"
```

---

### Task F23: Delete the old admin palette mirror

**Files:**
- Delete: `swingbot/admin/static/tokens.css`
- Modify: `scripts/dev/testrun.py:50-60` (`ESCALATE_PREFIXES` and its comment)
- Modify: `docs/features/features-admin.md:119-126` (the "Admin UI" paragraph)
- Create: `tests/scripts/test_testrun_escalation.py`
- Test: `tests/charts/test_chart_theme.py` (one test appended)

**Interfaces:**
- Consumes: F21, after which nothing reads `swingbot/admin/static/tokens.css`
  (`git grep` finds only `testrun.py`'s comment and `features-admin.md`).
- Produces: `ESCALATE_PREFIXES = ("swingbot/core/charts/", "frontend/src/styles/tokens.css")`.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_testrun_escalation.py`:

```python
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "dev"))


def test_a_token_edit_escalates_fast_to_full(monkeypatch):
    """tests/charts/test_chart_theme.py reads frontend/src/styles/tokens.css
    and runs only in the slow tier, so a token edit must not let `fast` skip it."""
    import testrun

    monkeypatch.setattr(testrun, "changed_paths", lambda: ["frontend/src/styles/tokens.css"])
    escalate, reason = testrun.should_escalate()
    assert escalate
    assert "frontend/src/styles/tokens.css" in reason


def test_the_deleted_admin_palette_is_no_longer_a_trigger():
    import testrun

    assert not any(prefix.startswith("swingbot/admin/static") for prefix in testrun.ESCALATE_PREFIXES)


def test_an_unrelated_frontend_edit_does_not_escalate(monkeypatch):
    import testrun

    monkeypatch.setattr(testrun, "changed_paths", lambda: ["frontend/src/app/ui/chip.ts"])
    assert testrun.should_escalate() == (False, "")
```

Append to `tests/charts/test_chart_theme.py`:

```python
def test_the_old_admin_palette_mirror_is_gone():
    """swingbot/admin/static/tokens.css outlived the Jinja pages it styled and
    survived only as the other side of this file's old sync test."""
    assert not (REPO / "swingbot" / "admin" / "static" / "tokens.css").exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python scripts/dev/testrun.py file tests/scripts/test_testrun_escalation.py
python scripts/dev/testrun.py file tests/charts/test_chart_theme.py
```

Expected: FAIL.
- `test_a_token_edit_escalates_fast_to_full` and
  `test_the_deleted_admin_palette_is_no_longer_a_trigger` fail; the unrelated
  edit test passes.
- In the second file, `test_the_old_admin_palette_mirror_is_gone` fails.

- [ ] **Step 3: Implement**

```bash
git rm swingbot/admin/static/tokens.css
```

In `scripts/dev/testrun.py`, replace:

```python
# `swingbot/admin/templates/` was here until Release B deleted it. `static/`
# stays: it is no longer page CSS, but `static/tokens.css` is still the source
# `core/charts/chart_style.THEME` mirrors, and tests/test_chart_theme.py pins
# the two together -- so editing it can still break a render-tier test.
ESCALATE_PREFIXES = (
    "swingbot/core/charts/",
    "swingbot/admin/static/",
)
```

with:

```python
# `swingbot/admin/templates/` was here until Release B deleted it, and
# `swingbot/admin/static/` until v80 deleted `static/tokens.css`. The palette
# `core/charts/chart_style.THEME` copies is now the SPA's own
# `frontend/src/styles/tokens.css`, and tests/charts/test_chart_theme.py (slow
# tier) reads it -- so a token edit can still break a render-tier test.
ESCALATE_PREFIXES = (
    "swingbot/core/charts/",
    "frontend/src/styles/tokens.css",
)
```

In `docs/features/features-admin.md`, replace:

```markdown
The admin UI's look is driven by one design-token layer, not scattered
per-page CSS: `static/tokens.css` is the single palette/spacing source of
truth, `swingbot/admin/chart_style.THEME` mirrors those same colors for
server-rendered PNG charts, and a test keeps the two in sync so they can
never quietly drift apart. **`tokens.css` survived the Jinja deletion for
exactly that reason** — it stopped being read by templates and became the
source the Angular build imports, and deleting it would have left the *bot's*
Discord chart colours with no single source.
```

with:

```markdown
The admin UI's look is driven by one design-token layer, not scattered
per-page CSS: `frontend/src/styles/tokens.css` is the single palette, type
and spacing source (direction C, "TradingView Blue", spec v80). The bot's
Discord chart PNGs share that palette: `swingbot/core/charts/chart_style.THEME`
copies the tokens it names, and `tests/charts/test_chart_theme.py` compares
the two byte for byte, so an admin colour change names the chart constant
that must follow it. The same test keeps every chart overlay clear of the
gain and loss colours. The old `swingbot/admin/static/tokens.css` mirror was
deleted in v80, having outlived the Jinja pages it styled.
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/scripts/test_testrun_escalation.py
python scripts/dev/testrun.py file tests/scripts/test_testrun_lint_gate.py
python scripts/dev/testrun.py file tests/charts/test_chart_theme.py
```

Expected: PASS all three. Then confirm nothing still names the file outside
plans and specs:

```bash
git grep -n "admin/static/tokens" -- ':!docs/superpowers'
```

Expected: only the history sentences in `testrun.py`'s comment,
`features-admin.md` and `test_chart_theme.py`, all of which say it was deleted.

- [ ] **Step 5: Commit**

```bash
git add scripts/dev/testrun.py docs/features/features-admin.md tests/scripts/test_testrun_escalation.py tests/charts/test_chart_theme.py
git commit -m "chore(v80): delete the admin/static palette mirror; escalate fast on a token edit"
```

---

### Task F24: Embed accents follow `--text-secondary`

**Files:**
- Modify: `swingbot/core/presentation/tokens.py:10,16`
- Test: `tests/presentation/test_tokens.py:10,24,28,29,33`

**Interfaces:**
- Consumes: D1's `--text-secondary` value `#9ea2ad` (spec; F2 lands it in `tokens.css`).
- Produces: `ACCENT_RAMP[3] == ACCENT_BLOCKED == 0x9EA2AD`. The scratch
  outcome and the unknown-outcome fallback follow, since both read
  `ACCENT_RAMP[3]`. The other four ramp values are unchanged.

- [ ] **Step 1: Write the failing tests**

In `tests/presentation/test_tokens.py`, replace every `0x9BA3BD` with `0x9EA2AD`.
There are five: in `test_accent_ramp_is_monotonic_worse_to_better`,
`test_outcome_accents_are_the_same_three_colours_as_the_ramp_ends` (one),
`test_unknown_outcome_is_grey_not_a_crash` (two) and
`test_blocked_accent_is_the_neutral_grey`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/presentation/test_tokens.py`

Expected: FAIL. Four tests fail with `0x9BA3BD != 0x9EA2AD`.

- [ ] **Step 3: Implement**

In `swingbot/core/presentation/tokens.py`, replace:

```python
    3: 0x9BA3BD,
```

with:

```python
    3: 0x9EA2AD,
```

and replace:

```python
ACCENT_BLOCKED: int = 0x9BA3BD
```

with:

```python
# Level 3 and blocked are the admin's --text-secondary (v80 D1), so a neutral
# embed and a neutral admin label are the same grey.
ACCENT_BLOCKED: int = 0x9EA2AD
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/presentation/test_tokens.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/presentation/tokens.py tests/presentation/test_tokens.py
git commit -m "feat(v80): embed neutral accent follows the new --text-secondary"
```

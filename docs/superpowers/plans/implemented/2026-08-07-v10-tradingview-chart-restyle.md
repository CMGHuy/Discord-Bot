# TradingView Chart Restyle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the generated static trade-plan PNG read like the admin UI's interactive lightweight-charts chart, without dropping any indicator or annotation.

**Architecture:** Volume and Volume Profile move inside the price pane; the centered title and boxed matplotlib legend collapse into one top-left legend block; level labels split into a line-end name plus a price-only right-axis tag; the ~45% of the price pane currently reserved as empty label space is reclaimed. New annotation code lands in a new sibling module rather than growing the already-62 KB `trade_chart.py`.

**Tech Stack:** Python 3.11, matplotlib (Agg), mplfinance 0.12.10b0, pandas, pytest, PIL (test-side only).

**Spec:** `docs/superpowers/specs/implemented/2026-08-07-v10-tradingview-chart-restyle-design.md`

**Version:** ui 1.0.7 · bot 1.1.1 — VERSION.json as of this plan's authoring commit (`6480bef`), not today's. A version stamp records the release a document was written against, so it is never updated after the fact.

## Global Constraints

- **The palette does not change.** `chart_style.py`'s colour constants, the `THEME` dict, and `swingbot/admin/static/tokens.css` must stay byte-identical. `tests/test_chart_theme.py::test_theme_dict_matches_module_constants` and `::test_theme_matches_tokens_css` must stay green untouched.
- **mplfinance is pinned at 0.12.10b0** (`requirements.txt`). `volume_panel` and `tight_layout` are supported; `scale_padding` is not. Do not add a kwarg without checking `inspect.getsource(mpf.plot)` first.
- **No change to scoring, level detection, confluence, sizing, or any trading logic.** This plan touches rendering only.
- **New chart test files must carry `pytestmark = pytest.mark.slow`**, matching every existing chart test file — the nine render-heavy files are excluded from `scripts/testrun.py fast` on purpose (`docs/claude/testing-cost.md`).
- **Verify with `python scripts/testrun.py file <path>`** while iterating and `python scripts/testrun.py full` before each commit. Green means `0 failed`. `tests/test_trade_monitor_wiring.py::test_flag_on_polls_open_plans` is quarantined `xfail(strict=False)`; `xfailed` or `xpassed` are both fine and must not be "fixed".
- **Never edit files under `.claude/worktrees/`** from the main tree.

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `tests/test_chart_layout.py` | **Create.** Structural layout assertions (pane count, dead space, left ladder, candle-fill ratio). The only tests that can see layout at all. | 1 |
| `swingbot/core/charts/trade_chart.py` | **Modify.** Panel wiring, figure margins, x-limit, legend removal, call sites for the new annotation module. | 2,3,5,6,7 |
| `swingbot/core/charts/chart_volume_profile.py` | **Modify.** Draw target changes from its own `fig.add_axes` panel to a blended-transform overlay on the price axes. Binning maths untouched. | 3 |
| `swingbot/core/charts/chart_annotations.py` | **Create.** The top-left legend block and the level name/tag pair. Keeps three new annotation systems out of the 62 KB module. | 4,6 |
| `swingbot/core/charts/chart_style.py` | **Modify.** New sizing constants; retire the VP panel geometry constants; grid style. | 3,7 |

---

### Task 1: Measure the layout and pin it with failing tests

The spec deliberately does **not** claim to know why ~20% of the image is empty. Measure first. This task ships the test file every later task is judged by; three of its four tests must fail at the end of this task, and that is the expected outcome.

**Files:**
- Create: `tests/test_chart_layout.py`

**Interfaces:**
- Consumes: `swingbot.core.charts.trade_chart.generate_trade_chart(ticker, df, entry, stop_loss, take_profit, direction, strategy, horizon_label, out_dir, ...) -> str | None` (returns the saved PNG path)
- Produces: `_render(tmp_path, monkeypatch, **kw) -> tuple[str, matplotlib.figure.Figure]` and the pytest fixture `chart` — later tasks reuse both.

- [ ] **Step 1: Write the layout test file**

`generate_trade_chart` closes its figure in a `finally`, so the figure must be captured at `savefig` time. Bounding boxes stay readable after close.

```python
# tests/test_chart_layout.py
"""Structural layout assertions for the generated trade chart.

tests/conftest.py's assert_rendered counts distinct colours -- it answers
"did we draw something" and is blind to WHERE things landed, so every
change in the TradingView restyle would pass it unchanged. These tests
are the ones that can actually see layout.
"""
import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.slow


def _df(periods=120, seed=7):
    idx = pd.bdate_range("2025-01-01", periods=periods)
    close = pd.Series(100 + np.cumsum(np.random.default_rng(seed).normal(0, 1, periods)), index=idx)
    return pd.DataFrame({"Open": close.shift(1).fillna(close), "High": close + 1,
                         "Low": close - 1, "Close": close, "Volume": 1_000_000}, index=idx)


def _render(tmp_path, monkeypatch, **kw):
    """Render a chart and hand back (png_path, figure). The figure is closed
    by generate_trade_chart's finally block, but its axes bboxes remain
    readable, which is all these assertions need."""
    import matplotlib.figure
    from swingbot.core.charts.trade_chart import generate_trade_chart

    captured = []
    real_savefig = matplotlib.figure.Figure.savefig

    def _spy(self, *a, **k):
        captured.append(self)
        return real_savefig(self, *a, **k)

    monkeypatch.setattr(matplotlib.figure.Figure, "savefig", _spy)

    df = kw.pop("df", None)
    if df is None:
        df = _df()
    last = float(df["Close"].iloc[-1])
    path = generate_trade_chart(
        ticker="TEST", df=df, entry=last, stop_loss=last * 0.95,
        take_profit=last * 1.08, direction="bullish", strategy="RSI",
        horizon_label="2w", out_dir=str(tmp_path), **kw)
    assert path is not None, "generate_trade_chart returned None"
    assert captured, "savefig was never called"
    return path, captured[0]


@pytest.fixture
def chart(tmp_path, monkeypatch):
    return _render(tmp_path, monkeypatch)


def test_bottom_pane_reaches_the_bottom_of_the_figure(chart):
    """No dead band under the lowest pane. Uses the figure's own axes rather
    than pixel-sniffing the PNG so it is DPI-independent."""
    _, fig = chart
    lowest = min(ax.get_position().y0 for ax in fig.axes)
    assert lowest <= 0.12, (
        f"lowest pane starts at y0={lowest:.3f}; expected <= 0.12 "
        f"(anything higher is dead space at the bottom of the image)")


def test_candles_fill_most_of_the_price_pane(chart):
    """trade_chart.py:887 widens xlim past the last candle to make room for
    the strategy-label column, which currently leaves roughly 45% of the
    price pane empty. Candles should own the pane."""
    _, fig = chart
    ax = fig.axes[0]
    x0, x1 = ax.get_xlim()
    n_bars = 120
    used = n_bars / (x1 - x0)
    assert used >= 0.80, (
        f"candles occupy only {used:.0%} of the price pane x-range "
        f"(xlim spans {x1 - x0:.1f} for {n_bars} bars)")


def test_no_price_ladder_on_the_left(chart):
    """The Volume Profile panel owns a second, duplicate price axis today.
    After the overlay move there must be exactly one ladder, on the right."""
    _, fig = chart
    left_labelled = [ax for ax in fig.axes
                     if ax.get_yticklabels() and any(t.get_text().strip() for t in ax.get_yticklabels())
                     and ax.yaxis.get_ticks_position() in ("left", "default")]
    assert not left_labelled, (
        f"{len(left_labelled)} axes still print y tick labels on the left")


def test_renders_at_all(chart):
    """Guards the three assertions above against passing on a blank canvas."""
    from tests.conftest import assert_rendered
    path, _ = chart
    assert_rendered(path)
```

- [ ] **Step 2: Run and record which fail**

Run: `python scripts/testrun.py file tests/test_chart_layout.py`

Expected: `test_renders_at_all` PASSES. The other three FAIL. Paste the three failure messages into the task's completion note — the measured `y0`, the measured candle-fill percentage, and the left-ladder axes count are the baseline every later task is judged against, and the `y0` number is the answer to the question the spec left open.

- [ ] **Step 3: Commit**

```bash
git add tests/test_chart_layout.py
git commit -m "test(charts): add failing structural layout assertions

assert_rendered counts colours and is blind to layout, so the restyle
needs tests that can see it. Three of these four fail today by design:
they measure the dead band under the lowest pane, the share of the price
pane the candles actually occupy, and the duplicate left price ladder."
```

---

### Task 2: Move volume into the price pane

**Files:**
- Modify: `swingbot/core/charts/trade_chart.py:394-421` (panel ratios, figure size, plot kwargs)
- Modify: `swingbot/core/charts/trade_chart.py:396-397` (MACD/RSI panel indices)
- Test: `tests/test_chart_layout.py`

**Interfaces:**
- Consumes: `_render` / `chart` from Task 1.
- Produces: panel indices MACD=1, RSI=2 — Task 3 and Task 7 both index panels and must use these.

- [ ] **Step 1: Write the failing test**

```python
def test_volume_shares_the_price_pane(chart):
    """chart-init.js:36-40 draws volume as an overlay in the price pane with
    scaleMargins {top: 0.82}, not as its own pane. Matching that frees a
    whole pane of vertical space."""
    _, fig = chart
    price_pos = fig.axes[0].get_position()
    twins = [ax for ax in fig.axes
             if ax is not fig.axes[0]
             and abs(ax.get_position().y0 - price_pos.y0) < 1e-6
             and abs(ax.get_position().height - price_pos.height) < 1e-6]
    assert twins, "no axes shares the price pane's box; volume is still a separate pane"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python scripts/testrun.py file tests/test_chart_layout.py`
Expected: `test_volume_shares_the_price_pane` FAILS with "volume is still a separate pane".

- [ ] **Step 3: Renumber the indicator panels**

`addplot` entries are built earlier at `trade_chart.py:317-331` with `panel=2` (MACD) and `panel=3` (RSI). With volume no longer occupying panel 1, both shift down one. Change every `panel=2` to `panel=1` and `panel=3` to `panel=2` in that block, then update the two detection lines:

```python
has_macd = any(ap.get("panel") == 1 for ap in addplots)
has_rsi  = any(ap.get("panel") == 2 for ap in addplots)
```

- [ ] **Step 4: Rewire the panel ratios and figure height**

Replace `trade_chart.py:394-406` with a height derived from the ratios in use rather than three hardcoded constants:

```python
# Volume now overlays the price panel (volume_panel=0), so panel 0 carries
# both and the indicator panels shift down one. Figure height is derived
# from the ratios actually in use -- the old fixed 11.0/9.5/7.0 constants
# were tuned for the 4-panel layout and did not follow when a pane was absent.
has_macd = any(ap.get("panel") == 1 for ap in addplots)
has_rsi  = any(ap.get("panel") == 2 for ap in addplots)
if has_macd and has_rsi:
    panel_ratios = (6, 1.5, 1.2)
elif has_macd or has_rsi:
    panel_ratios = (6, 1.5)
else:
    panel_ratios = (6,)
fig_height = 1.05 * sum(panel_ratios) + 1.4
```

- [ ] **Step 5: Overlay the volume**

In `_plot_kwargs` (`trade_chart.py:408-422`) add `volume_panel=0` next to `volume=True`, and push the bars into the bottom band after `mpf.plot` returns. Mirrors `chart-init.js:38`.

```python
    volume=True,
    volume_panel=0,
```

Then immediately after `fig, axes = mpf.plot(recent, **_plot_kwargs)`:

```python
    # Volume rides the bottom ~18% of the price panel on its own y-axis, the
    # matplotlib equivalent of chart-init.js:38's
    # scaleMargins {top: 0.82, bottom: 0} -- it scales independently of price,
    # so a low stop line can never squash the bars or vice versa.
    _vol_ax = axes[1] if len(axes) > 1 else None
    if _vol_ax is not None:
        _vmax = float(recent["Volume"].max() or 1.0)
        _vol_ax.set_ylim(0, _vmax / 0.18)
        _vol_ax.set_yticks([])
        _vol_ax.set_ylabel("")
```

- [ ] **Step 6: Run the layout and chart suites**

Run: `python scripts/testrun.py file tests/test_chart_layout.py`
Expected: `test_volume_shares_the_price_pane` PASSES. `test_bottom_pane_reaches_the_bottom_of_the_figure` may now pass as a side effect — record whether it does, since that answers the spec's open question.

Run: `python scripts/testrun.py file tests/test_chart_theme.py`
Expected: PASS, untouched.

- [ ] **Step 7: Look at the output**

Render one chart and open the PNG. Volume bars must sit in the bottom fifth of the price pane, translucent, not overlapping the candle bodies above them. If they dominate, lower the `0.18` divisor.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/charts/trade_chart.py tests/test_chart_layout.py
git commit -m "feat(charts): overlay volume in the price pane

Matches chart-init.js:38's scaleMargins {top: 0.82}: volume gets its own
hidden y-axis inside panel 0 rather than a pane of its own, so it scales
independently of price. MACD/RSI shift to panels 1/2 and figure height is
derived from the panel ratios in use instead of three fixed constants."
```

---

### Task 3: Overlay the Volume Profile, killing the duplicate ladder

**Files:**
- Modify: `swingbot/core/charts/chart_volume_profile.py:21-136`
- Modify: `swingbot/core/charts/trade_chart.py:538-544` (`subplots_adjust` left margin)
- Modify: `swingbot/core/charts/chart_style.py:157-161` (retire two constants)
- Test: `tests/test_chart_layout.py`

**Interfaces:**
- Consumes: panel indices from Task 2.
- Produces: `_draw_volume_profile_overlay(ax, df, lookback, entry_price=None, price_range=None) -> None` — note the signature **drops the leading `fig` argument**, since it no longer creates an Axes. Task 7 does not call it; `trade_chart.py` is the only caller.

- [ ] **Step 1: Write the failing test**

```python
def test_volume_profile_draws_inside_the_price_pane(chart):
    """TradingView's Volume Profile Visible Range overlays the price pane and
    grows leftward from the right edge; it does not own a second axis with a
    second price ladder."""
    _, fig = chart
    ax = fig.axes[0]
    from swingbot.core.charts.chart_style import VOLUME_PROFILE_COLOR
    bars = [p for p in ax.patches
            if getattr(p, "get_facecolor", None)
            and VOLUME_PROFILE_COLOR.lower() in str(p.get_facecolor()).lower()]
    assert bars or any(
        VOLUME_PROFILE_COLOR.lower() in str(c.get_facecolor()).lower()
        for c in ax.containers for c in getattr(c, "patches", [])
    ), "no volume-profile bars found on the price axes"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python scripts/testrun.py file tests/test_chart_layout.py::test_volume_profile_draws_inside_the_price_pane`
Expected: FAIL with "no volume-profile bars found on the price axes".

- [ ] **Step 3: Convert the panel into an overlay**

Rename `_draw_volume_profile_panel` to `_draw_volume_profile_overlay` and drop the `fig` parameter. Keep everything from the docstring's `panel_lookback` computation through `profile is None` (`chart_volume_profile.py:63-77`) **exactly as it is** — that is the binning maths and it is not changing. Replace the geometry block at lines 79-88:

```python
    # Bars are drawn straight onto the price axes with a blended transform:
    # width in AXES coordinates (so a full-width bar spans a fixed fraction of
    # the pane regardless of the price scale), position in DATA coordinates
    # (so each bucket lines up with its real price). This is what lets the
    # profile share the price panel's ladder instead of owning a second one.
    import matplotlib.transforms as mtransforms
    blended = mtransforms.blended_transform_factory(ax.transAxes, ax.transData)
    vp_ax = ax          # every barh below now targets the price axes
    max_frac = 0.16     # widest bucket spans 16% of the pane
```

Replace the `barh` call at lines 129-130 so bars grow **leftward from the right edge** — x starts at `1.0` and extends by a negative width in axes coordinates:

```python
        frac = (draw_volume / max_vol) * max_frac if max_vol > 0 else 0.0
        vp_ax.barh(center, -frac, left=1.0, height=bin_size * 0.92,
                   color=VOLUME_PROFILE_COLOR, alpha=alpha * 0.75,
                   edgecolor=edgecolor, linewidth=linewidth,
                   transform=blended, zorder=3 if is_entry else 2,
                   clip_on=True)
```

Delete `vp_ax.invert_xaxis()` and `vp_ax.set_ylim(...)` (lines 135-136) — with a blended transform there is no separate axis to flip or sync. Delete the per-bucket price tick labels that follow line 138: those **are** the duplicate ladder.

- [ ] **Step 4: Drop the reserved left margin**

`trade_chart.py:538-544` reserves figure width for the old panel. Remove the `left=` argument entirely so the price pane reclaims it:

```python
            fig.subplots_adjust(hspace=0.55, top=0.91, bottom=0.05, right=0.90)
```

Update the call site to the new name and signature (drop the `fig` argument), and remove the now-unused `VOLUME_PROFILE_PANEL_WIDTH_FRAC` / `VOLUME_PROFILE_PANEL_GAP_FRAC` imports in both files plus their definitions at `chart_style.py:157-161`.

- [ ] **Step 5: Run the tests**

Run: `python scripts/testrun.py file tests/test_chart_layout.py`
Expected: `test_volume_profile_draws_inside_the_price_pane` and `test_no_price_ladder_on_the_left` both PASS.

- [ ] **Step 6: Look at the output**

The profile must read as faded background structure over the newest candles, with the POC still the standout. If it obscures the right-edge candles, the spec's stated fallback is anchoring left (`left=0.0`, positive `frac`) rather than redesigning.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/charts/chart_volume_profile.py swingbot/core/charts/trade_chart.py swingbot/core/charts/chart_style.py tests/test_chart_layout.py
git commit -m "feat(charts): overlay the volume profile in the price pane

Replaces the detached left panel and its duplicate price ladder with a
blended-transform overlay growing leftward from the right edge, matching
TradingView's Volume Profile Visible Range. Binning maths is untouched --
only the draw target and geometry change. Reclaims the 15% of figure
width the old panel reserved."
```

---

### Task 4: The top-left legend block

**Files:**
- Create: `swingbot/core/charts/chart_annotations.py`
- Modify: `swingbot/core/charts/trade_chart.py:408-434` (drop `title=`, drop the boxed legend)
- Test: `tests/test_chart_annotations.py`

**Interfaces:**
- Produces: `draw_legend_block(ax, *, ticker, horizon_label, direction_label, ohlc, overlays) -> None` where `ohlc` is `dict` with float keys `open/high/low/close/volume` and `overlays` is `list[str]`. Task 5 appends the strategy names to `overlays`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_chart_annotations.py
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest

pytestmark = pytest.mark.slow


def _texts(ax):
    return [t.get_text() for t in ax.texts]


def test_legend_block_renders_three_lines():
    from swingbot.core.charts.chart_annotations import draw_legend_block
    fig, ax = plt.subplots()
    try:
        draw_legend_block(
            ax, ticker="KLAC", horizon_label="2-month swing",
            direction_label="SHORT",
            ohlc={"open": 235.55, "high": 240.12, "low": 231.08,
                  "close": 235.55, "volume": 21_400_000},
            overlays=["EMA35", "Fib 38.2%"])
        joined = "\n".join(_texts(ax))
        assert "KLAC" in joined and "2-month swing" in joined and "SHORT" in joined
        assert "235.55" in joined and "240.12" in joined and "231.08" in joined
        assert "21.4M" in joined
        assert "EMA35" in joined and "Fib 38.2%" in joined
    finally:
        plt.close(fig)


def test_legend_block_omits_the_overlay_line_when_there_are_none():
    from swingbot.core.charts.chart_annotations import draw_legend_block
    fig, ax = plt.subplots()
    try:
        draw_legend_block(ax, ticker="X", horizon_label="2w", direction_label="LONG",
                          ohlc={"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5,
                                "volume": 1000},
                          overlays=[])
        assert len(ax.texts) == 2, "empty overlay list must not draw a third line"
    finally:
        plt.close(fig)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python scripts/testrun.py file tests/test_chart_annotations.py`
Expected: FAIL with `ModuleNotFoundError: swingbot.core.charts.chart_annotations`.

- [ ] **Step 3: Write the module**

```python
"""
The chart's top-left legend block and its level name/price annotations --
the two systems that replace mplfinance's centered title, its auto-generated
boxed legend, and the old combined "{name} {price}" pills.

Split out of trade_chart.py (already 62 KB) rather than added to it: these
are self-contained text-drawing helpers with no dependency on that module's
figure-assembly state, and they are the parts most likely to be tuned.
"""
from .chart_style import CHART_BG, MUTED_TEXT_COLOR, TEXT_COLOR

LEGEND_X = 0.008
LEGEND_TOP = 0.985
LEGEND_LINE_STEP = 0.042


def _fmt_volume(v) -> str:
    """21_400_000 -> '21.4M'. Discord renders these small; a raw integer is
    unreadable at that size and adds nothing over a rounded magnitude."""
    v = float(v or 0)
    for cutoff, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(v) >= cutoff:
            return f"{v / cutoff:.1f}{suffix}"
    return f"{v:.0f}"


def draw_legend_block(ax, *, ticker, horizon_label, direction_label, ohlc, overlays) -> None:
    """TradingView's top-left legend, in up to three lines:

        KLAC  2-month swing  SHORT
        O 235.55  H 240.12  L 231.08  C 235.55   Vol 21.4M
        EMA35   Fib 38.2%   KC (EMA20 +/-1.5xATR)

    Line 3 is what makes removing mplfinance's boxed legend safe: it names
    every overlay actually drawn. It is omitted entirely when nothing is
    overlaid, rather than rendering an empty row.
    """
    lines = [
        (f"{ticker}   {horizon_label}   {direction_label}", TEXT_COLOR, 11.0, "bold"),
        (f"O {ohlc['open']:,.2f}   H {ohlc['high']:,.2f}   "
         f"L {ohlc['low']:,.2f}   C {ohlc['close']:,.2f}   "
         f"Vol {_fmt_volume(ohlc.get('volume'))}", MUTED_TEXT_COLOR, 8.5, "normal"),
    ]
    if overlays:
        lines.append(("   ".join(overlays), MUTED_TEXT_COLOR, 8.0, "normal"))

    for i, (text, color, size, weight) in enumerate(lines):
        ax.text(LEGEND_X, LEGEND_TOP - i * LEGEND_LINE_STEP, text,
                transform=ax.transAxes, ha="left", va="top",
                fontsize=size, fontweight=weight, color=color, zorder=7,
                bbox=dict(boxstyle="square,pad=0.25", fc=CHART_BG, ec="none", alpha=0.72))
```

- [ ] **Step 4: Run the test**

Run: `python scripts/testrun.py file tests/test_chart_annotations.py`
Expected: PASS.

- [ ] **Step 5: Wire it into the chart**

In `trade_chart.py`, delete the `title=dict(...)` entry from `_plot_kwargs` (line 411) and delete the whole overlay-legend block that builds `_legend_handles` (lines 449 onward, through its `ax.legend(...)` call). The existing legend-removal at lines 433-434 and the watermark at 438-442 both stay. Then call the new helper right after the watermark:

```python
        from .chart_annotations import draw_legend_block
        _last = recent.iloc[-1]
        draw_legend_block(
            ax, ticker=ticker, horizon_label=horizon_label,
            direction_label=direction_label,
            ohlc={"open": float(_last["Open"]), "high": float(_last["High"]),
                  "low": float(_last["Low"]), "close": float(_last["Close"]),
                  "volume": float(_last["Volume"])},
            overlays=_overlay_names)
```

Build `_overlay_names` immediately before that call from the same conditions the deleted legend used, so nothing silently stops being named:

```python
        _overlay_names = []
        if any(ap.get("panel") == 0 and ap.get("color") == KC_COLOR for ap in addplots):
            _overlay_names.append("KC (EMA20 ±1.5×ATR)")
```

- [ ] **Step 6: Run the full suite**

Run: `python scripts/testrun.py full`
Expected: `0 failed`.

- [ ] **Step 7: Look at the output**

Three legend lines, top-left, no centered title, no boxed legend. Confirm the block does not cover candles at the top-left; if it does, the candles are fine to sit under it — the chip background is translucent — but the text must stay legible.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/charts/chart_annotations.py swingbot/core/charts/trade_chart.py tests/test_chart_annotations.py
git commit -m "feat(charts): replace title and boxed legend with a TradingView legend block

One top-left block of up to three lines -- symbol/setup/direction, live
OHLC + volume, and the overlay names. Line 3 is what makes deleting
mplfinance's boxed legend safe: it names every overlay actually drawn."
```

---

### Task 5: Reclaim the price pane

The single biggest visual defect: `trade_chart.py:887` widens the x-axis ~16 bars past the last candle to make room for the strategy-label column, leaving roughly 45% of the pane empty. Task 4's legend line 3 gives those labels a home, so the widening can go.

**Files:**
- Modify: `swingbot/core/charts/trade_chart.py:705-708, 887`
- Modify: `swingbot/core/charts/trade_chart.py` (`_overlay_names` from Task 4)
- Test: `tests/test_chart_layout.py`

**Interfaces:**
- Consumes: `draw_legend_block(..., overlays=...)` from Task 4.

- [ ] **Step 1: Confirm the test from Task 1 still fails**

Run: `python scripts/testrun.py file tests/test_chart_layout.py::test_candles_fill_most_of_the_price_pane`
Expected: still FAILS. Record the measured percentage.

- [ ] **Step 2: Move the strategy names into the legend**

Extend the `_overlay_names` list built in Task 4 with the same two names the deleted legend rendered, using the identical conditions from the old block:

```python
        if target_primary and not target_primary.startswith("Trendline"):
            _overlay_names.append(f"Target: {target_primary}")
        if stop_primary and not stop_primary.startswith("Trendline"):
            _overlay_names.append(f"Stop: {stop_primary}")
```

- [ ] **Step 3: Delete the x-limit widening**

Remove `trade_chart.py:887` entirely, along with the `strategy_label_x` / `extra_width` definitions at lines 707-708 **if nothing else references them** — grep first:

```bash
git grep -n "strategy_label_x\|extra_width" -- swingbot/
```

If other call sites remain (the inline strategy-label text drawn on the price pane uses `strategy_label_x`), keep the definitions and delete only the `set_xlim` call, then re-anchor those labels to `x_right` so they sit just inside the pane instead of driving its width.

- [ ] **Step 4: Run the tests**

Run: `python scripts/testrun.py file tests/test_chart_layout.py`
Expected: `test_candles_fill_most_of_the_price_pane` PASSES.

- [ ] **Step 5: Look at the output**

Candles must now span the pane. Confirm the right-edge level tags are not clipped — `annotation_clip=False` is already set on them (`trade_chart.py:161, 180`), and `bbox_inches="tight"` at save will include them.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/charts/trade_chart.py tests/test_chart_layout.py
git commit -m "fix(charts): stop reserving 45% of the price pane for labels

The x-axis was widened ~16 bars past the last candle to make room for the
strategy-label column, squeezing candles into the left half of the frame.
Those names now live on legend line 3, so the widening goes and the
candles get the pane back."
```

---

### Task 6: Split the level pills into line-end name plus price tag

`_draw_level_pill` already anchors to the axis gutter (`xycoords=("axes fraction","data")` at x=1.0) — it is not being replaced, only split, so the name reads off the line and the tag carries the price alone, matching `chart-init.js:8-12`.

**Files:**
- Modify: `swingbot/core/charts/chart_annotations.py` (add the pair)
- Modify: `swingbot/core/charts/trade_chart.py:165-181, 868-872`
- Test: `tests/test_chart_annotations.py`

**Interfaces:**
- Consumes: `draw_legend_block` module from Task 4.
- Produces: `draw_level(ax, price, name, color, *, y_offset=0, tag_fontsize=9.0) -> None`.

- [ ] **Step 1: Write the failing test**

```python
def test_draw_level_puts_the_name_left_and_the_price_on_the_axis():
    from swingbot.core.charts.chart_annotations import draw_level
    fig, ax = plt.subplots()
    try:
        ax.set_ylim(200, 260)
        draw_level(ax, 240.69, "SL", "#ef5350")
        anns = ax.texts
        names = [a.get_text().strip() for a in anns]
        assert "SL" in names, f"level name missing: {names}"
        assert any("240.69" in n for n in names), f"price tag missing: {names}"
        assert not any("SL" in n and "240.69" in n for n in names), \
            "name and price must be two separate annotations, not one combined pill"
    finally:
        plt.close(fig)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python scripts/testrun.py file tests/test_chart_annotations.py::test_draw_level_puts_the_name_left_and_the_price_on_the_axis`
Expected: FAIL with `ImportError: cannot import name 'draw_level'`.

- [ ] **Step 3: Implement the pair**

```python
def draw_level(ax, price, name, color, *, y_offset: int = 0, tag_fontsize: float = 9.0) -> None:
    """A plan level rendered the way lightweight-charts' createPriceLine does
    (chart-init.js:8-12): the short name at the LEFT end of the line, the price
    alone on a coloured tag riding the right price axis.

    tag_fontsize defaults ABOVE TradingView's own size on purpose -- these PNGs
    are read in Discord on a phone, where the image is downscaled.

    y_offset is screen-space offset points, not data units, so the collision
    nudge moves only where the tag renders and never the anchor price (and so
    never the level line itself).
    """
    ax.annotate(
        f" {name} ", xy=(0.0, price), xycoords=("axes fraction", "data"),
        xytext=(3, 0), textcoords="offset points", va="center", ha="left",
        fontsize=tag_fontsize - 1.5, fontweight="bold", color=color, zorder=6,
        bbox=dict(boxstyle="square,pad=0.18", fc=CHART_BG, ec="none", alpha=0.7),
        annotation_clip=False,
    )
    ax.annotate(
        f" {price:,.2f} ", xy=(1.0, price), xycoords=("axes fraction", "data"),
        xytext=(2, y_offset), textcoords="offset points", va="center", ha="left",
        fontsize=tag_fontsize, fontweight="bold", color=CHART_BG, zorder=6,
        bbox=dict(boxstyle="round,pad=0.25", fc=color, ec="none"),
        annotation_clip=False,
    )
```

- [ ] **Step 4: Run the test**

Run: `python scripts/testrun.py file tests/test_chart_annotations.py`
Expected: PASS.

- [ ] **Step 5: Swap the call site**

At `trade_chart.py:868-872`, replace the combined-text loop. The collision logic is unchanged — only what gets drawn changes:

```python
        for price, color, label in sorted(raw_labels, key=lambda item: item[0]):
            overlaps = any(abs(price - placed_y) < _pill_overlap_gap for placed_y in _placed_pill_ys)
            draw_level(ax, price, label, color, y_offset=10 if overlaps else 0)
            _placed_pill_ys.append(price)
```

Shorten the names at `trade_chart.py:841-849` so they fit at the line's left end — `"Entry / current price"` becomes `"Entry"`, `"Entry (plan)"` becomes `"Entry"`, `"Target 1"` becomes `"TP1"`, `"Target 2"` becomes `"TP2"`, `"Stop"` becomes `"SL"`, `"Current price"` becomes `"Last"`. Delete `_draw_level_pill` (lines 165-181) and its imports once nothing calls it — grep to confirm.

- [ ] **Step 6: Run the full suite**

Run: `python scripts/testrun.py full`
Expected: `0 failed`.

- [ ] **Step 7: Look at the output, at Discord's scale**

Save the PNG and view it at ~40% zoom, which approximates Discord's inline render. Every price tag must stay readable; raise `tag_fontsize` if not. This is the check the spec flagged as impossible to fully automate.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/charts/chart_annotations.py swingbot/core/charts/trade_chart.py tests/test_chart_annotations.py
git commit -m "feat(charts): split level pills into line-end name plus price tag

_draw_level_pill already anchored to the axis gutter, so this splits
rather than replaces it: the short name reads off the left end of its own
line and the tag carries the price alone, matching what
createPriceLine(title=..., axisLabelVisible=true) renders. Tag font sits
above TradingView's own size because these are read in Discord on a phone."
```

---

### Task 7: Grid hairlines and the final pass

**Files:**
- Modify: `swingbot/core/charts/chart_style.py:126-144` (`PRO_STYLE`)
- Test: `tests/test_chart_layout.py`, `tests/test_chart_theme.py` (must stay green)

- [ ] **Step 1: Switch the grid to solid hairlines**

In `PRO_STYLE`, change `gridstyle="--"` to `gridstyle="-"` and add `"grid.linewidth": 0.5` to the `rc` dict. Matches `chart-init.js:26`, which draws plain one-pixel lines. **Do not touch `gridcolor`** — it is `GRID_COLOR`, which is palette and pinned by `test_chart_theme.py`.

- [ ] **Step 2: Run every chart test**

Run: `python scripts/testrun.py file tests/test_chart_theme.py`
Expected: PASS — the palette is untouched.

Run: `python scripts/testrun.py file tests/test_chart_layout.py`
Expected: all PASS, including the three that failed in Task 1.

- [ ] **Step 3: Full suite**

Run: `python scripts/testrun.py full`
Expected: `0 failed`. Note the pass count will have risen by the new tests; a changed count is not a failure.

- [ ] **Step 4: Side-by-side check**

Render one chart and compare against `exports/trade_charts/KLAC_84ab7e58.png`, the baseline this plan was written from. Walk the spec's eight-row deviation table and confirm each row now matches the right-hand column. Anything still failing goes in the completion note rather than being quietly accepted.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/charts/chart_style.py
git commit -m "style(charts): solid grid hairlines

chart-init.js:26 draws plain one-pixel grid lines; the dashed grid was the
last obviously non-TradingView finish. gridcolor is untouched -- it is
palette, pinned by test_chart_theme.py."
```

---

## Self-Review

**Spec coverage.** All eight deviation rows are covered: 1 → Tasks 1, 2; 2 → Task 3; 3 → Task 3; 4 → Task 4; 5 → Tasks 5, 6; 6 → Task 2; 7 → Task 4; 8 → Task 7. Spec §6's three verification layers map to Task 1 (structural), the "look at the output" step in every task (render-and-look), and the `testrun.py full` gate. Spec §7's three risks each have a mitigation step: volume crowding (Task 2 Step 7), profile over candles (Task 3 Step 6), Discord legibility (Task 6 Step 7).

**Placeholders.** None. Every code step carries the code; every test step carries the test and the exact command.

**Type consistency.** `_draw_volume_profile_overlay` drops the `fig` parameter in Task 3 and the plan says so explicitly at its Interfaces block and again at the call site. `draw_legend_block`'s `overlays` list is created in Task 4 and extended in Task 5 under the same name. `draw_level` replaces `_draw_level_pill` with the same `y_offset` semantics, so Task 6's untouched collision loop still reads correctly.

**Known soft spot.** Task 1 Step 2 is the only step whose outcome is not predicted — by design, it is the measurement the spec refused to guess. Task 2 Step 6 asks whether the dead-space test flipped as a side effect; if it did not, Task 7 needs a step to chase the real cause, and the executor should raise that rather than move on.

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

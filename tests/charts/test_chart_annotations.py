"""chart_annotations: the top-left legend block and the level name/price pair
that replaced mplfinance's centered title, its boxed legend, and the old
combined "{name} {price}" pills.
"""
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


@pytest.mark.parametrize("value,expected", [
    (21_400_000, "21.4M"),
    (2_100_000_000, "2.1B"),
    (4_300, "4.3K"),
    (812, "812"),
    (0, "0"),
    (None, "0"),
])
def test_volume_is_formatted_as_a_rounded_magnitude(value, expected):
    """A raw integer is unreadable at the size Discord renders these."""
    from swingbot.core.charts.chart_annotations import _fmt_volume
    assert _fmt_volume(value) == expected


def test_draw_level_puts_the_name_left_and_the_price_on_the_axis():
    from swingbot.core.charts.chart_annotations import draw_level
    fig, ax = plt.subplots()
    try:
        ax.set_ylim(200, 260)
        draw_level(ax, 240.69, "SL", "#ef5350")
        names = [a.get_text().strip() for a in ax.texts]
        assert "SL" in names, f"level name missing: {names}"
        assert any("240.69" in n for n in names), f"price tag missing: {names}"
        assert not any("SL" in n and "240.69" in n for n in names), \
            "name and price must be two separate annotations, not one combined pill"
    finally:
        plt.close(fig)


def test_draw_level_anchors_name_left_and_price_right():
    """The name rides the left end of its own line, the price the right axis --
    what createPriceLine(title=..., axisLabelVisible=true) renders."""
    from swingbot.core.charts.chart_annotations import draw_level
    fig, ax = plt.subplots()
    try:
        ax.set_ylim(200, 260)
        draw_level(ax, 240.69, "SL", "#ef5350")
        by_text = {a.get_text().strip(): a for a in ax.texts}
        assert by_text["SL"].xy[0] == 0.0
        price_ann = next(a for t, a in by_text.items() if "240.69" in t)
        assert price_ann.xy[0] == 1.0
    finally:
        plt.close(fig)


def test_draw_level_offset_moves_the_tag_not_the_anchor():
    """The collision nudge must never move the real anchor price, or the level
    line itself would shift."""
    from swingbot.core.charts.chart_annotations import draw_level
    fig, ax = plt.subplots()
    try:
        ax.set_ylim(200, 260)
        draw_level(ax, 240.69, "SL", "#ef5350", y_offset=10)
        price_ann = next(a for a in ax.texts if "240.69" in a.get_text())
        assert price_ann.xy[1] == 240.69, "anchor price moved"
        assert price_ann.xyann[1] == 10, "offset was not applied to the tag"
    finally:
        plt.close(fig)

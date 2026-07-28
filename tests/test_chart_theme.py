# tests/test_chart_theme.py
from swingbot.core.charts import chart_style as cs


def test_theme_dict_matches_module_constants():
    assert cs.THEME["bg-1"] == cs.CHART_BG
    assert cs.THEME["border-1"] == cs.GRID_COLOR
    assert cs.THEME["border-2"] == cs.SPINE_COLOR
    assert cs.THEME["text-1"] == cs.TEXT_COLOR
    assert cs.THEME["text-3"] == cs.MUTED_TEXT_COLOR
    assert cs.THEME["up"] == cs.UP_COLOR
    assert cs.THEME["down"] == cs.DOWN_COLOR
    assert cs.THEME["accent"] == cs.ENTRY_COLOR
    assert cs.THEME["warn"] == cs.CURRENT_PRICE_COLOR
    assert cs.THEME["purple"] == cs.TARGET2_COLOR


def test_theme_matches_tokens_css():
    """Parse tokens.css and compare the shared hex values byte-for-byte."""
    import re
    from pathlib import Path
    css = Path("swingbot/admin/static/tokens.css").read_text(encoding="utf-8")
    tokens = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", css))
    for key in ("bg-1", "border-1", "border-2", "text-1", "text-3", "up", "down", "accent", "warn", "purple"):
        assert tokens[key].lower() == cs.THEME[key].lower(), key

"""The vendored admin fonts (spec v240 §2, §11).

Jost is the one face of the SPA. It is proportional, so tables keep their
digits aligned only through its `tnum` (tabular figures) feature, and every
loss prints a true minus (U+2212). These tests open the vendored woff2
files with fontTools, so a future swap of the files cannot silently lose
either. The latin-ext subset holds no digits: figures always come from the
latin file, which is the one checked for `tnum`, digits and U+2212.

`vendor/inter/` stays while swingbot/core/charts/chart_style.py names
`inter-500.woff2` for the Discord chart PNGs.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / "swingbot/admin/static/vendor"
JOST_LATIN = VENDOR / "jost" / "jost-latin-wght-normal.woff2"
JOST_LATIN_EXT = VENDOR / "jost" / "jost-latin-ext-wght-normal.woff2"
JOST_LICENSE = VENDOR / "jost" / "LICENSE.txt"
TRUE_MINUS = 0x2212


def _font(path: Path):
    from fontTools.ttLib import TTFont
    return TTFont(str(path))


def _gsub_features(font) -> set[str]:
    if "GSUB" not in font:
        return set()
    return {record.FeatureTag for record in font["GSUB"].table.FeatureList.FeatureRecord}


def test_brotli_is_installed_so_woff2_can_be_read():
    import brotli  # noqa: F401  (requirements.txt, test-only)


@pytest.mark.parametrize("path", [JOST_LATIN, JOST_LATIN_EXT], ids=lambda p: p.name)
def test_each_jost_subset_is_a_real_woff2(path):
    assert path.is_file(), path
    assert path.stat().st_size > 10_000, path
    assert path.read_bytes()[:4] == b"wOF2", path


def test_the_licence_is_the_sil_ofl_1_1_naming_jost():
    text = JOST_LICENSE.read_text(encoding="utf-8")
    assert "The Jost Project Authors" in text
    assert "SIL Open Font License, Version 1.1" in text


def test_the_latin_subset_carries_tabular_figures():
    assert "tnum" in _gsub_features(_font(JOST_LATIN))


@pytest.mark.parametrize("path", [JOST_LATIN, JOST_LATIN_EXT], ids=lambda p: p.name)
def test_each_subset_is_variable_from_100_to_900(path):
    axes = {axis.axisTag: (axis.minValue, axis.maxValue) for axis in _font(path)["fvar"].axes}
    assert axes.get("wght") == (100, 900)


def test_the_latin_subset_maps_every_digit_and_the_true_minus():
    cmap = _font(JOST_LATIN).getBestCmap()
    for code in [ord(d) for d in "0123456789"] + [TRUE_MINUS]:
        assert code in cmap, hex(code)


def test_the_inter_file_the_discord_charts_name_is_still_vendored():
    assert (VENDOR / "inter" / "inter-500.woff2").is_file()

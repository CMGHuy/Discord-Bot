"""v208 V208-5: the Benchmark tab's proxy key (index "Global Constraints")."""
import pathlib

from swingbot import config

REPO = pathlib.Path(__file__).resolve().parents[1]
ATTR = "BENCHMARK_PROXY_SYMBOLS"
DEFAULT = "^IXIC=ONEQ,^DJI=DIA"


def _field(attr=ATTR):
    return next(f for f in config.FIELDS if f.attr == attr)


def test_is_a_hot_reloadable_data_sources_text_key():
    field = _field()
    assert (field.key, field.section, field.type, field.default) == (ATTR, "Data Sources", "text", DEFAULT)
    assert field.hot_reloadable is True
    assert field.search_class == "excluded"
    assert "v208" in field.help


def test_sits_after_the_v204_snapshot_knobs():
    attrs = [f.attr for f in config.FIELDS]
    assert attrs.index(ATTR) == attrs.index("ADMIN_STALE_SNAPSHOT_EXTENDED_S") + 1


def test_default_casts_to_itself():
    assert config._cast(_field(), _field().default) == DEFAULT


def test_env_example_lists_it_with_its_default():
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    assert f"\n{ATTR}={DEFAULT}\n" in text


def test_the_tape_key_is_untouched():
    assert _field("TAPE_PROXY_SYMBOLS").default == "^GSPC=SPY,^NDX=QQQ,^DJI=DIA,^VIX=VIXY,SI=F=SLV"

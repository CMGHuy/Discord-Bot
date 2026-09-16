"""Cross-store checks that only become possible after all of Part 2."""
import pathlib

from scripts.db.parity_report import STORES


PART2_STORES = {"trades", "plans", "starred_plans", "account", "journal", "state", "watchlist"}
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_every_part2_store_has_a_parity_entry():
    missing = PART2_STORES - set(STORES)
    assert not missing, f"no parity registration for: {sorted(missing)}"


def test_every_part2_store_has_an_importer():
    scripts = {path.stem for path in (REPO_ROOT / "scripts" / "db").glob("import_*.py")}
    expected = {f"import_{name}" for name in PART2_STORES}
    expected = {name.replace("import_starred_plans", "import_starred") for name in expected}
    assert expected <= scripts, f"missing importers: {sorted(expected - scripts)}"


def test_no_part2_store_defaults_to_a_stage_other_than_json():
    from swingbot import config
    from swingbot.core.db import stages
    configured = stages.parse(config.DB_STORES)
    assert not (PART2_STORES & set(configured)), "a committed config promoted a Part 2 store"

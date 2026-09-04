import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "dev"))


def test_undefined_names_flags_a_broken_module(tmp_path):
    import testrun

    bad = tmp_path / "bad_module.py"
    bad.write_text("def go():\n    return not_a_real_name\n")

    found = testrun.undefined_names([str(bad)])

    assert len(found) == 1
    assert "not_a_real_name" in found[0]


def test_undefined_names_is_clean_on_a_good_module(tmp_path):
    import testrun

    good = tmp_path / "good_module.py"
    good.write_text("import os\n\n\ndef go():\n    return os.getcwd()\n")

    assert testrun.undefined_names([str(good)]) == []


def test_the_repo_itself_has_no_undefined_names():
    """The gate must be green on the tree it is about to police."""
    import testrun

    assert testrun.undefined_names() == []

"""Checks that only make sense once every Part 3 task has landed."""
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]


def test_the_committed_env_example_promotes_no_store():
    """Exit criterion 7: DB_STORES is empty in every committed file. A
    promotion is a per-deployment setting, never a committed default."""
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    lines = re.findall(r"^DB_STORES=(.*)$", text, flags=re.MULTILINE)
    assert lines, ".env.example has no DB_STORES= line"
    assert all(value.strip() == "" for value in lines), (
        f".env.example promotes a store: DB_STORES={lines}"
    )

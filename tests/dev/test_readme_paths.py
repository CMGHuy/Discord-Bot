"""Every `.py` path README.md names must exist (spec v149 H3).

The README's module lists went stale when v27 moved `swingbot/core/` into
packages: it named bare files (`levels.py`) that no longer sat where a reader
would look. Requiring every backticked `.py` token to be a full, existing
repo-relative path is what gives this test teeth. A check that only looked at
tokens starting with `swingbot/` would have passed on the stale README.
"""
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]

# A backticked token with no whitespace that ends in `.py`: a path, never a
# command line such as `python bot.py`.
_PY_TOKEN = re.compile(r"`([^`\s]+\.py)`")


def py_tokens(text: str) -> list[str]:
    return sorted(set(_PY_TOKEN.findall(text)))


def missing_paths(text: str, repo: pathlib.Path) -> list[str]:
    def exists(token: str) -> bool:
        if token.startswith("/") or ".." in token.split("/"):
            return False
        return (repo / token).is_file()

    return [token for token in py_tokens(text) if not exists(token)]


def test_a_bare_module_name_is_reported_missing(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "levels.py").write_text("", encoding="utf-8")
    text = "- `levels.py` is stale, `pkg/levels.py` is right, run `python bot.py`"
    assert missing_paths(text, tmp_path) == ["levels.py"]


def test_a_path_outside_the_repo_is_reported_missing(tmp_path):
    assert missing_paths("see `../other/x.py` and `/abs/y.py`", tmp_path) == [
        "../other/x.py", "/abs/y.py"]


def test_every_py_path_the_readme_names_exists():
    text = (REPO / "README.md").read_text(encoding="utf-8")
    missing = missing_paths(text, REPO)
    assert not missing, (
        "README.md names .py paths that do not exist (write the full "
        "repo-relative path):\n  " + "\n  ".join(missing))

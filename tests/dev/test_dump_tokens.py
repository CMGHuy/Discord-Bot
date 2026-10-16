"""scripts/dev/dump_tokens.py: the Python half of the token resolver pair
(spec v167 § 1). frontend/src/app/ui/resolve-token.spec.ts holds the
TypeScript half to the same committed fixture."""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "dev"))

import dump_tokens as dt  # noqa: E402


def test_strip_comments_removes_block_comments_across_lines():
    assert dt.strip_comments("a /* x\n { y } */ b") == "a  b"


def test_parse_root_reads_every_root_block_and_later_wins():
    css = ":root { --a: #111; --b: 1px; }\n:root {\n  --a:   #222 ;\n}\n"
    assert dt.parse_root(css) == {"a": "#222", "b": "1px"}


def test_parse_root_drops_media_and_supports_blocks():
    css = (":root { --gap: 14px; }\n"
           "@media (max-width: 639px) { :root { --gap: 10px; } }\n"
           "@supports (color: color-mix(in srgb, red, blue)) { :root { --x: 1; } }\n")
    assert dt.parse_root(css) == {"gap": "14px"}


def test_parse_root_ignores_comments_and_non_root_rules():
    css = "/* :root { --ghost: 1; } */ body { --local: 2; } :root { --kept: 3; }"
    assert dt.parse_root(css) == {"kept": "3"}


def test_parse_root_collapses_whitespace_in_values():
    css = ":root { --shadow: 0 8px 24px\n      rgba(0, 0, 0, .55); }"
    assert dt.parse_root(css) == {"shadow": "0 8px 24px rgba(0, 0, 0, .55)"}


def test_resolve_follows_var_hops_to_a_literal():
    declared = {"navy": "#070b14", "bg": "var(--navy)", "scrim": "var(--bg)",
                "gap": "calc(2px * var(--scale))", "scale": "1"}
    assert dt.resolve(declared) == {"navy": "#070b14", "bg": "#070b14", "scrim": "#070b14",
                                    "gap": "calc(2px * 1)", "scale": "1"}


def test_resolve_names_an_undefined_reference():
    with pytest.raises(KeyError, match="--missing is not defined"):
        dt.resolve({"bg": "var(--missing)"})


def test_resolve_rejects_a_cycle():
    with pytest.raises(ValueError, match="cycle at --a"):
        dt.resolve({"a": "var(--b)", "b": "var(--a)"})


def test_resolve_rejects_fallback_syntax():
    with pytest.raises(ValueError, match="only plain var"):
        dt.resolve({"a": "#fff", "b": "var(--a, #000)"})


def test_resolve_tokens_merges_files_in_order_and_sorts(tmp_path):
    palette = tmp_path / "palette.css"
    tokens = tmp_path / "tokens.css"
    palette.write_text(":root { --navy-950: #070b14; }", encoding="utf-8")
    tokens.write_text(":root { --bg: var(--navy-950); --accent: #7cc4ff; }", encoding="utf-8")
    result = dt.resolve_tokens((palette, tokens))
    assert result == {"accent": "#7cc4ff", "bg": "#070b14", "navy-950": "#070b14"}
    assert list(result) == sorted(result)


def _point_at(monkeypatch, tmp_path, css):
    tokens = tmp_path / "tokens.css"
    tokens.write_text(css, encoding="utf-8")
    monkeypatch.setattr(dt, "STYLE_FILES", (tokens,))
    monkeypatch.setattr(dt, "FIXTURE", tmp_path / "resolved_tokens.json")


def test_main_writes_the_fixture_and_check_passes_on_it(monkeypatch, tmp_path):
    _point_at(monkeypatch, tmp_path, ":root { --b: 2px; --a: var(--b); }")
    assert dt.main([]) == 0
    assert (tmp_path / "resolved_tokens.json").read_bytes() == b'{\n  "a": "2px",\n  "b": "2px"\n}\n'
    assert dt.main(["--check"]) == 0


def test_check_fails_and_names_the_first_stale_token(monkeypatch, tmp_path, capsys):
    _point_at(monkeypatch, tmp_path, ":root { --a: 1px; }")
    dt.main([])
    (tmp_path / "tokens.css").write_text(":root { --a: 2px; }", encoding="utf-8")
    assert dt.main(["--check"]) == 1
    assert "--a" in capsys.readouterr().out


def test_the_committed_fixture_is_current():
    """A palette.css / tokens.css edit without `python scripts/dev/dump_tokens.py`
    fails here, in the fast tier (test_chart_theme.py runs only in the slow tier)."""
    assert dt.main(["--check"]) == 0

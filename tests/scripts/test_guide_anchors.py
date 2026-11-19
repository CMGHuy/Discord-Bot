"""v235 V235-6: the guide anchor fixture generator (scripts/dev/guide_anchors.py)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

import guide_anchors as ga  # noqa: E402


def _chapter(root: Path, order: int, slug: str, body: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{order:02d}-{slug}.md").write_text(
        f"---\ntitle: T {slug}\nslug: {slug}\norder: {order}\n"
        f"reviewed_for: 2.19.2\nsources: []\n---\n{body}", encoding="utf-8")


def _args(guide: Path, out: Path, *extra: str) -> list[str]:
    return ["--guide-dir", str(guide), "--out", str(out), *extra]


def test_build_lists_anchors_per_slug_sorted(tmp_path):
    _chapter(tmp_path, 3, "pipeline", "## Scan run\n### Gates\n## Gates\n")
    _chapter(tmp_path, 1, "what-it-is", "## The notice\n")
    data = ga.build(tmp_path)
    assert list(data["chapters"]) == ["pipeline", "what-it-is"]
    assert data["chapters"]["pipeline"] == ["scan-run", "gates", "gates-2"]
    assert data["chapters"]["what-it-is"] == ["the-notice"]


def test_missing_guide_renders_an_empty_two_space_fixture(tmp_path):
    assert ga.render(ga.build(tmp_path / "missing")) == '{\n  "chapters": {}\n}\n'


def test_main_writes_the_fixture_then_check_passes(tmp_path):
    guide, out = tmp_path / "guide", tmp_path / "web" / "anchors.json"
    _chapter(guide, 1, "what-it-is", "## The notice\n")
    assert ga.main(_args(guide, out)) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == {"chapters": {"what-it-is": ["the-notice"]}}
    assert ga.main(_args(guide, out, "--check")) == 0


def test_check_fails_on_drift_and_leaves_the_file_alone(tmp_path, capsys):
    guide, out = tmp_path / "guide", tmp_path / "anchors.json"
    _chapter(guide, 1, "what-it-is", "## The notice\n")
    ga.main(_args(guide, out))
    before = out.read_text(encoding="utf-8")
    _chapter(guide, 1, "what-it-is", "## The notice\n## Swing horizons\n")
    assert ga.main(_args(guide, out, "--check")) == 1
    assert "stale" in capsys.readouterr().err
    assert out.read_text(encoding="utf-8") == before
    assert ga.main(_args(guide, tmp_path / "absent.json", "--check")) == 1
    _chapter(guide, 1, "what-it-is", "## The notice\n")
    out.write_bytes(before.replace("\n", "\r\n").encode("utf-8"))
    assert ga.main(_args(guide, out, "--check")) == 0


def test_malformed_chapter_exits_2(tmp_path, capsys):
    guide = tmp_path / "guide"
    guide.mkdir()
    (guide / "01-what-it-is.md").write_text("no front matter\n", encoding="utf-8")
    assert ga.main(_args(guide, tmp_path / "anchors.json")) == 2
    assert "01-what-it-is.md" in capsys.readouterr().err
    assert ga.FIXTURE.as_posix() == "frontend/src/app/workspaces/guide/guide-anchors.json"

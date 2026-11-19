"""Write (or --check) the guide anchor fixture, from raw headings (v235)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot.admin.guide.chapters import GuideFormatError, load_chapters  # noqa: E402

FIXTURE = Path("frontend/src/app/workspaces/guide/guide-anchors.json")


def build(root: Path | None = None) -> dict:
    chapters = sorted(load_chapters(root), key=lambda chapter: chapter.slug)
    return {"chapters": {c.slug: [h.anchor for h in c.headings] for c in chapters}}


def render(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _parse(argv):
    parser = argparse.ArgumentParser(description="Write or check the guide anchor fixture.")
    parser.add_argument("--check", action="store_true", help="exit 1 when stale")
    parser.add_argument("--guide-dir", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=ROOT / FIXTURE)
    return parser.parse_args(argv)


def _check(out: Path, text: str) -> int:
    current = out.read_text(encoding="utf-8").replace("\r\n", "\n") if out.exists() else None
    if current == text:
        print("guide_anchors: fixture is current")
        return 0
    print(f"guide_anchors: {out} is stale -- run python scripts/dev/guide_anchors.py",
          file=sys.stderr)
    return 1


def main(argv=None) -> int:
    args = _parse(argv)
    try:
        data = build(args.guide_dir)
    except GuideFormatError as exc:
        print(f"guide_anchors: {exc}", file=sys.stderr)
        return 2
    text = render(data)
    if args.check:
        return _check(args.out, text)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8", newline="\n")
    print(f"guide_anchors: wrote {len(data['chapters'])} chapter(s) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
